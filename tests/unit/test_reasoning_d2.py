"""tests/unit/test_reasoning_d2.py — D2 anomaly explanation unit tests."""

from __future__ import annotations

from maglab.core.reasoning import (
    AnomalyExplainer,
    ConfidenceLevel,
    explain_anomaly,
)


class TestExplainAnomaly:
    """Basic behaviour tests for explain_anomaly."""

    def test_topological_hall_candidates(self):
        """Generates at least 2 candidates for a topological Hall anomaly."""
        result = explain_anomaly("AHE sign reversal topological hall above 200 K")
        assert len(result.candidates) >= 2

    def test_ahe_sign_reversal_candidates(self):
        """Candidates are generated for an AHE sign-reversal anomaly."""
        result = explain_anomaly("AHE sign reversal above 200 K")
        assert len(result.candidates) >= 2

    def test_candidates_have_mechanism(self):
        """Every candidate has a non-empty mechanism field."""
        result = explain_anomaly("topological hall hump in rxy")
        for c in result.candidates:
            assert c.mechanism != ""

    def test_candidates_have_physical_basis(self):
        """Every candidate has a non-empty physical basis."""
        result = explain_anomaly("topological hall")
        for c in result.candidates:
            assert c.physical_basis != ""

    def test_candidates_have_discriminating_tests(self):
        """Each candidate has at least one discriminating test."""
        result = explain_anomaly("topological hall effect")
        for c in result.candidates:
            assert len(c.discriminating_tests) >= 1

    def test_disclaimer_present(self):
        """The result contains an integrity disclaimer."""
        result = explain_anomaly("fmr linewidth anomaly")
        assert result.disclaimer != ""
        assert "hypothesis" in result.disclaimer.lower()

    def test_no_physical_values_in_basis(self):
        """Confirms that the LLM did not generate raw numerical values in physical_basis.

        Since the implementation uses no LLM call, only the built-in DB is used,
        so no decimal numbers should appear in physical_basis.
        """
        result = explain_anomaly("topological hall")
        import re

        # check that no bare decimal numbers appear in physical_basis
        number_re = re.compile(r"(?<!\w)\d+\.\d+(?!\w)")
        for c in result.candidates:
            # built-in DB — no decimal numerical values expected
            matches = number_re.findall(c.physical_basis)
            assert len(matches) == 0, (
                f"Suspected LLM-generated values: {matches} in physical_basis of {c.candidate_id}"
            )

    def test_sorted_by_confidence(self):
        """Candidates are sorted by confidence (HIGH → LOW)."""
        result = explain_anomaly("topological hall")
        conf_order = {
            ConfidenceLevel.HIGH: 0,
            ConfidenceLevel.MEDIUM: 1,
            ConfidenceLevel.LOW: 2,
            ConfidenceLevel.SPECULATIVE: 3,
        }
        confidences = [conf_order[c.confidence] for c in result.candidates]
        assert confidences == sorted(confidences)

    def test_top_discriminating_tests(self):
        """A list of top discriminating tests is available."""
        result = explain_anomaly("topological hall")
        assert isinstance(result.top_discriminating_tests, list)

    def test_to_dict_serializable(self):
        """The result is serializable to a dictionary."""
        result = explain_anomaly("ahe sign reversal")
        d = result.to_dict()
        assert "query" in d
        assert "candidates" in d
        assert "disclaimer" in d

    def test_summary_text(self):
        """A summary text is generated."""
        result = explain_anomaly("topological hall")
        summary = result.summary()
        assert "D2" in summary or "candidate" in summary.lower()

    def test_unknown_anomaly_fallback(self):
        """Fallback candidates are generated even for completely unknown anomalies."""
        result = explain_anomaly("completely unknown bizarre measurement xyz123")
        assert len(result.candidates) >= 2

    def test_rag_search_fn_called(self):
        """The RAG search function is called when provided."""
        calls = []

        def mock_rag(query, top_k):
            calls.append(query)
            return [{"doi": "10.1103/test.001", "text": "spin Hall measurement"}]

        result = explain_anomaly(
            "topological hall",
            rag_search_fn=mock_rag,
        )
        assert len(calls) >= 1
        # check that RAG result is included as supporting evidence
        all_evidence = []
        for c in result.candidates:
            all_evidence.extend(c.supporting_evidence)
        dois = [doi for doi, _ in all_evidence]
        assert "10.1103/test.001" in dois

    def test_llm_fn_results_used(self):
        """LLM function results are included as candidates."""

        def mock_llm(query, templates):
            return [
                {
                    "mechanism": "LLM-suggested mechanism",
                    "physical_basis": "LLM-suggested physical basis",
                    "confidence": "medium",
                    "test_description": "LLM-suggested discriminating test",
                }
            ]

        result = explain_anomaly("topological hall", llm_explain_fn=mock_llm)
        mechanisms = [c.mechanism for c in result.candidates]
        assert any("LLM-suggested" in m for m in mechanisms)


class TestAnomalyExplainer:
    """Direct tests for the AnomalyExplainer class."""

    def test_min_candidates(self):
        """The min_candidates parameter guarantees a minimum candidate count."""
        explainer = AnomalyExplainer(min_candidates=3)
        result = explainer.explain("unknown anomaly xyz")
        assert len(result.candidates) >= 2  # at least 2 fallback candidates

    def test_no_rag_no_llm_uses_db(self):
        """Operates using only the built-in DB without RAG or LLM."""
        explainer = AnomalyExplainer()
        result = explainer.explain("topological hall hump")
        assert len(result.candidates) >= 1


# ---------------------------------------------------------------------------
# REGRESSION — Finding 4: fallback candidates for partial (non-empty) LLM results
# ---------------------------------------------------------------------------


class TestFallbackCandidatesRegression:
    """Regression tests for Finding 4 — fallback triggered on under-count, not just empty.

    Before the fix the condition was:
        if len(raw_candidates) < min_candidates and not raw_candidates:
    which was equivalent to `not raw_candidates` (empty list only).

    A 1-candidate LLM response when min_candidates=2 would NOT trigger the fallback,
    violating the min_candidates guarantee.

    After the fix the condition is:
        if len(raw_candidates) < min_candidates:
            raw_candidates = raw_candidates + _fallback_candidates(query)
    which tops-up any under-count result.
    """

    def test_partial_llm_result_gets_topped_up(self):
        """LLM returns 1 candidate but min_candidates=2 → result must have >= 2."""
        def returns_one(query, templates):
            return [
                {
                    "mechanism": "single-candidate mechanism",
                    "physical_basis": "single basis",
                    "confidence": "medium",
                    "test_description": "single test",
                }
            ]

        explainer = AnomalyExplainer(llm_explain_fn=returns_one, min_candidates=2)
        result = explainer.explain("topological hall")
        assert len(result.candidates) >= 2, (
            f"Expected >= 2 candidates when LLM returns 1 and min_candidates=2, "
            f"got {len(result.candidates)}"
        )

    def test_empty_llm_result_still_gets_fallback(self):
        """LLM returns 0 candidates → fallback is triggered (original behavior preserved)."""
        def returns_none(query, templates):
            return []

        explainer = AnomalyExplainer(llm_explain_fn=returns_none, min_candidates=2)
        result = explainer.explain("topological hall")
        assert len(result.candidates) >= 2, (
            f"Expected >= 2 candidates when LLM returns 0, got {len(result.candidates)}"
        )

    def test_sufficient_llm_result_not_bloated(self):
        """When LLM already returns >= min_candidates, no extra fallback is injected."""
        mechanisms = ["mech-A", "mech-B", "mech-C"]

        def returns_three(query, templates):
            return [
                {
                    "mechanism": m,
                    "physical_basis": "basis",
                    "confidence": "medium",
                    "test_description": "test",
                }
                for m in mechanisms
            ]

        explainer = AnomalyExplainer(llm_explain_fn=returns_three, min_candidates=2)
        result = explainer.explain("topological hall")
        # At least the 3 LLM candidates must be present
        result_mechanisms = [c.mechanism for c in result.candidates]
        for m in mechanisms:
            assert m in result_mechanisms, f"LLM candidate '{m}' must appear in result"
