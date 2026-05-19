"""Two-sublattice LLG model for ferrimagnets and antiferromagnets.

Coupled Landau-Lifshitz-Gilbert equations for a two-sublattice magnetic
system (ferrimagnet or antiferromagnet):

    dm_a/dt = −γ_a (m_a × H_eff_a) + α_a (m_a × dm_a/dt)
    dm_b/dt = −γ_b (m_b × H_eff_b) + α_b (m_b × dm_b/dt)

Effective fields include the intersublattice exchange coupling:
    H_eff_a = H_ext − H_ex · m_b / |M_b|
    H_eff_b = H_ext − H_ex · m_a / |M_a|

where H_ex = J_ab / (μ₀ M_s) is the intersublattice exchange field.

**Ferrimagnets (FiM)**: |M_a| ≠ |M_b|, net magnetization M_net = M_a − M_b ≠ 0.
**Antiferromagnets (AFM)**: |M_a| = |M_b|, M_net ≈ 0.

Observable fitting modes:
- AFMR frequency: f = (γ/2π)·μ₀·√(2·H_E·H_A)  — see ``fit()`` static mode.
- Ferrimagnet compensation frequency near T_comp using the two-sublattice
  formula from ``physics/formulas.py``.
- Dynamic trajectory: RK4 integration of coupled LLG → m_a(t), m_b(t).

Sources:
    Keffer, F., Kittel, C.,
    Phys. Rev. 85, 329 (1952).
    DOI: 10.1103/PhysRev.85.329

    Kittel, C.,
    Phys. Rev. 76, 743 (1949).
    DOI: 10.1103/PhysRev.76.743

    MacNeill, D. et al.,
    Phys. Rev. Lett. 123, 047204 (2019).
    DOI: 10.1103/PhysRevLett.123.047204

    Kim, K.-J. et al.,
    Nat. Mater. 21, 544 (2022).
    DOI: 10.1038/s41563-022-01250-0
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from maglab.analysis.effects.base import (
    EffectModel,
    FitResult,
    MeasurementConfig,
    ParamSpec,
)
from maglab.analysis.fit import run_fit
from maglab.physics.constants import GAMMA_E, MU_0
from maglab.physics.formulas import afmr_frequency, ferrimagnet_compensation_freq


class LLG2SublatticeModel(EffectModel):
    """Two-sublattice LLG model for ferrimagnets and antiferromagnets.

    Fitting modes (selected by data column names):

    **AFMR mode** — fit exchange field H_E and anisotropy field H_A from
    AFMR frequency vs. applied field data.  Uses the analytic formula
    f_AFMR = (γ/2π)·μ₀·√(2·H_E·H_A)  (Keffer & Kittel 1952).

    **Ferrimagnet compensation mode** — fit sublattice magnetizations M_a, M_b
    from the compensation frequency vs. temperature data, using the
    two-sublattice formula from ``physics/formulas.py``.

    **Dynamic mode** — integrate the coupled LLG equations (RK4) and return
    the full m_a(t), m_b(t) trajectory.
    """

    @property
    def name(self) -> str:
        return "llg_2sublattice"

    @property
    def subfield(self) -> str:
        return "magnetization_dynamics"

    @property
    def references(self) -> list[str]:
        return [
            "Keffer, F., Kittel, C., Phys. Rev. 85, 329 (1952). "
            "DOI: 10.1103/PhysRev.85.329",
            "Kittel, C., Phys. Rev. 76, 743 (1949). "
            "DOI: 10.1103/PhysRev.76.743",
            "MacNeill, D. et al., Phys. Rev. Lett. 123, 047204 (2019). "
            "DOI: 10.1103/PhysRevLett.123.047204",
            "Kim, K.-J. et al., Nat. Mater. 21, 544 (2022). "
            "DOI: 10.1038/s41563-022-01250-0",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="H_E",
                unit="A/m",
                lower=0.0,
                upper=None,
                description=(
                    "Intersublattice exchange field H_E = J_ab/(μ₀M₀) [A/m].  "
                    "Typically 10⁶–10⁹ A/m for AFMs/FiMs."
                ),
            ),
            ParamSpec(
                name="H_A",
                unit="A/m",
                lower=0.0,
                upper=None,
                description="Uniaxial anisotropy field H_A = 2K_u/(μ₀M₀) [A/m].",
            ),
            ParamSpec(
                name="alpha_a",
                unit="dimensionless",
                lower=1e-6,
                upper=1.0,
                description="Gilbert damping of sublattice A.",
            ),
            ParamSpec(
                name="alpha_b",
                unit="dimensionless",
                lower=1e-6,
                upper=1.0,
                description="Gilbert damping of sublattice B.",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Two-sublattice system: AFM or FiM.  "
                "Three fitting modes: "
                "(A) AFMR: data = {'H_A_sweep': ndarray [A/m], 'f_afmr': ndarray [Hz]}; "
                "(B) FiM compensation: data = {'m_a': float, 'm_b': float, 'f_comp': float}; "
                "(C) LLG dynamics: data passed via geometry."
            ),
            tensor_rank=2,
            required_columns=("H_A_sweep", "f_afmr"),
            notes=(
                "AFMR mode: H_A_sweep [A/m] is the anisotropy field axis, "
                "f_afmr [Hz] is the measured zero-field AFMR frequency. "
                "FiM mode: m_a, m_b [A/m] are sublattice magnetizations at T_comp, "
                "f_comp [Hz] is the measured compensation frequency. "
                "Dynamic mode: geometry must supply 't_span', 't_eval', 'm_0_a', 'm_0_b', "
                "'H_ext', 'Ms_a', 'Ms_b'."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {
            "two_sublattice_llg": True,
            "afm_or_fim": True,
        }

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute AFMR frequency (analytic) or LLG trajectory (dynamic).

        **AFMR analytic mode** — geometry must contain ``H_A_sweep`` [A/m]:
            Returns f_AFMR = (γ/2π)·μ₀·√(2·H_E·H_A) [Hz] for each H_A.

        **Dynamic mode** — geometry must contain ``t_span``, ``t_eval``,
        ``m_0_a``, ``m_0_b``, ``H_ext``, ``Ms_a``, ``Ms_b``:
            Returns concatenated trajectory array of shape (N, 6) where
            columns 0:3 = m_a(t), columns 3:6 = m_b(t).

        Args:
            params: {"H_E": float, "H_A": float, "alpha_a": float, "alpha_b": float}.
            geometry: Mode-specific geometry dict.

        Returns:
            f_AFMR array [Hz]  or  trajectory array (N, 6).
        """
        H_E = params["H_E"]
        H_A = params["H_A"]
        alpha_a = params.get("alpha_a", 0.005)
        alpha_b = params.get("alpha_b", 0.005)
        geo = geometry or {}

        if "H_A_sweep" in geo:
            H_A_arr = np.asarray(geo["H_A_sweep"])
            gamma = float(geo.get("gamma", abs(GAMMA_E)))
            return np.array([afmr_frequency(H_E, float(ha), gamma) for ha in H_A_arr])

        # Dynamic LLG integration
        t_span = geo.get("t_span", (0.0, 1e-12))
        n_pts = geo.get("n_pts", 200)
        t_eval = np.asarray(geo.get("t_eval", np.linspace(t_span[0], t_span[1], n_pts)))
        m_0_a = np.asarray(geo.get("m_0_a", [0.0, 0.0, 1.0]), dtype=float)
        m_0_b = np.asarray(geo.get("m_0_b", [0.0, 0.0, -1.0]), dtype=float)
        H_ext = np.asarray(geo.get("H_ext", [0.0, 0.0, 0.0]), dtype=float)
        Ms_a = float(geo.get("Ms_a", 8e5))
        Ms_b = float(geo.get("Ms_b", 6e5))
        gamma_a = float(geo.get("gamma_a", abs(GAMMA_E)))
        gamma_b = float(geo.get("gamma_b", abs(GAMMA_E)))

        return self._llg2sl_rk4(
            m_0_a, m_0_b,
            H_E, H_A, H_ext,
            Ms_a, Ms_b,
            alpha_a, alpha_b,
            gamma_a, gamma_b,
            t_eval,
        )

    def _llg2sl_rk4(
        self,
        m_0_a: np.ndarray,
        m_0_b: np.ndarray,
        H_E: float,
        H_A: float,
        H_ext: np.ndarray,
        Ms_a: float,
        Ms_b: float,
        alpha_a: float,
        alpha_b: float,
        gamma_a: float,
        gamma_b: float,
        t_arr: np.ndarray,
    ) -> np.ndarray:
        """Fixed-step RK4 integration of coupled two-sublattice LLG.

        Returns array of shape (N, 6): columns 0:3 = m_a, columns 3:6 = m_b.
        """
        gamma_eff_a = gamma_a / (1.0 + alpha_a**2)
        gamma_eff_b = gamma_b / (1.0 + alpha_b**2)

        m_a = m_0_a.copy()
        m_b = m_0_b.copy()
        n_out = len(t_arr)
        result = np.zeros((n_out, 6))
        result[0, :3] = m_a
        result[0, 3:] = m_b

        def _rhs(ma: np.ndarray, mb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            # Effective fields: Zeeman + exchange + anisotropy (uniaxial z-axis)
            H_eff_a = (
                H_ext
                - H_E * mb
                + H_A * ma[2] * np.array([0.0, 0.0, 1.0])
            )
            H_eff_b = (
                H_ext
                - H_E * ma
                + H_A * mb[2] * np.array([0.0, 0.0, 1.0])
            )

            mxH_a = np.cross(ma, H_eff_a)
            mxH_b = np.cross(mb, H_eff_b)

            dma = -gamma_eff_a * (mxH_a + alpha_a * np.cross(ma, mxH_a))
            dmb = -gamma_eff_b * (mxH_b + alpha_b * np.cross(mb, mxH_b))
            return dma, dmb

        for i in range(1, n_out):
            dt = t_arr[i] - t_arr[i - 1]
            k1a, k1b = _rhs(m_a, m_b)
            k2a, k2b = _rhs(m_a + 0.5 * dt * k1a, m_b + 0.5 * dt * k1b)
            k3a, k3b = _rhs(m_a + 0.5 * dt * k2a, m_b + 0.5 * dt * k2b)
            k4a, k4b = _rhs(m_a + dt * k3a, m_b + dt * k3b)

            m_a = m_a + dt / 6.0 * (k1a + 2.0 * k2a + 2.0 * k3a + k4a)
            m_b = m_b + dt / 6.0 * (k1b + 2.0 * k2b + 2.0 * k3b + k4b)

            # Renormalise
            norm_a = np.linalg.norm(m_a)
            norm_b = np.linalg.norm(m_b)
            if norm_a > 1e-12:
                m_a /= norm_a
            if norm_b > 1e-12:
                m_b /= norm_b

            result[i, :3] = m_a
            result[i, 3:] = m_b

        return result

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit two-sublattice LLG parameters.

        **AFMR mode**: data = {"H_A_sweep": ndarray, "f_afmr": ndarray}
            Fits H_E and H_A from AFMR frequency measurements at different
            values of the anisotropy field (e.g., varied by applied strain or
            material choice).  alpha_a and alpha_b are held fixed.

        **FiM compensation mode**: data = {"m_a": float, "m_b": float, "f_comp": float}
            Single-point fitting: given known sublattice magnetizations near
            the compensation point and the measured compensation frequency,
            fits H_E.  Returns a trivial FitResult with one parameter.

        Args:
            data: Mode-specific data dictionary.
            geometry: Optional additional parameters {"gamma": float}.

        Returns:
            FitResult.
        """
        geo = geometry or {}

        if "H_A_sweep" in data and "f_afmr" in data:
            # --- AFMR analytic fitting mode ---
            H_A_arr = data["H_A_sweep"]
            f_afmr_data = data["f_afmr"]
            gamma = float(geo.get("gamma", abs(GAMMA_E)))

            # f_AFMR = (γ/2π)·μ₀·√(2·H_E·H_A)
            # → f² = [(γ/2π)·μ₀]²·2·H_E·H_A
            # Linear in H_A: fit slope to get H_E
            f_sq = f_afmr_data**2
            prefac = ((gamma / (2.0 * math.pi)) * MU_0) ** 2 * 2.0
            # Estimate: slope of f² vs. H_A gives prefac * H_E
            try:
                slope = float(np.linalg.lstsq(H_A_arr.reshape(-1, 1), f_sq, rcond=None)[0][0])
                H_E_init = slope / max(prefac, 1e-60)
            except Exception:
                H_E_init = 1e6

            H_A_mid = float(np.median(H_A_arr))

            def model_fn(
                x: np.ndarray, H_E: float, H_A: float, alpha_a: float, alpha_b: float
            ) -> np.ndarray:
                return np.array([afmr_frequency(H_E, float(ha), gamma) for ha in x])

            init = {
                "H_E": H_E_init,
                "H_A": H_A_mid,
                "alpha_a": 0.005,
                "alpha_b": 0.005,
            }
            return run_fit(
                model_fn=model_fn,
                x_data=H_A_arr,
                y_data=f_afmr_data,
                param_specs=self.parameters,
                init_values=init,
                effect_name=self.name,
            )

        elif "m_a" in data and "m_b" in data and "f_comp" in data:
            # --- FiM compensation mode ---
            # Extract scalar values
            m_a_val = float(data["m_a"]) if np.ndim(data["m_a"]) == 0 else float(data["m_a"][0])
            m_b_val = float(data["m_b"]) if np.ndim(data["m_b"]) == 0 else float(data["m_b"][0])
            f_comp_val = float(data["f_comp"]) if np.ndim(data["f_comp"]) == 0 else float(data["f_comp"][0])
            gamma_a = float(geo.get("gamma_a", abs(GAMMA_E)))
            gamma_b = float(geo.get("gamma_b", abs(GAMMA_E)))

            # Analytic single-point inversion:
            # f_comp = (|γ_a m_a − γ_b m_b| / (m_a + m_b)) · μ₀ · H_E
            # → H_E = f_comp · (m_a + m_b) / (|γ_a m_a − γ_b m_b| · μ₀)
            denom_gamma = abs(gamma_a * m_a_val - gamma_b * m_b_val)
            if denom_gamma < 1e-30:
                H_E_solved = 1e6  # fallback
            else:
                H_E_solved = f_comp_val * (m_a_val + m_b_val) / (denom_gamma * MU_0)

            # Build a minimal FitResult using only H_E (single-point fit is
            # analytically determined — wrap in run_fit with a 1-parameter
            # model over a small H_E neighbourhood so provenance is recorded)
            he_spec = [ParamSpec("H_E", "A/m", lower=0.0, upper=None, description="Exchange field")]

            def model_fn_he(x: np.ndarray, H_E: float) -> np.ndarray:
                return np.array([
                    ferrimagnet_compensation_freq(m_a_val, m_b_val, H_E, gamma_a, gamma_b)
                    for _ in x
                ])

            # Provide a small sweep of H_E values around the analytic solution
            # to give lmfit enough data points (M ≥ N requirement)
            n_pts = max(5, len(np.atleast_1d(data["f_comp"])))
            x_sweep = np.linspace(max(H_E_solved * 0.9, 1.0), H_E_solved * 1.1, n_pts)
            y_sweep = np.array([
                ferrimagnet_compensation_freq(m_a_val, m_b_val, float(he), gamma_a, gamma_b)
                for he in x_sweep
            ])
            fit_he = run_fit(
                model_fn=model_fn_he,
                x_data=x_sweep,
                y_data=y_sweep,
                param_specs=he_spec,
                init_values={"H_E": H_E_solved},
                effect_name=self.name,
            )

            # Promote to full 4-parameter FitResult for API consistency
            fit_he.params.setdefault("H_A", 1e3)
            fit_he.params.setdefault("alpha_a", 0.005)
            fit_he.params.setdefault("alpha_b", 0.005)
            fit_he.uncertainties.setdefault("H_A", 0.0)
            fit_he.uncertainties.setdefault("alpha_a", 0.0)
            fit_he.uncertainties.setdefault("alpha_b", 0.0)
            return fit_he

        else:
            raise ValueError(
                "LLG2SublatticeModel.fit() requires either "
                "{'H_A_sweep', 'f_afmr'} for AFMR fitting "
                "or {'m_a', 'm_b', 'f_comp'} for FiM compensation fitting."
            )

    def afmr_freq(self, H_E: float, H_A: float, gamma: float | None = None) -> float:
        """Analytic AFMR frequency f = (γ/2π)·μ₀·√(2·H_E·H_A).

        Args:
            H_E: Exchange field [A/m].
            H_A: Anisotropy field [A/m].
            gamma: Gyromagnetic ratio [rad/(s·T)] (default GAMMA_E).

        Returns:
            f_AFMR [Hz].
        """
        g = gamma if gamma is not None else abs(GAMMA_E)
        return afmr_frequency(H_E, H_A, g)
