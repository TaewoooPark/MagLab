"""Workspace-local primitive ingestion and review scaffolding.

This module implements the deterministic core for the plan/05 primitive
ingestion pipeline. It deliberately does not execute user-provided code. A
local SVG or JSON descriptor is copied into a workspace catalog package, basic
quality checks are recorded, and a human-review scaffold is written next to the
source material.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

WORKSPACE_CATALOG = Path(".maglab") / "figure" / "primitives" / "catalog"

_ALLOWED_DESCRIPTOR_KEYS = {
    "name",
    "category",
    "tags",
    "description",
    "parameters",
    "physics_convention",
    "references",
    "provenance",
    "preview",
    "journal_styles",
    "svg",
    "svg_path",
}
_SVG_EXTENSIONS = {".svg"}
_JSON_EXTENSIONS = {".json"}
_PARAMETER_TYPES = {"float", "int", "str", "bool", "enum", "color", "length"}


@dataclass(frozen=True)
class QualityCheck:
    """Single deterministic primitive-ingest check."""

    name: str
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "message": self.message}


@dataclass(frozen=True)
class PrimitiveIngestResult:
    """Paths and quality result produced by ``ingest_primitive``."""

    name: str
    status: str
    package_dir: Path
    primitive_md: Path
    descriptor_json: Path
    review_md: Path
    quality_json: Path
    preview_svg: Path | None
    checks: tuple[QualityCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "package_dir": str(self.package_dir),
            "primitive_md": str(self.primitive_md),
            "descriptor_json": str(self.descriptor_json),
            "review_md": str(self.review_md),
            "quality_json": str(self.quality_json),
            "preview_svg": str(self.preview_svg) if self.preview_svg else None,
            "checks": [check.as_dict() for check in self.checks],
        }


class PrimitiveIngestError(ValueError):
    """Raised when a primitive source cannot be ingested deterministically."""


def ingest_primitive(
    source: str | Path,
    *,
    workspace: str | Path = ".",
    metadata: Mapping[str, Any] | None = None,
    overwrite: bool = False,
) -> PrimitiveIngestResult:
    """Ingest a local SVG or JSON primitive descriptor into a workspace catalog.

    The output package is written to
    ``<workspace>/.maglab/figure/primitives/catalog/<primitive-name>/`` and
    contains:

    - ``PRIMITIVE.md``: registry metadata with YAML-like frontmatter.
    - ``primitive.json``: normalized descriptor for review/promotion.
    - ``preview.svg``: copied vector source when available.
    - ``quality.json``: deterministic check report.
    - ``REVIEW.md``: promotion checklist for a human or figure-designer agent.

    Parameters
    ----------
    source:
        Local ``.svg`` or ``.json`` descriptor path.
    workspace:
        Workspace root where the local primitive catalog should be created.
    metadata:
        Optional metadata overrides, useful when the source is a bare SVG.
    overwrite:
        Replace an existing workspace primitive package when true.
    """

    source_path = Path(source).expanduser().resolve()
    workspace_path = Path(workspace).expanduser().resolve()
    if not source_path.is_file():
        raise PrimitiveIngestError(f"Primitive source does not exist: {source_path}")

    source_kind = _source_kind(source_path)
    descriptor = _load_descriptor(source_path, source_kind)
    descriptor = _merge_metadata(descriptor, metadata or {})
    descriptor = _normalize_descriptor(descriptor, source_path)

    name = descriptor["name"]
    package_dir = workspace_path / WORKSPACE_CATALOG / name
    if package_dir.exists():
        if not overwrite:
            raise PrimitiveIngestError(
                f"Workspace primitive already exists: {package_dir}. "
                "Pass overwrite=True to replace it."
            )
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    preview_svg = _write_preview_svg(package_dir, source_path, source_kind, descriptor)
    primitive_md = package_dir / "PRIMITIVE.md"
    descriptor_json = package_dir / "primitive.json"
    review_md = package_dir / "REVIEW.md"
    quality_json = package_dir / "quality.json"

    checks = tuple(_run_quality_checks(descriptor, preview_svg))
    status = _status_from_checks(checks)

    primitive_md.write_text(_primitive_md(descriptor), encoding="utf-8")
    descriptor_json.write_text(
        json.dumps(_descriptor_for_disk(descriptor, preview_svg), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    quality_json.write_text(
        json.dumps(
            {
                "name": name,
                "status": status,
                "generated_at": _utc_now(),
                "checks": [check.as_dict() for check in checks],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    review_md.write_text(_review_md(descriptor, checks), encoding="utf-8")

    return PrimitiveIngestResult(
        name=name,
        status=status,
        package_dir=package_dir,
        primitive_md=primitive_md,
        descriptor_json=descriptor_json,
        review_md=review_md,
        quality_json=quality_json,
        preview_svg=preview_svg,
        checks=checks,
    )


def _source_kind(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix in _SVG_EXTENSIONS:
        return "svg"
    if suffix in _JSON_EXTENSIONS:
        return "json"
    raise PrimitiveIngestError(
        f"Unsupported primitive source format: {source_path.suffix or '<none>'}. Use .svg or .json."
    )


def _load_descriptor(source_path: Path, source_kind: str) -> dict[str, Any]:
    if source_kind == "svg":
        return {
            "name": source_path.stem,
            "category": "",
            "tags": [],
            "description": "",
            "parameters": [],
            "physics_convention": "",
            "references": [],
            "provenance": {"source_path": str(source_path), "source_format": "svg"},
            "journal_styles": [],
        }

    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrimitiveIngestError(f"Invalid JSON primitive descriptor: {exc}") from exc
    if not isinstance(data, dict):
        raise PrimitiveIngestError("Primitive JSON descriptor must be an object.")
    unknown = set(data) - _ALLOWED_DESCRIPTOR_KEYS
    if unknown:
        raise PrimitiveIngestError(
            "Unsupported primitive descriptor key(s): " + ", ".join(sorted(unknown))
        )
    data.setdefault("provenance", {})
    if isinstance(data["provenance"], dict):
        data["provenance"] = {
            **data["provenance"],
            "source_path": str(source_path),
            "source_format": "json",
        }
    return data


def _merge_metadata(
    descriptor: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    unknown = set(metadata) - _ALLOWED_DESCRIPTOR_KEYS
    if unknown:
        raise PrimitiveIngestError(
            "Unsupported primitive metadata key(s): " + ", ".join(sorted(unknown))
        )
    merged = dict(descriptor)
    for key, value in metadata.items():
        if value is not None:
            merged[key] = value
    return merged


def _normalize_descriptor(descriptor: Mapping[str, Any], source_path: Path) -> dict[str, Any]:
    name = _slugify(str(descriptor.get("name") or source_path.stem))
    if not name:
        raise PrimitiveIngestError("Primitive name is required.")

    tags = descriptor.get("tags", [])
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise PrimitiveIngestError("Primitive tags must be a list of strings.")

    parameters = descriptor.get("parameters", [])
    if not isinstance(parameters, list):
        raise PrimitiveIngestError("Primitive parameters must be a list.")
    normalized_parameters: list[dict[str, Any]] = []
    for idx, parameter in enumerate(parameters, start=1):
        if not isinstance(parameter, dict):
            raise PrimitiveIngestError(f"Primitive parameter #{idx} must be an object.")
        param_name = str(parameter.get("name", "")).strip()
        param_type = str(parameter.get("type", "")).strip()
        if not param_name or not param_type:
            raise PrimitiveIngestError(f"Primitive parameter #{idx} must include name and type.")
        if param_type not in _PARAMETER_TYPES:
            raise PrimitiveIngestError(
                f"Primitive parameter {param_name!r} has unsupported type {param_type!r}."
            )
        normalized_parameters.append(dict(parameter))

    references = descriptor.get("references", [])
    if isinstance(references, str):
        references = [references]
    if not isinstance(references, list) or not all(isinstance(ref, str) for ref in references):
        raise PrimitiveIngestError("Primitive references must be a list of strings.")

    journal_styles = descriptor.get("journal_styles", [])
    if isinstance(journal_styles, str):
        journal_styles = [journal_styles]
    if not isinstance(journal_styles, list) or not all(
        isinstance(style, str) for style in journal_styles
    ):
        raise PrimitiveIngestError("Primitive journal_styles must be a list of strings.")

    provenance = descriptor.get("provenance", {})
    if not isinstance(provenance, dict):
        raise PrimitiveIngestError("Primitive provenance must be an object.")
    provenance = {
        **provenance,
        "ingested_at": _utc_now(),
        "ingest_pipeline": "maglab.figure.primitives.ingest",
    }

    return {
        "name": name,
        "category": str(descriptor.get("category", "") or ""),
        "tags": sorted({tag.strip() for tag in tags if tag.strip()}),
        "description": str(descriptor.get("description", "") or ""),
        "parameters": normalized_parameters,
        "physics_convention": str(descriptor.get("physics_convention", "") or ""),
        "references": references,
        "provenance": provenance,
        "preview": descriptor.get("preview"),
        "journal_styles": journal_styles,
        "svg": descriptor.get("svg"),
        "svg_path": descriptor.get("svg_path"),
    }


def _write_preview_svg(
    package_dir: Path,
    source_path: Path,
    source_kind: str,
    descriptor: Mapping[str, Any],
) -> Path | None:
    svg_text = None
    if source_kind == "svg":
        svg_text = source_path.read_text(encoding="utf-8")
    elif descriptor.get("svg"):
        svg_text = str(descriptor["svg"])
    elif descriptor.get("svg_path"):
        svg_path = Path(str(descriptor["svg_path"]))
        if not svg_path.is_absolute():
            svg_path = source_path.parent / svg_path
        if not svg_path.is_file():
            raise PrimitiveIngestError(f"Descriptor svg_path does not exist: {svg_path}")
        svg_text = svg_path.read_text(encoding="utf-8")

    if svg_text is None:
        return None

    preview_path = package_dir / "preview.svg"
    preview_path.write_text(svg_text, encoding="utf-8")
    return preview_path


def _run_quality_checks(
    descriptor: Mapping[str, Any],
    preview_svg: Path | None,
) -> list[QualityCheck]:
    checks: list[QualityCheck] = []
    checks.append(QualityCheck("name", "pass", f"Primitive slug is {descriptor['name']}."))

    for field in ("category", "description", "physics_convention"):
        value = str(descriptor.get(field, "") or "").strip()
        status = "pass" if value else "warn"
        message = f"{field} is present." if value else f"{field} is missing; review required."
        checks.append(QualityCheck(field, status, message))

    checks.append(
        QualityCheck(
            "tags",
            "pass" if descriptor.get("tags") else "warn",
            "Search tags are present."
            if descriptor.get("tags")
            else "No search tags; primitive discovery will be weak.",
        )
    )
    checks.append(
        QualityCheck(
            "parameters",
            "pass" if descriptor.get("parameters") else "warn",
            "Typed parameters are present."
            if descriptor.get("parameters")
            else "No typed parameters; primitive is static until parameterized.",
        )
    )
    checks.append(
        QualityCheck(
            "references",
            "pass" if descriptor.get("references") else "warn",
            "Reference list is present."
            if descriptor.get("references")
            else "No references; add DOI/URL before promotion when possible.",
        )
    )

    if preview_svg is None:
        checks.append(
            QualityCheck(
                "preview_svg",
                "warn",
                "No SVG preview was provided; registry metadata can be reviewed only.",
            )
        )
        return checks

    svg_text = preview_svg.read_text(encoding="utf-8")
    try:
        root = ElementTree.fromstring(svg_text)
    except ElementTree.ParseError as exc:
        checks.append(QualityCheck("svg_parse", "fail", f"SVG XML parse failed: {exc}."))
        return checks

    checks.append(QualityCheck("svg_parse", "pass", "SVG XML parses successfully."))
    checks.append(_svg_dimension_check(root))
    checks.append(_svg_raster_check(root))
    checks.append(_svg_external_link_check(root))
    return checks


def _svg_dimension_check(root: ElementTree.Element) -> QualityCheck:
    width = root.attrib.get("width")
    height = root.attrib.get("height")
    viewbox = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if (width and height) or viewbox:
        return QualityCheck(
            "svg_dimensions",
            "pass",
            "SVG has width/height or viewBox for deterministic scaling.",
        )
    return QualityCheck(
        "svg_dimensions",
        "warn",
        "SVG lacks width/height and viewBox; add dimensions before publication.",
    )


def _svg_raster_check(root: ElementTree.Element) -> QualityCheck:
    for elem in root.iter():
        if _local_name(elem.tag) == "image":
            return QualityCheck(
                "vector_only",
                "warn",
                "SVG contains <image>; replace embedded raster content with vector geometry.",
            )
    return QualityCheck("vector_only", "pass", "No embedded raster <image> elements found.")


def _svg_external_link_check(root: ElementTree.Element) -> QualityCheck:
    for elem in root.iter():
        for attr, value in elem.attrib.items():
            local_attr = _local_name(attr)
            if local_attr in {"href", "src"} and str(value).startswith(("http://", "https://")):
                return QualityCheck(
                    "external_links",
                    "warn",
                    "SVG references an external URL; vendor the asset before promotion.",
                )
    return QualityCheck("external_links", "pass", "No external SVG asset links found.")


def _status_from_checks(checks: tuple[QualityCheck, ...]) -> str:
    if any(check.status == "fail" for check in checks):
        return "blocked"
    if any(check.status == "warn" for check in checks):
        return "needs_review"
    return "ready_for_promotion"


def _descriptor_for_disk(
    descriptor: Mapping[str, Any],
    preview_svg: Path | None,
) -> dict[str, Any]:
    data = {
        key: value
        for key, value in descriptor.items()
        if key not in {"svg", "svg_path"} and value not in (None, "")
    }
    if preview_svg is not None:
        data["preview"] = preview_svg.name
    return data


def _primitive_md(descriptor: Mapping[str, Any]) -> str:
    tags = ", ".join(str(tag) for tag in descriptor.get("tags", []))
    styles = ", ".join(str(style) for style in descriptor.get("journal_styles", []))
    description = str(descriptor.get("description", "") or "Review required.")
    convention = str(descriptor.get("physics_convention", "") or "Review required.")
    references = descriptor.get("references", [])
    reference_lines = "\n".join(f"- {ref}" for ref in references) or "- Review required."
    return (
        "---\n"
        f"name: {descriptor['name']}\n"
        f"category: {descriptor.get('category', '')}\n"
        f"tags: [{tags}]\n"
        f"description: {description}\n"
        f"journal_styles: [{styles}]\n"
        "---\n\n"
        f"# {descriptor['name']} primitive\n\n"
        f"{description}\n\n"
        "## Physics convention\n\n"
        f"{convention}\n\n"
        "## References\n\n"
        f"{reference_lines}\n"
    )


def _review_md(descriptor: Mapping[str, Any], checks: tuple[QualityCheck, ...]) -> str:
    checklist = "\n".join(
        f"- [{'x' if check.status == 'pass' else ' '}] {check.name}: "
        f"{check.status.upper()} - {check.message}"
        for check in checks
    )
    return (
        f"# Primitive review: {descriptor['name']}\n\n"
        "This workspace package is not promoted to the built-in MagLab catalog yet.\n"
        "Review the checks below, parameterize variable geometry, then add a "
        "`primitive.py` implementation before promotion.\n\n"
        "## Deterministic checks\n\n"
        f"{checklist}\n\n"
        "## Promotion checklist\n\n"
        "- [ ] Confirm the physics convention against a cited source.\n"
        "- [ ] Convert any raster content to vector geometry.\n"
        "- [ ] Expose variable geometry as typed parameters.\n"
        "- [ ] Render a parameter sweep under APS, Nature, IEEE, and Elsevier styles.\n"
        "- [ ] Add or update primitive unit tests before registry promotion.\n"
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
