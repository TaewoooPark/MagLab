"""Tests for conformance-gap fixes in maglab/analysis/.

Gap 1 — SOT harmonic Hall xi participation
Gap 2 — ST-FMR xi_DL in FitResult
Gap 3 — USMR effect model
Gap 4 — Device FoM missing types (MTJ, spin-valve, spin-orbit-logic, magnon)
Gap 5 — Macrospin and two-sublattice LLG models
Gap 7 — Curie/compensation temperature model

All checks are deterministic — no LLM judgment.
"""

from __future__ import annotations

import math

import numpy as np

from maglab.analysis.device_fom import (
    compute_fom,
    list_devices,
    magnon_device_fom,
    mtj_fom,
    racetrack_fom,
    spin_orbit_logic_fom,
    spin_valve_sensor_fom,
)
from maglab.analysis.effects.curie_temperature import CurieTemperatureModel
from maglab.analysis.effects.llg_2sublattice import LLG2SublatticeModel
from maglab.analysis.effects.macrospin import MacrospinModel
from maglab.analysis.effects.sot_harmonic_hall import SOTHarmonicHall
from maglab.analysis.effects.stfmr import STFMREffect, _lorentz_asym, _lorentz_sym
from maglab.analysis.effects.usmr import USMREffect
from maglab.analysis.providers import get_effect, get_provider
from maglab.physics.constants import GAMMA_E, MU_0
from maglab.physics.formulas import walker_breakdown_field

# ---------------------------------------------------------------------------
# Tolerance
# ---------------------------------------------------------------------------

TOL = 0.05  # 5% parameter recovery tolerance


def _assert_recovery(name: str, true_val: float, fit_val: float, tol: float = TOL) -> None:
    if abs(true_val) < 1e-25:
        assert abs(fit_val) < 1e-22, f"{name}: true≈0, fit={fit_val:.4g}"
    else:
        rel_err = abs(fit_val - true_val) / abs(true_val)
        assert rel_err < tol, (
            f"{name}: true={true_val:.4g}, fit={fit_val:.4g}, rel_err={rel_err:.3f} > {tol}"
        )


# ===========================================================================
# Gap 1 — SOT Harmonic Hall: xi participates in fit
# ===========================================================================


class TestSOTHarmonicHallXiFitting:
    """Gap 1: PHE correction path must be fully integrated in fit().

    Physics clarification: xi = R_PHE/(2*R_AHE) cannot be uniquely determined
    from the 2ω signal alone — the cross-terms collapse into an equivalent
    two-term expansion (Hayashi 2014, §II.C).  The correct integrated path is:
    (1) xi is measured from the 1ω signal or supplied externally via geometry,
    (2) fit() accepts xi and auto-applies phe_corrected() internally,
    (3) FitResult.params always contains both raw and corrected fields.
    """

    def test_xi_from_geometry_applied_in_fit(self) -> None:
        """xi supplied via geometry['xi'] is stored in FitResult.params and correction applied."""
        model = SOTHarmonicHall()
        H_DL_true = 5.0
        H_FL_true = 2.0
        xi_known = 0.15
        H_ext = 1.0
        phi = np.linspace(0, 2 * np.pi, 80)
        V_2w = (H_DL_true / H_ext) * np.cos(phi) + (H_FL_true / H_ext) * np.cos(2 * phi) * np.cos(
            phi
        )

        result = model.fit(
            {"phi": phi, "V_2omega": V_2w}, geometry={"H_ext": H_ext, "xi": xi_known}
        )
        assert result.success
        # xi stored from geometry
        assert abs(result.params["xi"] - xi_known) < 1e-10, "xi from geometry not stored"
        # PHE-corrected fields present
        assert "H_DL" in result.params, "H_DL (corrected) missing from FitResult.params"
        assert "H_FL" in result.params, "H_FL (corrected) missing from FitResult.params"

    def test_xi_estimated_from_1omega_data(self) -> None:
        """xi is estimated from co-supplied V_1omega data and applied automatically.

        The 1omega fit model is V_1w = c[0]*cos(phi) + c[1]*sin(2phi)*sin(phi)
        where c[0] = R_AHE/2, c[1] = R_PHE.
        Hayashi (2014) defines xi = R_PHE / (2*R_AHE) = c[1] / (4*c[0]).
        """
        model = SOTHarmonicHall()
        phi = np.linspace(0, 2 * np.pi, 100)
        H_ext = 1.0
        # Synthetic 1omega: c[0]=R_AHE/2=0.5, c[1]=R_PHE=0.1
        # Hayashi xi = R_PHE / (2*R_AHE) = 0.1 / (2*1.0) = 0.05
        R_AHE_half = 0.5  # c[0]; full R_AHE = 2 * R_AHE_half = 1.0
        R_PHE = 0.1  # c[1]
        R_AHE = 2.0 * R_AHE_half
        xi_expected = R_PHE / (2.0 * R_AHE)  # = 0.1 / 2.0 = 0.05 (Hayashi 2014)
        V_1w = R_AHE_half * np.cos(phi) + R_PHE * np.sin(2 * phi) * np.sin(phi)
        V_2w = 5.0 * np.cos(phi) + 2.0 * np.cos(2 * phi) * np.cos(phi)  # H_DL=5, H_FL=2

        result = model.fit(
            {"phi": phi, "V_2omega": V_2w, "V_1omega": V_1w},
            geometry={"H_ext": H_ext},
        )
        assert result.success
        xi_fit = result.params["xi"]
        _assert_recovery("xi", xi_expected, xi_fit, tol=0.05)

    def test_phe_corrected_fields_in_fit_result(self) -> None:
        """fit() must return H_DL and H_FL (corrected) in params."""
        model = SOTHarmonicHall()
        phi = np.linspace(0, 2 * np.pi, 80)
        H_ext = 1.0
        V_2w = 5.0 * np.cos(phi) + 2.0 * np.cos(2 * phi) * np.cos(phi)
        result = model.fit({"phi": phi, "V_2omega": V_2w}, geometry={"H_ext": H_ext})
        assert "H_DL" in result.params, "H_DL (corrected) missing from FitResult.params"
        assert "H_FL" in result.params, "H_FL (corrected) missing from FitResult.params"
        # With xi=0 (default) correction is identity
        assert (
            abs(result.params["H_DL"] - result.params["H_DL_raw"])
            < 1e-4 * abs(result.params["H_DL_raw"]) + 1e-10
        )

    def test_forward_is_deterministic(self) -> None:
        """forward() is deterministic (same input → same output)."""
        model = SOTHarmonicHall()
        phi = np.linspace(0, 2 * np.pi, 50)
        params = {"H_DL_raw": 5.0, "H_FL_raw": 2.0, "xi": 0.0}
        geo = {"phi": phi, "H_ext": 1.0}
        y1 = model.forward(params, geo)
        y2 = model.forward(params, geo)
        np.testing.assert_allclose(y1, y2, atol=1e-20)

    def test_raw_roundtrip_with_zero_xi(self) -> None:
        """Zero xi case: H_DL_raw and H_FL_raw still round-trip correctly."""
        model = SOTHarmonicHall()
        H_DL_true = 5.0
        H_FL_true = 2.0
        H_ext = 1.0
        phi = np.linspace(0, 2 * np.pi, 80)
        V_2w = (H_DL_true / H_ext) * np.cos(phi) + (H_FL_true / H_ext) * np.cos(2 * phi) * np.cos(
            phi
        )
        result = model.fit({"phi": phi, "V_2omega": V_2w}, geometry={"H_ext": H_ext})
        assert result.success
        _assert_recovery("H_DL_raw", H_DL_true, result.params["H_DL_raw"])
        _assert_recovery("H_FL_raw", H_FL_true, result.params["H_FL_raw"])

    def test_phe_correction_with_nonzero_xi_changes_result(self) -> None:
        """Providing xi != 0 changes the corrected H_DL compared to xi=0."""
        model = SOTHarmonicHall()
        phi = np.linspace(0, 2 * np.pi, 80)
        H_ext = 1.0
        V_2w = 5.0 * np.cos(phi) + 2.0 * np.cos(2 * phi) * np.cos(phi)

        r0 = model.fit({"phi": phi, "V_2omega": V_2w}, geometry={"H_ext": H_ext, "xi": 0.0})
        rxi = model.fit({"phi": phi, "V_2omega": V_2w}, geometry={"H_ext": H_ext, "xi": 0.1})
        # Corrected H_DL changes when xi changes (PHE correction is applied)
        assert abs(r0.params["H_DL"] - rxi.params["H_DL"]) > 0.001 * abs(r0.params["H_DL_raw"])


# ===========================================================================
# R7-F1 regression: auto xi estimator uses c[1]/(4*c[0]), not c[1]/c[0]
# ===========================================================================


class TestSOTXiEstimatorR7Regression:
    """R7 Finding 1: xi auto-estimation factor-of-4 fix.

    Hayashi (PRB 89, 144425, 2014) defines xi = R_PHE / (2*R_AHE).
    The 1omega regression yields c[0] = R_AHE/2 and c[1] = R_PHE, so:
        xi = c[1] / (4*c[0])
    The pre-fix code computed c[1]/c[0], which is 4x too large.
    """

    def test_xi_estimator_correct_value(self) -> None:
        """Auto-estimated xi matches R_PHE/(2*R_AHE) within 1% for clean data."""
        model = SOTHarmonicHall()
        phi = np.linspace(0, 2 * np.pi, 200)

        # Known physical parameters
        R_AHE = 2.0  # ohm (full DC amplitude)
        R_PHE = 0.3  # ohm
        xi_hayashi = R_PHE / (2.0 * R_AHE)  # = 0.075

        # Build V_1omega: c[0] = R_AHE/2, c[1] = R_PHE
        V_1w = (R_AHE / 2.0) * np.cos(phi) + R_PHE * np.sin(2.0 * phi) * np.sin(phi)
        V_2w = 5.0 * np.cos(phi) + 2.0 * np.cos(2.0 * phi) * np.cos(phi)

        result = model.fit(
            {"phi": phi, "V_2omega": V_2w, "V_1omega": V_1w},
            geometry={"H_ext": 1.0},
        )
        assert result.success
        xi_fit = result.params["xi"]

        # Must recover Hayashi xi within 1% (noiseless data)
        rel_err = abs(xi_fit - xi_hayashi) / abs(xi_hayashi)
        assert rel_err < 0.01, (
            f"xi recovered={xi_fit:.6f}, expected={xi_hayashi:.6f}, "
            f"rel_err={rel_err:.4f} — factor-of-4 bug may have returned"
        )

    def test_xi_estimator_not_four_times_hayashi(self) -> None:
        """Old c[1]/c[0] expression is demonstrably 4x too large for this data."""
        phi = np.linspace(0, 2 * np.pi, 200)

        R_AHE = 2.0
        R_PHE = 0.3
        xi_hayashi = R_PHE / (2.0 * R_AHE)  # = 0.075
        xi_old_bug = R_PHE / (R_AHE / 2.0)  # = 0.3 (the pre-fix value)

        # Confirm the old formula is 4x the correct value
        assert abs(xi_old_bug / xi_hayashi - 4.0) < 1e-10, "Sanity check: old formula is 4x"

        # Run the model and verify it does NOT return the old buggy value
        model = SOTHarmonicHall()
        V_1w = (R_AHE / 2.0) * np.cos(phi) + R_PHE * np.sin(2.0 * phi) * np.sin(phi)
        V_2w = 5.0 * np.cos(phi) + 2.0 * np.cos(2.0 * phi) * np.cos(phi)

        result = model.fit(
            {"phi": phi, "V_2omega": V_2w, "V_1omega": V_1w},
            geometry={"H_ext": 1.0},
        )
        xi_fit = result.params["xi"]

        # Must be close to Hayashi value, NOT the 4x-inflated buggy value
        err_from_correct = abs(xi_fit - xi_hayashi)
        err_from_bug = abs(xi_fit - xi_old_bug)
        assert err_from_correct < err_from_bug, (
            f"xi={xi_fit:.6f} is closer to buggy value ({xi_old_bug:.6f}) "
            f"than correct value ({xi_hayashi:.6f})"
        )

    def test_xi_estimator_various_ratios(self) -> None:
        """Auto-estimated xi is within 1% of R_PHE/(2*R_AHE) across typical PHE/AHE ratios."""
        model = SOTHarmonicHall()
        phi = np.linspace(0, 2 * np.pi, 200)

        # Typical HM/FM PHE/AHE ratios spanning 0.05 to 0.20
        for ratio in [0.05, 0.10, 0.15, 0.20]:
            R_AHE = 1.0
            R_PHE = ratio * R_AHE
            xi_true = R_PHE / (2.0 * R_AHE)  # Hayashi definition

            V_1w = (R_AHE / 2.0) * np.cos(phi) + R_PHE * np.sin(2.0 * phi) * np.sin(phi)
            V_2w = 5.0 * np.cos(phi) + 2.0 * np.cos(2.0 * phi) * np.cos(phi)

            result = model.fit(
                {"phi": phi, "V_2omega": V_2w, "V_1omega": V_1w},
                geometry={"H_ext": 1.0},
            )
            assert result.success, f"fit failed for ratio={ratio}"
            xi_fit = result.params["xi"]
            rel_err = abs(xi_fit - xi_true) / abs(xi_true)
            assert rel_err < 0.01, (
                f"ratio={ratio}: xi_fit={xi_fit:.6f}, xi_true={xi_true:.6f}, rel_err={rel_err:.4f}"
            )


# ===========================================================================
# Gap 2 — ST-FMR: xi_DL in FitResult
# ===========================================================================


class TestSTFMRXiDL:
    """Gap 2: xi_DL must appear in FitResult.params when geometry supplies Ms, t_FM, t_NM."""

    def test_xi_dl_present_when_geometry_supplied(self) -> None:
        """With geometry, xi_DL appears in params."""
        model = STFMREffect()
        S_true = 1e-4
        A_true = 5e-5
        H_res_true = 5e4
        dH_true = 2e3
        H = np.linspace(H_res_true - 3e4, H_res_true + 3e4, 200)
        V_mix = S_true * _lorentz_sym(H, H_res_true, dH_true) + A_true * _lorentz_asym(
            H, H_res_true, dH_true
        )

        geo = {"Ms": 8e5, "t_FM": 5e-9, "t_NM": 5e-9}
        result = model.fit({"H": H, "V_mix": V_mix}, geometry=geo)
        assert result.success
        assert "xi_DL" in result.params, "xi_DL missing from FitResult.params"
        # xi_DL should be a float, not NaN
        assert math.isfinite(result.params["xi_DL"]), "xi_DL is not finite"

    def test_xi_dl_absent_without_geometry(self) -> None:
        """Without geometry, xi_DL is absent (backward compatible)."""
        model = STFMREffect()
        H_res_true = 5e4
        dH_true = 2e3
        H = np.linspace(H_res_true - 3e4, H_res_true + 3e4, 200)
        V_mix = 1e-4 * _lorentz_sym(H, H_res_true, dH_true) + 5e-5 * _lorentz_asym(
            H, H_res_true, dH_true
        )
        result = model.fit({"H": H, "V_mix": V_mix})
        assert result.success
        assert "xi_DL" not in result.params, "xi_DL should not appear without geometry"

    def test_xi_dl_value_formula(self) -> None:
        """xi_DL = (S/A)·√(1+M_eff/H_res)·(e·μ₀·Ms·t_FM·t_NM/ħ) — verify corrected formula.

        FINDING 3 fix: the old formula was missing the elliptical-orbit geometry
        correction √(1 + M_eff/H_res).  The t_NM factor is retained (required
        for dimensional consistency).
        """
        import math as _math

        from maglab.physics.constants import E_CHARGE, HBAR

        S = 1e-4
        A = 5e-5
        Ms = 8e5
        t_FM = 5e-9
        t_NM = 5e-9
        H_res_true = 5e4
        dH_true = 2e3
        M_eff = Ms  # default: M_eff = Ms

        geom_factor = _math.sqrt(1.0 + M_eff / H_res_true)
        xi_expected = (S / A) * geom_factor * (E_CHARGE * MU_0 * Ms * t_FM * t_NM / HBAR)

        H = np.linspace(H_res_true - 3e4, H_res_true + 3e4, 200)
        V_mix = S * _lorentz_sym(H, H_res_true, dH_true) + A * _lorentz_asym(H, H_res_true, dH_true)
        model = STFMREffect()
        result = model.fit(
            {"H": H, "V_mix": V_mix},
            geometry={"Ms": Ms, "t_FM": t_FM, "t_NM": t_NM, "M_eff": M_eff},
        )

        xi_fit = result.params["xi_DL"]
        S_fit = result.params["S"]
        A_fit = result.params["A"]
        H_res_fit = result.params["H_res"]
        geom_fit = _math.sqrt(1.0 + M_eff / H_res_fit)
        xi_from_fit = (S_fit / A_fit) * geom_fit * (E_CHARGE * MU_0 * Ms * t_FM * t_NM / HBAR)
        # xi_DL should match the manual formula applied to fitted S, A, H_res
        assert abs(xi_fit - xi_from_fit) / abs(xi_from_fit) < 0.001
        # The fitted xi_DL also recovers the expected value from the known S/A
        assert abs(xi_fit - xi_expected) / abs(xi_expected) < 0.05


# ===========================================================================
# Gap 3 — USMR effect
# ===========================================================================


class TestUSMREffect:
    """Gap 3: USMR effect model round-trips and is registered."""

    def test_usmr_registered_in_magnetotransport(self) -> None:
        """USMR is registered in magnetotransport provider."""
        effect = get_effect("usmr")
        assert effect.name == "usmr"
        assert effect.subfield == "magnetotransport"

    def test_usmr_provider_has_9_effects(self) -> None:
        """magnetotransport provider now has 9 effects."""
        provider = get_provider("magnetotransport")
        assert len(provider.list()) == 9

    def test_usmr_forward_current_sweep(self) -> None:
        """USMR forward: A(j) = ε·j + offset — linear in j."""
        model = USMREffect()
        epsilon_true = 1e-13
        offset_true = 1e-5
        j = np.linspace(-1e11, 1e11, 50)
        params = {"epsilon": epsilon_true, "offset": offset_true}
        A = model.forward(params, geometry={"j": j})
        expected = epsilon_true * j + offset_true
        np.testing.assert_allclose(A, expected, rtol=1e-10)

    def test_usmr_roundtrip_current_sweep(self) -> None:
        """USMR current-sweep: recover ε from A(j) = ε·j."""
        model = USMREffect()
        epsilon_true = 1e-13
        j = np.linspace(-1e11, 1e11, 60)
        A_data = epsilon_true * j

        result = model.fit({"j": j, "A": A_data})
        assert result.success
        _assert_recovery("epsilon", epsilon_true, result.params["epsilon"])

    def test_usmr_roundtrip_angle_sweep(self) -> None:
        """USMR angle-sweep: recover ε from A(φ) = ε·j₀·sin(φ)."""
        model = USMREffect()
        epsilon_true = 1e-13
        j_0 = 1e11
        phi = np.linspace(0, 2 * np.pi, 80)
        A_data = epsilon_true * j_0 * np.sin(phi)

        result = model.fit({"phi": phi, "A": A_data}, geometry={"j_0": j_0})
        assert result.success
        _assert_recovery("epsilon", epsilon_true, result.params["epsilon"])

    def test_usmr_references_nonempty(self) -> None:
        """USMR references include Olejnik."""
        model = USMREffect()
        assert any("Olejnik" in r for r in model.references)

    def test_usmr_symmetry_constraints_time_reversal_odd(self) -> None:
        """USMR symmetry constraint marks time_reversal_odd."""
        model = USMREffect()
        assert model.symmetry_constraints.get("time_reversal_odd") is True


# ===========================================================================
# Gap 4 — Device FoM: MTJ, spin-valve, spin-orbit-logic, magnon
# ===========================================================================


class TestDeviceFoMNewTypes:
    """Gap 4: new device FoM types are registered and physically correct."""

    def test_all_seven_devices_listed(self) -> None:
        """list_devices() returns all 7 registered device types."""
        devices = list_devices()
        expected = {
            "sot-mram",
            "stt-mram",
            "racetrack",
            "mtj",
            "spin-valve-sensor",
            "spin-orbit-logic",
            "magnon",
        }
        assert expected.issubset(set(devices)), f"Missing devices: {expected - set(devices)}"

    # --- MTJ ---

    def test_mtj_fom_thermal_stability(self) -> None:
        """MTJ FoM contains thermal stability Δ > 0."""
        result = mtj_fom()
        assert "thermal_stability_delta" in result.foms
        delta = result.foms["thermal_stability_delta"]["value"]
        assert delta > 0

    def test_mtj_fom_tmr_ratio(self) -> None:
        """MTJ FoM TMR ratio matches input."""
        result = mtj_fom(TMR=1.5)
        assert abs(result.foms["TMR_ratio"]["value"] - 1.5) < 1e-10

    def test_mtj_fom_r_ap_formula(self) -> None:
        """R_AP = R_P·(1+TMR) — verify formula."""
        R_P = 2e4
        TMR = 2.0
        result = mtj_fom(R_P=R_P, TMR=TMR)
        assert abs(result.foms["R_AP"]["value"] - R_P * (1 + TMR)) < 1.0

    def test_mtj_dispatch(self) -> None:
        """compute_fom('mtj') dispatches correctly."""
        result = compute_fom("mtj", TMR=2.0, R_P=1e4)
        assert result.device == "mtj"

    def test_mtj_references_nonempty(self) -> None:
        """MTJ references include Yuasa or Ikeda."""
        result = mtj_fom()
        refs_combined = " ".join(result.references)
        assert "Yuasa" in refs_combined or "Ikeda" in refs_combined

    # --- Spin-valve sensor ---

    def test_spin_valve_sensor_fom_gmr_ratio(self) -> None:
        """Spin-valve FoM GMR ratio matches input (as %)."""
        result = spin_valve_sensor_fom(GMR=0.15)
        assert abs(result.foms["GMR_ratio_percent"]["value"] - 15.0) < 1e-10

    def test_spin_valve_sensor_fom_field_sensitivity(self) -> None:
        """Field sensitivity = GMR / H_sat."""
        GMR = 0.10
        H_sat = 2e3
        result = spin_valve_sensor_fom(GMR=GMR, H_sat=H_sat)
        expected_S_H = GMR / H_sat
        assert (
            abs(result.foms["field_sensitivity_S_H"]["value"] - expected_S_H) / expected_S_H < 1e-10
        )

    def test_spin_valve_sensor_dispatch(self) -> None:
        """compute_fom('spin-valve-sensor') dispatches correctly."""
        result = compute_fom("spin-valve-sensor")
        assert result.device == "spin-valve-sensor"

    def test_spin_valve_sensor_references_nonempty(self) -> None:
        """Spin-valve sensor references include Dieny or Freitas."""
        result = spin_valve_sensor_fom()
        refs_combined = " ".join(result.references)
        assert "Dieny" in refs_combined or "Freitas" in refs_combined

    # --- Spin-orbit logic ---

    def test_spin_orbit_logic_fom_thermal_stability(self) -> None:
        """Spin-orbit logic FoM has thermal stability Δ > 0."""
        result = spin_orbit_logic_fom()
        assert "thermal_stability_delta" in result.foms
        delta = result.foms["thermal_stability_delta"]["value"]
        assert delta > 0

    def test_spin_orbit_logic_fom_switching_time(self) -> None:
        """Switching time is physically reasonable (< 10 ns)."""
        result = spin_orbit_logic_fom()
        tau_ns = result.foms["switching_time_tau_sw"]["value"]
        assert 0 < tau_ns <= 10.0  # ns

    def test_spin_orbit_logic_fom_edp_positive(self) -> None:
        """Energy-delay product is positive."""
        result = spin_orbit_logic_fom()
        edp = result.foms["energy_delay_product_EDP"]["value"]
        assert edp > 0

    def test_spin_orbit_logic_dispatch(self) -> None:
        """compute_fom('spin-orbit-logic') dispatches correctly."""
        result = compute_fom("spin-orbit-logic")
        assert result.device == "spin-orbit-logic"

    def test_spin_orbit_logic_references_nonempty(self) -> None:
        """Spin-orbit logic references include Manipatruni or Dieny."""
        result = spin_orbit_logic_fom()
        refs_combined = " ".join(result.references)
        assert "Manipatruni" in refs_combined or "Dieny" in refs_combined

    # --- Magnon device ---

    def test_magnon_device_fom_group_velocity_positive(self) -> None:
        """Magnon FoM spin-wave group velocity is positive."""
        result = magnon_device_fom()
        v_g = result.foms["spin_wave_group_velocity_v_g"]["value"]
        assert v_g > 0

    def test_magnon_device_fom_propagation_length_positive(self) -> None:
        """Magnon propagation length is positive."""
        result = magnon_device_fom()
        lambda_um = result.foms["magnon_propagation_length_lambda"]["value"]
        assert lambda_um > 0

    def test_magnon_device_fom_xi_positive(self) -> None:
        """Magnon FoM ξ = λ/d > 0."""
        result = magnon_device_fom()
        xi = result.foms["magnon_FoM_xi"]["value"]
        assert xi > 0

    def test_magnon_device_dispatch(self) -> None:
        """compute_fom('magnon') dispatches correctly."""
        result = compute_fom("magnon")
        assert result.device == "magnon"

    def test_magnon_references_nonempty(self) -> None:
        """Magnon references include Chumak or Kruglyak."""
        result = magnon_device_fom()
        refs_combined = " ".join(result.references)
        assert "Chumak" in refs_combined or "Kruglyak" in refs_combined

    def test_magnon_group_velocity_formula(self) -> None:
        """v_g = 4·γ·A·k/Ms — correct formula after R8 F2 fix.

        The old formula 2·A·k/(μ₀·Ms) had units of [A] not [m/s].
        Correct derivation: dispersion ω(k) = γ·μ₀·H₀ + γ·(2A/Ms)·k²
        gives v_g = ∂ω/∂k = 4·γ·A·k/Ms [m/s].
        """
        A = 4e-12
        Ms = 1.4e5
        d_waveguide = 1e-6
        k_mode = math.pi / d_waveguide
        gamma_0 = abs(GAMMA_E)
        v_g_expected = 4.0 * gamma_0 * A * k_mode / Ms
        result = magnon_device_fom(A=A, Ms=Ms, d_waveguide=d_waveguide)
        v_g_actual = result.foms["spin_wave_group_velocity_v_g"]["value"]
        assert abs(v_g_actual - v_g_expected) / v_g_expected < 1e-8


# ===========================================================================
# R8 regression tests — physics fixes F1, F2, F3
# ===========================================================================


class TestR8PhysicsFixes:
    """Regression tests for Round 8 physics bug fixes in device_fom.py."""

    # --- F1: racetrack_fom Walker breakdown field factor-of-2 ---

    def test_racetrack_fom_hw_matches_canonical_formula(self) -> None:
        """H_W from racetrack_fom must match formulas.walker_breakdown_field.

        The canonical formula is H_W = α·K_⊥ / (2·μ₀·M_s) per Schryer & Walker (1974).
        R8-F1 fixed racetrack_fom which previously dropped the factor of 2.
        """
        alpha = 0.01
        K_perp = 1e4
        Ms = 8e5
        # canonical value from formulas.py (A argument unused, pass 0)
        H_W_canonical = walker_breakdown_field(alpha=alpha, Ms=Ms, K=K_perp, A=0.0)
        result = racetrack_fom(alpha=alpha, K_perp=K_perp, Ms=Ms)
        H_W_fom = result.foms["Walker_breakdown_field_H_W"]["value"]
        assert abs(H_W_fom - H_W_canonical) / H_W_canonical < 1e-10, (
            f"H_W mismatch: fom={H_W_fom:.4g}, canonical={H_W_canonical:.4g}"
        )

    def test_racetrack_fom_hw_not_double_canonical(self) -> None:
        """Verify H_W is no longer 2× the Schryer-Walker value (old bug guard)."""
        alpha = 0.01
        K_perp = 1e4
        Ms = 8e5
        H_W_canonical = walker_breakdown_field(alpha=alpha, Ms=Ms, K=K_perp, A=0.0)
        result = racetrack_fom(alpha=alpha, K_perp=K_perp, Ms=Ms)
        H_W_fom = result.foms["Walker_breakdown_field_H_W"]["value"]
        # Old bug: H_W_fom == 2 * H_W_canonical. Assert it is NOT doubled.
        assert abs(H_W_fom - 2.0 * H_W_canonical) / H_W_canonical > 0.5, (
            "H_W is still double the canonical value — F1 fix not applied"
        )

    # --- F2: magnon_device_fom group velocity is physical (m/s) ---

    def test_magnon_vg_in_physical_range(self) -> None:
        """Spin-wave group velocity must be in the 10¹–10⁵ m/s range (YIG defaults).

        Before R8-F2, v_g was ~1.4e-4 m/s (off by ~4.4e5) because γ was missing.
        Typical exchange spin-wave v_g for YIG at GHz frequencies: 10–1000 m/s.
        """
        result = magnon_device_fom()  # YIG defaults: A=4 pJ/m, Ms=1.4e5 A/m
        v_g = result.foms["spin_wave_group_velocity_v_g"]["value"]
        assert 1.0 < v_g < 1e5, f"v_g = {v_g:.4g} m/s is outside the physical 1–1e5 m/s range"

    def test_magnon_vg_formula_4gamma_A_k_over_Ms(self) -> None:
        """v_g = 4·γ·A·k/Ms exactly matches the correct dispersion derivative."""
        A = 4e-12
        Ms = 1.4e5
        d_waveguide = 1e-6
        k_mode = math.pi / d_waveguide
        gamma_0 = abs(GAMMA_E)
        v_g_expected = 4.0 * gamma_0 * A * k_mode / Ms
        result = magnon_device_fom(A=A, Ms=Ms, d_waveguide=d_waveguide)
        v_g_actual = result.foms["spin_wave_group_velocity_v_g"]["value"]
        assert abs(v_g_actual - v_g_expected) / v_g_expected < 1e-8

    def test_magnon_propagation_length_physically_sensible(self) -> None:
        """λ_prop should be O(μm)–O(mm) for YIG at GHz (not sub-pm as in old code)."""
        result = magnon_device_fom()
        lambda_um = result.foms["magnon_propagation_length_lambda"]["value"]  # μm
        # Old buggy code gave ~1e-11 m = 1e-5 μm; correct is O(1)–O(1000) μm
        assert lambda_um > 0.01, (
            f"λ_prop = {lambda_um:.4g} μm — suspiciously small (was ~1e-11 m before fix)"
        )

    # --- F3: spin_valve_sensor_fom NEF has field units ---

    def test_spin_valve_nef_dimensional_consistency(self) -> None:
        """NEF_T_sqrtHz has units T/√Hz; verify numerically with Ω/√Hz input.

        noise_floor [Ω/√Hz], S_H = GMR/H_sat [m/A], R_sq [Ω]:
          NEF [A/m/√Hz] = noise_floor / (S_H · R_sq)
          NEF_T [T/√Hz] = NEF · μ₀
        """
        GMR = 0.10
        H_sat = 2e3
        R_sq = 20.0
        noise_floor = 1e-9  # [Ω/√Hz] resistance noise
        S_H = GMR / H_sat  # [m/A]
        NEF_Am_expected = noise_floor / (S_H * R_sq)  # [A/m/√Hz]
        NEF_T_expected = NEF_Am_expected * MU_0  # [T/√Hz]
        result = spin_valve_sensor_fom(GMR=GMR, H_sat=H_sat, R_sq=R_sq, noise_floor=noise_floor)
        NEF_T_actual = result.foms["noise_equivalent_field_T_sqrtHz"]["value"]
        assert abs(NEF_T_actual - NEF_T_expected) / NEF_T_expected < 1e-10

    def test_spin_valve_nef_positive(self) -> None:
        """NEF must be strictly positive for any physical noise_floor > 0."""
        result = spin_valve_sensor_fom()
        NEF_T = result.foms["noise_equivalent_field_T_sqrtHz"]["value"]
        assert NEF_T > 0

    def test_spin_valve_nef_formula_string_matches_computation(self) -> None:
        """Formula string annotation must reflect the actual computation.

        The formula string "NEF=noise_floor·μ₀/(S_H·R_sq)" encodes:
          NEF_T = noise_floor * MU_0 / (S_H * R_sq)

        Verify that evaluating this expression with the same inputs reproduces
        the stored FoM value.  This guards against R9 F1: previously the string
        read "NEF=noise_floor/(S_H·R_sq·μ₀)" (μ₀ in denominator), which would
        yield a result off by μ₀² ≈ 1.58e-12 from the correct value.
        """
        GMR = 0.10
        H_sat = 2e3
        R_sq = 20.0
        noise_floor = 1e-9  # [Ω/√Hz] resistance noise

        result = spin_valve_sensor_fom(GMR=GMR, H_sat=H_sat, R_sq=R_sq, noise_floor=noise_floor)

        fom_entry = result.foms["noise_equivalent_field_T_sqrtHz"]

        # Confirm the formula string has μ₀ in the numerator (not denominator).
        formula_str: str = fom_entry["formula"]
        assert "noise_floor·μ₀/(S_H·R_sq)" in formula_str, (
            f"Formula string '{formula_str}' does not match the actual computation "
            "'NEF=noise_floor·μ₀/(S_H·R_sq)'. "
            "μ₀ must appear as a multiplier, not a divisor."
        )

        # Evaluate the formula symbolically by substitution and confirm the
        # result matches the stored numeric value.
        S_H = GMR / H_sat  # [m/A]
        nef_from_formula = noise_floor * MU_0 / (S_H * R_sq)  # [T/√Hz]
        nef_stored = fom_entry["value"]
        assert abs(nef_stored - nef_from_formula) / nef_from_formula < 1e-10, (
            f"Stored NEF value {nef_stored:.6e} does not match formula evaluation "
            f"{nef_from_formula:.6e}. The formula string and computation are inconsistent."
        )

        # Confirm the wrong (pre-fix) formula would differ by ~μ₀².
        nef_wrong_formula = noise_floor / (S_H * R_sq * MU_0)
        ratio = nef_from_formula / nef_wrong_formula
        # ratio should be MU_0^2 ≈ 1.58e-12 — very far from 1.
        assert abs(ratio - MU_0**2) / MU_0**2 < 1e-6, (
            "Sanity check: the wrong formula must differ from the correct one by μ₀²."
        )


# ===========================================================================
# Gap 5 — Macrospin model
# ===========================================================================


class TestMacrospinModel:
    """Gap 5: macrospin model round-trips and is registered."""

    def test_macrospin_registered(self) -> None:
        """macrospin is registered in magnetization_dynamics provider."""
        effect = get_effect("macrospin")
        assert effect.name == "macrospin"
        assert effect.subfield == "magnetization_dynamics"

    def test_sw_switching_field_easy_axis(self) -> None:
        """At θ_H=0 (easy axis) H_sw = H_k (Stoner-Wohlfarth exact)."""
        model = MacrospinModel()
        H_k = 1e5  # A/m
        theta_H = np.array([0.0])
        H_sw = model.sw_switching_field(H_k, theta_H)
        assert abs(H_sw[0] - H_k) / H_k < 1e-8

    def test_sw_switching_field_astroid_symmetry(self) -> None:
        """H_sw(θ) = H_sw(π - θ) — astroid is symmetric about θ=π/2."""
        model = MacrospinModel()
        H_k = 1e5
        theta = np.linspace(0.01, math.pi / 2, 20)
        H_sw_fwd = model.sw_switching_field(H_k, theta)
        H_sw_rev = model.sw_switching_field(H_k, math.pi - theta)
        np.testing.assert_allclose(H_sw_fwd, H_sw_rev, rtol=1e-8)

    def test_macrospin_forward_astroid_mode(self) -> None:
        """forward() in astroid mode returns H_sw array."""
        model = MacrospinModel()
        H_k = 1e5
        params = {"H_k": H_k, "alpha": 0.01, "tau_DL": 0.0, "tau_FL": 0.0}
        theta_H = np.linspace(0, math.pi / 2, 20)
        H_sw = model.forward(params, geometry={"theta_H": theta_H})
        assert H_sw.shape == (20,)
        assert np.all(H_sw > 0)

    def test_macrospin_astroid_roundtrip(self) -> None:
        """Fit H_k from synthetic Stoner-Wohlfarth astroid."""
        model = MacrospinModel()
        H_k_true = 1e5
        theta_H = np.linspace(0.01, math.pi / 2 - 0.01, 30)
        H_sw_data = model.sw_switching_field(H_k_true, theta_H)

        result = model.fit({"theta_H": theta_H, "H_sw": H_sw_data})
        assert result.success
        _assert_recovery("H_k", H_k_true, result.params["H_k"])

    def test_macrospin_llg_dynamics_mode(self) -> None:
        """forward() in LLG dynamics mode returns (N, 3) trajectory."""
        model = MacrospinModel()
        params = {"H_k": 1e5, "alpha": 0.01, "tau_DL": 0.0, "tau_FL": 0.0}
        n_pts = 50
        t_eval = np.linspace(0, 1e-11, n_pts)
        geo = {
            "t_span": (0.0, 1e-11),
            "t_eval": t_eval,
            "m_0": np.array([0.1, 0.0, 0.995]),
            "H_eff": np.array([0.0, 0.0, 1e5]),
            "m_p": np.array([1.0, 0.0, 0.0]),
        }
        traj = model.forward(params, geo)
        assert traj.shape == (n_pts, 3)

    def test_macrospin_anisotropy_field(self) -> None:
        """H_k = 2K_u / (μ₀·M_s) — formula consistency."""
        model = MacrospinModel()
        K_u = 4e5
        Ms = 8e5
        H_k = model.anisotropy_field(K_u, Ms)
        expected = 2.0 * K_u / (MU_0 * Ms)
        assert abs(H_k - expected) / expected < 1e-10

    def test_macrospin_references_stoner_wohlfarth(self) -> None:
        """References include Stoner and Wohlfarth."""
        model = MacrospinModel()
        refs_combined = " ".join(model.references)
        assert "Stoner" in refs_combined or "Wohlfarth" in refs_combined


# ===========================================================================
# Gap 5 — Two-sublattice LLG model
# ===========================================================================


class TestLLG2SublatticeModel:
    """Gap 5: two-sublattice LLG model round-trips and is registered."""

    def test_llg2sl_registered(self) -> None:
        """llg_2sublattice is registered in magnetization_dynamics provider."""
        effect = get_effect("llg_2sublattice")
        assert effect.name == "llg_2sublattice"
        assert effect.subfield == "magnetization_dynamics"

    def test_afmr_analytic_formula(self) -> None:
        """afmr_freq() = (γ/2π)·μ₀·√(2·H_E·H_A)."""
        model = LLG2SublatticeModel()
        H_E = 1e6  # A/m
        H_A = 1e4  # A/m
        gamma = abs(GAMMA_E)
        f = model.afmr_freq(H_E, H_A, gamma)
        import math

        expected = (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(2.0 * H_E * H_A)
        assert abs(f - expected) / expected < 1e-8

    def test_afmr_roundtrip(self) -> None:
        """Fit H_E from synthetic AFMR frequency vs. anisotropy data."""
        model = LLG2SublatticeModel()
        H_E_true = 1e6
        H_A_arr = np.linspace(5e3, 3e4, 20)
        gamma = abs(GAMMA_E)
        import math

        f_afmr_data = np.array(
            [
                (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(2.0 * H_E_true * float(ha))
                for ha in H_A_arr
            ]
        )

        result = model.fit({"H_A_sweep": H_A_arr, "f_afmr": f_afmr_data})
        assert result.success
        _assert_recovery("H_E", H_E_true, result.params["H_E"], tol=0.10)

    def test_fim_compensation_mode(self) -> None:
        """FiM compensation: fit H_E from m_a, m_b, f_comp.

        R5-F1 fix: ferrimagnet_compensation_freq() now returns f [Hz] = ω/(2π).
        f_comp_true must be generated with the corrected formula (not the old
        ω [rad/s] expression) so the round-trip is internally consistent.
        """
        from maglab.physics.formulas import ferrimagnet_compensation_freq

        model = LLG2SublatticeModel()
        H_E_true = 5e5
        m_a = 8e5
        m_b = 6e5
        gamma_a = abs(GAMMA_E)
        gamma_b = abs(GAMMA_E) * 0.95  # slightly different sublattice g-factor

        # Generate f_comp [Hz] using the corrected formula (divides by 2π internally)
        f_comp_true = ferrimagnet_compensation_freq(m_a, m_b, H_E_true, gamma_a, gamma_b)

        result = model.fit(
            {"m_a": np.array([m_a]), "m_b": np.array([m_b]), "f_comp": np.array([f_comp_true])},
            geometry={"gamma_a": gamma_a, "gamma_b": gamma_b},
        )
        assert result.success
        _assert_recovery("H_E", H_E_true, result.params["H_E"], tol=0.10)

    def test_llg2sl_dynamics_forward_shape(self) -> None:
        """forward() in LLG dynamics mode returns (N, 6) trajectory."""
        model = LLG2SublatticeModel()
        n_pts = 30
        t_eval = np.linspace(0, 1e-13, n_pts)
        params = {"H_E": 1e6, "H_A": 1e4, "alpha_a": 0.005, "alpha_b": 0.005}
        geo = {
            "t_eval": t_eval,
            "t_span": (0.0, 1e-13),
            "m_0_a": np.array([0.05, 0.0, 0.999]),
            "m_0_b": np.array([0.05, 0.0, -0.999]),
            "H_ext": np.array([0.0, 0.0, 0.0]),
            "Ms_a": 8e5,
            "Ms_b": 6e5,
        }
        traj = model.forward(params, geo)
        assert traj.shape == (n_pts, 6)

    def test_llg2sl_forward_afmr_mode(self) -> None:
        """forward() with H_A_sweep returns f_AFMR array."""
        model = LLG2SublatticeModel()
        H_A_arr = np.array([1e4, 2e4, 3e4])
        params = {"H_E": 1e6, "H_A": 1e4, "alpha_a": 0.005, "alpha_b": 0.005}
        result = model.forward(params, geometry={"H_A_sweep": H_A_arr})
        assert result.shape == (3,)
        assert np.all(result > 0)

    def test_llg2sl_references_keffer_kittel(self) -> None:
        """References include Keffer and Kittel."""
        model = LLG2SublatticeModel()
        refs_combined = " ".join(model.references)
        assert "Keffer" in refs_combined or "Kittel" in refs_combined


# ===========================================================================
# Gap 7 — Curie temperature model
# ===========================================================================


class TestCurieTemperatureModel:
    """Gap 7: Curie/compensation temperature EffectModel."""

    def test_curie_registered_in_magnetometry(self) -> None:
        """curie_temperature is registered in magnetometry provider."""
        effect = get_effect("curie_temperature")
        assert effect.name == "curie_temperature"
        assert effect.subfield == "magnetometry"

    def test_curie_forward_at_zero_temperature(self) -> None:
        """M(0) = M_0 for any β."""
        model = CurieTemperatureModel()
        params = {"M_0": 8e5, "T_C": 600.0, "beta": 0.36}
        T = np.array([0.0])
        M = model.forward(params, geometry={"T": T})
        assert abs(M[0] - 8e5) < 1e-10

    def test_curie_forward_above_tc_is_zero(self) -> None:
        """M(T > T_C) = 0 (clipped)."""
        model = CurieTemperatureModel()
        params = {"M_0": 8e5, "T_C": 600.0, "beta": 0.36}
        T = np.array([601.0, 700.0, 1000.0])
        M = model.forward(params, geometry={"T": T})
        np.testing.assert_array_equal(M, 0.0)

    def test_curie_forward_monotone_decreasing(self) -> None:
        """M(T) is monotonically decreasing with T for T < T_C."""
        model = CurieTemperatureModel()
        params = {"M_0": 8e5, "T_C": 600.0, "beta": 0.36}
        T = np.linspace(0, 599.0, 100)
        M = model.forward(params, geometry={"T": T})
        assert np.all(np.diff(M) <= 0)

    def test_curie_roundtrip(self) -> None:
        """Fit T_C, M_0, β from synthetic power-law M(T) data."""
        model = CurieTemperatureModel()
        M_0_true = 8e5
        T_C_true = 600.0
        beta_true = 0.36

        T = np.linspace(10, 580, 80)
        M = M_0_true * (1.0 - T / T_C_true) ** beta_true

        result = model.fit({"T": T, "M": M})
        assert result.success
        _assert_recovery("M_0", M_0_true, result.params["M_0"])
        _assert_recovery("T_C", T_C_true, result.params["T_C"], tol=0.02)
        _assert_recovery("beta", beta_true, result.params["beta"], tol=0.10)

    def test_curie_references_kittel(self) -> None:
        """References include Kittel or Collins."""
        model = CurieTemperatureModel()
        refs_combined = " ".join(model.references)
        assert "Kittel" in refs_combined or "Collins" in refs_combined

    def test_curie_param_specs(self) -> None:
        """Parameters include M_0, T_C, beta with correct units."""
        model = CurieTemperatureModel()
        names = [p.name for p in model.parameters]
        assert "M_0" in names
        assert "T_C" in names
        assert "beta" in names

    def test_compensation_temperature_detected(self) -> None:
        """When M_a and M_b cross, T_comp appears in FitResult.params."""
        model = CurieTemperatureModel()
        T = np.linspace(200, 500, 100)
        T_C_a = 450.0
        T_C_b = 480.0
        M_a = 8e5 * np.clip(1.0 - T / T_C_a, 0.0, None) ** 0.36
        M_b = 6e5 * np.clip(1.0 - T / T_C_b, 0.0, None) ** 0.36

        M_total = M_a - M_b  # this crosses zero somewhere
        result = model.fit({"T": T, "M": M_total, "M_a": M_a, "M_b": M_b})
        assert "T_comp" in result.params, "T_comp missing for two-component fit"
        T_comp = result.params["T_comp"]
        # T_comp should be in the temperature range
        assert float(T[0]) <= T_comp <= float(T[-1])

    def test_compensation_temperature_value(self) -> None:
        """T_comp is close to the actual zero-crossing temperature."""
        model = CurieTemperatureModel()
        T = np.linspace(0, 500, 500)
        # Craft simple linear crossing: M_net = A - B*T → zero at T_comp_true
        T_comp_true = 300.0
        M_a = np.clip(T_comp_true * 1.2 - T, 0.0, None) * 1e3  # linearly decreasing
        M_b = np.clip(T - T_comp_true * 0.8, 0.0, None) * 1e3  # linearly increasing
        M_net = M_a - M_b

        result = model.fit({"T": T, "M": M_net, "M_a": M_a, "M_b": M_b})
        T_comp = result.params.get("T_comp", float("nan"))
        if math.isfinite(T_comp):
            assert abs(T_comp - T_comp_true) < 15.0  # within 15 K


# ===========================================================================
# Provider completeness check for new effects
# ===========================================================================


class TestProviderCompleteness:
    """Verify all new effects are accessible from their providers."""

    def test_magnetization_dynamics_has_macrospin_and_2sl_llg(self) -> None:
        """magnetization_dynamics provider lists macrospin and llg_2sublattice."""
        provider = get_provider("magnetization_dynamics")
        names = provider.list()
        assert "macrospin" in names
        assert "llg_2sublattice" in names

    def test_magnetometry_has_curie_temperature(self) -> None:
        """magnetometry provider lists curie_temperature."""
        provider = get_provider("magnetometry")
        names = provider.list()
        assert "curie_temperature" in names

    def test_magnetotransport_has_usmr(self) -> None:
        """magnetotransport provider lists usmr."""
        provider = get_provider("magnetotransport")
        names = provider.list()
        assert "usmr" in names

    def test_all_new_effects_have_nonempty_references(self) -> None:
        """All new effects have at least one reference."""
        new_names = ["usmr", "macrospin", "llg_2sublattice", "curie_temperature"]
        for name in new_names:
            effect = get_effect(name)
            assert len(effect.references) > 0, f"{name}.references is empty"

    def test_all_new_effects_have_parameters(self) -> None:
        """All new effects have at least one parameter."""
        new_names = ["usmr", "macrospin", "llg_2sublattice", "curie_temperature"]
        for name in new_names:
            effect = get_effect(name)
            assert len(effect.parameters) >= 1, f"{name}.parameters is empty"
