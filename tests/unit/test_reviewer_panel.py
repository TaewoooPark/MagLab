"""tests/unit/test_reviewer_panel.py — ReviewPanel and MetaReviewer unit tests."""

from __future__ import annotations

import uuid

import pytest

from maglab.reviewer.corpus_rag import CorpusChunk, CorpusRAG
from maglab.reviewer.disclosure import (
    PersonaDisclosureError,
    clear_optout_registry,
    register_optout,
)
from maglab.reviewer.meta_reviewer import MetaReviewer
from maglab.reviewer.panel import PanelReview, PersonaSpec, ReviewPanel


def _make_rag_with_chunks(n: int = 3) -> CorpusRAG:
    rag = CorpusRAG()
    for i in range(n):
        rag.add_chunk(
            CorpusChunk(
                chunk_id=str(uuid.uuid4()),
                author_id=f"author_{i}",
                doi=f"10.1103/test.{i:03d}",
                title=f"Paper {i}",
                text=f"spin Hall effect measurement {i}",
            )
        )
    return rag


def _make_personas(n: int = 3) -> list[PersonaSpec]:
    return [
        PersonaSpec(
            author_id=f"author_{i}",
            author_name=f"Prof. Author{i}",
            paper_count=10 + i,
            verified_dois={f"10.1103/test.{i:03d}"},
        )
        for i in range(n)
    ]


class TestReviewPanel:
    """ReviewPanel basic behavior tests."""

    def setup_method(self):
        clear_optout_registry()

    def test_panel_review_returns_three_reviews(self):
        rag = _make_rag_with_chunks()
        personas = _make_personas(3)
        panel = ReviewPanel(personas=personas, corpus_rag=rag)
        result = panel.review("This is a test manuscript about spin Hall effect.")
        assert len(result.reviews) == 3

    def test_all_reviews_have_disclosure_label(self):
        """All reviews must contain the AI disclosure label."""
        rag = _make_rag_with_chunks()
        personas = _make_personas(3)
        panel = ReviewPanel(personas=personas, corpus_rag=rag)
        result = panel.review("Test manuscript.")
        for review in result.reviews:
            assert review.disclosure_passed
            assert (
                "AI Reviewer" in review.review_text or "corpus model" in review.review_text.lower()
            )

    def test_opted_out_author_raises(self):
        """Including an opted-out author in the panel raises an error."""
        register_optout("blocked_author")
        rag = CorpusRAG()
        persona = PersonaSpec(
            author_id="blocked_author",
            author_name="Blocked",
            paper_count=0,
        )
        panel = ReviewPanel(personas=[persona], corpus_rag=rag)
        with pytest.raises(PersonaDisclosureError):
            panel.review("manuscript text")

    def test_panel_review_journal_set(self):
        rag = _make_rag_with_chunks()
        personas = _make_personas(1)
        panel = ReviewPanel(personas=personas, corpus_rag=rag, journal="prl")
        result = panel.review("manuscript")
        assert result.journal == "prl"


class TestMetaReviewer:
    """MetaReviewer consensus and dissent tests."""

    def _run_panel_review(self, journal: str = "general") -> PanelReview:

        rag = _make_rag_with_chunks()
        personas = _make_personas(3)
        panel = ReviewPanel(personas=personas, corpus_rag=rag, journal=journal)
        return panel.review("Test manuscript about spin orbitronics.")

    def test_meta_review_has_consensus(self):
        panel_review = self._run_panel_review()
        meta = MetaReviewer().synthesize(panel_review)
        # Dummy scores are identical, so all dimensions should be consensus (zero dissents)
        assert isinstance(meta.consensus, list)
        assert isinstance(meta.dissents, list)

    def test_meta_review_has_scores(self):
        panel_review = self._run_panel_review()
        meta = MetaReviewer().synthesize(panel_review)
        assert len(meta.panel_mean_scores) > 0

    def test_meta_review_has_recommendation(self):
        panel_review = self._run_panel_review()
        meta = MetaReviewer().synthesize(panel_review)
        assert meta.overall_recommendation != ""

    def test_meta_review_summary_has_journal(self):
        panel_review = self._run_panel_review(journal="prl")
        meta = MetaReviewer().synthesize(panel_review)
        assert "PRL" in meta.summary or "prl" in meta.summary.lower()

    def test_dissent_threshold_detection(self):
        """Dimensions with score spread ≥3 points are classified as dissents."""
        from maglab.reviewer.rubrics import DimensionScore, ReviewScore, ScoreDimension

        # Artificially construct reviews with a dissent
        def make_score(novelty: float) -> ReviewScore:
            return ReviewScore(
                scores=[
                    DimensionScore(ScoreDimension.NOVELTY, novelty, "r", ["§1"]),
                    DimensionScore(ScoreDimension.SOUNDNESS, 7.0, "r", ["§2"]),
                    DimensionScore(ScoreDimension.SIGNIFICANCE, 7.0, "r", ["§3"]),
                    DimensionScore(ScoreDimension.CLARITY, 7.0, "r", ["§4"]),
                    DimensionScore(ScoreDimension.OVERALL, 7.0, "r", ["§5"]),
                ]
            )

        rag = _make_rag_with_chunks()
        personas = _make_personas(3)
        panel_review_base = ReviewPanel(personas=personas, corpus_rag=rag).review("test")

        # First reviewer: novelty=2, others: novelty=9 → spread of 7 points
        panel_review_base.reviews[0].score = make_score(2.0)
        panel_review_base.reviews[1].score = make_score(9.0)
        panel_review_base.reviews[2].score = make_score(9.0)

        meta = MetaReviewer(dissent_threshold=3.0).synthesize(panel_review_base)
        dissent_dims = {d.dimension for d in meta.dissents}
        assert ScoreDimension.NOVELTY in dissent_dims


# ---------------------------------------------------------------------------
# Regression tests — F-04: dummy score not used when llm_review_fn provided
# ---------------------------------------------------------------------------


class TestF04LLMScoreUsed:
    """Regression tests for F-04: when an llm_review_fn is provided, the
    PersonaReview.score must come from the LLM output — not from the dummy."""

    def setup_method(self):
        clear_optout_registry()

    def test_llm_fn_returning_tuple_uses_real_score(self):
        """When llm_review_fn returns (text, ReviewScore), that score is used."""
        from maglab.reviewer.rubrics import DimensionScore, ReviewScore, ScoreDimension

        rag = _make_rag_with_chunks()
        personas = _make_personas(1)

        real_score = ReviewScore(
            scores=[
                DimensionScore(ScoreDimension.NOVELTY, 9.5, "outstanding", ["§1"]),
                DimensionScore(ScoreDimension.SOUNDNESS, 9.0, "solid", ["§2"]),
                DimensionScore(ScoreDimension.SIGNIFICANCE, 9.0, "major", ["§3"]),
                DimensionScore(ScoreDimension.CLARITY, 8.5, "clear", ["§4"]),
                DimensionScore(ScoreDimension.OVERALL, 9.0, "accept", ["§5"]),
            ],
            summary_recommendation="Accept",
        )

        def fake_llm(persona, manuscript, rag_results, rubric):
            review_text = (
                "[AI Reviewer — Corpus Model] "
                "This review was generated by an AI Reviewer modeled from "
                f"{persona.paper_count} public papers by {persona.author_name}. "
                f"This is not {persona.author_name}'s actual opinion or endorsement.\n\n"
                "The manuscript is outstanding and should be accepted."
            )
            return (review_text, real_score)

        panel = ReviewPanel(personas=personas, corpus_rag=rag, llm_review_fn=fake_llm)
        result = panel.review("Test manuscript.")

        assert len(result.reviews) == 1
        pr = result.reviews[0]
        # The score must come from the LLM function — NOT the dummy (6.0/7.0/…)
        novelty_score = next(d.score for d in pr.score.scores if d.dimension.value == "novelty")
        assert novelty_score == 9.5, f"Expected real LLM score 9.5, got dummy score {novelty_score}"

    def test_llm_fn_returning_str_uses_fallback_dummy(self):
        """When llm_review_fn returns only str (no score), dummy is used as fallback."""
        rag = _make_rag_with_chunks()
        personas = _make_personas(1)

        def fake_llm_text_only(persona, manuscript, rag_results, rubric):
            return (
                "[AI Reviewer — Corpus Model] "
                "This review was generated by an AI Reviewer modeled from "
                f"{persona.paper_count} public papers by {persona.author_name}. "
                f"This is not {persona.author_name}'s actual opinion or endorsement.\n\n"
                "The manuscript is solid."
            )

        panel = ReviewPanel(personas=personas, corpus_rag=rag, llm_review_fn=fake_llm_text_only)
        result = panel.review("Test manuscript.")
        pr = result.reviews[0]
        # Dummy scores are used: NOVELTY = 6.0
        novelty_score = next(d.score for d in pr.score.scores if d.dimension.value == "novelty")
        assert novelty_score == 6.0, f"Expected dummy NOVELTY score 6.0, got {novelty_score}"

    def test_no_llm_fn_uses_dummy_score(self):
        """No llm_review_fn → dummy score (test mode unchanged)."""
        rag = _make_rag_with_chunks()
        personas = _make_personas(1)
        panel = ReviewPanel(personas=personas, corpus_rag=rag)  # no llm_fn
        result = panel.review("Test manuscript.")
        pr = result.reviews[0]
        novelty_score = next(d.score for d in pr.score.scores if d.dimension.value == "novelty")
        # Dummy: 6.0 (hardcoded in _make_dummy_score)
        assert novelty_score == 6.0


# ---------------------------------------------------------------------------
# Regression tests — F1: arXiv safeguard not bypassed with default PersonaSpec
# ---------------------------------------------------------------------------


class TestF1ArXivSafeguardViaPanelDefaultPersona:
    """Regression tests for F1 (legacy arXiv pass-through fix).

    These tests verify that verified_dois/verified_arxivs pass through
    ReviewPanel._review_single correctly: a populated set enforces the whitelist;
    None (the default) skips per-ID validation (correct lenient behavior).
    """

    def setup_method(self) -> None:
        clear_optout_registry()

    def test_arxiv_id_not_flagged_with_default_persona_spec(self) -> None:
        """When PersonaSpec uses the default verified_arxivs=None, arXiv IDs are
        NOT validated against a whitelist — no false FABRICATED_CITATION violation.

        This tests the corrected lenient-default semantics: None means
        'no whitelist supplied, skip per-ID check'.
        """
        from maglab.reviewer.corpus_rag import CorpusChunk, CorpusRAG

        rag = CorpusRAG()
        rag.add_chunk(
            CorpusChunk(
                chunk_id="f1-chunk-001",
                author_id="f1_author",
                doi="10.1234/real.001",
                title="A Real Paper",
                text="spin Hall effect measurement",
            )
        )

        # PersonaSpec with NO verified_arxivs provided (defaults to None)
        persona = PersonaSpec(
            author_id="f1_author",
            author_name="Prof. F1",
            paper_count=1,
            verified_dois={"10.1234/real.001"},
            # verified_arxivs intentionally omitted → defaults to None
        )

        # LLM returns a review that contains an arXiv ID
        review_with_arxiv = (
            "[AI Reviewer — Corpus Model] "
            "This review was generated by an AI Reviewer modeled from 1 public papers by Prof. F1. "
            "This is not Prof. F1's actual opinion or endorsement.\n\n"
            "The foundational theory is described in arXiv:9999.99999."
        )

        def fake_llm(p: PersonaSpec, manuscript: str, rag_results: list, rubric: object) -> str:
            return review_with_arxiv

        panel = ReviewPanel(
            personas=[persona],
            corpus_rag=rag,
            llm_review_fn=fake_llm,
        )
        result = panel.review("Test manuscript.", raise_on_disclosure_violation=False)
        pr = result.reviews[0]

        # With verified_arxivs=None, arXiv IDs are not validated — disclosure must pass.
        assert pr.disclosure_passed, (
            "ReviewPanel falsely flagged arXiv:9999.99999 when verified_arxivs=None "
            "(default). None must mean 'skip per-ID arXiv whitelist check'."
        )

    def test_empty_verified_arxivs_flags_any_arxiv_id(self) -> None:
        """With an explicit empty verified_arxivs set, ANY arXiv ID in the review is
        unverified and must be flagged — an empty set is a real whitelist with no entries.
        """
        from maglab.reviewer.disclosure import DisclosureViolation, PersonaGuard

        guard = PersonaGuard(
            author_id="f1_guard_test",
            author_name="Prof. F1-Guard",
            verified_dois=set(),
            verified_arxivs=set(),  # empty set, NOT None
        )

        # Any arXiv ID should be unverified when the set is empty
        text_with_arxiv = (
            "[AI Reviewer — Corpus Model] "
            "This review was generated by an AI Reviewer modeled from 0 public papers by Prof. F1-Guard. "
            "This is not Prof. F1-Guard's actual opinion or endorsement.\n\n"
            "See arXiv:2301.00001 for context."
        )
        result = guard.guard(text_with_arxiv, raise_on_violation=False)
        fabricated = [
            v for v in result.violations if v.violation == DisclosureViolation.FABRICATED_CITATION
        ]
        assert len(fabricated) >= 1, (
            "An arXiv ID present when verified_arxivs=set() should be flagged as unverified. "
            "An explicit empty set is a whitelist with zero allowed entries."
        )
