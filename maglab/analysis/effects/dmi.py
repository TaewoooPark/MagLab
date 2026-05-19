"""DMI (BLS non-reciprocity) EffectModel.

Δf = (γ·D_i) / (π·M_s) · k
BLS non-reciprocal frequency shift vs. wavevector k → linear fit to extract interfacial DMI constant D_i.

Sources:
    Di, K. et al.,
    Phys. Rev. Lett. 114, 047201 (2015).
    DOI: 10.1103/PhysRevLett.114.047201
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
from maglab.physics.constants import GAMMA_E, MU_0


class DMIEffect(EffectModel):
    """DMI (interfacial Dzyaloshinskii-Moriya interaction) BLS EffectModel.

    BLS non-reciprocal frequency shift:
    Δf(k) = f(+k) − f(−k) = 2·γ·D_i·k / (π·μ₀·M_s)

    where γ = γ/(2π) [GHz/T], k [m⁻¹], D_i [J/m²], M_s [A/m].

    D_i > 0: counterclockwise DMI (stabilizes Néel skyrmions).

    Sources:
        Di, K. et al., Phys. Rev. Lett. 114, 047201 (2015).
        DOI: 10.1103/PhysRevLett.114.047201
    """

    @property
    def name(self) -> str:
        return "dmi"

    @property
    def subfield(self) -> str:
        return "domain_walls_skyrmions"

    @property
    def references(self) -> list[str]:
        return [
            "Di, K. et al., "
            "Phys. Rev. Lett. 114, 047201 (2015). "
            "DOI: 10.1103/PhysRevLett.114.047201"
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="D_i",
                unit="J/m^2",
                lower=None,
                upper=None,
                description="Interfacial DMI constant D_i [J/m²]",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "BLS (Brillouin Light Scattering) k scan. "
                "Measure Stokes and anti-Stokes spin-wave frequencies in ±k directions."
            ),
            tensor_rank=2,
            required_columns=("k", "delta_f"),
            notes=(
                "k [m⁻¹]: spin-wave wavevector. "
                "delta_f [GHz]: non-reciprocal frequency shift Δf = f(+k) - f(-k). "
                "Ms [A/m] supplied via geometry."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"dmi_iDMI_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute Δf = 2γD_i k / (πμ₀M_s).

        Args:
            params: {"D_i": float [J/m²]}.
            geometry: {"k": ndarray [m⁻¹], "Ms": float [A/m]}.

        Returns:
            Δf array [GHz].
        """
        D_i = params["D_i"]
        k = geometry["k"] if geometry and "k" in geometry else np.array([1e7])
        Ms = float((geometry or {}).get("Ms", 8e5))
        # γ' = γ/(2π) [GHz/T], where γ = GAMMA_E [rad/(s·T)]
        gamma_p = abs(GAMMA_E) / (2.0 * np.pi) * 1e-9  # GHz/T
        return 2.0 * gamma_p * D_i * k / (np.pi * MU_0 * Ms)

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Linearly fit D_i from Δf(k) data.

        Args:
            data: {"k": ndarray [m⁻¹], "delta_f": ndarray [GHz]}.
            geometry: {"Ms": float [A/m]}.

        Returns:
            FitResult.
        """
        k = data["k"]
        delta_f = data["delta_f"]
        Ms = float((geometry or {}).get("Ms", 8e5))
        gamma_p = abs(GAMMA_E) / (2.0 * np.pi) * 1e-9  # GHz/T

        # Linear regression: Δf = slope·k, slope = 2γD_i/(πμ₀M_s)
        try:
            slope = float(np.polyfit(k, delta_f, 1)[0])
            D_i_init = slope * np.pi * MU_0 * Ms / (2.0 * gamma_p)
        except Exception:
            D_i_init = 1e-3

        _Ms = Ms
        _gamma_p = gamma_p

        def model_fn(x: np.ndarray, D_i: float) -> np.ndarray:
            return 2.0 * _gamma_p * D_i * x / (np.pi * MU_0 * _Ms)

        return run_fit(
            model_fn=model_fn,
            x_data=k,
            y_data=delta_f,
            param_specs=self.parameters,
            init_values={"D_i": D_i_init},
            effect_name=self.name,
        )
