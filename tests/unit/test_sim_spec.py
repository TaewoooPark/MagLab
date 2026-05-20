"""Unit tests for sim/spec.py — MultiScaleSpec IR serialization, deserialization, and validation."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from maglab.sim.spec import (
    FieldSweep,
    Handoff,
    MicroMagGeometry,
    MicroMagMaterial,
    MultiScaleSpec,
    ScaleSpec,
    ScaleType,
)

# ---------------------------------------------------------------------------
# Fixtures — Permalloy single-layer thin film standard ScaleSpec
# ---------------------------------------------------------------------------

PERMALLOY_MATERIAL = MicroMagMaterial(
    Ms_Am=860e3,  # Permalloy M_s ~ 860 kA/m
    A_Jm=13e-12,  # Permalloy A ~ 13 pJ/m
    alpha=0.008,  # Permalloy α
)

SMALL_GEOM = MicroMagGeometry(
    nx=4,
    ny=4,
    nz=1,
    dx_nm=2.0,
    dy_nm=2.0,
    dz_nm=3.0,
)


def make_micro_spec(label: str = "test") -> ScaleSpec:
    return ScaleSpec(
        scale=ScaleType.micro,
        label=label,
        material=PERMALLOY_MATERIAL,
        geometry=SMALL_GEOM,
    )


def make_multispec() -> MultiScaleSpec:
    return MultiScaleSpec(
        name="permalloy_film",
        description="Single-layer Permalloy thin film test",
        scales=[make_micro_spec()],
    )


# ---------------------------------------------------------------------------
# ScaleType enum tests
# ---------------------------------------------------------------------------


class TestScaleType:
    def test_all_four_scales_exist(self) -> None:
        """Verify that all four scale enum values are defined from the start (for P3 extension)."""
        assert ScaleType.micro == "micro"
        assert ScaleType.atomistic == "atomistic"
        assert ScaleType.dft == "dft"
        assert ScaleType.device == "device"

    def test_invalid_scale_raises(self) -> None:
        """ScaleSpec with an undefined scale string must raise an exception."""
        with pytest.raises(ValidationError):
            ScaleSpec(
                scale="quantum",  # type: ignore[arg-type]
                material=PERMALLOY_MATERIAL,
                geometry=SMALL_GEOM,
            )


# ---------------------------------------------------------------------------
# MicroMagMaterial tests
# ---------------------------------------------------------------------------


class TestMicroMagMaterial:
    def test_valid_permalloy(self) -> None:
        mat = PERMALLOY_MATERIAL
        assert mat.Ms_Am == pytest.approx(860e3)
        assert mat.A_Jm == pytest.approx(13e-12)
        assert mat.alpha == pytest.approx(0.008)

    def test_alpha_zero_invalid(self) -> None:
        with pytest.raises(ValidationError):
            MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.0)

    def test_ms_zero_invalid(self) -> None:
        with pytest.raises(ValidationError):
            MicroMagMaterial(Ms_Am=0.0, A_Jm=13e-12, alpha=0.01)

    def test_k_axis_wrong_dim(self) -> None:
        with pytest.raises(ValidationError):
            MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.01, K_axis=[0, 1])

    def test_default_k_axis(self) -> None:
        mat = MicroMagMaterial(Ms_Am=860e3, A_Jm=13e-12, alpha=0.01)
        assert mat.K_axis == [0.0, 0.0, 1.0]


# ---------------------------------------------------------------------------
# MicroMagGeometry tests
# ---------------------------------------------------------------------------


class TestMicroMagGeometry:
    def test_cell_size_m(self) -> None:
        dx, dy, dz = SMALL_GEOM.cell_size_m
        assert dx == pytest.approx(2e-9)
        assert dy == pytest.approx(2e-9)
        assert dz == pytest.approx(3e-9)

    def test_total_volume(self) -> None:
        vol = SMALL_GEOM.total_volume_m3
        assert vol == pytest.approx(4 * 4 * 1 * 2e-9 * 2e-9 * 3e-9)

    def test_nx_ge_1(self) -> None:
        with pytest.raises(ValidationError):
            MicroMagGeometry(nx=0, ny=4, nz=1, dx_nm=2, dy_nm=2, dz_nm=3)


# ---------------------------------------------------------------------------
# ScaleSpec tests
# ---------------------------------------------------------------------------


class TestScaleSpec:
    def test_micro_requires_material(self) -> None:
        with pytest.raises(Exception, match="material"):
            ScaleSpec(scale=ScaleType.micro, geometry=SMALL_GEOM)

    def test_micro_requires_geometry(self) -> None:
        with pytest.raises(Exception, match="geometry"):
            ScaleSpec(scale=ScaleType.micro, material=PERMALLOY_MATERIAL)

    def test_non_micro_no_material_ok(self) -> None:
        """P3 scales must be constructible without material in P1."""
        spec = ScaleSpec(scale=ScaleType.dft)
        assert spec.scale == ScaleType.dft

    def test_field_sweep_attached(self) -> None:
        fs = FieldSweep(H_start_Am=[0, 0, 0], H_end_Am=[1e5, 0, 0], n_steps=5)
        spec = make_micro_spec()
        spec2 = spec.model_copy(update={"field_sweep": fs})
        assert spec2.field_sweep is not None
        assert spec2.field_sweep.n_steps == 5


# ---------------------------------------------------------------------------
# MultiScaleSpec serialization/deserialization identity tests (DoD)
# ---------------------------------------------------------------------------


class TestMultiScaleSpec:
    def test_empty_scales_raises(self) -> None:
        with pytest.raises(Exception, match="at least one"):
            MultiScaleSpec(scales=[])

    def test_single_scale_roundtrip(self) -> None:
        """Serialize and deserialize a single micromagnetic ScaleSpec and verify identity."""
        spec = make_multispec()
        json_str = spec.model_dump_json()
        restored = MultiScaleSpec.model_validate_json(json_str)

        assert restored.name == spec.name
        assert len(restored.scales) == 1
        restored_mat = restored.scales[0].material
        assert restored_mat is not None
        assert restored_mat.Ms_Am == pytest.approx(spec.scales[0].material.Ms_Am)  # type: ignore[union-attr]
        assert restored_mat.alpha == pytest.approx(spec.scales[0].material.alpha)  # type: ignore[union-attr]

    def test_json_dict_roundtrip(self) -> None:
        """dict serialization/deserialization identity."""
        spec = make_multispec()
        d = spec.model_dump()
        restored = MultiScaleSpec.model_validate(d)
        assert restored.name == spec.name
        assert restored.scales[0].scale == ScaleType.micro

    def test_is_single_scale(self) -> None:
        spec = make_multispec()
        assert spec.is_single_scale()

    def test_single_scale_spec(self) -> None:
        spec = make_multispec()
        ss = spec.single_scale_spec()
        assert ss.scale == ScaleType.micro

    def test_multi_scale_not_single(self) -> None:
        spec = MultiScaleSpec(
            scales=[make_micro_spec("a"), make_micro_spec("b")],
        )
        assert not spec.is_single_scale()

    def test_scales_of_type_filter(self) -> None:
        spec = MultiScaleSpec(
            scales=[
                make_micro_spec("micro1"),
                ScaleSpec(scale=ScaleType.dft),
            ],
        )
        micro_specs = spec.scales_of_type(ScaleType.micro)
        assert len(micro_specs) == 1
        dft_specs = spec.scales_of_type(ScaleType.dft)
        assert len(dft_specs) == 1

    def test_handoff_roundtrip(self) -> None:
        """Handoff serialization identity."""
        hoff = Handoff(
            from_scale=ScaleType.dft,
            to_scale=ScaleType.micro,
            mapping={"A": "from_J_ij"},
            notes="DFT→micromagnetic handoff",
        )
        spec = MultiScaleSpec(
            scales=[make_micro_spec()],
            handoffs=[hoff],
        )
        d = json.loads(spec.model_dump_json())
        restored = MultiScaleSpec.model_validate(d)
        assert restored.handoffs[0].from_scale == ScaleType.dft
        assert restored.handoffs[0].to_scale == ScaleType.micro
