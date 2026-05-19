"""Literature index — evidence_matrix SQLite persistence and research orchestration support (§14.7).

``EvidenceMatrix`` is a structure used by research orchestration to accumulate
and validate candidate papers.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
_APP = "maglab"


# ---------------------------------------------------------------------------
# evidence_matrix schema (§14.7)
# ---------------------------------------------------------------------------


class EvidenceEntry(BaseModel):
    """Single evidence_matrix entry.

    Attributes
    ----------
    ref_key:
        Reference key (e.g. 'Smith2022_AHE').
    tier:
        Paper quality tier (T1: top/core, T2: supporting, T3: peripheral).
    title:
        Paper title.
    authors:
        Author list.
    year:
        Publication year.
    venue:
        Journal or conference.
    doi:
        DOI (if verified).
    url:
        Access URL.
    openalex_id:
        OpenAlex Work ID.
    s2_id:
        Semantic Scholar Paper ID.
    oa_status:
        Open Access status.
    retraction_status:
        Retraction status.
    verification_status:
        Verification status (verified/pending/failed).
    notes:
        Supplementary notes.
    """

    ref_key: str
    tier: Literal["T1", "T2", "T3"] = "T3"
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    url: str = ""
    openalex_id: str = ""
    s2_id: str = ""
    oa_status: str = "unknown"
    retraction_status: str = "unknown"
    verification_status: Literal["verified", "pending", "failed"] = "pending"
    notes: str = ""


# ---------------------------------------------------------------------------
# EvidenceMatrix DB
# ---------------------------------------------------------------------------


def _matrix_db_path() -> Path:
    d = Path(platformdirs.user_data_dir(_APP)) / "literature"
    d.mkdir(parents=True, exist_ok=True)
    return d / "evidence_matrix.db"


class EvidenceMatrix:
    """evidence_matrix SQLite persistence.

    Parameters
    ----------
    db_path:
        SQLite file path (None uses the default path).
    session_id:
        Research session ID (separates different sessions).
    """

    def __init__(
        self,
        db_path: Path | None = None,
        session_id: str = "default",
    ) -> None:
        self._db_path = db_path or _matrix_db_path()
        self._session_id = session_id
        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS evidence_matrix (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          TEXT NOT NULL,
                ref_key             TEXT NOT NULL,
                tier                TEXT NOT NULL DEFAULT 'T3',
                title               TEXT NOT NULL DEFAULT '',
                authors             TEXT NOT NULL DEFAULT '[]',
                year                INTEGER,
                venue               TEXT NOT NULL DEFAULT '',
                doi                 TEXT NOT NULL DEFAULT '',
                url                 TEXT NOT NULL DEFAULT '',
                openalex_id         TEXT NOT NULL DEFAULT '',
                s2_id               TEXT NOT NULL DEFAULT '',
                oa_status           TEXT NOT NULL DEFAULT 'unknown',
                retraction_status   TEXT NOT NULL DEFAULT 'unknown',
                verification_status TEXT NOT NULL DEFAULT 'pending',
                notes               TEXT NOT NULL DEFAULT '',
                added_at            REAL NOT NULL,
                UNIQUE(session_id, ref_key)
            );
            CREATE INDEX IF NOT EXISTS idx_em_session
              ON evidence_matrix(session_id);
            CREATE INDEX IF NOT EXISTS idx_em_tier
              ON evidence_matrix(tier);
            CREATE INDEX IF NOT EXISTS idx_em_verify
              ON evidence_matrix(verification_status);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, entry: EvidenceEntry) -> bool:
        """Add an entry. Returns False if ref_key is a duplicate."""
        try:
            self._conn.execute(
                """
                INSERT INTO evidence_matrix
                  (session_id, ref_key, tier, title, authors, year, venue,
                   doi, url, openalex_id, s2_id, oa_status,
                   retraction_status, verification_status, notes, added_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self._session_id,
                    entry.ref_key,
                    entry.tier,
                    entry.title,
                    json.dumps(entry.authors),
                    entry.year,
                    entry.venue,
                    entry.doi,
                    entry.url,
                    entry.openalex_id,
                    entry.s2_id,
                    entry.oa_status,
                    entry.retraction_status,
                    entry.verification_status,
                    entry.notes,
                    time.time(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_verification(
        self, ref_key: str, status: Literal["verified", "pending", "failed"]
    ) -> None:
        """Update the verification status."""
        self._conn.execute(
            "UPDATE evidence_matrix SET verification_status=? WHERE session_id=? AND ref_key=?",
            (status, self._session_id, ref_key),
        )
        self._conn.commit()

    def update_retraction(self, ref_key: str, retraction_status: str) -> None:
        """Update the retraction status."""
        self._conn.execute(
            "UPDATE evidence_matrix SET retraction_status=? WHERE session_id=? AND ref_key=?",
            (retraction_status, self._session_id, ref_key),
        )
        self._conn.commit()

    def all(self, tier: str | None = None) -> list[EvidenceEntry]:
        """Return all entries or entries for a specific tier."""
        if tier:
            rows = self._conn.execute(
                "SELECT * FROM evidence_matrix WHERE session_id=? AND tier=? ORDER BY added_at",
                (self._session_id, tier),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM evidence_matrix WHERE session_id=? ORDER BY tier, added_at",
                (self._session_id,),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def verified(self) -> list[EvidenceEntry]:
        """Return only verified entries."""
        rows = self._conn.execute(
            "SELECT * FROM evidence_matrix WHERE session_id=? AND verification_status='verified'",
            (self._session_id,),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def flagged_retracted(self) -> list[EvidenceEntry]:
        """Return the list of retracted entries."""
        rows = self._conn.execute(
            "SELECT * FROM evidence_matrix WHERE session_id=? AND retraction_status='retracted'",
            (self._session_id,),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def to_json(self) -> str:
        """Serialize the full matrix to a JSON string."""
        entries = self.all()
        return json.dumps([e.model_dump() for e in entries], ensure_ascii=False, indent=2)

    def count(self) -> int:
        """Entry count for the current session."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM evidence_matrix WHERE session_id=?",
            (self._session_id,),
        ).fetchone()[0]

    def clear(self) -> None:
        """Delete all entries for the current session."""
        self._conn.execute("DELETE FROM evidence_matrix WHERE session_id=?", (self._session_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> EvidenceEntry:
        return EvidenceEntry(
            ref_key=row["ref_key"],
            tier=row["tier"],  # type: ignore[arg-type]
            title=row["title"],
            authors=json.loads(row["authors"]),
            year=row["year"],
            venue=row["venue"],
            doi=row["doi"],
            url=row["url"],
            openalex_id=row["openalex_id"],
            s2_id=row["s2_id"],
            oa_status=row["oa_status"],
            retraction_status=row["retraction_status"],
            verification_status=row["verification_status"],  # type: ignore[arg-type]
            notes=row["notes"],
        )
