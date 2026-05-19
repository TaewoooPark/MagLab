"""Planar Hall Effect (PHE) EffectModel.

Fitting equation: ρ_xy = (Δρ/2)·sin(2φ)
Parameters: Δρ = ρ_∥ - ρ_⊥ (AMR anisotropic resistivity difference)

Sources:
    Taskin, A. A., Ando, Y.,
    Phys. Rev. B 84, 035301 (2011).
    DOI: 10.1103/PhysRevB.84.035301

    Tang, H. X. et al., Phys. Rev. Lett. 90, 107201 (2003).
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


class PlanarHallEffect(EffectModel):
    """Planar Hall Effect EffectModel.

    ρ_xy = (Δρ/2)·sin(2φ)

    Δρ = ρ_∥ - ρ_⊥: longitudinal AMR anisotropic resistivity difference [Ohm·m]
    φ: in-plane magnetization angle relative to the current direction [rad]

    Sources:
        Taskin, A. A., Ando, Y.,
        Phys. Rev. B 84, 035301 (2011). DOI: 10.1103/PhysRevB.84.035301
    """

    @property
    def name(self) -> str:
        return "planar_hall"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return [
            "Taskin, A. A., Ando, Y., Phys. Rev. B 84, 035301 (2011). "
            "DOI: 10.1103/PhysRevB.84.035301",
            "Tang, H. X. et al., Phys. Rev. Lett. 90, 107201 (2003).",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="delta_rho",
                unit="Ohm*m",
                lower=None,
                upper=None,
                description="AMR anisotropic resistivity difference Δρ = ρ_∥ - ρ_⊥",
            )
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Hall bar, in-plane external field φ rotation (0~2π). Current I∥x, Hall voltage V_y measured."
            ),
            tensor_rank=2,
            required_columns=("phi", "rho_xy"),
            notes="phi [rad]: in-plane field azimuthal angle. rho_xy [Ohm·m]: Hall resistivity.",
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"phe_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute ρ_xy = (Δρ/2)·sin(2φ).

        Args:
            params: {"delta_rho": float}.
            geometry: {"phi": ndarray} (angle [rad]).

        Returns:
            ρ_xy array.
        """
        delta_rho = params["delta_rho"]
        phi = geometry["phi"] if geometry and "phi" in geometry else np.array([0.0])
        return (delta_rho / 2.0) * np.sin(2.0 * phi)

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit Δρ from φ-sweep ρ_xy data.

        Args:
            data: {"phi": ndarray, "rho_xy": ndarray}.
            geometry: Additional geometry info (optional).

        Returns:
            FitResult.
        """
        phi = data["phi"]
        rho_xy = data["rho_xy"]

        # Initial value via linear regression on sin2φ
        sin2phi = np.sin(2.0 * phi)
        try:
            init_val = float(np.polyfit(sin2phi, rho_xy, 1)[0]) * 2.0
        except Exception:
            init_val = 1e-8

        def model_fn(x: np.ndarray, delta_rho: float) -> np.ndarray:
            return (delta_rho / 2.0) * np.sin(2.0 * x)

        return run_fit(
            model_fn=model_fn,
            x_data=phi,
            y_data=rho_xy,
            param_specs=self.parameters,
            init_values={"delta_rho": init_val},
            effect_name=self.name,
        )
