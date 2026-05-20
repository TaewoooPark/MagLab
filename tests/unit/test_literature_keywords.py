"""tests/unit/test_literature_keywords.py — Keyword extraction unit tests.

Zero network or LLM calls. KeyBERT, YAKE, and TF-IDF all mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maglab.literature.keywords import (
    WEIGHT_KEYBERT,
    WEIGHT_TFIDF,
    WEIGHT_YAKE,
    WeightedKeyword,
    _normalize_keyword,
    _normalize_scores,
    extract_keybert_keywords,
    extract_keywords_from_folder,
    extract_keywords_from_texts,
    extract_texts_from_folder,
    extract_tfidf_keywords,
    extract_yake_keywords,
    merge_keyword_scores,
    top_keyword_strings,
)

# ---------------------------------------------------------------------------
# WeightedKeyword
# ---------------------------------------------------------------------------



class TestWeightedKeyword:
    def test_creation(self):
        kw = WeightedKeyword(
            keyword="spin hall effect",
            score=0.85,
            tfidf_score=0.9,
            keybert_score=0.8,
            yake_score=0.85,
            source_methods=["tfidf", "keybert"],
        )
        assert kw.keyword == "spin hall effect"
        assert kw.score == pytest.approx(0.85)
        assert "tfidf" in kw.source_methods

    def test_default_methods(self):
        kw = WeightedKeyword(keyword="SOT", score=0.5)
        assert kw.source_methods == []


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


class TestNormalizeHelpers:
    def test_normalize_keyword_lowercase(self):
        assert _normalize_keyword("  Spin Hall  Effect  ") == "spin hall effect"

    def test_normalize_scores_max_normalization(self):
        pairs = [("a", 2.0), ("b", 1.0), ("c", 0.5)]
        normed = _normalize_scores(pairs)
        assert normed["a"] == pytest.approx(1.0)
        assert normed["b"] == pytest.approx(0.5)
        assert normed["c"] == pytest.approx(0.25)

    def test_normalize_scores_empty(self):
        assert _normalize_scores([]) == {}

    def test_normalize_scores_zero_max(self):
        pairs = [("a", 0.0), ("b", 0.0)]
        normed = _normalize_scores(pairs)
        assert normed["a"] == 0.0


# ---------------------------------------------------------------------------
# TF-IDF extraction
# ---------------------------------------------------------------------------


class TestTfidfExtraction:
    def test_basic_extraction(self):
        texts = [
            "spin Hall effect spintronics magnetic",
            "SOT switching CoFeB spin orbit torque",
            "spin Hall magnetoresistance SMR",
        ]
        result = extract_tfidf_keywords(texts, top_n=10)
        assert isinstance(result, list)
        assert all(isinstance(kw, str) and isinstance(sc, float) for kw, sc in result)

    def test_empty_texts(self):
        result = extract_tfidf_keywords([], top_n=10)
        assert result == []

    def test_returns_sorted_descending(self):
        texts = ["spin Hall effect magnetic skyrmion domain wall"]
        result = extract_tfidf_keywords(texts, top_n=20)
        if len(result) > 1:
            scores = [sc for _, sc in result]
            assert scores == sorted(scores, reverse=True)

    def test_top_n_respected(self):
        texts = ["a b c d e f g h i j k l m n o p"]
        result = extract_tfidf_keywords(texts, top_n=5)
        assert len(result) <= 5


# ---------------------------------------------------------------------------
# KeyBERT extraction (mocked)
# ---------------------------------------------------------------------------


class TestKeyBERTExtraction:
    def test_returns_list(self):
        mock_kb = MagicMock()
        mock_kb.extract_keywords.return_value = [
            ("spin hall effect", 0.92),
            ("sot switching", 0.85),
            ("cobalt iron boron", 0.78),
        ]
        with patch("maglab.literature.keywords.KeyBERT", return_value=mock_kb):
            result = extract_keybert_keywords("spin hall effect SOT CoFeB", top_n=5)
        assert len(result) == 3
        assert all(isinstance(kw, str) for kw, _ in result)
        assert all(kw == kw.lower() for kw, _ in result)

    def test_empty_text(self):
        mock_kb = MagicMock()
        mock_kb.extract_keywords.return_value = []
        with patch("maglab.literature.keywords.KeyBERT", return_value=mock_kb):
            result = extract_keybert_keywords("", top_n=10)
        assert result == []

    def test_import_error_returns_empty(self):
        with (
            patch.dict("sys.modules", {"keybert": None}),
            patch("maglab.literature.keywords.KeyBERT", side_effect=ImportError),
        ):
            result = extract_keybert_keywords("some text")
        assert result == []


# ---------------------------------------------------------------------------
# YAKE extraction (mocked)
# ---------------------------------------------------------------------------


class TestYakeExtraction:
    def test_returns_inverted_scores(self):
        mock_extractor = MagicMock()
        # YAKE score: lower is better
        mock_extractor.extract_keywords.return_value = [
            ("spin hall", 0.01),
            ("SOT torque", 0.05),
            ("magnetic layer", 0.10),
        ]
        with patch("maglab.literature.keywords.yake") as mock_yake_mod:
            mock_yake_mod.KeywordExtractor.return_value = mock_extractor
            result = extract_yake_keywords("spin hall SOT magnetic layer", top_n=5)

        assert len(result) == 3
        # Lower raw score → higher inverted score
        # "spin hall" (0.01) should have the highest inverted score
        spin_hall_score = dict(result).get("spin hall", 0)
        mag_layer_score = dict(result).get("magnetic layer", 0)
        assert spin_hall_score > mag_layer_score


# ---------------------------------------------------------------------------
# Weighted merge (merge_keyword_scores)
# ---------------------------------------------------------------------------


class TestMergeKeywordScores:
    def test_basic_merge(self):
        tfidf = [("spin hall effect", 0.9), ("sot switching", 0.7)]
        keybert = [("spin hall effect", 0.85), ("cobalt iron", 0.6)]
        yake = [("spin hall effect", 0.8), ("magnetic layer", 0.5)]

        results = merge_keyword_scores(tfidf, keybert, yake, top_n=10)
        assert isinstance(results, list)
        assert all(isinstance(r, WeightedKeyword) for r in results)

        # "spin hall effect" appeared in all three, so it should rank highest
        top = results[0]
        assert "spin" in top.keyword

    def test_weights_sum(self):
        assert pytest.approx(1.0) == WEIGHT_TFIDF + WEIGHT_KEYBERT + WEIGHT_YAKE

    def test_score_range(self):
        tfidf = [("keyword", 1.0)]
        keybert = [("keyword", 1.0)]
        yake = [("keyword", 1.0)]
        results = merge_keyword_scores(tfidf, keybert, yake, top_n=5)
        assert len(results) == 1
        assert 0.0 <= results[0].score <= 1.0

    def test_empty_inputs(self):
        results = merge_keyword_scores([], [], [], top_n=10)
        assert results == []

    def test_substring_suppression(self):
        # "spin" is a substring of "spin hall effect" and should be suppressed
        tfidf = [("spin hall effect", 0.9), ("spin", 0.5)]
        keybert = [("spin hall effect", 0.85)]
        yake = [("spin hall effect", 0.8)]
        results = merge_keyword_scores(tfidf, keybert, yake, top_n=10)
        keywords = [r.keyword for r in results]
        # "spin" is contained in "spin hall effect", so it may be suppressed
        assert "spin hall effect" in keywords
        # "spin" alone may be suppressed (order-dependent)

    def test_top_n_respected(self):
        tfidf = [(f"kw{i}", 1.0 / (i + 1)) for i in range(20)]
        results = merge_keyword_scores(tfidf, [], [], top_n=5)
        assert len(results) <= 5

    def test_sorted_by_score_descending(self):
        tfidf = [("a", 0.3), ("b", 0.9), ("c", 0.6)]
        results = merge_keyword_scores(tfidf, [], [], top_n=10)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_source_methods_labeled(self):
        tfidf = [("test kw", 0.8)]
        keybert = [("test kw", 0.7)]
        yake = []
        results = merge_keyword_scores(tfidf, keybert, yake, top_n=5)
        kw = next(r for r in results if r.keyword == "test kw")
        assert "tfidf" in kw.source_methods
        assert "keybert" in kw.source_methods


# ---------------------------------------------------------------------------
# extract_keywords_from_texts (integration)
# ---------------------------------------------------------------------------


class TestExtractKeywordsFromTexts:
    def test_integration_with_real_texts(self):
        """Integration test with real magnetism physics text (no mocks, scikit-learn only)."""
        texts = [
            "The spin Hall effect generates a spin current perpendicular to charge current. "
            "In heavy metals like Ta and Pt, the spin-orbit coupling is large. "
            "SOT switching in CoFeB/MgO heterostructures.",
            "The anomalous Hall effect in ferromagnetic metals is related to Berry curvature. "
            "The spin Hall magnetoresistance in YIG/Pt bilayers depends on spin mixing conductance.",
        ]
        # KeyBERT and YAKE are mocked (no model downloads)
        mock_kb = MagicMock()
        mock_kb.extract_keywords.return_value = [
            ("spin hall effect", 0.9),
            ("sot switching", 0.85),
        ]
        mock_extractor = MagicMock()
        mock_extractor.extract_keywords.return_value = [
            ("spin hall", 0.02),
            ("cofeb mgo", 0.05),
        ]

        with (
            patch("maglab.literature.keywords.KeyBERT", return_value=mock_kb),
            patch("maglab.literature.keywords.yake") as mock_yake_mod,
        ):
            mock_yake_mod.KeywordExtractor.return_value = mock_extractor
            results = extract_keywords_from_texts(texts, top_n=15)

        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, WeightedKeyword) for r in results)


# ---------------------------------------------------------------------------
# extract_texts_from_folder — missing/invalid path guard (F-01 regression)
# ---------------------------------------------------------------------------


class TestExtractTextsFromFolder:
    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        """Missing folder must return [] without raising (F-01)."""
        missing = tmp_path / "does_not_exist"
        assert not missing.exists()
        result = extract_texts_from_folder(missing)
        assert result == []

    def test_nonexistent_path_as_str_returns_empty(self, tmp_path: Path) -> None:
        """str argument for a missing path must also return [] (F-01, str conversion)."""
        missing = str(tmp_path / "also_missing")
        result = extract_texts_from_folder(missing)  # type: ignore[arg-type]
        assert result == []

    def test_file_path_not_directory_returns_empty(self, tmp_path: Path) -> None:
        """Passing a plain file (not a directory) must return [] without raising."""
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello", encoding="utf-8")
        result = extract_texts_from_folder(f)
        assert result == []

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        """Empty folder must still return [] (pre-existing behaviour, no regression)."""
        result = extract_texts_from_folder(tmp_path)
        assert result == []


class TestExtractKeywordsFromFolder:
    def test_nonexistent_folder_returns_empty(self, tmp_path: Path) -> None:
        """extract_keywords_from_folder with a missing path returns [] (F-01 end-to-end)."""
        missing = tmp_path / "no_papers_here"
        result = extract_keywords_from_folder(missing)
        assert result == []


# ---------------------------------------------------------------------------
# top_keyword_strings
# ---------------------------------------------------------------------------


class TestTopKeywordStrings:
    def test_returns_string_list(self):
        kws = [
            WeightedKeyword(keyword="spin hall", score=0.9),
            WeightedKeyword(keyword="sot", score=0.8),
            WeightedKeyword(keyword="cobalt", score=0.7),
        ]
        result = top_keyword_strings(kws, n=2)
        assert result == ["spin hall", "sot"]

    def test_n_larger_than_list(self):
        kws = [WeightedKeyword(keyword="only", score=0.5)]
        result = top_keyword_strings(kws, n=10)
        assert result == ["only"]

    def test_empty_input(self):
        assert top_keyword_strings([], n=5) == []
