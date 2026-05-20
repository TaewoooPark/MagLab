"""Unit tests for workspace-local figure primitive ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maglab.figure.primitives.ingest import PrimitiveIngestError, ingest_primitive


def test_ingest_svg_creates_workspace_review_scaffold(tmp_path: Path) -> None:
    source = tmp_path / "SOT Torque Loop.svg"
    source.write_text(
        '<svg width="120" height="80" viewBox="0 0 120 80" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<path d="M10 40 C30 10 80 10 100 40" fill="none" stroke="black"/>'
        "</svg>\n",
        encoding="utf-8",
    )

    result = ingest_primitive(
        source,
        workspace=tmp_path / "workspace",
        metadata={
            "category": "concept/process",
            "tags": ["SOT", "torque", "loop"],
            "description": "Spin-orbit torque loop schematic.",
            "physics_convention": "Current along x; spin accumulation along y.",
            "references": ["doi:10.1038/nnano.2013.243"],
            "parameters": [
                {
                    "name": "arrow_scale",
                    "type": "float",
                    "default": 1.0,
                    "description": "Relative arrow scale.",
                }
            ],
        },
    )

    assert result.name == "sot-torque-loop"
    assert result.status == "ready_for_promotion"
    assert result.package_dir.is_dir()
    assert result.primitive_md.is_file()
    assert result.descriptor_json.is_file()
    assert result.review_md.is_file()
    assert result.quality_json.is_file()
    assert result.preview_svg is not None
    assert result.preview_svg.read_text(encoding="utf-8").startswith("<svg")

    descriptor = json.loads(result.descriptor_json.read_text(encoding="utf-8"))
    assert descriptor["name"] == "sot-torque-loop"
    assert descriptor["preview"] == "preview.svg"
    assert descriptor["provenance"]["ingest_pipeline"] == "maglab.figure.primitives.ingest"

    quality = json.loads(result.quality_json.read_text(encoding="utf-8"))
    assert quality["status"] == "ready_for_promotion"
    assert {check["name"] for check in quality["checks"]} >= {
        "svg_parse",
        "svg_dimensions",
        "vector_only",
        "external_links",
    }

    review_text = result.review_md.read_text(encoding="utf-8")
    assert "Promotion checklist" in review_text
    assert "ready_for_promotion" not in review_text


def test_ingest_json_descriptor_embedded_svg_warns_for_static_primitive(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "mtj-callout.json"
    descriptor.write_text(
        json.dumps(
            {
                "name": "MTJ Callout",
                "category": "annotation",
                "tags": ["MTJ", "callout"],
                "description": "Static MTJ callout primitive.",
                "physics_convention": "Labels free layer, barrier, and pinned layer.",
                "references": ["https://example.test/reference"],
                "svg": '<svg viewBox="0 0 40 20" xmlns="http://www.w3.org/2000/svg">'
                '<rect x="1" y="1" width="38" height="18"/></svg>',
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = ingest_primitive(descriptor, workspace=tmp_path / "workspace")

    assert result.name == "mtj-callout"
    assert result.status == "needs_review"
    quality = json.loads(result.quality_json.read_text(encoding="utf-8"))
    parameter_check = next(check for check in quality["checks"] if check["name"] == "parameters")
    assert parameter_check["status"] == "warn"
    assert result.preview_svg is not None
    assert result.preview_svg.name == "preview.svg"


def test_ingest_rejects_unknown_descriptor_keys(tmp_path: Path) -> None:
    descriptor = tmp_path / "bad.json"
    descriptor.write_text('{"name": "bad", "shell": "rm -rf"}\n', encoding="utf-8")

    with pytest.raises(PrimitiveIngestError, match="Unsupported primitive descriptor key"):
        ingest_primitive(descriptor, workspace=tmp_path / "workspace")


def test_ingest_refuses_to_overwrite_without_flag(tmp_path: Path) -> None:
    source = tmp_path / "axis.svg"
    source.write_text(
        '<svg width="10" height="10" xmlns="http://www.w3.org/2000/svg"></svg>',
        encoding="utf-8",
    )

    ingest_primitive(source, workspace=tmp_path / "workspace")

    with pytest.raises(PrimitiveIngestError, match="already exists"):
        ingest_primitive(source, workspace=tmp_path / "workspace")

    result = ingest_primitive(source, workspace=tmp_path / "workspace", overwrite=True)
    assert result.package_dir.is_dir()
