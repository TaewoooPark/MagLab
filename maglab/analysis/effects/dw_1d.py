"""1D domain wall (DW) q–Φ coupled model EffectModel.

Thiele-Schryer-Walker q–Φ ODE.
Walker breakdown field: H_W = α·K_⊥ / (2·μ₀·M_s).

Sources:
    Schryer, N. L., Walker, L. R.,
    J. Appl. Phys. 45, 5406 (1974).
    DOI: 10.1063/1.1663252

    Thiele, A. A.,
    Phys. Rev. Lett. 30, 230 (1973).
    DOI: 10.1103/PhysRevLett.30.230
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


class DW1DModel(EffectModel):
    """1D domain wall q–Φ dynamics EffectModel.

    q–Φ coupled ODE (below Walker breakdown):
    dq/dt = Δ·γ₀·H / (1 + α²) − α·Δ·(γ₀·μ₀·M_s/2)·sin(2Φ) / (1+α²)
    dΦ/dt = α·γ₀·H / (Δ(1+α²)) + (γ₀·μ₀·M_s/2)·sin(2Φ) / (1+α²)

    Walker breakdown field: H_W = α·K_⊥ / (2·μ₀·M_s)

    Parameters: α (damping), Δ (DW width), K_⊥ (in-plane anisotropy)

    Sources:
        Schryer, N. L., Walker, L. R., J. Appl. Phys. 45, 5406 (1974).
        DOI: 10.1063/1.1663252
    """

    @property
    def name(self) -> str:
        return "dw_1d"

    @property
    def subfield(self) -> str:
        return "magnetization_dynamics"

    @property
    def references(self) -> list[str]:
        return [
            "Schryer, N. L., Walker, L. R., J. Appl. Phys. 45, 5406 (1974). DOI: 10.1063/1.1663252",
            "Thiele, A. A., Phys. Rev. Lett. 30, 230 (1973). DOI: 10.1103/PhysRevLett.30.230",
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
                name="Delta",
                unit="m",
                lower=1e-10,
                upper=1e-5,
                description="DW width Δ [m]",
            ),
            ParamSpec(
                name="K_perp",
                unit="J/m^3",
                lower=0.0,
                upper=None,
                description="In-plane anisotropy K_⊥ [J/m³]",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "Nanowire DW dynamics. Driving field H vs. DW velocity v measurement. "
                "Linear and nonlinear v(H) regimes before and after Walker breakdown H_W."
            ),
            tensor_rank=2,
            required_columns=("H", "v_dw"),
            notes=(
                "H [A/m]: driving magnetic field. v_dw [m/s]: DW propagation velocity. "
                "H < H_W: v = μ·H (mobility μ = γΔ/(1+α²)). "
                "H > H_W: average velocity decreases after Walker collapse."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"dw_dynamics_valid": True}

    def walker_field(self, alpha: float, K_perp: float, Ms: float) -> float:
        """Compute Walker breakdown field H_W.

        H_W = α·K_⊥ / (2·μ₀·M_s)

        Consistent with Schryer & Walker (1974) and Thiaville et al.
        EPL 69, 990 (2005), Eq. (6), and with physics/formulas.py
        walker_breakdown_field().  The factor of 2 was previously missing.

        Args:
            alpha: Gilbert damping constant.
            K_perp: In-plane anisotropy [J/m³].
            Ms: Saturation magnetization [A/m].

        Returns:
            H_W [A/m].
        """
        return alpha * K_perp / (2.0 * MU_0 * Ms)

    def dw_velocity_below_walker(self, alpha: float, Delta: float, H: float) -> float:
        """Analytical DW velocity below Walker breakdown (H < H_W).

        v = γ₀·Δ·H / (1 + α²) (linear mobility regime)

        Args:
            alpha: Gilbert damping constant.
            Delta: DW width [m].
            H: Driving magnetic field [A/m].

        Returns:
            DW velocity [m/s].
        """
        gamma_0 = abs(GAMMA_E)
        return gamma_0 * Delta * MU_0 * H / (1.0 + alpha**2)

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute DW velocity array in the H < H_W regime (linear analytical solution).

        Args:
            params: {"alpha": float, "Delta": float, "K_perp": float}.
            geometry: {"H": ndarray [A/m], "Ms": float [A/m]}.

        Returns:
            v_dw array [m/s].
        """
        alpha = params["alpha"]
        Delta = params["Delta"]
        H = geometry["H"] if geometry and "H" in geometry else np.array([1e4])
        return np.array([self.dw_velocity_below_walker(alpha, Delta, h) for h in H])

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit α, Δ from v_dw vs. H data (assuming linear regime).

        Args:
            data: {"H": ndarray [A/m], "v_dw": ndarray [m/s]}.
            geometry: {"Ms": float [A/m]}.

        Returns:
            FitResult.
        """
        H = data["H"]
        v_dw = data["v_dw"]
        gamma_0 = abs(GAMMA_E)

        # v = γ₀·μ₀·Δ·H / (1+α²) → slope = γ₀·μ₀·Δ/(1+α²) = μ_DW
        try:
            slope = float(np.polyfit(H, v_dw, 1)[0])
        except Exception:
            slope = 10.0

        # Initial alpha = 0.01, initial Delta derived from slope
        alpha_init = 0.01
        Delta_init = max(slope * (1.0 + alpha_init**2) / (gamma_0 * MU_0), 1e-9)

        init = {"alpha": alpha_init, "Delta": Delta_init, "K_perp": 1e4}

        def model_fn(x: np.ndarray, alpha: float, Delta: float, K_perp: float) -> np.ndarray:
            return gamma_0 * MU_0 * Delta * x / (1.0 + alpha**2)

        return run_fit(
            model_fn=model_fn,
            x_data=H,
            y_data=v_dw,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )
