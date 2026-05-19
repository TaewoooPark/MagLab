"""GMR/TMR EffectModel.

Spin-valve / MTJ angle-dependent conductance (Slonczewski 1989):

    G(θ) = G_0 · (1 + P₁P₂ · cosθ)

where G_0 = (G_P + G_AP)/2 is the average conductance and P₁, P₂ are the
spin polarizations of the two ferromagnetic layers.  At θ = 0 (parallel) and
θ = π (antiparallel) this gives:

    G_P  = G_0 · (1 + P₁P₂)
    G_AP = G_0 · (1 − P₁P₂)

The Julliere TMR ratio follows from these extremes:

    TMR = (G_P − G_AP) / G_AP = 2P₁P₂ / (1 − P₁P₂)

Sources:
    Slonczewski, J. C., Phys. Rev. B 39, 6995 (1989), Eq. (4).
    DOI: 10.1103/PhysRevB.39.6995

    Julliere, M., Phys. Lett. A 54, 225 (1975).
    DOI: 10.1016/0375-9601(75)90174-7
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


class GMRTMREffect(EffectModel):
    """GMR/TMR EffectModel.

    Spin-valve / MTJ angle-dependent conductance (Slonczewski 1989):

        G(θ) = G_0 · (1 + P₁P₂ · cosθ)

    where G_0 = (G_P + G_AP)/2 is the average conductance and P₁, P₂ are the
    spin polarizations of the two ferromagnetic layers [0, 1).

    At θ = 0 (parallel): G_P = G_0·(1 + P₁P₂).
    At θ = π (antiparallel): G_AP = G_0·(1 − P₁P₂).
    Julliere TMR ratio: TMR = (G_P − G_AP)/G_AP = 2P₁P₂/(1 − P₁P₂).

    Sources:
        Slonczewski, J. C., Phys. Rev. B 39, 6995 (1989), Eq. (4).
        DOI: 10.1103/PhysRevB.39.6995
        Julliere, M., Phys. Lett. A 54, 225 (1975).
        DOI: 10.1016/0375-9601(75)90174-7
    """

    @property
    def name(self) -> str:
        return "gmr_tmr"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return [
            "Julliere, M., Phys. Lett. A 54, 225 (1975). DOI: 10.1016/0375-9601(75)90174-7",
            "Slonczewski, J. C., Phys. Rev. B 39, 6995 (1989). DOI: 10.1103/PhysRevB.39.6995",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="G_0",
                unit="S",
                lower=0.0,
                upper=None,
                description="Average conductance (midpoint between P and AP states)",
            ),
            ParamSpec(
                name="P1",
                unit="dimensionless",
                lower=0.0,
                upper=0.9999,
                description="Spin polarization of magnetic layer 1 [0, 1)",
            ),
            ParamSpec(
                name="P2",
                unit="dimensionless",
                lower=0.0,
                upper=0.9999,
                description="Spin polarization of magnetic layer 2 [0, 1)",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=("Spin-valve/MTJ relative angle θ sweep between two layers (0~π). θ=0: parallel (P), θ=π: antiparallel (AP)."),
            tensor_rank=2,
            required_columns=("theta", "G"),
            notes="theta [rad]: angle between magnetizations of the two magnetic layers. G [S]: conductance.",
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"note": "GMR/TMR has no magnetic point group constraint"}

    @staticmethod
    def tmr_from_polarizations(P1: float, P2: float) -> float:
        """Compute TMR ratio from the Julliere formula.

        TMR = 2P₁P₂ / (1 − P₁P₂)
        """
        denom = 1.0 - P1 * P2
        if abs(denom) < 1e-15:
            return float("inf")
        return 2.0 * P1 * P2 / denom

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute G(θ) = G_0·(1 + P₁P₂·cosθ).

        The conductance oscillation amplitude is P₁P₂ (Slonczewski, PRB 39,
        6995, 1989), NOT TMR/2.  Using TMR/2 = P₁P₂/(1 − P₁P₂) inflates the
        amplitude by 1/(1 − P₁P₂) and makes G_AP non-positive for P₁P₂ ≥ 0.5.

        Args:
            params: {"G_0": float, "P1": float, "P2": float}.
            geometry: {"theta": ndarray}.

        Returns:
            G(θ) array.
        """
        G_0 = params["G_0"]
        P1 = params["P1"]
        P2 = params["P2"]
        theta = geometry["theta"] if geometry and "theta" in geometry else np.array([0.0])
        return G_0 * (1.0 + P1 * P2 * np.cos(theta))

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit G_0, P1, P2 from G(θ) data.

        Args:
            data: {"theta": ndarray, "G": ndarray}.
            geometry: Additional geometry info (optional).

        Returns:
            FitResult.
        """
        theta = data["theta"]
        G = data["G"]

        # Initial TMR estimate: G_P ≈ G(0), G_AP ≈ G(π)
        G_mean = float(np.mean(G))
        G_amp = float((np.max(G) - np.min(G)) / 2.0)
        tmr_init = 2.0 * G_amp / G_mean if G_mean > 0 else 0.5
        # Initial P: TMR = 2P² / (1-P²) → P = sqrt(TMR/(2+TMR))
        p_init = min(float(np.sqrt(tmr_init / (2.0 + tmr_init + 1e-15))), 0.9)

        init = {"G_0": G_mean, "P1": p_init, "P2": p_init}

        def model_fn(x: np.ndarray, G_0: float, P1: float, P2: float) -> np.ndarray:
            # Slonczewski (1989): amplitude is P1·P2, not TMR/2.
            return G_0 * (1.0 + P1 * P2 * np.cos(x))

        return run_fit(
            model_fn=model_fn,
            x_data=theta,
            y_data=G,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
