"""tests/integrity/test_honesty_gate.py — Honesty Gate exhaustive tests (§5.15·§17).

Each case:
- Untagged number injection → blocked
- Fake citation injection → blocked
- Persona disclosure missing → blocked
- Promise-check mismatch → flagged
"""

from __future__ import annotations

import uuid

import pytest

from maglab.report.honesty_gate import (
    GateResult,
    HonestyViolation,
    ViolationKind,
    audit_claims,
    check_citations,
    check_figure_data_tags,
    check_first_person_attribution,
    check_persona_disclosure,
    check_promises,
    check_untagged_numbers,
    check_vault_references,
    run_gate,
)
from maglab.report.reporting import ReportBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_uuid() -> str:
    return str(uuid.uuid4())


def _text_with_uuid(value: str, dp_id: str) -> str:
    """Text containing a DataPoint UUID surrounding a numeric value."""
    return f"The value of DataPoint({dp_id}) is {value} T."


# ---------------------------------------------------------------------------
# 1. Untagged number detection and blocking (5 cases)
# ---------------------------------------------------------------------------


class TestUntaggedNumbers:
    """Text containing untagged bare numbers is blocked."""

    @pytest.mark.parametrize(
        "text",
        [
            "The saturation magnetisation is 1.23 T.",
            "The exchange length is 5.7e-9 m.",
            "The TMR ratio is 300.0 %.",
            "The Gilbert damping constant was measured as 0.015.",
            "An external magnetic field of -0.5 T is applied.",
        ],
    )
    def test_untagged_number_detected(self, text: str):
        violations = check_untagged_numbers(text, known_dp_ids=set())
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.UNTAGGED_NUMBER for v in violations)

    def test_tagged_number_passes(self):
        dp_id = _fresh_uuid()
        text = _text_with_uuid("1.23", dp_id)
        violations = check_untagged_numbers(text, known_dp_ids={dp_id})
        assert violations == []

    def test_multiple_untagged_numbers(self):
        text = "Magnetisation 1.23 T, anisotropy 4.5e4 J/m3, damping 0.01."
        violations = check_untagged_numbers(text, known_dp_ids=set())
        assert len(violations) >= 2  # at least 2 violations

    def test_run_gate_blocks_untagged(self):
        text = "The measured value is 3.14 T."
        with pytest.raises(HonestyViolation) as exc_info:
            run_gate(text, known_dp_ids=set(), raise_on_violation=True)
        assert any(v.kind is ViolationKind.UNTAGGED_NUMBER for v in exc_info.value.violations)

    def test_no_violation_when_no_numbers(self):
        text = "Please refer to the data vault for the saturation magnetisation value."
        violations = check_untagged_numbers(text, known_dp_ids=set())
        assert violations == []


# ---------------------------------------------------------------------------
# 2. Fake citation detection and blocking (10 cases)
# ---------------------------------------------------------------------------


class TestFakeCitations:
    """Citations not in the verification pool are blocked."""

    FAKE_DOIS = [
        "10.9999/fake-doi-001",
        "10.9999/fake-doi-002",
        "10.9999/fake-doi-003",
        "10.9999/fake-doi-004",
        "10.9999/fake-doi-005",
        "10.9999/fake-doi-006",
        "10.9999/fake-doi-007",
        "10.9999/fake-doi-008",
        "10.9999/fake-doi-009",
        "10.9999/fake-doi-010",
    ]

    @pytest.mark.parametrize("fake_doi", FAKE_DOIS)
    def test_fake_doi_detected(self, fake_doi: str):
        """Each fake DOI is detected as a violation when absent from the verification pool."""
        text = f"This study cites {fake_doi}."
        verified = {"10.1103/PhysRevLett.100.026601"}  # fake DOI not present
        violations = check_citations(text, verified_citations=verified)
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.UNVERIFIED_CITATION for v in violations)

    def test_valid_doi_passes(self):
        doi = "10.1103/PhysRevLett.100.026601"
        text = f"This study cites {doi}."
        violations = check_citations(text, verified_citations={doi})
        assert violations == []

    def test_no_citations_in_text_passes(self):
        text = "This sentence contains no citations."
        violations = check_citations(text, verified_citations={"10.1000/test"})
        assert violations == []

    def test_none_verified_pool_skips(self):
        """Citation check is skipped when verified_citations=None."""
        text = "This cites 10.9999/fake-doi-001."
        violations = check_citations(text, verified_citations=None)
        assert violations == []

    def test_run_gate_blocks_fake_citation(self):
        text = "This cites 10.9999/hallucinated-doi."
        with pytest.raises(HonestyViolation) as exc_info:
            run_gate(
                text,
                verified_citations={"10.1103/real-doi"},
                raise_on_violation=True,
            )
        assert any(v.kind is ViolationKind.UNVERIFIED_CITATION for v in exc_info.value.violations)

    def test_arxiv_fake_detected(self):
        text = "Inspired by arXiv:9999.99999."
        violations = check_citations(text, verified_citations={"arXiv:2304.12345"})
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# 3. Persona disclosure missing → blocked
# ---------------------------------------------------------------------------


class TestPersonaDisclosure:
    """Persona reviewer utterances without an AI disclosure label are blocked."""

    @pytest.mark.parametrize(
        "text",
        [
            "The methodology of this paper is insufficient.",
            "The experimental conditions are not clearly described.",
            "Statistical tests are missing.",
            "The reference format does not meet journal standards.",
        ],
    )
    def test_missing_disclosure_detected(self, text: str):
        violations = check_persona_disclosure(text, require_disclosure=True)
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.MISSING_PERSONA_DISCLOSURE for v in violations)

    @pytest.mark.parametrize(
        "text",
        [
            "AI.system reviewer: the methodology of this paper is insufficient.",
            "As a simulated reviewer, the experimental conditions are unclear.",
            "This review was produced by an AI reviewer system.",
        ],
    )
    def test_with_disclosure_passes(self, text: str):
        violations = check_persona_disclosure(text, require_disclosure=True)
        assert violations == []

    def test_require_false_always_passes(self):
        text = "A review written without disclosure."
        violations = check_persona_disclosure(text, require_disclosure=False)
        assert violations == []

    def test_run_gate_persona_mode_blocks(self):
        text = "This paper has low reproducibility."
        with pytest.raises(HonestyViolation) as exc_info:
            run_gate(text, is_persona=True, raise_on_violation=True)
        assert any(
            v.kind is ViolationKind.MISSING_PERSONA_DISCLOSURE for v in exc_info.value.violations
        )

    def test_run_gate_non_persona_mode_passes_without_disclosure(self):
        text = "This paper has low reproducibility."
        # No disclosure check when is_persona=False
        result = run_gate(
            text,
            is_persona=False,
            known_dp_ids=set(),
            raise_on_violation=False,
        )
        # Only number violations should be present (no MISSING_PERSONA_DISCLOSURE)
        persona_viols = [
            v for v in result.violations if v.kind is ViolationKind.MISSING_PERSONA_DISCLOSURE
        ]
        assert persona_viols == []


# ---------------------------------------------------------------------------
# 4. First-person attribution detection
# ---------------------------------------------------------------------------


class TestFirstPersonAttribution:
    def test_korean_first_person(self):
        # Korean first-person pattern tested via English equivalent
        text = "I calculated the result; the exchange length is 5.7 nm."
        violations = check_first_person_attribution(text)
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.FIRST_PERSON_ATTRIBUTION for v in violations)

    def test_english_first_person(self):
        text = "I found that the exchange length is 5.7 nm."
        violations = check_first_person_attribution(text)
        assert len(violations) >= 1

    def test_no_first_person(self):
        text = "The calculation confirmed the exchange length."
        violations = check_first_person_attribution(text)
        assert violations == []


# ---------------------------------------------------------------------------
# 5. Promise-check mismatch → flagged (2 or more cases)
# ---------------------------------------------------------------------------


class TestPromiseCheck:
    """Agent utterances claiming 'executed' that are not in the tool log are flagged."""

    def test_promise_without_tool_log_flagged(self):
        """Claims execution with an empty tool log → violation."""
        agent_text = "I have executed the simulation."
        violations = check_promises(agent_text, tool_log=[])
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.PROMISE_MISMATCH for v in violations)

    def test_english_promise_without_log_flagged(self):
        """English promises are also detected."""
        agent_text = "I have executed the fitting routine."
        violations = check_promises(agent_text, tool_log=[])
        assert len(violations) >= 1

    def test_promise_with_matching_tool_log_passes(self):
        """Passes when a successful execution record exists in the tool log."""
        agent_text = "I have executed the simulation."
        tool_log = [{"tool": "sim_run", "status": "success"}]
        violations = check_promises(agent_text, tool_log=tool_log)
        assert violations == []

    def test_no_promise_no_violation(self):
        """No violation when no promise pattern is present."""
        agent_text = "The following steps are planned for later."
        violations = check_promises(agent_text, tool_log=[])
        assert violations == []

    def test_run_gate_promise_check(self):
        """run_gate executes promise-check when tool_log is provided."""
        agent_text = "I have saved the data."
        result = run_gate(
            agent_text,
            known_dp_ids=set(),
            tool_log=[],  # empty
            raise_on_violation=False,
        )
        promise_viols = [v for v in result.violations if v.kind is ViolationKind.PROMISE_MISMATCH]
        assert len(promise_viols) >= 1

    def test_multiple_promises_flagged(self):
        """Multiple promises are each flagged individually."""
        agent_text = "I have completed the calculation and saved the results."
        violations = check_promises(agent_text, tool_log=[])
        assert len(violations) >= 1  # at least 1 violation


# ---------------------------------------------------------------------------
# 6. Vault reference check
# ---------------------------------------------------------------------------


class TestVaultReferences:
    def test_out_of_vault_id_detected(self):
        fake_id = _fresh_uuid()
        text = f"Numeric reference: {fake_id}"
        violations = check_vault_references(text, vault_ids=set())
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.OUT_OF_VAULT_VALUE for v in violations)

    def test_valid_vault_id_passes(self):
        valid_id = _fresh_uuid()
        text = f"Numeric reference: {valid_id}"
        violations = check_vault_references(text, vault_ids={valid_id})
        assert violations == []


# ---------------------------------------------------------------------------
# 7. Figure untagged data check
# ---------------------------------------------------------------------------


class TestFigureDataTags:
    def test_figure_untagged_number_detected(self):
        text = "Figure 1: magnetisation saturates at 1.23 T."
        violations = check_figure_data_tags(text, known_dp_ids=set())
        assert len(violations) >= 1

    def test_non_figure_text_skipped(self):
        # Must be regular body text without the word "figure"
        text = "The saturation magnetisation is 1.23 T."
        violations = check_figure_data_tags(text, known_dp_ids=set())
        # No figure context word → skipped
        assert violations == []

    def test_figure_tagged_number_passes(self):
        dp_id = _fresh_uuid()
        text = f"Fig. 1: DataPoint({dp_id}) value 1.23 T."
        violations = check_figure_data_tags(text, known_dp_ids={dp_id})
        assert violations == []


# ---------------------------------------------------------------------------
# 8. Audit claims integration tests
# ---------------------------------------------------------------------------


class TestAuditClaims:
    def test_clean_text_no_violations(self):
        dp_id = _fresh_uuid()
        text = f"Please refer to result DataPoint({dp_id})."
        violations = audit_claims(text, verified_dp_ids={dp_id})
        # No first-person or citation → passes
        assert violations == []

    def test_combined_violations(self):
        text = "I calculated the value as 3.14 T, citing 10.9999/fake."
        violations = audit_claims(
            text,
            verified_dp_ids=set(),
            verified_citations={"10.1103/real"},
        )
        kinds = {v.kind for v in violations}
        assert ViolationKind.UNTAGGED_NUMBER in kinds
        assert ViolationKind.FIRST_PERSON_ATTRIBUTION in kinds
        assert ViolationKind.UNVERIFIED_CITATION in kinds


# ---------------------------------------------------------------------------
# 9. run_gate — GateResult return (raise_on_violation=False)
# ---------------------------------------------------------------------------


class TestRunGateResult:
    def test_clean_text_passes(self):
        text = "Please refer to the source vault."
        result = run_gate(text, known_dp_ids=set(), raise_on_violation=False)
        assert isinstance(result, GateResult)
        assert result.passed

    def test_violation_returns_result_not_raise(self):
        text = "The value is 3.14 T."
        result = run_gate(
            text,
            known_dp_ids=set(),
            raise_on_violation=False,
        )
        assert not result.passed
        assert len(result.violations) >= 1

    def test_summary_contains_blocked(self):
        text = "The value is 3.14 T."
        result = run_gate(text, known_dp_ids=set(), raise_on_violation=False)
        summary = result.summary()
        assert "BLOCKED" in summary

    def test_honesty_violation_exception(self):
        text = "The value is 3.14 T."
        with pytest.raises(HonestyViolation):
            run_gate(text, known_dp_ids=set(), raise_on_violation=True)

    def test_honesty_violation_has_violations(self):
        text = "The value is 3.14 T."
        try:
            run_gate(text, known_dp_ids=set(), raise_on_violation=True)
        except HonestyViolation as exc:
            assert len(exc.violations) >= 1
            assert str(exc)  # __str__ works correctly


# ---------------------------------------------------------------------------
# REGRESSION — Finding 2: promise-check must flag violations even when a
# read-only tool is in the log (the former `if not executed_tools` guard
# would suppress ALL violations as soon as any tool had run).
# ---------------------------------------------------------------------------


class TestPromiseCheckRegression:
    """Regression tests for Finding 2 — promise check must not be silently suppressed.

    Before the fix:
        check_promises("I have executed the simulation.",
                       tool_log=[{"tool": "memory.read", "status": "success"}])
        → [] (zero violations; bug)

    After the fix:
        → at least 1 PROMISE_MISMATCH violation (only read-only tool ran)
    """

    def test_promise_flagged_when_only_read_only_tool_ran(self):
        """A read-only tool in the log must NOT suppress promise violations."""
        agent_text = "I have already executed the simulation and saved the results."
        tool_log = [{"tool": "memory.read", "status": "success"}]
        violations = check_promises(agent_text, tool_log=tool_log)
        assert len(violations) >= 1, (
            "Promise-check must still flag violations when only a read-only "
            "tool (memory.read) appears in the log."
        )
        assert all(v.kind is ViolationKind.PROMISE_MISMATCH for v in violations)

    def test_promise_flagged_with_pool_query_only(self):
        """pool.query is a read-only tool and must not suppress promise violations."""
        agent_text = "I have completed the simulation run."
        tool_log = [{"tool": "pool.query", "status": "success"}]
        violations = check_promises(agent_text, tool_log=tool_log)
        assert len(violations) >= 1

    def test_promise_passes_when_write_tool_ran(self):
        """A write-tier tool in the log suppresses the violation (expected behaviour)."""
        agent_text = "I have executed the simulation."
        tool_log = [
            {"tool": "memory.read", "status": "success"},
            {"tool": "sim_run", "status": "success"},
        ]
        violations = check_promises(agent_text, tool_log=tool_log)
        assert violations == [], (
            "When a write-tier tool (sim_run) is in the log, the promise is satisfied."
        )

    def test_promise_flagged_when_read_tool_fails(self):
        """A failed read-only tool must not suppress the violation either."""
        agent_text = "I have saved the results."
        tool_log = [{"tool": "memory.read", "status": "error"}]
        violations = check_promises(agent_text, tool_log=tool_log)
        # memory.read with error status is not in executed_tools at all
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# REGRESSION — Finding 1 (R2): passive/third-person voice must NOT trigger
# PROMISE_MISMATCH.  Before the fix, verbs like "saved", "recorded",
# "completed", "performed", "processed", "verified", "ran", "done", "finished"
# matched without any first-person subject, producing systematic false positives
# on standard physics report language.
# ---------------------------------------------------------------------------


class TestPassiveVoiceNoFalsePositive:
    """check_promises must NOT fire on passive or third-person constructions."""

    @pytest.mark.parametrize(
        "passive_text",
        [
            "The magnetization measurements were completed at 300 K.",
            "Results are saved in the data vault.",
            "Data were recorded over a 10-hour period.",
            "The simulation was performed with default parameters.",
            "All checkpoints were verified before publishing.",
            "The fitting procedure was processed automatically.",
            "The experiment ran successfully overnight.",
            "The calibration is done.",
            "Analysis has been finished.",
        ],
    )
    def test_passive_voice_produces_no_promise_violation(self, passive_text: str):
        """Passive / third-person text must produce zero PROMISE_MISMATCH violations."""
        violations = check_promises(passive_text, tool_log=[])
        promise_viols = [v for v in violations if v.kind is ViolationKind.PROMISE_MISMATCH]
        assert promise_viols == [], (
            f"False-positive PROMISE_MISMATCH on passive text: {passive_text!r}"
        )

    def test_first_person_still_flagged(self):
        """First-person promise with empty tool log must still be flagged."""
        violations = check_promises("I have saved the results.", tool_log=[])
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.PROMISE_MISMATCH for v in violations)

    def test_we_first_person_still_flagged(self):
        """'we ran' with empty tool log must still be flagged."""
        violations = check_promises("We ran the experiment successfully.", tool_log=[])
        assert len(violations) >= 1
        assert all(v.kind is ViolationKind.PROMISE_MISMATCH for v in violations)


# ---------------------------------------------------------------------------
# REGRESSION — Finding 1 (R3): ReportBuilder.build() must surface real
# HonestyGate violations when raise_on_violation=False (the default).
#
# Before the fix, run_gate() was called without capturing its return value.
# When raise_on_violation=False the gate returns a GateResult instead of
# raising, so the except branch was never reached and violations was always [].
# Report.passed_gate was therefore always True regardless of the narrative.
# ---------------------------------------------------------------------------


class TestReportBuilderGateRegression:
    """R3/F1 — ReportBuilder.build() must not always return passed_gate=True.

    Verifies that violations returned by run_gate (raise_on_violation=False)
    are captured and forwarded to the Report object.
    """

    def test_untagged_number_in_narrative_fails_gate(self):
        """A narrative with an untagged number must produce passed_gate=False."""
        builder = ReportBuilder("regression-r3-f1")
        builder.narrative("The saturation magnetisation is 1.23 T.")
        report = builder.build(run_honesty_gate=True, raise_on_violation=False)
        assert not report.passed_gate, (
            "ReportBuilder.build() returned passed_gate=True even though "
            "the narrative contains an untagged number '1.23 T'."
        )
        assert len(report.violations) >= 1, (
            "Expected at least 1 violation for untagged number, got 0."
        )

    def test_clean_narrative_passes_gate(self):
        """A clean narrative with no violations must still pass the gate."""
        builder = ReportBuilder("regression-r3-f1-clean")
        builder.narrative("Please refer to the data vault for all values.")
        report = builder.build(run_honesty_gate=True, raise_on_violation=False)
        assert report.passed_gate, "Clean narrative was incorrectly blocked by the gate."
        assert report.violations == []

    def test_fake_citation_in_narrative_fails_gate(self):
        """A narrative with a fake DOI must produce passed_gate=False."""
        builder = ReportBuilder("regression-r3-f1-citation")
        builder.narrative("This result confirms 10.9999/hallucinated-doi-r3.")
        report = builder.build(
            run_honesty_gate=True,
            raise_on_violation=False,
            verified_citations={"10.1103/real-doi"},
        )
        assert not report.passed_gate
        kinds = {v.kind for v in report.violations}
        assert ViolationKind.UNVERIFIED_CITATION in kinds, (
            "Expected UNVERIFIED_CITATION violation for fake DOI in narrative."
        )

    def test_violations_non_empty_when_raise_false(self):
        """Confirms the pre-fix bug is absent: violations list must not be empty."""
        builder = ReportBuilder("regression-r3-f1-nonempty")
        builder.narrative("I measured the exchange length as 5.7e-9 m.")
        report = builder.build(run_honesty_gate=True, raise_on_violation=False)
        # Before the fix: report.violations was always [] here
        assert len(report.violations) >= 1, (
            "report.violations was empty — gate return value was not captured."
        )


# ---------------------------------------------------------------------------
# REGRESSION — Finding 1 (R4): ReportBuilder must not generate spurious
# OUT_OF_VAULT_VALUE violations for DataPoints that the caller registered via
# builder.add().
#
# Before the fix: known_ids (the UUIDs of registered DataPoints) were NOT
# merged into vault_ids before calling run_gate().  When a caller provided a
# non-None vault_ids and included dp.id in the narrative, run_gate flagged
# those UUIDs as OUT_OF_VAULT_VALUE and passed_gate returned False for a
# correctly-built, fully-provenanced report.
# ---------------------------------------------------------------------------


class TestReportBuilderVaultMergeRegression:
    """R4/F1 — registered DataPoint IDs must not trigger OUT_OF_VAULT_VALUE."""

    def test_narrative_with_registered_dp_id_passes_gate(self):
        """A narrative referencing its own registered DataPoint UUID must pass the gate.

        Scenario (from the review report):
            dp = DataPoint(...)
            builder.add(dp)
            builder.narrative(f"Measured Ms = 8e5 A/m [{dp.id}]...")
            report = builder.build(vault_ids={"some-external-vault-id"})
            # Before fix: report.passed_gate == False due to OUT_OF_VAULT_VALUE
            # After fix:  report.passed_gate == True
        """
        from maglab.provenance.datapoint import DataPoint, ProvenanceType

        dp = DataPoint(value=8e5, units="A/m", provenance_type=ProvenanceType.MEASURED)
        external_vault_id = str(uuid.uuid4())

        builder = ReportBuilder("R4 regression — vault merge")
        builder.add(dp, label="Ms")
        # Narrative explicitly embeds the dp UUID (provenance-tagging pattern)
        builder.narrative(f"Measured Ms = 8e5 A/m [{dp.id}], within expected range.")

        report = builder.build(
            run_honesty_gate=True,
            raise_on_violation=False,
            vault_ids={external_vault_id},  # dp.id intentionally absent here
        )

        out_of_vault = [v for v in report.violations if v.kind is ViolationKind.OUT_OF_VAULT_VALUE]
        assert out_of_vault == [], (
            f"Spurious OUT_OF_VAULT_VALUE violations for registered dp.id={dp.id!r}: {out_of_vault}"
        )
        assert report.passed_gate, (
            "passed_gate must be True when the only UUID in the narrative is the "
            "report's own registered DataPoint."
        )

    def test_genuine_out_of_vault_id_still_detected(self):
        """An unknown UUID in the narrative that is NOT a registered DataPoint is still flagged."""
        from maglab.provenance.datapoint import DataPoint, ProvenanceType

        dp = DataPoint(value=1.0, units="T", provenance_type=ProvenanceType.SIMULATED)
        unknown_id = str(uuid.uuid4())  # not registered and not in vault_ids

        builder = ReportBuilder("R4 regression — genuine out-of-vault")
        builder.add(dp, label="B_sat")
        builder.narrative(f"Refer to external result [{unknown_id}].")

        report = builder.build(
            run_honesty_gate=True,
            raise_on_violation=False,
            vault_ids={str(uuid.uuid4())},  # neither dp.id nor unknown_id is here
        )

        out_of_vault = [v for v in report.violations if v.kind is ViolationKind.OUT_OF_VAULT_VALUE]
        assert len(out_of_vault) >= 1, (
            "A genuinely unknown UUID in the narrative must still raise OUT_OF_VAULT_VALUE."
        )

    def test_vault_ids_none_skips_vault_check(self):
        """When vault_ids=None the vault check is skipped regardless of narrative UUIDs."""
        from maglab.provenance.datapoint import DataPoint, ProvenanceType

        dp = DataPoint(value=2.0, units="T", provenance_type=ProvenanceType.MEASURED)
        random_id = str(uuid.uuid4())

        builder = ReportBuilder("R4 regression — vault_ids=None")
        builder.add(dp, label="B_sat")
        builder.narrative(f"Result [{dp.id}] and also [{random_id}].")

        report = builder.build(
            run_honesty_gate=True,
            raise_on_violation=False,
            vault_ids=None,  # vault check must be skipped entirely
        )

        out_of_vault = [v for v in report.violations if v.kind is ViolationKind.OUT_OF_VAULT_VALUE]
        assert out_of_vault == [], "vault_ids=None must suppress all OUT_OF_VAULT_VALUE checks."


# ---------------------------------------------------------------------------
# REGRESSION — Finding 1 (R11): ReportBuilder.build(raise_on_violation=True)
# must raise HonestyViolation on violation; raise_on_violation=False (default)
# must return a Report with violations populated and must not raise.
#
# Before the fix: build() forwarded raise_on_violation=True to run_gate, which
# raised HonestyViolation — but the surrounding try/except caught it and stuffed
# violations into a local list, then returned a Report instead of propagating
# the exception.  Callers expecting a hard stop silently received a Report.
# ---------------------------------------------------------------------------


class TestReportBuilderRaiseOnViolationContract:
    """R11/F1 — raise_on_violation=True must raise; =False must return Report."""

    def test_raise_on_violation_true_raises(self):
        """build(raise_on_violation=True) must raise HonestyViolation when there is a violation."""
        builder = ReportBuilder("r11-raise-true")
        builder.narrative("The saturation magnetisation is 1.23 T.")
        with pytest.raises(HonestyViolation) as exc_info:
            builder.build(run_honesty_gate=True, raise_on_violation=True)
        assert len(exc_info.value.violations) >= 1, (
            "HonestyViolation must carry the violation list."
        )

    def test_raise_on_violation_false_returns_report_with_violations(self):
        """build(raise_on_violation=False) must return a Report with violations, not raise."""
        builder = ReportBuilder("r11-raise-false")
        builder.narrative("The saturation magnetisation is 1.23 T.")
        report = builder.build(run_honesty_gate=True, raise_on_violation=False)
        assert isinstance(report, object)  # Report returned, not raised
        assert not report.passed_gate, "Report must reflect violation state."
        assert len(report.violations) >= 1, (
            "Report.violations must be populated when raise_on_violation=False."
        )

    def test_raise_on_violation_true_clean_narrative_does_not_raise(self):
        """build(raise_on_violation=True) with a clean narrative must not raise."""
        builder = ReportBuilder("r11-raise-true-clean")
        builder.narrative("Please refer to the data vault for all values.")
        report = builder.build(run_honesty_gate=True, raise_on_violation=True)
        assert report.passed_gate
        assert report.violations == []

    def test_build_report_helper_raise_on_violation_true_raises(self):
        """The build_report() convenience function must honour raise_on_violation=True."""
        from maglab.report.reporting import build_report

        with pytest.raises(HonestyViolation):
            build_report(
                title="r11-helper-raise",
                datapoints=[],
                narrative="I calculated the Gilbert damping as 0.015.",
                run_honesty_gate=True,
                raise_on_violation=True,
            )


# ---------------------------------------------------------------------------
# REGRESSION — Finding 1 (R15): run_gate(is_figure=True) must NOT produce
# duplicate UNTAGGED_NUMBER violations.
#
# Before the fix: run_gate with is_figure=True called check_untagged_numbers()
# in step 1 AND again (indirectly) via check_figure_data_tags() in step 6,
# producing two identical violations for every bare number in the text.
# The is_figure flag was intended to activate the *figure-specific* check,
# not to duplicate the general check.
# ---------------------------------------------------------------------------


class TestFigureDuplicateViolationRegression:
    """R15/F1 — run_gate(is_figure=True) must not duplicate UNTAGGED_NUMBER violations.

    Before the fix:
        run_gate('Figure 1 shows 3.14.', is_figure=True, raise_on_violation=False)
        → 4 violations (2 × UNTAGGED_NUMBER for '1' and '3.14'; bug)

    After the fix:
        → 2 violations (1 × UNTAGGED_NUMBER for '1' and '3.14'; correct)
    """

    def test_no_duplicate_violations_with_is_figure_true(self):
        """Each number in figure text must produce exactly one UNTAGGED_NUMBER violation."""
        text = "Figure 1 shows the value 3.14 without a DataPoint."
        result_figure = run_gate(text, is_figure=True, raise_on_violation=False)
        result_plain = run_gate(text, is_figure=False, raise_on_violation=False)

        figure_untagged = [
            v for v in result_figure.violations if v.kind is ViolationKind.UNTAGGED_NUMBER
        ]
        plain_untagged = [
            v for v in result_plain.violations if v.kind is ViolationKind.UNTAGGED_NUMBER
        ]
        assert len(figure_untagged) == len(plain_untagged), (
            f"run_gate(is_figure=True) produced {len(figure_untagged)} UNTAGGED_NUMBER "
            f"violations but run_gate(is_figure=False) produced {len(plain_untagged)}. "
            "is_figure=True must not duplicate violations."
        )

    def test_figure_gate_detects_untagged_numbers(self):
        """run_gate(is_figure=True) must still detect untagged numbers (not suppress them)."""
        text = "Figure 2: saturation magnetisation 1.23 T."
        result = run_gate(text, is_figure=True, raise_on_violation=False)
        untagged = [v for v in result.violations if v.kind is ViolationKind.UNTAGGED_NUMBER]
        assert len(untagged) >= 1, (
            "is_figure=True must still detect bare numbers; check_figure_data_tags must run."
        )

    def test_figure_gate_no_figure_context_still_clean(self):
        """When is_figure=True but no figure keyword in text, no untagged violations fire."""
        text = "The saturation magnetisation is high."
        result = run_gate(text, is_figure=True, raise_on_violation=False)
        untagged = [v for v in result.violations if v.kind is ViolationKind.UNTAGGED_NUMBER]
        assert untagged == [], (
            "is_figure=True with no figure-context keyword must not flag any numbers "
            "(check_figure_data_tags returns [] when no figure context is detected)."
        )

    def test_is_figure_false_checks_numbers_in_all_text(self):
        """is_figure=False runs the general untagged-number check unconditionally."""
        text = "The saturation magnetisation is 1.23 T."
        result = run_gate(text, is_figure=False, raise_on_violation=False)
        untagged = [v for v in result.violations if v.kind is ViolationKind.UNTAGGED_NUMBER]
        assert len(untagged) >= 1, (
            "is_figure=False must still detect bare numbers via the general check."
        )
