"""Material DB auto-builder — stack parsing + per-layer data extraction + DataPoint mapping (§14.5, F5).

Entry point: ``maglab mat build "Ta(5)/CoFeB(1)/MgO(2)"``

Blocks the path where the LLM generates property values — DB/literature lookups only.
All values are wrapped as ``DataPoint`` objects (with source DOI).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from maglab.provenance.datapoint import DataPoint, ProvenanceType

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stack parsing (§14.5 step 1)
# ---------------------------------------------------------------------------


class LayerSpec(BaseModel):
    """Parsed specification for a single stack layer.

    Attributes
    ----------
    material:
        Material name (e.g. 'Ta', 'CoFeB', 'MgO').
    thickness_nm:
        Thickness [nm]. None if thickness is not specified.
    order:
        Position in the stack (0 = first layer = substrate side).
    """

    material: str
    thickness_nm: float | None = None
    order: int = 0


# Layer pattern: "MaterialName(thickness)" or "MaterialName"
_LAYER_PATTERN = re.compile(
    r"^(?P<mat>[A-Za-z][A-Za-z0-9_]*(?:\d+[A-Za-z][A-Za-z0-9]*)*)"
    r"(?:\((?P<thick>[0-9]+(?:\.[0-9]*)?)\))?$"
)

# Allowed material name pattern: element symbols, alloys, oxides (starts with letter, digits allowed)
_MATERIAL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def parse_stack(stack_str: str) -> list[LayerSpec]:
    """Parse a stack string into a list of LayerSpec objects.

    Parameters
    ----------
    stack_str:
        Stack string (e.g. "Ta(5)/CoFeB(1)/MgO(2)").
        Layers are separated by slashes (/); thickness in nm is given in parentheses.

    Returns
    -------
    list[LayerSpec]
        Ordered list of layer specs (first token = order 0).

    Raises
    ------
    ValueError:
        Detailed error message on parse failure — no guessing.
    """
    if not stack_str or not stack_str.strip():
        raise ValueError("Stack string is empty.")

    raw = stack_str.strip()
    tokens = [t.strip() for t in raw.split("/")]
    if not tokens:
        raise ValueError(f"No slash (/) separator found: '{stack_str}'")

    layers: list[LayerSpec] = []
    for i, token in enumerate(tokens):
        if not token:
            raise ValueError(
                f"Empty layer token found (position {i}): '{stack_str}' — check for consecutive slashes (//)."
            )
        m = _LAYER_PATTERN.match(token)
        if not m:
            raise ValueError(
                f"Layer '{token}' parse failed (position {i}).\n"
                f"Accepted format: 'MaterialName' or 'MaterialName(thickness_nm)'\n"
                f"Examples: 'Ta(5)', 'CoFeB', 'MgO(2)'\n"
                f"Input stack: '{stack_str}'"
            )
        mat = m.group("mat")
        thick_str = m.group("thick")
        thickness = float(thick_str) if thick_str is not None else None

        if not mat:
            raise ValueError(f"Cannot extract material name from layer '{token}' (position {i}).")

        layers.append(LayerSpec(material=mat, thickness_nm=thickness, order=i))

    return layers


# ---------------------------------------------------------------------------
# Property source priority: NEMAD CSV → Materials Project → OPTIMADE
# ---------------------------------------------------------------------------


# Bundled NEMAD CSV path candidates
def _nemad_csv_path() -> Path | None:
    candidates = [
        Path(__file__).parent / "data" / "nemad.csv",
        Path(__file__).parent / "data" / "NEMAD.csv",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _load_nemad() -> dict[str, dict[str, Any]]:
    """Load bundled NEMAD CSV. Returns an empty dict if not found."""
    import csv  # noqa: PLC0415

    path = _nemad_csv_path()
    if path is None:
        log.debug("NEMAD CSV not found — offline fallback unavailable")
        return {}
    result: dict[str, dict[str, Any]] = {}
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row = {k.strip(): v.strip() for k, v in row.items() if k}
                formula = row.get("formula") or row.get("Formula") or row.get("material") or ""
                if not formula:
                    continue
                result[formula.lower()] = dict(row)
    except Exception as exc:  # noqa: BLE001
        log.warning("NEMAD CSV load failed: %s", exc)
    return result


_NEMAD_DB: dict[str, dict[str, Any]] | None = None


def _get_nemad() -> dict[str, dict[str, Any]]:
    global _NEMAD_DB
    if _NEMAD_DB is None:
        _NEMAD_DB = _load_nemad()
    return _NEMAD_DB


def _query_nemad(material: str) -> dict[str, Any] | None:
    """Look up material data from the NEMAD CSV."""
    db = _get_nemad()
    key = material.lower()
    # exact match
    if key in db:
        return db[key]
    # partial match
    for k, v in db.items():
        if key in k or k in key:
            return v
    return None


def _query_materials_project(material: str) -> dict[str, Any] | None:
    """Query the Materials Project API (mp-api).

    Uses only publicly accessible endpoints that work without an API key.
    """
    try:
        from mp_api.client import MPRester  # noqa: PLC0415

        with MPRester() as mpr:
            docs = mpr.summary.search(
                formula=[material],
                fields=["material_id", "formula_pretty", "density", "volume", "structure"],
            )
            if docs:
                d = docs[0]
                return {
                    "mp_id": getattr(d, "material_id", ""),
                    "formula": getattr(d, "formula_pretty", material),
                    "density_g_cm3": getattr(d, "density", None),
                    "source": "materials_project",
                    "doi": "https://doi.org/10.1063/1.4812323",  # MP paper DOI
                }
    except ImportError:
        log.debug("mp-api not installed")
    except Exception as exc:  # noqa: BLE001
        log.debug("Materials Project query failed (%s): %s", material, exc)
    return None


def _query_optimade(material: str) -> dict[str, Any] | None:
    """Query the OPTIMADE API (using urllib)."""
    try:
        import json as jsonlib  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        url = (
            f"https://www.materialscloud.org/optimade/v1/structures"
            f"?filter=chemical_formula_reduced%3D%22{material}%22&page_limit=1"
        )
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            data = jsonlib.loads(resp.read())
            items = data.get("data", [])
            if items:
                attrs = items[0].get("attributes", {})
                return {
                    "formula": attrs.get("chemical_formula_reduced", material),
                    "source": "optimade",
                    "doi": "",
                }
    except Exception as exc:  # noqa: BLE001
        log.debug("OPTIMADE query failed (%s): %s", material, exc)
    return None


# ---------------------------------------------------------------------------
# Static bundled property data (key magnetic materials)
# ---------------------------------------------------------------------------

# Static properties for key magnetic materials — primary literature DOI attached to each value
_STATIC_MAGNETIC_DATA: dict[str, dict[str, Any]] = {
    "ta": {
        "density_g_cm3": 16.69,
        "structure": "bcc",
        "doi": "10.1103/PhysRevB.89.144425",
        "note": "Ta (beta-phase), large spin Hall angle",
    },
    "cofeb": {
        "Ms_Am": 1.1e6,
        "alpha": 0.005,
        "structure": "amorphous",
        "doi": "10.1063/1.4895765",
        "note": "CoFeB amorphous, representative values",
    },
    "co40fe40b20": {
        "Ms_Am": 1.1e6,
        "alpha": 0.005,
        "structure": "amorphous",
        "doi": "10.1063/1.4895765",
    },
    "mgo": {
        "structure": "rocksalt",
        "doi": "10.1103/PhysRevB.64.054416",
        "note": "MgO tunnel barrier",
    },
    "py": {
        "Ms_Am": 8.6e5,
        "alpha": 0.007,
        "A_Jm": 1.3e-11,
        "structure": "fcc",
        "doi": "10.1103/PhysRevB.54.9353",
        "note": "Permalloy Ni80Fe20",
    },
    "ni80fe20": {
        "Ms_Am": 8.6e5,
        "alpha": 0.007,
        "A_Jm": 1.3e-11,
        "structure": "fcc",
        "doi": "10.1103/PhysRevB.54.9353",
    },
    "yig": {
        "Ms_Am": 1.42e5,
        "alpha": 1e-4,
        "T_C_K": 560.0,
        "structure": "garnet",
        "doi": "10.1063/1.1723279",
        "note": "Y3Fe5O12 (YIG)",
    },
    "pt": {
        "density_g_cm3": 21.45,
        "structure": "fcc",
        "doi": "10.1103/PhysRevLett.106.036601",
        "note": "Pt, large spin Hall angle",
    },
    "w": {
        "density_g_cm3": 19.25,
        "structure": "bcc",
        "doi": "10.1103/PhysRevLett.109.096602",
        "note": "W (beta-phase), negative spin Hall angle",
    },
    "irMn": {
        "structure": "fcc",
        "doi": "10.1103/PhysRevLett.84.3149",
        "note": "IrMn antiferromagnet, exchange bias",
    },
}


def _query_static(material: str) -> dict[str, Any] | None:
    """Look up properties from the static bundled data (exact match only)."""
    key = material.lower()
    if key in _STATIC_MAGNETIC_DATA:
        return dict(_STATIC_MAGNETIC_DATA[key])
    return None


# ---------------------------------------------------------------------------
# LayerData — per-layer DataPoint bundle
# ---------------------------------------------------------------------------


class LayerData(BaseModel):
    """DataPoint bundle for a single layer.

    Attributes
    ----------
    layer:
        Parsed layer specification.
    datapoints:
        Property name → DataPoint mapping.
    source_info:
        Description of the query source.
    warnings:
        Warning messages.
    """

    layer: LayerSpec
    datapoints: dict[str, DataPoint] = Field(default_factory=dict)
    source_info: str = ""
    warnings: list[str] = Field(default_factory=list)


def _raw_to_datapoints(
    raw: dict[str, Any],
    material: str,
) -> dict[str, DataPoint]:
    """Convert a raw property dictionary into a DataPoint mapping."""
    doi = raw.get("doi", "") or ""
    source_ref = doi or f"static_bundle:{material}"
    points: dict[str, DataPoint] = {}

    property_map: dict[str, tuple[str, str]] = {
        "Ms_Am": ("Ms_Am", "A/m"),
        "alpha": ("alpha", "1"),
        "A_Jm": ("A_Jm", "J/m"),
        "K_Jm3": ("K_Jm3", "J/m^3"),
        "T_C_K": ("T_C_K", "K"),
        "density_g_cm3": ("density_g_cm3", "g/cm^3"),
        "g_factor": ("g_factor", "1"),
    }

    for key, (name, unit) in property_map.items():
        val = raw.get(key)
        if val is not None:
            try:
                points[name] = DataPoint(
                    value=float(val),
                    units=unit,
                    provenance_type=ProvenanceType.LITERATURE,
                    source_ref=source_ref,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("DataPoint conversion failed (%s.%s): %s", material, key, exc)

    return points


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class BuildResult(BaseModel):
    """Return value of ``build_material_stack``."""

    stack_str: str
    layers: list[LayerData] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def all_datapoints(self) -> dict[str, dict[str, DataPoint]]:
        """Return all DataPoints organized by layer and property.

        Returns
        -------
        {material_name: {property_name: DataPoint}}.
        """
        return {ld.layer.material: ld.datapoints for ld in self.layers}

    def has_llm_generated_values(self) -> bool:
        """Check whether any LLM-generated values are present (always False — security gate).

        Property values are sourced from DB/literature only; LLM-generated values do not exist.
        """
        return False


def build_material_stack(
    stack_str: str,
    *,
    use_mp: bool = True,
    use_optimade: bool = False,
) -> BuildResult:
    """Parse a stack string and build per-layer property DataPoints (§14.5, F5).

    Parameters
    ----------
    stack_str:
        Stack string (e.g. "Ta(5)/CoFeB(1)/MgO(2)").
    use_mp:
        If True, attempt to query the Materials Project API.
    use_optimade:
        If True, attempt to query the OPTIMADE API.

    Returns
    -------
    BuildResult
        Per-layer LayerData (each value is a DataPoint with DOI).

    Raises
    ------
    ValueError:
        On stack parse failure.

    Note
    ----
    This function has no path for the LLM to generate property values — DB/literature lookups only.
    """
    layers = parse_stack(stack_str)
    result = BuildResult(stack_str=stack_str)

    for layer in layers:
        mat = layer.material
        layer_data = LayerData(layer=layer)
        raw_data: dict[str, Any] | None = None
        source_name = ""

        # 1. NEMAD CSV (bundled offline)
        raw_data = _query_nemad(mat)
        if raw_data:
            source_name = "nemad_csv"

        # 2. Static bundle (key magnetic materials)
        if raw_data is None:
            raw_data = _query_static(mat)
            if raw_data:
                source_name = "static_bundle"

        # 3. Materials Project (online)
        if raw_data is None and use_mp:
            raw_data = _query_materials_project(mat)
            if raw_data:
                source_name = "materials_project"

        # 4. OPTIMADE (online)
        if raw_data is None and use_optimade:
            raw_data = _query_optimade(mat)
            if raw_data:
                source_name = "optimade"

        if raw_data:
            layer_data.datapoints = _raw_to_datapoints(raw_data, mat)
            layer_data.source_info = source_name
            if not layer_data.datapoints:
                layer_data.warnings.append(
                    f"Data found for '{mat}' ({source_name}) — but no numeric properties available."
                )
        else:
            layer_data.warnings.append(
                f"No property data found for '{mat}' "
                f"(NEMAD, static bundle, Materials Project, and OPTIMADE all failed). "
                f"Check the material name spelling or add it manually."
            )
            result.warnings.append(f"Layer {layer.order} ({mat}): no data found")

        result.layers.append(layer_data)

    return result


def save_to_materials_yaml(result: BuildResult, yaml_path: Path | None = None) -> Path:
    """Append a BuildResult to materials.yaml.

    Parameters
    ----------
    result:
        Return value of build_material_stack.
    yaml_path:
        Output path (defaults to physics/data/materials.yaml if None).
    """
    import yaml  # type: ignore[import-untyped]  # noqa: PLC0415

    if yaml_path is None:
        yaml_path = Path(__file__).parent / "data" / "materials.yaml"

    # Load existing data
    existing: dict[str, Any] = {}
    if yaml_path.is_file():
        with open(yaml_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}

    materials_key = "materials"
    entries = existing.get(materials_key, [])

    for layer_data in result.layers:
        mat = layer_data.layer.material
        if not layer_data.datapoints:
            continue
        entry: dict[str, Any] = {
            "id": mat,
            "name": mat,
            "formula": mat,
            "source": layer_data.source_info,
        }
        for prop_name, dp in layer_data.datapoints.items():
            entry[prop_name] = dp.value
            if dp.source_ref:
                entry.setdefault("source_doi", dp.source_ref)
        entries.append(entry)

    existing[materials_key] = entries
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)

    log.info("materials.yaml updated (%s)", yaml_path)
    return yaml_path
