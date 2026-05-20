"""FMR Kittel dispersion relation EffectModel.

In-plane: (ω/γ)² = μ₀²·H_res·(H_res + M_eff)
Out-of-plane: (ω/γ)  = μ₀·(H_res − M_eff)
Parameters: M_eff (effective magnetization), γ (gyromagnetic ratio)

Sources:
    Kittel, C.,
    Phys. Rev. 73, 155 (1948).
    DOI: 10.1103/PhysRev.73.155
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


class FMRKittel(EffectModel):
    """FMR Kittel dispersion relation EffectModel.

    In-plane configuration:
      (f / γ')² = μ₀² H_res (H_res + M_eff)
      γ' = γ / (2π) [GHz/T]

    Out-of-plane configuration:
      f / γ' = μ₀ (H_res − M_eff)

    f: FMR frequency [GHz]
    H_res: resonance field [T]
    M_eff: effective magnetization = M_s − 2K_u/(μ₀M_s) [A/m]
    γ: gyromagnetic ratio [rad/(s·T)]

    Sources:
        Kittel, C., Phys. Rev. 73, 155 (1948).
        DOI: 10.1103/PhysRev.73.155
    """

    def __init__(self, mode: str = "in_plane") -> None:
        """
        Args:
            mode: "in_plane" (default) or "out_of_plane".
        """
        if mode not in ("in_plane", "out_of_plane"):
            raise ValueError(f"mode must be 'in_plane' or 'out_of_plane'. Got: {mode}")
        self._mode = mode

    @property
    def name(self) -> str:
        return "fmr_kittel"

    @property
    def subfield(self) -> str:
        return "ferromagnetic_resonance"

    @property
    def references(self) -> list[str]:
        return ["Kittel, C., Phys. Rev. 73, 155 (1948). DOI: 10.1103/PhysRev.73.155"]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="M_eff",
                unit="A/m",
                lower=0.0,
                upper=None,
                description="Effective magnetization M_eff = M_s − 2K_u/(μ₀M_s) [A/m]",
            ),
            ParamSpec(
                name="gamma_ghz_t",
                unit="GHz/T",
                lower=0.0,
                upper=50.0,
                description="Gyromagnetic ratio (frequency units) γ' = γ/(2π) [GHz/T]",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        geometry_str = (
            "In-plane or out-of-plane FMR" if self._mode == "in_plane" else "Out-of-plane FMR"
        )
        return MeasurementConfig(
            geometry=(
                f"{geometry_str}: frequency-swept FMR measurement (VNA-FMR). Collect f vs. H_res pairs."
            ),
            tensor_rank=2,
            required_columns=("H_res", "f"),
            notes=(
                "H_res [T]: FMR resonance field at each frequency. f [GHz]: microwave frequency."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"fmr_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute f(H_res) from the Kittel dispersion relation.

        Args:
            params: {"M_eff": float, "gamma_ghz_t": float}.
            geometry: {"H_res": ndarray [T]}.

        Returns:
            f [GHz] array.
        """
        M_eff = params["M_eff"]
        gamma_p = params["gamma_ghz_t"]  # GHz/T
        H_res = geometry["H_res"] if geometry and "H_res" in geometry else np.array([0.1])

        if self._mode == "in_plane":
            # f = γ' · sqrt[μ₀H_res · μ₀(H_res + M_eff)]
            # = γ' · μ₀ · sqrt[H_res · (H_res + M_eff)]
            # Note: H_res is input in [T] (i.e., μ₀·H in SI),
            # so Kittel: (f/γ')² = μ₀²·H[A/m]·(H[A/m]+M_eff[A/m])
            # Convert H_res [T] → H_Am [A/m] via H_Am = H_res / μ₀
            H_Am = H_res / MU_0  # A/m
            # Use np.abs to match fit() — keeps forward() usable for fitted params
            # where M_eff < -H_Am (PMA-like regime or optimizer excursion).
            f = gamma_p * MU_0 * np.sqrt(np.abs(H_Am * (H_Am + M_eff)))
        else:
            # Out-of-plane: f = γ' · μ₀ · |H[A/m] − M_eff|
            # abs() keeps f non-negative when H_res < M_eff·μ₀, consistent
            # with formulas.py:403 and physical convention that FMR frequency
            # is positive definite.
            H_Am = H_res / MU_0
            f = gamma_p * MU_0 * np.abs(H_Am - M_eff)

        return f

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit M_eff, γ from f vs. H_res data.

        Args:
            data: {"H_res": ndarray [T], "f": ndarray [GHz]}.
            geometry: {"mode": str} (optional, overrides constructor mode).

        Returns:
            FitResult.
        """
        H_res = data["H_res"]
        f_data = data["f"]

        # Standard γ' ≈ 28 GHz/T (g≈2)
        gamma_init = abs(GAMMA_E) / (2.0 * np.pi) * 1e-9  # rad/(s·T) → GHz/T

        # Initial M_eff: from in-plane Kittel f² ≈ γ'²μ₀²·H_res·(H_res + M_eff)
        # Simplified: M_eff ≈ (f/γ'/μ₀)² / H_res - H_res at the maximum H_res point
        H_max_idx = int(np.argmax(H_res))
        H_Am_max = H_res[H_max_idx] / MU_0
        f_max = f_data[H_max_idx]
        if self._mode == "in_plane":
            ratio = (f_max / gamma_init / MU_0) ** 2
            M_eff_init = max(ratio / H_Am_max - H_Am_max, 1e3)
        else:
            M_eff_init = max(H_Am_max - f_max / gamma_init / MU_0, 1e3)

        M_eff_init = float(M_eff_init)
        init = {"M_eff": M_eff_init, "gamma_ghz_t": gamma_init}
        _mode = self._mode

        def model_fn(x: np.ndarray, M_eff: float, gamma_ghz_t: float) -> np.ndarray:
            H_Am = x / MU_0
            if _mode == "in_plane":
                return gamma_ghz_t * MU_0 * np.sqrt(np.abs(H_Am * (H_Am + M_eff)))
            else:
                return gamma_ghz_t * MU_0 * np.abs(H_Am - M_eff)

        return run_fit(
            model_fn=model_fn,
            x_data=H_res,
            y_data=f_data,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
