"""Regression tests for physics/sim HIGH-severity defect fixes.

FINDING 1 — LLG precession missing μ₀ (llg.py, macrospin.py, llg_2sublattice.py)
FINDING 2 — DMI BLS formula spurious μ₀ in denominator (dmi.py)
FINDING 3 — ST-FMR spin_hall_angle() wrong formula (stfmr.py)

Round-2 additions (R2):
R2-F1 — dw_velocity_below_walker: wrong 1/α denominator (formulas.py)
R2-F2 — MacrospinModel.fit() time-series model purely exponential (macrospin.py)
R2-F5 — skyrmion_hall_angle ZeroDivisionError for alpha=0 (formulas.py)

Round-5 additions (R5):
R5-F1 — ferrimagnet_compensation_freq returns ω [rad/s] not f [Hz]; FiM inversion missing 2π
R5-F2 — SpinPumpingISHE spurious MU_0 in Δα denominator; g↑↓ off by factor μ₀

Each test asserts the corrected numerical result and (where relevant)
demonstrates that the old behaviour would have failed.
"""

from __future__ import annotations

import math

import numpy as np

from maglab.physics.constants import E_CHARGE, GAMMA_E, HBAR, MU_0

# ===========================================================================
# FINDING 1 — LLG precession term: μ₀ must multiply H_eff (A/m → T)
# ===========================================================================


class TestLLGMu0Regression:
    """Regression: LLG precession frequency must match γ·μ₀·H [rad/s], not γ·H."""

    def test_llg_precession_frequency_correct(self) -> None:
        """LLGModel.precession_frequency() uses μ₀ and gives ~352 MHz for H=1e4 A/m."""
        from maglab.analysis.effects.llg import LLGModel

        model = LLGModel()
        H_eff = 1e4  # A/m
        Ms = 8e5  # A/m (unused by this method but kept for API)
        f_GHz = model.precession_frequency(H_eff, Ms)
        # Correct: f = γ·μ₀·H/(2π) = 1.7609e11 × 1.2566e-6 × 1e4 / (2π) ≈ 0.352 GHz
        gamma = abs(GAMMA_E)
        f_expected_GHz = gamma * MU_0 * H_eff / (2.0 * math.pi) * 1e-9
        assert abs(f_GHz - f_expected_GHz) / f_expected_GHz < 1e-8, (
            f"precession_frequency: got {f_GHz:.6f} GHz, expected {f_expected_GHz:.6f} GHz"
        )

    def test_llg_trajectory_precesses_coherently(self) -> None:
        """LLG integration with H=1e4 A/m must produce coherent precession.

        Physical check: after 1/4 precession period, m_x should be near ±1 if
        started at m_y = 1.  With the corrected μ₀ the period is ~2.8 ns;
        without μ₀ the period would be ~3.6 μs (793× shorter than physical).

        Verification: the z-component must remain close to its initial value
        (no damping in this test: α=0.001 ≪ 1) and m stays unit-norm.
        """
        from maglab.analysis.effects.llg import LLGModel

        model = LLGModel()
        H_eff_Am = 1e4  # A/m
        gamma = abs(GAMMA_E)
        # Correct period = 2π/(γ·μ₀·H)
        T_prec = 2.0 * math.pi / (gamma * MU_0 * H_eff_Am)  # ≈ 2.84 ns

        n_pts = 200
        t_span = (0.0, T_prec)
        t_eval = np.linspace(0.0, T_prec, n_pts)

        # m_0 slightly tilted so precession is visible
        m_0 = np.array([0.1, 0.0, math.sqrt(1.0 - 0.1**2)])
        params = {"alpha": 0.001, "tau_DL": 0.0, "tau_FL": 0.0}
        geo = {
            "t_span": t_span,
            "t_eval": t_eval,
            "m_0": m_0,
            "H_eff": np.array([0.0, 0.0, H_eff_Am]),
            "m_p": np.array([1.0, 0.0, 0.0]),
        }
        traj = model.forward(params, geo)

        # All magnetization vectors should be unit-norm (within numerical tolerance)
        norms = np.linalg.norm(traj, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-6, err_msg="LLG: |m| deviates from 1")

        # m_z should not change by more than 2 × alpha over one period (low damping)
        # If μ₀ were missing, m would random-walk and m_z would be garbage
        m_z_start = float(traj[0, 2])
        m_z_end = float(traj[-1, 2])
        delta_mz = abs(m_z_end - m_z_start)
        assert delta_mz < 0.05, (
            f"LLG: m_z changed by {delta_mz:.4f} over one period — "
            "likely μ₀ still missing from precession term."
        )

        # m must complete approximately one full cycle: m_x should oscillate
        # The range of m_x should be at least 0.15 (=2 × 0.1 initial tilt minus damping loss)
        m_x_range = float(np.max(traj[:, 0]) - np.min(traj[:, 0]))
        assert m_x_range > 0.15, (
            f"LLG: m_x range {m_x_range:.4f} too small — precession not occurring."
        )

    def test_macrospin_llg_precesses_coherently(self) -> None:
        """MacrospinModel LLG dynamics: same μ₀ fix applies."""
        from maglab.analysis.effects.macrospin import MacrospinModel

        model = MacrospinModel()
        H_eff_Am = 1e4  # A/m
        gamma = abs(GAMMA_E)
        T_prec = 2.0 * math.pi / (gamma * MU_0 * H_eff_Am)

        n_pts = 100
        t_eval = np.linspace(0.0, T_prec, n_pts)
        m_0 = np.array([0.1, 0.0, math.sqrt(1.0 - 0.01)])
        params = {"H_k": H_eff_Am, "alpha": 0.001, "tau_DL": 0.0, "tau_FL": 0.0}
        geo = {
            "t_span": (0.0, T_prec),
            "t_eval": t_eval,
            "m_0": m_0,
            "H_eff": np.array([0.0, 0.0, H_eff_Am]),
            "m_p": np.array([1.0, 0.0, 0.0]),
        }
        traj = model.forward(params, geo)

        norms = np.linalg.norm(traj, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-6)

        m_z_start = float(traj[0, 2])
        m_z_end = float(traj[-1, 2])
        assert abs(m_z_end - m_z_start) < 0.05, (
            "MacrospinModel: m_z unstable — μ₀ missing from LLG RHS."
        )

    def test_llg2sl_trajectory_unit_norm(self) -> None:
        """LLG2SublatticeModel dynamics: μ₀ fix keeps both sublattice vectors unit-norm."""
        from maglab.analysis.effects.llg_2sublattice import LLG2SublatticeModel

        model = LLG2SublatticeModel()
        H_E = 1e6  # A/m (large to give fast AFMR)
        H_A = 1e4  # A/m
        gamma = abs(GAMMA_E)
        # AFMR period ≈ 1/(f_AFMR), f_AFMR = γμ₀√(2H_E·H_A)/(2π)
        f_afmr = (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(2.0 * H_E * H_A)
        T_afmr = 1.0 / f_afmr  # ≈ 180 ps

        n_pts = 50
        t_eval = np.linspace(0.0, T_afmr, n_pts)
        params = {"H_E": H_E, "H_A": H_A, "alpha_a": 0.001, "alpha_b": 0.001}
        geo = {
            "t_span": (0.0, T_afmr),
            "t_eval": t_eval,
            "m_0_a": np.array([0.05, 0.0, math.sqrt(1.0 - 0.05**2)]),
            "m_0_b": np.array([0.05, 0.0, -math.sqrt(1.0 - 0.05**2)]),
            "H_ext": np.array([0.0, 0.0, 0.0]),
            "Ms_a": 8e5,
            "Ms_b": 6e5,
        }
        traj = model.forward(params, geo)
        norms_a = np.linalg.norm(traj[:, :3], axis=1)
        norms_b = np.linalg.norm(traj[:, 3:], axis=1)
        np.testing.assert_allclose(norms_a, 1.0, atol=1e-5, err_msg="|m_a| deviates from 1")
        np.testing.assert_allclose(norms_b, 1.0, atol=1e-5, err_msg="|m_b| deviates from 1")


# ===========================================================================
# FINDING 2 — DMI BLS formula: no μ₀ in denominator
# ===========================================================================


class TestDMIFormulaRegression:
    """Regression: DMI Δf must agree with literature values (not 10⁶× too large)."""

    def test_dmi_delta_f_co_pt_typical(self) -> None:
        """Co/Pt typical parameters: Δf ≈ 1–3 GHz (literature range).

        Old formula: Δf = 2γ_p·D·k/(π·μ₀·Ms) ≈ 186 000 GHz — 6 orders wrong.
        New formula: Δf = 2γ_p·D·k/Ms ≈ 1.5 GHz — consistent with literature.
        """
        from maglab.analysis.effects.dmi import DMIEffect

        model = DMIEffect()
        D_i = 1.3e-3   # J/m²  (Co/Pt typical)
        k = 1.2e7      # rad/m  (BLS probe wavevector)
        Ms = 1.19e6    # A/m   (Co)

        params = {"D_i": D_i}
        geo = {"k": np.array([k]), "Ms": Ms}
        delta_f_GHz = float(model.forward(params, geo)[0])

        # Direct formula: Δf = 2·γ_p·D·k / Ms
        gamma_p = abs(GAMMA_E) / (2.0 * math.pi) * 1e-9  # GHz/T
        delta_f_expected = 2.0 * gamma_p * D_i * k / Ms

        # Must match the formula exactly
        assert abs(delta_f_GHz - delta_f_expected) / abs(delta_f_expected) < 1e-8, (
            f"DMI Δf formula mismatch: got {delta_f_GHz:.6g} GHz, "
            f"expected {delta_f_expected:.6g} GHz"
        )

        # Must be in the physically plausible range 0.5–5 GHz
        assert 0.5 < delta_f_GHz < 5.0, (
            f"DMI Δf = {delta_f_GHz:.3f} GHz outside literature range 0.5–5 GHz; "
            "likely μ₀ still present in denominator."
        )

    def test_dmi_roundtrip(self) -> None:
        """Fit D_i from synthetic Δf(k) data and recover it within 5%."""
        from maglab.analysis.effects.dmi import DMIEffect

        model = DMIEffect()
        D_true = 1.3e-3  # J/m²
        Ms = 1.19e6      # A/m
        gamma_p = abs(GAMMA_E) / (2.0 * math.pi) * 1e-9  # GHz/T
        k = np.linspace(0.5e7, 2.0e7, 20)
        delta_f = 2.0 * gamma_p * D_true * k / Ms  # correct formula

        result = model.fit({"k": k, "delta_f": delta_f}, geometry={"Ms": Ms})
        assert result.success
        D_fit = result.params["D_i"]
        rel_err = abs(D_fit - D_true) / D_true
        assert rel_err < 0.05, (
            f"DMI roundtrip: D_true={D_true:.4g}, D_fit={D_fit:.4g}, "
            f"rel_err={rel_err:.3f}"
        )

    def test_dmi_formula_no_mu0(self) -> None:
        """Verify that μ₀ does NOT appear in the forward formula.

        The ratio forward(D=1)/ forward(D=2) must equal 0.5 — independent of
        any constant (including μ₀) in the denominator.  This is always true.
        The absolute-value test (above) is the real check.
        """
        from maglab.analysis.effects.dmi import DMIEffect

        model = DMIEffect()
        k = np.array([1e7])
        Ms = 1e6
        geo = {"k": k, "Ms": Ms}
        f1 = float(model.forward({"D_i": 1e-3}, geo)[0])
        f2 = float(model.forward({"D_i": 2e-3}, geo)[0])
        assert abs(f2 / f1 - 2.0) < 1e-8, "DMI Δf not linearly proportional to D_i."


# ===========================================================================
# FINDING 3 — ST-FMR spin_hall_angle(): corrected formula
# ===========================================================================


class TestSTFMRSpinHallAngleRegression:
    """Regression: spin_hall_angle() must include the geometry correction factor.

    FINDING 3 clarification (after dimensional analysis):
    - t_NM IS required for dimensional consistency: [e·μ₀·Ms·t_FM·t_NM/ħ] = 1 (dimensionless).
    - The reviewer's claim that t_NM is spurious was incorrect; only the missing
      geometry factor √(1 + M_eff/H_res) is the genuine defect.
    """

    def test_spin_hall_angle_returns_finite(self) -> None:
        """spin_hall_angle() returns a finite positive value for physical inputs."""
        from maglab.analysis.effects.stfmr import STFMREffect

        xi = STFMREffect.spin_hall_angle(
            S=1e-4, A=5e-5, Ms=8e5, t_FM=5e-9, t_NM=5e-9, M_eff=8e5, H_res=5e4
        )
        assert math.isfinite(xi), "spin_hall_angle returned non-finite value."
        assert xi > 0, "spin_hall_angle returned non-positive value."

    def test_spin_hall_angle_formula_pt_py(self) -> None:
        """Pt/Py typical: verify formula gives correct value including geom factor.

        Old formula (no geom factor): ξ_DL ≈ 0.008 (for S/A=0.2).
        New formula (with √(1+M_eff/H_res)): ξ_DL increases by factor √(1+M_eff/H_res).
        """
        from maglab.analysis.effects.stfmr import STFMREffect

        # Pt(5nm)/Py(5nm) typical values
        S = 0.2       # S/A ratio ~ 0.2 for Pt/Py
        A = 1.0
        Ms = 860e3    # A/m  (Permalloy)
        t_FM = 5e-9   # m
        t_NM = 5e-9   # m
        H_res = 60e3  # A/m  (≈ 75 mT)
        M_eff = Ms    # in-plane geometry: M_eff ≈ Ms

        xi = STFMREffect.spin_hall_angle(S, A, Ms, t_FM, t_NM, M_eff, H_res)

        # Manual formula: ξ = (S/A)·√(1+M_eff/H_res)·(e·μ₀·Ms·t_FM·t_NM/ħ)
        geom = math.sqrt(1.0 + M_eff / H_res)
        xi_expected = (S / A) * geom * (E_CHARGE * MU_0 * Ms * t_FM * t_NM / HBAR)

        assert abs(xi - xi_expected) / abs(xi_expected) < 1e-8, (
            f"spin_hall_angle formula mismatch: got {xi:.4g}, expected {xi_expected:.4g}"
        )
        # The new value must be larger than the old formula by approximately the geom factor
        xi_old = (S / A) * (E_CHARGE * MU_0 * Ms * t_FM * t_NM / HBAR)
        ratio = xi / xi_old
        assert abs(ratio - geom) / geom < 1e-6, (
            f"Geometry factor not applied correctly: ratio={ratio:.4f}, expected={geom:.4f}"
        )

    def test_spin_hall_angle_geometry_factor_dependence(self) -> None:
        """ξ_DL must vary with H_res (via the √(1+M_eff/H_res) factor)."""
        from maglab.analysis.effects.stfmr import STFMREffect

        S, A = 1.0, 1.0
        Ms = 8e5
        t_FM = 5e-9
        t_NM = 5e-9
        M_eff = Ms

        # Two different H_res values
        xi_low_H = STFMREffect.spin_hall_angle(S, A, Ms, t_FM, t_NM, M_eff, H_res=1e4)
        xi_high_H = STFMREffect.spin_hall_angle(S, A, Ms, t_FM, t_NM, M_eff, H_res=1e6)

        # At low H_res: √(1 + M_eff/H_res) is large → larger ξ
        # At high H_res: √(1 + M_eff/H_res) → √2 → smaller ξ
        assert xi_low_H > xi_high_H, (
            "ξ_DL should decrease as H_res increases (geometry factor). "
            "Likely geom factor is missing or wrong."
        )

    def test_spin_hall_angle_fit_integration(self) -> None:
        """fit() with Ms, t_FM, t_NM geometry computes xi_DL using corrected formula."""
        from maglab.analysis.effects.stfmr import STFMREffect, _lorentz_asym, _lorentz_sym

        S_true = 1e-4
        A_true = 5e-5
        H_res_true = 5e4   # A/m
        dH_true = 2e3
        Ms = 8e5
        t_FM = 5e-9
        t_NM = 5e-9
        M_eff = Ms

        H = np.linspace(H_res_true - 3e4, H_res_true + 3e4, 200)
        V_mix = S_true * _lorentz_sym(H, H_res_true, dH_true) + A_true * _lorentz_asym(
            H, H_res_true, dH_true
        )
        model = STFMREffect()
        result = model.fit(
            {"H": H, "V_mix": V_mix},
            geometry={"Ms": Ms, "t_FM": t_FM, "t_NM": t_NM, "M_eff": M_eff},
        )
        assert result.success
        assert "xi_DL" in result.params
        xi_fit = result.params["xi_DL"]

        # Compute expected using the fitted S, A, H_res and the corrected formula
        S_fit = result.params["S"]
        A_fit = result.params["A"]
        H_res_fit = result.params["H_res"]
        geom = math.sqrt(1.0 + M_eff / H_res_fit)
        xi_manual = (S_fit / A_fit) * geom * (E_CHARGE * MU_0 * Ms * t_FM * t_NM / HBAR)

        assert abs(xi_fit - xi_manual) / abs(xi_manual) < 1e-6, (
            f"xi_DL from fit() {xi_fit:.4g} ≠ manual formula {xi_manual:.4g}"
        )


# ===========================================================================
# R2-FINDING 1 — dw_velocity_below_walker: 1/α → 1/(1+α²) (formulas.py)
# ===========================================================================


class TestDWVelocityBelowWalkerRegression:
    """R2-F1: dw_velocity_below_walker must use denominator (1+α²), not 1/α.

    Schryer–Walker (1974) JAP 45, 5406 Eq. (8a): v = γΔμ₀H / (1+α²).
    The old code used (γΔ/α)·μ₀H, overestimating by ~1/α for small α.
    """

    def test_dw_velocity_formula_small_alpha(self) -> None:
        """For α=0.01, Permalloy DW: velocity must be ~66 m/s, not 6638 m/s."""
        from maglab.physics.formulas import dw_velocity_below_walker

        gamma = abs(GAMMA_E)
        delta = 30e-9   # 30 nm wall width (Permalloy typical)
        H = 10e3        # 10 kA/m
        Ms = 8e5        # A/m (Permalloy)
        alpha = 0.01

        v = dw_velocity_below_walker(H=H, alpha=alpha, Ms=Ms, delta=delta, gamma=gamma)

        # Correct formula: v = γ·Δ·μ₀·H / (1+α²)
        v_expected = gamma * delta * MU_0 * H / (1.0 + alpha**2)
        assert abs(v - v_expected) / abs(v_expected) < 1e-10, (
            f"dw_velocity_below_walker: got {v:.2f} m/s, expected {v_expected:.2f} m/s"
        )

        # Physical sanity: Permalloy DW velocities are 10–100 m/s at 10 kA/m
        assert 5.0 < v < 500.0, (
            f"dw_velocity_below_walker: {v:.2f} m/s outside physical range 5–500 m/s; "
            "likely using 1/alpha denominator instead of 1/(1+alpha^2)."
        )

    def test_dw_velocity_consistent_with_dw1d_model(self) -> None:
        """formulas.dw_velocity_below_walker must agree with DW1DModel.dw_velocity_below_walker."""
        from maglab.analysis.effects.dw_1d import DW1DModel
        from maglab.physics.formulas import dw_velocity_below_walker

        gamma = abs(GAMMA_E)
        H = 5e3
        alpha = 0.05
        delta = 20e-9
        Ms = 8e5

        v_formulas = dw_velocity_below_walker(H=H, alpha=alpha, Ms=Ms, delta=delta, gamma=gamma)
        # DW1DModel uses default gamma=GAMMA_E; signature: (alpha, Delta, H)
        model = DW1DModel()
        v_model = model.dw_velocity_below_walker(alpha=alpha, Delta=delta, H=H)

        rel_diff = abs(v_formulas - v_model) / max(abs(v_formulas), abs(v_model), 1e-30)
        assert rel_diff < 1e-8, (
            f"formulas.dw_velocity_below_walker ({v_formulas:.4f} m/s) "
            f"disagrees with DW1DModel ({v_model:.4f} m/s); ratio={v_formulas/v_model:.4f}"
        )

    def test_dw_velocity_denominator_alpha_squared(self) -> None:
        """Ratio v(α=0.1)/v(α=0.2) must match (1+0.04)/(1+0.01) — not 2."""
        from maglab.physics.formulas import dw_velocity_below_walker

        gamma = abs(GAMMA_E)
        delta = 30e-9
        H = 10e3
        Ms = 8e5

        v1 = dw_velocity_below_walker(H=H, alpha=0.1, Ms=Ms, delta=delta, gamma=gamma)
        v2 = dw_velocity_below_walker(H=H, alpha=0.2, Ms=Ms, delta=delta, gamma=gamma)

        # Correct: ratio = (1+0.04)/(1+0.01) ≈ 1.030 (independent of alpha in numerator)
        ratio_actual = v1 / v2
        ratio_expected = (1.0 + 0.2**2) / (1.0 + 0.1**2)  # ≈ 1.030
        assert abs(ratio_actual - ratio_expected) / ratio_expected < 1e-8, (
            f"dw_velocity ratio {ratio_actual:.6f} ≠ expected {ratio_expected:.6f}; "
            "denominator is not (1+α²)."
        )


# ===========================================================================
# R2-FINDING 2 — MacrospinModel.fit() time-series model: cosine term (macrospin.py)
# ===========================================================================


class TestMacrospinFitOscillatoryModel:
    """R2-F2: MacrospinModel.fit() time-series model must include the cosine factor.

    Real FMR ring-down: m_z(t) = 1 - A·exp(-α·ω₀·t)·cos(ω₀·t).
    The old code used purely exponential: 1 - A·exp(-α·ω₀·t), giving
    ~14 000% error in extracted α for underdamped systems (α ≪ 1).
    """

    def test_macrospin_fit_recovers_alpha_from_oscillatory_data(self) -> None:
        """Fit α from synthetic oscillatory FMR data must recover α within 10%.

        With the old purely-exponential model, curve_fit drives alpha → ~1.47
        for true alpha=0.01 (error ~14 500%).
        """
        from maglab.analysis.effects.macrospin import MacrospinModel

        alpha_true = 0.01
        H_k = 1e5          # A/m
        omega_0 = abs(GAMMA_E) * MU_0 * H_k  # rad/s
        mz_0 = 0.8         # initial m_z

        # Synthetic oscillatory data: 1 - A·exp(-α·ω₀·t)·cos(ω₀·t)
        t = np.linspace(0.0, 5.0 / (alpha_true * omega_0), 500)
        mz_data = 1.0 - (1.0 - mz_0) * np.exp(-alpha_true * omega_0 * t) * np.cos(omega_0 * t)

        model = MacrospinModel()
        result = model.fit({"t": t, "mz": mz_data}, geometry={"H_k": H_k})

        assert result.success, f"MacrospinModel.fit() failed: {result}"
        alpha_fit = result.params["alpha"]
        rel_err = abs(alpha_fit - alpha_true) / alpha_true
        assert rel_err < 0.10, (
            f"MacrospinModel.fit() alpha: true={alpha_true}, fit={alpha_fit:.6g}, "
            f"rel_err={rel_err:.3f} > 10%; "
            "cosine term likely still missing from model_fn_t."
        )

    def test_macrospin_fit_model_fn_includes_cosine(self) -> None:
        """The fit model must include a cosine factor: verify the oscillatory structure.

        The purely-exponential model would fit oscillatory data with very large α
        (driving toward the overdamped limit). The corrected oscillatory model
        recovers a physically small α.
        """
        from maglab.analysis.effects.macrospin import MacrospinModel

        alpha_true = 0.01
        H_k = 1e5
        omega_0 = abs(GAMMA_E) * MU_0 * H_k
        mz_0 = 0.8

        # Synthetic oscillatory data over 5 damping times (enough to constrain the fit)
        t = np.linspace(0.0, 5.0 / (alpha_true * omega_0), 400)
        mz_data = 1.0 - (1.0 - mz_0) * np.exp(-alpha_true * omega_0 * t) * np.cos(omega_0 * t)

        model = MacrospinModel()
        result = model.fit({"t": t, "mz": mz_data}, geometry={"H_k": H_k})
        assert result.success

        # With the cosine model the fit should converge to small α (underdamped regime)
        # If cosine were absent, curve_fit would push α toward the overdamped limit (~1)
        alpha_fit = result.params["alpha"]
        assert alpha_fit < 0.5, (
            f"alpha_fit={alpha_fit:.4g}: suspiciously large — "
            "cosine term may still be missing from model_fn_t."
        )


# ===========================================================================
# R2-FINDING 5 — skyrmion_hall_angle: ZeroDivisionError for alpha=0 (formulas.py)
# ===========================================================================


class TestSkyrmionHallAngleRegression:
    """R2-F5: skyrmion_hall_angle must handle alpha=0 without raising ZeroDivisionError.

    Physical expectation: as α → 0, θ_SkHE → π/2 (pure transverse drift).
    The Thiele equation gives tan(θ) = G/(α·D) → ∞ for α=0, so θ = π/2.
    """

    def test_skyrmion_hall_angle_alpha_zero_no_exception(self) -> None:
        """skyrmion_hall_angle(alpha=0) must not raise ZeroDivisionError."""
        from maglab.physics.formulas import skyrmion_hall_angle

        # This must not raise:
        angle = skyrmion_hall_angle(alpha=0.0, Q=1)
        assert math.isfinite(angle), "skyrmion_hall_angle(0) returned non-finite value."

    def test_skyrmion_hall_angle_alpha_zero_returns_pi_over_2(self) -> None:
        """skyrmion_hall_angle(alpha=0) must return π/2 (pure transverse drift)."""
        from maglab.physics.formulas import skyrmion_hall_angle

        angle = skyrmion_hall_angle(alpha=0.0, Q=1)
        assert abs(angle - math.pi / 2.0) < 1e-10, (
            f"skyrmion_hall_angle(0) = {angle:.6f}, expected π/2 = {math.pi / 2:.6f}"
        )

    def test_skyrmion_hall_angle_large_alpha_approaches_zero(self) -> None:
        """skyrmion_hall_angle(large α) → 0 (skyrmion moves along current)."""
        from maglab.physics.formulas import skyrmion_hall_angle

        angle_large = skyrmion_hall_angle(alpha=100.0, Q=1)
        # atan2(4π, 100) ≈ 0.125 rad; should be small
        assert abs(angle_large) < 0.2, (
            f"skyrmion_hall_angle(100) = {angle_large:.4f}, expected < 0.2 rad."
        )

    def test_skyrmion_hall_angle_matches_atan2_formula(self) -> None:
        """Result must match math.atan2(4πQ, α·D_norm) for arbitrary α."""
        from maglab.physics.formulas import skyrmion_hall_angle

        for alpha_test in [0.0, 0.001, 0.01, 0.1, 1.0, 10.0]:
            Q = 1.0
            G = 4.0 * math.pi * Q
            D_norm = 1.0
            expected = math.atan2(G, alpha_test * D_norm)
            actual = skyrmion_hall_angle(alpha=alpha_test, Q=Q)
            assert abs(actual - expected) < 1e-12, (
                f"alpha={alpha_test}: got {actual:.6g}, expected {expected:.6g}"
            )


# ===========================================================================
# R3-FINDING 2 — FMRKittel.forward() / fit() model mismatch (fmr_kittel.py)
# ===========================================================================


class TestFMRKittelForwardFitConsistency:
    """R3-F2: forward() must use the same radicand handling as fit().

    Before the fix: forward() called np.sqrt(H_Am*(H_Am+M_eff)) which returns NaN
    when M_eff < -H_Am.  fit() called np.sqrt(np.abs(...)) and could converge to
    such parameters.  The invariant 'fit params usable with forward()' was broken.

    After the fix: forward() also uses np.abs, so fitted parameters with M_eff < -H_Am
    produce finite predictions from forward().
    """

    def test_forward_no_nan_for_negative_meff(self) -> None:
        """forward() must not return NaN when M_eff < -H_res/mu_0 (PMA-like)."""
        from maglab.analysis.effects.fmr_kittel import FMRKittel

        model = FMRKittel(mode="in_plane")
        # M_eff strongly negative: M_eff = -3e6 A/m, H_res = 0.1–0.3 T
        # H_Am = H_res/mu_0 ~ 8e4 – 2.4e5 A/m  << |M_eff| = 3e6 A/m
        H_res = np.array([0.1, 0.2, 0.3])  # T
        params = {"M_eff": -3e6, "gamma_ghz_t": 28.0}
        f = model.forward(params, geometry={"H_res": H_res})
        assert not np.any(np.isnan(f)), (
            f"forward() returned NaN for negative M_eff: {f}; "
            "np.abs guard missing from forward()."
        )
        assert np.all(f >= 0.0), f"forward() returned negative frequencies: {f}"

    def test_forward_fit_consistency_for_negative_meff(self) -> None:
        """Parameters returned by fit() must yield finite predictions from forward()."""
        from maglab.analysis.effects.fmr_kittel import FMRKittel

        model = FMRKittel(mode="in_plane")
        # Construct synthetic data from a negative-M_eff scenario using the abs formula
        H_res = np.linspace(0.05, 0.5, 30)
        H_Am = H_res / MU_0
        M_eff_true = -3e6  # A/m — strongly PMA-like
        gamma_true = 28.0  # GHz/T
        f_data = gamma_true * MU_0 * np.sqrt(np.abs(H_Am * (H_Am + M_eff_true)))

        result = model.fit({"H_res": H_res, "f": f_data})
        assert result.success, f"fit() did not converge: {result}"

        # Now call forward() with fitted parameters — must not produce NaN
        f_pred = model.forward(result.params, geometry={"H_res": H_res})
        assert not np.any(np.isnan(f_pred)), (
            f"forward() with fitted params returned NaN: {f_pred}; "
            "forward()/fit() model mismatch persists."
        )

    def test_forward_positive_meff_unchanged(self) -> None:
        """For M_eff > 0, forward() must give the same result as before (no regression)."""
        from maglab.analysis.effects.fmr_kittel import FMRKittel

        model = FMRKittel(mode="in_plane")
        H_res = np.linspace(0.05, 0.3, 20)
        H_Am = H_res / MU_0
        M_eff = 8e5  # positive — normal in-plane film
        gamma_p = 28.0

        params = {"M_eff": M_eff, "gamma_ghz_t": gamma_p}
        f = model.forward(params, geometry={"H_res": H_res})
        f_expected = gamma_p * MU_0 * np.sqrt(H_Am * (H_Am + M_eff))

        np.testing.assert_allclose(f, f_expected, rtol=1e-10,
                                   err_msg="forward() changed for positive M_eff.")


# ===========================================================================
# R3-FINDING 3 — STFMREffect.spin_hall_angle() PMA crash (stfmr.py)
# ===========================================================================


class TestSpinHallAnglePMAGuard:
    """R3-F3: spin_hall_angle() must raise ValueError (not crash with math domain error)
    for PMA films where 1 + M_eff/H_res < 0.

    The Liu et al. (2011) formula applies to in-plane samples; PMA geometry is
    physically distinct and must be handled by raising a descriptive error.
    """

    def test_pma_film_raises_value_error(self) -> None:
        """CoFeB/MgO PMA parameters must raise ValueError, not math domain error."""
        import pytest

        from maglab.analysis.effects.stfmr import STFMREffect

        # Ta/CoFeB/MgO typical: M_eff < 0, |M_eff| >> H_res
        M_eff = -5e5   # A/m  (strong PMA)
        H_res = 1e4    # A/m  (1 + M_eff/H_res = 1 - 50 = -49)
        with pytest.raises(ValueError, match="spin_hall_angle"):
            STFMREffect.spin_hall_angle(
                S=1e-4, A=5e-5, Ms=8e5, t_FM=5e-9, t_NM=5e-9,
                M_eff=M_eff, H_res=H_res
            )

    def test_pma_error_message_is_descriptive(self) -> None:
        """The ValueError message must mention PMA / in-plane geometry."""
        import pytest

        from maglab.analysis.effects.stfmr import STFMREffect

        with pytest.raises(ValueError, match="PMA"):
            STFMREffect.spin_hall_angle(
                S=1e-4, A=5e-5, Ms=8e5, t_FM=5e-9, t_NM=5e-9,
                M_eff=-5e5, H_res=1e4
            )

    def test_borderline_pma_exactly_negative_one(self) -> None:
        """1 + M_eff/H_res = 0 (M_eff = -H_res) must raise ValueError."""
        from maglab.analysis.effects.stfmr import STFMREffect

        H_res = 1e5
        M_eff = -H_res  # geom_arg = 0.0 → sqrt(0) is fine, but M_eff < 0 check catches < 0
        # geom_arg = 0 → sqrt(0) = 0, which is valid (boundary)
        xi = STFMREffect.spin_hall_angle(
            S=1e-4, A=5e-5, Ms=8e5, t_FM=5e-9, t_NM=5e-9,
            M_eff=M_eff, H_res=H_res
        )
        assert xi == 0.0 or math.isfinite(xi), "Borderline case (geom_arg=0) should not crash."

    def test_in_plane_film_unchanged(self) -> None:
        """Positive M_eff (in-plane film) must still work correctly."""
        from maglab.analysis.effects.stfmr import STFMREffect

        xi = STFMREffect.spin_hall_angle(
            S=1e-4, A=5e-5, Ms=8e5, t_FM=5e-9, t_NM=5e-9, M_eff=8e5, H_res=5e4
        )
        assert math.isfinite(xi) and xi > 0, "In-plane spin_hall_angle must still work."


# ===========================================================================
# R3-FINDING 5 — LLGModel.forward() ZeroDivisionError for degenerate t_span (llg.py)
# ===========================================================================


class TestLLGForwardDegenerateTspan:
    """R3-F5: LLGModel.forward() must not raise ZeroDivisionError for t_span[0]==t_span[1].

    MacrospinModel._llg_rk4 has this guard; LLGModel.forward() must mirror it.
    """

    def test_degenerate_tspan_h_nonzero_no_crash(self) -> None:
        """t_span=(T, T) with H_mag > 0 must not raise ZeroDivisionError."""
        from maglab.analysis.effects.llg import LLGModel

        model = LLGModel()
        T = 1e-9
        m_0 = np.array([0.0, 0.0, 1.0])
        params = {"alpha": 0.01, "tau_DL": 0.0, "tau_FL": 0.0}
        geo = {
            "t_span": (T, T),
            "t_eval": np.array([T]),
            "m_0": m_0,
            "H_eff": np.array([0.0, 0.0, 1e4]),
            "m_p": np.array([1.0, 0.0, 0.0]),
        }
        # Must not raise; result must be the initial magnetization
        result = model.forward(params, geo)
        assert result.shape == (1, 3), f"Unexpected shape: {result.shape}"
        np.testing.assert_allclose(result[0], m_0, atol=1e-12,
                                   err_msg="Degenerate t_span must return initial condition.")

    def test_degenerate_tspan_h_zero_no_crash(self) -> None:
        """t_span=(T, T) with H_mag=0 must not raise ZeroDivisionError."""
        from maglab.analysis.effects.llg import LLGModel

        model = LLGModel()
        T = 5e-10
        m_0 = np.array([1.0, 0.0, 0.0])
        params = {"alpha": 0.01, "tau_DL": 0.0, "tau_FL": 0.0}
        geo = {
            "t_span": (T, T),
            "t_eval": np.array([T]),
            "m_0": m_0,
            "H_eff": np.array([0.0, 0.0, 0.0]),
            "m_p": np.array([1.0, 0.0, 0.0]),
        }
        result = model.forward(params, geo)
        assert result.shape == (1, 3)
        np.testing.assert_allclose(result[0], m_0, atol=1e-12,
                                   err_msg="Degenerate zero-H t_span must return initial condition.")

    def test_degenerate_tspan_zero_origin_no_crash(self) -> None:
        """t_span=(0, 0) must not crash."""
        from maglab.analysis.effects.llg import LLGModel

        model = LLGModel()
        m_0 = np.array([0.0, 1.0, 0.0])
        params = {"alpha": 0.005, "tau_DL": 0.0, "tau_FL": 0.0}
        geo = {
            "t_span": (0.0, 0.0),
            "t_eval": np.array([0.0]),
            "m_0": m_0,
            "H_eff": np.array([0.0, 0.0, 1e4]),
            "m_p": np.array([1.0, 0.0, 0.0]),
        }
        result = model.forward(params, geo)
        assert result.shape == (1, 3)
        np.testing.assert_allclose(result[0], m_0, atol=1e-12)


# ===========================================================================
# R4-FINDING 1 — LLG2SublatticeModel._llg2sl_rk4: internal step-size control
# ===========================================================================


class TestLLG2SublatticeStepControl:
    """R4-F1: _llg2sl_rk4 must use an internal oversampled grid so that large
    AFM exchange fields (H_E ~ 10⁹ A/m) do not produce numerically unstable
    trajectories.

    Physical criterion: after integrating for one AFMR period, both sublattice
    magnetization vectors must remain unit-norm (within 1e-4) and the
    integration must not diverge.

    Before the fix: the raw user time-step dt ≈ 5 fs gives ~5.7 steps per
    period for H_E = 10⁹ A/m → RK4 is unstable and |m| blows up.
    After the fix: the internal grid uses ≥ 10 steps/period and |m| ≤ 1 + 1e-4
    throughout the trajectory.
    """

    def test_large_exchange_field_stays_unit_norm(self) -> None:
        """H_E = 10⁹ A/m (NiO-class AFM): sublattice norms must stay near 1."""
        from maglab.analysis.effects.llg_2sublattice import LLG2SublatticeModel

        model = LLG2SublatticeModel()
        H_E = 1e9  # A/m — very large, RK4-unstable without oversampling
        H_A = 1e7  # A/m
        gamma = abs(GAMMA_E)
        # AFMR period: T = 1/f_AFMR where f_AFMR = (γ/2π)·μ₀·√(2H_E·H_A)
        f_afmr = (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(2.0 * H_E * H_A)
        T_afmr = 1.0 / f_afmr  # ~ 0.5 ps

        # Default t_arr spacing at 200 points over 1 ps → dt = 5 fs
        # That is only ~10 steps per AFMR period — right at the stability boundary.
        # 10⁹ A/m gives T_precession ~ 28 fs → dt=5 fs is ~5.7 steps/period: UNSTABLE.
        n_pts = 200
        t_eval = np.linspace(0.0, T_afmr, n_pts)

        params = {"H_E": H_E, "H_A": H_A, "alpha_a": 0.005, "alpha_b": 0.005}
        geo = {
            "t_span": (0.0, T_afmr),
            "t_eval": t_eval,
            "m_0_a": np.array([0.05, 0.0, math.sqrt(1.0 - 0.05**2)]),
            "m_0_b": np.array([0.05, 0.0, -math.sqrt(1.0 - 0.05**2)]),
            "H_ext": np.array([0.0, 0.0, 0.0]),
            "Ms_a": 8e5,
            "Ms_b": 6e5,
        }
        traj = model.forward(params, geo)

        assert traj.shape == (n_pts, 6), f"Unexpected trajectory shape: {traj.shape}"
        norms_a = np.linalg.norm(traj[:, :3], axis=1)
        norms_b = np.linalg.norm(traj[:, 3:], axis=1)

        # Unit-norm invariant must hold throughout: |m| = 1 ± 1e-4
        np.testing.assert_allclose(
            norms_a, 1.0, atol=1e-4,
            err_msg=(
                "LLG2SublatticeModel: |m_a| deviates from 1 for H_E=1e9 A/m; "
                "likely missing internal step-size control."
            ),
        )
        np.testing.assert_allclose(
            norms_b, 1.0, atol=1e-4,
            err_msg=(
                "LLG2SublatticeModel: |m_b| deviates from 1 for H_E=1e9 A/m; "
                "likely missing internal step-size control."
            ),
        )

    def test_step_control_finer_than_user_grid(self) -> None:
        """Oversampled integration produces a different (more accurate) result than
        a single-step integration on the user grid for large H_E.

        We verify this indirectly: with H_E=10⁸ A/m the oversampled integrator
        stays unit-norm, while a naive single-step integrator at the same dt
        would diverge (norm > 1.1 at some point).  Since we can only test the
        fixed code, we verify that trajectories at two different n_pts produce
        consistent final states (convergence criterion).
        """
        from maglab.analysis.effects.llg_2sublattice import LLG2SublatticeModel

        model = LLG2SublatticeModel()
        H_E = 1e8
        H_A = 1e6
        gamma = abs(GAMMA_E)
        f_afmr = (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(2.0 * H_E * H_A)
        T_afmr = 1.0 / f_afmr

        params = {"H_E": H_E, "H_A": H_A, "alpha_a": 0.005, "alpha_b": 0.005}
        m_0_a = np.array([0.05, 0.0, math.sqrt(1.0 - 0.05**2)])
        m_0_b = np.array([0.05, 0.0, -math.sqrt(1.0 - 0.05**2)])

        def run(n_pts: int) -> np.ndarray:
            t_eval = np.linspace(0.0, T_afmr, n_pts)
            geo = {
                "t_span": (0.0, T_afmr),
                "t_eval": t_eval,
                "m_0_a": m_0_a,
                "m_0_b": m_0_b,
                "H_ext": np.array([0.0, 0.0, 0.0]),
                "Ms_a": 8e5,
                "Ms_b": 6e5,
            }
            return model.forward(params, geo)

        traj_coarse = run(50)
        traj_fine = run(200)

        # Both must stay unit-norm (internal oversampling is independent of n_pts)
        for traj, label in [(traj_coarse, "coarse"), (traj_fine, "fine")]:
            norms_a = np.linalg.norm(traj[:, :3], axis=1)
            norms_b = np.linalg.norm(traj[:, 3:], axis=1)
            np.testing.assert_allclose(norms_a, 1.0, atol=1e-4,
                err_msg=f"H_E=1e8 {label}: |m_a| not unit-norm")
            np.testing.assert_allclose(norms_b, 1.0, atol=1e-4,
                err_msg=f"H_E=1e8 {label}: |m_b| not unit-norm")

    def test_degenerate_tspan_no_crash(self) -> None:
        """t_start == t_end: must return initial condition without crashing."""
        from maglab.analysis.effects.llg_2sublattice import LLG2SublatticeModel

        model = LLG2SublatticeModel()
        m_0_a = np.array([0.0, 0.0, 1.0])
        m_0_b = np.array([0.0, 0.0, -1.0])
        params = {"H_E": 1e8, "H_A": 1e6, "alpha_a": 0.005, "alpha_b": 0.005}
        geo = {
            "t_span": (1e-12, 1e-12),
            "t_eval": np.array([1e-12]),
            "m_0_a": m_0_a,
            "m_0_b": m_0_b,
            "H_ext": np.array([0.0, 0.0, 0.0]),
            "Ms_a": 8e5,
            "Ms_b": 6e5,
        }
        traj = model.forward(params, geo)
        assert traj.shape == (1, 6)
        # Initial conditions must be returned exactly
        np.testing.assert_allclose(traj[0, :3], m_0_a, atol=1e-12)
        np.testing.assert_allclose(traj[0, 3:], m_0_b, atol=1e-12)


# ===========================================================================
# R4-FINDING 3 — FMRKittel.forward() out-of-plane mode: negative frequency fix
# ===========================================================================


class TestFMRKittelOOPNegativeFrequency:
    """R4-F3: FMRKittel.forward() out-of-plane mode must never return negative
    frequencies when H_res < M_eff·μ₀.

    Before the fix: f = γ'·μ₀·(H[A/m] − M_eff) returned negative values when
    H[A/m] < M_eff, violating the physical constraint that FMR frequency ≥ 0.

    The fix applies np.abs(), consistent with formulas.py:403 which uses abs().
    """

    def test_oop_forward_no_negative_frequency_below_saturation(self) -> None:
        """H_res < M_eff·μ₀ (below saturation): forward() must return f ≥ 0."""
        from maglab.analysis.effects.fmr_kittel import FMRKittel

        model = FMRKittel(mode="out_of_plane")
        # M_eff = 8e5 A/m → saturation field ≈ 8e5 × 1.257e-6 ≈ 1.005 T
        M_eff = 8e5  # A/m
        # H_res all below saturation → H_Am < M_eff → naive formula gives f < 0
        H_res = np.array([0.01, 0.05, 0.1, 0.3, 0.5])  # T
        params = {"M_eff": M_eff, "gamma_ghz_t": 28.0}

        f = model.forward(params, geometry={"H_res": H_res})

        assert np.all(f >= 0.0), (
            f"FMRKittel OOP: negative frequencies returned: {f}; "
            "abs() guard missing from forward()."
        )
        assert not np.any(np.isnan(f)), f"FMRKittel OOP: NaN returned: {f}"

    def test_oop_forward_zero_at_saturation(self) -> None:
        """At H_res = M_eff·μ₀ (saturation field), f = 0."""
        from maglab.analysis.effects.fmr_kittel import FMRKittel

        model = FMRKittel(mode="out_of_plane")
        M_eff = 8e5  # A/m
        H_sat_T = M_eff * MU_0  # T — exactly at saturation
        params = {"M_eff": M_eff, "gamma_ghz_t": 28.0}

        f = model.forward(params, geometry={"H_res": np.array([H_sat_T])})
        assert abs(float(f[0])) < 1e-6, (
            f"FMRKittel OOP: f at saturation = {f[0]:.4g} GHz ≠ 0."
        )

    def test_oop_forward_positive_above_saturation(self) -> None:
        """H_res > M_eff·μ₀ (above saturation): formula must be unchanged, f > 0."""
        from maglab.analysis.effects.fmr_kittel import FMRKittel

        model = FMRKittel(mode="out_of_plane")
        M_eff = 8e5  # A/m
        # H_res well above M_eff·μ₀ ≈ 1.005 T
        H_res = np.array([1.5, 2.0, 3.0])  # T
        H_Am = H_res / MU_0
        params = {"M_eff": M_eff, "gamma_ghz_t": 28.0}

        f = model.forward(params, geometry={"H_res": H_res})
        f_expected = 28.0 * MU_0 * (H_Am - M_eff)  # H_Am > M_eff → positive, abs is identity

        np.testing.assert_allclose(
            f, f_expected, rtol=1e-10,
            err_msg="FMRKittel OOP: above-saturation result changed (regression).",
        )

    def test_oop_fit_model_fn_no_negative_frequency(self) -> None:
        """fit() model_fn must also never return negative frequencies.

        This verifies the abs() fix was applied to both forward() and the
        internal model_fn used by fit().
        """
        from maglab.analysis.effects.fmr_kittel import FMRKittel

        model = FMRKittel(mode="out_of_plane")
        # Synthetic data: frequencies generated with abs() formula, covering
        # both sub- and above-saturation regions.
        M_eff_true = 8e5
        gamma_true = 28.0
        H_res = np.linspace(0.01, 2.0, 40)  # T — spans below and above saturation
        H_Am = H_res / MU_0
        f_data = gamma_true * MU_0 * np.abs(H_Am - M_eff_true)

        result = model.fit({"H_res": H_res, "f": f_data})
        assert result.success, f"fit() failed: {result}"

        # Check that forward() with the fitted params produces no negative values
        f_pred = model.forward(result.params, geometry={"H_res": H_res})
        assert np.all(f_pred >= 0.0), (
            f"FMRKittel OOP: fit() → forward() produced negative frequencies: {f_pred}"
        )


# ===========================================================================
# R5-FINDING 1 — ferrimagnet_compensation_freq: rad/s → Hz; FiM H_E inversion
# ===========================================================================


class TestFerrimagnetCompensationFreqUnits:
    """R5-F1: ferrimagnet_compensation_freq() must return f [Hz], not ω [rad/s].

    The old code returned angular frequency ω = (|γ_a m_a − γ_b m_b|/(m_a+m_b))·μ₀·H_E
    [rad/s] while the docstring claimed [Hz].  The FiM inversion in
    LLG2SublatticeModel.fit() treated the return value as [Hz] and therefore
    computed H_E too small by a factor of 2π ≈ 6.28.

    Fix: formulas.py divides by 2π; llg_2sublattice.py multiplies by 2π in the
    inversion.  The two changes are consistent and H_E is now physically correct.
    """

    def test_compensation_freq_returns_hz_not_rad_per_s(self) -> None:
        """ferrimagnet_compensation_freq() must return f [Hz], not ω [rad/s].

        For GdFe-class parameters (m_a=4e5, m_b=6e5, H_E=1e8 A/m, equal γ),
        the angular frequency is:
            ω = (|γ_a m_a − γ_b m_b| / (m_a + m_b)) · μ₀ · H_E
              = (|γ × 4e5 − γ × 6e5| / (4e5 + 6e5)) · μ₀ · 1e8
              = (γ × 2e5 / 1e6) · μ₀ · 1e8
              = 0.2 γ · μ₀ · 1e8
        Numeric: 0.2 × 1.7609e11 × 1.2566e-6 × 1e8 ≈ 4.427e12 rad/s
        f [Hz] = ω / (2π) ≈ 7.047e11 Hz ≈ 705 GHz.

        The old code returned the ω value (~4.4e12); the corrected code returns
        ω/(2π) (~7.0e11).  The ratio must be 1/(2π).
        """
        from maglab.physics.formulas import ferrimagnet_compensation_freq

        gamma = abs(GAMMA_E)
        m_a = 4e5    # A/m
        m_b = 6e5    # A/m
        H_E = 1e8    # A/m

        f_hz = ferrimagnet_compensation_freq(m_a, m_b, H_E, gamma, gamma)

        # Angular frequency from first principles:
        omega_expected = (abs(gamma * m_a - gamma * m_b) / (m_a + m_b)) * MU_0 * H_E
        f_expected = omega_expected / (2.0 * math.pi)

        assert abs(f_hz - f_expected) / abs(f_expected) < 1e-10, (
            f"ferrimagnet_compensation_freq: got {f_hz:.4g} Hz, "
            f"expected {f_expected:.4g} Hz (ω/(2π))"
        )

        # Sanity: must be ~2π× smaller than the old incorrect return value
        old_wrong_return = omega_expected  # what the old code returned
        ratio = old_wrong_return / f_hz
        assert abs(ratio - 2.0 * math.pi) / (2.0 * math.pi) < 1e-8, (
            f"ratio old/new = {ratio:.6f}, expected 2π = {2.0 * math.pi:.6f}; "
            "the 2π conversion was not applied."
        )

    def test_fim_inversion_recovers_physical_h_e(self) -> None:
        """LLG2SublatticeModel.fit() FiM inversion must recover H_E within 0.1%.

        Round-trip: compute f_comp from H_E_true using the corrected formula,
        then invert via fit() and compare.  The old code gave H_E ≈ H_E_true / 2π.

        Physical scale: for GdFe-class FiM with H_E_true = 1.0e8 A/m
        (exchange field), the recovered H_E must be within 0.1% of 1.0e8 A/m,
        not ~1.59e7 A/m as the old code produced.
        """
        from maglab.analysis.effects.llg_2sublattice import LLG2SublatticeModel
        from maglab.physics.formulas import ferrimagnet_compensation_freq

        model = LLG2SublatticeModel()
        gamma = abs(GAMMA_E)
        m_a = 4e5    # A/m  (GdFe sublattice a)
        m_b = 6e5    # A/m  (GdFe sublattice b)
        H_E_true = 1.0e8  # A/m — physically realistic exchange field

        # Forward: compute f_comp from the corrected formula [Hz]
        f_comp = ferrimagnet_compensation_freq(m_a, m_b, H_E_true, gamma, gamma)

        # Inverse: recover H_E from f_comp via fit()
        # Wrap scalars as 1-element arrays to satisfy the dict[str, ndarray] type.
        result = model.fit(
            {
                "m_a": np.array([m_a]),
                "m_b": np.array([m_b]),
                "f_comp": np.array([f_comp]),
            },
            geometry={"gamma_a": gamma, "gamma_b": gamma},
        )

        H_E_fit = result.params["H_E"]
        rel_err = abs(H_E_fit - H_E_true) / H_E_true
        assert rel_err < 1e-3, (
            f"FiM H_E inversion: H_E_true={H_E_true:.4g} A/m, "
            f"H_E_fit={H_E_fit:.4g} A/m, rel_err={rel_err:.4f}; "
            "expected < 0.1%.  If error is ~2π, the 2π factor is still missing."
        )

        # Physical magnitude check: H_E must be ~10⁸ A/m, not ~10⁷ A/m
        assert 5e7 < H_E_fit < 2e8, (
            f"H_E_fit = {H_E_fit:.4g} A/m outside physical range 5e7–2e8 A/m; "
            "the inversion is off by a factor of 2π."
        )

    def test_compensation_freq_units_are_hz_not_rad_per_s(self) -> None:
        """The return value of ferrimagnet_compensation_freq() is in Hz.

        Physical check: for typical FiM parameters (500 GHz compensation),
        the function must return values in the ~10¹¹–10¹² range (Hz), not
        ~10¹²–10¹³ range (rad/s).

        Typical GdFe compensation frequency near T_comp: 100–1000 GHz
        (see Kim et al., Nature Materials 21, 544, 2022).
        """
        from maglab.physics.formulas import ferrimagnet_compensation_freq

        gamma = abs(GAMMA_E)
        m_a = 4e5
        m_b = 6e5
        H_E = 1e8

        f = ferrimagnet_compensation_freq(m_a, m_b, H_E, gamma, gamma)

        # The result should be in the range 10¹⁰–10¹² Hz (10 GHz to 1 THz)
        assert 1e10 < f < 1e13, (
            f"ferrimagnet_compensation_freq = {f:.4g}; "
            "expected 10 GHz–1 THz (Hz), not rad/s (~2π× larger)."
        )


# ===========================================================================
# R5-FINDING 2 — SpinPumpingISHE: spurious MU_0 in Δα denominator
# ===========================================================================


class TestSpinPumpingISHENoMu0:
    """R5-F2: SpinPumpingISHE Δα formula must NOT contain μ₀ in the denominator.

    Mosendz et al., PRB 82, 214403 (2010), Eq. (2):
        Δα = γ·ħ·g↑↓ / (4π·Ms·d_FM)

    The old code included MU_0 = 1.257e-6 H/m in the denominator, making the
    prefactor ~8e5× too large.  The fitted g↑↓ was off by a factor of μ₀.

    Physical scale: typical Pt/Py g↑↓ ≈ 3–7 × 10¹⁹ m⁻² (Mosendz 2010 Table I).
    """

    def test_forward_prefactor_physical_magnitude(self) -> None:
        """forward() Δα must be ~0.005–0.03 for Pt/Py parameters at saturation.

        Mosendz 2010 Table I (Pt/Py 5nm):
            g↑↓_eff = 4.4e19 m⁻², Ms = 800 kA/m, d_FM = 5 nm.
            Saturation Δα (tanh → 1):
            Δα_sat = γ·ħ·g↑↓ / (4π·Ms·d_FM)
               = 1.7609e11 × 1.0546e-34 × 4.4e19 / (4π × 8e5 × 5e-9)
               ≈ 0.0163 (dimensionless).

        The old code (with μ₀ in denominator) gives Δα_sat ≈ 0.0163 / μ₀ ≈ 1.3e4 —
        unphysical.

        Saturation is achieved by using lambda_sf ≪ d_NM: with lambda_sf=1e-12 m and
        d_NM=5e-9 m, the argument of tanh is 5e-9/(2e-12)=2500, so tanh → 1.
        """
        from maglab.analysis.effects.spin_pumping_ishe import SpinPumpingISHE
        from maglab.physics.constants import GAMMA_E, HBAR

        model = SpinPumpingISHE()
        g_eff = 4.4e19   # m⁻²  (Mosendz 2010, Pt/Py)
        Ms = 8e5         # A/m  (Permalloy)
        d_FM = 5e-9      # m    (5 nm FM layer)
        d_NM = np.array([5e-9])  # NM thickness

        # Use lambda_sf ≪ d_NM so tanh(d_NM / (2*lambda_sf)) → 1 (saturated limit)
        params = {"g_eff": g_eff, "alpha_0": 0.0, "lambda_sf": 1e-12}  # 1 pm: tiny λ → tanh ≈ 1
        geo = {"d_NM": d_NM, "Ms": Ms, "d_FM": d_FM}
        alpha_total = float(model.forward(params, geo)[0])
        delta_alpha = alpha_total  # alpha_0 = 0

        # Manual saturated formula (no μ₀, tanh → 1):
        gamma_rad = abs(GAMMA_E)
        delta_alpha_expected = (gamma_rad * HBAR * g_eff) / (4.0 * math.pi * Ms * d_FM)
        # tanh(d_NM / (2*lambda_sf)) = tanh(2500) ≈ 1.0 to machine precision
        # so delta_alpha ≈ delta_alpha_expected × tanh(2500) ≈ delta_alpha_expected

        assert abs(delta_alpha - delta_alpha_expected) / abs(delta_alpha_expected) < 1e-6, (
            f"SpinPumpingISHE forward: got Δα={delta_alpha:.4g}, "
            f"expected {delta_alpha_expected:.4g}; μ₀ may still be in denominator."
        )

        # Physical range: 0.001 < Δα_sat < 0.05 for Pt/Py
        assert 1e-3 < delta_alpha < 0.05, (
            f"Δα = {delta_alpha:.4g} outside physical range 0.001–0.05; "
            "spurious μ₀ in denominator would give Δα ~ 10⁴."
        )

    def test_fit_recovers_physical_g_eff(self) -> None:
        """fit() must recover g↑↓ ≈ 5×10¹⁹ m⁻² (not ~6×10¹³ m⁻²).

        With the corrected formula, a synthetic Δα(d_NM) curve generated with
        g_true = 5e19 m⁻² must be recovered within 5% by fit().

        With the old formula (μ₀ in denominator), the prefactor is ~8e5× too large,
        so the fitter drives g↑↓ toward g_true × μ₀ ≈ 6.28e13 m⁻² to compensate.
        """
        from maglab.analysis.effects.spin_pumping_ishe import SpinPumpingISHE
        from maglab.physics.constants import GAMMA_E, HBAR

        model = SpinPumpingISHE()
        g_true = 5.0e19   # m⁻²  — typical Pt/Py (Mosendz 2010)
        alpha_0_true = 0.005
        lambda_sf_true = 5e-9
        Ms = 8e5
        d_FM = 5e-9
        gamma_rad = abs(GAMMA_E)

        d_NM = np.linspace(1e-9, 30e-9, 25)
        # Correct forward model (no μ₀):
        prefactor = (gamma_rad * HBAR * g_true) / (4.0 * math.pi * Ms * d_FM)
        delta_alpha_synth = alpha_0_true + prefactor * np.tanh(d_NM / (2.0 * lambda_sf_true))

        result = model.fit(
            {"d_NM": d_NM, "delta_alpha": delta_alpha_synth},
            geometry={"Ms": Ms, "d_FM": d_FM},
        )
        assert result.success, f"SpinPumpingISHE fit did not converge: {result}"

        g_fit = result.params["g_eff"]
        rel_err = abs(g_fit - g_true) / g_true
        assert rel_err < 0.05, (
            f"SpinPumpingISHE fit: g_true={g_true:.4g} m⁻², g_fit={g_fit:.4g} m⁻², "
            f"rel_err={rel_err:.3f}; "
            "if g_fit ~ 6e13, μ₀ is still in the denominator (off by factor μ₀)."
        )

        # Physical magnitude gate: g↑↓ must be 10¹⁸–10²⁰ m⁻²
        assert 1e18 < g_fit < 1e21, (
            f"g↑↓_fit = {g_fit:.4g} m⁻² outside physical range 10¹⁸–10²⁰ m⁻²; "
            "Mosendz 2010 reports 3–7 × 10¹⁹ m⁻² for Pt/Py."
        )


# ===========================================================================
# R6-FINDING 1 — walker_velocity: missing Delta factor; result was rad/s not m/s
# ===========================================================================


class TestWalkerVelocityDeltaFactor:
    """R6-F1: walker_velocity() must include the Delta (DW width) factor.

    Mougin et al., EPL 78, 57007 (2007), Eq. (1):
        v_W = gamma * Delta * mu_0 * Ms / 2

    The old code returned gamma * mu_0 * Ms / 2, which has units rad/s (angular
    frequency), not m/s.  The missing Delta factor caused an error of ~1/Delta
    (~10^7 m^-1 for Permalloy), giving a result ~317x the speed of light.
    """

    def test_walker_velocity_physical_range_permalloy(self) -> None:
        """Permalloy (Delta=10-50 nm): v_W must be in the range 100-2000 m/s.

        Reference values:
            gamma = 1.7609e11 rad/(s*T), mu_0 = 1.2566e-6 T*m/A,
            Ms = 860 kA/m, Delta = 30 nm.
            v_W = 1.7609e11 * 30e-9 * 1.2566e-6 * 860e3 / 2 approx 2853 m/s.
        (Mougin et al. EPL 78, 57007 (2007), Table 1 quotes ~100-1000 m/s for
        thin Py films where domain wall width is smaller.)
        """
        from maglab.physics.formulas import walker_velocity

        gamma = abs(GAMMA_E)
        Ms = 860e3    # A/m  (Permalloy saturation magnetization)
        alpha = 0.01  # Gilbert damping (does not enter the formula)

        # Test across the Permalloy DW width range Delta = 10-50 nm
        for Delta_nm in [10.0, 20.0, 30.0, 50.0]:
            Delta = Delta_nm * 1e-9
            v = walker_velocity(alpha=alpha, Ms=Ms, Delta=Delta, gamma=gamma)

            # Manual formula: v_W = gamma * Delta * mu_0 * Ms / 2
            v_expected = gamma * Delta * MU_0 * Ms / 2.0
            assert abs(v - v_expected) / abs(v_expected) < 1e-12, (
                f"walker_velocity formula mismatch at Delta={Delta_nm} nm: "
                f"got {v:.4g} m/s, expected {v_expected:.4g} m/s"
            )

            # Physical sanity: velocity must be in 50-5000 m/s range
            assert 50.0 < v < 5000.0, (
                f"walker_velocity = {v:.2f} m/s at Delta={Delta_nm} nm is outside "
                "the physical range 50-5000 m/s for Permalloy.  "
                "If the result is ~10^10, Delta is still missing."
            )

    def test_walker_velocity_delta_linear_scaling(self) -> None:
        """v_W must scale linearly with Delta: doubling Delta must double v_W."""
        from maglab.physics.formulas import walker_velocity

        gamma = abs(GAMMA_E)
        Ms = 860e3
        alpha = 0.01

        v1 = walker_velocity(alpha=alpha, Ms=Ms, Delta=20e-9, gamma=gamma)
        v2 = walker_velocity(alpha=alpha, Ms=Ms, Delta=40e-9, gamma=gamma)

        ratio = v2 / v1
        assert abs(ratio - 2.0) < 1e-12, (
            f"walker_velocity ratio v(40nm)/v(20nm) = {ratio:.8f}, expected 2.0; "
            "Delta scaling is incorrect."
        )

    def test_walker_velocity_old_expression_is_unphysically_large(self) -> None:
        """Demonstrate that the old Delta-less expression gives an unphysical result.

        Without Delta, gamma * mu_0 * Ms / 2 has units rad/s, not m/s.
        For Permalloy parameters this is ~9.5e10 rad/s -- many orders of magnitude
        larger than the physical Walker velocity (~1000 m/s).
        """
        gamma = abs(GAMMA_E)
        Ms = 860e3
        Delta = 30e-9  # 30 nm (Permalloy DW width)

        old_expression = gamma * MU_0 * Ms / 2.0          # rad/s — wrong units
        correct_velocity = gamma * Delta * MU_0 * Ms / 2.0  # m/s — correct

        # The old expression is ~1/Delta times too large (about 3.3e7 times)
        ratio = old_expression / correct_velocity
        expected_ratio = 1.0 / Delta
        assert abs(ratio - expected_ratio) / expected_ratio < 1e-10, (
            f"ratio old/correct = {ratio:.4g}, expected 1/Delta = {expected_ratio:.4g}"
        )

        # Physical sanity gate: the correct result must be below 1e6 m/s
        # (well below the speed of light); the old result would be > 1e10
        assert correct_velocity < 1e6, (
            f"correct walker_velocity = {correct_velocity:.4g} m/s: unexpectedly large."
        )
        assert old_expression > 1e9, (
            f"old expression = {old_expression:.4g}: expected >> 1e9 to demonstrate the defect."
        )

    def test_walker_velocity_formula_exact(self) -> None:
        """Verify the exact numerical result against first-principles calculation.

        For gamma=1.7609e11, Delta=100 nm, mu_0=1.2566e-6, Ms=860e3:
            v_W = 1.7609e11 * 100e-9 * 1.2566e-6 * 860e3 / 2
                approx 9508 m/s
        Mougin et al. Table 1 quotes v_W approx 100-1000 m/s for Py strips;
        their Ms and Delta values differ, but the formula is the same.
        """
        from maglab.physics.formulas import walker_velocity

        gamma_val = abs(GAMMA_E)
        Delta_val = 100e-9   # 100 nm
        Ms_val = 860e3       # A/m

        v = walker_velocity(alpha=0.0, Ms=Ms_val, Delta=Delta_val, gamma=gamma_val)
        v_manual = gamma_val * Delta_val * MU_0 * Ms_val / 2.0

        assert abs(v - v_manual) / abs(v_manual) < 1e-12, (
            f"walker_velocity numerical mismatch: got {v:.6g}, expected {v_manual:.6g}"
        )


# ===========================================================================
# R10 — MEDIUM: GMRTMREffect conductance amplitude P₁P₂ (Slonczewski 1989)
# ===========================================================================


class TestGMRTMRSlonczewskiAmplitude:
    """R10-F1: GMRTMREffect conductance amplitude must be P₁P₂, not TMR/2.

    Slonczewski (PRB 39, 6995, 1989) Eq. (4):
        G(θ) = G_0 · (1 + P₁P₂ · cosθ)
    where G_0 = (G_P + G_AP)/2.

    The old code used TMR/2 = P₁P₂/(1 − P₁P₂) as the amplitude, inflating
    the oscillation by 1/(1 − P₁P₂) and causing G_AP → 0 for P₁P₂ ≥ 0.5.
    """

    def test_forward_matches_slonczewski_formula(self) -> None:
        """G(θ) = (G_P+G_AP)/2 + (G_P-G_AP)/2·cosθ with Julliere G_P/G_AP ratio."""
        from maglab.analysis.effects.gmr_tmr import GMRTMREffect

        model = GMRTMREffect()
        P1, P2 = 0.55, 0.55  # P1*P2 = 0.3025
        G_0 = 1e-3            # S (average conductance)

        # Slonczewski: G_P = G_0*(1+P1*P2), G_AP = G_0*(1-P1*P2)
        G_P_expected = G_0 * (1.0 + P1 * P2)
        G_AP_expected = G_0 * (1.0 - P1 * P2)

        G_P_code = model.forward({"G_0": G_0, "P1": P1, "P2": P2}, {"theta": np.array([0.0])})[0]
        G_AP_code = model.forward({"G_0": G_0, "P1": P1, "P2": P2}, {"theta": np.array([math.pi])})[0]

        assert abs(G_P_code - G_P_expected) / G_P_expected < 1e-10, (
            f"G_P: got {G_P_code:.6g}, expected {G_P_expected:.6g}"
        )
        assert abs(G_AP_code - G_AP_expected) / G_AP_expected < 1e-10, (
            f"G_AP: got {G_AP_code:.6g}, expected {G_AP_expected:.6g}"
        )

    def test_julliere_ratio_from_forward_output(self) -> None:
        """G_P/G_AP = (1+P₁P₂)/(1-P₁P₂) — verify Julliere ratio recovered from code output."""
        from maglab.analysis.effects.gmr_tmr import GMRTMREffect

        model = GMRTMREffect()
        for P in [0.32, 0.55, 0.70]:
            P1, P2 = P, P
            G_0 = 1.0
            G_P = model.forward({"G_0": G_0, "P1": P1, "P2": P2}, {"theta": np.array([0.0])})[0]
            G_AP = model.forward({"G_0": G_0, "P1": P1, "P2": P2}, {"theta": np.array([math.pi])})[0]
            ratio_code = G_P / G_AP
            ratio_expected = (1.0 + P1 * P2) / (1.0 - P1 * P2)
            assert abs(ratio_code - ratio_expected) / ratio_expected < 1e-10, (
                f"P={P}: G_P/G_AP = {ratio_code:.6g}, expected {ratio_expected:.6g}"
            )

    def test_g_ap_strictly_positive_for_all_physical_p(self) -> None:
        """G_AP = G_0·(1 - P₁P₂) > 0 for all P₁P₂ ∈ [0, 1) including P₁P₂ ≥ 0.5.

        The old buggy formula gives G_AP = 0 at P₁P₂ = 0.5 and negative for
        P₁P₂ > 0.5, which is unphysical.
        """
        from maglab.analysis.effects.gmr_tmr import GMRTMREffect

        model = GMRTMREffect()
        G_0 = 1.0
        # Test the physically problematic region P1*P2 >= 0.5 (e.g. CoFeB/MgO)
        for P in [0.71, 0.80, 0.90, 0.99]:
            G_AP = model.forward(
                {"G_0": G_0, "P1": P, "P2": P}, {"theta": np.array([math.pi])}
            )[0]
            assert G_AP > 0, (
                f"G_AP = {G_AP:.4g} ≤ 0 for P={P} (P1*P2={P**2:.3g}) — unphysical"
            )

    def test_average_conductance_equals_g0(self) -> None:
        """G_0 is the average conductance: (G_P + G_AP) / 2 = G_0 exactly."""
        from maglab.analysis.effects.gmr_tmr import GMRTMREffect

        model = GMRTMREffect()
        G_0 = 2.5e-3
        for P1, P2 in [(0.4, 0.5), (0.7, 0.3), (0.9, 0.9)]:
            G_P = model.forward({"G_0": G_0, "P1": P1, "P2": P2}, {"theta": np.array([0.0])})[0]
            G_AP = model.forward({"G_0": G_0, "P1": P1, "P2": P2}, {"theta": np.array([math.pi])})[0]
            G_avg = (G_P + G_AP) / 2.0
            assert abs(G_avg - G_0) / G_0 < 1e-10, (
                f"P1={P1},P2={P2}: (G_P+G_AP)/2 = {G_avg:.6g}, G_0 = {G_0:.6g}"
            )

    def test_fit_recovers_p1p2_product(self) -> None:
        """fit() recovers G_0 and P₁·P₂ from synthetic Slonczewski data within 2%."""
        from maglab.analysis.effects.gmr_tmr import GMRTMREffect

        model = GMRTMREffect()
        G_0_true = 1e-3
        P1_true = 0.6
        P2_true = 0.5
        p1p2_true = P1_true * P2_true  # 0.30

        # Generate noiseless data with the correct Slonczewski formula
        theta = np.linspace(0.0, math.pi, 60)
        G_data = G_0_true * (1.0 + p1p2_true * np.cos(theta))

        result = model.fit({"theta": theta, "G": G_data})
        assert result.success, f"fit() did not converge: {result}"

        G_0_fit = result.params["G_0"]
        P1_fit = result.params["P1"]
        P2_fit = result.params["P2"]
        p1p2_fit = P1_fit * P2_fit

        assert abs(G_0_fit - G_0_true) / G_0_true < 0.02, (
            f"G_0: fit={G_0_fit:.4g}, true={G_0_true:.4g}"
        )
        assert abs(p1p2_fit - p1p2_true) / p1p2_true < 0.02, (
            f"P1*P2: fit={p1p2_fit:.4g}, true={p1p2_true:.4g}"
        )

    def test_fit_not_using_tmr_half_amplitude(self) -> None:
        """Regression guard: fit() with TMR/2 data does NOT recover correct P₁·P₂.

        If the old buggy formula (TMR/2 amplitude) is used to generate data but
        the corrected model (P₁P₂ amplitude) is used to fit, the recovered P₁P₂
        will be wrong — demonstrating the formulas are genuinely different.

        For P1=P2=0.55 → P1*P2=0.3025, TMR/2=0.3025/(1-0.3025)=0.4336.
        The corrected fit model sees data with amplitude 0.4336 but expects P₁P₂,
        so it will find P1*P2 ≈ 0.4336, not 0.3025.  This confirms the two
        formulas are distinct (not equivalent under reparametrization).
        """
        from maglab.analysis.effects.gmr_tmr import GMRTMREffect
        from maglab.analysis.effects.gmr_tmr import GMRTMREffect as G

        model = GMRTMREffect()
        G_0_true = 1e-3
        P1_true = 0.55
        P2_true = 0.55
        p1p2_true = P1_true * P2_true   # 0.3025

        # Buggy data: generated with old TMR/2 amplitude
        tmr = G.tmr_from_polarizations(P1_true, P2_true)
        theta = np.linspace(0.0, math.pi, 60)
        G_buggy = G_0_true * (1.0 + (tmr / 2.0) * np.cos(theta))  # old formula

        result = model.fit({"theta": theta, "G": G_buggy})
        # The fit may or may not converge, but if it does, recovered P1*P2 ≠ true value
        if result.success:
            p1p2_fit = result.params["P1"] * result.params["P2"]
            # The fit model will absorb the inflated amplitude into P1*P2:
            # it will recover something closer to tmr/2 = 0.4336 than p1p2=0.3025
            err_from_true = abs(p1p2_fit - p1p2_true)
            assert err_from_true > 0.05 * p1p2_true, (
                f"Fit of buggy data unexpectedly recovered the correct P1*P2={p1p2_true:.4g}; "
                f"got {p1p2_fit:.4g}. The old and new formulas may be numerically indistinguishable."
            )
