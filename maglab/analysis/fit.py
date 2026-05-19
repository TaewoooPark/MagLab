"""lmfit-based fitting engine — FitResult and run_fit.

Wraps lmfit Minimizer to apply physical bounds, and registers results as
FitResult and DataPoint(FITTED) with provenance.

Design basis: plan/04-analysis.md §11.2·§11.4, impl/03-P2-analysis.md T-P2-07
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import lmfit
import numpy as np

from maglab.analysis.effects.base import FitResult, ParamSpec
from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FitConvergenceError(RuntimeError):
    """Raised when fitting fails to converge or violates physical bounds."""


# ---------------------------------------------------------------------------
# Core fitting functions
# ---------------------------------------------------------------------------


def run_fit(
    model_fn: Callable[..., np.ndarray],
    x_data: np.ndarray,
    y_data: np.ndarray,
    param_specs: list[ParamSpec],
    init_values: dict[str, float],
    method: str = "leastsq",
    weights: np.ndarray | None = None,
    effect_name: str = "",
    max_nfev: int = 10000,
) -> FitResult:
    """Run nonlinear least-squares fitting using lmfit and return a FitResult.

    Args:
        model_fn: Model function (x_data, **params) → y_predicted.
        x_data: Independent variable array.
        y_data: Dependent variable array (measured values).
        param_specs: Parameter specification list (ParamSpec).
        init_values: Initial values dictionary {name: value}.
        method: lmfit minimization method ('leastsq', 'least_squares', 'nelder', etc.).
        weights: Weight array for each data point (optional). Uniform if not provided.
        effect_name: Effect name (for provenance recording).
        max_nfev: Maximum number of function evaluations.

    Returns:
        FitResult instance.

    Raises:
        FitConvergenceError: When fitting fails to converge.
    """
    # Build lmfit Parameters
    lm_params = lmfit.Parameters()
    for spec in param_specs:
        name = spec.name
        init = init_values.get(name, 0.0)
        lm_params.add(
            name,
            value=init,
            min=spec.lower if spec.lower is not None else -np.inf,
            max=spec.upper if spec.upper is not None else np.inf,
        )

    # Residual function
    def residual(p: lmfit.Parameters) -> np.ndarray:
        pv = {k: p[k].value for k in p}
        y_pred = model_fn(x_data, **pv)
        res = y_data - y_pred
        if weights is not None:
            res = res * weights
        return res

    # Minimize
    minimizer = lmfit.Minimizer(residual, lm_params, max_nfev=max_nfev)
    result = minimizer.minimize(method=method)

    # leastsq often converges even with success=False — allow if covar is present
    if not result.success and method == "leastsq" and result.covar is None:
        raise FitConvergenceError(f"Fitting did not converge: {result.message}. Review initial values and bounds.")

    # Extract parameters and uncertainties
    params_out: dict[str, float] = {}
    uncertainties: dict[str, float] = {}
    for name, par in result.params.items():
        params_out[name] = par.value
        uncertainties[name] = par.stderr if par.stderr is not None else 0.0

    # Covariance matrix
    covar = (
        result.covar if result.covar is not None else np.zeros((len(param_specs), len(param_specs)))
    )

    # chi2 calculation
    chi2 = float(np.sum(result.residual**2)) if result.residual is not None else 0.0
    ndata = len(y_data)
    nvar = result.nvarys
    dof = max(ndata - nvar, 1)
    reduced_chi2 = chi2 / dof

    # Register DataPoint(FITTED)
    prov_id = _record_fit_datapoint(params_out, uncertainties, chi2, reduced_chi2, effect_name)

    return FitResult(
        params=params_out,
        uncertainties=uncertainties,
        chi2=chi2,
        reduced_chi2=reduced_chi2,
        covariance=covar,
        provenance_id=prov_id,
        message=result.message or "",
        success=result.success,
        effect_name=effect_name,
        raw_result=result,
    )


def run_fit_multi(
    model_fn: Callable[..., np.ndarray],
    datasets: list[dict[str, Any]],
    param_specs: list[ParamSpec],
    init_values: dict[str, float],
    method: str = "leastsq",
    effect_name: str = "",
    max_nfev: int = 10000,
) -> FitResult:
    """Simultaneously fit multiple datasets (e.g., SMR 3 geometries).

    Args:
        model_fn: Model function (x_data, geometry_key, **params) → y_predicted.
        datasets: [{"x": array, "y": array, "geometry": str}] list.
        param_specs: Parameter specifications.
        init_values: Initial values.
        method: lmfit method.
        effect_name: Effect name.
        max_nfev: Maximum evaluation count.

    Returns:
        FitResult.
    """
    lm_params = lmfit.Parameters()
    for spec in param_specs:
        name = spec.name
        init = init_values.get(name, 0.0)
        lm_params.add(
            name,
            value=init,
            min=spec.lower if spec.lower is not None else -np.inf,
            max=spec.upper if spec.upper is not None else np.inf,
        )

    def residual(p: lmfit.Parameters) -> np.ndarray:
        pv = {k: p[k].value for k in p}
        all_res = []
        for ds in datasets:
            y_pred = model_fn(ds["x"], ds.get("geometry", ""), **pv)
            all_res.append(ds["y"] - y_pred)
        return np.concatenate(all_res)

    minimizer = lmfit.Minimizer(residual, lm_params, max_nfev=max_nfev)
    result = minimizer.minimize(method=method)

    if not result.success and result.covar is None:
        raise FitConvergenceError(f"Multi-dataset fitting did not converge: {result.message}")

    params_out: dict[str, float] = {}
    uncertainties: dict[str, float] = {}
    for name, par in result.params.items():
        params_out[name] = par.value
        uncertainties[name] = par.stderr if par.stderr is not None else 0.0

    covar = (
        result.covar if result.covar is not None else np.zeros((len(param_specs), len(param_specs)))
    )

    total_n = sum(len(ds["y"]) for ds in datasets)
    nvar = result.nvarys
    dof = max(total_n - nvar, 1)
    chi2 = float(np.sum(result.residual**2)) if result.residual is not None else 0.0
    reduced_chi2 = chi2 / dof

    prov_id = _record_fit_datapoint(params_out, uncertainties, chi2, reduced_chi2, effect_name)

    return FitResult(
        params=params_out,
        uncertainties=uncertainties,
        chi2=chi2,
        reduced_chi2=reduced_chi2,
        covariance=covar,
        provenance_id=prov_id,
        message=result.message or "",
        success=result.success,
        effect_name=effect_name,
        raw_result=result,
    )


# ---------------------------------------------------------------------------
# Provenance registration helper
# ---------------------------------------------------------------------------


def _record_fit_datapoint(
    params: dict[str, float],
    uncertainties: dict[str, float],
    chi2: float,
    reduced_chi2: float,
    effect_name: str,
) -> str:
    """Create a DataPoint(FITTED) from fitting results and return its ID."""
    try:
        dp = DataPoint(
            value=list(params.values()),
            units="dimensionless",
            provenance_type=ProvenanceType.FITTED,
            source_ref=f"fit:{effect_name}:{uuid.uuid4().hex[:8]}",
            conditions={
                "effect": effect_name,
                "chi2": chi2,
                "reduced_chi2": reduced_chi2,
                "params": params,
                "uncertainties": uncertainties,
            },
        )
        return dp.id
    except Exception:
        return ""
