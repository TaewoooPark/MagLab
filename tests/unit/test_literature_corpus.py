"""tests/unit/test_literature_corpus.py — CorpusDB unit tests.

Covers DOI-prefix normalization in get_by_doi() and update_retraction_status()
(regression for F-01: doi: prefix not stripped in SQL REPLACE chain).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from maglab.literature.connectors import LiteratureRecord
from maglab.literature.corpus import CorpusDB


@pytest.fixture()
def db(tmp_path) -> Generator[CorpusDB, None, None]:
    """In-memory (tmp_path) CorpusDB for each test."""
    instance = CorpusDB(db_path=tmp_path / "corpus_test.db")
    yield instance
    instance.close()


def _record(doi: str, title: str = "Test Paper") -> LiteratureRecord:
    return LiteratureRecord(
        doi=doi,
        title=title,
        authors=["Smith, J."],
        year=2021,
        venue="Physical Review B",
    )


# ---------------------------------------------------------------------------
# F-01 regression — doi: prefix normalization in SQL REPLACE chain
# ---------------------------------------------------------------------------


class TestGetByDoiPrefixNormalization:
    """get_by_doi() must find records regardless of which DOI form was used at
    storage time or lookup time (bare, https://, http://, doi:)."""

    def test_stored_bare_lookup_bare(self, db: CorpusDB):
        rec = _record("10.1103/physrevb.103.014412")
        db.add(rec)
        result = db.get_by_doi("10.1103/physrevb.103.014412")
        assert result is not None

    def test_stored_bare_lookup_doi_prefix(self, db: CorpusDB):
        """Record stored with bare DOI is found when looked up with doi: prefix."""
        rec = _record("10.1103/physrevb.103.014412")
        db.add(rec)
        result = db.get_by_doi("doi:10.1103/physrevb.103.014412")
        assert result is not None

    def test_stored_bare_lookup_https(self, db: CorpusDB):
        """Record stored with bare DOI is found when looked up with https://doi.org/ prefix."""
        rec = _record("10.1103/physrevb.103.014412")
        db.add(rec)
        result = db.get_by_doi("https://doi.org/10.1103/physrevb.103.014412")
        assert result is not None

    def test_stored_doi_prefix_lookup_bare(self, db: CorpusDB):
        """Record stored with doi: prefix is found when looked up with bare DOI (F-01 core case)."""
        rec = _record("doi:10.1103/physrevb.103.014412")
        db.add(rec)
        result = db.get_by_doi("10.1103/physrevb.103.014412")
        assert result is not None

    def test_stored_doi_prefix_lookup_doi_prefix(self, db: CorpusDB):
        """Record stored with doi: prefix is found when looked up with doi: prefix."""
        rec = _record("doi:10.1103/physrevb.103.014412")
        db.add(rec)
        result = db.get_by_doi("doi:10.1103/physrevb.103.014412")
        assert result is not None

    def test_stored_https_lookup_doi_prefix(self, db: CorpusDB):
        """Record stored with https:// prefix is found when looked up with doi: prefix."""
        rec = _record("https://doi.org/10.1103/physrevb.103.014412")
        db.add(rec)
        result = db.get_by_doi("doi:10.1103/physrevb.103.014412")
        assert result is not None

    def test_missing_doi_returns_none(self, db: CorpusDB):
        rec = _record("10.9999/absent")
        db.add(rec)
        result = db.get_by_doi("10.9999/not-here")
        assert result is None

    def test_case_insensitive_match(self, db: CorpusDB):
        """DOI comparison is case-insensitive."""
        rec = _record("10.1103/PhysRevB.103.014412")
        db.add(rec)
        result = db.get_by_doi("10.1103/physrevb.103.014412")
        assert result is not None


class TestUpdateRetractionStatusPrefixNormalization:
    """update_retraction_status() must update the correct row regardless of
    which DOI form was used at storage time or lookup time."""

    def test_stored_doi_prefix_update_bare(self, db: CorpusDB):
        """Retraction update with bare DOI hits row stored with doi: prefix (F-01 core case)."""
        rec = _record("doi:10.1103/physrevb.103.014412")
        db.add(rec)

        db.update_retraction_status("10.1103/physrevb.103.014412", "retracted")

        found = db.get_by_doi("doi:10.1103/physrevb.103.014412")
        assert found is not None
        assert found.retraction_status == "retracted"

    def test_stored_bare_update_doi_prefix(self, db: CorpusDB):
        """Retraction update with doi: prefix hits row stored with bare DOI."""
        rec = _record("10.1103/physrevb.103.014412")
        db.add(rec)

        db.update_retraction_status("doi:10.1103/physrevb.103.014412", "retracted")

        found = db.get_by_doi("10.1103/physrevb.103.014412")
        assert found is not None
        assert found.retraction_status == "retracted"

    def test_stored_doi_prefix_update_https(self, db: CorpusDB):
        """Retraction update with https:// prefix hits row stored with doi: prefix."""
        rec = _record("doi:10.1103/physrevb.103.014412")
        db.add(rec)

        db.update_retraction_status("https://doi.org/10.1103/physrevb.103.014412", "retracted")

        found = db.get_by_doi("10.1103/physrevb.103.014412")
        assert found is not None
        assert found.retraction_status == "retracted"

    def test_no_match_is_silent_noop(self, db: CorpusDB):
        """update_retraction_status on a non-existent DOI does not raise."""
        db.update_retraction_status("10.9999/nonexistent", "retracted")
        # Verify no row was created
        assert db.count() == 0
