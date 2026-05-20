"""tests/unit/test_reviewer_rubrics.py — Rubric unit tests."""

from __future__ import annotations

import json

from maglab.reviewer.rubrics import (
    CalibrationRecord,
    DimensionScore,
    ReviewScore,
    Rubric,
    ScoreDimension,
    calibrate,
    get_rubric,
    list_journals,
    register_rubric,
)


class TestGetRubric:
    """Rubric registry lookup tests."""

    def test_general_rubric(self):
        rubric = get_rubric("general")
        assert rubric.journal == "general"
        assert len(rubric.dimensions) >= 5

    def test_prl_rubric(self):
        rubric = get_rubric("prl")
        assert rubric.journal == "prl"
        assert rubric.novelty_threshold >= 7.0
        assert rubric.significance_threshold >= 7.0
        assert rubric.max_pages == 4

    def test_prb_rubric(self):
        rubric = get_rubric("prb")
        assert rubric.journal == "prb"

    def test_nature_family_rubric(self):
        rubric = get_rubric("nature_family")
        assert rubric.novelty_threshold >= 9.0

    def test_unknown_journal_returns_general(self):
        rubric = get_rubric("unknown_xyz")
        assert rubric.journal == "general"

    def test_list_journals_contains_required(self):
        journals = list_journals()
        for j in ["general", "prl", "prb", "prx", "npj", "nature_family"]:
            assert j in journals

    def test_register_custom_rubric(self):
        custom = Rubric(journal="custom_test", journal_display_name="Custom Test")
        register_rubric(custom)
        assert get_rubric("custom_test").journal == "custom_test"


class TestReviewScore:
    """ReviewScore validation tests."""

    def _make_score(
        self, dim: ScoreDimension, score_val: float, evidence: list[str]
    ) -> DimensionScore:
        return DimensionScore(
            dimension=dim,
            score=score_val,
            rationale="test rationale",
            evidence_sections=evidence,
        )

    def test_valid_score_passes_validation(self):
        rubric = get_rubric("general")
        review_score = ReviewScore(
            scores=[
                self._make_score(ScoreDimension.NOVELTY, 7.0, ["Introduction"]),
                self._make_score(ScoreDimension.SOUNDNESS, 8.0, ["Methods"]),
                self._make_score(ScoreDimension.SIGNIFICANCE, 6.0, ["Discussion"]),
                self._make_score(ScoreDimension.CLARITY, 7.0, ["Abstract"]),
                self._make_score(ScoreDimension.OVERALL, 7.0, ["Conclusion"]),
            ]
        )
        errors = review_score.validate(rubric)
        assert errors == []

    def test_missing_evidence_section_fails(self):
        """A score without an evidence section fails validation."""
        rubric = get_rubric("general")
        review_score = ReviewScore(
            scores=[
                self._make_score(ScoreDimension.NOVELTY, 7.0, []),  # No evidence
            ]
        )
        errors = review_score.validate(rubric)
        assert any("evidence" in e.lower() for e in errors)

    def test_score_out_of_range_fails(self):
        """A score outside the valid range fails validation."""
        rubric = get_rubric("general")
        review_score = ReviewScore(
            scores=[
                self._make_score(ScoreDimension.NOVELTY, 15.0, ["§1"]),  # Exceeds 10
            ]
        )
        errors = review_score.validate(rubric)
        assert any("range" in e.lower() or "outside" in e.lower() for e in errors)

    def test_to_json_serializable(self):
        review_score = ReviewScore(
            scores=[
                self._make_score(ScoreDimension.NOVELTY, 7.0, ["§1"]),
            ],
            journal="prl",
        )
        json_str = review_score.to_json()
        data = json.loads(json_str)
        assert "scores" in data
        assert data["journal"] == "prl"


class TestCalibration:
    """Calibration mode tests."""

    def _make_review_score(self, novelty: float, significance: float) -> ReviewScore:
        return ReviewScore(
            scores=[
                DimensionScore(ScoreDimension.NOVELTY, novelty, "n", ["§1"]),
                DimensionScore(ScoreDimension.SIGNIFICANCE, significance, "s", ["§1"]),
                DimensionScore(ScoreDimension.SOUNDNESS, 7.0, "so", ["§2"]),
                DimensionScore(ScoreDimension.CLARITY, 7.0, "c", ["§3"]),
                DimensionScore(ScoreDimension.OVERALL, 7.0, "o", ["§4"]),
            ]
        )

    def test_calibration_precision_recall(self):
        rubric = get_rubric("general")  # threshold: novelty≥5, significance≥5
        records = [
            CalibrationRecord("doi:1", actual_accepted=True, score=self._make_review_score(8, 8)),
            CalibrationRecord("doi:2", actual_accepted=False, score=self._make_review_score(3, 3)),
            CalibrationRecord("doi:3", actual_accepted=True, score=self._make_review_score(7, 7)),
            CalibrationRecord("doi:4", actual_accepted=False, score=self._make_review_score(6, 6)),
        ]
        result = calibrate(records, rubric)
        assert result.n_total == 4
        assert 0.0 <= result.precision <= 1.0
        assert 0.0 <= result.recall <= 1.0
        assert 0.0 <= result.false_positive_rate <= 1.0
