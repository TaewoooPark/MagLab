"""Anomalous Hall Effect (AHE) EffectModel.

Fitting equation: ρ_xy = R_0·B + μ₀·R_s·M(H)
Parameters: R_0 (ordinary Hall coefficient), R_s (anomalous Hall coefficient)

Sources:
    Nagaosa, N., Sinova, J., Onoda, S., MacDonald, A. H., Ong, N. P.,
    Rev. Mod. Phys. 82, 1539 (2010). DOI: 10.1103/RevModPhys.82.1539
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


class AnomalousHallEffect(EffectModel):
    """Anomalous Hall Effect EffectModel.

    ρ_xy = R_0·B + μ₀·R_s·M(H)

    R_0: ordinary Hall coefficient [m³/C]
    R_s: anomalous Hall coefficient [m³/C or Ohm·m/T]
    M(H): magnetization at external field H [A/m] — supplied from separate data or tanh model.

    Sources:
        Nagaosa, N. et al., Rev. Mod. Phys. 82, 1539 (2010).
        DOI: 10.1103/RevModPhys.82.1539
    """

    @property
    def name(self) -> str:
        return "anomalous_hall"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return [
            "Nagaosa, N., Sinova, J., Onoda, S., MacDonald, A. H., Ong, N. P., "
            "Rev. Mod. Phys. 82, 1539 (2010). DOI: 10.1103/RevModPhys.82.1539"
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="R_0",
                unit="m^3/C",
                lower=None,
                upper=None,
                description="Ordinary Hall coefficient (OHE contribution)",
            ),
            ParamSpec(
                name="R_s",
                unit="m^3/C",
                lower=None,
                upper=None,
                description="Anomalous Hall coefficient (AHE contribution)",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Hall bar, field swept beyond saturation magnetization. I∥x, B∥z, V_y. Slope at saturation field = R_0."
            ),
            tensor_rank=2,
            required_columns=("B", "rho_xy", "M"),
            notes=(
                "B [T]: external magnetic field. rho_xy [Ohm·m]: Hall resistivity. "
                "M [A/m]: simultaneously measured magnetization or Langevin model value."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {
            "ahe_allowed": True,
            "hall_components": [(0, 1), (1, 0)],
        }

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute ρ_xy = R_0·B + μ₀·R_s·M(H).

        Args:
            params: {"R_0": float, "R_s": float}.
            geometry: {"B": ndarray, "M": ndarray}.
                B [T], M [A/m].

        Returns:
            ρ_xy array [Ohm·m].
        """
        R_0 = params["R_0"]
        R_s = params["R_s"]
        B = geometry["B"] if geometry and "B" in geometry else np.array([0.0])
        M = geometry.get("M", np.zeros_like(B)) if geometry else np.zeros_like(B)
        return R_0 * B + MU_0 * R_s * M

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Simultaneously fit R_0, R_s from ρ_xy(B, M) data.

        Args:
            data: {"B": ndarray, "rho_xy": ndarray, "M": ndarray}.
            geometry: Additional geometry information (optional).

        Returns:
            FitResult.
        """
        B = data["B"]
        rho_xy = data["rho_xy"]
        M = data.get("M", np.zeros_like(B))

        # Linear regression with X = [B, μ₀M] 2-column matrix
        X = np.column_stack([B, MU_0 * M])
        # Initial values from linear regression
        try:
            coeffs = np.linalg.lstsq(X, rho_xy, rcond=None)[0]
            init = {"R_0": float(coeffs[0]), "R_s": float(coeffs[1])}
        except Exception:
            init = {"R_0": 1e-10, "R_s": 1e-10}

        def model_fn(x: np.ndarray, R_0: float, R_s: float) -> np.ndarray:
            # x = B, M passed via outer closure
            return R_0 * x + MU_0 * R_s * M

        return run_fit(
            model_fn=model_fn,
            x_data=B,
            y_data=rho_xy,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
