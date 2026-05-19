"""TYJ scaling EffectModel (Tian-Ye-Jin AHE scaling).

Fitting equation: ρ_AHE = a·ρ_xx0 + b·ρ_xx²
a: extrinsic contribution (skew scattering + side jump)
b: intrinsic Berry phase contribution

Sources:
    Tian, Y., Ye, L., Jin, X., Phys. Rev. Lett. 103, 087206 (2009).
    DOI: 10.1103/PhysRevLett.103.087206
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


class TYJScaling(EffectModel):
    """TYJ AHE scaling EffectModel.

    ρ_AHE = a·ρ_xx0 + b·ρ_xx²

    a: extrinsic coefficient (skew scattering, linear ρ_xx0 term)
    b: intrinsic coefficient (Berry phase, quadratic ρ_xx² term)
    Input temperature-dependent (ρ_xx(T), ρ_AHE(T)) pairs → fit a, b.

    Sources:
        Tian, Y., Ye, L., Jin, X.,
        Phys. Rev. Lett. 103, 087206 (2009).
        DOI: 10.1103/PhysRevLett.103.087206
    """

    @property
    def name(self) -> str:
        return "tyj_scaling"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return [
            "Tian, Y., Ye, L., Jin, X., "
            "Phys. Rev. Lett. 103, 087206 (2009). "
            "DOI: 10.1103/PhysRevLett.103.087206"
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="a",
                unit="dimensionless",
                lower=None,
                upper=None,
                description="Extrinsic AHE coefficient (skew scattering + side jump, linear ρ_xx term)",
            ),
            ParamSpec(
                name="b",
                unit="1/Ohm/m",
                lower=None,
                upper=None,
                description="Intrinsic AHE coefficient (Berry phase, quadratic ρ_xx² term)",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Temperature-variable measurement: record (ρ_xx, ρ_AHE) pairs at multiple temperatures. "
                "ρ_AHE is the value after subtracting OHE background at saturation field."
            ),
            tensor_rank=2,
            required_columns=("rho_xx", "rho_AHE"),
            notes=(
                "rho_xx [Ohm·m]: longitudinal resistivity. "
                "rho_AHE [Ohm·m]: anomalous Hall resistivity (after OHE subtraction). "
                "Input as a single (rho_xx, rho_AHE) pair array even for multiple temperatures."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"ahe_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute ρ_AHE = a·ρ_xx + b·ρ_xx².

        Args:
            params: {"a": float, "b": float}.
            geometry: {"rho_xx": ndarray}.

        Returns:
            ρ_AHE array.
        """
        a = params["a"]
        b = params["b"]
        rho_xx = geometry["rho_xx"] if geometry and "rho_xx" in geometry else np.array([0.0])
        return a * rho_xx + b * rho_xx**2

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit a, b from (ρ_xx, ρ_AHE) pairs.

        Args:
            data: {"rho_xx": ndarray, "rho_AHE": ndarray}.
            geometry: Additional geometry info (optional).

        Returns:
            FitResult.
        """
        rho_xx = data["rho_xx"]
        rho_AHE = data["rho_AHE"]

        # Initial values via linear regression: X = [rho_xx, rho_xx²]
        X = np.column_stack([rho_xx, rho_xx**2])
        try:
            coeffs = np.linalg.lstsq(X, rho_AHE, rcond=None)[0]
            init = {"a": float(coeffs[0]), "b": float(coeffs[1])}
        except Exception:
            init = {"a": 0.01, "b": 1e6}

        def model_fn(x: np.ndarray, a: float, b: float) -> np.ndarray:
            return a * x + b * x**2

        return run_fit(
            model_fn=model_fn,
            x_data=rho_xx,
            y_data=rho_AHE,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
