"""Topological Hall Effect (THE) EffectModel.

Fitting equation: ρ_THE = ρ_xy − R_0·B − μ₀·R_s·M
Extract residual after subtracting background (OHE + AHE).

Sources:
    Neubauer, A. et al.,
    Phys. Rev. Lett. 102, 186602 (2009).
    DOI: 10.1103/PhysRevLett.102.186602
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
from maglab.physics.constants import MU_0


class TopologicalHallEffect(EffectModel):
    """Topological Hall Effect EffectModel.

    ρ_THE = ρ_xy − R_0·B − μ₀·R_s·M

    Subtract the background (ordinary Hall + anomalous Hall) to extract the THE signal.
    R_0, R_s can be obtained in advance from AHE fitting or extracted at saturation field.

    Sources:
        Neubauer, A. et al.,
        Phys. Rev. Lett. 102, 186602 (2009).
        DOI: 10.1103/PhysRevLett.102.186602
    """

    @property
    def name(self) -> str:
        return "topological_hall"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return [
            "Neubauer, A. et al., "
            "Phys. Rev. Lett. 102, 186602 (2009). "
            "DOI: 10.1103/PhysRevLett.102.186602"
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="R_0",
                unit="m^3/C",
                lower=None,
                upper=None,
                description="Ordinary Hall coefficient (for OHE background subtraction)",
            ),
            ParamSpec(
                name="R_s",
                unit="m^3/C",
                lower=None,
                upper=None,
                description="Anomalous Hall coefficient (for AHE background subtraction)",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=("Hall bar, simultaneous ρ_xy(H)·M(H) measurement required. Sweep beyond saturation field to extract R_0."),
            tensor_rank=2,
            required_columns=("B", "rho_xy", "M"),
            notes=(
                "B [T]: external magnetic field. rho_xy [Ohm·m]: total Hall resistivity. "
                "M [A/m]: magnetization. Fit R_0, R_s from high-field data, "
                "then compute ρ_THE residual."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"ahe_allowed": True, "note": "THE arises from non-collinear spin structures"}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute ρ_THE = ρ_xy − R_0·B − μ₀·R_s·M.

        Args:
            params: {"R_0": float, "R_s": float}.
            geometry: {"B": ndarray, "rho_xy": ndarray, "M": ndarray}.

        Returns:
            ρ_THE residual array.
        """
        R_0 = params["R_0"]
        R_s = params["R_s"]
        B = geometry["B"] if geometry and "B" in geometry else np.array([0.0])
        rho_xy = geometry.get("rho_xy", np.zeros_like(B)) if geometry else np.zeros_like(B)
        M = geometry.get("M", np.zeros_like(B)) if geometry else np.zeros_like(B)
        background = R_0 * B + MU_0 * R_s * M
        return rho_xy - background

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit background (OHE+AHE) from ρ_xy(B), M(B) data to extract THE residual.

        Fit R_0, R_s from the high-field region (magnetization saturation), then subtract background over the full range.

        Args:
            data: {"B": ndarray, "rho_xy": ndarray, "M": ndarray}.
            geometry: Additional geometry info (optional).

        Returns:
            FitResult (including R_0, R_s).
        """
        B = data["B"]
        rho_xy = data["rho_xy"]
        M = data.get("M", np.zeros_like(B))

        # Simultaneous linear fitting of background = R_0·B + μ₀·R_s·M
        X = np.column_stack([B, MU_0 * M])
        try:
            coeffs = np.linalg.lstsq(X, rho_xy, rcond=None)[0]
            init = {"R_0": float(coeffs[0]), "R_s": float(coeffs[1])}
        except Exception:
            init = {"R_0": 1e-10, "R_s": 1e-10}

        _M = M  # closure

        def model_fn(x: np.ndarray, R_0: float, R_s: float) -> np.ndarray:
            return R_0 * x + MU_0 * R_s * _M

        return run_fit(
            model_fn=model_fn,
            x_data=B,
            y_data=rho_xy,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )

    def extract_the(
        self,
        data: dict[str, np.ndarray],
        fit_result: FitResult,
    ) -> np.ndarray:
        """Extract THE signal by subtracting the fitted background.

        Args:
            data: {"B": ndarray, "rho_xy": ndarray, "M": ndarray}.
            fit_result: Output of fit().

        Returns:
            ρ_THE array.
        """
        B = data["B"]
        rho_xy = data["rho_xy"]
        M = data.get("M", np.zeros_like(B))
        R_0 = fit_result.params["R_0"]
        R_s = fit_result.params["R_s"]
        return rho_xy - R_0 * B - MU_0 * R_s * M
