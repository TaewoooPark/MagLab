"""Anisotropic Magnetoresistance (AMR) EffectModel.

Fitting equation: ρ(θ) = ρ_perp + Δρ_AMR·cos²θ
Parameters: ρ_perp (transverse resistivity), Δρ_AMR (AMR anisotropy magnitude)

Sources:
    McGuire, T. R., Potter, R. I.,
    IEEE Trans. Magn. 11, 1018 (1975).
    DOI: 10.1109/TMAG.1975.1058782
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
from maglab.analysis.symmetry import is_amr_allowed


class AMREffect(EffectModel):
    """Anisotropic Magnetoresistance EffectModel.

    ρ(θ) = ρ_⊥ + Δρ_AMR·cos²θ

    θ: angle between current direction and magnetization direction [rad]
    ρ_⊥: resistivity when magnetization ⊥ current [Ohm·m]
    Δρ_AMR = ρ_∥ - ρ_⊥: AMR anisotropy magnitude [Ohm·m]

    AMR ratio: AMR(%) = Δρ_AMR / ρ_⊥ × 100

    Sources:
        McGuire, T. R., Potter, R. I.,
        IEEE Trans. Magn. 11, 1018 (1975).
        DOI: 10.1109/TMAG.1975.1058782
    """

    def __init__(self, point_group: str = "m3m") -> None:
        self._point_group = point_group

    @property
    def name(self) -> str:
        return "amr"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return [
            "McGuire, T. R., Potter, R. I., "
            "IEEE Trans. Magn. 11, 1018 (1975). "
            "DOI: 10.1109/TMAG.1975.1058782"
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="rho_perp",
                unit="Ohm*m",
                lower=0.0,
                upper=None,
                description="Resistivity when magnetization is perpendicular to current",
            ),
            ParamSpec(
                name="delta_rho",
                unit="Ohm*m",
                lower=None,
                upper=None,
                description="AMR anisotropy magnitude Δρ = ρ_∥ - ρ_⊥",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=("Hall bar, in-plane magnetization angle θ rotation (0~2π). I∥x, longitudinal voltage V_x measured."),
            tensor_rank=2,
            required_columns=("theta", "rho_xx"),
            notes="theta [rad]: angle between current and magnetization. rho_xx [Ohm·m]: longitudinal resistivity.",
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        amr_ok = is_amr_allowed(self._point_group)
        return {
            "amr_allowed": amr_ok,
            "point_group": self._point_group,
        }

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute ρ(θ) = ρ_⊥ + Δρ·cos²θ.

        Args:
            params: {"rho_perp": float, "delta_rho": float}.
            geometry: {"theta": ndarray} (angle [rad]).

        Returns:
            ρ(θ) array.
        """
        rho_perp = params["rho_perp"]
        delta_rho = params["delta_rho"]
        theta = geometry["theta"] if geometry and "theta" in geometry else np.array([0.0])
        return rho_perp + delta_rho * np.cos(theta) ** 2

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit ρ_⊥, Δρ from θ-sweep ρ_xx(θ) data.

        Args:
            data: {"theta": ndarray, "rho_xx": ndarray}.
            geometry: Additional geometry info (optional).

        Returns:
            FitResult.
        """
        theta = data["theta"]
        rho_xx = data["rho_xx"]

        # Check symmetry-forbidden components
        sym = self.symmetry_constraints
        if not sym.get("amr_allowed", True):
            # Fix delta_rho = 0 when symmetry-forbidden
            from maglab.analysis.effects.base import FitResult

            return FitResult(
                params={"rho_perp": float(np.mean(rho_xx)), "delta_rho": 0.0},
                uncertainties={"rho_perp": 0.0, "delta_rho": 0.0},
                chi2=0.0,
                reduced_chi2=0.0,
                covariance=np.zeros((2, 2)),
                effect_name=self.name,
                message="Symmetry constraint: delta_rho fixed to 0.",
            )

        cos2 = np.cos(theta) ** 2
        X = np.column_stack([np.ones_like(theta), cos2])
        try:
            coeffs = np.linalg.lstsq(X, rho_xx, rcond=None)[0]
            init = {"rho_perp": float(coeffs[0]), "delta_rho": float(coeffs[1])}
        except Exception:
            init = {"rho_perp": float(np.mean(rho_xx)), "delta_rho": 1e-9}

        def model_fn(x: np.ndarray, rho_perp: float, delta_rho: float) -> np.ndarray:
            return rho_perp + delta_rho * np.cos(x) ** 2

        return run_fit(
            model_fn=model_fn,
            x_data=theta,
            y_data=rho_xx,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
