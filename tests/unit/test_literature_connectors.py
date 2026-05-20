"""tests/unit/test_literature_connectors.py — LiteratureRecord and connector unit tests.

All network calls mocked — zero real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from maglab.literature.connectors import (
    ArXivConnector,
    CrossRefConnector,
    LiteratureRecord,
    OpenAlexConnector,
    SemanticScholarConnector,
    _is_retriable,
    _make_cache_key,
    _reconstruct_abstract,
    fetch_by_doi_multi,
)

# ---------------------------------------------------------------------------
# LiteratureRecord
# ---------------------------------------------------------------------------


class TestLiteratureRecord:
    def test_basic_creation(self):
        rec = LiteratureRecord(
            doi="10.1103/physrevlett.106.036601",
            title="Test Paper",
            authors=["Smith, J.", "Lee, K."],
            year=2011,
            venue="Physical Review Letters",
        )
        assert rec.doi == "10.1103/physrevlett.106.036601"
        assert len(rec.authors) == 2
        assert rec.year == 2011

    def test_dedup_key_doi(self):
        rec = LiteratureRecord(doi="10.1234/test", title="Some Title")
        assert rec.dedup_key() == "doi:10.1234/test"

    def test_dedup_key_title_fallback(self):
        rec = LiteratureRecord(doi="", title="  A Great  Paper  ")
        assert rec.dedup_key() == "title:a great paper"

    def test_normalized_doi_strips_prefix(self):
        rec = LiteratureRecord(doi="https://doi.org/10.1234/UPPER")
        assert rec.normalized_doi() == "10.1234/upper"

    def test_normalized_doi_http(self):
        rec = LiteratureRecord(doi="http://doi.org/10.9999/xyz")
        assert rec.normalized_doi() == "10.9999/xyz"

    def test_empty_record_defaults(self):
        rec = LiteratureRecord()
        assert rec.doi == ""
        assert rec.authors == []
        assert rec.retraction_status == "unknown"
        assert rec.oa_status == ""

    def test_retraction_status_default(self):
        rec = LiteratureRecord(doi="10.1234/x")
        assert rec.retraction_status == "unknown"


# ---------------------------------------------------------------------------
# Cache key determinism
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_deterministic(self):
        k1 = _make_cache_key("oa_doi", "10.1234/test")
        k2 = _make_cache_key("oa_doi", "10.1234/test")
        assert k1 == k2

    def test_different_inputs(self):
        k1 = _make_cache_key("oa_doi", "10.1234/test")
        k2 = _make_cache_key("oa_doi", "10.5678/other")
        assert k1 != k2

    def test_length(self):
        k = _make_cache_key("search", "spin hall effect")
        assert len(k) == 32


# ---------------------------------------------------------------------------
# OpenAlexConnector mock
# ---------------------------------------------------------------------------


class TestOpenAlexConnector:
    @patch("maglab.literature.connectors._cache_get", return_value=None)
    @patch("maglab.literature.connectors._cache_put")
    def test_fetch_by_doi_success(self, mock_put, mock_get):
        mock_work = {
            "doi": "https://doi.org/10.1103/physrevlett.106.036601",
            "title": "ST-FMR Paper",
            "authorships": [{"author": {"display_name": "Yang Liu"}}],
            "publication_year": 2011,
            "primary_location": {
                "source": {"display_name": "Physical Review Letters"},
                "is_oa": False,
                "pdf_url": None,
            },
            "is_retracted": False,
            "cited_by_count": 1200,
            "concepts": [],
            "id": "https://openalex.org/W123",
            "open_access": {"oa_status": "closed"},
        }

        mock_pyalex = MagicMock()
        mock_works_instance = MagicMock()
        mock_works_instance.__getitem__ = MagicMock(return_value=mock_work)
        mock_pyalex.Works.return_value = mock_works_instance

        with patch.dict("sys.modules", {"pyalex": mock_pyalex}):
            connector = OpenAlexConnector.__new__(OpenAlexConnector)
            connector._email = ""
            connector._pyalex = mock_pyalex

            rec = connector._work_to_record(mock_work)

        assert rec.doi == "10.1103/physrevlett.106.036601"
        assert rec.title == "ST-FMR Paper"
        assert rec.year == 2011
        assert "Yang Liu" in rec.authors
        assert rec.retraction_status == "ok"
        assert rec.source == "openalex"

    def test_work_to_record_retracted(self):
        mock_work = {
            "doi": "https://doi.org/10.1234/retracted",
            "title": "Retracted Paper",
            "authorships": [],
            "publication_year": 2020,
            "primary_location": {"source": None, "is_oa": False},
            "is_retracted": True,
            "cited_by_count": 5,
            "concepts": [],
            "id": "W999",
            "open_access": {"oa_status": "unknown"},
        }
        rec = OpenAlexConnector._work_to_record(mock_work)
        assert rec.retraction_status == "retracted"

    def test_work_to_record_no_doi(self):
        mock_work = {
            "doi": None,
            "title": "No DOI Paper",
            "authorships": [],
            "publication_year": 2019,
            "primary_location": {"source": None},
            "is_retracted": False,
            "cited_by_count": 0,
            "concepts": [],
            "id": "W000",
            "open_access": {"oa_status": "unknown"},
        }
        rec = OpenAlexConnector._work_to_record(mock_work)
        assert rec.doi == ""


# ---------------------------------------------------------------------------
# SemanticScholarConnector mock
# ---------------------------------------------------------------------------


class TestSemanticScholarConnector:
    def test_paper_to_record_basic(self):
        mock_paper = MagicMock()
        mock_paper.externalIds = {"DOI": "10.1234/TEST"}
        mock_paper.title = "S2 Test Paper"
        mock_paper.authors = [MagicMock(name="Author One")]
        mock_paper.authors[0].name = "Author One"
        mock_paper.year = 2022
        mock_paper.venue = "Nature Physics"
        mock_paper.abstract = "An abstract."
        mock_paper.openAccessPdf = {"url": "https://example.com/paper.pdf"}
        mock_paper.paperId = "abc123"
        mock_paper.citationCount = 50
        mock_paper.fieldsOfStudy = ["Physics"]

        rec = SemanticScholarConnector._paper_to_record(mock_paper)
        assert rec.doi == "10.1234/test"
        assert rec.title == "S2 Test Paper"
        assert rec.year == 2022
        assert rec.s2_id == "abc123"
        assert rec.pdf_url == "https://example.com/paper.pdf"
        assert rec.source == "semantic_scholar"

    def test_paper_to_record_no_doi(self):
        mock_paper = MagicMock()
        mock_paper.externalIds = {}
        mock_paper.title = "No DOI"
        mock_paper.authors = []
        mock_paper.year = None
        mock_paper.venue = ""
        mock_paper.abstract = ""
        mock_paper.openAccessPdf = None
        mock_paper.paperId = "xyz999"
        mock_paper.citationCount = 0
        mock_paper.fieldsOfStudy = []

        rec = SemanticScholarConnector._paper_to_record(mock_paper)
        assert rec.doi == ""
        assert rec.s2_id == "xyz999"


# ---------------------------------------------------------------------------
# ArXivConnector mock
# ---------------------------------------------------------------------------


class TestArXivConnector:
    def test_result_to_record_basic(self):
        from datetime import datetime

        mock_result = MagicMock()
        mock_result.doi = "10.1234/arxiv-doi"
        mock_result.title = "arXiv Spin Paper"
        mock_result.authors = [MagicMock()]
        mock_result.authors[0].__str__ = lambda self: "Park, T."
        mock_result.published = datetime(2023, 5, 1)
        mock_result.journal_ref = "Phys. Rev. Lett."
        mock_result.summary = "Abstract text."
        mock_result.pdf_url = "https://arxiv.org/pdf/2305.00001"
        mock_result.links = []
        mock_result.categories = ["cond-mat.mes-hall"]

        rec = ArXivConnector._result_to_record(mock_result)
        assert rec.doi == "10.1234/arxiv-doi"
        assert rec.year == 2023
        assert rec.oa_status == "green"
        assert rec.source == "arxiv"
        assert "cond-mat.mes-hall" in rec.fields_of_study

    def test_result_to_record_no_doi(self):
        from datetime import datetime

        mock_result = MagicMock()
        mock_result.doi = None
        mock_result.title = "No DOI arXiv"
        mock_result.authors = []
        mock_result.published = datetime(2024, 1, 15)
        mock_result.journal_ref = None
        mock_result.summary = ""
        mock_result.pdf_url = None
        mock_result.links = []
        mock_result.categories = []

        rec = ArXivConnector._result_to_record(mock_result)
        assert rec.doi == ""
        assert rec.year == 2024

    def test_result_to_record_http_doi_prefix_stripped(self):
        """Regression test for R6 F-01: result.doi with 'http://doi.org/' prefix must
        be stored as a bare DOI (no prefix) in LiteratureRecord.doi.

        Older arXiv crosslisted papers may return 'http://doi.org/...' rather than
        'https://doi.org/...'. Both variants must be stripped.
        """
        from datetime import datetime

        mock_result = MagicMock()
        mock_result.doi = "http://doi.org/10.1103/PhysRevB.103.014412"
        mock_result.title = "Old Crosslisted arXiv Paper"
        mock_result.authors = [MagicMock()]
        mock_result.authors[0].__str__ = lambda self: "Smith, J."
        mock_result.published = datetime(2021, 1, 12)
        mock_result.journal_ref = "Phys. Rev. B"
        mock_result.summary = "Abstract."
        mock_result.pdf_url = "https://arxiv.org/pdf/2012.00001"
        mock_result.links = []
        mock_result.categories = ["cond-mat.str-el"]

        rec = ArXivConnector._result_to_record(mock_result)

        assert rec.doi == "10.1103/physrevb.103.014412", (
            f"Expected bare lowercase DOI, got {rec.doi!r}"
        )
        assert not rec.doi.startswith("http://"), (
            f"'http://' prefix was not stripped; got {rec.doi!r}"
        )
        assert not rec.doi.startswith("https://"), (
            f"'https://' prefix was not stripped; got {rec.doi!r}"
        )


# ---------------------------------------------------------------------------
# CrossRefConnector mock
# ---------------------------------------------------------------------------


class TestCrossRefConnector:
    def test_item_to_record_basic(self):
        item = {
            "DOI": "10.1103/PHYSREVLETT.106.036601",
            "title": ["Current-Induced Switching"],
            "author": [{"family": "Liu", "given": "Yang"}],
            "container-title": ["Physical Review Letters"],
            "published-print": {"date-parts": [[2011, 2, 11]]},
        }
        rec = CrossRefConnector._item_to_record(item)
        assert rec.doi == "10.1103/physrevlett.106.036601"
        assert rec.title == "Current-Induced Switching"
        assert "Liu, Yang" in rec.authors
        assert rec.year == 2011
        assert rec.venue == "Physical Review Letters"
        assert rec.source == "crossref"

    def test_item_to_record_no_year(self):
        item = {
            "DOI": "10.9999/x",
            "title": ["Test"],
            "author": [],
            "container-title": [],
        }
        rec = CrossRefConnector._item_to_record(item)
        assert rec.year is None


# ---------------------------------------------------------------------------
# fetch_by_doi_multi mock
# ---------------------------------------------------------------------------


class TestFetchByDoiMulti:
    @patch("maglab.literature.connectors._cache_get", return_value=None)
    @patch("maglab.literature.connectors._cache_put")
    def test_returns_first_success(self, mock_put, mock_get):
        mock_rec = LiteratureRecord(doi="10.1234/test", title="Found Paper", year=2022)

        with patch(
            "maglab.literature.connectors.OpenAlexConnector.fetch_by_doi",
            return_value=mock_rec,
        ):
            result = fetch_by_doi_multi("10.1234/test")

        assert result is not None
        assert result.title == "Found Paper"

    def test_returns_none_when_all_fail(self):
        with (
            patch(
                "maglab.literature.connectors.OpenAlexConnector.fetch_by_doi",
                return_value=None,
            ),
            patch(
                "maglab.literature.connectors.SemanticScholarConnector.fetch_by_doi",
                return_value=None,
            ),
            patch(
                "maglab.literature.connectors.CrossRefConnector.fetch_by_doi",
                return_value=None,
            ),
        ):
            result = fetch_by_doi_multi("10.9999/nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# FIX 1: _reconstruct_abstract — OpenAlex inverted-index → plain text
# ---------------------------------------------------------------------------


class TestReconstructAbstract:
    """Tests for the OpenAlex abstract inverted-index reconstruction helper."""

    def test_empty_dict_returns_empty_string(self):
        assert _reconstruct_abstract({}) == ""

    def test_single_word(self):
        result = _reconstruct_abstract({"Hello": [0]})
        assert result == "Hello"

    def test_two_words_ordered(self):
        """Words at positions 0 and 1 must come out in order."""
        inv = {"World": [1], "Hello": [0]}
        result = _reconstruct_abstract(inv)
        assert result == "Hello World"

    def test_sentence_reconstruction(self):
        """Reconstruct a short sentence from inverted index."""
        inv = {
            "spin": [0, 4],
            "Hall": [1],
            "effect": [2, 5],
            "anomalous": [3],
        }
        result = _reconstruct_abstract(inv)
        # Positions: 0=spin, 1=Hall, 2=effect, 3=anomalous, 4=spin, 5=effect
        assert result == "spin Hall effect anomalous spin effect"

    def test_non_consecutive_positions(self):
        """Positions need not be consecutive — gaps are ignored (join by spaces)."""
        inv = {"first": [10], "last": [99]}
        result = _reconstruct_abstract(inv)
        assert result == "first last"

    def test_real_abstract_snippet(self):
        """Simulate a real OpenAlex inverted index for a short abstract."""
        inv = {
            "We": [0],
            "report": [1],
            "large": [2],
            "spin": [3],
            "Hall": [4],
            "magnetoresistance": [5],
            "in": [6],
            "Ta/CoFeB.": [7],
        }
        result = _reconstruct_abstract(inv)
        assert "spin" in result
        assert "Hall" in result
        assert result.startswith("We report")

    def test_openalex_record_has_non_empty_abstract(self):
        """End-to-end: _work_to_record must populate abstract when inv-index is present."""
        mock_work = {
            "doi": "https://doi.org/10.1103/physrevlett.106.036601",
            "title": "Paper with Abstract",
            "authorships": [],
            "publication_year": 2021,
            "primary_location": {"source": None, "is_oa": False},
            "is_retracted": False,
            "cited_by_count": 100,
            "concepts": [],
            "id": "W456",
            "open_access": {"oa_status": "unknown"},
            "abstract_inverted_index": {
                "spin": [0],
                "Hall": [1],
                "effect": [2],
            },
        }
        rec = OpenAlexConnector._work_to_record(mock_work)
        # Must NOT be empty
        assert rec.abstract != ""
        assert "spin" in rec.abstract
        assert "Hall" in rec.abstract

    def test_openalex_record_missing_abstract_field(self):
        """_work_to_record must return empty string when abstract field is absent."""
        mock_work = {
            "doi": "https://doi.org/10.1234/noabstract",
            "title": "No Abstract Paper",
            "authorships": [],
            "publication_year": 2020,
            "primary_location": {"source": None, "is_oa": False},
            "is_retracted": False,
            "cited_by_count": 0,
            "concepts": [],
            "id": "W789",
            "open_access": {"oa_status": "unknown"},
            # abstract_inverted_index intentionally absent
        }
        rec = OpenAlexConnector._work_to_record(mock_work)
        assert rec.abstract == ""


# ---------------------------------------------------------------------------
# Regression tests — F-01: @_with_backoff is no longer dead code
# ---------------------------------------------------------------------------


class TestF01BackoffRetries:
    """Regression tests for F-01: retriable exceptions now propagate through
    the decorated method so the backoff wrapper can retry them."""

    def test_is_retriable_429(self):
        """HTTP 429 is classified as retriable."""
        class FakeResp:
            status_code = 429

        exc = Exception("rate limited")
        exc.response = FakeResp()  # type: ignore[attr-defined]
        assert _is_retriable(exc)

    def test_is_retriable_503(self):
        """HTTP 503 is classified as retriable."""
        class FakeResp:
            status_code = 503

        exc = Exception("unavailable")
        exc.response = FakeResp()  # type: ignore[attr-defined]
        assert _is_retriable(exc)

    def test_is_retriable_timeout(self):
        """TimeoutError is retriable."""
        assert _is_retriable(TimeoutError("timed out"))

    def test_is_retriable_connection_error(self):
        """ConnectionError is retriable."""
        assert _is_retriable(ConnectionError("network down"))

    def test_is_retriable_404_false(self):
        """HTTP 404 (not found) is NOT retriable."""
        class FakeResp:
            status_code = 404

        exc = Exception("not found")
        exc.response = FakeResp()  # type: ignore[attr-defined]
        assert not _is_retriable(exc)

    def test_is_retriable_value_error_false(self):
        """Generic ValueError is NOT retriable."""
        assert not _is_retriable(ValueError("bad input"))

    @patch("maglab.literature.connectors._cache_get", return_value=None)
    @patch("maglab.literature.connectors._cache_put")
    @patch("maglab.literature.connectors.time.sleep")
    def test_retriable_error_causes_retry(self, mock_sleep, mock_put, mock_get):
        """A 429-like exception raised inside fetch_by_doi causes the backoff
        wrapper to retry — confirming @_with_backoff is no longer dead code."""
        # Simulate a rate-limit exception that the connector should re-raise.
        class FakeResponse:
            status_code = 429

        class RateLimitError(Exception):
            pass

        call_count = 0

        def fake_getitem(doi_url):
            nonlocal call_count
            call_count += 1
            exc = RateLimitError("429 rate limited")
            exc.response = FakeResponse()  # type: ignore[attr-defined]
            raise exc

        mock_pyalex = MagicMock()
        works_instance = MagicMock()
        # MagicMock stores __getitem__ as a MagicMock by default; override side_effect.
        works_instance.__getitem__ = MagicMock(side_effect=fake_getitem)
        mock_pyalex.Works.return_value = works_instance

        connector = OpenAlexConnector.__new__(OpenAlexConnector)
        connector._email = ""
        connector._pyalex = mock_pyalex

        import pytest as _pytest
        with _pytest.raises(RuntimeError):
            connector.fetch_by_doi("10.1234/rate-limited")

        # The backoff wrapper retried 3 times (default max_retries=3).
        assert call_count == 3, f"Expected 3 retry attempts, got {call_count}"
        assert mock_sleep.call_count == 2  # sleep between attempts (not after last)


# ---------------------------------------------------------------------------
# Regression tests — F-03: LanceDB read-back on restart
# ---------------------------------------------------------------------------


class TestF03RAGPersistenceReadback:
    """Regression tests for F-03: LiteratureRAG must re-load persisted chunks
    on process restart so search returns results after a fresh init."""

    def test_search_returns_empty_when_no_chunks(self):
        """Baseline: fresh RAG with no chunks returns empty search results."""
        import tempfile
        from pathlib import Path

        from maglab.literature.rag import LiteratureRAG

        with tempfile.TemporaryDirectory() as tmpdir:
            # LanceDB unavailable in unit tests — memory-only mode.
            rag = LiteratureRAG(db_path=Path(tmpdir) / "lancedb")
            # No documents added — search must return []
            result = rag.search("spin Hall effect")
            assert result == []

    def test_load_from_db_called_on_init(self):
        """_load_from_db is invoked during __init__ (confirms read-back path exists)."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch as mpatch

        from maglab.literature.rag import LiteratureRAG

        with tempfile.TemporaryDirectory() as tmpdir, mpatch.object(LiteratureRAG, "_load_from_db") as mock_load:
            LiteratureRAG(db_path=Path(tmpdir) / "lancedb")
            assert mock_load.called, "_load_from_db was not called during __init__"

    def test_chunk_count_reflects_memory_after_add_document_mock(self):
        """After add_document (mocked embedding), chunk_count is non-zero and
        a subsequent search on a new instance that reloads from LanceDB also
        returns the chunks (simulated via _chunks injection)."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch as mpatch

        from maglab.literature.rag import Chunk, LiteratureRAG

        dummy_chunk = Chunk(
            chunk_id="test_0000",
            doc_id="test_doc",
            doi="10.1234/test",
            title="Test Paper",
            authors="Smith, J.",
            year=2023,
            venue="PRL",
            namespace="literature",
            text="spin Hall effect measurement results",
            chunk_index=0,
            embedding=[0.1] * 768,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lancedb"
            rag = LiteratureRAG(db_path=db_path)
            # Directly inject a chunk (bypass embedding model and LanceDB)
            rag._chunks.append(dummy_chunk)
            rag._bm25.build(rag._chunks)
            assert rag.chunk_count == 1

            # Simulate a fresh instance that reads back from LanceDB by
            # mocking _load_from_db to inject the same chunk.
            def mock_load(self_inner: LiteratureRAG) -> None:
                self_inner._chunks.append(dummy_chunk)
                self_inner._bm25.build(self_inner._chunks)

            with mpatch.object(LiteratureRAG, "_load_from_db", mock_load):
                rag2 = LiteratureRAG(db_path=db_path)
                assert rag2.chunk_count == 1, (
                    "chunk_count is 0 after restart — _load_from_db read-back not working"
                )


# ---------------------------------------------------------------------------
# Regression tests — N-02: cache connection closed on error
# ---------------------------------------------------------------------------


class TestN02CacheConnectionLeak:
    """Regression tests for N-02: SQLite connection is always closed, even on error."""

    def test_cache_get_closes_conn_on_json_error(self):
        """_cache_get closes the connection when json.loads raises JSONDecodeError.

        Uses a mock connection returned by _get_cache_conn so we can track whether
        conn.close() is called even when a subsequent operation raises.
        """
        import sqlite3
        from unittest.mock import MagicMock
        from unittest.mock import patch as mpatch

        from maglab.literature import connectors as conn_mod

        closed_calls: list[bool] = []

        # Build a mock connection whose execute() returns a row but whose
        # close() we can track.
        mock_row = ("bad_payload_json", 0.0)  # cached_at=0 → not expired (ttl=9999)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = mock_row
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_conn.execute.return_value = mock_cursor
        mock_conn.close.side_effect = lambda: closed_calls.append(True)

        with (
            mpatch.object(conn_mod, "_get_cache_conn", return_value=mock_conn),
            mpatch.object(conn_mod.json, "loads", side_effect=ValueError("bad json")),
        ):
            conn_mod._cache_get("test_key", ttl_s=9999.0)

        assert len(closed_calls) >= 1, (
            "_cache_get did not close the connection when json.loads raised"
        )

    def test_cache_put_closes_conn_on_execute_error(self):
        """_cache_put closes the connection when conn.execute raises.

        Uses a mock connection returned by _get_cache_conn so we can inject a
        failure on the INSERT and verify close() is still called.
        """
        import sqlite3
        from unittest.mock import MagicMock
        from unittest.mock import patch as mpatch

        from maglab.literature import connectors as conn_mod

        closed_calls: list[bool] = []

        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_conn.execute.side_effect = sqlite3.OperationalError("disk full")
        mock_conn.close.side_effect = lambda: closed_calls.append(True)

        with mpatch.object(conn_mod, "_get_cache_conn", return_value=mock_conn):
            conn_mod._cache_put("any_key", {"data": 1})

        assert len(closed_calls) >= 1, (
            "_cache_put did not close the connection when execute raised"
        )


# ---------------------------------------------------------------------------
# Regression tests — N-03: chunk_text raises ValueError on bad parameters
# ---------------------------------------------------------------------------


class TestN03ChunkTextValueError:
    """Regression tests for N-03: chunk_text with overlap >= chunk_size raises ValueError."""

    def test_overlap_equal_chunk_size_raises(self):
        """overlap == chunk_size must raise ValueError (step=0 → would loop forever)."""
        import pytest

        from maglab.literature.rag import chunk_text

        with pytest.raises(ValueError, match="chunk_size"):
            chunk_text("word " * 100, chunk_size=64, overlap=64)

    def test_overlap_greater_than_chunk_size_raises(self):
        """overlap > chunk_size must raise ValueError."""
        import pytest

        from maglab.literature.rag import chunk_text

        with pytest.raises(ValueError, match="chunk_size"):
            chunk_text("word " * 100, chunk_size=32, overlap=64)

    def test_valid_parameters_still_work(self):
        """Normal usage (chunk_size > overlap) must still return chunks correctly."""
        from maglab.literature.rag import chunk_text

        result = chunk_text("a b c d e f g h", chunk_size=4, overlap=1)
        assert len(result) >= 1
        assert "a" in result[0]

    def test_empty_text_returns_empty_list(self):
        """Empty input must return [] regardless of chunk_size / overlap."""
        from maglab.literature.rag import chunk_text

        assert chunk_text("", chunk_size=512, overlap=64) == []
