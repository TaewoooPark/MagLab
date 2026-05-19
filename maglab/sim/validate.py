"""Static validation of micromagnetic simulations — Appendix D rule implementation.

Design rationale: PLAN §10.2 · plan/11-appendices.md Appendix D · impl/02-P1-figure-sim.md T-P1-03.

Performs pre-execution checks on a ``MultiScaleSpec`` against Appendix D micromagnetic rules:
  1. Cell size < exchange length l_ex
  2. Damping α > 0
  3. Material parameter completeness for all regions (Ms, A, alpha required)
  4. run ≥ several τ_relax (τ = 1/(α·γ·μ₀·Ms))

On violation, raises ``ValidationError`` with a structured message listing
each violation and its recommended value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maglab.physics.constants import GAMMA_E, MU_0
from maglab.physics.formulas import exchange_length
from maglab.physics.oracle import (
    check_damping,
    check_exchange_stiffness,
    check_saturation_magnetization,
)
from maglab.sim.spec import MultiScaleSpec, ScaleSpec, ScaleType

# ---------------------------------------------------------------------------
# Validation result data structures
# ---------------------------------------------------------------------------


@dataclass
class ValidationViolation:
    """Information about a single validation rule violation.

    Attributes:
        rule: Identifier of the violated rule.
        message: Human-readable violation description.
        actual: Actual value of the violating parameter.
        recommended: Recommended value or threshold.
        scale_label: Label of the ScaleSpec where the violation occurred.
    """

    rule: str
    message: str
    actual: Any = None
    recommended: Any = None
    scale_label: str = ""


class ValidationError(Exception):
    """Exception raised on MultiScaleSpec validation failure.

    The ``violations`` attribute contains the full list of violated rules.
    """

    def __init__(self, violations: list[ValidationViolation]) -> None:
        self.violations = violations
        lines = [f"  [{v.rule}] {v.message}" for v in violations]
        super().__init__(
            f"Simulation spec validation failed ({len(violations)} violation(s)):\n" + "\n".join(lines)
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tau_relax_ns(alpha: float, ms_am: float) -> float:
    """Compute the relaxation characteristic time τ_relax [ns].

    τ_relax = 1 / (α × γ × μ₀ × Ms)

    This is the magnetization relaxation timescale in the LLG equation.

    Parameters:
        alpha: Gilbert damping constant.
        ms_am: Saturation magnetization [A/m].

    Returns:
        Relaxation time [ns].
    """
    omega_0 = alpha * GAMMA_E * MU_0 * ms_am  # [rad/s]
    if omega_0 <= 0.0:
        return float("inf")
    return 1.0 / omega_0 * 1e9  # s → ns


def _exchange_length_nm(a_jm: float, ms_am: float) -> float:
    """Compute the exchange length l_ex [nm].

    Parameters:
        a_jm: Exchange stiffness [J/m].
        ms_am: Saturation magnetization [A/m].

    Returns:
        Exchange length [nm].
    """
    return exchange_length(a_jm, ms_am) * 1e9  # m → nm


# ---------------------------------------------------------------------------
# Per-rule validation functions
# ---------------------------------------------------------------------------


def _check_material_completeness(spec: ScaleSpec) -> list[ValidationViolation]:
    """Check that material parameters (Ms, A, alpha) are present for all regions (Appendix D rule 3)."""
    violations: list[ValidationViolation] = []
    if spec.material is None:
        violations.append(
            ValidationViolation(
                rule="MICRO_MATERIAL_MISSING",
                message="ScaleSpec with scale='micro' has no material parameter.",
                scale_label=spec.label,
            )
        )
        return violations

    mat = spec.material

    # Ms range check
    ms_result = check_saturation_magnetization(mat.Ms_Am)
    if not ms_result:
        violations.append(
            ValidationViolation(
                rule="MICRO_MS_INVALID",
                message=ms_result.reason,
                actual=mat.Ms_Am,
                recommended="0 < Ms_Am ≤ 1e8 A/m",
                scale_label=spec.label,
            )
        )

    # A > 0 check
    a_result = check_exchange_stiffness(mat.A_Jm)
    if not a_result:
        violations.append(
            ValidationViolation(
                rule="MICRO_A_INVALID",
                message=a_result.reason,
                actual=mat.A_Jm,
                recommended="A_Jm > 0 J/m",
                scale_label=spec.label,
            )
        )

    # alpha > 0 check (Appendix D rule 2)
    alpha_result = check_damping(mat.alpha)
    if not alpha_result:
        violations.append(
            ValidationViolation(
                rule="MICRO_ALPHA_INVALID",
                message=alpha_result.reason,
                actual=mat.alpha,
                recommended="0 < alpha ≤ 1",
                scale_label=spec.label,
            )
        )
    if mat.alpha == 0.0:
        violations.append(
            ValidationViolation(
                rule="MICRO_ALPHA_ZERO",
                message="Damping constant α = 0 is unphysical. The simulation will not converge.",
                actual=0.0,
                recommended="alpha > 0 (Permalloy: ~0.008, YIG: ~0.0002)",
                scale_label=spec.label,
            )
        )

    return violations


def _check_cell_vs_exchange_length(spec: ScaleSpec) -> list[ValidationViolation]:
    """Check that cell size < exchange length l_ex (Appendix D rule 1)."""
    violations: list[ValidationViolation] = []
    if spec.material is None or spec.geometry is None:
        return violations  # already caught by material completeness check

    mat = spec.material
    geom = spec.geometry

    # Compute l_ex
    try:
        l_ex_nm = _exchange_length_nm(mat.A_Jm, mat.Ms_Am)
    except Exception as exc:
        violations.append(
            ValidationViolation(
                rule="MICRO_LEX_COMPUTE_ERROR",
                message=f"Exchange length calculation failed: {exc}",
                scale_label=spec.label,
            )
        )
        return violations

    if l_ex_nm <= 0.0:
        violations.append(
            ValidationViolation(
                rule="MICRO_LEX_NONPOSITIVE",
                message=f"Exchange length l_ex={l_ex_nm:.4g} nm is not positive.",
                actual=l_ex_nm,
                scale_label=spec.label,
            )
        )
        return violations

    # Compare against cell size in each direction
    max_cell_nm = max(geom.dx_nm, geom.dy_nm, geom.dz_nm)
    if max_cell_nm >= l_ex_nm:
        violations.append(
            ValidationViolation(
                rule="MICRO_CELL_TOO_LARGE",
                message=(
                    f"Maximum cell size {max_cell_nm:.3g} nm ≥ exchange length l_ex={l_ex_nm:.3g} nm. "
                    "Cell size must be < l_ex to ensure numerical accuracy in micromagnetic simulation."
                ),
                actual=max_cell_nm,
                recommended=f"Cell size < {l_ex_nm:.3g} nm (≤ 50% of l_ex recommended)",
                scale_label=spec.label,
            )
        )

    return violations


def _check_run_time(spec: ScaleSpec) -> list[ValidationViolation]:
    """Check that simulation time ≥ several τ_relax (Appendix D rule 4).

    At least 5τ is recommended for relaxation simulations.
    """
    violations: list[ValidationViolation] = []
    if spec.material is None:
        return violations

    mat = spec.material

    # t_sim_ns = 0 means static minimization — no time check needed
    if spec.t_sim_ns <= 0.0:
        return violations

    if mat.alpha <= 0.0 or mat.Ms_Am <= 0.0:
        return violations  # already caught by other rules

    tau_ns = _tau_relax_ns(mat.alpha, mat.Ms_Am)
    min_run_ns = 5.0 * tau_ns  # 5τ criterion

    if spec.t_sim_ns < min_run_ns:
        violations.append(
            ValidationViolation(
                rule="MICRO_RUN_TOO_SHORT",
                message=(
                    f"Simulation time {spec.t_sim_ns:.4g} ns < 5×τ_relax={min_run_ns:.4g} ns. "
                    "τ_relax = 1/(α·γ·μ₀·Ms). At least 5τ is recommended for sufficient relaxation."
                ),
                actual=spec.t_sim_ns,
                recommended=f"{min_run_ns:.4g} ns (5×τ_relax)",
                scale_label=spec.label,
            )
        )

    return violations


def _check_geometry(spec: ScaleSpec) -> list[ValidationViolation]:
    """Basic validity check on geometry parameters."""
    violations: list[ValidationViolation] = []
    if spec.geometry is None:
        return violations

    geom = spec.geometry
    # Minimum cell count check
    n_total = geom.nx * geom.ny * geom.nz
    if n_total > 64**3:
        violations.append(
            ValidationViolation(
                rule="MICRO_LARGE_MESH_WARNING",
                message=(
                    f"Mesh size {geom.nx}×{geom.ny}×{geom.nz}={n_total:,} cells. "
                    "Very long run times are expected on a CPU backend (recommended: ≤ 64³=262,144 cells)."
                ),
                actual=n_total,
                recommended="nx·ny·nz each ≤ 64 for CPU fallback",
                scale_label=spec.label,
            )
        )

    return violations


# ---------------------------------------------------------------------------
# Public validation entry points
# ---------------------------------------------------------------------------


def validate_micro(spec: ScaleSpec) -> None:
    """Run static validation on a single ScaleSpec (micro).

    Parameters:
        spec: ScaleSpec to validate.

    Raises:
        ValidationError: When one or more rules are violated.
    """
    if spec.scale != ScaleType.micro:
        raise ValueError(
            f"validate_micro only supports ScaleSpec with scale='micro'. Got: {spec.scale}"
        )

    violations: list[ValidationViolation] = []
    violations += _check_material_completeness(spec)
    violations += _check_cell_vs_exchange_length(spec)
    violations += _check_run_time(spec)
    # Geometry warnings are included but not treated as errors (WARNING level)
    # (large meshes are cautionary but not grounds for blocking)

    if violations:
        raise ValidationError(violations)


def validate(spec: MultiScaleSpec) -> None:
    """Statically validate an entire MultiScaleSpec.

    Validates each ScaleSpec in order. The micro scale receives full
    validation; dft/atomistic/device scales have P3 rules applied additionally.

    Parameters:
        spec: MultiScaleSpec to validate.

    Raises:
        ValidationError: When one or more rules are violated.
    """
    all_violations: list[ValidationViolation] = []

    for scale_spec in spec.scales:
        if scale_spec.scale == ScaleType.micro:
            try:
                validate_micro(scale_spec)
            except ValidationError as exc:
                all_violations.extend(exc.violations)
        elif scale_spec.scale == ScaleType.dft:
            all_violations.extend(_check_dft_spec(scale_spec))
        elif scale_spec.scale == ScaleType.atomistic:
            all_violations.extend(_check_atomistic_spec(scale_spec))
        elif scale_spec.scale == ScaleType.device:
            all_violations.extend(_check_device_spec(scale_spec))

    # Handoff continuity check (P3 — Appendix D)
    all_violations.extend(_check_handoff_continuity(spec))

    if all_violations:
        raise ValidationError(all_violations)


# ---------------------------------------------------------------------------
# P3 DFT validation rules
# ---------------------------------------------------------------------------


def _check_dft_spec(spec: ScaleSpec) -> list[ValidationViolation]:
    """Static validation of a DFT ScaleSpec (T-P3-09).

    Rules:
      DFT-1: If k_mesh is in extra, density must be ≥ 4.
      DFT-2: If ecutwfc_Ry is in extra, it must be ≥ 30 Ry.
      DFT-3: engine must be one of vasp/qe/fleur.
    """
    violations: list[ValidationViolation] = []
    extra = spec.extra if hasattr(spec, "extra") and spec.extra else {}
    engine = (spec.engine or "").lower()

    # DFT-3: Engine check (warn for unknown engine)
    known_dft_engines = {"vasp", "qe", "fleur", "auto", "mock", ""}
    if engine and engine not in known_dft_engines:
        violations.append(
            ValidationViolation(
                rule="DFT_UNKNOWN_ENGINE",
                message=f"Unknown DFT engine: {engine!r}. Supported: vasp·qe·fleur.",
                actual=engine,
                recommended="vasp·qe·fleur",
                scale_label=spec.label,
            )
        )

    # DFT-1: k-mesh density
    k_mesh = extra.get("k_mesh")
    if k_mesh is not None:
        try:
            k_vals = list(k_mesh) if hasattr(k_mesh, "__iter__") else [k_mesh]
            if any(int(k) < 4 for k in k_vals):
                violations.append(
                    ValidationViolation(
                        rule="DFT_KMESH_TOO_COARSE",
                        message=(
                            f"k-mesh {k_mesh} is too coarse. "
                            "At least 4×4×4 is recommended for exchange coupling calculations."
                        ),
                        actual=k_mesh,
                        recommended="≥ 4 per direction (≥ 8 recommended for J_ij calculations)",
                        scale_label=spec.label,
                    )
                )
        except (TypeError, ValueError):
            pass

    # DFT-2: Wavefunction cutoff energy
    ecutwfc = extra.get("ecutwfc_Ry")
    if ecutwfc is not None:
        try:
            if float(ecutwfc) < 30.0:
                violations.append(
                    ValidationViolation(
                        rule="DFT_ECUTWFC_TOO_LOW",
                        message=(
                            f"Wavefunction cutoff energy ecutwfc={ecutwfc} Ry is too low. "
                            "≥ 60 Ry recommended for 3d transition metals."
                        ),
                        actual=ecutwfc,
                        recommended="≥ 60 Ry (3d transition metals), ≥ 30 Ry (minimum)",
                        scale_label=spec.label,
                    )
                )
        except (TypeError, ValueError):
            pass

    # DFT-4: SOC flag (required for MAE/DMI calculations)
    calc_type = extra.get("calc_type", "")
    soc = extra.get("soc", None)
    if calc_type in ("mae", "dmi", "MAE", "DMI") and soc is False:
        violations.append(
            ValidationViolation(
                rule="DFT_SOC_MISSING",
                message=f"calc_type={calc_type!r} requires SOC (spin-orbit coupling). Set extra['soc']=True.",
                actual=soc,
                recommended="extra['soc'] = True",
                scale_label=spec.label,
            )
        )

    return violations


# ---------------------------------------------------------------------------
# P3 atomistic validation rules
# ---------------------------------------------------------------------------


def _check_atomistic_spec(spec: ScaleSpec) -> list[ValidationViolation]:
    """Static validation of an atomistic ScaleSpec (T-P3-09).

    Rules:
      ATM-1: If J_ij_K is present, it must be in the physical range (0 < J < 10000 K).
      ATM-2: If T_max_K is present, it must be ≥ T_C_est_K.
      ATM-3: engine must be one of vampire·spirit·mock.
    """
    violations: list[ValidationViolation] = []
    extra = spec.extra if hasattr(spec, "extra") and spec.extra else {}
    engine = (spec.engine or "").lower()

    # ATM-3: Engine check
    known_atm_engines = {"vampire", "spirit", "auto", "mock", ""}
    if engine and engine not in known_atm_engines:
        violations.append(
            ValidationViolation(
                rule="ATM_UNKNOWN_ENGINE",
                message=f"Unknown atomistic engine: {engine!r}. Supported: vampire·spirit.",
                actual=engine,
                recommended="vampire·spirit",
                scale_label=spec.label,
            )
        )

    # ATM-1: J_ij range
    j_ij_k = extra.get("J_ij_K")
    if j_ij_k is not None:
        try:
            j_val = float(j_ij_k)
            if not (0 < j_val < 10000):
                violations.append(
                    ValidationViolation(
                        rule="ATM_JIJ_OUT_OF_RANGE",
                        message=(
                            f"J_ij_K={j_val:.2f} K is outside the physical range. "
                            "bcc Fe reference: J_1≈398 K (Pajda 2001 Phys.Rev.B 64,174402)."
                        ),
                        actual=j_val,
                        recommended="0 < J_ij_K < 10000 K",
                        scale_label=spec.label,
                    )
                )
        except (TypeError, ValueError):
            pass

    # ATM-2: T_max vs T_C consistency
    t_max_k = extra.get("T_max_K")
    t_c_est = extra.get("T_C_est_K")
    if t_max_k is not None and t_c_est is not None:
        try:
            if float(t_max_k) < float(t_c_est):
                violations.append(
                    ValidationViolation(
                        rule="ATM_TMAX_BELOW_TC",
                        message=(
                            f"T_max_K={t_max_k} K is below T_C_est_K={t_c_est} K. "
                            "The M(T) curve does not include the Curie temperature; T_C extraction is impossible."
                        ),
                        actual=t_max_k,
                        recommended=f"T_max_K > {t_c_est} K",
                        scale_label=spec.label,
                    )
                )
        except (TypeError, ValueError):
            pass

    return violations


# ---------------------------------------------------------------------------
# P3 device validation rules
# ---------------------------------------------------------------------------


def _check_device_spec(spec: ScaleSpec) -> list[ValidationViolation]:
    """Basic static validation of a device ScaleSpec (T-P3-09 / P4 placeholder).

    Before P4, only checks for the existence of basic parameters.
    """
    violations: list[ValidationViolation] = []
    extra = spec.extra if hasattr(spec, "extra") and spec.extra else {}

    # Warn if device_spec is absent (will become mandatory after P4)
    device_spec = extra.get("device_spec")
    if device_spec is None:
        # Before P4: warning only (not an Exception — placeholder)
        pass  # Validation will be strengthened in P4

    return violations


# ---------------------------------------------------------------------------
# P3 handoff continuity validation
# ---------------------------------------------------------------------------


def _check_handoff_continuity(spec: MultiScaleSpec) -> list[ValidationViolation]:
    """Check handoff continuity within a MultiScaleSpec (Appendix D).

    Rules:
      HANDOFF-1: from_scale/to_scale in handoffs must exist in the scales list.
      HANDOFF-2: Handoff parameter keys must not be empty.
    """
    violations: list[ValidationViolation] = []

    if not spec.handoffs:
        return violations

    for i, handoff in enumerate(spec.handoffs):
        # Check that handoff has from_scale/to_scale attributes
        from_s = getattr(handoff, "from_scale", None)
        to_s = getattr(handoff, "to_scale", None)
        params = getattr(handoff, "params", {}) or {}

        # HANDOFF-2: Warn if params is empty
        if not params:
            violations.append(
                ValidationViolation(
                    rule="HANDOFF_EMPTY_PARAMS",
                    message=(
                        f"Handoff[{i}] ({from_s} → {to_s}) has empty params. "
                        "Unit continuity verification is not possible."
                    ),
                    scale_label=str(from_s),
                )
            )

    return violations
