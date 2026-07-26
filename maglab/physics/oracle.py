"""Sanity oracle — physical range, dimensional, and conservation-law checks.

Deterministically checks whether input parameters are physically valid
and returns structured rejection reasons for non-physical results.

Design principles (PLAN §9, T-P0-04):
  - Fully deterministic — no LLM involvement, no network access.
  - On check failure, returns a structured result rather than raising an exception.
  - All check functions return an ``OracleResult``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from maglab.physics.constants import C_LIGHT

# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OracleResult:
    """Oracle check result.

    Attributes:
        ok: True if physically valid, False if non-physical.
        reason: Reason for check failure (empty string when ok=True).
        param: Name of the problematic parameter.
        value: Problematic value (for debugging).
        checks: List of check names that passed.
    """

    ok: bool
    reason: str = ""
    param: str = ""
    value: Any = None
    checks: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


# ---------------------------------------------------------------------------
# Finiteness guard
# ---------------------------------------------------------------------------


def _non_finite(value: Any, param: str) -> OracleResult | None:
    """Reject NaN and ±inf, or return None when *value* is a finite number.

    Every range check below is a pair of comparisons, and IEEE-754 makes *all*
    comparisons against NaN false — so ``check_damping(nan)`` found α neither
    below 0 nor above 1 and reported the value physical. ``+inf`` slipped through
    the one-sided checks the same way. That defeats the point of the oracle: a
    NaN admitted here propagates silently through the calculation and can be
    recorded as a result, since NaN arithmetic does not raise either.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return OracleResult(
            ok=False,
            reason=f"Parameter {param}={value!r} is not a number.",
            param=param,
            value=value,
        )
    if not math.isfinite(value):
        label = "NaN" if math.isnan(value) else f"{value:+g}"
        return OracleResult(
            ok=False,
            reason=(
                f"Parameter {param}={label} is not a finite number. "
                "NaN and infinity are not physical values."
            ),
            param=param,
            value=value,
        )
    return None


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_damping(alpha: float) -> OracleResult:
    """Check that the Gilbert damping constant α is in range: 0 ≤ α ≤ 1.

    Physical basis: α = 0 is non-physical (perfectly undamped motion does not exist,
    though it is allowed computationally). α > 1 exceeds the overdamped boundary.
    Typical values: Permalloy α ≈ 0.008, YIG α ≈ 0.0002.

    Args:
        alpha: Gilbert damping constant [dimensionless].

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(alpha, "alpha")) is not None:
        return bad
    if alpha < 0.0:
        return OracleResult(
            ok=False,
            reason=f"Damping constant α={alpha:.6g} is negative. α ≥ 0 is required.",
            param="alpha",
            value=alpha,
        )
    if alpha > 1.0:
        return OracleResult(
            ok=False,
            reason=f"Damping constant α={alpha:.6g} exceeds 1. α ≤ 1 is required (overdamping boundary).",
            param="alpha",
            value=alpha,
        )
    return OracleResult(ok=True, checks=["alpha_range"])


def check_magnetization(m: float, ms: float) -> OracleResult:
    """Check that magnetization M does not exceed the saturation magnetization M_s: 0 ≤ |M| ≤ M_s.

    Physical basis: In a ferromagnet, the magnetization magnitude cannot exceed
    the saturation magnetization (upper bound from exchange interaction — §9).

    Args:
        m: Magnetization magnitude [A/m]. Negative values are treated by absolute value.
        ms: Saturation magnetization [A/m]. Must be positive.

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(m, "M")) is not None:
        return bad
    if (bad := _non_finite(ms, "Ms")) is not None:
        return bad
    if ms <= 0.0:
        return OracleResult(
            ok=False,
            reason=f"Saturation magnetization M_s={ms:.6g} A/m is not positive.",
            param="Ms",
            value=ms,
        )
    abs_m = abs(m)
    # Numerical tolerance: 1 ppm (allows for floating-point rounding)
    tol = ms * 1e-6
    if abs_m > ms + tol:
        return OracleResult(
            ok=False,
            reason=f"|M|={abs_m:.6g} A/m > M_s={ms:.6g} A/m. Magnetization exceeds saturation magnetization.",
            param="M",
            value=m,
        )
    return OracleResult(ok=True, checks=["M_le_Ms"])


def check_temperature(t: float) -> OracleResult:
    """Check that temperature T > 0 K (third law of thermodynamics: T = 0 K is unattainable).

    Args:
        t: Temperature [K].

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(t, "T")) is not None:
        return bad
    if t <= 0.0:
        return OracleResult(
            ok=False,
            reason=f"Temperature T={t:.6g} K is at or below 0 K. T > 0 is required.",
            param="T",
            value=t,
        )
    return OracleResult(ok=True, checks=["T_positive"])


def check_velocity(v: float) -> OracleResult:
    """Check that speed |v| < c (speed of light).

    Verifies that domain-wall velocities, skyrmion drift velocities, etc.
    are not in a non-physical regime.
    Practical threshold: domain-wall velocities are typically below a few hundred m/s.

    Args:
        v: Velocity [m/s]. Absolute value is used.

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(v, "velocity")) is not None:
        return bad
    abs_v = abs(v)
    if abs_v >= C_LIGHT:
        return OracleResult(
            ok=False,
            reason=f"|v|={abs_v:.6g} m/s ≥ c={C_LIGHT:.6g} m/s. Velocity exceeds the speed of light.",
            param="velocity",
            value=v,
        )
    return OracleResult(ok=True, checks=["v_lt_c"])


def check_exchange_stiffness(a: float) -> OracleResult:
    """Check that exchange stiffness A > 0.

    Physical basis: In a ferromagnet, the exchange stiffness A must be positive.
    (In antiferromagnets A > 0 as well, but with opposite sign of exchange energy —
    this check assumes ferromagnetic ordering.)

    Args:
        a: Exchange stiffness [J/m].

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(a, "A")) is not None:
        return bad
    if a <= 0.0:
        return OracleResult(
            ok=False,
            reason=f"Exchange stiffness A={a:.6g} J/m is not positive. A > 0 is required for ferromagnets.",
            param="A",
            value=a,
        )
    return OracleResult(ok=True, checks=["A_positive"])


def check_anisotropy(k: float) -> OracleResult:
    """Check the sign of anisotropy constant K — both K > 0 (PMA) and K < 0 (in-plane) are physical.

    However, |K| that is unrealistically large is flagged. (|K| > 1e10 J/m³ is non-physical.)

    Args:
        k: Anisotropy constant [J/m³].

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(k, "K")) is not None:
        return bad
    if abs(k) > 1e10:
        return OracleResult(
            ok=False,
            reason=(
                f"Anisotropy constant |K|={abs(k):.6g} J/m³ is in a non-physical range (|K| ≤ 10¹⁰ J/m³ expected)."
            ),
            param="K",
            value=k,
        )
    return OracleResult(ok=True, checks=["K_range"])


def check_saturation_magnetization(ms: float) -> OracleResult:
    """Check that saturation magnetization M_s > 0.

    Args:
        ms: Saturation magnetization [A/m].

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(ms, "Ms")) is not None:
        return bad
    if ms <= 0.0:
        return OracleResult(
            ok=False,
            reason=f"Saturation magnetization M_s={ms:.6g} A/m is not positive.",
            param="Ms",
            value=ms,
        )
    # Non-physically large value (Fe M_s ≈ 1.7e6 A/m, reasonable upper bound ~1e8 A/m)
    if ms > 1e8:
        return OracleResult(
            ok=False,
            reason=(
                f"Saturation magnetization M_s={ms:.6g} A/m is in a non-physical range "
                "(maximum for magnetic materials is ~1.7 × 10⁶ A/m)."
            ),
            param="Ms",
            value=ms,
        )
    return OracleResult(ok=True, checks=["Ms_range"])


def check_curie_temperature(t_c: float) -> OracleResult:
    """Check that Curie temperature T_C is in range: 0 < T_C < 5000 K.

    Known highest T_C values: Fe₂O₃ ≈ 956 K, CrBr₃ ≈ 37 K, Fe ≈ 1043 K.
    5000 K is set as a non-physical upper bound.

    Args:
        t_c: Curie temperature [K].

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(t_c, "T_C")) is not None:
        return bad
    if t_c <= 0.0:
        return OracleResult(
            ok=False,
            reason=f"Curie temperature T_C={t_c:.6g} K is at or below 0 K.",
            param="T_C",
            value=t_c,
        )
    if t_c > 5000.0:
        return OracleResult(
            ok=False,
            reason=f"Curie temperature T_C={t_c:.6g} K is in a non-physical range (exceeds 5000 K).",
            param="T_C",
            value=t_c,
        )
    return OracleResult(ok=True, checks=["T_C_range"])


def check_exchange_length(l_ex: float) -> OracleResult:
    """Check that exchange length l_ex > 0 and within a reasonable range.

    Typical exchange lengths in magnetic materials: 2 nm (Co) to 500 nm (YIG and soft magnets).

    Args:
        l_ex: Exchange length [m].

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(l_ex, "l_ex")) is not None:
        return bad
    if l_ex <= 0.0:
        return OracleResult(
            ok=False,
            reason=f"Exchange length l_ex={l_ex:.6g} m is not positive.",
            param="l_ex",
            value=l_ex,
        )
    # Non-physical upper bound: 1 mm (1e-3 m)
    if l_ex > 1e-3:
        return OracleResult(
            ok=False,
            reason=f"Exchange length l_ex={l_ex:.6g} m is in a non-physical range (exceeds 1 mm).",
            param="l_ex",
            value=l_ex,
        )
    return OracleResult(ok=True, checks=["l_ex_range"])


def check_energy_conservation(
    e_initial: float,
    e_final: float,
    dissipation: float,
    tol: float = 1e-3,
) -> OracleResult:
    """Simple energy conservation check: E_final ≤ E_initial - dissipation + tol.

    A simplified post-check for spin dynamics simulation results.
    dissipation ≥ 0 (energy must decrease).

    Args:
        e_initial: Initial energy [J/m³].
        e_final: Final energy [J/m³].
        dissipation: Expected energy dissipation [J/m³]. Cannot be negative.
        tol: Relative tolerance (default 0.1%).

    Returns:
        OracleResult.
    """
    if (bad := _non_finite(e_initial, "e_initial")) is not None:
        return bad
    if (bad := _non_finite(e_final, "e_final")) is not None:
        return bad
    if (bad := _non_finite(dissipation, "dissipation")) is not None:
        return bad
    if dissipation < 0.0:
        return OracleResult(
            ok=False,
            reason=f"Dissipated energy {dissipation:.6g} J/m³ is negative.",
            param="dissipation",
            value=dissipation,
        )
    scale = max(abs(e_initial), 1e-30)
    excess = e_final - (e_initial - dissipation)
    if excess > tol * scale:
        return OracleResult(
            ok=False,
            reason=(
                f"Energy conservation violated: E_final={e_final:.6g} exceeds "
                f"E_initial-dissipation={e_initial - dissipation:.6g} by "
                f"{excess:.6g} J/m³ (tolerance {tol * scale:.6g})."
            ),
            param="energy_balance",
            value={"e_initial": e_initial, "e_final": e_final, "dissipation": dissipation},
        )
    return OracleResult(ok=True, checks=["energy_conservation"])


# ---------------------------------------------------------------------------
# Integrated check entry point
# ---------------------------------------------------------------------------


def check(params: dict[str, Any]) -> OracleResult:
    """Accept a parameter dictionary and run all applicable checks.

    Supported keys:
        alpha     : Gilbert damping constant
        M, Ms     : magnetization and saturation magnetization (M ≤ Ms checked when both present)
        Ms        : saturation magnetization range check
        T         : temperature
        velocity  : velocity
        A         : exchange stiffness
        K         : anisotropy constant
        T_C       : Curie temperature
        l_ex      : exchange length

    Args:
        params: Dictionary mapping parameter names to values.

    Returns:
        The first failed check result, or an OracleResult with ok=True if all checks pass.
    """
    passed: list[str] = []

    if "alpha" in params:
        result = check_damping(params["alpha"])
        if not result:
            return result
        passed.extend(result.checks)

    if "Ms" in params:
        result = check_saturation_magnetization(params["Ms"])
        if not result:
            return result
        passed.extend(result.checks)

    if "M" in params and "Ms" in params:
        result = check_magnetization(params["M"], params["Ms"])
        if not result:
            return result
        passed.extend(result.checks)

    if "T" in params:
        result = check_temperature(params["T"])
        if not result:
            return result
        passed.extend(result.checks)

    if "velocity" in params:
        result = check_velocity(params["velocity"])
        if not result:
            return result
        passed.extend(result.checks)

    if "A" in params:
        result = check_exchange_stiffness(params["A"])
        if not result:
            return result
        passed.extend(result.checks)

    if "K" in params:
        result = check_anisotropy(params["K"])
        if not result:
            return result
        passed.extend(result.checks)

    if "T_C" in params:
        result = check_curie_temperature(params["T_C"])
        if not result:
            return result
        passed.extend(result.checks)

    if "l_ex" in params:
        result = check_exchange_length(params["l_ex"])
        if not result:
            return result
        passed.extend(result.checks)

    return OracleResult(ok=True, checks=passed)
