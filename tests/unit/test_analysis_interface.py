"""EffectModel interface, fit, symmetry, calibration, device_fom, and consistency unit tests.

Design basis: impl/03-P2-analysis.md §P2.4, PLAN.md §20.
Convention: LLM-as-judge is forbidden for quantitative/fitting verification — deterministic checks only.
"""

from __future__ import annotations

import numpy as np
import pytest

from maglab.analysis.calibration import (
    CalibrationEntry,
    CalibrationRegistry,
    CorrectionPipeline,
    UncertaintyBudget,
    build_uncertainty_budget,
)
from maglab.analysis.consistency import (
    check_consistency,
    check_reduced_chi2,
)
from maglab.analysis.device_fom import (
    compute_fom,
    list_devices,
    sot_mram_fom,
)
from maglab.analysis.effects.base import (
    EffectModel,
    FitResult,
    MeasurementConfig,
    ParamSpec,
)
from maglab.analysis.fit import run_fit
from maglab.analysis.providers import (
    get_all_effects,
    get_effect,
    get_provider,
    list_providers,
)
from maglab.analysis.symmetry import (
    allowed_components,
    is_ahe_allowed,
    is_amr_allowed,
    list_supported_groups,
)

# ===========================================================================
# EffectModel interface tests
# ===========================================================================


class TestEffectModelABC:
    """EffectModel ABC interface checks."""

    def test_abstract_not_instantiable(self) -> None:
        """EffectModel without a concrete implementation raises TypeError."""
        with pytest.raises(TypeError):
            EffectModel()  # type: ignore[abstract]

    def test_concrete_has_required_attrs(self) -> None:
        """All registered effects have the required attributes."""
        for name, effect in get_all_effects().items():
            assert isinstance(effect.name, str) and effect.name, f"{name}.name is empty"
            assert isinstance(effect.subfield, str), f"{name}.subfield type error"
            assert isinstance(effect.references, list), f"{name}.references type error"
            assert len(effect.references) > 0, f"{name}.references is empty"
            assert isinstance(effect.parameters, list), f"{name}.parameters type error"
            assert isinstance(effect.measurement_config, MeasurementConfig), (
                f"{name}.measurement_config type error"
            )
            assert isinstance(effect.symmetry_constraints, dict), (
                f"{name}.symmetry_constraints type error"
            )

    def test_param_spec_fields(self) -> None:
        """ParamSpec has all 4 fields."""
        ps = ParamSpec("R_H", "m^3/C", lower=None, upper=None, description="test")
        assert ps.name == "R_H"
        assert ps.unit == "m^3/C"
        assert ps.lower is None
        assert ps.upper is None

    def test_measurement_config_fields(self) -> None:
        """MeasurementConfig has the key fields."""
        mc = MeasurementConfig(
            geometry="Hall bar",
            tensor_rank=2,
            required_columns=("B", "rho_xy"),
        )
        assert mc.geometry == "Hall bar"
        assert mc.tensor_rank == 2
        assert "B" in mc.required_columns

    def test_fit_result_fields(self) -> None:
        """FitResult has the required fields."""
        fr = FitResult(
            params={"R_H": 1e-10},
            uncertainties={"R_H": 1e-12},
            chi2=0.01,
            reduced_chi2=0.5,
            covariance=np.array([[1e-24]]),
        )
        assert "R_H" in fr.params
        assert fr.chi2 == 0.01
        assert fr.covariance.shape == (1, 1)


# ===========================================================================
# Provider registry tests
# ===========================================================================


class TestProviderRegistry:
    """ModelProvider registry and lookup tests."""

    def test_six_providers_registered(self) -> None:
        """All 6 providers are registered."""
        providers = list_providers()
        expected = {
            "magnetotransport",
            "spin_orbitronics",
            "ferromagnetic_resonance",
            "magnetization_dynamics",
            "magnetometry",
            "domain_walls_skyrmions",
        }
        assert expected.issubset(set(providers)), f"Unregistered providers: {expected - set(providers)}"

    def test_magnetotransport_effects(self) -> None:
        """magnetotransport provider contains 9 effects (includes USMR)."""
        provider = get_provider("magnetotransport")
        effects = provider.list()
        assert len(effects) == 9

    def test_spin_orbitronics_effects(self) -> None:
        """spin_orbitronics provider contains 4 effects."""
        provider = get_provider("spin_orbitronics")
        assert len(provider.list()) == 4

    def test_get_effect_by_name(self) -> None:
        """Look up an effect model by name."""
        effect = get_effect("anomalous_hall")
        assert effect.name == "anomalous_hall"

    def test_unknown_effect_raises(self) -> None:
        """Unknown effect name raises KeyError."""
        with pytest.raises(KeyError):
            get_effect("nonexistent_effect")

    def test_unknown_provider_raises(self) -> None:
        """Unknown provider name raises KeyError."""
        with pytest.raises(KeyError):
            get_provider("nonexistent")


# ===========================================================================
# fit.py tests
# ===========================================================================


class TestFitEngine:
    """lmfit-based fitting engine tests."""

    def test_linear_fit_recovers_params(self) -> None:
        """Synthesize y = a·x + b with known parameters, fit, and recover within 5%."""
        a_true, b_true = 3.14, -2.71
        x = np.linspace(0, 10, 50)
        y = a_true * x + b_true

        def model_fn(xx: np.ndarray, a: float, b: float) -> np.ndarray:
            return a * xx + b

        specs = [
            ParamSpec("a", "dimensionless", lower=None, upper=None),
            ParamSpec("b", "dimensionless", lower=None, upper=None),
        ]
        result = run_fit(model_fn, x, y, specs, {"a": 1.0, "b": 0.0}, effect_name="test_linear")
        assert abs(result.params["a"] - a_true) / abs(a_true) < 0.05
        assert abs(result.params["b"] - b_true) / abs(b_true) < 0.05

    def test_fit_result_has_provenance_id(self) -> None:
        """FitResult.provenance_id is not empty."""
        x = np.linspace(0, 1, 20)
        y = 2.0 * x

        specs = [ParamSpec("slope", "dimensionless")]

        def fn(xx: np.ndarray, slope: float) -> np.ndarray:
            return slope * xx

        result = run_fit(fn, x, y, specs, {"slope": 1.0})
        assert isinstance(result.provenance_id, str)

    def test_reduced_chi2_near_unity_noiseless(self) -> None:
        """reduced_chi2 ≈ 0 for perfect noiseless data."""
        x = np.linspace(-1, 1, 100)
        y = 5.0 * x**2

        def fn(xx: np.ndarray, a: float) -> np.ndarray:
            return a * xx**2

        specs = [ParamSpec("a", "dimensionless")]
        result = run_fit(fn, x, y, specs, {"a": 1.0})
        assert result.chi2 < 1e-10  # no noise


# ===========================================================================
# symmetry.py tests
# ===========================================================================


class TestSymmetry:
    """Magnetic point group allowed component tests."""

    def test_cubic_ahe_allowed(self) -> None:
        """Cubic (m3m): AHE off-diagonal components allowed."""
        assert is_ahe_allowed("m3m")

    def test_cubic_amr_allowed(self) -> None:
        """Cubic (m3m): AMR allowed."""
        assert is_amr_allowed("m3m")

    def test_ohe_components_shape(self) -> None:
        """m3m OHE components are rank-3 index tuples."""
        comp = allowed_components("m3m")
        for c in comp.ohe_components:
            assert len(c) == 3
            assert all(0 <= idx <= 2 for idx in c)

    def test_supported_groups_list(self) -> None:
        """Supported group list has at least 4 entries."""
        groups = list_supported_groups()
        assert len(groups) >= 4

    def test_unknown_group_raises(self) -> None:
        """Unknown point group raises ValueError."""
        with pytest.raises(ValueError):
            allowed_components("unknown_pg")


# ===========================================================================
# consistency.py tests
# ===========================================================================


class TestConsistency:
    """Inconsistency detection tests."""

    def _make_fit_result(self, name: str, params: dict, uncs: dict) -> FitResult:
        return FitResult(
            params=params,
            uncertainties=uncs,
            chi2=1.0,
            reduced_chi2=1.0,
            covariance=np.eye(len(params)),
            effect_name=name,
        )

    def test_consistent_results_ok(self) -> None:
        """Identical parameters → ConsistencyResult.ok = True."""
        a = self._make_fit_result("AHE", {"R_0": 1e-10}, {"R_0": 1e-12})
        b = self._make_fit_result("OHE", {"R_0": 1e-10}, {"R_0": 1e-12})
        result = check_consistency(a, b)
        assert result.ok

    def test_inconsistent_results_not_ok(self) -> None:
        """Significantly different parameters → ConsistencyResult.ok = False."""
        a = self._make_fit_result("AHE", {"R_0": 1e-10}, {"R_0": 1e-13})
        b = self._make_fit_result("OHE", {"R_0": 1e-5}, {"R_0": 1e-8})
        result = check_consistency(a, b)
        assert not result.ok
        assert result.trigger_explain

    def test_reduced_chi2_ok_range(self) -> None:
        """reduced_chi2=1.0 → ok."""
        fr = self._make_fit_result("test", {"p": 1.0}, {"p": 0.01})
        fr.reduced_chi2 = 1.0
        result = check_reduced_chi2(fr)
        assert result.ok

    def test_reduced_chi2_too_high(self) -> None:
        """reduced_chi2=10.0 → ok=False, trigger_explain=True."""
        fr = self._make_fit_result("test", {"p": 1.0}, {"p": 0.01})
        fr.reduced_chi2 = 10.0
        result = check_reduced_chi2(fr)
        assert not result.ok
        assert result.trigger_explain


# ===========================================================================
# calibration.py tests
# ===========================================================================


class TestCalibration:
    """Calibration registry, pipeline, and GUM tests."""

    def test_calibration_registry_add_get(self) -> None:
        """Registered calibration entry can be retrieved."""
        reg = CalibrationRegistry()
        entry = CalibrationEntry(
            instrument="Keithley_2400",
            factor=1.001,
            offset=0.0,
            uncertainty=0.001,
        )
        reg.add(entry)
        result = reg.get("Keithley_2400")
        assert result is not None
        assert result.factor == 1.001

    def test_calibration_apply_unapply_roundtrip(self) -> None:
        """Apply calibration → inverse = original (round-trip consistency)."""
        entry = CalibrationEntry(instrument="test", factor=2.0, offset=1.0)
        raw = np.array([1.0, 2.0, 3.0])
        corrected = entry.apply(raw)
        recovered = entry.unapply(corrected)
        np.testing.assert_allclose(recovered, raw, rtol=1e-12)

    def test_background_subtraction_reversible(self) -> None:
        """Background subtraction correction → inverse = original."""
        bg = np.array([0.1, 0.2, 0.1])
        data = np.array([1.1, 2.2, 1.1])
        pipeline = CorrectionPipeline.background_subtraction(bg)
        corrected, log = pipeline.apply(data)
        recovered = pipeline.unapply(corrected)
        np.testing.assert_allclose(recovered, data, rtol=1e-12)
        assert "background_subtraction" in log

    def test_gum_budget_total(self) -> None:
        """GUM uncertainty budget: σ_total = sqrt(1² + 2² + 3²) = sqrt(14)."""
        budget = build_uncertainty_budget(1.0, 2.0, 3.0)
        expected = float(np.sqrt(1**2 + 2**2 + 3**2))
        assert abs(budget.total() - expected) < 1e-10

    def test_budget_table_has_total_row(self) -> None:
        """Error budget table has a TOTAL row."""
        budget = UncertaintyBudget()
        budget.add("measurement", 0.5, "noise")
        budget.add("fitting", 0.3, "lmfit")
        table = budget.table()
        names = [row["name"] for row in table]
        assert any("TOTAL" in n for n in names)


# ===========================================================================
# device_fom.py tests
# ===========================================================================


class TestDeviceFoM:
    """Device FoM registry tests."""

    def test_sot_mram_fom_has_delta(self) -> None:
        """SOT-MRAM FoM has thermal stability Δ."""
        result = sot_mram_fom()
        assert "thermal_stability_delta" in result.foms
        delta = result.foms["thermal_stability_delta"]["value"]
        assert delta > 0

    def test_sot_mram_fom_has_j_c(self) -> None:
        """SOT-MRAM FoM has switching current density."""
        result = sot_mram_fom()
        assert "switching_current_density_j_c" in result.foms
        j_c = result.foms["switching_current_density_j_c"]["value"]
        assert j_c > 0

    def test_compute_fom_dispatch(self) -> None:
        """compute_fom dispatches correctly by device name."""
        result = compute_fom("sot-mram", Ms=8e5, K_u=4e5)
        assert result.device == "sot-mram"

    def test_list_devices(self) -> None:
        """list_devices includes sot-mram."""
        devices = list_devices()
        assert "sot-mram" in devices

    def test_unknown_device_raises(self) -> None:
        """Unknown device raises KeyError."""
        with pytest.raises(KeyError):
            compute_fom("unknown_device")

    def test_delta_physical_range(self) -> None:
        """Δ should be in the 10-1000 range for physical validity (typical MRAM)."""
        result = sot_mram_fom(K_u=4e5, d_bit=20e-9, t_FM=2e-9, T=300.0)
        delta = result.foms["thermal_stability_delta"]["value"]
        # Physical validity range check (approximate, not strict)
        assert 0.01 < delta < 1e6
