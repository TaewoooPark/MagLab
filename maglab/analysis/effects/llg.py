"""LLG (+STT/SOT) EffectModel.

dm/dt = -γ₀(m×H_eff) + α(m×dm/dt) + τ_STT + τ_SOT
scipy ODE integration (RK45). Forward compute then extract observables.

Sources:
    Landau, L. D., Lifshitz, E. M., Phys. Z. Sowjetunion 8, 153 (1935).
    Gilbert, T. L., IEEE Trans. Magn. 40, 3443 (2004).
    Slonczewski, J. C., J. Magn. Magn. Mater. 159, L1 (1996).
"""

from __future__ import annotations

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


class LLGModel(EffectModel):
    """LLG (+STT/SOT) magnetization dynamics EffectModel.

    Landau-Lifshitz-Gilbert equation (+STT):
    dm/dt = −γ₀(m×H_eff) + α(m×dm/dt) + τ_DL·(m×m_p×m) + τ_FL·(m×m_p)

    Forward compute: ODE integration (RK45) → m(t).
    Fitting: compare with analytical solution for precession frequency and damping.

    Sources:
        Landau, L. D., Lifshitz, E. M., Phys. Z. Sowjetunion 8, 153 (1935).
        Gilbert, T. L., IEEE Trans. Magn. 40, 3443 (2004).
        DOI: 10.1109/TMAG.2004.836740
        Slonczewski, J. C., J. Magn. Magn. Mater. 159, L1 (1996).
        DOI: 10.1016/0304-8853(96)00062-5
    """

    @property
    def name(self) -> str:
        return "llg"

    @property
    def subfield(self) -> str:
        return "magnetization_dynamics"

    @property
    def references(self) -> list[str]:
        return [
            "Landau, L. D., Lifshitz, E. M., Phys. Z. Sowjetunion 8, 153 (1935).",
            "Gilbert, T. L., IEEE Trans. Magn. 40, 3443 (2004). DOI: 10.1109/TMAG.2004.836740",
            "Slonczewski, J. C., J. Magn. Magn. Mater. 159, L1 (1996). "
            "DOI: 10.1016/0304-8853(96)00062-5",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="alpha",
                unit="dimensionless",
                lower=1e-5,
                upper=1.0,
                description="Gilbert damping constant α",
            ),
            ParamSpec(
                name="tau_DL",
                unit="1/s",
                lower=None,
                upper=None,
                description="Damping-like STT/SOT torque magnitude τ_DL [s⁻¹]",
            ),
            ParamSpec(
                name="tau_FL",
                unit="1/s",
                lower=None,
                upper=None,
                description="Field-like STT/SOT torque magnitude τ_FL [s⁻¹]",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Macrospin model. Provide initial condition m_0 and H_eff. Compute m(t) via ODE integration."
            ),
            tensor_rank=2,
            required_columns=("t", "mx", "my", "mz"),
            notes="t [s]: time array. mx, my, mz: magnetization components (|m|=1 normalized).",
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"llg_always_valid": True}

    def _llg_rhs(
        self,
        t: float,
        m: np.ndarray,
        H_eff: np.ndarray,
        alpha: float,
        gamma_0: float,
        tau_DL: float,
        tau_FL: float,
        m_p: np.ndarray,
    ) -> np.ndarray:
        """LLG RHS: dm/dt = -γ₀/(1+α²) · [m×H + α·m×(m×H) + STT terms].

        Landau-Lifshitz form (with renormalized α):
        dm/dt = -γ_eff (m×H_eff) - α·γ_eff (m×m×H_eff)
        """
        gamma_eff = gamma_0 / (1.0 + alpha**2)
        # H_eff is in A/m; multiply by MU_0 to convert to T before the cross product.
        # LLG in SI: dm/dt = -γ·μ₀·(m×H_eff) + ...
        mxH = np.cross(m, MU_0 * H_eff)
        precession = -gamma_eff * mxH
        damping = -alpha * gamma_eff * np.cross(m, mxH)

        # STT/SOT terms (Slonczewski)
        mxmp = np.cross(m, m_p)
        stt_dl = tau_DL * np.cross(m, mxmp)  # damping-like
        stt_fl = tau_FL * mxmp  # field-like

        return precession + damping + stt_dl + stt_fl

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Integrate the LLG ODE and return the m(t) trajectory.

        Args:
            params: {"alpha": float, "tau_DL": float, "tau_FL": float}.
            geometry: {
                "t_span": (t0, tf) [s],
                "t_eval": ndarray [s] (optional),
                "m_0": ndarray shape (3,) (initial magnetization),
                "H_eff": ndarray shape (3,) or (N,3) [A/m],
                "m_p": ndarray shape (3,) (fixed-layer magnetization direction),
                "gamma_0": float (gyromagnetic ratio, default GAMMA_E),
            }.

        Returns:
            m(t) array of shape (N, 3).
        """
        alpha = params["alpha"]
        tau_DL = params.get("tau_DL", params.get("tau_DL", 0.0))
        tau_FL = params.get("tau_FL", params.get("tau_FL", 0.0))

        geo = geometry or {}
        t_span = geo.get("t_span", (0.0, 1e-9))
        t_eval = geo.get("t_eval", np.linspace(t_span[0], t_span[1], 200))
        m_0 = np.asarray(geo.get("m_0", [0.0, 0.0, 1.0]), dtype=float)
        H_eff = np.asarray(geo.get("H_eff", [0.0, 0.0, 1e4]), dtype=float)
        m_p = np.asarray(geo.get("m_p", [1.0, 0.0, 0.0]), dtype=float)
        gamma_0 = float(geo.get("gamma_0", abs(GAMMA_E)))

        # H_eff is constant (1D array)
        if H_eff.ndim == 1:
            H_const = H_eff

            def rhs(t: float, m: np.ndarray) -> np.ndarray:
                return self._llg_rhs(t, m, H_const, alpha, gamma_0, tau_DL, tau_FL, m_p)
        else:
            # Time-dependent H_eff: use first row (simplified)
            H_const = H_eff[0]

            def rhs(t: float, m: np.ndarray) -> np.ndarray:
                return self._llg_rhs(t, m, H_const, alpha, gamma_0, tau_DL, tau_FL, m_p)

        # max_step: 1/10 of precession period (ensures minimum integration step)
        duration = t_span[1] - t_span[0]
        H_mag = float(np.linalg.norm(H_const))
        if H_mag > 0:
            omega_max = gamma_0 * float(MU_0) * H_mag
            max_step = min(
                duration / 5.0 if duration > 0 else 1e-12,
                2.0 * np.pi / omega_max / 10.0,
            )
        else:
            max_step = duration / 100.0 if duration > 0 else 1e-12

        # Determine internal steps from number of t_eval points
        t_arr = np.asarray(t_eval)
        n_out = len(t_arr)

        # Fixed-step RK4 (fast and stable; sufficient for short integration intervals)
        n_steps = max(int((t_span[1] - t_span[0]) / max_step) + 1, 4 * n_out)
        t_internal = np.linspace(t_span[0], t_span[1], n_steps + 1)
        dt = t_internal[1] - t_internal[0]

        m_curr = m_0.copy().astype(float)
        result = np.zeros((n_out, 3), dtype=float)

        # Store initial condition exactly when t_eval[0] == t_span[0]
        out_idx = 0
        if n_out > 0 and t_arr[0] <= t_span[0] + 1e-15:
            result[0] = m_curr
            out_idx = 1

        for i, t_i in enumerate(t_internal[:-1]):
            # RK4
            k1 = rhs(t_i, m_curr)
            k2 = rhs(t_i + dt / 2, m_curr + dt / 2 * k1)
            k3 = rhs(t_i + dt / 2, m_curr + dt / 2 * k2)
            k4 = rhs(t_i + dt, m_curr + dt * k3)
            m_curr = m_curr + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
            # Maintain |m| = 1
            norm_m = np.linalg.norm(m_curr)
            if norm_m > 1e-12:
                m_curr /= norm_m
            # Collect t_eval points
            t_next = t_internal[i + 1]
            while out_idx < n_out and t_arr[out_idx] <= t_next + 1e-15:
                result[out_idx] = m_curr
                out_idx += 1

        # Fill remaining t_eval points
        while out_idx < n_out:
            result[out_idx] = m_curr
            out_idx += 1

        return result

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit α from m(t) data (τ_DL, τ_FL fixed at 0).

        Simplified fitting to extract damping constant from FMR precession.
        Uses the approximation m_z(t) = 1 - A·exp(-α·ω₀·t)·cos(ω₀·t).

        Args:
            data: {"t": ndarray, "mz": ndarray}.
            geometry: {"omega_0": float} (precession angular frequency, optional).

        Returns:
            FitResult.
        """
        t = data["t"]
        mz = data["mz"]
        omega_0 = float((geometry or {}).get("omega_0", 2.0 * np.pi * 10e9))

        # Only α is identifiable from the oscillatory ring-down m_z(t).
        # τ_DL and τ_FL do not appear in the model expression and are held
        # fixed at 0 (not fitted) to avoid a singular covariance matrix.
        alpha_spec = [p for p in self.parameters if p.name == "alpha"]

        def model_fn(x: np.ndarray, alpha: float) -> np.ndarray:
            # Oscillatory ring-down: mz(t) ≈ 1 - A·exp(-α·ω₀·t)·cos(ω₀·t)
            # Correct in the underdamped limit (α ≪ 1) which is the physical regime.
            mz_0 = float(mz[0]) if len(mz) > 0 else 0.8
            return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x) * np.cos(omega_0 * x)

        init = {"alpha": 0.01}
        fit_result = run_fit(
            model_fn=model_fn,
            x_data=t,
            y_data=mz,
            param_specs=alpha_spec,
            init_values=init,
            effect_name=self.name,
        )
        # Report tau_DL and tau_FL as fixed/not-fitted so FitResult is complete
        # but clearly marks them as not constrained by this measurement.
        fit_result.params.setdefault("tau_DL", 0.0)
        fit_result.params.setdefault("tau_FL", 0.0)
        fit_result.uncertainties.setdefault("tau_DL", 0.0)
        fit_result.uncertainties.setdefault("tau_FL", 0.0)
        return fit_result

    def precession_frequency(
        self,
        H_eff: float,
        Ms: float,
        gamma_0: float | None = None,
    ) -> float:
        """Compute free precession frequency f_0 (analytical solution).

        f_0 = γ₀ μ₀ H_eff / (2π)

        Args:
            H_eff: Effective magnetic field [A/m].
            Ms: Saturation magnetization [A/m].
            gamma_0: Gyromagnetic ratio [rad/(s·T)] (default GAMMA_E).

        Returns:
            f_0 [GHz].
        """
        g = gamma_0 if gamma_0 is not None else abs(GAMMA_E)
        return g * MU_0 * H_eff / (2.0 * np.pi) * 1e-9
