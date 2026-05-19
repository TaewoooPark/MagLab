"""Curated magnetic materials database query interface.

Loads static property data from `data/materials.yaml` and provides
an interface for querying by name, formula, or ID.

Each property value is accompanied by a source reference (PLAN §9, T-P0-06).

Design principles:
  - Purely static data — no network or external database access. P0 uses only bundled YAML.
  - `MaterialData` Pydantic model is defined here so that P5 `material_builder.py`
    can interface with Materials Project and OPTIMADE.
  - Query failures return None (not exceptions) — caller is responsible for handling.
"""

from __future__ import annotations

import importlib.resources
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Material data model (Pydantic v2)
# ---------------------------------------------------------------------------


class MaterialData(BaseModel):
    """Curated property record for a single magnetic material.

    Attributes:
        id: Unique identifier string (e.g., "Permalloy", "YIG").
        name: Human-readable name.
        formula: Chemical formula.
        structure: Crystal structure (e.g., "bcc", "fcc", "amorphous").
        Ms_Am: Saturation magnetization [A/m] at 300 K.
        A_Jm: Exchange stiffness [J/m] at 300 K.
        K_Jm3: Anisotropy constant [J/m³] at 300 K. (K₁ or K_u)
        alpha: Gilbert damping constant [dimensionless] at 300 K.
        T_C_K: Curie temperature [K].
        g_factor: g-factor [dimensionless].
        source_doi: Source DOI.
        source_ref: Full source reference (textbook or paper).
        notes: Supplementary notes.
    """

    id: str
    name: str
    formula: str
    structure: str = "unknown"

    # Key properties — None means data not available
    Ms_Am: float | None = Field(default=None, description="Saturation magnetization [A/m]")
    A_Jm: float | None = Field(default=None, description="Exchange stiffness [J/m]")
    K_Jm3: float | None = Field(default=None, description="Anisotropy constant [J/m³]")
    alpha: float | None = Field(default=None, description="Gilbert damping constant")
    T_C_K: float | None = Field(default=None, description="Curie temperature [K]")
    g_factor: float | None = Field(default=None, description="g-factor")

    # Source
    source_doi: str = ""
    source_ref: str = ""
    notes: str = ""

    # Extended fields (to be filled by material_builder.py from external databases)
    extra: dict[str, Any] = Field(default_factory=dict)

    def exchange_length_m(self) -> float | None:
        """Return the exchange length l_ex [m].

        l_ex = sqrt(2A / μ₀Ms²).
        Returns None if A or Ms data is missing.
        """
        from maglab.physics.formulas import exchange_length

        if self.A_Jm is None or self.Ms_Am is None or self.Ms_Am == 0:
            return None
        return exchange_length(self.A_Jm, self.Ms_Am)

    def bloch_wall_width_m(self) -> float | None:
        """Return the Bloch domain-wall width Δ [m].

        Δ = π√(A/K). Returns None if K ≤ 0 (depends on K definition).
        """
        from maglab.physics.formulas import bloch_wall_width

        if self.A_Jm is None or self.K_Jm3 is None or self.K_Jm3 <= 0:
            return None
        try:
            return bloch_wall_width(self.A_Jm, self.K_Jm3)
        except ValueError:
            return None

    def summary(self) -> dict[str, Any]:
        """Return a summary dictionary of key properties."""
        return {
            "id": self.id,
            "name": self.name,
            "formula": self.formula,
            "Ms_Am": self.Ms_Am,
            "A_Jm": self.A_Jm,
            "K_Jm3": self.K_Jm3,
            "alpha": self.alpha,
            "T_C_K": self.T_C_K,
            "l_ex_nm": (
                round(l_ex * 1e9, 2) if (l_ex := self.exchange_length_m()) is not None else None
            ),
            "source_doi": self.source_doi,
        }


# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------


def _yaml_path() -> Path:
    """Return the path to the bundled materials.yaml."""
    # Access package file via importlib.resources
    try:
        pkg_files = importlib.resources.files("maglab.physics.data")
        return Path(str(pkg_files.joinpath("materials.yaml")))
    except (TypeError, AttributeError):
        # Fallback: direct path
        return Path(__file__).parent / "data" / "materials.yaml"


@lru_cache(maxsize=1)
def _load_all() -> list[MaterialData]:
    """Load all material data from the bundled YAML (cached)."""
    path = _yaml_path()
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    records: list[MaterialData] = []
    for item in raw.get("materials", []):
        records.append(MaterialData(**item))
    return records


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------


def list_materials() -> list[MaterialData]:
    """Return all material records in the bundle.

    Returns:
        List of MaterialData.
    """
    return _load_all()


def lookup(material_id: str) -> MaterialData | None:
    """Look up a material by ID.

    Searches case-insensitively.

    Args:
        material_id: Material ID (e.g., "Permalloy", "YIG", "Fe").

    Returns:
        MaterialData, or None if not found.
    """
    mid = material_id.strip().lower()
    for mat in _load_all():
        if mat.id.lower() == mid:
            return mat
    return None


def search(
    query: str,
    *,
    fields: tuple[str, ...] = ("id", "name", "formula"),
) -> list[MaterialData]:
    """Search for materials by substring match.

    Args:
        query: Search term (case-insensitive).
        fields: Field names to search.

    Returns:
        List of matching MaterialData.
    """
    q = query.strip().lower()
    results: list[MaterialData] = []
    for mat in _load_all():
        for f in fields:
            val = getattr(mat, f, "")
            if val and q in str(val).lower():
                results.append(mat)
                break
    return results


def get_property(material_id: str, prop: str) -> Any:
    """Return the value of a specific property for a given material.

    Args:
        material_id: Material ID.
        prop: Property name (e.g., "Ms_Am", "A_Jm", "T_C_K").

    Returns:
        Property value; None if material not found; raises AttributeError if property not found.
    """
    mat = lookup(material_id)
    if mat is None:
        return None
    return getattr(mat, prop)


def available_ids() -> list[str]:
    """Return a list of all material IDs in the bundle.

    Returns:
        List of material ID strings.
    """
    return [mat.id for mat in _load_all()]
