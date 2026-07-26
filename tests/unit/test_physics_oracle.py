"""Physical/unphysical input oracle judgment tests.

Validation principle (PLAN §20): accurate judgment for multiple physical and unphysical cases.
LLM-as-judge is forbidden — deterministic checks only.
"""

from __future__ import annotations

import pytest

from maglab.physics import oracle as oc
from maglab.physics.oracle import OracleResult, check, check_energy_conservation

# ---------------------------------------------------------------------------
# OracleResult data structure
# ---------------------------------------------------------------------------


class TestOracleResult:
    """OracleResult basic behavior."""

    def test_ok_result_is_truthy(self) -> None:
        r = OracleResult(ok=True)
        assert bool(r) is True

    def test_fail_result_is_falsy(self) -> None:
        r = OracleResult(ok=False, reason="test failure")
        assert bool(r) is False

    def test_fail_has_reason(self) -> None:
        r = OracleResult(ok=False, reason="negative temperature", param="T", value=-10.0)
        assert r.reason != ""
        assert r.param == "T"
        assert r.value == -10.0


# ---------------------------------------------------------------------------
# Damping constant α
# ---------------------------------------------------------------------------


class TestCheckDamping:
    """check_damping tests — 5 physical + 5 unphysical."""

    @pytest.mark.parametrize(
        "alpha",
        [
            0.0,  # boundary value — physically allowed
            0.001,  # YIG level
            0.008,  # Permalloy level
            0.5,  # high damping
            1.0,  # maximum allowed boundary
        ],
    )
    def test_physical_alpha(self, alpha: float) -> None:
        assert oc.check_damping(alpha).ok, f"α={alpha} should be physical"

    @pytest.mark.parametrize(
        "alpha",
        [
            -1e-6,  # negative (even very small values are unphysical)
            -0.001,
            -1.0,
            1.001,  # exceeds 1
            10.0,
        ],
    )
    def test_unphysical_alpha(self, alpha: float) -> None:
        result = oc.check_damping(alpha)
        assert not result.ok, f"α={alpha} should be rejected as unphysical"
        assert result.reason != ""
        assert result.param == "alpha"


# ---------------------------------------------------------------------------
# Saturation magnetization M_s
# ---------------------------------------------------------------------------


class TestCheckSaturationMagnetization:
    """check_saturation_magnetization tests — physical + unphysical."""

    @pytest.mark.parametrize(
        "ms",
        [
            1.43e5,  # YIG
            4.85e5,  # Ni
            8.0e5,  # Permalloy
            1.44e6,  # Co
            1.71e6,  # Fe
        ],
    )
    def test_physical_ms(self, ms: float) -> None:
        assert oc.check_saturation_magnetization(ms).ok, f"Ms={ms} A/m should be physical"

    @pytest.mark.parametrize(
        "ms",
        [
            0.0,  # zero is unphysical
            -1e5,
            -1.0,
            1e9,  # exceeds unphysical upper bound
            1e10,
        ],
    )
    def test_unphysical_ms(self, ms: float) -> None:
        result = oc.check_saturation_magnetization(ms)
        assert not result.ok, f"Ms={ms} A/m should be rejected as unphysical"
        assert result.reason != ""


# ---------------------------------------------------------------------------
# Magnetization M ≤ M_s
# ---------------------------------------------------------------------------


class TestCheckMagnetization:
    """check_magnetization tests."""

    @pytest.mark.parametrize(
        "m, ms",
        [
            (0.0, 8e5),  # M = 0
            (4e5, 8e5),  # M = Ms/2
            (8e5, 8e5),  # M = Ms (boundary)
            (-8e5, 8e5),  # reversed (absolute value check)
            (1.7e6, 1.71e6),  # Fe near saturation
        ],
    )
    def test_physical_magnetization(self, m: float, ms: float) -> None:
        assert oc.check_magnetization(m, ms).ok, f"M={m}, Ms={ms} should be physical"

    @pytest.mark.parametrize(
        "m, ms",
        [
            (9e5, 8e5),  # M > Ms
            (1.8e6, 1.71e6),  # Fe over-saturation
            (1.0, 0.0),  # Ms=0 is unphysical
            (-1.0, 0.5),  # Ms too small (outside valid range, ok=False here)
        ],
    )
    def test_unphysical_magnetization(self, m: float, ms: float) -> None:
        result = oc.check_magnetization(m, ms)
        assert not result.ok, f"M={m}, Ms={ms} should be rejected as unphysical"


# ---------------------------------------------------------------------------
# Temperature T
# ---------------------------------------------------------------------------


class TestCheckTemperature:
    """check_temperature tests — 5 physical + 5 unphysical."""

    @pytest.mark.parametrize("t", [0.001, 1.0, 77.0, 300.0, 1043.0])
    def test_physical_temperature(self, t: float) -> None:
        assert oc.check_temperature(t).ok, f"T={t} K should be physical"

    @pytest.mark.parametrize("t", [0.0, -0.001, -1.0, -77.0, -300.0])
    def test_unphysical_temperature(self, t: float) -> None:
        result = oc.check_temperature(t)
        assert not result.ok, f"T={t} K should be rejected as unphysical"
        assert result.param == "T"


# ---------------------------------------------------------------------------
# Velocity limit
# ---------------------------------------------------------------------------


class TestCheckVelocity:
    """check_velocity tests."""

    @pytest.mark.parametrize("v", [0.0, 100.0, 1000.0, 1e5, 1e8])
    def test_physical_velocity(self, v: float) -> None:
        assert oc.check_velocity(v).ok, f"v={v} m/s should be physical"

    @pytest.mark.parametrize("v", [3e8, 4e8, 1e9, -3e8, -1e9])
    def test_unphysical_velocity(self, v: float) -> None:
        result = oc.check_velocity(v)
        assert not result.ok, f"v={v} m/s should be rejected as unphysical"
        assert result.param == "velocity"


# ---------------------------------------------------------------------------
# Exchange stiffness A
# ---------------------------------------------------------------------------


class TestCheckExchangeStiffness:
    """check_exchange_stiffness tests."""

    @pytest.mark.parametrize(
        "a",
        [4e-12, 9e-12, 1.3e-11, 2.1e-11, 3e-11],
    )
    def test_physical_A(self, a: float) -> None:
        assert oc.check_exchange_stiffness(a).ok

    @pytest.mark.parametrize("a", [0.0, -1e-12, -1.0])
    def test_unphysical_A(self, a: float) -> None:
        result = oc.check_exchange_stiffness(a)
        assert not result.ok
        assert result.param == "A"


# ---------------------------------------------------------------------------
# Anisotropy constant K
# ---------------------------------------------------------------------------


class TestCheckAnisotropy:
    """check_anisotropy tests."""

    @pytest.mark.parametrize(
        "k",
        [-4.5e3, 0.0, 1e4, 4.1e5, 4.8e4],
    )
    def test_physical_K(self, k: float) -> None:
        assert oc.check_anisotropy(k).ok

    @pytest.mark.parametrize("k", [1.1e10, -1.1e10, 1e15])
    def test_unphysical_K(self, k: float) -> None:
        result = oc.check_anisotropy(k)
        assert not result.ok
        assert result.param == "K"


# ---------------------------------------------------------------------------
# Curie temperature T_C
# ---------------------------------------------------------------------------


class TestCheckCurieTemperature:
    """check_curie_temperature tests."""

    @pytest.mark.parametrize("tc", [37.0, 559.0, 627.0, 1043.0, 1388.0])
    def test_physical_tc(self, tc: float) -> None:
        assert oc.check_curie_temperature(tc).ok

    @pytest.mark.parametrize("tc", [0.0, -1.0, 5001.0, 1e6])
    def test_unphysical_tc(self, tc: float) -> None:
        result = oc.check_curie_temperature(tc)
        assert not result.ok
        assert result.param == "T_C"


# ---------------------------------------------------------------------------
# Energy conservation
# ---------------------------------------------------------------------------


class TestCheckEnergyConservation:
    """check_energy_conservation tests."""

    def test_energy_decreasing(self) -> None:
        """Energy decreasing due to dissipation — should pass."""
        result = oc.check_energy_conservation(
            e_initial=1000.0,
            e_final=900.0,
            dissipation=100.0,
        )
        assert result.ok

    def test_energy_increase_rejected(self) -> None:
        """Energy increase — should be rejected."""
        result = oc.check_energy_conservation(
            e_initial=1000.0,
            e_final=1100.0,
            dissipation=0.0,
        )
        assert not result.ok

    def test_negative_dissipation_rejected(self) -> None:
        """Negative dissipation — should be rejected."""
        result = oc.check_energy_conservation(
            e_initial=1000.0,
            e_final=900.0,
            dissipation=-50.0,
        )
        assert not result.ok


# ---------------------------------------------------------------------------
# Integrated check() function
# ---------------------------------------------------------------------------


class TestCheckIntegration:
    """Integrated check() entry point tests."""

    def test_all_physical_params(self) -> None:
        """Typical Permalloy parameters — all physical."""
        result = oc.check(
            {
                "alpha": 0.008,
                "Ms": 8e5,
                "M": 7e5,
                "T": 300.0,
                "A": 1.3e-11,
            }
        )
        assert result.ok

    def test_negative_alpha_rejected(self) -> None:
        """Negative α → immediate rejection with reason."""
        result = oc.check({"alpha": -0.1, "Ms": 8e5})
        assert not result.ok
        assert "alpha" in result.reason.lower() or result.param == "alpha"

    def test_m_exceeds_ms_rejected(self) -> None:
        """M > Ms → rejected."""
        result = oc.check({"Ms": 8e5, "M": 9e5})
        assert not result.ok

    def test_negative_temperature_rejected(self) -> None:
        """T ≤ 0 → rejected."""
        result = oc.check({"T": -100.0})
        assert not result.ok
        assert result.param == "T"

    def test_superluminal_velocity_rejected(self) -> None:
        """v ≥ c → rejected."""
        result = oc.check({"velocity": 4e8})
        assert not result.ok
        assert result.param == "velocity"

    def test_empty_params_ok(self) -> None:
        """Empty dictionary → no checks, ok=True."""
        result = oc.check({})
        assert result.ok

    def test_checks_list_populated(self) -> None:
        """Passed check list is populated."""
        result = oc.check({"alpha": 0.01, "T": 300.0, "Ms": 8e5})
        assert len(result.checks) > 0

    def test_unphysical_ms_range(self) -> None:
        """Ms = 1e9 A/m → rejected as unphysical range."""
        result = oc.check({"Ms": 1e9})
        assert not result.ok

    def test_yig_params(self) -> None:
        """YIG parameters — physical."""
        result = oc.check(
            {
                "alpha": 0.0002,
                "Ms": 1.43e5,
                "T": 300.0,
                "A": 4e-12,
                "K": -610.0,
                "T_C": 559.0,
            }
        )
        assert result.ok

    def test_exchange_length_positive(self) -> None:
        """Valid exchange length — should pass."""
        result = oc.check({"l_ex": 5.3e-9})
        assert result.ok

    def test_exchange_length_negative_rejected(self) -> None:
        """Negative exchange length → rejected."""
        result = oc.check({"l_ex": -1e-9})
        assert not result.ok


class TestNonFiniteInputs:
    """NaN and ±inf must be rejected, not waved through.

    Every range check is a pair of comparisons, and IEEE-754 makes all
    comparisons against NaN false — so `check_damping(nan)` found α neither
    below 0 nor above 1 and reported it physical, and `+inf` slipped past the
    one-sided checks the same way. A NaN admitted by the oracle then propagates
    silently through the calculation and can be recorded as a result, because
    NaN arithmetic does not raise either.
    """

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    @pytest.mark.parametrize(
        "params",
        [
            {"alpha": None},
            {"T": None},
            {"Ms": None},
            {"velocity": None},
            {"A": None},
            {"K": None},
            {"T_C": None},
            {"l_ex": None},
        ],
    )
    def test_check_rejects_non_finite(self, params: dict, bad: float) -> None:
        key = next(iter(params))
        result = check({key: bad})

        assert not result.ok, f"{key}={bad} was accepted as physical"
        assert result.param == key
        assert "finite" in result.reason

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_magnetization_pair_rejects_non_finite(self, bad: float) -> None:
        assert not check({"M": bad, "Ms": 8e5}).ok
        assert not check({"M": 4e5, "Ms": bad}).ok

    def test_non_numeric_values_are_rejected(self) -> None:
        result = check({"alpha": "0.01"})
        assert not result.ok
        assert "not a number" in result.reason

    def test_booleans_are_not_accepted_as_numbers(self) -> None:
        result = check({"alpha": True})
        assert not result.ok

    @pytest.mark.parametrize(
        "params",
        [
            {"alpha": 0.008},
            {"T": 300.0},
            {"Ms": 8.0e5},
            {"velocity": 120.0},
            {"A": 1.3e-11},
            {"T_C": 850.0},
            {"l_ex": 5.0e-9},
            {"M": 4.0e5, "Ms": 8.0e5},
        ],
    )
    def test_physical_values_still_pass(self, params: dict) -> None:
        assert check(params).ok, f"{params} was wrongly rejected"

    def test_energy_conservation_rejects_non_finite(self) -> None:
        assert not check_energy_conservation(float("nan"), 1.0, 0.5).ok
        assert not check_energy_conservation(1.0, float("inf"), 0.5).ok
        assert not check_energy_conservation(1.0, 0.4, float("nan")).ok


class TestNonFiniteBlockedAtTheToolGate:
    """The oracle hook exists to stop unphysical parameters before a tool runs."""

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_hook_blocks_non_finite_parameters(self, bad: float) -> None:
        from maglab.core.hooks import ToolCall, default_registry

        allowed, reason = default_registry().is_allowed(
            ToolCall(name="physics_compute", args={"alpha": bad})
        )

        assert not allowed, "a non-finite parameter reached the tool"
        assert "oracle" in reason.lower()

    def test_hook_still_allows_physical_parameters(self) -> None:
        from maglab.core.hooks import ToolCall, default_registry

        allowed, _reason = default_registry().is_allowed(
            ToolCall(name="physics_compute", args={"alpha": 0.008, "T": 300.0})
        )
        assert allowed
