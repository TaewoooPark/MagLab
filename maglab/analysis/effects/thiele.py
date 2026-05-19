"""Thiele equation — skyrmion dynamics EffectModel.

G×v + α·D·v = F
Skyrmion Hall angle: tan(θ_SkH) = G / (α·D)

Sources:
    Thiele, A. A.,
    Phys. Rev. Lett. 30, 230 (1973).
    DOI: 10.1103/PhysRevLett.30.230
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from maglab.analysis.effects.base import (
    EffectModel,
    FitResult,
    MeasurementConfig,
    ParamSpec,
)
from maglab.analysis.fit import run_fit


class ThieleModel(EffectModel):
    """Thiele skyrmion dynamics EffectModel.

    Thiele equation:
    G×v + α·D·v = F

    G = 4πQ ħ/(a²): gyrovector (Q = winding number/topological charge, a = lattice constant)
    D: dissipation tensor (isotropic D·I)
    v: skyrmion velocity vector
    F: driving force (from current)

    Skyrmion Hall angle:
    tan(θ_SkH) = G_z / (α·D)
    θ_SkH = arctan(G_z / (α·D))

    Sources:
        Thiele, A. A., Phys. Rev. Lett. 30, 230 (1973).
        DOI: 10.1103/PhysRevLett.30.230
    """

    @property
    def name(self) -> str:
        return "thiele"

    @property
    def subfield(self) -> str:
        return "domain_walls_skyrmions"

    @property
    def references(self) -> list[str]:
        return ["Thiele, A. A., Phys. Rev. Lett. 30, 230 (1973). DOI: 10.1103/PhysRevLett.30.230"]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="Q",
                unit="dimensionless",
                lower=-2.0,
                upper=2.0,
                description="Skyrmion winding number (topological charge Q = ±1 for a simple skyrmion)",
            ),
            ParamSpec(
                name="D",
                unit="dimensionless",
                lower=0.0,
                upper=None,
                description="Dissipation tensor D (isotropic component)",
            ),
            ParamSpec(
                name="alpha",
                unit="dimensionless",
                lower=1e-5,
                upper=1.0,
                description="Gilbert damping constant α",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=("Current-driven skyrmion Hall angle measurement. v_x, v_y vs. driving current density j."),
            tensor_rank=2,
            required_columns=("j", "v_x", "v_y"),
            notes=(
                "j [A/m²]: current density. v_x, v_y [m/s]: skyrmion velocity components. θ_SkH = arctan(v_y/v_x)."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"skyrmion_dynamics_valid": True}

    def skyrmion_hall_angle(self, Q: float, alpha: float, D: float) -> float:
        """Compute skyrmion Hall angle θ_SkH.

        tan(θ_SkH) = 4πQ / (α·D)
        θ_SkH = arctan(4πQ / (α·D))

        Args:
            Q: Winding number (topological charge).
            alpha: Gilbert damping constant.
            D: Dissipation tensor component.

        Returns:
            θ_SkH [rad].
        """
        G_z = 4.0 * math.pi * Q
        if abs(alpha * D) < 1e-20:
            return math.pi / 2.0 * (1.0 if G_z > 0 else -1.0)
        return math.atan2(G_z, alpha * D)

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute skyrmion Hall angle θ_SkH and velocity.

        Args:
            params: {"Q": float, "D": float, "alpha": float}.
            geometry: {"j": ndarray [A/m²], "driving_coeff": float}.
                driving_coeff: conversion coefficient from j to F [m/s per A/m²].

        Returns:
            θ_SkH (wrapped as a scalar) or v_x, v_y arrays.
        """
        Q = params["Q"]
        D = params["D"]
        alpha = params["alpha"]
        j = geometry.get("j", np.array([1e10])) if geometry else np.array([1e10])
        c = float((geometry or {}).get("driving_coeff", 1e-12))  # j → F [m/s per A/m²]

        G_z = 4.0 * math.pi * Q
        denom = alpha**2 * D**2 + G_z**2
        if abs(denom) < 1e-30:
            return np.zeros_like(j)

        F = c * j
        # v_x = (αD·F) / (α²D² + G²),  v_y = (G·F) / (α²D² + G²)
        v_x = alpha * D * F / denom
        v_y = G_z * F / denom
        # Hall angle
        theta_SkH = self.skyrmion_hall_angle(Q, alpha, D)
        return np.column_stack([v_x, v_y, np.full_like(j, theta_SkH)])

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit Q, D, α from v_x, v_y vs. j data.

        Args:
            data: {"j": ndarray, "v_x": ndarray, "v_y": ndarray}.
            geometry: {"driving_coeff": float}.

        Returns:
            FitResult.
        """
        j = data["j"]
        v_x = data.get("v_x", j * 1e-12)  # fallback
        c = float((geometry or {}).get("driving_coeff", 1e-12))

        init = {"Q": 1.0, "D": 1.0, "alpha": 0.01}

        # Use v_x as the fitting target
        def model_fn(x: np.ndarray, Q: float, D: float, alpha: float) -> np.ndarray:
            G_z = 4.0 * math.pi * Q
            denom = alpha**2 * D**2 + G_z**2
            if abs(denom) < 1e-30:
                return np.zeros_like(x)
            F = c * x
            return alpha * D * F / denom

        return run_fit(
            model_fn=model_fn,
            x_data=j,
            y_data=v_x,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
