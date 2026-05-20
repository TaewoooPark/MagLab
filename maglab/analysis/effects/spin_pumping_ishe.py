"""Spin pumping/ISHE EffectModel.

FMR linewidth enhancement → spin mixing conductance g↑↓ extraction.
Compute ISHE voltage: V_ISHE = θ_SH·λ_sf·tanh(d/(2λ_sf))·ρ·j_s·w

Sources:
    Mizukami, S. et al.,
    Jpn. J. Appl. Phys. 40, 580 (2001).
    DOI: 10.1143/JJAP.40.580

    Mosendz, O. et al.,
    Phys. Rev. B 82, 214403 (2010).
    DOI: 10.1103/PhysRevB.82.214403
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
from maglab.physics.constants import GAMMA_E, HBAR


class SpinPumpingISHE(EffectModel):
    """Spin pumping/ISHE EffectModel.

    FMR linewidth enhancement formula:
    Δα = (γ ħ g↑↓) / (4π M_s d_FM)
    → Extract g↑↓ from FMR linewidth vs. NM thickness.

    ISHE voltage:
    V_ISHE = θ_SH · λ_sf · tanh(d_NM / (2λ_sf)) · ρ_NM · j_s · w_sample

    Sources:
        Mizukami, S. et al., Jpn. J. Appl. Phys. 40, 580 (2001).
        Mosendz, O. et al., Phys. Rev. B 82, 214403 (2010).
        DOI: 10.1103/PhysRevB.82.214403
    """

    @property
    def name(self) -> str:
        return "spin_pumping_ishe"

    @property
    def subfield(self) -> str:
        return "spin_orbitronics"

    @property
    def references(self) -> list[str]:
        return [
            "Mizukami, S. et al., Jpn. J. Appl. Phys. 40, 580 (2001). DOI: 10.1143/JJAP.40.580",
            "Mosendz, O. et al., Phys. Rev. B 82, 214403 (2010). DOI: 10.1103/PhysRevB.82.214403",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="g_eff",
                unit="m^-2",
                lower=0.0,
                upper=None,
                description="Effective spin mixing conductance g↑↓ [m⁻²]",
            ),
            ParamSpec(
                name="alpha_0",
                unit="dimensionless",
                lower=0.0,
                upper=1.0,
                description="Intrinsic FM Gilbert damping (without NM layer)",
            ),
            ParamSpec(
                name="lambda_sf",
                unit="m",
                lower=1e-12,
                upper=None,
                description="Spin diffusion length λ_sf [m] of the NM layer",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "FMR frequency or NM thickness-dependent linewidth measurement. HM/FM bilayer, FMR linewidth ΔH vs. d_NM."
            ),
            tensor_rank=2,
            required_columns=("d_NM", "delta_alpha"),
            notes=(
                "d_NM [m]: NM layer thickness array. delta_alpha [dimensionless]: Δα extracted from FMR linewidth enhancement."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"ishe_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute Δα(d_NM) = γħg↑↓ / (4π M_s·d_FM) · tanh(d_NM / (2λ_sf)).

        Full thickness-dependent formula including spin backflow (Mosendz 2010):
            Δα(d_NM) = (γħg↑↓)/(4π·M_s·d_FM) · tanh(d_NM / (2λ_sf))

        This varies with d_NM and saturates for d_NM ≫ λ_sf.

        Args:
            params: {"g_eff": float, "alpha_0": float, "lambda_sf": float}.
            geometry: {"d_NM": ndarray [m], "Ms": float [A/m], "d_FM": float [m]}.

        Returns:
            Total α = alpha_0 + Δα(d_NM) array, same shape as d_NM.
        """
        g_eff = params["g_eff"]
        alpha_0 = params["alpha_0"]
        lambda_sf = params.get("lambda_sf", 5e-9)
        Ms = float(geometry.get("Ms", 8e5)) if geometry else 8e5
        d_FM = float(geometry.get("d_FM", 5e-9)) if geometry else 5e-9
        d_NM = np.asarray(
            geometry.get("d_NM", np.array([5e-9])) if geometry else np.array([5e-9]),
            dtype=float,
        )

        gamma_rad = abs(GAMMA_E)  # rad/(s·T)
        # Mosendz et al., PRB 82, 214403 (2010), Eq. (2):
        # Δα = γ·ħ·g↑↓ / (4π·Ms·d_FM)   — no μ₀ in denominator.
        prefactor = (gamma_rad * HBAR * g_eff) / (4.0 * np.pi * Ms * d_FM)
        delta_alpha = prefactor * np.tanh(d_NM / (2.0 * lambda_sf))
        return alpha_0 + delta_alpha

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit g↑↓, alpha_0 from d_NM·Δα data.

        Args:
            data: {"d_NM": ndarray, "delta_alpha": ndarray}.
            geometry: {"Ms": float, "d_FM": float}.

        Returns:
            FitResult.
        """
        d_NM = data["d_NM"]
        delta_alpha = data["delta_alpha"]
        Ms = float((geometry or {}).get("Ms", 8e5))
        d_FM = float((geometry or {}).get("d_FM", 5e-9))
        gamma_rad = abs(GAMMA_E)

        # Mosendz et al., PRB 82, 214403 (2010), Eq. (2): no μ₀ in denominator.
        prefactor = (gamma_rad * HBAR) / (4.0 * np.pi * Ms * d_FM)

        def model_fn(x: np.ndarray, g_eff: float, alpha_0: float, lambda_sf: float) -> np.ndarray:
            return alpha_0 + prefactor * g_eff * np.tanh(x / (2.0 * lambda_sf))

        # Initial values: saturated Δα estimate for g_init; lambda_sf = 5 nm typical
        da_max = float(np.max(delta_alpha - np.min(delta_alpha)))
        g_init = max(da_max / prefactor, 1e17) if prefactor > 0 else 1e18
        init = {"g_eff": g_init, "alpha_0": float(np.min(delta_alpha)), "lambda_sf": 5e-9}

        return run_fit(
            model_fn=model_fn,
            x_data=d_NM,
            y_data=delta_alpha,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )

    @staticmethod
    def v_ishe(
        theta_SH: float,
        lambda_sf: float,
        d_NM: float,
        rho_NM: float,
        j_s: float,
        w: float,
    ) -> float:
        """Compute ISHE voltage.

        V_ISHE = θ_SH · λ_sf · tanh(d_NM / (2λ_sf)) · ρ_NM · j_s · w

        Args:
            theta_SH: Spin Hall angle.
            lambda_sf: Spin diffusion length [m].
            d_NM: NM layer thickness [m].
            rho_NM: NM layer resistivity [Ohm·m].
            j_s: Spin current density [A/m²].
            w: Sample width [m].

        Returns:
            V_ISHE [V].
        """
        return theta_SH * lambda_sf * np.tanh(d_NM / (2.0 * lambda_sf)) * rho_NM * j_s * w
