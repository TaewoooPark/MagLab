"""Hysteresis loop analysis EffectModel.

Extract M_s (saturation), M_r (remanence), H_c (coercivity) from M(H) loops.
Stoner-Wohlfarth model optional.

Sources:
    Stoner, E. C., Wohlfarth, E. P.,
    Philos. Trans. R. Soc. London A 240, 599 (1948).
    DOI: 10.1098/rsta.1948.0007
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np

from maglab.analysis.effects.base import (
    EffectModel,
    FitResult,
    MeasurementConfig,
    ParamSpec,
)
from maglab.analysis.fit import run_fit


class HysteresisLoop(EffectModel):
    """Hysteresis loop analysis EffectModel.

    Extract the following parameters from M(H) loops:
    - M_s: saturation magnetization (high-field extrapolation)
    - M_r: remanent magnetization (M at H=0)
    - H_c: coercivity (H at M=0)

    High-field linearization: M(H) = M_s + χ_p·H (paramagnetic background correction).

    Sources:
        Stoner, E. C., Wohlfarth, E. P.,
        Philos. Trans. R. Soc. London A 240, 599 (1948).
        DOI: 10.1098/rsta.1948.0007
    """

    @property
    def name(self) -> str:
        return "hysteresis"

    @property
    def subfield(self) -> str:
        return "magnetometry"

    @property
    def references(self) -> list[str]:
        return [
            "Stoner, E. C., Wohlfarth, E. P., "
            "Philos. Trans. R. Soc. London A 240, 599 (1948). "
            "DOI: 10.1098/rsta.1948.0007"
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="M_s",
                unit="A/m",
                lower=0.0,
                upper=None,
                description="Saturation magnetization [A/m]",
            ),
            ParamSpec(
                name="chi_p",
                unit="dimensionless",
                lower=None,
                upper=None,
                description="High-field paramagnetic contribution χ_p (linear slope)",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "VSM or SQUID magnetometer. M(H) loop measurement. Full bidirectional loop (+H → -H → +H)."
            ),
            tensor_rank=2,
            required_columns=("H", "M"),
            notes=(
                "H [A/m]: external magnetic field. M [A/m]: magnetization. "
                "Full loop data or first-quadrant data accepted."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"magnetometry_valid": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute simple high-field M(H) = M_s + χ_p·H.

        Args:
            params: {"M_s": float, "chi_p": float}.
            geometry: {"H": ndarray}.

        Returns:
            M array [A/m].
        """
        M_s = params["M_s"]
        chi_p = params["chi_p"]
        H = geometry["H"] if geometry and "H" in geometry else np.array([0.0])
        # Saturation component: tanh approximation (converges to M_s at high fields)
        H_sat = float((geometry or {}).get("H_sat", 1e6))  # characteristic saturation field
        return M_s * np.tanh(H / H_sat) + chi_p * H

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit M_s, χ_p from M(H) loop data.

        Args:
            data: {"H": ndarray, "M": ndarray}.
            geometry: {"H_sat": float (initial characteristic saturation field)}.

        Returns:
            FitResult (M_s, chi_p).
        """
        H = data["H"]
        M = data["M"]
        H_sat_init = float((geometry or {}).get("H_sat", float(np.max(np.abs(H))) / 3.0))

        M_s_init = float(np.max(np.abs(M)))
        chi_init = 0.0

        def model_fn(x: np.ndarray, M_s: float, chi_p: float) -> np.ndarray:
            return M_s * np.tanh(x / H_sat_init) + chi_p * x

        return run_fit(
            model_fn=model_fn,
            x_data=H,
            y_data=M,
            param_specs=self.parameters,
            init_values={"M_s": M_s_init, "chi_p": chi_init},
            effect_name=self.name,
        )

    def extract_loop_params(self, H: np.ndarray, M: np.ndarray) -> dict[str, float]:
        """Deterministically extract M_s, M_r, H_c from an M(H) loop.

        M_r and H_c require the data to contain actual zero-crossings.  If the
        H (or M) array does not straddle zero, the corresponding quantity is
        returned as float('nan') and a warning is emitted — returning the
        nearest-boundary value would be physically meaningless.

        Args:
            H: External magnetic field array [A/m].
            M: Magnetization array [A/m].

        Returns:
            Dictionary {"M_s": float, "M_r": float, "H_c": float}.
            M_r and/or H_c may be nan if the data lacks a zero-crossing.
        """
        M_s = float(np.max(np.abs(M)))

        # M_r: M at H = 0 — requires H to straddle zero
        H_min, H_max = float(np.min(H)), float(np.max(H))
        if H_min >= 0.0 or H_max <= 0.0:
            warnings.warn(
                "extract_loop_params: H data does not cross zero "
                f"(range [{H_min:.3g}, {H_max:.3g}] A/m). "
                "Returning M_r = nan.",
                stacklevel=2,
            )
            M_r = float("nan")
        else:
            idx_zero = int(np.argmin(np.abs(H)))
            M_r = float(abs(M[idx_zero]))

        # H_c: H at M = 0 — requires M to straddle zero
        M_min, M_max = float(np.min(M)), float(np.max(M))
        if M_min >= 0.0 or M_max <= 0.0:
            warnings.warn(
                "extract_loop_params: M data does not cross zero "
                f"(range [{M_min:.3g}, {M_max:.3g}] A/m). "
                "Returning H_c = nan.",
                stacklevel=2,
            )
            H_c = float("nan")
        else:
            idx_mc = int(np.argmin(np.abs(M)))
            H_c = float(abs(H[idx_mc]))

        return {"M_s": M_s, "M_r": M_r, "H_c": H_c}
