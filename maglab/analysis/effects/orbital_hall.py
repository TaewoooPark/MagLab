"""Orbital Hall Effect (OHE) EffectModel.

OHE has a rank-3 tensor σ^{l_γ}_{α,β}, unlike the charge Hall effect (rank-2 tensor).
  α = current direction, β = transverse (Hall) direction, γ = orbital angular momentum polarization direction.
Holds sigma_OH[α][β][γ] (3×3×3 ndarray).

Fitting: extract θ_OH = σ_OH/σ_xx from harmonic Hall signal.

Sources:
    Choi, Y.-G. et al.,
    Nature 619, 52 (2023). DOI: 10.1038/s41586-023-06101-9

    Go, D. et al., arXiv:2409.20526 (2024).
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
from maglab.analysis.symmetry import ohe_constraints


class OrbitalHallEffect(EffectModel):
    """Orbital Hall Effect EffectModel (rank-3 tensor).

    Orbital Hall conductivity tensor σ^{l_γ}_{α,β} (3×3×3):
      σ_OH[α][β][γ]: current in α-direction, transverse β-direction, orbital angular momentum γ-direction

    θ_OH = σ_OH_xy_z / σ_xx (orbital Hall angle)

    Measurement: extract θ_OH from harmonic Hall signal / Hanle MR / MOKE angular dependence.

    Sources:
        Choi, Y.-G. et al., Nature 619, 52 (2023).
        DOI: 10.1038/s41586-023-06101-9
        Go, D. et al., arXiv:2409.20526 (2024).
    """

    def __init__(self, point_group: str = "m3m") -> None:
        self._point_group = point_group
        # Initialize rank-3 tensor: 3×3×3 zeros
        self._sigma_OH: np.ndarray = np.zeros((3, 3, 3), dtype=np.float64)

    @property
    def sigma_OH(self) -> np.ndarray:  # noqa: N802
        """Orbital Hall conductivity rank-3 tensor σ_OH[α][β][γ] (3×3×3)."""
        return self._sigma_OH.copy()

    def set_sigma_OH(self, tensor: np.ndarray) -> None:  # noqa: N802
        """Set the orbital Hall conductivity tensor.

        Args:
            tensor: shape (3,3,3) float64 array.
        """
        tensor = np.asarray(tensor, dtype=np.float64)
        if tensor.shape != (3, 3, 3):
            raise ValueError(f"sigma_OH must have shape (3,3,3). Got: {tensor.shape}")
        self._sigma_OH = tensor.copy()

    @property
    def name(self) -> str:
        return "orbital_hall"

    @property
    def subfield(self) -> str:
        return "spin_orbitronics"

    @property
    def references(self) -> list[str]:
        return [
            "Choi, Y.-G. et al., Nature 619, 52 (2023). DOI: 10.1038/s41586-023-06101-9",
            "Go, D. et al., arXiv:2409.20526 (2024).",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="theta_OH",
                unit="dimensionless",
                lower=-10.0,
                upper=10.0,
                description="Orbital Hall angle θ_OH = σ_OH/σ_xx",
            ),
            ParamSpec(
                name="sigma_xx",
                unit="S/m",
                lower=0.0,
                upper=None,
                description="Longitudinal electrical conductivity σ_xx [S/m]",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Harmonic Hall measurement / Hanle MR / MOKE angular dependence. "
                "Combined multi-geometry measurement to extract rank-3 tensor components."
            ),
            tensor_rank=3,
            required_columns=("phi", "V_2omega"),
            notes=(
                "phi [rad]: in-plane field azimuthal angle. "
                "V_2omega [V]: second-harmonic Hall voltage. "
                "rank-3 tensor: sigma_OH[alpha][beta][gamma] (3×3×3). "
                "α=current direction, β=transverse direction, γ=orbital angular momentum polarization direction."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        try:
            return ohe_constraints(self._point_group)
        except ValueError:
            return {"ohe_components": [(0, 1, 2), (1, 0, 2)]}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute harmonic Hall signal (simplified θ_OH model).

        V_2ω ≈ (θ_OH / H_ext) · cos(φ)  (simplified; actual geometry details required for full calculation)

        Args:
            params: {"theta_OH": float, "sigma_xx": float}.
            geometry: {"phi": ndarray, "H_ext": float}.

        Returns:
            V_2ω array.
        """
        theta_OH = params["theta_OH"]
        phi = geometry["phi"] if geometry and "phi" in geometry else np.array([0.0])
        H_ext = float(geometry.get("H_ext", 1.0)) if geometry else 1.0
        return (theta_OH / H_ext) * np.cos(phi)

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit θ_OH from V_2ω(φ) data.

        Args:
            data: {"phi": ndarray, "V_2omega": ndarray}.
            geometry: {"H_ext": float, "sigma_xx": float}.

        Returns:
            FitResult (including θ_OH).
        """
        phi = data["phi"]
        V_2w = data["V_2omega"]
        H_ext = float((geometry or {}).get("H_ext", 1.0))
        sigma_xx = float((geometry or {}).get("sigma_xx", 1e6))

        # Initial value via linear regression on cos(φ)
        cos_phi = np.cos(phi)
        try:
            theta_init = float(np.polyfit(cos_phi, V_2w, 1)[0]) * H_ext
        except Exception:
            theta_init = 0.1

        # Use only theta_OH as fitting parameter; sigma_xx is treated as a fixed value from geometry
        theta_spec = [p for p in self.parameters if p.name == "theta_OH"]

        def model_fn(x: np.ndarray, theta_OH: float) -> np.ndarray:
            return (theta_OH / H_ext) * np.cos(x)

        result = run_fit(
            model_fn=model_fn,
            x_data=phi,
            y_data=V_2w,
            param_specs=theta_spec,
            init_values={"theta_OH": theta_init},
            effect_name=self.name,
        )

        # Update σ_OH[0][1][2] component with fitted θ_OH
        if result.success:
            sigma_OH_val = result.params["theta_OH"] * result.params.get("sigma_xx", sigma_xx)
            new_tensor = np.zeros((3, 3, 3), dtype=np.float64)
            new_tensor[0, 1, 2] = sigma_OH_val  # α=x, β=y, γ=z
            new_tensor[1, 0, 2] = -sigma_OH_val  # antisymmetric component
            self.set_sigma_OH(new_tensor)

        return result

    def orbital_hall_conductivity(self, alpha: int, beta: int, gamma: int) -> float:
        """Return a specific component σ_OH[α][β][γ] from the rank-3 tensor.

        Args:
            alpha: Current direction index (0=x, 1=y, 2=z).
            beta: Transverse direction index.
            gamma: Orbital angular momentum polarization direction index.

        Returns:
            σ_OH[α][β][γ] [S/m].
        """
        return float(self._sigma_OH[alpha, beta, gamma])
