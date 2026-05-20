"""tests/unit/test_provenance_datapoint.py — DataPoint validation, serialisation, and enum tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from pydantic_core import ValidationError as PydanticCoreValidationError

from maglab.provenance.datapoint import (
    BADGE_LABEL,
    DataPoint,
    ProvenanceType,
)

# ---------------------------------------------------------------------------
# Basic creation
# ---------------------------------------------------------------------------


class TestDataPointCreation:
    """DataPoint normal creation cases."""

    def test_simulated_datapoint(self):
        dp = DataPoint(
            value=5.7e-9,
            units="m",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref="mumax3-job-001",
        )
        assert dp.value == pytest.approx(5.7e-9)
        assert dp.units == "m"
        assert dp.provenance_type is ProvenanceType.SIMULATED

    def test_measured_datapoint_with_uncertainty(self):
        dp = DataPoint(
            value=1.23,
            units="T",
            uncertainty=0.01,
            provenance_type=ProvenanceType.MEASURED,
            source_ref="VSM-run-42",
        )
        assert dp.uncertainty == pytest.approx(0.01)

    def test_literature_datapoint_requires_source_ref(self):
        dp = DataPoint(
            value=4.2e5,
            units="A/m",
            provenance_type=ProvenanceType.LITERATURE,
            source_ref="10.1103/PhysRevB.85.094428",
        )
        assert dp.source_ref.startswith("10.")

    def test_fitted_datapoint(self):
        dp = DataPoint(
            value=0.015,
            units="1",
            provenance_type=ProvenanceType.FITTED,
            source_ref="lmfit-AHE-run-7",
        )
        assert dp.provenance_type is ProvenanceType.FITTED

    def test_theory_datapoint(self):
        dp = DataPoint(
            value=2.006,
            units="1",
            provenance_type=ProvenanceType.THEORY,
            source_ref="Dirac eq. electron g-factor",
        )
        assert dp.provenance_type is ProvenanceType.THEORY

    def test_array_value(self):
        dp = DataPoint(
            value=[1.0, 2.0, 3.0],
            units="T",
            provenance_type=ProvenanceType.MEASURED,
        )
        assert isinstance(dp.value, list)
        assert len(dp.value) == 3

    def test_auto_id_generated(self):
        dp1 = DataPoint(value=1.0, units="T", provenance_type=ProvenanceType.SIMULATED)
        dp2 = DataPoint(value=1.0, units="T", provenance_type=ProvenanceType.SIMULATED)
        assert dp1.id != dp2.id

    def test_auto_timestamp(self):
        before = datetime.now(UTC)
        dp = DataPoint(value=1.0, units="T", provenance_type=ProvenanceType.SIMULATED)
        after = datetime.now(UTC)
        assert before <= dp.timestamp <= after

    def test_conditions_dict(self):
        dp = DataPoint(
            value=300.0,
            units="K",
            provenance_type=ProvenanceType.MEASURED,
            conditions={"B_ext": 0.1, "sample_id": "GdFeCo-01"},
        )
        assert dp.conditions["sample_id"] == "GdFeCo-01"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestDataPointValidation:
    """DataPoint validation error cases."""

    def test_missing_provenance_type_raises(self):
        with pytest.raises(ValidationError):
            DataPoint(value=1.0, units="T")  # provenance_type omitted

    def test_blank_units_raises(self):
        with pytest.raises(ValidationError):
            DataPoint(value=1.0, units="", provenance_type=ProvenanceType.SIMULATED)

    def test_whitespace_only_units_raises(self):
        with pytest.raises(ValidationError):
            DataPoint(value=1.0, units="   ", provenance_type=ProvenanceType.SIMULATED)

    def test_negative_uncertainty_raises(self):
        with pytest.raises(ValidationError):
            DataPoint(
                value=1.0,
                units="T",
                uncertainty=-0.01,
                provenance_type=ProvenanceType.MEASURED,
            )

    def test_literature_without_source_ref_raises(self):
        with pytest.raises(ValidationError):
            DataPoint(
                value=1.0,
                units="T",
                provenance_type=ProvenanceType.LITERATURE,
                source_ref="",  # empty source_ref
            )

    def test_literature_with_whitespace_source_ref_raises(self):
        with pytest.raises(ValidationError):
            DataPoint(
                value=1.0,
                units="T",
                provenance_type=ProvenanceType.LITERATURE,
                source_ref="   ",
            )

    def test_zero_uncertainty_allowed(self):
        dp = DataPoint(
            value=1.0,
            units="T",
            uncertainty=0.0,
            provenance_type=ProvenanceType.MEASURED,
        )
        assert dp.uncertainty == 0.0

    def test_dimensionless_units_ok(self):
        dp = DataPoint(value=0.015, units="1", provenance_type=ProvenanceType.FITTED)
        assert dp.units == "1"
        dp2 = DataPoint(value=0.015, units="dimensionless", provenance_type=ProvenanceType.FITTED)
        assert dp2.units == "dimensionless"


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestDataPointImmutability:
    """DataPoint must be frozen (immutable)."""

    def test_value_immutable(self):
        dp = DataPoint(value=1.0, units="T", provenance_type=ProvenanceType.SIMULATED)
        # Pydantic frozen models raise ValidationError
        with pytest.raises(
            (ValidationError, PydanticCoreValidationError, TypeError, AttributeError)
        ):
            dp.value = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialisation and deserialisation
# ---------------------------------------------------------------------------


class TestDataPointSerialization:
    """Serialisation/deserialisation completeness checks."""

    def test_to_dict_roundtrip(self):
        dp = DataPoint(
            value=5.7e-9,
            units="m",
            uncertainty=0.2e-9,
            provenance_type=ProvenanceType.SIMULATED,
            source_ref="mumax3-job-001",
            conditions={"T": 300.0},
        )
        d = dp.to_dict()
        dp2 = DataPoint.from_dict(d)
        assert dp2.value == pytest.approx(dp.value)
        assert dp2.units == dp.units
        assert dp2.uncertainty == pytest.approx(dp.uncertainty)
        assert dp2.provenance_type is dp.provenance_type
        assert dp2.source_ref == dp.source_ref
        assert dp2.id == dp.id

    def test_to_dict_json_serializable(self):
        dp = DataPoint(
            value=1.0,
            units="T",
            provenance_type=ProvenanceType.MEASURED,
        )
        d = dp.to_dict()
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

    def test_from_dict_preserves_all_fields(self):
        dp = DataPoint(
            value=[1.0, 2.0],
            units="A/m",
            provenance_type=ProvenanceType.LITERATURE,
            source_ref="10.1000/xyz123",
            conditions={"author": "Bloch"},
        )
        d = dp.to_dict()
        dp2 = DataPoint.from_dict(d)
        assert dp2.value == dp.value
        assert dp2.conditions == dp.conditions

    def test_model_dump_json(self):
        dp = DataPoint(
            value=42.0,
            units="Oe",
            provenance_type=ProvenanceType.THEORY,
        )
        j = dp.model_dump_json()
        obj = json.loads(j)
        assert obj["provenance_type"] == "THEORY"


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class TestProvenanceTypeEnum:
    """ProvenanceType enum member and value checks."""

    def test_all_members_exist(self):
        members = {pt.value for pt in ProvenanceType}
        assert members == {"SIMULATED", "MEASURED", "THEORY", "LITERATURE", "FITTED"}

    def test_string_coercion(self):
        assert ProvenanceType("SIMULATED") is ProvenanceType.SIMULATED
        assert ProvenanceType("FITTED") is ProvenanceType.FITTED

    def test_invalid_enum_value_raises(self):
        with pytest.raises(ValueError):
            ProvenanceType("UNKNOWN")


# ---------------------------------------------------------------------------
# Badge
# ---------------------------------------------------------------------------


class TestBadge:
    """Badge label checks."""

    @pytest.mark.parametrize(
        "ptype, expected",
        [
            (ProvenanceType.SIMULATED, "[SIM]"),
            (ProvenanceType.MEASURED, "[MEAS]"),
            (ProvenanceType.THEORY, "[PRED]"),
            (ProvenanceType.LITERATURE, "[LIT]"),
            (ProvenanceType.FITTED, "[FIT]"),
        ],
    )
    def test_badge_labels(self, ptype: ProvenanceType, expected: str):
        dp = DataPoint(
            value=1.0,
            units="T",
            provenance_type=ptype,
            source_ref="ref" if ptype is ProvenanceType.LITERATURE else "",
        )
        assert dp.badge == expected

    def test_badge_label_map_complete(self):
        for pt in ProvenanceType:
            assert pt in BADGE_LABEL


# ---------------------------------------------------------------------------
# scalar() method
# ---------------------------------------------------------------------------


class TestScalar:
    def test_scalar_float(self):
        dp = DataPoint(value=3.14, units="T", provenance_type=ProvenanceType.SIMULATED)
        assert dp.scalar() == pytest.approx(3.14)

    def test_scalar_raises_for_list(self):
        dp = DataPoint(value=[1.0, 2.0], units="T", provenance_type=ProvenanceType.SIMULATED)
        with pytest.raises(TypeError):
            dp.scalar()
