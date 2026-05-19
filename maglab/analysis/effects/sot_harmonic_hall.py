"""SOT harmonic Hall EffectModel.

Separate damping-like (H_DL) and field-like (H_FL) SOT effective fields from 1ω·2ω angular dependence.
Includes fully integrated PHE correction: H_DL = (H_DL_raw − 2ξ·H_FL_raw) / (1 − 4ξ²)

PHE correction integration workflow
------------------------------------
ξ = R_PHE / (2·R_AHE) is the PHE-to-AHE amplitude ratio measured from the
*1ω signal* in the same experiment.  It cannot be uniquely extracted from
the 2ω signal alone (the 2ω cross-terms collapse to an equivalent two-term
expansion — see Hayashi 2014 §II.C).

Integrated path supported by this model:
1. fit() fits H_DL_raw and H_FL_raw from 2ω data.
2. xi is supplied via geometry["xi"] (measured from 1ω) or data["V_1omega"]
   (if 1ω data is co-supplied, xi is estimated from the R_PHE/2R_AHE ratio).
3. PHE correction is applied *automatically* inside fit() — PHE-corrected
   H_DL and H_FL appear directly in FitResult.params without any manual
   post-processing step.

Sources:
    Hayashi, M. et al.,
    Phys. Rev. B 89, 144425 (2014).
    DOI: 10.1103/PhysRevB.89.144425

    Garello, K. et al.,
    Nat. Nanotechnol. 8, 587 (2013).
    DOI: 10.1038/nnano.2013.145
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


class SOTHarmonicHall(EffectModel):
    """SOT harmonic Hall EffectModel.

    1ω signal: V_1ω ∝ (R_AHE/2)·cos(φ) + R_PHE·sin(2φ)·sin(φ)
    2ω signal: V_2ω ∝ H_DL_raw·cos(φ)/H_ext + H_FL_raw·cos(2φ)·cos(φ)/H_ext

    Simplified angular dependence (Hayashi 2014):
    V_2ω ∝ H_DL·cos(φ) + 2·H_FL·cos(2φ)·cos(φ)

    PHE correction (auto-applied in fit()):
    H_DL = (H_DL_raw − 2ξ·H_FL_raw) / (1 − 4ξ²)
    ξ = R_PHE / (2·R_AHE)  (PHE-to-AHE ratio, from 1ω measurement)

    The ξ parameter is sourced from:
    - geometry["xi"] if provided explicitly from 1ω measurement.
    - Estimated from data["V_1omega"] if co-supplied (linear regression of
      R_PHE/2R_AHE from 1ω signal amplitudes).
    - Defaults to 0.0 (no PHE correction) if neither is supplied.

    Sources:
        Hayashi, M. et al., Phys. Rev. B 89, 144425 (2014).
        DOI: 10.1103/PhysRevB.89.144425
    """

    @property
    def name(self) -> str:
        return "sot_harmonic_hall"

    @property
    def subfield(self) -> str:
        return "spin_orbitronics"

    @property
    def references(self) -> list[str]:
        return [
            "Hayashi, M. et al., Phys. Rev. B 89, 144425 (2014). DOI: 10.1103/PhysRevB.89.144425",
            "Garello, K. et al., Nat. Nanotechnol. 8, 587 (2013). DOI: 10.1038/nnano.2013.145",
        ]

    @property
    def parameters(self) -> list[ParamSpec]:
        return [
            ParamSpec(
                name="H_DL_raw",
                unit="A/m",
                lower=None,
                upper=None,
                description="Damping-like SOT effective field (before PHE correction)",
            ),
            ParamSpec(
                name="H_FL_raw",
                unit="A/m",
                lower=None,
                upper=None,
                description="Field-like SOT effective field (before PHE correction)",
            ),
            ParamSpec(
                name="xi",
                unit="dimensionless",
                lower=-0.49,
                upper=0.49,
                description=(
                    "PHE/AHE correction ratio ξ = R_PHE/(2·R_AHE).  "
                    "This parameter is NOT a free fit parameter of the 2ω signal — "
                    "it is measured from the 1ω signal and supplied via geometry['xi'] "
                    "or estimated from data['V_1omega'].  "
                    "Bounded |ξ| < 0.5 to keep PHE denominator (1−4ξ²) > 0."
                ),
            ),
        ]

    @property
    def measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            geometry=("In-plane external field φ rotation + simultaneous lock-in 1ω·2ω recording. HM/FM bilayer, I_rf∥x."),
            tensor_rank=2,
            required_columns=("phi", "V_2omega"),
            notes=(
                "phi [rad]: in-plane field azimuthal angle. "
                "V_2omega [V]: second-harmonic Hall voltage. "
                "Optionally supply V_1omega [V] or provide xi in geometry to enable "
                "integrated PHE correction.  "
                "FitResult.params always contains H_DL_raw, H_FL_raw, xi (from input "
                "or 0.0 default) and PHE-corrected H_DL, H_FL."
            ),
        )

    @property
    def symmetry_constraints(self) -> dict[str, Any]:
        return {"sot_allowed": True}

    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute 2ω angular dependence signal.

        Standard two-term model (Hayashi 2014, Eq. 6):

            V_2ω ≈ (H_DL_raw / H_ext)·cos(φ)
                  + (H_FL_raw / H_ext)·cos(2φ)·cos(φ)

        The ``xi`` parameter in ``params`` does not alter the signal shape
        (it is a geometry-supplied correction applied post-fit — see ``fit()``).

        Args:
            params: {"H_DL_raw": float, "H_FL_raw": float, "xi": float}.
            geometry: {"phi": ndarray, "H_ext": float (external field [A/m])}.

        Returns:
            V_2ω array (same units as inputs normalised by H_ext).
        """
        H_DL_raw = params["H_DL_raw"]
        H_FL_raw = params["H_FL_raw"]
        phi = geometry["phi"] if geometry and "phi" in geometry else np.array([0.0])
        H_ext = geometry.get("H_ext", 1.0) if geometry else 1.0

        return (H_DL_raw / H_ext) * np.cos(phi) + (H_FL_raw / H_ext) * np.cos(2.0 * phi) * np.cos(
            phi
        )

    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Fit H_DL_raw, H_FL_raw from 2ω φ-sweep data with integrated PHE correction.

        The PHE correction ratio ξ is obtained from:
        1. ``geometry["xi"]`` if explicitly provided (from 1ω measurement).
        2. Estimated from ``data["V_1omega"]`` if present: the 1ω signal is
           modelled as V_1ω = (R_AHE/2)·cos(φ) + R_PHE·sin(2φ)·sin(φ), and
           ξ = R_PHE / (2·R_AHE) is extracted by linear regression.
        3. Defaults to 0.0 (no correction) if neither is supplied.

        After fitting H_DL_raw and H_FL_raw, the PHE-corrected fields H_DL
        and H_FL are automatically computed via ``phe_corrected()`` and stored
        in ``FitResult.params``.  The user never needs to call
        ``phe_corrected()`` manually.

        Args:
            data: {
                "phi": ndarray [rad],
                "V_2omega": ndarray [V],
                "V_1omega": ndarray [V] (optional — enables auto xi estimation),
            }.
            geometry: {
                "H_ext": float [A/m] (external field magnitude),
                "xi": float (optional — PHE correction ratio from 1ω measurement),
            }.

        Returns:
            FitResult with params:
                H_DL_raw [A/m], H_FL_raw [A/m] — fitted from 2ω data,
                xi [dimensionless] — supplied or estimated (0.0 default),
                H_DL [A/m], H_FL [A/m] — PHE-corrected fields (auto-computed).
        """
        phi = data["phi"]
        V_2w = data["V_2omega"]
        geo = geometry or {}
        H_ext = float(geo.get("H_ext", 1.0))

        # --- Determine xi (PHE correction ratio) ---
        if "xi" in geo:
            xi_val = float(geo["xi"])
        elif "V_1omega" in data:
            # Estimate ξ from 1ω signal: V_1ω = A_AHE·cos(φ) + A_PHE·sin(2φ)·sin(φ)
            V_1w = data["V_1omega"]
            A_1w = np.column_stack([np.cos(phi), np.sin(2.0 * phi) * np.sin(phi)])
            try:
                c = np.linalg.lstsq(A_1w, V_1w, rcond=None)[0]
                # Regression coefficients: c[0] = R_AHE/2, c[1] = R_PHE.
                # Hayashi (2014) defines xi = R_PHE / (2*R_AHE).
                # Substituting R_AHE = 2*c[0]:
                #   xi = c[1] / (2 * 2*c[0]) = c[1] / (4*c[0])
                xi_val = float(c[1] / (4.0 * c[0])) if abs(c[0]) > 1e-30 else 0.0
            except Exception:
                xi_val = 0.0
        else:
            xi_val = 0.0

        # --- Fit H_DL_raw and H_FL_raw from 2ω data ---
        # Only fit these two physically meaningful parameters (xi is geometry input)
        fit_specs = [
            ParamSpec("H_DL_raw", "A/m", lower=None, upper=None,
                      description="Damping-like SOT effective field (before PHE correction)"),
            ParamSpec("H_FL_raw", "A/m", lower=None, upper=None,
                      description="Field-like SOT effective field (before PHE correction)"),
        ]
        A_mat = np.column_stack([np.cos(phi), np.cos(2.0 * phi) * np.cos(phi)])
        try:
            coeffs = np.linalg.lstsq(A_mat, V_2w, rcond=None)[0]
            init = {
                "H_DL_raw": float(coeffs[0]) * H_ext,
                "H_FL_raw": float(coeffs[1]) * H_ext,
            }
        except Exception:
            init = {"H_DL_raw": 1.0, "H_FL_raw": 1.0}

        _H_ext = H_ext

        def model_fn(x: np.ndarray, H_DL_raw: float, H_FL_raw: float) -> np.ndarray:
            return (H_DL_raw / _H_ext) * np.cos(x) + (H_FL_raw / _H_ext) * np.cos(
                2.0 * x
            ) * np.cos(x)

        fit_result = run_fit(
            model_fn=model_fn,
            x_data=phi,
            y_data=V_2w,
            param_specs=fit_specs,
            init_values=init,
            effect_name=self.name,
        )

        # Insert xi into params (measured/estimated, not fitted from 2ω)
        fit_result.params["xi"] = xi_val

        # --- PHE correction: auto-apply and store corrected fields ---
        try:
            H_DL_corr, H_FL_corr = self.phe_corrected(
                fit_result.params["H_DL_raw"],
                fit_result.params["H_FL_raw"],
                xi_val,
            )
        except ValueError:
            # |ξ| ≥ 0.5 — correction denominator near zero; store NaN
            H_DL_corr, H_FL_corr = float("nan"), float("nan")

        fit_result.params["H_DL"] = H_DL_corr
        fit_result.params["H_FL"] = H_FL_corr

        return fit_result

    @staticmethod
    def phe_corrected(H_DL_raw: float, H_FL_raw: float, xi: float) -> tuple[float, float]:
        """Return PHE-corrected H_DL and H_FL.

        H_DL = (H_DL_raw − 2ξ·H_FL_raw) / (1 − 4ξ²)
        H_FL = (H_FL_raw − 2ξ·H_DL_raw) / (1 − 4ξ²)

        Args:
            H_DL_raw: H_DL before correction.
            H_FL_raw: H_FL before correction.
            xi: PHE correction ratio.

        Returns:
            (H_DL, H_FL) corrected values.
        """
        denom = 1.0 - 4.0 * xi**2
        if abs(denom) < 1e-15:
            raise ValueError(f"PHE correction denominator=0: ξ={xi}. Requires |ξ| < 0.5.")
        H_DL = (H_DL_raw - 2.0 * xi * H_FL_raw) / denom
        H_FL = (H_FL_raw - 2.0 * xi * H_DL_raw) / denom
        return H_DL, H_FL
