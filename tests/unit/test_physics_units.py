"""Unit conversion round-trip accuracy tests.

Validation principle (PLAN §20): deterministic checks only — LLM-as-judge forbidden.
Round-trip error tolerance: relative error < 1 ppm (1e-6).
"""

from __future__ import annotations

import math

from maglab.physics import units as u
from maglab.physics.constants import MU_0

REL_TOL = 1e-6  # 1 ppm round-trip tolerance


# ---------------------------------------------------------------------------
# Magnetic field H conversion
# ---------------------------------------------------------------------------


class TestHField:
    """Magnetic field Oe ↔ A/m ↔ T conversion tests."""

    def test_oe_to_am_known_value(self) -> None:
        """Verify 1 Oe = 1000/(4π) A/m is implemented exactly."""
        expected = 1000.0 / (4.0 * math.pi)
        assert math.isclose(u.oe_to_am(1.0), expected, rel_tol=1e-12)

    def test_oe_to_am_round_trip(self) -> None:
        """Oe → A/m → Oe round-trip."""
        for h_oe in [0.1, 1.0, 10.0, 100.0, 1e4, 1e6, -500.0]:
            restored = u.am_to_oe(u.oe_to_am(h_oe))
            assert math.isclose(restored, h_oe, rel_tol=REL_TOL), (
                f"Round-trip failed: h_oe={h_oe}, restored={restored}"
            )

    def test_am_to_oe_round_trip(self) -> None:
        """A/m → Oe → A/m round-trip."""
        for h_am in [79.577, 1000.0, 1e5, 1e7, -1e4]:
            restored = u.oe_to_am(u.am_to_oe(h_am))
            assert math.isclose(restored, h_am, rel_tol=REL_TOL)

    def test_am_to_tesla_known_value(self) -> None:
        """A/m → T: verify μ₀H relationship."""
        h = 1e6  # A/m
        expected = MU_0 * h
        assert math.isclose(u.am_to_tesla(h), expected, rel_tol=1e-12)

    def test_am_to_tesla_round_trip(self) -> None:
        """A/m → T → A/m round-trip."""
        for h in [1.0, 1e3, 1e5, 1e6, 8e5]:
            assert math.isclose(u.tesla_to_am(u.am_to_tesla(h)), h, rel_tol=REL_TOL)

    def test_oe_to_tesla_round_trip(self) -> None:
        """Oe → T → Oe round-trip (composite conversion)."""
        for h_oe in [1.0, 100.0, 1e4, 1e6]:
            assert math.isclose(u.tesla_to_oe(u.oe_to_tesla(h_oe)), h_oe, rel_tol=REL_TOL)

    def test_zero_field(self) -> None:
        """Zero field conversion."""
        assert u.oe_to_am(0.0) == 0.0
        assert u.am_to_oe(0.0) == 0.0
        assert u.am_to_tesla(0.0) == 0.0

    def test_10000_oe_to_am(self) -> None:
        """10000 Oe ≈ 795775 A/m (textbook standard value)."""
        # 10000 Oe = 10000 × 1000/(4π) A/m
        expected = 10000.0 * 1000.0 / (4.0 * math.pi)
        assert math.isclose(u.oe_to_am(10000.0), expected, rel_tol=1e-10)


# ---------------------------------------------------------------------------
# Magnetization M conversion
# ---------------------------------------------------------------------------


class TestMagnetization:
    """Magnetization emu/cm³ ↔ A/m conversion tests."""

    def test_emu_cm3_to_am_factor(self) -> None:
        """1 emu/cm³ = 1000 A/m."""
        assert math.isclose(u.emu_cm3_to_am(1.0), 1000.0, rel_tol=1e-12)

    def test_am_to_emu_cm3_factor(self) -> None:
        """1000 A/m = 1 emu/cm³."""
        assert math.isclose(u.am_to_emu_cm3(1000.0), 1.0, rel_tol=1e-12)

    def test_round_trip_emu_to_am(self) -> None:
        """emu/cm³ → A/m → emu/cm³ round-trip."""
        for m_emu in [0.01, 1.0, 100.0, 800.0, 1700.0]:
            assert math.isclose(u.am_to_emu_cm3(u.emu_cm3_to_am(m_emu)), m_emu, rel_tol=REL_TOL)

    def test_round_trip_am_to_emu(self) -> None:
        """A/m → emu/cm³ → A/m round-trip."""
        for m_am in [1e3, 8e5, 1.44e6, 1.71e6]:
            assert math.isclose(u.emu_cm3_to_am(u.am_to_emu_cm3(m_am)), m_am, rel_tol=REL_TOL)

    def test_permalloy_ms(self) -> None:
        """Permalloy M_s=800 emu/cm³ → 800000 A/m."""
        assert math.isclose(u.emu_cm3_to_am(800.0), 8e5, rel_tol=1e-10)


# ---------------------------------------------------------------------------
# Energy density
# ---------------------------------------------------------------------------


class TestEnergyDensity:
    """Energy density erg/cm³ ↔ J/m³ conversion tests."""

    def test_erg_cm3_to_jm3_factor(self) -> None:
        """1 erg/cm³ = 0.1 J/m³."""
        assert math.isclose(u.erg_cm3_to_jm3(1.0), 0.1, rel_tol=1e-12)

    def test_round_trip_erg_cm3(self) -> None:
        """erg/cm³ → J/m³ → erg/cm³ round-trip."""
        for e_erg in [1.0, 10.0, 4.8e5, 1e8]:
            assert math.isclose(u.jm3_to_erg_cm3(u.erg_cm3_to_jm3(e_erg)), e_erg, rel_tol=REL_TOL)

    def test_round_trip_jm3(self) -> None:
        """J/m³ → erg/cm³ → J/m³ round-trip."""
        for e_jm3 in [0.1, 1.0, 4.8e4, 4.1e5]:
            assert math.isclose(u.erg_cm3_to_jm3(u.jm3_to_erg_cm3(e_jm3)), e_jm3, rel_tol=REL_TOL)


# ---------------------------------------------------------------------------
# Energy per length (exchange stiffness, domain wall energy)
# ---------------------------------------------------------------------------


class TestEnergyPerLength:
    """Energy/length erg/cm ↔ J/m conversion tests."""

    def test_erg_cm_to_jm_factor(self) -> None:
        """1 erg/cm = 1e-3 J/m."""
        assert math.isclose(u.erg_cm_to_jm(1.0), 1e-3, rel_tol=1e-12)

    def test_round_trip_erg_cm(self) -> None:
        """erg/cm → J/m → erg/cm round-trip."""
        for sigma in [0.01, 1.0, 10.0, 100.0]:
            assert math.isclose(u.jm_to_erg_cm(u.erg_cm_to_jm(sigma)), sigma, rel_tol=REL_TOL)

    def test_exchange_stiffness_permalloy(self) -> None:
        """Permalloy A = 1.3 μerg/cm = 1.3e-6 erg/cm = 1.3e-9 J/m ≠ 1.3e-11 J/m.

        Note: erg/cm and μerg/cm are frequently conflated in the literature.
        A = 1.3e-6 erg/cm = 1.3e-9 J/m. If the literature gives A = 1.3e-11 J/m,
        then 1.3e-11 J/m = 1.3e-8 erg/cm — verified here.
        """
        # 1.3e-11 J/m in erg/cm:
        a_jm = 1.3e-11
        a_erg_cm = u.jm_to_erg_cm(a_jm)
        assert math.isclose(a_erg_cm, 1.3e-8, rel_tol=1e-10)
        # verify inverse
        assert math.isclose(u.erg_cm_to_jm(a_erg_cm), a_jm, rel_tol=1e-10)


# ---------------------------------------------------------------------------
# Exchange energy meV ↔ K
# ---------------------------------------------------------------------------


class TestExchangeEnergy:
    """Exchange energy meV ↔ K conversion tests."""

    def test_mev_to_kelvin_known(self) -> None:
        """1 meV → K: 1.60218e-22 J / 1.38065e-23 J/K ≈ 11.605 K."""
        from maglab.physics.constants import E_CHARGE, K_B

        expected = E_CHARGE * 1e-3 / K_B
        assert math.isclose(u.mev_to_kelvin(1.0), expected, rel_tol=1e-6)

    def test_round_trip_mev_to_k(self) -> None:
        """meV → K → meV round-trip."""
        for e_mev in [0.1, 1.0, 10.0, 100.0, 500.0]:
            assert math.isclose(u.kelvin_to_mev(u.mev_to_kelvin(e_mev)), e_mev, rel_tol=REL_TOL)

    def test_round_trip_k_to_mev(self) -> None:
        """K → meV → K round-trip."""
        for t_k in [10.0, 100.0, 300.0, 1000.0]:
            assert math.isclose(u.mev_to_kelvin(u.kelvin_to_mev(t_k)), t_k, rel_tol=REL_TOL)


# ---------------------------------------------------------------------------
# DMI mJ/m² ↔ meV/Å²
# ---------------------------------------------------------------------------


class TestDMI:
    """DMI mJ/m² ↔ meV/Å² conversion tests."""

    def test_mev_a2_to_mjm2_factor(self) -> None:
        """1 meV/Å² = ? mJ/m².

        1 meV/Å² = 1.60218e-22 J / 1e-20 m² = 1.60218e-2 J/m² = 16.0218 mJ/m².
        """
        from maglab.physics.constants import E_CHARGE

        expected = (E_CHARGE * 1e-3) / 1e-20 * 1e3  # mJ/m²
        assert math.isclose(u.mev_a2_to_mjm2(1.0), expected, rel_tol=1e-6)

    def test_round_trip_dmi(self) -> None:
        """meV/Å² → mJ/m² → meV/Å² round-trip."""
        for d in [0.1, 0.5, 1.0, 2.0, 5.0]:
            assert math.isclose(u.mjm2_to_mev_a2(u.mev_a2_to_mjm2(d)), d, rel_tol=REL_TOL)

    def test_round_trip_mjm2(self) -> None:
        """mJ/m² → meV/Å² → mJ/m² round-trip."""
        for d in [0.5, 1.0, 2.5, 5.0, 10.0]:
            assert math.isclose(u.mev_a2_to_mjm2(u.mjm2_to_mev_a2(d)), d, rel_tol=REL_TOL)


# ---------------------------------------------------------------------------
# CGS_SI_FACTORS dictionary
# ---------------------------------------------------------------------------


class TestCGSSIFactors:
    """CGS_SI_FACTORS dictionary consistency tests."""

    def test_h_field_factor(self) -> None:
        """CGS_SI_FACTORS['H_field'] factor matches oe_to_am(1)."""
        factor, cgs_unit, si_unit = u.CGS_SI_FACTORS["H_field"]
        assert si_unit == "A/m"
        assert math.isclose(factor, u.oe_to_am(1.0), rel_tol=1e-12)

    def test_magnetization_factor(self) -> None:
        """CGS_SI_FACTORS['M_magnetization'] factor matches emu_cm3_to_am(1)."""
        factor, _, si_unit = u.CGS_SI_FACTORS["M_magnetization"]
        assert si_unit == "A/m"
        assert math.isclose(factor, u.emu_cm3_to_am(1.0), rel_tol=1e-12)
