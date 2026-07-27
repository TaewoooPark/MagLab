"""Integrity test — citation auditor blocking gate (§16.4, §16.7, §20).

This test injects an UNSUPPORTED citation and verifies that the blocking gate
raises AuthoringBlockedError.  All checks are deterministic (no LLM-as-judge).
"""

from __future__ import annotations

import pytest

from maglab.authoring.bib_manager import BibManager
from maglab.authoring.citation_auditor import (
    PreSectionFinalizeHook,
    SemanticFinding,
    SemanticLabel,
    audit_existence,
    audit_semantics,
    preflight_citations,
)
from maglab.authoring.data_vault import AuthoringBlockedError, DataVault

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mgr_with_entries(*dois: str) -> BibManager:
    """Create a BibManager with the given DOIs pre-registered."""
    mgr = BibManager()
    for doi in dois:
        mgr.add_verified(doi, {"title": "Test Paper", "author": "A, B", "year": "2024"})
    return mgr


def _always_supports(claim: str, paper_text: str, cite_key: str) -> SemanticFinding:
    """Mock classifier: always classifies as SUPPORTS."""
    return SemanticFinding(
        cite_key=cite_key,
        claim_sentence=claim,
        label=SemanticLabel.SUPPORTS,
        confidence=0.95,
        evidence_snippet="Directly demonstrated in Fig. 3.",
    )


def _always_unsupported(claim: str, paper_text: str, cite_key: str) -> SemanticFinding:
    """Mock classifier: always classifies as UNSUPPORTED."""
    return SemanticFinding(
        cite_key=cite_key,
        claim_sentence=claim,
        label=SemanticLabel.UNSUPPORTED,
        confidence=0.9,
        evidence_snippet="Paper discusses a different effect.",
    )


def _always_uncertain(claim: str, paper_text: str, cite_key: str) -> SemanticFinding:
    """Mock classifier: always classifies as UNCERTAIN."""
    return SemanticFinding(
        cite_key=cite_key,
        claim_sentence=claim,
        label=SemanticLabel.UNCERTAIN,
        confidence=0.3,
        evidence_snippet="Full text unavailable.",
    )


# ---------------------------------------------------------------------------
# Existence verification
# ---------------------------------------------------------------------------


class TestAuditExistence:
    r"""Tests for cite-key existence verification."""

    def test_known_key_passes(self) -> None:
        r"""A cite-key present in the bib pool passes the gate."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        # Retrieve the assigned key
        key = mgr.get_verified_keys()[0]
        draft = rf"As shown in \cite{{{key}}}."
        report = audit_existence(draft, mgr, raise_on_missing=False)
        assert report.all_present

    def test_missing_key_is_detected(self) -> None:
        r"""A cite-key absent from the pool is flagged as MISSING."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        draft = r"As shown in \cite{NonExistentKey2024}."
        report = audit_existence(draft, mgr, raise_on_missing=False)
        assert not report.all_present
        assert "NonExistentKey2024" in report.missing_keys

    def test_missing_key_raises_blocking_error(self) -> None:
        r"""A missing cite-key raises AuthoringBlockedError when raise_on_missing=True."""
        mgr = BibManager()  # empty
        draft = r"This claim \cite{FakeKey2099} has no backing."
        with pytest.raises(AuthoringBlockedError, match="FakeKey2099"):
            audit_existence(draft, mgr, raise_on_missing=True)

    def test_no_citations_passes(self) -> None:
        """A draft with no citations passes without error."""
        mgr = BibManager()
        draft = "This section has no citations."
        report = audit_existence(draft, mgr, raise_on_missing=False)
        assert report.all_present

    def test_multiple_keys_all_present_passes(self) -> None:
        r"""Multiple known cite-keys all pass."""
        mgr = _make_mgr_with_entries(
            "10.1103/PhysRevLett.132.106701",
            "10.1038/s41563-022-01222-4",
        )
        keys = mgr.get_verified_keys()
        draft = rf"Results from \cite{{{keys[0]}}} and \cite{{{keys[1]}}}."
        report = audit_existence(draft, mgr, raise_on_missing=False)
        assert report.all_present

    def test_mixed_present_and_missing_reports_missing(self) -> None:
        r"""When some keys are present and some are missing, missing keys are reported."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        good_key = mgr.get_verified_keys()[0]
        draft = rf"See \cite{{{good_key}}} and \cite{{InventedKey}}."
        report = audit_existence(draft, mgr, raise_on_missing=False)
        assert not report.all_present
        assert "InventedKey" in report.missing_keys


# ---------------------------------------------------------------------------
# Semantic verification — the critical blocking test
# ---------------------------------------------------------------------------


class TestAuditSemantics:
    r"""Tests for semantic 4-class citation verification (§16.7)."""

    def test_unsupported_citation_is_blocked(self) -> None:
        """UNSUPPORTED citation → AuthoringBlockedError (§16.7 blocking gate)."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"The anomalous Hall effect is suppressed by thermal fluctuations \cite{{{key}}}."
        with pytest.raises(AuthoringBlockedError, match="blocking"):
            audit_semantics(
                draft,
                mgr,
                semantic_classify_fn=_always_unsupported,
                raise_on_blocking=True,
            )

    def test_uncertain_citation_is_blocked(self) -> None:
        """UNCERTAIN citation → AuthoringBlockedError (§16.7 blocking gate)."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"The mechanism is unclear \cite{{{key}}}."
        with pytest.raises(AuthoringBlockedError, match="blocking"):
            audit_semantics(
                draft,
                mgr,
                semantic_classify_fn=_always_uncertain,
                raise_on_blocking=True,
            )

    def test_supports_citation_passes(self) -> None:
        """SUPPORTS citation passes without error."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"A large AHE was observed \cite{{{key}}}."
        report = audit_semantics(
            draft,
            mgr,
            semantic_classify_fn=_always_supports,
            raise_on_blocking=True,
        )
        assert report.passes_gate

    def test_partial_citation_passes(self) -> None:
        """PARTIAL classification does NOT block authoring."""
        mgr = _make_mgr_with_entries("10.1038/s41563-022-01222-4")
        key = mgr.get_verified_keys()[0]
        draft = rf"Related observations were made \cite{{{key}}}."

        def _always_partial(claim, text, ck) -> SemanticFinding:
            return SemanticFinding(
                cite_key=ck,
                claim_sentence=claim,
                label=SemanticLabel.PARTIAL,
                confidence=0.6,
            )

        report = audit_semantics(
            draft, mgr, semantic_classify_fn=_always_partial, raise_on_blocking=True
        )
        assert report.passes_gate

    def test_no_citations_in_draft_passes(self) -> None:
        """A draft with no citations produces an empty SemanticReport with passes_gate=True."""
        mgr = BibManager()
        draft = "No citations in this section."
        report = audit_semantics(
            draft, mgr, semantic_classify_fn=_always_unsupported, raise_on_blocking=True
        )
        assert report.passes_gate
        assert len(report.findings) == 0

    def test_unsupported_report_contains_blocking_findings(self) -> None:
        """blocking_findings list is non-empty for UNSUPPORTED label."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"Claim \cite{{{key}}}."
        report = audit_semantics(
            draft, mgr, semantic_classify_fn=_always_unsupported, raise_on_blocking=False
        )
        assert len(report.blocking_findings) > 0


# ---------------------------------------------------------------------------
# PreSectionFinalizeHook — integrated gate
# ---------------------------------------------------------------------------


class TestPreSectionFinalizeHook:
    """Tests for the pre-section finalisation hook (§5.15, T-P6-09)."""

    def test_all_checks_pass(self) -> None:
        """Hook passes when citations are verified and no DataVault issues."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"AHE was observed \cite{{{key}}}."
        hook = PreSectionFinalizeHook(
            bib_manager=mgr,
            vault=DataVault(),
            semantic_classify_fn=_always_supports,
        )
        # Should not raise
        hook.run(draft, section="results")

    def test_missing_cite_key_blocks(self) -> None:
        """Hook raises AuthoringBlockedError for a missing cite-key."""
        mgr = BibManager()  # empty pool
        draft = r"See \cite{InventedKey}."
        hook = PreSectionFinalizeHook(bib_manager=mgr, vault=DataVault())
        with pytest.raises(AuthoringBlockedError):
            hook.run(draft, section="methods")

    def test_unsupported_citation_blocks(self) -> None:
        """Hook raises AuthoringBlockedError for an UNSUPPORTED citation."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"Contradictory claim \cite{{{key}}}."
        hook = PreSectionFinalizeHook(
            bib_manager=mgr,
            vault=DataVault(),
            semantic_classify_fn=_always_unsupported,
        )
        with pytest.raises(AuthoringBlockedError):
            hook.run(draft)

    def test_missing_data_vault_key_blocks(self) -> None:
        """Hook raises AuthoringBlockedError when a DataVault key is absent."""
        mgr = BibManager()
        vault = DataVault()  # empty vault
        draft = r"Field strength {{dp:B_applied}} was applied."
        hook = PreSectionFinalizeHook(bib_manager=mgr, vault=vault)
        with pytest.raises(AuthoringBlockedError, match="B_applied"):
            hook.run(draft, section="methods")


# ---------------------------------------------------------------------------
# Preflight citations
# ---------------------------------------------------------------------------


class TestPreflightCitations:
    """Tests for the preflight_citations pipeline."""

    def test_no_search_fn_returns_empty_pool(self) -> None:
        """Without a search function, preflight returns an empty pool (offline mode)."""
        pool = preflight_citations("AHE in GdFeCo")
        assert pool.cite_keys == []

    def test_search_fn_verified_results_added(self) -> None:
        """Verified candidates from search_fn are added to the pool."""
        mgr = BibManager()

        def _mock_search(topic: str, n: int):  # noqa: ARG001
            return [
                {
                    "doi": "10.1103/PhysRevLett.132.106701",
                    "title": "AHE Paper",
                    "author": "A, B",
                    "year": "2024",
                },
            ]

        pool = preflight_citations(
            "AHE",
            n_candidates=1,
            bib_manager=mgr,
            search_fn=_mock_search,
        )
        assert len(pool.cite_keys) == 1
        assert mgr.has_doi("10.1103/PhysRevLett.132.106701")

    def test_doi_verify_fn_false_excludes_entry(self) -> None:
        """Candidates that fail DOI verification are excluded from the pool."""
        mgr = BibManager()

        def _mock_search(topic: str, n: int):  # noqa: ARG001
            return [
                {
                    "doi": "10.1103/PhysRevLett.132.106701",
                    "title": "P",
                    "author": "A",
                    "year": "2024",
                }
            ]

        pool = preflight_citations(
            "AHE",
            bib_manager=mgr,
            search_fn=_mock_search,
            doi_verify_fn=lambda doi: False,  # always fails
        )
        assert len(pool.cite_keys) == 0


# ---------------------------------------------------------------------------
# FIX 3: No-LLM fallback must NOT hard-block existence-verified citations
# ---------------------------------------------------------------------------


class TestNoLLMFallback:
    """When no semantic_classify_fn is injected, authoring must NOT be blocked.

    The existence check still runs and blocks on missing keys; the semantic
    fallback must use PARTIAL (non-blocking) rather than UNCERTAIN (blocking).
    """

    def test_no_classifier_does_not_block_verified_citations(self) -> None:
        """audit_semantics with no classifier must pass for existence-verified citations."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"Spin-orbit torque was measured \cite{{{key}}}."

        # No semantic_classify_fn injected — should use the PARTIAL fallback.
        report = audit_semantics(
            draft,
            mgr,
            semantic_classify_fn=None,  # explicitly None
            raise_on_blocking=True,
        )
        # Must not raise AuthoringBlockedError; PARTIAL is non-blocking.
        assert report.passes_gate

    def test_no_classifier_produces_partial_label(self) -> None:
        """The default fallback must return PARTIAL, not UNCERTAIN."""
        from maglab.authoring.citation_auditor import (
            SemanticLabel,
            _default_semantic_fn,
        )

        finding = _default_semantic_fn("A claim.", "paper text", "SomeKey2024")
        assert finding.label == SemanticLabel.PARTIAL, (
            f"Default fallback must return PARTIAL, got {finding.label!r}"
        )

    def test_no_classifier_hook_passes_with_verified_citations(self) -> None:
        """PreSectionFinalizeHook with no semantic_classify_fn must not block verified cites."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"As demonstrated in \cite{{{key}}}."

        # Create hook without a semantic classifier.
        hook = PreSectionFinalizeHook(
            bib_manager=mgr,
            vault=DataVault(),
            semantic_classify_fn=None,  # no LLM
        )

        # Must not raise — PARTIAL fallback is non-blocking.
        hook.run(draft, section="results")

    def test_no_classifier_hook_still_blocks_missing_keys(self) -> None:
        """Existence check must still block on missing keys even without a classifier."""
        mgr = BibManager()  # empty pool
        draft = r"See \cite{InventedKey2099}."

        hook = PreSectionFinalizeHook(
            bib_manager=mgr,
            vault=DataVault(),
            semantic_classify_fn=None,
        )

        with pytest.raises(AuthoringBlockedError, match="InventedKey2099"):
            hook.run(draft, section="introduction")

    def test_injected_classifier_uncertain_still_blocks(self) -> None:
        """A real injected classifier returning UNCERTAIN must still block authoring."""
        mgr = _make_mgr_with_entries("10.1103/PhysRevLett.132.106701")
        key = mgr.get_verified_keys()[0]
        draft = rf"An uncertain claim \cite{{{key}}}."

        # Inject an LLM-like classifier that returns UNCERTAIN.
        with pytest.raises(AuthoringBlockedError, match="blocking"):
            audit_semantics(
                draft,
                mgr,
                semantic_classify_fn=_always_uncertain,
                raise_on_blocking=True,
            )

    def test_no_classifier_fallback_produces_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The default fallback must log a warning when skipping semantic verification."""
        import logging

        from maglab.authoring.citation_auditor import _default_semantic_fn

        with caplog.at_level(logging.WARNING, logger="maglab.authoring.citation_auditor"):
            _default_semantic_fn("A claim.", "", "SomeKey2024")

        assert any("semantic" in r.message.lower() for r in caplog.records), (
            "Expected a warning about skipped semantic verification, got: "
            + str([r.message for r in caplog.records])
        )


class TestCitationIdentifiersAreNotMeasurements:
    """A DOI is a reference, not a measured value.

    `10.1088/0034-4885/74/3/036501` produced six UNTAGGED_NUMBER violations, so
    any answer citing literature drowned the gate in noise — and a gate that
    fires on every reference is one people switch off.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "See DOI: 10.1088/0034-4885/74/3/036501.",
            "Refs: 10.1038/s41467-020-20692-1 and 10.1103/revmodphys.90.015005.",
            "Preprint arXiv:1901.07879 covers this.",
            "10.48550/arxiv.1901.07879",
        ],
    )
    def test_identifiers_alone_raise_nothing(self, text: str) -> None:
        from maglab.report.honesty_gate import run_gate

        assert run_gate(text, raise_on_violation=False).violations == []

    def test_real_untagged_values_are_still_caught(self) -> None:
        from maglab.report.honesty_gate import run_gate

        result = run_gate("The measured Ms is 8.0e5 A/m.", raise_on_violation=False)

        assert [v.kind.value for v in result.violations] == ["UNTAGGED_NUMBER"]

    def test_a_value_beside_a_doi_is_still_caught(self) -> None:
        """Masking identifiers must not create a hiding place for real numbers."""
        from maglab.report.honesty_gate import run_gate

        result = run_gate("Ms = 8.0e5 A/m [10.1038/nmat4566].", raise_on_violation=False)

        messages = [v.message for v in result.violations]
        assert len(messages) == 1
        assert "8.0e5" in messages[0]
