"""Bilevel fitting — deterministic inner layer.

The outer LLM layer proposes the model *form*, and the inner layer optimizes
continuous parameters using lmfit/scipy. The LLM performs no numerical computation —
this module is the deterministic layer. Entered via the `maglab fit --discover` flag.

Design basis: plan/04-analysis.md §11.8, impl/03-P2-analysis.md T-P2-35
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from maglab.analysis.effects.base import FitResult, ParamSpec
from maglab.analysis.fit import FitConvergenceError, run_fit

# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreakerError(RuntimeError):
    """Raised when the maximum number of iterations is exceeded."""


# ---------------------------------------------------------------------------
# Bilevel inner optimization result
# ---------------------------------------------------------------------------


@dataclass
class BilevelResult:
    """Bilevel inner layer optimization result.

    Attributes:
        fit_result: Best FitResult.
        aic: Akaike Information Criterion.
        bic: Bayesian Information Criterion.
        n_iter: Number of attempts made.
        converged: Whether fitting converged.
        model_description: Description of the model form proposed by LLM.
    """

    fit_result: FitResult
    aic: float
    bic: float
    n_iter: int
    converged: bool
    model_description: str = ""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def optimize_inner(
    model_fn: Callable[..., np.ndarray],
    x_data: np.ndarray,
    y_data: np.ndarray,
    param_specs: list[ParamSpec],
    init_candidates: list[dict[str, float]] | None = None,
    max_attempts: int = 5,
    method: str = "leastsq",
    model_description: str = "",
) -> BilevelResult:
    """Inner layer: deterministic continuous parameter optimization.

    Optimizes continuous parameters of a model_fn proposed by LLM using
    multi-start initialization. The LLM calls this function but all numerical
    computation happens here.

    Args:
        model_fn: Symbolic model function generated (and validated) by LLM.
        x_data: Independent variable array.
        y_data: Dependent variable array.
        param_specs: Parameter specification list.
        init_candidates: List of initial value candidates. Uses simple defaults if None.
        max_attempts: Maximum number of initial value attempts (circuit breaker).
        method: lmfit minimization method.
        model_description: Model form description (for provenance).

    Returns:
        BilevelResult.

    Raises:
        CircuitBreakerError: When max_attempts is exceeded.
        FitConvergenceError: When all attempts fail to converge.
    """
    if init_candidates is None:
        # Default initial values: 0 for all params, or midpoint of lower/upper if bounds given
        default_init: dict[str, float] = {}
        for spec in param_specs:
            if spec.lower is not None and spec.upper is not None:
                default_init[spec.name] = (spec.lower + spec.upper) / 2.0
            elif spec.lower is not None:
                default_init[spec.name] = spec.lower + 1.0
            elif spec.upper is not None:
                default_init[spec.name] = spec.upper - 1.0
            else:
                default_init[spec.name] = 0.0
        init_candidates = [default_init]

    if len(init_candidates) > max_attempts:
        raise CircuitBreakerError(
            f"Number of initial value candidates ({len(init_candidates)}) exceeds max_attempts ({max_attempts})."
        )

    best_result: FitResult | None = None
    best_chi2 = float("inf")
    n_iter = 0
    last_error: Exception | None = None

    for init in init_candidates[:max_attempts]:
        n_iter += 1
        try:
            result = run_fit(
                model_fn=model_fn,
                x_data=x_data,
                y_data=y_data,
                param_specs=param_specs,
                init_values=init,
                method=method,
                effect_name=model_description or "bilevel_inner",
            )
            if result.chi2 < best_chi2:
                best_chi2 = result.chi2
                best_result = result
        except FitConvergenceError as e:
            last_error = e
            continue

    if best_result is None:
        raise FitConvergenceError(
            f"All {n_iter} initial value attempts failed to converge. Last error: {last_error}"
        )

    # AIC/BIC calculation
    ndata = len(y_data)
    nvar = len(param_specs)
    aic, bic = _compute_aic_bic(best_result.chi2, ndata, nvar)

    return BilevelResult(
        fit_result=best_result,
        aic=aic,
        bic=bic,
        n_iter=n_iter,
        converged=best_result.success,
        model_description=model_description,
    )


def discover_fit(
    model_fn: Callable[..., np.ndarray],
    x_data: np.ndarray,
    y_data: np.ndarray,
    param_specs: list[ParamSpec],
    init_grid: dict[str, list[float]] | None = None,
    max_attempts: int = 10,
    model_description: str = "",
) -> BilevelResult:
    """--discover flag entry point: grid search over initial values then optimize.

    Args:
        model_fn: Model function to fit.
        x_data: Independent variable.
        y_data: Dependent variable.
        param_specs: Parameter specifications.
        init_grid: {parameter: [value1, value2, ...]} initial value grid.
        max_attempts: Circuit breaker maximum attempt count.
        model_description: Model description.

    Returns:
        BilevelResult.
    """
    # Generate initial value candidates (grid combinations)
    if init_grid is None:
        candidates = None
    else:
        import itertools

        keys = list(init_grid.keys())
        values_list = [init_grid[k] for k in keys]
        candidates = [dict(zip(keys, combo)) for combo in itertools.product(*values_list)]

    return optimize_inner(
        model_fn=model_fn,
        x_data=x_data,
        y_data=y_data,
        param_specs=param_specs,
        init_candidates=candidates,
        max_attempts=max_attempts,
        model_description=model_description,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_aic_bic(chi2: float, ndata: int, nvar: int) -> tuple[float, float]:
    """Compute AIC and BIC.

    AIC = ndata·log(chi2/ndata) + 2·nvar
    BIC = ndata·log(chi2/ndata) + nvar·log(ndata)

    Args:
        chi2: Sum of squared residuals.
        ndata: Number of data points.
        nvar: Number of free parameters.

    Returns:
        (AIC, BIC) tuple.
    """
    if ndata <= 0 or chi2 <= 0:
        return (float("inf"), float("inf"))
    log_term = ndata * np.log(chi2 / ndata)
    aic = log_term + 2.0 * nvar
    bic = log_term + nvar * np.log(ndata)
    return float(aic), float(bic)
