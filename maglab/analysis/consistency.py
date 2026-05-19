"""Inconsistency detection — physical consistency checks between two FitResults.

Performs only deterministic checks (no LLM judgment). Returns warnings and an
explain trigger signal on inconsistency.

Design basis: plan/04-analysis.md §11, impl/03-P2-analysis.md T-P2-06
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maglab.analysis.effects.base import FitResult

# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsistencyResult:
    """Inconsistency check result.

    Attributes:
        ok: True = consistent, False = inconsistency detected.
        warnings: List of inconsistency warning messages.
        trigger_explain: Whether to trigger D2 explain.
        details: Detailed inconsistency information.
    """

    ok: bool
    warnings: list[str] = field(default_factory=list)
    trigger_explain: bool = False
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core check functions
# ---------------------------------------------------------------------------


def check_consistency(
    result_a: FitResult,
    result_b: FitResult,
    checks: list[str] | None = None,
) -> ConsistencyResult:
    """Check physical consistency between two independent effect fitting results.

    Example: whether the carrier density extracted from AHE R_0 is consistent
    with a direct Hall effect measurement.

    Args:
        result_a: First FitResult.
        result_b: Second FitResult.
        checks: List of check names to perform. All applicable checks if None.

    Returns:
        ConsistencyResult.
    """
    warnings: list[str] = []
    details: dict[str, Any] = {}

    # Check consistency of shared parameters
    common_params = set(result_a.params.keys()) & set(result_b.params.keys())

    for param in common_params:
        if checks and f"param:{param}" not in checks:
            continue
        val_a = result_a.params[param]
        val_b = result_b.params[param]
        unc_a = result_a.uncertainties.get(param, 0.0)
        unc_b = result_b.uncertainties.get(param, 0.0)

        if not _is_consistent(val_a, val_b, unc_a, unc_b):
            msg = (
                f"Parameter '{param}' inconsistency: "
                f"{result_a.effect_name}={val_a:.4g}±{unc_a:.2g} vs "
                f"{result_b.effect_name}={val_b:.4g}±{unc_b:.2g}"
            )
            warnings.append(msg)
            details[param] = {
                "val_a": val_a,
                "val_b": val_b,
                "unc_a": unc_a,
                "unc_b": unc_b,
                "sigma_pull": _sigma_pull(val_a, val_b, unc_a, unc_b),
            }

    ok = len(warnings) == 0
    trigger = not ok  # Inconsistency triggers D2 explain

    return ConsistencyResult(
        ok=ok,
        warnings=warnings,
        trigger_explain=trigger,
        details=details,
    )


def check_carrier_density_consistency(
    r_0: float,
    r_0_unc: float,
    n_hall: float,
    n_hall_unc: float,
    charge: float = 1.602176634e-19,
    rtol: float = 0.20,
) -> ConsistencyResult:
    """Check consistency between AHE R_0 (ordinary Hall coefficient) and direct Hall measurement.

    Computes n from R_H = R_0 = 1/(n·e) and compares with n_hall.

    Args:
        r_0: Ordinary Hall coefficient R_0 from AHE fitting [m³/C].
        r_0_unc: R_0 uncertainty.
        n_hall: Carrier density from direct Hall measurement [m⁻³].
        n_hall_unc: n_hall uncertainty.
        charge: Charge (default e = 1.60218e-19 C).
        rtol: Relative tolerance (default 20%).

    Returns:
        ConsistencyResult.
    """
    if r_0 == 0.0:
        return ConsistencyResult(
            ok=False,
            warnings=["R_0 = 0: cannot compute carrier density."],
            trigger_explain=True,
        )

    n_from_r0 = 1.0 / (abs(r_0) * charge)
    rel_diff = abs(n_from_r0 - n_hall) / max(n_hall, 1.0)

    if rel_diff > rtol:
        msg = (
            f"Carrier density inconsistency: n from R_0={n_from_r0:.3e} m⁻³ vs "
            f"Hall measurement n={n_hall:.3e} m⁻³ (relative diff={rel_diff:.1%}, tolerance={rtol:.0%})"
        )
        return ConsistencyResult(
            ok=False,
            warnings=[msg],
            trigger_explain=True,
            details={"n_from_r0": n_from_r0, "n_hall": n_hall, "rel_diff": rel_diff},
        )

    return ConsistencyResult(ok=True)


def check_reduced_chi2(
    result: FitResult,
    lower: float = 0.5,
    upper: float = 3.0,
) -> ConsistencyResult:
    """Check whether reduced_chi2 is within the physically valid range.

    Args:
        result: FitResult.
        lower: Lower bound for reduced_chi2 (default 0.5).
        upper: Upper bound for reduced_chi2 (default 3.0).

    Returns:
        ConsistencyResult.
    """
    rc = result.reduced_chi2
    if rc < lower:
        msg = f"reduced_chi2={rc:.3f} < {lower}: possible overfitting or overestimated uncertainty."
        return ConsistencyResult(ok=False, warnings=[msg], trigger_explain=False)
    if rc > upper:
        msg = (
            f"reduced_chi2={rc:.3f} > {upper}: poor model fit or heterogeneous data. "
            f"Effect '{result.effect_name}' should be reviewed."
        )
        return ConsistencyResult(ok=False, warnings=[msg], trigger_explain=True)
    return ConsistencyResult(ok=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_consistent(
    val_a: float,
    val_b: float,
    unc_a: float,
    unc_b: float,
    n_sigma: float = 3.0,
) -> bool:
    """Deterministically compare whether two values agree within n_sigma confidence."""
    combined_unc = (unc_a**2 + unc_b**2) ** 0.5
    if combined_unc == 0.0:
        return abs(val_a - val_b) < 1e-10 * max(abs(val_a), abs(val_b), 1.0)
    return abs(val_a - val_b) <= n_sigma * combined_unc


def _sigma_pull(val_a: float, val_b: float, unc_a: float, unc_b: float) -> float:
    """Return the sigma pull (standardized residual) between two measurements."""
    combined_unc = (unc_a**2 + unc_b**2) ** 0.5
    if combined_unc == 0.0:
        return float("inf")
    return abs(val_a - val_b) / combined_unc
