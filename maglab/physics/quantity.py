"""Lightweight Quantity type — bundling value, unit, and uncertainty.

A minimal unit-aware data structure implemented without pint dependency.
Unit conversions from `units.py` are exposed via the `.to(unit)` method.

Design principles (PLAN §9):
  - Purely deterministic — no LLM calls or network access.
  - No pint dependency.
  - Provides a serialization interface convertible to `DataPoint` (provenance).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from maglab.physics import units as _u

# ---------------------------------------------------------------------------
# Supported unit sets (string identifiers)
# ---------------------------------------------------------------------------

#: Set of supported units. Only units convertible to each other are grouped per category.
UNIT_CATEGORIES: dict[str, set[str]] = {
    "H_field": {"Oe", "A/m", "T"},
    "magnetization": {"emu/cm3", "A/m"},
    "energy_density": {"erg/cm3", "J/m3"},
    "energy_per_length": {"erg/cm", "J/m"},
    "exchange_energy": {"meV", "K", "J"},
    "dmi": {"mJ/m2", "meV/A2"},
    "dimensionless": {"dimensionless", "1"},
    "temperature": {"K"},
    "frequency": {"GHz", "Hz", "rad/s"},
    "length": {"nm", "m", "A"},  # A = Angstrom
    "time": {"ns", "s", "ps"},
    "velocity": {"m/s"},
    "angle": {"deg", "rad"},
}

# ---------------------------------------------------------------------------
# Conversion function map: (from_unit, to_unit) -> scalar conversion function
# ---------------------------------------------------------------------------


def _identity(x: float) -> float:
    return x


def _ghz_to_hz(x: float) -> float:
    return x * 1e9


def _hz_to_ghz(x: float) -> float:
    return x * 1e-9


def _rads_to_hz(x: float) -> float:
    return x / (2.0 * math.pi)


def _hz_to_rads(x: float) -> float:
    return x * (2.0 * math.pi)


def _ghz_to_rads(x: float) -> float:
    return _hz_to_rads(_ghz_to_hz(x))


def _rads_to_ghz(x: float) -> float:
    return _hz_to_ghz(_rads_to_hz(x))


def _nm_to_m(x: float) -> float:
    return x * 1e-9


def _m_to_nm(x: float) -> float:
    return x * 1e9


def _angstrom_to_m(x: float) -> float:
    return x * 1e-10


def _m_to_angstrom(x: float) -> float:
    return x * 1e10


def _nm_to_angstrom(x: float) -> float:
    return x * 10.0


def _angstrom_to_nm(x: float) -> float:
    return x * 0.1


def _ns_to_s(x: float) -> float:
    return x * 1e-9


def _s_to_ns(x: float) -> float:
    return x * 1e9


def _ps_to_s(x: float) -> float:
    return x * 1e-12


def _s_to_ps(x: float) -> float:
    return x * 1e12


def _ns_to_ps(x: float) -> float:
    return x * 1e3


def _ps_to_ns(x: float) -> float:
    return x * 1e-3


def _deg_to_rad(x: float) -> float:
    return math.radians(x)


def _rad_to_deg(x: float) -> float:
    return math.degrees(x)


def _mev_to_j(x: float) -> float:
    from maglab.physics.units import _MEV_TO_J

    return x * _MEV_TO_J


def _j_to_mev(x: float) -> float:
    from maglab.physics.units import _MEV_TO_J

    return x / _MEV_TO_J


def _k_to_j(x: float) -> float:
    from maglab.physics.units import _K_TO_J

    return x * _K_TO_J


def _j_to_k(x: float) -> float:
    from maglab.physics.units import _K_TO_J

    return x / _K_TO_J


#: (from, to) -> conversion function
_CONVERSION_MAP: dict[tuple[str, str], Any] = {
    # H_field
    ("Oe", "A/m"): _u.oe_to_am,
    ("A/m", "Oe"): _u.am_to_oe,
    ("A/m", "T"): _u.am_to_tesla,
    ("T", "A/m"): _u.tesla_to_am,
    ("Oe", "T"): _u.oe_to_tesla,
    ("T", "Oe"): _u.tesla_to_oe,
    # magnetization
    ("emu/cm3", "A/m"): _u.emu_cm3_to_am,
    ("A/m", "emu/cm3"): _u.am_to_emu_cm3,
    # energy_density
    ("erg/cm3", "J/m3"): _u.erg_cm3_to_jm3,
    ("J/m3", "erg/cm3"): _u.jm3_to_erg_cm3,
    # energy_per_length
    ("erg/cm", "J/m"): _u.erg_cm_to_jm,
    ("J/m", "erg/cm"): _u.jm_to_erg_cm,
    # exchange_energy
    ("meV", "K"): _u.mev_to_kelvin,
    ("K", "meV"): _u.kelvin_to_mev,
    ("meV", "J"): _mev_to_j,
    ("J", "meV"): _j_to_mev,
    ("K", "J"): _k_to_j,
    ("J", "K"): _j_to_k,
    # dmi
    ("meV/A2", "mJ/m2"): _u.mev_a2_to_mjm2,
    ("mJ/m2", "meV/A2"): _u.mjm2_to_mev_a2,
    # frequency
    ("GHz", "Hz"): _ghz_to_hz,
    ("Hz", "GHz"): _hz_to_ghz,
    ("rad/s", "Hz"): _rads_to_hz,
    ("Hz", "rad/s"): _hz_to_rads,
    ("GHz", "rad/s"): _ghz_to_rads,
    ("rad/s", "GHz"): _rads_to_ghz,
    # length
    ("nm", "m"): _nm_to_m,
    ("m", "nm"): _m_to_nm,
    ("A", "m"): _angstrom_to_m,
    ("m", "A"): _m_to_angstrom,
    ("nm", "A"): _nm_to_angstrom,
    ("A", "nm"): _angstrom_to_nm,
    # time
    ("ns", "s"): _ns_to_s,
    ("s", "ns"): _s_to_ns,
    ("ps", "s"): _ps_to_s,
    ("s", "ps"): _s_to_ps,
    ("ns", "ps"): _ns_to_ps,
    ("ps", "ns"): _ps_to_ns,
    # angle
    ("deg", "rad"): _deg_to_rad,
    ("rad", "deg"): _rad_to_deg,
    # dimensionless (no-op)
    ("dimensionless", "1"): _identity,
    ("1", "dimensionless"): _identity,
}


# ---------------------------------------------------------------------------
# Quantity data structure
# ---------------------------------------------------------------------------


@dataclass
class Quantity:
    """Lightweight physical quantity type bundling value, unit, and uncertainty.

    Args:
        value: Numerical value.
        unit: Unit string (e.g., "A/m", "T", "J/m³").
        uncertainty: Absolute uncertainty (default None = unknown).
        label: Optional label (e.g., "M_s", "H_K").

    Example::

        ms = Quantity(8e5, "A/m", label="M_s")
        ms_emu = ms.to("emu/cm3")  # -> Quantity(800.0, "emu/cm3")
    """

    value: float
    unit: str
    uncertainty: float | None = field(default=None)
    label: str | None = field(default=None)

    # ------------------------------------------------------------------
    # Unit conversion
    # ------------------------------------------------------------------

    def to(self, target_unit: str) -> Quantity:
        """Return a new Quantity converted to the specified unit.

        Args:
            target_unit: Target unit string.

        Returns:
            Converted Quantity (original is unchanged).

        Raises:
            ValueError: When the conversion path is unknown.
        """
        if self.unit == target_unit:
            return Quantity(self.value, target_unit, self.uncertainty, self.label)

        key = (self.unit, target_unit)
        if key not in _CONVERSION_MAP:
            raise ValueError(
                f"Unit conversion not supported: '{self.unit}' -> '{target_unit}'. "
                f"Supported conversions: {list(_CONVERSION_MAP.keys())}"
            )

        fn = _CONVERSION_MAP[key]
        new_value = fn(self.value)

        # Uncertainty transformed with the same linear factor (linear conversion assumed)
        new_uncertainty: float | None = None
        if self.uncertainty is not None:
            try:
                new_uncertainty = fn(self.uncertainty)
                # For a linear transform, uncertainty = |df/dx| × σ, but
                # here we approximate as f(σ) - f(0).
                # (Requires f(0) = 0 — only offset-free conversions are supported.)
            except Exception:
                new_uncertainty = None

        return Quantity(new_value, target_unit, new_uncertainty, self.label)

    # ------------------------------------------------------------------
    # Arithmetic operations (same unit only)
    # ------------------------------------------------------------------

    def _check_unit(self, other: Quantity) -> None:
        if self.unit != other.unit:
            raise ValueError(
                f"Unit mismatch: '{self.unit}' vs '{other.unit}'. Convert to the same unit before operating."
            )

    def __add__(self, other: Quantity) -> Quantity:
        """Add two Quantities with the same unit."""
        self._check_unit(other)
        unc = _combine_unc(self.uncertainty, other.uncertainty)
        return Quantity(self.value + other.value, self.unit, unc, self.label)

    def __sub__(self, other: Quantity) -> Quantity:
        """Subtract two Quantities with the same unit."""
        self._check_unit(other)
        unc = _combine_unc(self.uncertainty, other.uncertainty)
        return Quantity(self.value - other.value, self.unit, unc, self.label)

    def __mul__(self, scalar: float) -> Quantity:
        """Multiply by a scalar."""
        unc = self.uncertainty * abs(scalar) if self.uncertainty is not None else None
        return Quantity(self.value * scalar, self.unit, unc, self.label)

    def __rmul__(self, scalar: float) -> Quantity:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Quantity:
        """Divide by a scalar."""
        if scalar == 0.0:
            raise ZeroDivisionError("Cannot divide a Quantity by zero.")
        unc = self.uncertainty / abs(scalar) if self.uncertainty is not None else None
        return Quantity(self.value / scalar, self.unit, unc, self.label)

    def __neg__(self) -> Quantity:
        unc = self.uncertainty
        return Quantity(-self.value, self.unit, unc, self.label)

    def __abs__(self) -> Quantity:
        return Quantity(abs(self.value), self.unit, self.uncertainty, self.label)

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        return self.unit == other.unit and math.isclose(self.value, other.value, rel_tol=1e-12)

    # ------------------------------------------------------------------
    # Serialization interface (DataPoint integration)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        Returns:
            Dictionary with keys {"value", "unit", "uncertainty", "label"}.
        """
        return {
            "value": self.value,
            "unit": self.unit,
            "uncertainty": self.uncertainty,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Quantity:
        """Restore a Quantity from a dictionary.

        Args:
            d: Dictionary returned by to_dict().

        Returns:
            Quantity instance.
        """
        return cls(
            value=float(d["value"]),
            unit=str(d["unit"]),
            uncertainty=d.get("uncertainty"),
            label=d.get("label"),
        )

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        unc_str = f" ± {self.uncertainty}" if self.uncertainty is not None else ""
        label_str = f" [{self.label}]" if self.label else ""
        return f"Quantity({self.value}{unc_str} {self.unit}{label_str})"

    def __format__(self, spec: str) -> str:
        val_str = format(self.value, spec) if spec else str(self.value)
        return f"{val_str} {self.unit}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _combine_unc(a: float | None, b: float | None) -> float | None:
    """Combine two absolute uncertainties in quadrature (assuming independent errors)."""
    if a is None and b is None:
        return None
    a_val = a if a is not None else 0.0
    b_val = b if b is not None else 0.0
    return math.sqrt(a_val**2 + b_val**2)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def quantity(
    value: float, unit: str, uncertainty: float | None = None, label: str | None = None
) -> Quantity:
    """Convenience factory function for Quantity.

    Args:
        value: Numerical value.
        unit: Unit string.
        uncertainty: Absolute uncertainty (optional).
        label: Label (optional).

    Returns:
        Quantity instance.
    """
    return Quantity(value=value, unit=unit, uncertainty=uncertainty, label=label)
