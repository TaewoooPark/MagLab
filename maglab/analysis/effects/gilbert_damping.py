"""Gilbert damping EffectModel.

ΔH = ΔH₀ + (2α/γ)·f
Fit frequency-dependent FMR linewidth data → α, ΔH₀ (inhomogeneous linewidth).

Sources:
    Kalinikos, B. A., Slavin, A. N.,
    J. Phys. C 19, 7013 (1986). DOI: 10.1088/0022-3719/19/35/014

    Gilbert, T. L.,
    IEEE Trans. Magn. 40, 3443 (2004). DOI: 10.1109/TMAG.2004.836740
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
from maglab.physics.constants import GAMMA_E


class GilbertDamping(EffectModel):
    """Gilbert damping EffectModel.

    ΔH = ΔH₀ + (2α / γ) · f

    ΔH: FMR half-linewidth HWHM [T or A/m]
    ΔH₀: inhomogeneous linewidth contribution (extrapolation to f=0)
    α: Gilbert damping constant [dimensionless]
    γ: gyromagnetic ratio [rad/(s·T)]
    f: FMR frequency [GHz]

    Sources:
        Gilbert, T. L., IEEE Trans. Magn. 40, 3443 (2004).
        DOI: 10.1109/TMAG.2004.836740
        Kalinikos, B. A., Slavin, A. N., J. Phys. C 19, 7013 (1986).
    """

    @property
    def name(self) -> str:
        return "gilbert_damping"

    @property
    def subfield(self) -> str:
        return "ferromagnetic_resonance"

    @property
    def references(self) -> list[str]:
        return [
            "Gilbert, T. L., IEEE Trans. Magn. 40, 3443 (2004). DOI: 10.1109/TMAG.2004.836740",
            "Kalinikos, B. A., Slavin, A. N., J. Phys. C 19, 7013 (1986). "
            "DOI: 10.1088/0022-3719/19/35/014",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="alpha",
                unit="dimensionless",
                lower=1e-5,
                upper=1.0,
                description="Gilbert damping constant α",
            ),
            ParamSpec(
                name="dH_0",
                unit="T",
                lower=0.0,
                upper=None,
                description="Inhomogeneous linewidth contribution ΔH₀ (extrapolated to f→0) [T]",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=("Broadband FMR (VNA-FMR or ST-FMR frequency sweep). Measure ΔH vs. f."),
            tensor_rank=2,
            required_columns=("f", "dH"),
            notes=("f [GHz]: microwave frequency. dH [T]: FMR half-linewidth (HWHM) at each frequency."),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"damping_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute ΔH(f) = ΔH₀ + (2α/γ)·f.

        Args:
            params: {"alpha": float, "dH_0": float}.
            geometry: {"f": ndarray [GHz], "gamma_ghz_t": float (optional)}.

        Returns:
            ΔH array [T].
        """
        alpha = params["alpha"]
        dH_0 = params["dH_0"]
        f = geometry["f"] if geometry and "f" in geometry else np.array([1.0])
        # γ' = γ/(2π) [GHz/T] ≈ 28 GHz/T
        gamma_p = float((geometry or {}).get("gamma_ghz_t", abs(GAMMA_E) / (2.0 * np.pi) * 1e-9))
        return dH_0 + (2.0 * alpha / gamma_p) * f

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Linearly fit α, ΔH₀ from ΔH vs. f data.

        Args:
            data: {"f": ndarray [GHz], "dH": ndarray [T]}.
            geometry: {"gamma_ghz_t": float} (optional).

        Returns:
            FitResult.
        """
        f = data["f"]
        dH = data["dH"]
        gamma_p = float((geometry or {}).get("gamma_ghz_t", abs(GAMMA_E) / (2.0 * np.pi) * 1e-9))

        # Linear regression: dH = dH_0 + (2α/γ')·f
        X = np.column_stack([np.ones_like(f), f])
        try:
            coeffs = np.linalg.lstsq(X, dH, rcond=None)[0]
            dH_0_init = float(coeffs[0])
            slope = float(coeffs[1])
            alpha_init = max(slope * gamma_p / 2.0, 1e-4)
        except Exception:
            dH_0_init = float(np.min(dH))
            alpha_init = 0.01

        init = {"alpha": alpha_init, "dH_0": max(dH_0_init, 0.0)}
        _gamma_p = gamma_p

        def model_fn(x: np.ndarray, alpha: float, dH_0: float) -> np.ndarray:
            return dH_0 + (2.0 * alpha / _gamma_p) * x

        return run_fit(
            model_fn=model_fn,
            x_data=f,
            y_data=dH,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
