"""Ordinary Hall Effect (OHE) EffectModel.

Fitting equation: ρ_xy = R_H · B,  R_H = 1/(n·q)
Parameters: R_H [m³/C] (ordinary Hall coefficient)

Sources:
    Kittel, C., *Introduction to Solid State Physics*, 8th ed.
    (John Wiley & Sons, 2005), Ch. 6.
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
from maglab.physics.constants import E_CHARGE


class OrdinaryHallEffect(EffectModel):
    """Ordinary Hall Effect EffectModel.

    ρ_xy = R_H · B
    R_H = 1/(n·q), n = carrier density [m⁻³], q = charge [C].

    Sources:
        Kittel, C., *Introduction to Solid State Physics*, 8th ed.
        (Wiley, 2005), Ch. 6.
    """

    @property
    def name(self) -> str:
        return "ordinary_hall"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return ["Kittel, C., Introduction to Solid State Physics, 8th ed., Wiley (2005), Ch. 6."]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="R_H",
                unit="m^3/C",
                lower=None,
                upper=None,
                description="Ordinary Hall coefficient (positive = hole carriers, negative = electron carriers)",
            )
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry="Hall bar, I∥x, B∥z, V_y measurement (6-terminal Hall bar configuration)",
            tensor_rank=2,
            required_columns=("B", "rho_xy"),
            notes="B: external magnetic field in z-direction [T], rho_xy: Hall resistivity [Ohm·m].",
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"ahe_allowed": False, "note": "OHE has no symmetry constraint"}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute ρ_xy = R_H · B.

        Args:
            params: {"R_H": float} (Hall coefficient [m³/C]).
            geometry: {"B": np.ndarray} (magnetic field array [T]).

        Returns:
            ρ_xy array.
        """
        R_H = params["R_H"]
        B = geometry["B"] if geometry and "B" in geometry else np.array([0.0])
        return R_H * B

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Recover R_H from ρ_xy(B) data via linear fitting.

        Args:
            data: {"B": magnetic field array, "rho_xy": Hall resistivity array}.
            geometry: Additional geometry info (optional).

        Returns:
            FitResult (R_H, uncertainty, chi2).
        """
        B = data["B"]
        rho_xy = data["rho_xy"]

        def model_fn(x: np.ndarray, R_H: float) -> np.ndarray:
            return R_H * x

        init = {"R_H": float(np.polyfit(B, rho_xy, 1)[0])}

        return run_fit(
            model_fn=model_fn,
            x_data=B,
            y_data=rho_xy,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )

    def carrier_density(self, R_H: float) -> float:
        """Compute carrier density n from R_H.

        n = 1/(|R_H| · e)

        Args:
            R_H: Ordinary Hall coefficient [m³/C].

        Returns:
            Carrier density [m⁻³].
        """
        return 1.0 / (abs(R_H) * E_CHARGE)
