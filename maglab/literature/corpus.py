"""Local corpus — LiteratureRecord SQLite persistence, deduplication, and search (§14).

DOI-first deduplication, falling back to normalized title.
Corpus accumulates across sessions — linked to research_pool.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import platformdirs

from maglab.literature.connectors import LiteratureRecord

log = logging.getLogger(__name__)
_APP = "maglab"


# ---------------------------------------------------------------------------
# DB path
# ---------------------------------------------------------------------------


def _corpus_db_path() -> Path:
    d = Path(platformdirs.user_data_dir(_APP)) / "literature"
    d.mkdir(parents=True, exist_ok=True)
    return d / "corpus.db"


# ---------------------------------------------------------------------------
# Corpus DB
# ---------------------------------------------------------------------------


class CorpusDB:
    """Local corpus that persists LiteratureRecord objects in SQLite.

    Parameters
    ----------
    db_path:
        SQLite file path (None uses the default XDG path).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _corpus_db_path()
        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initialize the DB schema."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                dedup_key   TEXT PRIMARY KEY,
                doi         TEXT NOT NULL DEFAULT '',
                title       TEXT NOT NULL DEFAULT '',
                authors     TEXT NOT NULL DEFAULT '[]',
                year        INTEGER,
                venue       TEXT NOT NULL DEFAULT '',
                abstract    TEXT NOT NULL DEFAULT '',
                pdf_url     TEXT NOT NULL DEFAULT '',
                pdf_path    TEXT NOT NULL DEFAULT '',
                openalex_id TEXT NOT NULL DEFAULT '',
                s2_id       TEXT NOT NULL DEFAULT '',
                oa_status   TEXT NOT NULL DEFAULT 'unknown',
                retraction_status TEXT NOT NULL DEFAULT 'unknown',
                source      TEXT NOT NULL DEFAULT '',
                citation_count INTEGER,
                fields_of_study TEXT NOT NULL DEFAULT '[]',
                added_at    REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_doi ON records(doi);
            CREATE INDEX IF NOT EXISTS idx_year ON records(year);
            CREATE INDEX IF NOT EXISTS idx_venue ON records(venue);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, record: LiteratureRecord, pdf_path: str = "") -> bool:
        """Add a record. Returns False if it already exists (duplicate ignored).

        Returns
        -------
        True if newly inserted, False if skipped as a duplicate.
        """
        import json  # noqa: PLC0415

        key = record.dedup_key()
        existing = self._conn.execute(
            "SELECT dedup_key FROM records WHERE dedup_key = ?", (key,)
        ).fetchone()
        if existing:
            return False

        self._conn.execute(
            """
            INSERT INTO records
              (dedup_key, doi, title, authors, year, venue, abstract,
               pdf_url, pdf_path, openalex_id, s2_id, oa_status,
               retraction_status, source, citation_count,
               fields_of_study, added_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                key,
                record.doi,
                record.title,
                json.dumps(record.authors),
                record.year,
                record.venue,
                record.abstract,
                record.pdf_url,
                pdf_path,
                record.openalex_id,
                record.s2_id,
                record.oa_status,
                record.retraction_status,
                record.source,
                record.citation_count,
                json.dumps(record.fields_of_study),
                time.time(),
            ),
        )
        self._conn.commit()
        log.debug("Corpus added: %s (%s)", record.title[:60], key)
        return True

    def add_many(self, records: list[LiteratureRecord]) -> int:
        """Add a list of records in bulk and return the insertion count."""
        return sum(1 for r in records if self.add(r))

    def get_by_doi(self, doi: str) -> LiteratureRecord | None:
        """Retrieve a record by DOI.

        Handles both prefixed (``https://doi.org/10.x``) and bare
        (``10.x``) DOI forms stored in the database by normalising the
        query *and* stripping the prefix inside the SQL expression so that
        records inserted with a URL prefix are also found (fix for F-10).
        """
        doi_norm = (
            doi.lower()
            .replace("https://doi.org/", "")
            .replace("http://doi.org/", "")
            .replace("doi:", "")
        )
        row = self._conn.execute(
            "SELECT * FROM records WHERE LOWER(REPLACE(REPLACE(REPLACE(doi, 'https://doi.org/', ''), 'http://doi.org/', ''), 'doi:', '')) = ?",
            (doi_norm,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def search(
        self,
        *,
        year_min: int | None = None,
        year_max: int | None = None,
        author: str = "",
        venue: str = "",
        query: str = "",
        limit: int = 50,
    ) -> list[LiteratureRecord]:
        """Condition-based search."""
        clauses = []
        params: list[Any] = []

        if year_min is not None:
            clauses.append("year >= ?")
            params.append(year_min)
        if year_max is not None:
            clauses.append("year <= ?")
            params.append(year_max)
        if author:
            clauses.append("authors LIKE ?")
            params.append(f"%{author}%")
        if venue:
            clauses.append("venue LIKE ?")
            params.append(f"%{venue}%")
        if query:
            clauses.append("(title LIKE ? OR abstract LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM records {where} ORDER BY year DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def count(self) -> int:
        """Number of stored records."""
        return self._conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    def all_records(self, limit: int = 1000) -> list[LiteratureRecord]:
        """Return all records."""
        rows = self._conn.execute(
            "SELECT * FROM records ORDER BY added_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def update_pdf_path(self, dedup_key: str, pdf_path: str) -> None:
        """Update the PDF path."""
        self._conn.execute(
            "UPDATE records SET pdf_path = ? WHERE dedup_key = ?",
            (pdf_path, dedup_key),
        )
        self._conn.commit()

    def update_retraction_status(self, doi: str, status: str) -> None:
        """Update the retraction status.

        Applies the same three-prefix normalization as ``get_by_doi()`` so that
        prefixed DOIs (``https://doi.org/10.x``, ``http://doi.org/10.x``,
        ``doi:10.x``) correctly match bare rows stored as ``10.x``.
        """
        doi_norm = (
            doi.lower()
            .replace("https://doi.org/", "")
            .replace("http://doi.org/", "")
            .replace("doi:", "")
        )
        self._conn.execute(
            "UPDATE records SET retraction_status = ? "
            "WHERE LOWER(REPLACE(REPLACE(REPLACE(doi, 'https://doi.org/', ''), 'http://doi.org/', ''), 'doi:', '')) = ?",
            (status, doi_norm),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the DB connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> LiteratureRecord:
        import json  # noqa: PLC0415

        return LiteratureRecord(
            doi=row["doi"],
            title=row["title"],
            authors=json.loads(row["authors"]),
            year=row["year"],
            venue=row["venue"],
            abstract=row["abstract"],
            pdf_url=row["pdf_url"],
            openalex_id=row["openalex_id"],
            s2_id=row["s2_id"],
            oa_status=row["oa_status"],
            retraction_status=row["retraction_status"],
            source=row["source"],
            citation_count=row["citation_count"],
            fields_of_study=json.loads(row["fields_of_study"]),
        )


# ---------------------------------------------------------------------------
# Module-level default instance
# ---------------------------------------------------------------------------

_default_corpus: CorpusDB | None = None


def get_corpus(db_path: Path | None = None) -> CorpusDB:
    """Return the default CorpusDB instance."""
    global _default_corpus
    if db_path is not None:
        return CorpusDB(db_path)
    if _default_corpus is None:
        _default_corpus = CorpusDB()
    return _default_corpus
