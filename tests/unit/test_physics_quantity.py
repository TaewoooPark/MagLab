"""Quantity type conversion and arithmetic tests.

Validation principle (PLAN §20): deterministic checks only.
"""

from __future__ import annotations

import math

import pytest

from maglab.physics.quantity import Quantity, quantity

REL_TOL = 1e-9


# ---------------------------------------------------------------------------
# Basic creation
# ---------------------------------------------------------------------------


class TestQuantityCreation:
    """Quantity creation tests."""

    def test_basic_creation(self) -> None:
        q = Quantity(8e5, "A/m")
        assert q.value == 8e5
        assert q.unit == "A/m"
        assert q.uncertainty is None
        assert q.label is None

    def test_with_uncertainty(self) -> None:
        q = Quantity(8e5, "A/m", uncertainty=1e3)
        assert q.uncertainty == 1e3

    def test_with_label(self) -> None:
        q = Quantity(8e5, "A/m", label="M_s")
        assert q.label == "M_s"

    def test_factory_function(self) -> None:
        q = quantity(300.0, "K", label="T")
        assert q.value == 300.0
        assert q.unit == "K"
        assert q.label == "T"


# ---------------------------------------------------------------------------
# Unit conversion .to()
# ---------------------------------------------------------------------------


class TestQuantityConversion:
    """Quantity.to() conversion tests."""

    def test_identity_conversion(self) -> None:
        """Converting to the same unit leaves the value unchanged."""
        q = Quantity(8e5, "A/m")
        q2 = q.to("A/m")
        assert q2.value == q.value
        assert q2.unit == "A/m"

    def test_h_field_oe_to_am(self) -> None:
        """Magnetic field Oe → A/m conversion."""
        q = Quantity(1.0, "Oe")
        q2 = q.to("A/m")
        expected = 1000.0 / (4.0 * math.pi)
        assert math.isclose(q2.value, expected, rel_tol=1e-10)

    def test_h_field_am_to_oe(self) -> None:
        """Magnetic field A/m → Oe conversion."""
        q = Quantity(1000.0, "A/m")
        q2 = q.to("Oe")
        assert math.isclose(q2.value, 1000.0 * 4.0 * math.pi / 1000.0, rel_tol=1e-10)

    def test_magnetization_emu_to_am(self) -> None:
        """Magnetization emu/cm3 → A/m."""
        q = Quantity(800.0, "emu/cm3")
        q2 = q.to("A/m")
        assert math.isclose(q2.value, 8e5, rel_tol=1e-10)

    def test_length_nm_to_m(self) -> None:
        """Length nm → m."""
        q = Quantity(5.3, "nm")
        q2 = q.to("m")
        assert math.isclose(q2.value, 5.3e-9, rel_tol=1e-10)

    def test_length_m_to_nm(self) -> None:
        """Length m → nm."""
        q = Quantity(5.3e-9, "m")
        q2 = q.to("nm")
        assert math.isclose(q2.value, 5.3, rel_tol=1e-10)

    def test_length_nm_to_angstrom(self) -> None:
        """Length nm → Angstrom."""
        q = Quantity(1.0, "nm")
        q2 = q.to("A")
        assert math.isclose(q2.value, 10.0, rel_tol=1e-10)

    def test_mev_to_kelvin(self) -> None:
        """Exchange energy meV → K."""
        q = Quantity(1.0, "meV")
        q2 = q.to("K")
        # 1 meV = e×1e-3 / k_B K ≈ 11.605 K
        assert math.isclose(q2.value, 11.605, rel_tol=1e-3)

    def test_ghz_to_hz(self) -> None:
        """Frequency GHz → Hz."""
        q = Quantity(10.0, "GHz")
        q2 = q.to("Hz")
        assert math.isclose(q2.value, 10e9, rel_tol=1e-10)

    def test_unknown_conversion_raises(self) -> None:
        """Unsupported conversion raises ValueError."""
        q = Quantity(8e5, "A/m")
        with pytest.raises(ValueError, match="Unit conversion not supported"):
            q.to("kg")

    def test_label_preserved_on_conversion(self) -> None:
        """Label is preserved after conversion."""
        q = Quantity(800.0, "emu/cm3", label="M_s")
        q2 = q.to("A/m")
        assert q2.label == "M_s"

    def test_unit_preserved_after_to(self) -> None:
        """Original Quantity is immutable."""
        q = Quantity(800.0, "emu/cm3")
        _ = q.to("A/m")
        assert q.unit == "emu/cm3"
        assert q.value == 800.0


# ---------------------------------------------------------------------------
# Round-trip conversion
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Quantity round-trip conversion tests."""

    @pytest.mark.parametrize(
        "value, from_unit, to_unit",
        [
            (1.0, "Oe", "A/m"),
            (1000.0, "A/m", "Oe"),
            (1.0, "A/m", "T"),
            (800.0, "emu/cm3", "A/m"),
            (1.3e-11, "J/m", "erg/cm"),
            (100.0, "meV", "K"),
            (10.0, "GHz", "Hz"),
            (5.3, "nm", "m"),
        ],
    )
    def test_round_trip(self, value: float, from_unit: str, to_unit: str) -> None:
        """from_unit → to_unit → from_unit round-trip error < 1e-9."""
        q = Quantity(value, from_unit)
        q2 = q.to(to_unit).to(from_unit)
        assert math.isclose(q2.value, value, rel_tol=REL_TOL), (
            f"Round-trip failed: {value} {from_unit} → {to_unit} → {from_unit}, got {q2.value}"
        )


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


class TestArithmetic:
    """Quantity arithmetic operation tests."""

    def test_add_same_unit(self) -> None:
        q1 = Quantity(3e5, "A/m")
        q2 = Quantity(5e5, "A/m")
        result = q1 + q2
        assert math.isclose(result.value, 8e5, rel_tol=1e-12)
        assert result.unit == "A/m"

    def test_sub_same_unit(self) -> None:
        q1 = Quantity(8e5, "A/m")
        q2 = Quantity(3e5, "A/m")
        result = q1 - q2
        assert math.isclose(result.value, 5e5, rel_tol=1e-12)

    def test_add_different_units_raises(self) -> None:
        """Adding quantities with different units raises ValueError."""
        q1 = Quantity(8e5, "A/m")
        q2 = Quantity(1.0, "T")
        with pytest.raises(ValueError, match="Unit mismatch"):
            _ = q1 + q2

    def test_mul_scalar(self) -> None:
        q = Quantity(2.0, "A/m")
        result = q * 3.0
        assert math.isclose(result.value, 6.0, rel_tol=1e-12)
        assert result.unit == "A/m"

    def test_rmul_scalar(self) -> None:
        q = Quantity(2.0, "A/m")
        result = 3.0 * q
        assert math.isclose(result.value, 6.0, rel_tol=1e-12)

    def test_div_scalar(self) -> None:
        q = Quantity(6.0, "A/m")
        result = q / 3.0
        assert math.isclose(result.value, 2.0, rel_tol=1e-12)

    def test_div_by_zero_raises(self) -> None:
        q = Quantity(1.0, "A/m")
        with pytest.raises(ZeroDivisionError):
            _ = q / 0.0

    def test_neg(self) -> None:
        q = Quantity(5.0, "A/m")
        result = -q
        assert result.value == -5.0

    def test_abs(self) -> None:
        q = Quantity(-5.0, "A/m")
        result = abs(q)
        assert result.value == 5.0

    def test_uncertainty_propagation_add(self) -> None:
        """Addition uncertainty combined in quadrature."""
        q1 = Quantity(1.0, "A/m", uncertainty=0.1)
        q2 = Quantity(1.0, "A/m", uncertainty=0.1)
        result = q1 + q2
        assert result.uncertainty is not None
        expected_unc = math.sqrt(0.1**2 + 0.1**2)
        assert math.isclose(result.uncertainty, expected_unc, rel_tol=1e-10)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Quantity serialization and deserialization tests."""

    def test_to_dict_round_trip(self) -> None:
        """to_dict → from_dict round-trip."""
        q = Quantity(8e5, "A/m", uncertainty=1e3, label="M_s")
        d = q.to_dict()
        q2 = Quantity.from_dict(d)
        assert q2.value == q.value
        assert q2.unit == q.unit
        assert q2.uncertainty == q.uncertainty
        assert q2.label == q.label

    def test_to_dict_keys(self) -> None:
        """to_dict includes all required keys."""
        q = Quantity(1.0, "T")
        d = q.to_dict()
        assert "value" in d
        assert "unit" in d
        assert "uncertainty" in d
        assert "label" in d

    def test_from_dict_without_optional(self) -> None:
        """Restore from minimal dictionary."""
        d = {"value": 5.3e-9, "unit": "m"}
        q = Quantity.from_dict(d)
        assert math.isclose(q.value, 5.3e-9, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------


class TestRepresentation:
    """__repr__ and __format__ tests."""

    def test_repr_contains_value_and_unit(self) -> None:
        q = Quantity(8e5, "A/m")
        r = repr(q)
        assert "800000" in r or "8e+05" in r or "8e5" in r
        assert "A/m" in r

    def test_format(self) -> None:
        q = Quantity(8e5, "A/m")
        s = f"{q}"
        assert "A/m" in s
