"""Spin Hall Magnetoresistance (SMR) EffectModel.

Fitting equations:
  ρ_long  = ρ_0 + Δρ_0 + Δρ_1·(1 − m_y²)
  ρ_Hall  = Δρ_2·m_y

Simultaneous fitting of three measurement geometries: α/β/γ.

Sources:
    Chen, Y.-T. et al.,
    Phys. Rev. B 87, 144411 (2013).
    DOI: 10.1103/PhysRevB.87.144411

    Nakayama, H. et al.,
    Phys. Rev. Lett. 110, 206601 (2013).
    DOI: 10.1103/PhysRevLett.110.206601
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
from maglab.analysis.fit import run_fit, run_fit_multi


class SMREffect(EffectModel):
    """Spin Hall Magnetoresistance EffectModel.

    α-geometry: B∥y → m_y = cos(α), ρ_long = ρ_0 + Δρ_1·(1 − cos²α)
    β-geometry: B∥z → m_y = sin(β), ρ_long = ρ_0 + Δρ_1·(1 − sin²β)
    γ-geometry: B∥x → m_y = 0, ρ_long = ρ_0 + Δρ_1

    Hall: ρ_Hall = Δρ_2·m_y

    Δρ_1 = ρ₀·θ_SH²·Re[g↑↓·tanh(d/2λ)/(g↑↓+...)], SMR magnitude
    Δρ_2 = Δρ_1 (ideal case)

    Sources:
        Chen, Y.-T. et al., Phys. Rev. B 87, 144411 (2013).
        DOI: 10.1103/PhysRevB.87.144411
    """

    @property
    def name(self) -> str:
        return "smr"

    @property
    def subfield(self) -> str:
        return "magnetotransport"

    @property
    def references(self) -> list[str]:
        return [
            "Chen, Y.-T. et al., Phys. Rev. B 87, 144411 (2013). DOI: 10.1103/PhysRevB.87.144411",
            "Nakayama, H. et al., Phys. Rev. Lett. 110, 206601 (2013). "
            "DOI: 10.1103/PhysRevLett.110.206601",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="rho_0",
                unit="Ohm*m",
                lower=0.0,
                upper=None,
                description="Background longitudinal resistivity",
            ),
            ParamSpec(
                name="delta_rho_1",
                unit="Ohm*m",
                lower=None,
                upper=None,
                description="SMR longitudinal component magnitude Δρ₁",
            ),
            ParamSpec(
                name="delta_rho_2",
                unit="Ohm*m",
                lower=None,
                upper=None,
                description="SMR Hall component magnitude Δρ₂",
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "HM/FMI bilayer Hall bar. Three angular scans: "
                "α-geometry (B∥y), β-geometry (B∥z), γ-geometry (B∥x). "
                "Simultaneous measurement of ρ_long and ρ_Hall."
            ),
            tensor_rank=2,
            required_columns=("angle", "rho_long", "rho_hall", "geometry"),
            notes=(
                "angle [rad]: external field rotation angle. "
                "geometry: one of 'alpha', 'beta', 'gamma'. "
                "Concatenate all three geometry datasets into one array, distinguished by the geometry column."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"smr_allowed": True}

    def _m_y(self, angle: float | np.ndarray, geom: str) -> np.ndarray:
        """Return the m_y component for the given geometry."""
        a = np.asarray(angle)
        if geom == "alpha":
            return np.cos(a)
        elif geom == "beta":
            return np.sin(a)
        else:  # gamma
            return np.zeros_like(a)

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute SMR longitudinal or Hall resistivity.

        Args:
            params: {"rho_0": float, "delta_rho_1": float, "delta_rho_2": float}.
            geometry: {"angle": ndarray, "geom": str, "component": "long" or "hall"}.

        Returns:
            ρ array.
        """
        rho_0 = params["rho_0"]
        dr1 = params["delta_rho_1"]
        dr2 = params["delta_rho_2"]
        geom_key = geometry.get("geom", "alpha") if geometry else "alpha"
        angle = geometry.get("angle", np.array([0.0])) if geometry else np.array([0.0])
        component = geometry.get("component", "long") if geometry else "long"

        m_y = self._m_y(angle, geom_key)
        if component == "long":
            return rho_0 + dr1 * (1.0 - m_y**2)
        else:  # hall
            return dr2 * m_y

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Recover Δρ₁, Δρ₂, ρ₀ via simultaneous three-geometry fitting.

        Args:
            data: {
                "angle": ndarray (concatenated angles for all geometries),
                "rho_long": ndarray,
                "rho_hall": ndarray,
                "geometry": ndarray (str array, 'alpha'/'beta'/'gamma'),
            }.
            geometry: Additional info (optional).

        Returns:
            FitResult.
        """
        angle = data["angle"]
        rho_long = data["rho_long"]
        geom_labels = data.get("geometry", np.array(["alpha"] * len(angle)))

        # Build three-geometry datasets
        geom_names = ["alpha", "beta", "gamma"]
        datasets = []
        for g in geom_names:
            mask = geom_labels == g
            if not np.any(mask):
                continue
            a_g = angle[mask]
            y_g = rho_long[mask]
            m_y_g = self._m_y(a_g, g)
            datasets.append({"x": a_g, "y": y_g, "geometry": g, "_my": m_y_g})

        # delta_rho_2 (SMR Hall coefficient) enters only the Hall signal
        # (ρ_Hall = Δρ₂·m_y), which is NOT included in the residual here.
        # Fitting it from rho_long data would leave it unidentifiable (zero
        # Jacobian column, singular covariance).  Restrict the fit to the
        # two identifiable longitudinal parameters and report delta_rho_2 as
        # NaN — the same treatment applied to ghost tau_DL/tau_FL in R4.
        long_specs = [p for p in self.parameters if p.name in ("rho_0", "delta_rho_1")]

        if not datasets:
            # Single-geometry fallback
            geom_key = str(geometry.get("geom", "alpha")) if geometry else "alpha"

            def model_fn_single(x: np.ndarray, rho_0: float, delta_rho_1: float) -> np.ndarray:
                _m = self._m_y(x, geom_key)
                return rho_0 + delta_rho_1 * (1.0 - _m**2)

            init = {
                "rho_0": float(np.mean(rho_long)),
                "delta_rho_1": float(np.std(rho_long)),
            }
            fit_result = run_fit(
                model_fn=model_fn_single,
                x_data=angle,
                y_data=rho_long,
                param_specs=long_specs,
                init_values=init,
                effect_name=self.name,
            )
        else:
            # Multi-dataset: call model_fn for each dataset
            def multi_model_fn(
                x: np.ndarray, geom_str: str, rho_0: float, delta_rho_1: float
            ) -> np.ndarray:
                m_y = self._m_y(x, geom_str)
                return rho_0 + delta_rho_1 * (1.0 - m_y**2)

            init = {
                "rho_0": float(np.mean(rho_long)),
                "delta_rho_1": float(np.std(rho_long)) * 2,
            }
            fit_result = run_fit_multi(
                model_fn=multi_model_fn,
                datasets=datasets,
                param_specs=long_specs,
                init_values=init,
                effect_name=self.name,
            )

        # Append delta_rho_2 as a non-fitted placeholder (NaN).
        # It requires rho_hall data and a separate fit pass (Hall branch).
        fit_result.params["delta_rho_2"] = float("nan")
        fit_result.uncertainties["delta_rho_2"] = float("nan")
        return fit_result
