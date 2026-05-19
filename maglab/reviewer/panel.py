"""Three-person parallel reviewer panel (§15.1·§15.3).

Combines author corpus RAG, rubrics, and seven safeguards to form a
three-person panel and conduct reviews in parallel.

LLM calls are defined by interface only; replaced by mocks in tests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from maglab.reviewer.corpus_rag import CorpusRAG, SearchResult
from maglab.reviewer.disclosure import PersonaDisclosureError, PersonaGuard
from maglab.reviewer.rubrics import (
    DimensionScore,
    ReviewScore,
    Rubric,
    ScoreDimension,
    get_rubric,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persona reviewer
# ---------------------------------------------------------------------------


@dataclass
class PersonaSpec:
    """Persona reviewer specification.

    Attributes
    ----------
    author_id:
        Author ID (S2 or arXiv format).
    author_name:
        Author display name.
    paper_count:
        Number of corpus papers (for disclosure label).
    verified_dois:
        Verified DOI set retrieved from corpus RAG.
    """

    author_id: str
    author_name: str = ""
    paper_count: int = 0
    verified_dois: set[str] = field(default_factory=set)


@dataclass
class PersonaReview:
    """Single persona review result.

    Attributes
    ----------
    persona:
        Reviewer persona specification.
    score:
        Rubric score.
    review_text:
        Full review text (all seven safeguards applied).
    rag_chunks_used:
        Chunks cited from RAG (prevents fabricated citations).
    validation_errors:
        Rubric validation error list.
    disclosure_passed:
        Whether all seven safeguards passed.
    """

    persona: PersonaSpec
    score: ReviewScore
    review_text: str
    rag_chunks_used: list[SearchResult] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    disclosure_passed: bool = True


# ---------------------------------------------------------------------------
# Panel review
# ---------------------------------------------------------------------------


@dataclass
class PanelReview:
    """Three-person panel review result.

    Attributes
    ----------
    journal:
        Target journal for evaluation.
    reviews:
        List of three individual reviews.
    rubric:
        Applied rubric.
    """

    journal: str
    reviews: list[PersonaReview]
    rubric: Rubric


# ---------------------------------------------------------------------------
# ReviewPanel
# ---------------------------------------------------------------------------


class ReviewPanel:
    """Three-person parallel reviewer panel (§15.1·§15.3).

    Parameters
    ----------
    personas:
        List of panel persona specifications (typically 3).
    corpus_rag:
        Author corpus RAG index.
    journal:
        Target journal identifier for evaluation.
    llm_review_fn:
        LLM review generation function.
        Signature: (persona: PersonaSpec, manuscript: str, rag_results: list[SearchResult],
                   rubric: Rubric) -> str
        None generates dummy reviews (test mode).
    """

    def __init__(
        self,
        personas: list[PersonaSpec],
        corpus_rag: CorpusRAG,
        journal: str = "general",
        llm_review_fn: Callable[..., str] | None = None,
    ) -> None:
        self._personas = personas
        self._rag = corpus_rag
        self._journal = journal
        self._rubric = get_rubric(journal)
        self._llm_fn = llm_review_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review(
        self,
        manuscript: str,
        *,
        rag_top_k: int = 3,
        raise_on_disclosure_violation: bool = True,
    ) -> PanelReview:
        """Have the three-person panel review a manuscript in parallel.

        Parameters
        ----------
        manuscript:
            Manuscript text to review.
        rag_top_k:
            Number of RAG search results per persona.
        raise_on_disclosure_violation:
            If True, raises an exception on seven-safeguard violations.

        Returns
        -------
        PanelReview
        """
        reviews = []
        for persona in self._personas:
            pr = self._review_single(
                persona,
                manuscript,
                rag_top_k=rag_top_k,
                raise_on_disclosure_violation=raise_on_disclosure_violation,
            )
            reviews.append(pr)

        return PanelReview(
            journal=self._journal,
            reviews=reviews,
            rubric=self._rubric,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _review_single(
        self,
        persona: PersonaSpec,
        manuscript: str,
        *,
        rag_top_k: int,
        raise_on_disclosure_violation: bool,
    ) -> PersonaReview:
        """Conduct a single persona review."""
        # Check opt-out
        guard = PersonaGuard(
            author_id=persona.author_id,
            author_name=persona.author_name,
            verified_dois=persona.verified_dois,
        )
        optout_violations = guard.check_author_eligibility()
        if optout_violations:
            raise PersonaDisclosureError(optout_violations)

        # RAG search (author namespace)
        rag_results = self._rag.search(
            manuscript[:1000],  # Query with the beginning of the manuscript
            author_id=persona.author_id,
            top_k=rag_top_k,
        )

        # Generate LLM review
        if self._llm_fn is not None:
            raw_review = self._llm_fn(persona, manuscript, rag_results, self._rubric)
        else:
            # Test dummy review
            raw_review = self._dummy_review(persona, rag_results)

        # Apply seven safeguards
        raw_review = guard.add_disclosure(raw_review, persona.paper_count)
        disclosure_passed = True
        try:
            guard.guard(raw_review, raise_on_violation=raise_on_disclosure_violation)
        except PersonaDisclosureError:
            disclosure_passed = False
            if raise_on_disclosure_violation:
                raise

        # Generate dummy scores (when no LLM)
        score = self._make_dummy_score(persona)
        validation_errors = score.validate(self._rubric)

        return PersonaReview(
            persona=persona,
            score=score,
            review_text=raw_review,
            rag_chunks_used=rag_results,
            validation_errors=validation_errors,
            disclosure_passed=disclosure_passed,
        )

    def _dummy_review(
        self,
        persona: PersonaSpec,
        rag_results: list[SearchResult],
    ) -> str:
        """Generate a dummy review text for testing."""
        rag_summary = ""
        if rag_results:
            chunk = rag_results[0].chunk
            rag_summary = (
                f"\nRelevant corpus reference: {chunk.title} (DOI: {chunk.doi})\nExcerpt: {chunk.text[:100]}..."
            )

        return (
            f"[AI Reviewer — Corpus Model] "
            f"This review was generated by an AI Reviewer modeled from "
            f"{persona.paper_count} public papers by {persona.author_name or persona.author_id}. "
            f"This is not {persona.author_name or persona.author_id}'s actual opinion or endorsement.\n"
            f"{rag_summary}\n"
            "This manuscript requires examination from methodological and results-presentation perspectives."
        )

    def _make_dummy_score(self, persona: PersonaSpec) -> ReviewScore:
        """Generate dummy scores for testing."""
        return ReviewScore(
            scores=[
                DimensionScore(
                    dimension=ScoreDimension.NOVELTY,
                    score=6.0,
                    rationale="Novelty assessment",
                    evidence_sections=["Introduction §1"],
                ),
                DimensionScore(
                    dimension=ScoreDimension.SOUNDNESS,
                    score=7.0,
                    rationale="Methodological soundness",
                    evidence_sections=["Methods §2"],
                ),
                DimensionScore(
                    dimension=ScoreDimension.SIGNIFICANCE,
                    score=6.0,
                    rationale="Field impact",
                    evidence_sections=["Discussion §4"],
                ),
                DimensionScore(
                    dimension=ScoreDimension.CLARITY,
                    score=7.0,
                    rationale="Presentation clarity",
                    evidence_sections=["Abstract"],
                ),
                DimensionScore(
                    dimension=ScoreDimension.OVERALL,
                    score=6.5,
                    rationale="Overall assessment",
                    evidence_sections=["Abstract", "Conclusion"],
                ),
            ],
            journal=self._journal,
            reviewer_persona=persona.author_name or persona.author_id,
            summary_recommendation="Minor Revision",
        )
