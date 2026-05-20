"""Unit tests for maglab/authoring/data_vault.py (§16.4, §5.15)."""

from __future__ import annotations

import pytest

from maglab.authoring.data_vault import AuthoringBlockedError, DataVault, make_vault
from maglab.provenance.datapoint import DataPoint, ProvenanceType


def _make_dp(value: float = 1.23, units: str = "T") -> DataPoint:
    """Create a minimal DataPoint for testing."""
    return DataPoint(
        value=value,
        units=units,
        provenance_type=ProvenanceType.MEASURED,
        source_ref="test-measurement",
    )


class TestDataVault:
    """Tests for DataVault core operations."""

    def test_register_and_get(self) -> None:
        """Registered DataPoints are retrievable by key."""
        vault = DataVault()
        dp = _make_dp()
        vault.register("B_app", dp)
        retrieved = vault.get("B_app")
        assert retrieved is not None
        assert retrieved.id == dp.id

    def test_get_missing_returns_none(self) -> None:
        """Getting an unregistered key returns None."""
        vault = DataVault()
        assert vault.get("nonexistent_key") is None

    def test_get_locked_value_alias(self) -> None:
        """get_locked_value is an alias for get."""
        vault = DataVault()
        dp = _make_dp()
        vault.register("Ms", dp)
        assert vault.get_locked_value("Ms") is dp

    def test_ids_returns_uuid_set(self) -> None:
        """ids() returns the set of DataPoint UUIDs."""
        dp1 = _make_dp(1.0)
        dp2 = _make_dp(2.0)
        vault = DataVault({"a": dp1, "b": dp2})
        assert vault.ids() == {dp1.id, dp2.id}


class TestInjectIntoDraft:
    """Tests for placeholder injection."""

    def test_placeholder_substituted(self) -> None:
        """A registered placeholder is replaced with the formatted value."""
        dp = _make_dp(value=3.14, units="T")
        vault = DataVault({"B_app": dp})
        draft = r"The applied field is {{dp:B_app}} at room temperature."
        result = vault.inject_into_draft(draft)
        assert "{{dp:B_app}}" not in result
        assert "3.14" in result

    def test_provenance_comment_injected(self) -> None:
        """After substitution a LaTeX provenance comment is present."""
        dp = _make_dp()
        vault = DataVault({"B": dp})
        result = vault.inject_into_draft(r"Field {{dp:B}}.")
        assert "prov:" in result
        assert dp.id in result

    def test_missing_placeholder_raises(self) -> None:
        """An unregistered placeholder key raises AuthoringBlockedError."""
        vault = DataVault()  # empty vault
        draft = r"Resistivity {{dp:rho_xy}} was measured."
        with pytest.raises(AuthoringBlockedError, match="rho_xy"):
            vault.inject_into_draft(draft)

    def test_multiple_placeholders_all_substituted(self) -> None:
        """Multiple registered placeholders are all substituted."""
        dp1 = _make_dp(1.0, "T")
        dp2 = _make_dp(2.0, "Ohm")
        vault = DataVault({"B": dp1, "R": dp2})
        draft = r"B = {{dp:B}}, R = {{dp:R}}."
        result = vault.inject_into_draft(draft)
        assert "{{dp:B}}" not in result
        assert "{{dp:R}}" not in result

    def test_partial_missing_raises_with_all_keys(self) -> None:
        """If one of multiple placeholders is missing, the error lists it."""
        dp = _make_dp()
        vault = DataVault({"B": dp})
        draft = r"B = {{dp:B}}, unknown = {{dp:MISSING}}."
        with pytest.raises(AuthoringBlockedError, match="MISSING"):
            vault.inject_into_draft(draft)


class TestValidateDraft:
    """Tests for pre-flight validation (no exception raised)."""

    def test_validate_returns_empty_for_registered_keys(self) -> None:
        """validate_draft returns empty list when all keys are present."""
        dp = _make_dp()
        vault = DataVault({"B": dp})
        missing = vault.validate_draft(r"Field {{dp:B}}.")
        assert missing == []

    def test_validate_returns_missing_key(self) -> None:
        """validate_draft returns list of missing keys without raising."""
        vault = DataVault()
        missing = vault.validate_draft(r"Value {{dp:rho_AHE}}.")
        assert "rho_AHE" in missing


class TestMakeVault:
    """Tests for the make_vault factory."""

    def test_make_vault_from_datapoints(self) -> None:
        """make_vault correctly wraps DataPoint objects."""
        dp = _make_dp()
        vault = make_vault({"x": dp})
        assert vault.get("x") is dp

    def test_make_vault_from_dicts(self) -> None:
        """make_vault deserialises DataPoint dicts."""
        dp = _make_dp()
        vault = make_vault({"x": dp.to_dict()})
        result = vault.get("x")
        assert result is not None
        assert result.id == dp.id

    def test_make_vault_invalid_type_raises(self) -> None:
        """make_vault raises TypeError for non-DataPoint, non-dict values."""
        with pytest.raises(TypeError):
            make_vault({"x": 42})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Regression tests for F4: vector DataPoints must include SI unit annotation
# ---------------------------------------------------------------------------


def _make_vector_dp(value: list[float], units: str = "T") -> DataPoint:
    """Create a vector DataPoint for testing."""
    return DataPoint(
        value=value,
        units=units,
        provenance_type=ProvenanceType.MEASURED,
        source_ref="test-vector-measurement",
    )


class TestVectorFormatValue:
    """F4 regression: _format_value must annotate vector values with SI units."""

    def test_vector_injection_contains_units(self) -> None:
        """F4: injected vector value must include the SI unit string.

        Before the fix, list values were formatted as bare numbers with no unit,
        e.g. '1.2, 3.4, 5.6'.  After the fix the unit is appended.
        """
        dp = _make_vector_dp([1.2, 3.4, 5.6], units="T")
        vault = DataVault({"B_vec": dp})
        draft = r"Field vector {{dp:B_vec}} measured."
        result = vault.inject_into_draft(draft)

        assert "{{dp:B_vec}}" not in result, "Placeholder was not substituted"
        # The unit must appear in the injected text
        assert r"\si{T}" in result or "\\si{T}" in result, (
            f"F4: SI unit annotation missing in vector injection.\n"
            f"Got: {result!r}\n"
            f"Expected '\\si{{T}}' to be present."
        )

    def test_vector_injection_contains_values(self) -> None:
        """F4: all numeric values are still present after the fix."""
        dp = _make_vector_dp([1.2, 3.4, 5.6], units="T")
        vault = DataVault({"B_vec": dp})
        result = vault.inject_into_draft(r"B = {{dp:B_vec}}.")
        assert "1.2" in result
        assert "3.4" in result
        assert "5.6" in result

    def test_scalar_injection_still_has_units(self) -> None:
        """F4 fix must not break the existing scalar branch (units still present)."""
        dp = _make_dp(value=2.71, units="Ohm")
        vault = DataVault({"rho": dp})
        result = vault.inject_into_draft(r"Resistivity {{dp:rho}}.")
        assert r"\si{Ohm}" in result or "\\si{Ohm}" in result, (
            "Scalar branch unit annotation was broken by the F4 fix."
        )

    def test_vector_injection_no_bare_numbers_without_unit(self) -> None:
        """F4: the injected text must NOT be a bare comma-list with no unit context.

        This captures the exact pre-fix output format and asserts it is gone.
        The pre-fix output was e.g. '1.2, 3.4, 5.6' with nothing after.
        After the fix a \\si{} annotation follows.
        """
        dp = _make_vector_dp([9.8, 7.6, 5.4], units="A/m")
        vault = DataVault({"M_vec": dp})
        result = vault.inject_into_draft(r"Magnetisation {{dp:M_vec}}.")
        # After injection, the si unit must be present
        assert "A/m" in result, (
            f"F4: Unit 'A/m' not found in injected vector output.\nGot: {result!r}"
        )
