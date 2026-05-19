"""Magnetic point group allowed component filter.

Input a magnetic point group label → return allowed electrical conductivity, Hall conductivity, and AMR tensor component lists.
EffectModel.symmetry_constraints calls this to automatically fix forbidden components to zero.

Key magnetic point groups (common in magnetic experiments):
  m3m  — cubic (Oh): off-diagonal AHE allowed, AMR components forbidden
  4/mmm — tetragonal (D4h): AHE allowed, PHE components allowed
  mm2  — orthorhombic (C2v): AMR and PHE components allowed
  2/m  — monoclinic (C2h)
  -1   — triclinic (Ci)
  6/mmm — hexagonal (D6h)

Design basis: plan/04-analysis.md §11, impl/03-P2-analysis.md T-P2-05
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Allowed component data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllowedComponents:
    """List of allowed tensor components for a magnetic point group.

    Attributes:
        point_group: Magnetic point group label.
        hall_components: Allowed Hall conductivity components [(alpha, beta), ...].
        amr_allowed: Whether AMR components are allowed.
        phe_allowed: Whether PHE components are allowed.
        ahe_allowed: Whether AHE off-diagonal components are allowed.
        ohe_components: Allowed OHE rank-3 components [(alpha, beta, gamma), ...].
        notes: Additional notes.
    """

    point_group: str
    hall_components: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    amr_allowed: bool = True
    phe_allowed: bool = True
    ahe_allowed: bool = True
    ohe_components: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)
    notes: str = ""


# ---------------------------------------------------------------------------
# Magnetic point group database
# ---------------------------------------------------------------------------

# Index convention: 0=x, 1=y, 2=z
# σ_xy = current in x-direction, Hall in y-direction → (0,1)

_SYMMETRY_DB: dict[str, AllowedComponents] = {
    # --------------------------------------------------------------
    # Cubic Oh (m3m) — highest symmetry
    # AHE (σ_xy = -σ_yx): allowed (forbidden in non-magnetic cubic, allowed in magnetic cubic)
    # AMR: Δρ = ρ_∥ - ρ_⊥ ≠ 0 in cubic, angle-dependent cos²θ component present
    # PHE: (Δρ/2)sin2φ in cubic — allowed
    # OHE rank-3: only off-diagonal components such as σ^z_{xy} are allowed
    # --------------------------------------------------------------
    "m3m": AllowedComponents(
        point_group="m3m",
        hall_components=((0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1)),
        amr_allowed=True,
        phe_allowed=True,
        ahe_allowed=True,
        ohe_components=((0, 1, 2), (1, 0, 2), (0, 2, 1), (2, 0, 1), (1, 2, 0), (2, 1, 0)),
        notes="Cubic Oh magnetic point group. AHE, PHE, AMR allowed. Off-diagonal OHE components allowed.",
    ),
    # --------------------------------------------------------------
    # Tetragonal D4h (4/mmm)
    # --------------------------------------------------------------
    "4/mmm": AllowedComponents(
        point_group="4/mmm",
        hall_components=((0, 1), (1, 0)),
        amr_allowed=True,
        phe_allowed=True,
        ahe_allowed=True,
        ohe_components=((0, 1, 2), (1, 0, 2)),
        notes="Tetragonal D4h. AHE σ_xy allowed. AMR and PHE allowed.",
    ),
    # --------------------------------------------------------------
    # Orthorhombic C2v (mm2)
    # --------------------------------------------------------------
    "mm2": AllowedComponents(
        point_group="mm2",
        hall_components=((0, 1), (1, 0), (0, 2), (2, 0)),
        amr_allowed=True,
        phe_allowed=True,
        ahe_allowed=True,
        ohe_components=((0, 1, 2), (1, 0, 2), (0, 2, 1)),
        notes="Orthorhombic C2v. AMR, PHE, AHE allowed.",
    ),
    # --------------------------------------------------------------
    # Monoclinic C2h (2/m)
    # --------------------------------------------------------------
    "2/m": AllowedComponents(
        point_group="2/m",
        hall_components=((0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1)),
        amr_allowed=True,
        phe_allowed=True,
        ahe_allowed=True,
        ohe_components=tuple(
            (a, b, c) for a in range(3) for b in range(3) for c in range(3) if a != b
        ),
        notes="Monoclinic C2h. Most components allowed.",
    ),
    # --------------------------------------------------------------
    # Triclinic Ci (-1)
    # --------------------------------------------------------------
    "-1": AllowedComponents(
        point_group="-1",
        hall_components=tuple((a, b) for a in range(3) for b in range(3) if a != b),
        amr_allowed=True,
        phe_allowed=True,
        ahe_allowed=True,
        ohe_components=tuple(
            (a, b, c) for a in range(3) for b in range(3) for c in range(3) if a != b
        ),
        notes="Triclinic Ci. All components allowed.",
    ),
    # --------------------------------------------------------------
    # Hexagonal D6h (6/mmm)
    # --------------------------------------------------------------
    "6/mmm": AllowedComponents(
        point_group="6/mmm",
        hall_components=((0, 1), (1, 0)),
        amr_allowed=True,
        phe_allowed=True,
        ahe_allowed=True,
        ohe_components=((0, 1, 2), (1, 0, 2)),
        notes="Hexagonal D6h. AHE σ_xy allowed.",
    ),
    # --------------------------------------------------------------
    # Trigonal C3 (3) — skyrmion host family
    # --------------------------------------------------------------
    "3": AllowedComponents(
        point_group="3",
        hall_components=((0, 1), (1, 0)),
        amr_allowed=True,
        phe_allowed=True,
        ahe_allowed=True,
        ohe_components=((0, 1, 2), (1, 0, 2), (0, 2, 1), (2, 0, 1)),
        notes="Trigonal C3. Skyrmion host family.",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def allowed_components(point_group: str) -> AllowedComponents:
    """Return allowed component list for a magnetic point group label.

    Args:
        point_group: Schönflies or international notation magnetic point group label
                     (e.g., "m3m", "4/mmm", "mm2", "2/m", "-1", "6/mmm").

    Returns:
        AllowedComponents instance.

    Raises:
        ValueError: Unknown point group.
    """
    pg = point_group.strip()
    if pg not in _SYMMETRY_DB:
        available = list(_SYMMETRY_DB.keys())
        raise ValueError(f"Unknown magnetic point group: '{pg}'. Supported list: {available}")
    return _SYMMETRY_DB[pg]


def is_ahe_allowed(point_group: str) -> bool:
    """Return whether AHE off-diagonal components are allowed for the given magnetic point group."""
    return allowed_components(point_group).ahe_allowed


def is_amr_allowed(point_group: str) -> bool:
    """Return whether AMR angle-dependent components are allowed for the given magnetic point group."""
    return allowed_components(point_group).amr_allowed


def ahe_constraints(point_group: str) -> dict[str, Any]:
    """Return the AHE constraint dictionary to pass to EffectModel.symmetry_constraints.

    Returns:
        {"ahe_allowed": bool, "hall_components": [(α,β),...]} dictionary.
    """
    comp = allowed_components(point_group)
    return {
        "ahe_allowed": comp.ahe_allowed,
        "hall_components": list(comp.hall_components),
    }


def ohe_constraints(point_group: str) -> dict[str, Any]:
    """Return the OHE rank-3 tensor allowed component constraint dictionary.

    Returns:
        {"ohe_components": [(α,β,γ),...]} dictionary.
    """
    comp = allowed_components(point_group)
    return {"ohe_components": list(comp.ohe_components)}


def list_supported_groups() -> list[str]:
    """Return the list of supported magnetic point group labels."""
    return list(_SYMMETRY_DB.keys())
