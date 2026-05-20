"""Unit tests for sim/validate.py — micromagnetic static validation rules (Appendix D)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from maglab.sim.spec import (
    MicroMagGeometry,
    MicroMagMaterial,
    MultiScaleSpec,
    ScaleSpec,
    ScaleType,
)
from maglab.sim.validate import ValidationError, validate, validate_micro

# ---------------------------------------------------------------------------
# Valid ScaleSpec (validation pass baseline)
# ---------------------------------------------------------------------------


def make_valid_spec() -> ScaleSpec:
    """Standard Permalloy ScaleSpec that passes all Appendix D rules."""
    # l_ex = sqrt(2A/μ₀Ms²) ≈ sqrt(2*13e-12 / (4π×10⁻⁷ * (860e3)²)) ≈ 5.3 nm
    # cell size 2 nm < 5.3 nm → pass
    # α = 0.008 > 0 → pass
    # t_sim_ns = 0 → no time check (static minimization)
    return ScaleSpec(
        scale=ScaleType.micro,
        label="permalloy_valid",
        material=MicroMagMaterial(
            Ms_Am=860e3,
            A_Jm=13e-12,
            alpha=0.008,
        ),
        geometry=MicroMagGeometry(
            nx=4,
            ny=4,
            nz=1,
            dx_nm=2.0,
            dy_nm=2.0,
            dz_nm=3.0,  # dz=3nm < l_ex≈5.3nm → pass
        ),
    )


# ---------------------------------------------------------------------------
# Rule 1: cell size < exchange length l_ex
# ---------------------------------------------------------------------------


class TestCellVsExchangeLength:
    def test_valid_passes(self) -> None:
        validate_micro(make_valid_spec())

    def test_cell_too_large_raises(self) -> None:
        """ValidationError must be raised when cell size exceeds the exchange length."""
        spec = ScaleSpec(
            scale=ScaleType.micro,
            material=MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.008),
            geometry=MicroMagGeometry(
                nx=4,
                ny=4,
                nz=1,
                dx_nm=10.0,
                dy_nm=10.0,
                dz_nm=10.0,  # 10 nm >> l_ex ≈ 5.3 nm
            ),
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_micro(spec)
        assert any(v.rule == "MICRO_CELL_TOO_LARGE" for v in exc_info.value.violations)

    def test_cell_exactly_lex_raises(self) -> None:
        """Cell size ≈ l_ex is a boundary case — equal or larger must be a violation."""
        # l_ex ≈ 5.3 nm. A 6 nm cell should be a violation.
        spec = ScaleSpec(
            scale=ScaleType.micro,
            material=MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.008),
            geometry=MicroMagGeometry(
                nx=4,
                ny=4,
                nz=1,
                dx_nm=6.0,
                dy_nm=6.0,
                dz_nm=6.0,
            ),
        )
        with pytest.raises(ValidationError):
            validate_micro(spec)


# ---------------------------------------------------------------------------
# Rule 2: α > 0
# ---------------------------------------------------------------------------


class TestAlphaPositive:
    def test_alpha_zero_raises(self) -> None:
        """α = 0 must be rejected at the MicroMagMaterial construction stage."""
        with pytest.raises(PydanticValidationError):
            MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.0)

    def test_alpha_negative_raises(self) -> None:
        """α < 0 must be rejected at the MicroMagMaterial construction stage."""
        with pytest.raises(PydanticValidationError):
            MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=-0.01)


# ---------------------------------------------------------------------------
# Rule 3: material parameter completeness
# ---------------------------------------------------------------------------


class TestMaterialCompleteness:
    def test_valid_material_passes(self) -> None:
        validate_micro(make_valid_spec())

    def test_missing_material_in_spec(self) -> None:
        """A spec without material must be rejected at the ScaleSpec construction stage."""
        with pytest.raises(Exception, match="material"):
            ScaleSpec(
                scale=ScaleType.micro,
                geometry=MicroMagGeometry(nx=4, ny=4, nz=1, dx_nm=2, dy_nm=2, dz_nm=3),
            )


# ---------------------------------------------------------------------------
# Rule 4: run ≥ several × τ_relax
# ---------------------------------------------------------------------------


class TestRunTime:
    def test_static_mode_no_time_check(self) -> None:
        """t_sim_ns = 0 (static minimization) skips the time check."""
        spec = make_valid_spec()  # t_sim_ns=0
        validate_micro(spec)  # must not raise

    def test_run_too_short_raises(self) -> None:
        """ValidationError must be raised when t_sim_ns << 5τ.

        Permalloy α=0.008, Ms=860kA/m:
        τ = 1/(0.008 × 1.76e11 × 4π×10⁻⁷ × 860e3) ≈ 0.000655 ns
        5τ ≈ 0.00327 ns. t_sim_ns = 0.001 << 5τ → violation.
        """
        spec = ScaleSpec(
            scale=ScaleType.micro,
            material=MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.008),
            geometry=MicroMagGeometry(
                nx=4,
                ny=4,
                nz=1,
                dx_nm=2.0,
                dy_nm=2.0,
                dz_nm=3.0,
            ),
            t_sim_ns=1e-6,  # 1 ps — extremely short
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_micro(spec)
        assert any(v.rule == "MICRO_RUN_TOO_SHORT" for v in exc_info.value.violations)

    def test_run_sufficient_passes(self) -> None:
        """Passes when t_sim_ns ≥ 5τ.

        Permalloy α=0.008, Ms=860kA/m:
        τ = 1/(0.008 × 1.76e11 × 4π×10⁻⁷ × 860e3) ≈ 0.657 ns
        5τ ≈ 3.28 ns. t_sim_ns=10.0 ns >> 5τ → pass.
        """
        spec = ScaleSpec(
            scale=ScaleType.micro,
            material=MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.008),
            geometry=MicroMagGeometry(
                nx=4,
                ny=4,
                nz=1,
                dx_nm=2.0,
                dy_nm=2.0,
                dz_nm=3.0,
            ),
            t_sim_ns=10.0,  # 10 ns >> 5τ ≈ 3.28 ns
        )
        validate_micro(spec)


# ---------------------------------------------------------------------------
# Multiple violation tests
# ---------------------------------------------------------------------------


class TestMultipleViolations:
    def test_multiple_violations_all_reported(self) -> None:
        """All violations must be reported when multiple rules are violated simultaneously.

        Oversized cell + run too short → 2 or more violations.
        """
        spec = ScaleSpec(
            scale=ScaleType.micro,
            material=MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.008),
            geometry=MicroMagGeometry(
                nx=4,
                ny=4,
                nz=1,
                dx_nm=20.0,
                dy_nm=20.0,
                dz_nm=20.0,  # oversized cell
            ),
            t_sim_ns=1e-6,  # run too short
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_micro(spec)
        rules = {v.rule for v in exc_info.value.violations}
        assert "MICRO_CELL_TOO_LARGE" in rules
        assert "MICRO_RUN_TOO_SHORT" in rules


# ---------------------------------------------------------------------------
# MultiScaleSpec validate() entry-point tests
# ---------------------------------------------------------------------------


class TestValidateMultiScale:
    def test_valid_multispec_passes(self) -> None:
        ms = MultiScaleSpec(scales=[make_valid_spec()])
        validate(ms)

    def test_invalid_multispec_raises(self) -> None:
        bad_spec = ScaleSpec(
            scale=ScaleType.micro,
            material=MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.008),
            geometry=MicroMagGeometry(
                nx=4,
                ny=4,
                nz=1,
                dx_nm=20.0,
                dy_nm=20.0,
                dz_nm=20.0,
            ),
        )
        ms = MultiScaleSpec(scales=[bad_spec])
        with pytest.raises(ValidationError):
            validate(ms)

    def test_non_micro_scale_no_error(self) -> None:
        """P3 scales (dft/atomistic) pass only basic validation in P1."""
        ms = MultiScaleSpec(
            scales=[
                make_valid_spec(),
                ScaleSpec(scale=ScaleType.dft),
            ]
        )
        validate(ms)  # must not raise
