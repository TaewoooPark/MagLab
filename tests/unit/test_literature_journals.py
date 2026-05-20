"""tests/unit/test_literature_journals.py — Journal metrics unit tests (§14.4).

Includes validation that 'JCR Impact Factor' labels are forbidden.
Zero network calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from maglab.literature.journals import (
    _FORBIDDEN_LABELS,
    JournalMetrics,
    _match_journal_name,
    get_journal_metrics,
    list_top_journals_by_sjr,
)

# ---------------------------------------------------------------------------
# JournalMetrics
# ---------------------------------------------------------------------------


class TestJournalMetrics:
    def test_basic_creation(self):
        m = JournalMetrics(
            journal_name="Physical Review Letters",
            sjr=3.5,
            sjr_quartile="Q1",
            sjr_year=2023,
            openalex_2yr_mean_citedness=8.2,
            eigenfactor=0.05,
        )
        assert m.journal_name == "Physical Review Letters"
        assert m.sjr == pytest.approx(3.5)
        assert m.sjr_quartile == "Q1"

    def test_sources_correctly_labeled(self):
        m = JournalMetrics(journal_name="Test Journal")
        assert "SJR" in m.sjr_source
        assert "JCR" not in m.sjr_source
        assert "Impact Factor" not in m.sjr_source
        assert "OpenAlex" in m.openalex_source
        assert "Eigenfactor" in m.eigenfactor_source

    def test_validate_no_jcr_label_passes(self):
        m = JournalMetrics(
            journal_name="PRL",
            sjr_source="SJR (SCImago)",
            openalex_source="OpenAlex 2yr_mean_citedness",
            eigenfactor_source="Eigenfactor",
        )
        m.validate_no_jcr_label()  # Should raise no error

    def test_validate_no_jcr_label_fails_on_jcr(self):
        m = JournalMetrics(
            journal_name="PRL",
            sjr_source="JCR Impact Factor",
        )
        with pytest.raises(ValueError, match="Forbidden"):
            m.validate_no_jcr_label()

    def test_validate_no_jcr_label_fails_on_if(self):
        m = JournalMetrics(
            journal_name="PRL",
            openalex_source="Impact Factor",
        )
        with pytest.raises(ValueError, match="Forbidden"):
            m.validate_no_jcr_label()

    def test_as_display_no_forbidden_keys(self):
        m = JournalMetrics(
            journal_name="npj Spintronics",
            sjr=2.0,
            openalex_2yr_mean_citedness=5.5,
            eigenfactor=0.01,
        )
        display = m.as_display()
        for key in display:
            for forbidden in _FORBIDDEN_LABELS:
                assert forbidden.lower() not in key.lower(), (
                    f"Forbidden label '{forbidden}' found: key='{key}'"
                )

    def test_as_display_contains_three_metrics(self):
        m = JournalMetrics(
            journal_name="Test",
            sjr=1.0,
            openalex_2yr_mean_citedness=3.0,
            eigenfactor=0.005,
        )
        d = m.as_display()
        # SJR, OpenAlex, and Eigenfactor all present
        keys_str = " ".join(d.keys())
        assert "SJR" in keys_str
        assert "OpenAlex" in keys_str
        assert "Eigenfactor" in keys_str

    def test_as_display_raises_on_forbidden_sjr_source(self):
        m = JournalMetrics(
            journal_name="Bad",
            sjr_source="JCR IF",
        )
        with pytest.raises(ValueError):
            m.as_display()


# ---------------------------------------------------------------------------
# Forbidden label set
# ---------------------------------------------------------------------------


class TestForbiddenLabels:
    def test_contains_jcr_if(self):
        assert "JCR Impact Factor" in _FORBIDDEN_LABELS
        assert "JCR IF" in _FORBIDDEN_LABELS
        assert "Impact Factor" in _FORBIDDEN_LABELS

    def test_does_not_contain_sjr(self):
        # SJR is an allowed label
        assert "SJR" not in _FORBIDDEN_LABELS
        assert "SJR (SCImago)" not in _FORBIDDEN_LABELS


# ---------------------------------------------------------------------------
# Matching helper
# ---------------------------------------------------------------------------


class TestMatchJournalName:
    def test_exact_match(self):
        lookup = {"physical review letters": {"sjr": 3.5}}
        result = _match_journal_name("Physical Review Letters", lookup)
        assert result == "physical review letters"

    def test_partial_match(self):
        lookup = {"physical review letters": {"sjr": 3.5}}
        result = _match_journal_name("Review Letters", lookup)
        assert result is not None

    def test_no_match(self):
        lookup = {"nature": {"sjr": 10.0}}
        result = _match_journal_name("nonexistent journal xyz", lookup)
        assert result is None


# ---------------------------------------------------------------------------
# get_journal_metrics (mocked OpenAlex)
# ---------------------------------------------------------------------------


class TestGetJournalMetrics:
    @patch(
        "maglab.literature.journals._load_sjr_csv",
        return_value={
            "physical review letters": {
                "title": "Physical Review Letters",
                "sjr": 3.521,
                "quartile": "Q1",
                "year": 2023,
            }
        },
    )
    @patch(
        "maglab.literature.journals._load_eigenfactor_csv",
        return_value={"physical review letters": 0.052},
    )
    @patch(
        "maglab.literature.journals._fetch_openalex_venue_metrics",
        return_value={
            "id": "S4210176966",
            "display_name": "Physical Review Letters",
            "2yr_mean_citedness": 8.3,
            "h_index": 503,
        },
    )
    def test_prl_metrics(self, mock_oa, mock_ef, mock_sjr):
        m = get_journal_metrics("Physical Review Letters")
        assert m.journal_name == "Physical Review Letters"
        assert m.sjr == pytest.approx(3.521)
        assert m.sjr_quartile == "Q1"
        assert m.eigenfactor == pytest.approx(0.052)
        assert m.openalex_2yr_mean_citedness == pytest.approx(8.3)
        assert m.h_index == 503

    @patch("maglab.literature.journals._load_sjr_csv", return_value={})
    @patch("maglab.literature.journals._load_eigenfactor_csv", return_value={})
    @patch("maglab.literature.journals._fetch_openalex_venue_metrics", return_value={})
    def test_no_data_journal(self, mock_oa, mock_ef, mock_sjr):
        m = get_journal_metrics("Unknown Journal XYZXYZ")
        assert m.sjr is None
        assert m.eigenfactor is None
        assert m.openalex_2yr_mean_citedness is None
        assert len(m.notes) > 0  # Should have warning notes

    @patch("maglab.literature.journals._load_sjr_csv", return_value={})
    @patch("maglab.literature.journals._load_eigenfactor_csv", return_value={})
    @patch("maglab.literature.journals._fetch_openalex_venue_metrics", return_value={})
    def test_result_has_no_jcr_label(self, mock_oa, mock_ef, mock_sjr):
        m = get_journal_metrics("Nature")
        m.validate_no_jcr_label()  # Should raise no error
        assert "JCR" not in m.sjr_source
        assert "Impact Factor" not in m.openalex_source

    @patch(
        "maglab.literature.journals._load_sjr_csv",
        return_value={"nature": {"title": "Nature", "sjr": 15.0, "quartile": "Q1", "year": 2023}},
    )
    @patch("maglab.literature.journals._load_eigenfactor_csv", return_value={})
    @patch(
        "maglab.literature.journals._fetch_openalex_venue_metrics",
        return_value={"2yr_mean_citedness": 50.0, "h_index": 1200, "id": "S137773608"},
    )
    def test_nature_metrics(self, mock_oa, mock_ef, mock_sjr):
        m = get_journal_metrics("Nature")
        assert m.sjr == pytest.approx(15.0)
        assert m.openalex_2yr_mean_citedness == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# list_top_journals_by_sjr
# ---------------------------------------------------------------------------


class TestListTopJournalsBySjr:
    @patch(
        "maglab.literature.journals._load_sjr_csv",
        return_value={
            "nature": {"title": "Nature", "sjr": 15.0, "quartile": "Q1", "year": 2023},
            "physical review letters": {
                "title": "Physical Review Letters",
                "sjr": 3.5,
                "quartile": "Q1",
                "year": 2023,
            },
            "journal of magnetism": {
                "title": "Journal of Magnetism and Magnetic Materials",
                "sjr": 0.9,
                "quartile": "Q2",
                "year": 2023,
            },
        },
    )
    def test_sorted_by_sjr(self, mock_sjr):
        results = list_top_journals_by_sjr(top_n=3)
        assert len(results) == 3
        assert results[0].sjr >= results[1].sjr >= results[2].sjr

    @patch(
        "maglab.literature.journals._load_sjr_csv",
        return_value={
            "nature": {"title": "Nature", "sjr": 15.0, "quartile": "Q1", "year": 2023},
            "journal of magnetism": {
                "title": "Journal of Magnetism",
                "sjr": 0.9,
                "quartile": "Q2",
                "year": 2023,
            },
        },
    )
    def test_field_filter(self, mock_sjr):
        results = list_top_journals_by_sjr(field_query="Magnetism", top_n=5)
        assert len(results) == 1
        assert "Magnetism" in results[0].journal_name

    @patch(
        "maglab.literature.journals._load_sjr_csv",
        return_value={
            "test": {"title": "Test Journal", "sjr": 1.0, "quartile": "Q2", "year": 2023}
        },
    )
    def test_no_jcr_label_in_list_results(self, mock_sjr):
        results = list_top_journals_by_sjr(top_n=5)
        for m in results:
            m.validate_no_jcr_label()
            assert "JCR" not in m.sjr_source


# ---------------------------------------------------------------------------
# FIX 3: Bundled CSV data files (SJR + Eigenfactor + NEMAD)
# ---------------------------------------------------------------------------


class TestBundledCsvFiles:
    """Verify that bundled CSV files exist and parse correctly."""

    def test_sjr_csv_exists(self):
        """maglab/physics/data/sjr.csv must be present."""
        from pathlib import Path

        csv_path = Path(__file__).parent.parent.parent / "maglab" / "physics" / "data" / "sjr.csv"
        assert csv_path.is_file(), f"SJR CSV not found at {csv_path}"

    def test_sjr_csv_loads_prl(self):
        """SJR CSV must contain Physical Review Letters with a valid SJR score."""
        # Reload without cache

        from maglab.literature.journals import _load_sjr_csv

        _load_sjr_csv.cache_clear()
        data = _load_sjr_csv()
        _load_sjr_csv.cache_clear()  # clean up

        key = "physical review letters"
        assert key in data, f"PRL not found in SJR CSV. Keys: {list(data.keys())[:10]}"
        assert data[key]["sjr"] is not None
        assert data[key]["sjr"] > 0
        assert data[key]["quartile"] in ("Q1", "Q2", "Q3", "Q4"), (
            f"Unexpected quartile: {data[key]['quartile']}"
        )

    def test_sjr_csv_has_magnetism_journals(self):
        """SJR CSV must contain at least one magnetism-related journal."""
        from maglab.literature.journals import _load_sjr_csv

        _load_sjr_csv.cache_clear()
        data = _load_sjr_csv()
        _load_sjr_csv.cache_clear()

        magnetism_found = any("magnet" in key or "spintronic" in key for key in data)
        assert magnetism_found, "No magnetism journal found in SJR CSV"

    def test_eigenfactor_csv_exists(self):
        """maglab/physics/data/eigenfactor.csv must be present."""
        from pathlib import Path

        csv_path = (
            Path(__file__).parent.parent.parent / "maglab" / "physics" / "data" / "eigenfactor.csv"
        )
        assert csv_path.is_file(), f"Eigenfactor CSV not found at {csv_path}"

    def test_eigenfactor_csv_loads_prl(self):
        """Eigenfactor CSV must contain Physical Review Letters with a valid score."""
        from maglab.literature.journals import _load_eigenfactor_csv

        _load_eigenfactor_csv.cache_clear()
        data = _load_eigenfactor_csv()
        _load_eigenfactor_csv.cache_clear()

        key = "physical review letters"
        assert key in data, f"PRL not found in Eigenfactor CSV. Keys: {list(data.keys())[:10]}"
        assert data[key] > 0

    def test_eigenfactor_csv_no_jcr_labels(self):
        """Eigenfactor CSV must not introduce any JCR IF metric labels."""
        from maglab.literature.journals import _FORBIDDEN_LABELS, _load_eigenfactor_csv

        _load_eigenfactor_csv.cache_clear()
        data = _load_eigenfactor_csv()
        _load_eigenfactor_csv.cache_clear()

        for journal_name in data:
            for forbidden in _FORBIDDEN_LABELS:
                assert forbidden.lower() not in journal_name.lower(), (
                    f"Forbidden label '{forbidden}' found in eigenfactor CSV key '{journal_name}'"
                )

    def test_nemad_csv_exists(self):
        """maglab/physics/data/nemad.csv must be present."""
        from pathlib import Path

        csv_path = Path(__file__).parent.parent.parent / "maglab" / "physics" / "data" / "nemad.csv"
        assert csv_path.is_file(), f"NEMAD CSV not found at {csv_path}"

    def test_nemad_csv_loads_key_materials(self):
        """NEMAD CSV must contain key magnetic materials: CoFeB, Ta, Py."""
        import csv
        from pathlib import Path

        csv_path = Path(__file__).parent.parent.parent / "maglab" / "physics" / "data" / "nemad.csv"
        formulae = set()
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row = {k.strip(): v.strip() for k, v in row.items() if k}
                formula = row.get("formula") or row.get("Formula") or row.get("material") or ""
                if formula:
                    formulae.add(formula.lower())

        assert "cofeb" in formulae, f"CoFeB not in NEMAD. Found: {list(formulae)[:10]}"
        assert "ta" in formulae, f"Ta not in NEMAD. Found: {list(formulae)[:10]}"
        assert "py" in formulae, f"Py not in NEMAD. Found: {list(formulae)[:10]}"

    def test_bundled_csvs_enable_prl_offline_metrics(self):
        """With bundled CSVs, get_journal_metrics('Physical Review Letters') must return
        non-None SJR and Eigenfactor without any network calls."""
        from unittest.mock import patch

        from maglab.literature.journals import (
            _load_eigenfactor_csv,
            _load_sjr_csv,
            get_journal_metrics,
        )

        # Use real bundled CSVs but mock OpenAlex to avoid network
        _load_sjr_csv.cache_clear()
        _load_eigenfactor_csv.cache_clear()
        with patch(
            "maglab.literature.journals._fetch_openalex_venue_metrics",
            return_value={},
        ):
            metrics = get_journal_metrics("Physical Review Letters", use_openalex=False)
        _load_sjr_csv.cache_clear()
        _load_eigenfactor_csv.cache_clear()

        assert metrics.sjr is not None, "SJR should be available from bundled CSV"
        assert metrics.sjr > 0
        assert metrics.eigenfactor is not None, "Eigenfactor should be available from bundled CSV"
        assert metrics.eigenfactor > 0
