"""Macrospin (Stoner-Wohlfarth) single-domain model with STT/SOT.

The macrospin model treats the ferromagnetic free layer as a rigid, uniformly
magnetised single-domain particle (Stoner-Wohlfarth assumption).  Dynamics
are governed by the scalar energy landscape under uniaxial anisotropy plus
applied fields and STT/SOT torques.

**Static Stoner-Wohlfarth switching** (astroid, coercive field):
    E(θ) = K_u·V·sin²θ − μ₀·M_s·V·H·cos(θ − θ_H)
    Switching field: H_sw(θ_H) = H_k / [(cos²θ_H)^(2/3) + (sin²θ_H)^(2/3)]^(3/2)
    where H_k = 2K_u / (μ₀ M_s) — anisotropy field.

**Dynamic trajectory** (LLG RK4, macrospin limit):
    dm/dt = −γ₀(m×H_eff) + α(m×dm/dt) + τ_DL·(m×m_p×m) + τ_FL·(m×m_p)

This model is the canonical single-domain approximation used to extract
anisotropy, damping, and SOT efficiency from switching experiments.

Sources:
    Stoner, E. C., Wohlfarth, E. P.,
    Philos. Trans. R. Soc. London Ser. A 240, 599 (1948).
    DOI: 10.1098/rsta.1948.0007

    Slonczewski, J. C.,
    J. Magn. Magn. Mater. 159, L1 (1996).
    DOI: 10.1016/0304-8853(96)00062-5

    Sun, J. Z.,
    Phys. Rev. B 62, 570 (2000).
    DOI: 10.1103/PhysRevB.62.570
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


class MacrospinModel(EffectModel):
    """Stoner-Wohlfarth macrospin model with STT/SOT.

    Attributes supported by ``forward()``:
    - Static SW switching field H_sw(θ_H) from the anisotropy astroid.
    - Dynamic m(t) trajectory via RK4 LLG integration.

    ``fit()`` recovers the anisotropy field H_k from a measured switching-
    field astroid or from a single-axis switching field measurement.  If
    time-series data (t, mz) are provided, α is fitted instead.

    Physical model:
        H_k = 2 K_u / (μ₀ M_s)
        H_sw(θ_H=0) = H_k  [easy-axis]
        H_sw(θ_H=45°) = H_k / 2  [hard-axis limit of SW astroid]
    """

    @property
    def name(self) -> str:
        return "macrospin"

    @property
    def subfield(self) -> str:
        return "magnetization_dynamics"

    @property
    def references(self) -> list[str]:
        return [
            "Stoner, E. C., Wohlfarth, E. P., "
            "Philos. Trans. R. Soc. London Ser. A 240, 599 (1948). "
            "DOI: 10.1098/rsta.1948.0007",
            "Slonczewski, J. C., J. Magn. Magn. Mater. 159, L1 (1996). "
            "DOI: 10.1016/0304-8853(96)00062-5",
            "Sun, J. Z., Phys. Rev. B 62, 570 (2000). DOI: 10.1103/PhysRevB.62.570",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="H_k",
                unit="A/m",
                lower=0.0,
                upper=None,
                description=(
                    "Uniaxial anisotropy field H_k = 2K_u/(μ₀M_s) [A/m].  "
                    "Equal to the easy-axis switching field H_sw(θ_H=0)."
                ),
            ),
            ParamSpec(
                name="alpha",
                unit="dimensionless",
                lower=1e-6,
                upper=1.0,
                description="Gilbert damping constant α.",
            ),
            ParamSpec(
                name="tau_DL",
                unit="1/s",
                lower=None,
                upper=None,
                description="Damping-like STT/SOT torque magnitude [s⁻¹].",
            ),
            ParamSpec(
                name="tau_FL",
                unit="1/s",
                lower=None,
                upper=None,
                description="Field-like STT/SOT torque magnitude [s⁻¹].",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Single-domain FM free layer.  Two fitting modes: "
                "(A) Switching-field astroid: H_sw vs. θ_H — provide 'theta_H' and 'H_sw' columns. "
                "(B) LLG time-series: m_z(t) decay — provide 't' and 'mz' columns."
            ),
            tensor_rank=2,
            required_columns=("theta_H", "H_sw"),
            notes=(
                "theta_H [rad]: applied field angle from easy axis. "
                "H_sw [A/m]: measured switching field at each angle. "
                "For time-series mode: t [s], mz [dimensionless]."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"macrospin_uniaxial": True}

    @staticmethod
    def sw_switching_field(H_k: float, theta_H: np.ndarray) -> np.ndarray:
        """Stoner-Wohlfarth switching field astroid.

        H_sw(θ_H) = H_k / [(cos²θ_H)^(2/3) + (sin²θ_H)^(2/3)]^(3/2)

        This is the exact analytic solution for a uniaxial single-domain
        particle in an applied field at angle θ_H from the easy axis.

        Args:
            H_k: Anisotropy field H_k = 2K_u/(μ₀M_s) [A/m].
            theta_H: Field angle from easy axis [rad], shape (N,).

        Returns:
            H_sw array [A/m].
        """
        cos2 = np.cos(theta_H) ** 2
        sin2 = np.sin(theta_H) ** 2
        denom = (cos2 ** (2.0 / 3.0) + sin2 ** (2.0 / 3.0)) ** (3.0 / 2.0)
        # Guard against θ_H = 0 or π/2 (numerically safe)
        denom = np.where(denom < 1e-30, 1e-30, denom)
        return H_k / denom

    def _llg_rk4(
        self,
        m_0: np.ndarray,
        H_eff: np.ndarray,
        alpha: float,
        tau_DL: float,
        tau_FL: float,
        m_p: np.ndarray,
        t_arr: np.ndarray,
    ) -> np.ndarray:
        """Fixed-step RK4 LLG integration (macrospin).

        Uses an internal oversampled time grid to ensure at least 10 steps
        per precession period at the applied field (matching LLGModel.forward()).

        Returns m(t) array of shape (N, 3) where N = len(t_arr).
        """
        gamma_eff = abs(GAMMA_E) / (1.0 + alpha**2)
        m_curr = m_0.copy().astype(float)
        n_out = len(t_arr)
        result = np.zeros((n_out, 3))

        def rhs(m: np.ndarray) -> np.ndarray:
            # H_eff is in A/m; multiply by MU_0 to convert to T.
            # LLG in SI: dm/dt = -γ·μ₀·(m×H_eff) + ...
            mxH = np.cross(m, MU_0 * H_eff)
            precession = -gamma_eff * mxH
            damping = -alpha * gamma_eff * np.cross(m, mxH)
            mxmp = np.cross(m, m_p)
            stt_dl = tau_DL * np.cross(m, mxmp)
            stt_fl = tau_FL * mxmp
            return precession + damping + stt_dl + stt_fl

        # Build internal oversampled grid: at least 10 steps per precession period
        t_start = float(t_arr[0])
        t_end = float(t_arr[-1])
        H_mag = float(np.linalg.norm(H_eff))
        if H_mag > 0:
            omega_max = abs(GAMMA_E) * float(MU_0) * H_mag
            max_step = min(
                (t_end - t_start) / 5.0 if t_end > t_start else 1e-12,
                2.0 * np.pi / omega_max / 10.0,
            )
        else:
            max_step = (t_end - t_start) / 100.0 if t_end > t_start else 1e-12

        n_internal = (
            max(int((t_end - t_start) / max_step) + 1, 4 * n_out) if t_end > t_start else n_out
        )
        t_internal = np.linspace(t_start, t_end, n_internal + 1)
        dt_int = t_internal[1] - t_internal[0] if n_internal > 0 else 0.0

        # Store initial condition exactly at t_arr[0]
        result[0] = m_curr
        out_idx = 1

        for i in range(len(t_internal) - 1):
            if dt_int == 0.0:
                break
            k1 = rhs(m_curr)
            k2 = rhs(m_curr + 0.5 * dt_int * k1)
            k3 = rhs(m_curr + 0.5 * dt_int * k2)
            k4 = rhs(m_curr + dt_int * k3)
            m_curr = m_curr + dt_int / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
            norm = np.linalg.norm(m_curr)
            if norm > 1e-12:
                m_curr /= norm
            # Collect requested output points that fall within this step
            t_next = t_internal[i + 1]
            while out_idx < n_out and t_arr[out_idx] <= t_next + 1e-15:
                result[out_idx] = m_curr
                out_idx += 1

        # Fill any remaining output points
        while out_idx < n_out:
            result[out_idx] = m_curr
            out_idx += 1

        return result

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute macrospin observable.

        Two modes (determined by the keys in ``geometry``):

        **Astroid mode** — geometry must contain ``theta_H`` [rad]:
            Returns H_sw(θ_H) array [A/m] (Stoner-Wohlfarth switching field).

        **LLG dynamics mode** — geometry must contain ``t_span``, ``t_eval``,
            ``m_0``, ``H_eff``, ``m_p``:
            Returns m(t) array of shape (N, 3).

        Args:
            params: {"H_k": float, "alpha": float, "tau_DL": float, "tau_FL": float}.
            geometry: Mode-specific keys (see above).

        Returns:
            H_sw array [A/m]  or  m(t) array (N, 3).
        """
        H_k = params["H_k"]
        alpha = params.get("alpha", 0.01)
        tau_DL = params.get("tau_DL", 0.0)
        tau_FL = params.get("tau_FL", 0.0)
        geo = geometry or {}

        if "theta_H" in geo:
            theta_H = np.asarray(geo["theta_H"])
            return self.sw_switching_field(H_k, theta_H)

        # LLG dynamics mode
        t_span = geo.get("t_span", (0.0, 1e-9))
        n_pts = geo.get("n_pts", 200)
        t_eval = np.asarray(geo.get("t_eval", np.linspace(t_span[0], t_span[1], n_pts)))
        m_0 = np.asarray(geo.get("m_0", [0.1, 0.0, 0.995]))
        H_eff = np.asarray(geo.get("H_eff", [0.0, 0.0, H_k]))
        m_p = np.asarray(geo.get("m_p", [1.0, 0.0, 0.0]))

        return self._llg_rk4(m_0, H_eff, alpha, tau_DL, tau_FL, m_p, t_eval)

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit macrospin parameters from switching-field astroid or LLG time-series.

        **Astroid mode**: data = {"theta_H": ndarray, "H_sw": ndarray}
            Fits H_k via the Stoner-Wohlfarth formula.  alpha, tau_DL, tau_FL
            are held at 0 (not observable from static astroid).

        **Time-series mode**: data = {"t": ndarray, "mz": ndarray}
            Fits alpha from m_z(t) relaxation.  H_k must be supplied in
            geometry["H_k"] or defaults to 1e5 A/m.

        Args:
            data: {"theta_H": ndarray, "H_sw": ndarray}
                  or {"t": ndarray, "mz": ndarray}.
            geometry: Optional additional parameters.

        Returns:
            FitResult.
        """
        geo = geometry or {}

        if "theta_H" in data and "H_sw" in data:
            # --- Astroid fitting mode ---
            theta_H = data["theta_H"]
            H_sw_data = data["H_sw"]

            # Initial estimate: at θ_H = 0, H_sw ≈ H_k
            idx_easy = int(np.argmax(H_sw_data))
            H_k_init = float(H_sw_data[idx_easy])

            # Only H_k is identifiable from a static switching-field astroid.
            # alpha, tau_DL, tau_FL are dynamic quantities; keeping them as free
            # parameters produces a degenerate covariance (they do not appear in
            # sw_switching_field).  Fit only H_k; report the rest as fixed.
            hk_spec = [p for p in self.parameters if p.name == "H_k"]

            def model_fn(x: np.ndarray, H_k: float) -> np.ndarray:
                return self.sw_switching_field(H_k, x)

            init = {"H_k": H_k_init}
            fit_result = run_fit(
                model_fn=model_fn,
                x_data=theta_H,
                y_data=H_sw_data,
                param_specs=hk_spec,
                init_values=init,
                effect_name=self.name,
            )
            # Report non-fitted parameters as fixed defaults in FitResult.
            fit_result.params.setdefault("alpha", 0.01)
            fit_result.params.setdefault("tau_DL", 0.0)
            fit_result.params.setdefault("tau_FL", 0.0)
            fit_result.uncertainties.setdefault("alpha", 0.0)
            fit_result.uncertainties.setdefault("tau_DL", 0.0)
            fit_result.uncertainties.setdefault("tau_FL", 0.0)
            return fit_result

        elif "t" in data and "mz" in data:
            # --- Time-series damping fitting mode ---
            t = data["t"]
            mz = data["mz"]
            H_k_fixed = float(geo.get("H_k", 1e5))  # A/m
            omega_0 = abs(GAMMA_E) * MU_0 * H_k_fixed

            # Only α is identifiable from the ring-down signal.  H_k is held
            # fixed (supplied via geometry); tau_DL and tau_FL do not enter the
            # model expression and are reported as fixed defaults to avoid a
            # singular covariance matrix.
            alpha_spec = [p for p in self.parameters if p.name == "alpha"]

            def model_fn_t(x: np.ndarray, alpha: float) -> np.ndarray:
                mz_0 = float(mz[0]) if len(mz) > 0 else 0.8
                # Oscillatory FMR ring-down: m_z(t) = 1 - A·exp(-α·ω₀·t)·cos(ω₀·t)
                return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x) * np.cos(omega_0 * x)

            init = {"alpha": 0.01}
            fit_result = run_fit(
                model_fn=model_fn_t,
                x_data=t,
                y_data=mz,
                param_specs=alpha_spec,
                init_values=init,
                effect_name=self.name,
            )
            # Report non-fitted parameters as fixed defaults in FitResult.
            fit_result.params.setdefault("H_k", H_k_fixed)
            fit_result.params.setdefault("tau_DL", 0.0)
            fit_result.params.setdefault("tau_FL", 0.0)
            fit_result.uncertainties.setdefault("H_k", 0.0)
            fit_result.uncertainties.setdefault("tau_DL", 0.0)
            fit_result.uncertainties.setdefault("tau_FL", 0.0)
            return fit_result

        else:
            raise ValueError(
                "MacrospinModel.fit() requires either "
                "{'theta_H', 'H_sw'} for astroid fitting "
                "or {'t', 'mz'} for time-series damping fitting."
            )

    def anisotropy_field(self, K_u: float, Ms: float) -> float:
        """Return the anisotropy field H_k = 2K_u / (μ₀·M_s).

        Args:
            K_u: Uniaxial anisotropy constant [J/m³].
            Ms: Saturation magnetization [A/m].

        Returns:
            H_k [A/m].
        """
        return 2.0 * K_u / (MU_0 * Ms)
