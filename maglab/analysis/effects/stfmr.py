"""ST-FMR EffectModel.

V_mix = S·F_sym(H) + A·F_asym(H)
F_sym: symmetric Lorentzian (damping-like torque → S)
F_asym: antisymmetric Lorentzian (field-like torque → A)
Extract damping-like spin Hall angle ξ_DL from S/A ratio.

Sources:
    Liu, L. Q. et al.,
    Phys. Rev. Lett. 106, 036601 (2011).
    DOI: 10.1103/PhysRevLett.106.036601
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


def _lorentz_sym(H: np.ndarray, H_res: float, dH: float) -> np.ndarray:
    """Symmetric Lorentzian form: dH² / [(H − H_res)² + dH²]."""
    return dH**2 / ((H - H_res) ** 2 + dH**2)


def _lorentz_asym(H: np.ndarray, H_res: float, dH: float) -> np.ndarray:
    """Antisymmetric Lorentzian form: dH·(H − H_res) / [(H − H_res)² + dH²]."""
    return dH * (H - H_res) / ((H - H_res) ** 2 + dH**2)


class STFMREffect(EffectModel):
    """ST-FMR EffectModel.

    V_mix = S · F_sym(H; H_res, ΔH) + A · F_asym(H; H_res, ΔH)

    S: symmetric component amplitude (damping-like torque, τ_DL)
    A: antisymmetric component amplitude (field-like torque, τ_FL)
    H_res: resonance field [A/m or T]
    ΔH: half-linewidth [A/m or T]

    Spin Hall angle:
    ξ_DL = (S/A) · (eμ₀M_s t_FM t_NM / ħ)

    Sources:
        Liu, L. Q. et al., Phys. Rev. Lett. 106, 036601 (2011).
        DOI: 10.1103/PhysRevLett.106.036601
    """

    @property
    def name(self) -> str:
        return "stfmr"

    @property
    def subfield(self) -> str:
        return "spin_orbitronics"

    @property
    def references(self) -> list[str]:
        return [
            "Liu, L. Q. et al., "
            "Phys. Rev. Lett. 106, 036601 (2011). "
            "DOI: 10.1103/PhysRevLett.106.036601"
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="S",
                unit="V",
                lower=None,
                upper=None,
                description="Symmetric Lorentzian amplitude (damping-like SOT)",
            ),
            ParamSpec(
                name="A",
                unit="V",
                lower=None,
                upper=None,
                description="Antisymmetric Lorentzian amplitude (field-like SOT)",
            ),
            ParamSpec(
                name="H_res",
                unit="A/m",
                lower=0.0,
                upper=None,
                description="ST-FMR resonance field",
            ),
            ParamSpec(
                name="dH",
                unit="A/m",
                lower=1.0,
                upper=None,
                description="FMR half-linewidth ΔH (HWHM)",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "CPW (coplanar waveguide), RF current I_rf∥x. "
                "DC mixing voltage V_mix vs. external field H sweep."
            ),
            tensor_rank=2,
            required_columns=("H", "V_mix"),
            notes=("H [A/m or T]: external field sweep. V_mix [V]: rectified DC mixing voltage."),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"stfmr_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute V_mix = S·F_sym + A·F_asym.

        Args:
            params: {"S": float, "A": float, "H_res": float, "dH": float}.
            geometry: {"H": ndarray}.

        Returns:
            V_mix array.
        """
        S = params["S"]
        A = params["A"]
        H_res = params["H_res"]
        dH = params["dH"]
        H = geometry["H"] if geometry and "H" in geometry else np.array([H_res])
        return S * _lorentz_sym(H, H_res, dH) + A * _lorentz_asym(H, H_res, dH)

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit S, A, H_res, ΔH from V_mix(H) data.

        If ``geometry`` provides material parameters ``Ms``, ``t_FM``, and
        ``t_NM``, the damping-like spin Hall angle ξ_DL is computed from the
        fitted S/A ratio and stored in ``FitResult.params["xi_DL"]``.

        Args:
            data: {"H": ndarray, "V_mix": ndarray}.
            geometry: Optional dict with material parameters for ξ_DL derivation:
                {"Ms": float [A/m], "t_FM": float [m], "t_NM": float [m]}.

        Returns:
            FitResult with params {"S", "A", "H_res", "dH"} and optionally
            {"xi_DL"} if geometry supplies Ms, t_FM, t_NM.
        """
        H = data["H"]
        V_mix = data["V_mix"]

        # Initial values: position of maximum → H_res, half-width → ΔH
        idx_max = int(np.argmax(np.abs(V_mix)))
        H_res_init = float(H[idx_max])
        # Estimate HWHM: location where V drops to half
        v_half = np.abs(V_mix[idx_max]) / 2.0
        above_half = np.where(np.abs(V_mix) >= v_half)[0]
        if len(above_half) > 1:
            dH_init = float(abs(H[above_half[-1]] - H[above_half[0]]) / 2.0)
        else:
            dH_init = float(np.ptp(H) / 10.0)
        dH_init = max(dH_init, 1.0)

        S_init = float(np.max(V_mix))
        A_init = float(np.max(np.abs(V_mix)) * 0.3)

        init = {"S": S_init, "A": A_init, "H_res": H_res_init, "dH": dH_init}

        def model_fn(x: np.ndarray, S: float, A: float, H_res: float, dH: float) -> np.ndarray:
            return S * _lorentz_sym(x, H_res, dH) + A * _lorentz_asym(x, H_res, dH)

        fit_result = run_fit(
            model_fn=model_fn,
            x_data=H,
            y_data=V_mix,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )

        # --- Derive xi_DL if material geometry is provided ---
        geo = geometry or {}
        if "Ms" in geo and "t_FM" in geo and "t_NM" in geo:
            Ms = float(geo["Ms"])
            t_FM = float(geo["t_FM"])
            t_NM = float(geo["t_NM"])
            S_fit = fit_result.params["S"]
            A_fit = fit_result.params["A"]
            try:
                xi_DL = self.spin_hall_angle(S_fit, A_fit, Ms, t_FM, t_NM)
                fit_result.params["xi_DL"] = xi_DL
            except (ValueError, ZeroDivisionError):
                fit_result.params["xi_DL"] = float("nan")

        return fit_result

    @staticmethod
    def spin_hall_angle(
        S: float,
        A: float,
        Ms: float,
        t_FM: float,
        t_NM: float,
        mu_0: float = 1.25663706212e-6,
        hbar: float = 1.054571817e-34,
        e: float = 1.602176634e-19,
    ) -> float:
        """Compute damping-like spin Hall angle ξ_DL from S/A ratio.

        ξ_DL = (S/A) · (eμ₀M_s t_FM t_NM / ħ)

        Args:
            S: Symmetric component amplitude [V].
            A: Antisymmetric component amplitude [V].
            Ms: Saturation magnetization [A/m].
            t_FM: FM layer thickness [m].
            t_NM: NM layer thickness [m].

        Returns:
            Damping-like spin Hall angle ξ_DL [dimensionless].
        """
        if abs(A) < 1e-30:
            raise ValueError("A ≈ 0: cannot compute spin Hall angle.")
        return (S / A) * (e * mu_0 * Ms * t_FM * t_NM / hbar)
