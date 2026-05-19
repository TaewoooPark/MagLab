"""Review rubrics — general rubric and journal-specific rubrics (§15.3·§15.4).

General rubric: novelty·soundness·significance·clarity·overall (0–10 each, evidence section required).
Journal-specific rubrics: PRL·PRB·PRX·npj·APL Materials·Nature family.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Rubric criterion data structures
# ---------------------------------------------------------------------------


class ScoreDimension(StrEnum):
    """Scoring dimensions."""

    NOVELTY = "novelty"
    """Novelty — is this a new finding or method?"""
    SOUNDNESS = "soundness"
    """Soundness — are the methodology, data, and logic valid?"""
    SIGNIFICANCE = "significance"
    """Significance — field impact."""
    CLARITY = "clarity"
    """Clarity — clarity of writing, structure, and figures."""
    OVERALL = "overall"
    """Overall score."""


@dataclass(frozen=True)
class DimensionSpec:
    """Single scoring dimension specification.

    Attributes
    ----------
    dimension:
        Score dimension.
    min_score:
        Minimum score (default 0).
    max_score:
        Maximum score (default 10).
    description:
        Dimension description.
    require_evidence_section:
        If True, an evidence section (paper section/paragraph reference) is required.
    """

    dimension: ScoreDimension
    min_score: float = 0.0
    max_score: float = 10.0
    description: str = ""
    require_evidence_section: bool = True


@dataclass
class DimensionScore:
    """Single dimension score result.

    Attributes
    ----------
    dimension:
        Score dimension.
    score:
        Assigned score.
    rationale:
        Rationale for the score.
    evidence_sections:
        Evidence section reference list (e.g. ["Methods §2", "Fig.3"]).
    """

    dimension: ScoreDimension
    score: float
    rationale: str
    evidence_sections: list[str] = field(default_factory=list)

    def validate(self, spec: DimensionSpec) -> list[str]:
        """Check score range and evidence section requirements; return violation messages."""
        errors = []
        if not (spec.min_score <= self.score <= spec.max_score):
            errors.append(
                f"{self.dimension}: score {self.score} is outside the range "
                f"[{spec.min_score}, {spec.max_score}]."
            )
        if spec.require_evidence_section and not self.evidence_sections:
            errors.append(
                f"{self.dimension}: evidence section is empty. "
                "A paper section or paragraph must be specified to support the score."
            )
        return errors


@dataclass
class ReviewScore:
    """Full review score set.

    Attributes
    ----------
    scores:
        DimensionScore list by dimension.
    journal:
        Target journal identifier (empty string uses the general rubric).
    reviewer_persona:
        Reviewer persona name.
    summary_recommendation:
        Final recommendation (Accept / Reject / Major Revision / Minor Revision).
    notes:
        Additional notes.
    """

    scores: list[DimensionScore] = field(default_factory=list)
    journal: str = ""
    reviewer_persona: str = ""
    summary_recommendation: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to structured JSON."""
        return {
            "journal": self.journal,
            "reviewer_persona": self.reviewer_persona,
            "summary_recommendation": self.summary_recommendation,
            "scores": [
                {
                    "dimension": s.dimension.value,
                    "score": s.score,
                    "rationale": s.rationale,
                    "evidence_sections": s.evidence_sections,
                }
                for s in self.scores
            ],
            "notes": self.notes,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def validate(self, rubric: Rubric) -> list[str]:
        """Validate scores against the rubric specification; return violation messages."""
        errors = []
        spec_map = {s.dimension: s for s in rubric.dimensions}
        score_dim_set = {s.dimension for s in self.scores}

        # Check for missing required dimensions
        for dim, _spec in spec_map.items():
            if dim not in score_dim_set:
                errors.append(f"Required dimension '{dim}' score is missing.")

        # Validate each score
        for ds in self.scores:
            spec = spec_map.get(ds.dimension)
            if spec is None:
                continue
            errors.extend(ds.validate(spec))

        return errors


# ---------------------------------------------------------------------------
# Rubric definitions
# ---------------------------------------------------------------------------


@dataclass
class RejectionCriteria:
    """Typical rejection reason list."""

    criteria: list[str] = field(default_factory=list)
    """List of rejection criterion strings."""


@dataclass
class Rubric:
    """Single rubric (general or journal-specific).

    Attributes
    ----------
    journal:
        Journal identifier (default 'general').
    journal_display_name:
        Official journal name.
    dimensions:
        Scoring dimension specification list.
    novelty_threshold:
        Minimum novelty score to pass.
    significance_threshold:
        Minimum significance score to pass.
    max_pages:
        Maximum paper length (None = no limit).
    focus:
        Journal focus description.
    rejection_criteria:
        Typical rejection reasons.
    notes:
        Additional notes.
    """

    journal: str = "general"
    journal_display_name: str = "General Rubric"
    dimensions: list[DimensionSpec] = field(default_factory=list)
    novelty_threshold: float = 5.0
    significance_threshold: float = 5.0
    max_pages: int | None = None
    focus: str = ""
    rejection_criteria: RejectionCriteria = field(default_factory=RejectionCriteria)
    notes: str = ""

    def is_accepted(self, score: ReviewScore) -> bool:
        """Check whether the score meets this rubric's minimum criteria (for calibration mode)."""
        score_map = {s.dimension: s.score for s in score.scores}
        novelty = score_map.get(ScoreDimension.NOVELTY, 0.0)
        significance = score_map.get(ScoreDimension.SIGNIFICANCE, 0.0)
        return novelty >= self.novelty_threshold and significance >= self.significance_threshold


# ---------------------------------------------------------------------------
# Rubric definition factories
# ---------------------------------------------------------------------------

_BASE_DIMENSIONS = [
    DimensionSpec(
        dimension=ScoreDimension.NOVELTY,
        description="Is this a new finding, method, or theory — does it clearly advance prior work?",
        require_evidence_section=True,
    ),
    DimensionSpec(
        dimension=ScoreDimension.SOUNDNESS,
        description="Are the methodology, experimental design, statistics, and data quality valid?",
        require_evidence_section=True,
    ),
    DimensionSpec(
        dimension=ScoreDimension.SIGNIFICANCE,
        description="Impact and importance on the field or broader science.",
        require_evidence_section=True,
    ),
    DimensionSpec(
        dimension=ScoreDimension.CLARITY,
        description="Are the writing, structure, figures, and equations clear and reproducible?",
        require_evidence_section=True,
    ),
    DimensionSpec(
        dimension=ScoreDimension.OVERALL,
        description="Overall composite score.",
        require_evidence_section=True,
    ),
]


def _make_general_rubric() -> Rubric:
    """General rubric (journal-agnostic)."""
    return Rubric(
        journal="general",
        journal_display_name="General Physics/Magnetism Journal",
        dimensions=list(_BASE_DIMENSIONS),
        novelty_threshold=5.0,
        significance_threshold=5.0,
        focus="Balanced novelty·soundness·significance·clarity.",
        rejection_criteria=RejectionCriteria(
            criteria=[
                "No novelty — replicates prior work",
                "Methodological deficiency — insufficient statistics or error analysis",
                "Insufficient data — too weak to support conclusions",
                "Not reproducible — incomplete methods description",
            ]
        ),
    )


def _make_prl_rubric() -> Rubric:
    """Physical Review Letters rubric.

    PRL emphasizes broad interest and immediacy, limited to 4 pages + SI.
    Novelty and significance thresholds are higher than the general rubric.
    """
    return Rubric(
        journal="prl",
        journal_display_name="Physical Review Letters",
        dimensions=list(_BASE_DIMENSIONS),
        novelty_threshold=7.0,
        significance_threshold=7.0,
        max_pages=4,
        focus=(
            "Findings of immediate interest to the broad physics community. "
            "A single, clear message. 4 pages + Supplemental Material."
        ),
        rejection_criteria=RejectionCriteria(
            criteria=[
                "Results of interest only to a narrow subfield — does not meet PRL broad-interest criterion",
                "Insufficient immediacy — not timely or only incremental progress",
                "Unclear message — does not present a single central finding",
                "Core result exceeds 4 pages — key point unclear even after moving to SI",
                "Claims without sufficient experimental or theoretical support",
            ]
        ),
        notes="4-page main text (two-column APS format) + SI. Novelty and breadth are key criteria.",
    )


def _make_prb_rubric() -> Rubric:
    """Physical Review B rubric.

    PRB is a comprehensive journal for condensed matter, magnetism, and spintronics.
    Emphasizes technical completeness and soundness.
    """
    return Rubric(
        journal="prb",
        journal_display_name="Physical Review B",
        dimensions=list(_BASE_DIMENSIONS),
        novelty_threshold=5.0,
        significance_threshold=4.0,
        focus=(
            "Technically sound research across condensed matter physics. "
            "Covers magnetism, spintronics, topology, superconductivity, etc. "
            "Incremental progress recognized with sufficient technical contribution."
        ),
        rejection_criteria=RejectionCriteria(
            criteria=[
                "Methodological deficiency — fitting quality not reported (χ²·R², etc.)",
                "Insufficient prior literature citation",
                "No physical interpretation — numerical results without physical meaning",
                "Insufficient reproducibility — sample and conditions not specified",
            ]
        ),
    )


def _make_prx_rubric() -> Rubric:
    """Physical Review X rubric.

    PRX emphasizes multidisciplinary impact and conceptual advance.
    """
    return Rubric(
        journal="prx",
        journal_display_name="Physical Review X",
        dimensions=list(_BASE_DIMENSIONS),
        novelty_threshold=8.0,
        significance_threshold=8.0,
        focus=("Broad impact within and beyond physics. Conceptually new frameworks. Experimental, theoretical, and computational disciplines."),
        rejection_criteria=RejectionCriteria(
            criteria=[
                "No conceptual novelty — only a technical improvement",
                "Cross-disciplinary impact not demonstrated",
                "Content sparse relative to paper length",
            ]
        ),
    )


def _make_npj_rubric() -> Rubric:
    """npj Computational Materials rubric."""
    return Rubric(
        journal="npj",
        journal_display_name="npj Computational Materials",
        dimensions=list(_BASE_DIMENSIONS),
        novelty_threshold=6.5,
        significance_threshold=6.5,
        focus=(
            "Computation/theory-centric but experimental validation preferred. "
            "Suitable for magnetism, spintronics, and topological materials. "
            "Open access Nature family journal."
        ),
        rejection_criteria=RejectionCriteria(
            criteria=[
                "Pure prediction without experimental validation (recommended: experimental comparison required)",
                "Insufficient computational methodology transparency",
                "Field impact not demonstrated",
            ]
        ),
    )


def _make_nature_family_rubric() -> Rubric:
    """Common rubric for Nature family journals (Nature, Nature Physics, Nature Materials, etc.)."""
    return Rubric(
        journal="nature_family",
        journal_display_name="Nature Family",
        dimensions=list(_BASE_DIMENSIONS),
        novelty_threshold=9.0,
        significance_threshold=9.0,
        max_pages=6,
        focus=(
            "Discoveries that transform all of science. Immediate broad interest. "
            "Nature: all natural sciences. Nature Physics: all of physics. "
            "Nature Materials: materials science. Rejection rate >90%."
        ),
        rejection_criteria=RejectionCriteria(
            criteria=[
                "Does not meet broad natural-science interest — field-specific journal recommended",
                "No conceptual breakthrough — incremental progress better suited for PRB/PRX",
                "Incomplete data — not all experiments supporting conclusions included",
                "Insufficient reproducibility — inadequate n and statistics",
                "Unclear writing — inaccessible to non-specialists",
            ]
        ),
        notes="Letter format (6-page main text). SI unlimited. Review process 2–4 months.",
    )


def _make_apl_materials_rubric() -> Rubric:
    """APL Materials rubric (§15.4).

    APL Materials targets applied and computational materials science
    with a short letter format.  Strong experimental validation is required;
    pure theory/simulation without experimental comparison is discouraged.
    """
    return Rubric(
        journal="apl_materials",
        journal_display_name="APL Materials",
        dimensions=list(_BASE_DIMENSIONS),
        novelty_threshold=6.0,
        significance_threshold=6.0,
        max_pages=8,
        focus=(
            "Applied and computational materials research — thin films, interfaces, "
            "and functional materials. Short letter format. Strong experimental "
            "validation required; pure prediction without experimental comparison "
            "is discouraged. Covers magnetism, spintronics, and spintronic devices."
        ),
        rejection_criteria=RejectionCriteria(
            criteria=[
                "No experimental validation — pure theoretical or computational work without experimental comparison",
                "Insufficient device or application relevance",
                "Weak reproducibility — sample fabrication and measurement conditions underspecified",
                "Main text exceeds 8 pages — concise letter format expected",
                "Claims not supported by sufficient materials characterization",
            ]
        ),
        notes=(
            "Letter format (≤8 pages main text). Open access (AIP/ACS). "
            "Emphasis on materials relevance and practical impact. "
            "Peer review ~6–8 weeks."
        ),
    )


# ---------------------------------------------------------------------------
# Rubric registry
# ---------------------------------------------------------------------------


_RUBRIC_REGISTRY: dict[str, Rubric] = {
    "general": _make_general_rubric(),
    "prl": _make_prl_rubric(),
    "prb": _make_prb_rubric(),
    "prx": _make_prx_rubric(),
    "npj": _make_npj_rubric(),
    "nature_family": _make_nature_family_rubric(),
    "apl_materials": _make_apl_materials_rubric(),
}


def get_rubric(journal: str) -> Rubric:
    """Retrieve a rubric by journal identifier.

    Parameters
    ----------
    journal:
        Journal identifier (e.g. 'prl', 'prb', 'general').
        Returns the general rubric for unregistered identifiers.

    Returns
    -------
    Rubric
    """
    return _RUBRIC_REGISTRY.get(journal.lower(), _RUBRIC_REGISTRY["general"])


def list_journals() -> list[str]:
    """Return the list of registered journal identifiers."""
    return sorted(_RUBRIC_REGISTRY.keys())


def register_rubric(rubric: Rubric) -> None:
    """Register a custom rubric in the registry."""
    _RUBRIC_REGISTRY[rubric.journal.lower()] = rubric


# ---------------------------------------------------------------------------
# Calibration mode — measure false-negative/false-positive rate against known accept/reject set
# ---------------------------------------------------------------------------


@dataclass
class CalibrationRecord:
    """Calibration case record.

    Attributes
    ----------
    paper_id:
        Paper identifier (DOI, etc.).
    actual_accepted:
        Whether the paper was actually accepted (True) or rejected (False).
    score:
        ReviewScore assigned by the panel.
    """

    paper_id: str
    actual_accepted: bool
    score: ReviewScore


@dataclass
class CalibrationResult:
    """Calibration mode run result.

    Attributes
    ----------
    precision:
        Precision (fraction of predicted accepts that are actually accepted).
    recall:
        Recall (fraction of actual accepts that are predicted as accepted).
    false_positive_rate:
        False positive rate (fraction of actual rejects predicted as accepted).
    false_negative_rate:
        False negative rate (fraction of actual accepts predicted as rejected).
    n_total:
        Total number of cases.
    notes:
        Additional notes.
    """

    precision: float
    recall: float
    false_positive_rate: float
    false_negative_rate: float
    n_total: int
    notes: str = ""


def calibrate(
    records: list[CalibrationRecord],
    rubric: Rubric,
) -> CalibrationResult:
    """Measure panel false-negative/false-positive rate against a calibration case set.

    Parameters
    ----------
    records:
        Calibration case record list.
    rubric:
        Rubric used for evaluation.

    Returns
    -------
    CalibrationResult
    """
    tp = fp = tn = fn = 0

    for rec in records:
        predicted_accepted = rubric.is_accepted(rec.score)
        actual = rec.actual_accepted
        if predicted_accepted and actual:
            tp += 1
        elif predicted_accepted and not actual:
            fp += 1
        elif not predicted_accepted and actual:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    return CalibrationResult(
        precision=precision,
        recall=recall,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        n_total=len(records),
        notes=f"Rubric: {rubric.journal_display_name}",
    )
