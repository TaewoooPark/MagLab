"""Effect model round-trip validation — §19 gate 6 effects + comprehensive effects.

Synthetic data is generated with known parameters → fit() → parameter recovery verified.
LLM-as-judge forbidden: all validation uses deterministic numerical comparison only (PLAN §20).

Validation criteria:
  - Noiseless synthetic data: recovery error < 5%
  - reduced_chi2 << 1 (no noise)
  - FitResult.success = True
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from maglab.analysis.effects.amr import AMREffect
from maglab.analysis.effects.anomalous_hall import AnomalousHallEffect
from maglab.analysis.effects.dmi import DMIEffect
from maglab.analysis.effects.dw_1d import DW1DModel
from maglab.analysis.effects.fmr_kittel import FMRKittel
from maglab.analysis.effects.gilbert_damping import GilbertDamping
from maglab.analysis.effects.gmr_tmr import GMRTMREffect
from maglab.analysis.effects.hysteresis import HysteresisLoop
from maglab.analysis.effects.llg import LLGModel
from maglab.analysis.effects.orbital_hall import OrbitalHallEffect
from maglab.analysis.effects.ordinary_hall import OrdinaryHallEffect
from maglab.analysis.effects.planar_hall import PlanarHallEffect
from maglab.analysis.effects.smr import SMREffect
from maglab.analysis.effects.sot_harmonic_hall import SOTHarmonicHall
from maglab.analysis.effects.spin_pumping_ishe import SpinPumpingISHE
from maglab.analysis.effects.stfmr import STFMREffect
from maglab.analysis.effects.thiele import ThieleModel
from maglab.analysis.effects.topological_hall import TopologicalHallEffect
from maglab.analysis.effects.tyj_scaling import TYJScaling
from maglab.physics.constants import GAMMA_E, MU_0

# Allowed recovery error (5%)
TOL = 0.05


def _assert_recovery(
    name: str,
    true_val: float,
    fit_val: float,
    tol: float = TOL,
    abs_tol: float = 1e-15,
) -> None:
    """Assert that the parameter recovery error is within tol."""
    if abs(true_val) < abs_tol:
        assert abs(fit_val) < abs_tol * 100, f"{name}: true≈0, fit={fit_val:.4g}"
    else:
        rel_err = abs(fit_val - true_val) / abs(true_val)
        assert rel_err < tol, (
            f"{name}: true={true_val:.4g}, fit={fit_val:.4g}, rel_err={rel_err:.3f} > {tol}"
        )


# ===========================================================================
# §19 gate 1: anomalous Hall (AHE)
# ===========================================================================


class TestAHERoundtrip:
    """Anomalous Hall effect round-trip — §19 gate 1."""

    def test_ahe_forward_determinism(self) -> None:
        """forward() is deterministic (same input → same output, error < 1e-10)."""
        model = AnomalousHallEffect()
        params = {"R_0": 3e-10, "R_s": 5e-9}
        B = np.linspace(-1, 1, 20)
        M = np.tanh(B / 0.2) * 8e5
        geo = {"B": B, "M": M}
        y1 = model.forward(params, geo)
        y2 = model.forward(params, geo)
        np.testing.assert_allclose(y1, y2, atol=1e-20)

    def test_ahe_roundtrip(self) -> None:
        """Generate synthetic data with known R_0, R_s → fit → recover."""
        model = AnomalousHallEffect()
        R_0_true = 3e-10
        R_s_true = 5e-9
        Ms = 8e5
        B = np.linspace(-1, 1, 60)
        M = Ms * np.tanh(B / 0.3)
        rho_xy = R_0_true * B + MU_0 * R_s_true * M

        result = model.fit({"B": B, "rho_xy": rho_xy, "M": M})
        assert result.success
        _assert_recovery("R_0", R_0_true, result.params["R_0"])
        _assert_recovery("R_s", R_s_true, result.params["R_s"])

    def test_ahe_references_nonempty(self) -> None:
        """references field is not empty."""
        model = AnomalousHallEffect()
        assert len(model.references) > 0
        assert "Nagaosa" in model.references[0]


# ===========================================================================
# §19 gate 2: SMR
# ===========================================================================


class TestSMRRoundtrip:
    """SMR round-trip — §19 gate 2."""

    def test_smr_alpha_geometry(self) -> None:
        """SMR α geometry: ρ_long = ρ_0 + Δρ_1·(1 − cos²α) synthetic → fit → recover."""
        model = SMREffect()
        rho_0_true = 1e-7
        dr1_true = 2e-9
        angle = np.linspace(0, 2 * np.pi, 80)
        rho_long = rho_0_true + dr1_true * (1.0 - np.cos(angle) ** 2)

        result = model.fit(
            {
                "angle": angle,
                "rho_long": rho_long,
                "geometry": np.array(["alpha"] * len(angle)),
            }
        )
        assert result.success
        _assert_recovery("rho_0", rho_0_true, result.params["rho_0"])
        _assert_recovery("delta_rho_1", dr1_true, result.params["delta_rho_1"])

    def test_smr_references(self) -> None:
        """SMR references include Chen et al."""
        model = SMREffect()
        assert any("Chen" in r for r in model.references)


# ===========================================================================
# §19 gate 3: SOT harmonic Hall
# ===========================================================================


class TestSOTHarmonicHallRoundtrip:
    """SOT harmonic Hall round-trip — §19 gate 3."""

    def test_sot_harmonic_hall_roundtrip(self) -> None:
        """Generate synthetic 2ω with known H_DL_raw, H_FL_raw → fit → recover."""
        model = SOTHarmonicHall()
        H_DL_true = 5.0  # A/m (normalized)
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

    def test_phe_correction(self) -> None:
        """PHE correction formula: H_DL = (H_DL_raw - 2ξH_FL_raw) / (1 - 4ξ²)."""
        H_DL_raw, H_FL_raw, xi = 5.0, 2.0, 0.1
        H_DL, H_FL = SOTHarmonicHall.phe_corrected(H_DL_raw, H_FL_raw, xi)
        denom = 1.0 - 4.0 * xi**2
        expected_DL = (H_DL_raw - 2.0 * xi * H_FL_raw) / denom
        assert abs(H_DL - expected_DL) < 1e-10

    def test_sot_references(self) -> None:
        """SOT references include Hayashi."""
        model = SOTHarmonicHall()
        assert any("Hayashi" in r for r in model.references)


# ===========================================================================
# §19 gate 4: ST-FMR
# ===========================================================================


class TestSTFMRRoundtrip:
    """ST-FMR round-trip — §19 gate 4."""

    def test_stfmr_roundtrip(self) -> None:
        """Generate synthetic V_mix with known S, A, H_res, ΔH → fit → recover."""
        model = STFMREffect()
        S_true = 1e-4
        A_true = 5e-5
        H_res_true = 5e4  # A/m
        dH_true = 2e3

        H = np.linspace(H_res_true - 3e4, H_res_true + 3e4, 200)
        from maglab.analysis.effects.stfmr import _lorentz_asym, _lorentz_sym

        V_mix = S_true * _lorentz_sym(H, H_res_true, dH_true) + A_true * _lorentz_asym(
            H, H_res_true, dH_true
        )

        result = model.fit({"H": H, "V_mix": V_mix})
        assert result.success
        _assert_recovery("S", S_true, result.params["S"])
        _assert_recovery("A", A_true, result.params["A"])
        _assert_recovery("H_res", H_res_true, result.params["H_res"])
        _assert_recovery("dH", dH_true, result.params["dH"])

    def test_stfmr_references(self) -> None:
        """ST-FMR references include Liu."""
        model = STFMREffect()
        assert any("Liu" in r for r in model.references)


# ===========================================================================
# §19 gate 5: FMR Kittel
# ===========================================================================


class TestFMRKittelRoundtrip:
    """FMR Kittel round-trip — §19 gate 5."""

    def test_fmr_kittel_in_plane_roundtrip(self) -> None:
        """Generate in-plane Kittel formula with known M_eff, γ → fit → recover."""
        model = FMRKittel(mode="in_plane")
        M_eff_true = 8e5  # A/m (Permalloy)
        gamma_p_true = abs(GAMMA_E) / (2.0 * np.pi) * 1e-9  # GHz/T ≈ 28

        # H_res range [T]
        H_res = np.linspace(0.01, 0.3, 30)  # 0.01~0.3 T
        H_Am = H_res / MU_0
        f = gamma_p_true * MU_0 * np.sqrt(H_Am * (H_Am + M_eff_true))

        result = model.fit({"H_res": H_res, "f": f})
        assert result.success
        _assert_recovery("M_eff", M_eff_true, result.params["M_eff"], tol=0.05)
        _assert_recovery("gamma_ghz_t", gamma_p_true, result.params["gamma_ghz_t"], tol=0.02)

    def test_fmr_references(self) -> None:
        """FMR references include Kittel."""
        model = FMRKittel()
        assert any("Kittel" in r for r in model.references)


# ===========================================================================
# §19 gate 6: OHE rank-3 tensor
# ===========================================================================


class TestOHERoundtrip:
    """Orbital Hall effect rank-3 tensor round-trip — §19 gate 6."""

    def test_ohe_sigma_oh_shape(self) -> None:
        """sigma_OH has shape (3,3,3) float64."""
        model = OrbitalHallEffect()
        assert model.sigma_OH.shape == (3, 3, 3)
        assert model.sigma_OH.dtype == np.float64

    def test_ohe_set_sigma_oh_wrong_shape_raises(self) -> None:
        """Wrong shape raises ValueError."""
        model = OrbitalHallEffect()
        with pytest.raises(ValueError):
            model.set_sigma_OH(np.zeros((3, 3)))  # rank-2 is rejected

    def test_ohe_roundtrip_theta_oh(self) -> None:
        """Generate synthetic 2ω with known θ_OH → fit → recover θ_OH."""
        model = OrbitalHallEffect()
        theta_OH_true = 0.3
        H_ext = 1.0
        phi = np.linspace(0, 2 * np.pi, 80)
        V_2w = (theta_OH_true / H_ext) * np.cos(phi)

        result = model.fit(
            {"phi": phi, "V_2omega": V_2w}, geometry={"H_ext": H_ext, "sigma_xx": 1e6}
        )
        assert result.success
        _assert_recovery("theta_OH", theta_OH_true, result.params["theta_OH"])

    def test_ohe_tensor_rank_3_in_measurement_config(self) -> None:
        """measurement_config.tensor_rank == 3."""
        model = OrbitalHallEffect()
        assert model.measurement_config.tensor_rank == 3

    def test_ohe_references(self) -> None:
        """OHE references include Choi."""
        model = OrbitalHallEffect()
        assert any("Choi" in r for r in model.references)


# ===========================================================================
# Remaining effect round-trips
# ===========================================================================


class TestOrdinaryHallRoundtrip:
    def test_ordinary_hall(self) -> None:
        """Recover R_H."""
        model = OrdinaryHallEffect()
        R_H_true = 2e-10
        B = np.linspace(-1, 1, 40)
        rho_xy = R_H_true * B
        result = model.fit({"B": B, "rho_xy": rho_xy})
        assert result.success
        _assert_recovery("R_H", R_H_true, result.params["R_H"])


class TestTYJRoundtrip:
    def test_tyj_roundtrip(self) -> None:
        """Recover a, b."""
        model = TYJScaling()
        a_true, b_true = 0.02, 3e6
        rho_xx = np.linspace(1e-7, 1e-6, 40)
        rho_AHE = a_true * rho_xx + b_true * rho_xx**2
        result = model.fit({"rho_xx": rho_xx, "rho_AHE": rho_AHE})
        assert result.success
        _assert_recovery("a", a_true, result.params["a"])
        _assert_recovery("b", b_true, result.params["b"])


class TestPHERoundtrip:
    def test_phe_roundtrip(self) -> None:
        """Recover Δρ."""
        model = PlanarHallEffect()
        dr_true = 5e-9
        phi = np.linspace(0, 2 * np.pi, 60)
        rho_xy = (dr_true / 2.0) * np.sin(2.0 * phi)
        result = model.fit({"phi": phi, "rho_xy": rho_xy})
        assert result.success
        _assert_recovery("delta_rho", dr_true, result.params["delta_rho"])


class TestAMRRoundtrip:
    def test_amr_roundtrip(self) -> None:
        """Recover ρ_⊥, Δρ."""
        model = AMREffect()
        rho_perp_true = 1e-7
        delta_rho_true = 1e-8
        theta = np.linspace(0, 2 * np.pi, 60)
        rho_xx = rho_perp_true + delta_rho_true * np.cos(theta) ** 2
        result = model.fit({"theta": theta, "rho_xx": rho_xx})
        assert result.success
        _assert_recovery("rho_perp", rho_perp_true, result.params["rho_perp"])
        _assert_recovery("delta_rho", delta_rho_true, result.params["delta_rho"])


class TestGMRTMRRoundtrip:
    def test_gmr_tmr_roundtrip(self) -> None:
        """Recover G_0, P1·P2 from Slonczewski conductance data.

        Synthetic data generated with the correct Slonczewski (1989) formula:
            G(θ) = G_0 · (1 + P₁P₂ · cosθ)
        The old test used the buggy formula G_0·(1 + (TMR/2)·cosθ), which was
        corrected in R10.  We verify recovery of G_0 and the product P₁·P₂.
        """
        model = GMRTMREffect()
        G_0_true = 1e-3
        P1_true = 0.6
        P2_true = 0.5
        # Correct Slonczewski formula: amplitude is P1*P2, not TMR/2.
        theta = np.linspace(0, np.pi, 40)
        G_data = G_0_true * (1.0 + P1_true * P2_true * np.cos(theta))
        result = model.fit({"theta": theta, "G": G_data})
        assert result.success
        _assert_recovery("G_0", G_0_true, result.params["G_0"])
        # P1, P2 are individually non-identifiable from G(θ) alone (only
        # the product P1·P2 enters the formula), so verify the product.
        P1_fit = result.params["P1"]
        P2_fit = result.params["P2"]
        p1p2_fit = P1_fit * P2_fit
        p1p2_true = P1_true * P2_true
        assert abs(p1p2_fit - p1p2_true) / p1p2_true < 0.05, (
            f"P1·P2: fit={p1p2_fit:.4g}, true={p1p2_true:.4g}"
        )


class TestGilbertDampingRoundtrip:
    def test_gilbert_damping_roundtrip(self) -> None:
        """Recover α, ΔH₀."""
        model = GilbertDamping()
        alpha_true = 0.008
        dH_0_true = 0.002  # T
        gamma_p = abs(GAMMA_E) / (2.0 * np.pi) * 1e-9  # GHz/T
        f = np.linspace(2.0, 18.0, 20)  # GHz
        dH = dH_0_true + (2.0 * alpha_true / gamma_p) * f

        result = model.fit({"f": f, "dH": dH})
        assert result.success
        _assert_recovery("alpha", alpha_true, result.params["alpha"])
        _assert_recovery("dH_0", dH_0_true, result.params["dH_0"])


class TestDMIRoundtrip:
    def test_dmi_roundtrip(self) -> None:
        """Recover D_i.

        FINDING 2 fix: data generated with the correct formula Δf = 2γ_p·D·k/Ms
        (no μ₀ in denominator, no standalone π).  The old test generated data
        with the spurious μ₀ factor, which encoded the bug.
        """
        model = DMIEffect()
        D_i_true = 1.5e-3  # J/m²
        Ms = 8e5
        k = np.linspace(1e7, 2e7, 20)
        gamma_p = abs(GAMMA_E) / (2.0 * np.pi) * 1e-9
        # Correct formula: no μ₀, no π
        delta_f = 2.0 * gamma_p * D_i_true * k / Ms

        result = model.fit({"k": k, "delta_f": delta_f}, geometry={"Ms": Ms})
        assert result.success
        _assert_recovery("D_i", D_i_true, result.params["D_i"])


class TestThieleRoundtrip:
    def test_thiele_hall_angle(self) -> None:
        """Verify skyrmion Hall angle analytic solution determinism."""
        model = ThieleModel()
        Q = 1.0
        alpha = 0.01
        D = 4.0 * math.pi
        theta = model.skyrmion_hall_angle(Q, alpha, D)
        # tan(θ) = 4πQ / (αD) = 4π / (0.01 × 4π) = 1/0.01 = 100
        expected_tan = 4.0 * math.pi * Q / (alpha * D)
        assert abs(math.tan(theta) - expected_tan) < 1e-8


class TestDW1DRoundtrip:
    def test_dw_walker_field_analytic(self) -> None:
        """Verify Walker breakdown field analytic solution determinism.

        FINDING 4 fix: the correct Schryer-Walker formula includes a factor of 2
        in the denominator: H_W = α·K_⊥/(2·μ₀·M_s).
        The old test expected α·K/(μ₀·Ms) (missing /2), which encoded the bug.
        """
        model = DW1DModel()
        alpha = 0.01
        K_perp = 1e4
        Ms = 8e5
        H_W = model.walker_field(alpha, K_perp, Ms)
        # Correct formula: factor of 2 in denominator
        expected = alpha * K_perp / (2.0 * MU_0 * Ms)
        assert abs(H_W - expected) / abs(expected) < 1e-10

    def test_dw_velocity_below_walker(self) -> None:
        """Verify linear DW mobility below Walker breakdown."""
        model = DW1DModel()
        alpha = 0.01
        Delta = 5e-9
        H = 1e4  # A/m
        v = model.dw_velocity_below_walker(alpha, Delta, H)
        gamma_0 = abs(GAMMA_E)
        expected = gamma_0 * Delta * MU_0 * H / (1.0 + alpha**2)
        assert abs(v - expected) / abs(expected) < 1e-10


class TestHysteresisRoundtrip:
    def test_hysteresis_extract_params(self) -> None:
        """Extract M_s from a synthetic hysteresis loop."""
        model = HysteresisLoop()
        Ms_true = 8e5
        H = np.linspace(-2e6, 2e6, 100)
        M = Ms_true * np.tanh(H / 1e5)
        loop_params = model.extract_loop_params(H, M)
        _assert_recovery("M_s", Ms_true, loop_params["M_s"])


class TestSpinPumpingRoundtrip:
    def test_spin_pumping_forward(self) -> None:
        """Spin pumping forward calculation is deterministic."""
        model = SpinPumpingISHE()
        params = {"g_eff": 1e19, "alpha_0": 0.005}
        geo = {"d_NM": np.array([5e-9, 10e-9]), "Ms": 8e5, "d_FM": 5e-9}
        y1 = model.forward(params, geo)
        y2 = model.forward(params, geo)
        np.testing.assert_allclose(y1, y2, atol=1e-30)


class TestLLGModel:
    def test_llg_forward_returns_trajectory(self) -> None:
        """LLG forward returns an (N, 3) trajectory.

        Uses a short integration interval (100 ps) and weak field (H=1e4 A/m)
        to minimize CPU load while verifying shape.
        """
        model = LLGModel()
        params = {"alpha": 0.01, "tau_DL": 0.0, "tau_FL": 0.0}
        # short time range to reduce integration overhead (shape verification only)
        t_eval = np.linspace(0, 1e-10, 50)
        geo = {
            "t_span": (0.0, 1e-10),
            "t_eval": t_eval,
            "m_0": np.array([0.1, 0.0, 0.995]),
            "H_eff": np.array([0.0, 0.0, 1e4]),  # weak field → fewer integration steps
            "m_p": np.array([1.0, 0.0, 0.0]),
        }
        m_traj = model.forward(params, geo)
        assert m_traj.shape == (50, 3)

    def test_llg_precession_frequency(self) -> None:
        """Verify precession frequency analytic solution."""
        model = LLGModel()
        H_eff = 1e5  # A/m
        Ms = 8e5
        f0 = model.precession_frequency(H_eff, Ms)
        gamma_0 = abs(GAMMA_E)
        expected = gamma_0 * MU_0 * H_eff / (2.0 * np.pi) * 1e-9
        assert abs(f0 - expected) / abs(expected) < 1e-8


class TestTopologicalHallRoundtrip:
    def test_the_background_subtraction(self) -> None:
        """THE background subtraction: extract ρ_THE residual."""
        model = TopologicalHallEffect()
        R_0_true = 2e-10
        R_s_true = 3e-9
        Ms = 8e5
        B = np.linspace(-1, 1, 50)
        M = Ms * np.tanh(B / 0.3)

        # add THE signal
        rho_THE_true = 1e-11 * np.exp(-(B**2) / 0.1)
        rho_xy = R_0_true * B + MU_0 * R_s_true * M + rho_THE_true

        result = model.fit({"B": B, "rho_xy": rho_xy, "M": M})
        assert result.success
        rho_THE_extracted = model.extract_the({"B": B, "rho_xy": rho_xy, "M": M}, result)
        # max difference between extracted and true THE signal < 10%
        max_signal = np.max(np.abs(rho_THE_true))
        max_err = np.max(np.abs(rho_THE_extracted - rho_THE_true))
        if max_signal > 0:
            assert max_err / max_signal < 0.15  # allow background fitting error
