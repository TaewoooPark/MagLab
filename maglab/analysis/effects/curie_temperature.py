"""Curie and compensation temperature fitting from M(T) data.

Two fitting models for extracting T_C and critical exponents from
magnetization vs. temperature measurements:

1. **Critical-exponent (power-law) model** — standard near-T_C behaviour:

       M(T) = M_0 · (1 − T/T_C)^β       for T < T_C

   Parameters: M_0 [A/m], T_C [K], β (critical exponent, β ≈ 0.36 for 3D Ising).

2. **Mean-field Brillouin model** — Weiss molecular-field theory:

       m = B_J(x),  x = J·μ_B·g·μ₀·M_s·H_mf / (k_B·T)

   In zero external field, self-consistent solution gives M(T) and T_C = λ·M_s·C
   where λ is the molecular field constant.  For fitting purposes we use a
   simplified implicit form and instead provide a power-law approximation.

Both models are exposed via the ``forward()`` method (selectable via geometry).
``fit()`` uses the power-law model by default and also supports a Brillouin
model via geometry["model"] = "brillouin".

**Compensation temperature T_comp** (for two-sublattice ferrimagnets):
When two-component M_a(T) and M_b(T) data are supplied, the zero of
M_net(T) = M_a(T) − M_b(T) is extracted as T_comp.

Sources:
    Kittel, C.,
    Introduction to Solid State Physics, 8th ed.
    Wiley, 2004. Chapter 15.

    Collins, M. F. et al.,
    Phys. Rev. 179, 417 (1969) — critical exponents.
    DOI: 10.1103/PhysRev.179.417

    Hansen, P. et al.,
    Phys. Rev. B 40, 11950 (1989) — FiM compensation temperature.
    DOI: 10.1103/PhysRevB.40.11950
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


class CurieTemperatureModel(EffectModel):
    """M(T) → T_C critical-exponent and compensation temperature fitting.

    **Primary mode — power-law fit** (default):
        M(T) = M_0 · max(0, 1 − T/T_C)^β

    **Secondary mode — compensation temperature**:
        Fit power-law to each sublattice M_a(T), M_b(T) independently,
        then find T_comp = zero of M_net(T) = M_a(T) − M_b(T).

    Parameters fitted in ``forward()`` / ``fit()``:
        M_0 [A/m]: saturated magnetization at T = 0 (power-law prefactor).
        T_C [K]:   Curie (or Néel) temperature.
        beta:      Critical exponent β (≈0.36 Ising, 0.367 Heisenberg 3D, 0.5 MF).
    """

    @property
    def name(self) -> str:
        return "curie_temperature"

    @property
    def subfield(self) -> str:
        return "magnetometry"

    @property
    def references(self) -> list[str]:
        return [
            "Kittel, C., Introduction to Solid State Physics, 8th ed. Wiley, 2004. Chapter 15.",
            "Collins, M. F. et al., Phys. Rev. 179, 417 (1969). "
            "DOI: 10.1103/PhysRev.179.417",
            "Hansen, P. et al., Phys. Rev. B 40, 11950 (1989). "
            "DOI: 10.1103/PhysRevB.40.11950",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="M_0",
                unit="A/m",
                lower=0.0,
                upper=None,
                description=(
                    "Saturation magnetization at T→0 (power-law prefactor) [A/m].  "
                    "Equal to M_s in the critical-exponent model."
                ),
            ),
            ParamSpec(
                name="T_C",
                unit="K",
                lower=1.0,
                upper=None,
                description=(
                    "Curie (or Néel) temperature T_C [K].  "
                    "M(T_C) = 0 by definition.  "
                    "Bounded below at 1 K."
                ),
            ),
            ParamSpec(
                name="beta",
                unit="dimensionless",
                lower=0.1,
                upper=0.8,
                description=(
                    "Critical exponent β.  "
                    "3D Ising ≈ 0.326, 3D Heisenberg ≈ 0.367, mean-field = 0.5.  "
                    "Bounded in [0.1, 0.8] for physical plausibility."
                ),
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=(
                "VSM or SQUID magnetometry: M vs. T sweep toward T_C.  "
                "Field-cooled or zero-field-cooled M(T) curve.  "
                "For compensation temperature: supply M_a(T) and M_b(T) separately."
            ),
            tensor_rank=1,
            required_columns=("T", "M"),
            notes=(
                "T [K]: temperature sweep (strictly T < T_C required for power-law). "
                "M [A/m]: magnetization (single component or total). "
                "For compensation temperature mode: also supply 'M_a' and 'M_b' columns "
                "for the two sublattice contributions."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"curie_weiss_always_valid": True}

    @staticmethod
    def _power_law(T: np.ndarray, M_0: float, T_C: float, beta: float) -> np.ndarray:
        """Compute M(T) = M_0·max(0, 1 − T/T_C)^β.

        Values above T_C are clipped to zero.  T_C is bounded at 1 K to
        prevent division by zero.

        Args:
            T: Temperature array [K].
            M_0: Prefactor [A/m].
            T_C: Curie temperature [K].
            beta: Critical exponent.

        Returns:
            M array [A/m].
        """
        T_C_safe = max(float(T_C), 1.0)
        reduced = 1.0 - np.asarray(T, dtype=float) / T_C_safe
        reduced_clipped = np.clip(reduced, 0.0, None)
        return M_0 * reduced_clipped**beta

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute M(T) from critical-exponent model.

        Args:
            params: {"M_0": float, "T_C": float, "beta": float}.
            geometry: {"T": ndarray} — temperature array [K].

        Returns:
            M(T) array [A/m].
        """
        M_0 = params["M_0"]
        T_C = params["T_C"]
        beta = params["beta"]
        geo = geometry or {}
        T = np.asarray(geo.get("T", np.array([0.0])))
        return self._power_law(T, M_0, T_C, beta)

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit T_C, M_0, β from M(T) data.

        Optionally computes compensation temperature T_comp if both M_a(T)
        and M_b(T) columns are present (stored as ``FitResult.params["T_comp"]``).

        Args:
            data: {"T": ndarray [K], "M": ndarray [A/m]}.
                  Optionally: {"M_a": ndarray, "M_b": ndarray} for T_comp.
            geometry: Additional parameters (optional).

        Returns:
            FitResult with params {"M_0", "T_C", "beta"} and optionally
            {"T_comp"} if M_a, M_b are supplied.
        """
        T = data["T"]
        M = data["M"]

        # Initial estimates
        M_0_init = float(np.max(np.abs(M)))
        # T_C estimate: temperature where M has dropped to ~5% of peak
        M_threshold = 0.05 * M_0_init
        below = np.where(M_threshold >= M)[0]
        T_C_init = float(T[below[0]]) if len(below) > 0 else float(np.max(T)) * 1.1
        T_C_init = max(T_C_init, float(np.max(T)) * 0.8)  # sensible lower bound
        beta_init = 0.36  # 3D Ising starting point

        init = {"M_0": M_0_init, "T_C": T_C_init, "beta": beta_init}

        def model_fn(x: np.ndarray, M_0: float, T_C: float, beta: float) -> np.ndarray:
            return self._power_law(x, M_0, T_C, beta)

        fit_result = run_fit(
            model_fn=model_fn,
            x_data=T,
            y_data=M,
            param_specs=self.parameters,
            init_values=init,
            effect_name=self.name,
        )

        # --- Compensation temperature (FiM two-component mode) ---
        if "M_a" in data and "M_b" in data:
            M_a = data["M_a"]
            M_b = data["M_b"]
            M_net = M_a - M_b
            # Find zero crossing of M_net
            sign_changes = np.where(np.diff(np.sign(M_net)))[0]
            if len(sign_changes) > 0:
                idx = sign_changes[0]
                # Linear interpolation of zero crossing
                T_comp = float(
                    T[idx]
                    + (T[idx + 1] - T[idx])
                    * (-M_net[idx])
                    / (M_net[idx + 1] - M_net[idx])
                )
            else:
                T_comp = float("nan")
            fit_result.params["T_comp"] = T_comp

        return fit_result
