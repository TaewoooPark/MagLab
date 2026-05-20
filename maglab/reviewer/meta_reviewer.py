"""Meta-reviewer — panel consensus and dissent synthesis (§15.3).

Synthesizes three-panel reviews to identify consensus points and dissents,
and generates a meta-review. Dimensions with a panel score spread ≥3 are
classified as dissents.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from maglab.reviewer.panel import PanelReview
from maglab.reviewer.rubrics import ScoreDimension

# ---------------------------------------------------------------------------
# Meta-review data structures
# ---------------------------------------------------------------------------


@dataclass
class ConsensusItem:
    """Consensus item agreed upon by all three reviewers.

    Attributes
    ----------
    dimension:
        Scoring dimension in question.
    mean_score:
        Panel mean score.
    std_score:
        Score standard deviation.
    common_rationale:
        Summary of shared critique.
    evidence_sections:
        List of common evidence sections.
    """

    dimension: ScoreDimension
    mean_score: float
    std_score: float
    common_rationale: str
    evidence_sections: list[str] = field(default_factory=list)


@dataclass
class DissentItem:
    """Dissent item among panel (score spread ≥3 points).

    Attributes
    ----------
    dimension:
        Scoring dimension with dissent.
    scores:
        Each reviewer's score [(reviewer_name, score), ...].
    range_:
        Score range (max - min).
    rationale:
        Summary of dissent rationale.
    """

    dimension: ScoreDimension
    scores: list[tuple[str, float]]
    range_: float
    rationale: str


@dataclass
class MetaReview:
    """Meta-review result.

    Attributes
    ----------
    consensus:
        Consensus item list (shared by all three reviewers).
    dissents:
        Dissent item list (score spread ≥3 points).
    panel_mean_scores:
        Panel mean scores by dimension.
    overall_recommendation:
        Final meta-review recommendation.
    summary:
        Meta-review summary text.
    journal:
        Target journal for evaluation.
    """

    consensus: list[ConsensusItem]
    dissents: list[DissentItem]
    panel_mean_scores: dict[str, float]
    overall_recommendation: str
    summary: str
    journal: str = "general"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a structured dict."""
        return {
            "journal": self.journal,
            "overall_recommendation": self.overall_recommendation,
            "summary": self.summary,
            "panel_mean_scores": self.panel_mean_scores,
            "consensus_count": len(self.consensus),
            "dissent_count": len(self.dissents),
            "consensus": [
                {
                    "dimension": c.dimension.value,
                    "mean_score": c.mean_score,
                    "std_score": c.std_score,
                    "rationale": c.common_rationale,
                    "evidence_sections": c.evidence_sections,
                }
                for c in self.consensus
            ],
            "dissents": [
                {
                    "dimension": d.dimension.value,
                    "scores": d.scores,
                    "range": d.range_,
                    "rationale": d.rationale,
                }
                for d in self.dissents
            ],
        }


# ---------------------------------------------------------------------------
# Meta-reviewer
# ---------------------------------------------------------------------------

# Dissent score spread threshold (max - min ≥ this value → dissent)
_DISSENT_THRESHOLD = 3.0


class MetaReviewer:
    """Synthesizes panel reviews to produce a meta-review (§15.3).

    Parameters
    ----------
    dissent_threshold:
        Score spread threshold for classifying a dimension as a dissent (default 3.0).
    """

    def __init__(self, dissent_threshold: float = _DISSENT_THRESHOLD) -> None:
        self._dissent_threshold = dissent_threshold

    def synthesize(self, panel_review: PanelReview) -> MetaReview:
        """Synthesize a panel review into a meta-review.

        Parameters
        ----------
        panel_review:
            PanelReview returned by ReviewPanel.review().

        Returns
        -------
        MetaReview
        """
        reviews = panel_review.reviews
        if not reviews:
            return MetaReview(
                consensus=[],
                dissents=[],
                panel_mean_scores={},
                overall_recommendation="N/A",
                summary="No reviewers present.",
                journal=panel_review.journal,
            )

        # Collect scores by dimension
        dim_scores: dict[ScoreDimension, list[tuple[str, float]]] = {}
        for review in reviews:
            name = review.persona.author_name or review.persona.author_id
            for ds in review.score.scores:
                dim_scores.setdefault(ds.dimension, []).append((name, ds.score))

        # Classify consensus and dissents
        consensus: list[ConsensusItem] = []
        dissents: list[DissentItem] = []
        mean_scores: dict[str, float] = {}

        for dim, name_scores in dim_scores.items():
            values = [s for _, s in name_scores]
            mean_val = statistics.mean(values) if values else 0.0
            std_val = statistics.pstdev(values) if len(values) > 1 else 0.0
            score_range = max(values) - min(values) if values else 0.0

            mean_scores[dim.value] = round(mean_val, 2)

            # Collect evidence sections
            evidence: list[str] = []
            rationales: list[str] = []
            for review in reviews:
                for ds in review.score.scores:
                    if ds.dimension == dim:
                        evidence.extend(ds.evidence_sections)
                        if ds.rationale:
                            rationales.append(ds.rationale)

            # Deduplicate
            evidence = list(dict.fromkeys(evidence))

            if score_range >= self._dissent_threshold:
                dissents.append(
                    DissentItem(
                        dimension=dim,
                        scores=name_scores,
                        range_=round(score_range, 2),
                        rationale=(
                            f"Panel score spread {score_range:.1f} points (threshold {self._dissent_threshold} points). "
                            + " / ".join(rationales[:2])
                        ),
                    )
                )
            else:
                consensus.append(
                    ConsensusItem(
                        dimension=dim,
                        mean_score=round(mean_val, 2),
                        std_score=round(std_val, 2),
                        common_rationale=" ".join(rationales[:2]) or "Panel consensus point",
                        evidence_sections=evidence[:5],
                    )
                )

        # Overall recommendation
        overall_mean = statistics.mean(mean_scores.values()) if mean_scores else 0.0
        recommendation = self._recommend(overall_mean, len(dissents))

        # Summary text
        summary = self._build_summary(
            consensus, dissents, mean_scores, recommendation, panel_review.journal
        )

        return MetaReview(
            consensus=consensus,
            dissents=dissents,
            panel_mean_scores=mean_scores,
            overall_recommendation=recommendation,
            summary=summary,
            journal=panel_review.journal,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _recommend(overall_mean: float, n_dissents: int) -> str:
        """Determine recommendation from the overall mean score and dissent count."""
        if overall_mean >= 7.5:
            return "Accept"
        elif overall_mean >= 6.0:
            return "Minor Revision"
        elif overall_mean >= 4.5:
            return (
                "Major Revision"
                if n_dissents == 0
                else "Major Revision (dissents must be resolved)"
            )
        else:
            return "Reject"

    @staticmethod
    def _build_summary(
        consensus: list[ConsensusItem],
        dissents: list[DissentItem],
        mean_scores: dict[str, float],
        recommendation: str,
        journal: str,
    ) -> str:
        """Build the meta-review summary text."""
        lines = [
            f"[Meta-Review — {journal.upper()}]",
            f"Final Recommendation: {recommendation}",
            "",
            "■ Panel Mean Scores:",
        ]
        for dim, score in sorted(mean_scores.items()):
            lines.append(f"  {dim}: {score:.1f}/10")

        if consensus:
            lines.append("\n■ Consensus Points:")
            for c in consensus[:3]:
                lines.append(f"  [{c.dimension.value}] {c.common_rationale[:80]}")

        if dissents:
            lines.append("\n■ Dissent Items:")
            for d in dissents:
                score_str = ", ".join(f"{n}: {s:.0f}" for n, s in d.scores)
                lines.append(f"  [{d.dimension.value}] spread {d.range_:.1f} pts ({score_str})")

        return "\n".join(lines)
