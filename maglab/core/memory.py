"""Three-tier memory system (§5.5, §5.13).

Tier 1 — Working context: ``WorkingContext`` in ``core/context.py`` (in-memory).
Tier 2 — Session state: SQLite (``~/.local/share/maglab/sessions/sessions.db``).
Tier 3 — Long-term memory: ``memories/*.md`` files, grep search.

research_pool (§5.13) — Accumulates confirmed results, failed parameter regions,
and anomalies as structured records in ``memories/research_pool/``.
Supports two query paths: ``query()`` (substring grep) and ``semantic_query()``
(TF-IDF cosine relevance ranking — the §5.13 vector search).

Depends only on maglab.config.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import platformdirs

log = logging.getLogger(__name__)

_APP = "maglab"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _sessions_db_path() -> Path:
    data_dir = Path(platformdirs.user_data_dir(_APP)) / "sessions"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "sessions.db"


def _memories_dir() -> Path:
    data_dir = Path(platformdirs.user_data_dir(_APP)) / "memories"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _research_pool_dir() -> Path:
    d = _memories_dir() / "research_pool"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Tier 2 — Session state (SQLite)
# ---------------------------------------------------------------------------


def _ensure_session_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id   TEXT PRIMARY KEY,
            created_at   REAL NOT NULL,
            updated_at   REAL NOT NULL,
            state        TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_kv (
            session_id   TEXT NOT NULL,
            key          TEXT NOT NULL,
            value        TEXT NOT NULL,
            ts           REAL NOT NULL,
            PRIMARY KEY (session_id, key)
        )
        """
    )
    conn.commit()


class SessionMemory:
    """Session state memory — SQLite persistence.

    Parameters
    ----------
    session_id:
        Session identifier (auto-generated UUID4 if None).
    db_path:
        SQLite file path (None → default XDG path).
    """

    def __init__(
        self,
        session_id: str | None = None,
        db_path: Path | None = None,
    ) -> None:
        self._db_path = db_path or _sessions_db_path()
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        _ensure_session_schema(self._conn)
        self._session_id = session_id or str(uuid.uuid4())
        self._ensure_session()

    @property
    def session_id(self) -> str:
        return self._session_id

    def _ensure_session(self) -> None:
        cur = self._conn.execute(
            "SELECT session_id FROM sessions WHERE session_id=?",
            (self._session_id,),
        )
        if not cur.fetchone():
            now = time.time()
            self._conn.execute(
                "INSERT INTO sessions (session_id, created_at, updated_at) VALUES (?, ?, ?)",
                (self._session_id, now, now),
            )
            self._conn.commit()

    def set(self, key: str, value: Any) -> None:
        """Store a key-value pair in the session."""
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO session_kv (session_id, key, value, ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, key) DO UPDATE SET value=excluded.value, ts=excluded.ts
            """,
            (self._session_id, key, json.dumps(value), now),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?",
            (now, self._session_id),
        )
        self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for key (or default if not found)."""
        cur = self._conn.execute(
            "SELECT value FROM session_kv WHERE session_id=? AND key=?",
            (self._session_id, key),
        )
        row = cur.fetchone()
        return json.loads(row["value"]) if row else default

    def all_keys(self) -> list[str]:
        """Return all keys in the session."""
        cur = self._conn.execute(
            "SELECT key FROM session_kv WHERE session_id=? ORDER BY ts ASC",
            (self._session_id,),
        )
        return [row["key"] for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Tier 3 — Long-term memory (memories/*.md)
# ---------------------------------------------------------------------------


class LongTermMemory:
    """Long-term memory — ``memories/*.md`` files with grep search.

    Parameters
    ----------
    memories_dir:
        Memory directory path (None → default XDG path).
    """

    def __init__(self, memories_dir: Path | None = None) -> None:
        self._dir = memories_dir or _memories_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, content: str) -> Path:
        """Write a memory file.

        Parameters
        ----------
        name:
            File name (without extension; ``.md`` is added automatically).
        content:
            Markdown content.
        """
        p = self._dir / f"{name}.md"
        p.write_text(content, encoding="utf-8")
        return p

    def read(self, name: str) -> str | None:
        """Read a memory file (returns None if not found)."""
        p = self._dir / f"{name}.md"
        return p.read_text(encoding="utf-8") if p.is_file() else None

    def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Simple grep search — returns files and lines containing the query string.

        Returns
        -------
        list of {file, line_no, text}
        """
        results: list[dict[str, Any]] = []
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        for md_file in sorted(self._dir.glob("*.md")):
            for lineno, line in enumerate(
                md_file.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if pattern.search(line):
                    results.append({"file": md_file.name, "line_no": lineno, "text": line.strip()})
                    if len(results) >= max_results:
                        return results
        return results

    def list_files(self) -> list[str]:
        """Return the list of memory file names (with extension)."""
        return [p.name for p in sorted(self._dir.glob("*.md"))]


# ---------------------------------------------------------------------------
# research_pool (§5.13)
# ---------------------------------------------------------------------------


class PoolRecordKind(StrEnum):
    """research_pool record type."""

    CONFIRMED_RESULT = "confirmed_result"
    """Confirmed result (DataPoint level)."""
    FAILED_REGION = "failed_region"
    """Failed parameter region."""
    ANOMALY = "anomaly"
    """Unexpected anomaly."""
    EFFECTIVE_CONFIG = "effective_config"
    """Tool configuration that proved effective."""


@dataclass
class PoolRecord:
    """A single research_pool record."""

    record_id: str
    """UUID4 identifier."""
    kind: PoolRecordKind
    """Record type."""
    topic_tags: list[str]
    """Topic tag list (for search)."""
    summary: str
    """Summary string."""
    provenance_ref: str | None
    """Associated provenance ID (if any)."""
    timestamp: float
    """Record timestamp (Unix epoch)."""
    data: dict[str, Any] = field(default_factory=dict)
    """Free-form additional data."""


# ---------------------------------------------------------------------------
# TF-IDF relevance ranking (§5.13 vector search)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens (ASCII alphanumerics + underscore)."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _tfidf_vectors(docs: list[str]) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Compute TF-IDF vectors for a document collection.

    Returns ``(vectors, idf)`` where each vector maps token → TF-IDF weight and
    *idf* is the shared inverse-document-frequency table.
    """
    tokenized = [_tokenize(d) for d in docs]
    n_docs = len(docs)
    df: Counter[str] = Counter()
    for toks in tokenized:
        for tok in set(toks):
            df[tok] += 1
    idf = {tok: math.log((n_docs + 1) / (count + 1)) + 1.0 for tok, count in df.items()}
    vectors: list[dict[str, float]] = []
    for toks in tokenized:
        tf = Counter(toks)
        total = len(toks) or 1
        vectors.append({tok: (n / total) * idf.get(tok, 0.0) for tok, n in tf.items()})
    return vectors, idf


def _tfidf_query_vector(query: str, idf: dict[str, float]) -> dict[str, float]:
    """Build a TF-IDF vector for a query using a pre-computed *idf* table."""
    tf = Counter(_tokenize(query))
    total = sum(tf.values()) or 1
    return {tok: (n / total) * idf[tok] for tok, n in tf.items() if tok in idf}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity of two sparse vectors, in ``[0, 1]``."""
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in a.keys() & b.keys())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class ResearchPool:
    """Cumulative research memory — research_pool.

    Stored as ``memories/research_pool/<record_id>.json`` files.

    Parameters
    ----------
    pool_dir:
        Pool directory (None → default XDG path).
    """

    def __init__(self, pool_dir: Path | None = None) -> None:
        self._dir = pool_dir or _research_pool_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        *,
        kind: PoolRecordKind,
        topic_tags: list[str],
        summary: str,
        provenance_ref: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> PoolRecord:
        """Add a record to the pool."""
        rec = PoolRecord(
            record_id=str(uuid.uuid4()),
            kind=kind,
            topic_tags=topic_tags,
            summary=summary,
            provenance_ref=provenance_ref,
            timestamp=time.time(),
            data=data or {},
        )
        self._save(rec)
        return rec

    def query(
        self,
        *,
        keywords: list[str] | None = None,
        kind: PoolRecordKind | None = None,
        topic_tag: str | None = None,
        max_results: int = 20,
    ) -> list[PoolRecord]:
        """Query the pool.

        Parameters
        ----------
        keywords:
            Keyword list to grep-search in summary or topic_tags.
        kind:
            Record type filter.
        topic_tag:
            Exact tag filter.
        max_results:
            Maximum number of results to return.
        """
        results: list[PoolRecord] = []
        kw_patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in (keywords or [])]
        for json_file in sorted(self._dir.glob("*.json"), reverse=True):
            if len(results) >= max_results:
                break
            try:
                rec = self._load(json_file)
            except Exception as exc:  # noqa: BLE001
                log.warning("ResearchPool: skipping malformed record %s: %s", json_file.name, exc)
                continue
            if kind and rec.kind != kind:
                continue
            if topic_tag and topic_tag not in rec.topic_tags:
                continue
            if kw_patterns:
                target = rec.summary + " " + " ".join(rec.topic_tags)
                if not all(p.search(target) for p in kw_patterns):
                    continue
            results.append(rec)
        return results

    def semantic_query(
        self,
        query: str,
        *,
        kind: PoolRecordKind | None = None,
        max_results: int = 10,
        min_score: float = 0.0,
    ) -> list[PoolRecord]:
        """Relevance-ranked query over the pool (§5.13 vector search).

        Ranks every record by TF-IDF cosine similarity between *query* and the
        record's ``summary`` + ``topic_tags``.  Unlike :meth:`query` (substring
        grep), this surfaces semantically related prior research even when no
        single keyword matches verbatim.

        Parameters
        ----------
        query:
            Free-text query string.
        kind:
            Optional record-type filter applied before ranking.
        max_results:
            Maximum number of records to return.
        min_score:
            Drop records whose cosine similarity is at or below this value.

        Returns
        -------
        Records sorted by descending relevance.
        """
        records: list[PoolRecord] = []
        for json_file in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                rec = self._load(json_file)
            except Exception as exc:  # noqa: BLE001
                log.warning("ResearchPool: skipping malformed record %s: %s", json_file.name, exc)
                continue
            if kind and rec.kind != kind:
                continue
            records.append(rec)
        if not records:
            return []
        docs = [f"{r.summary} {' '.join(r.topic_tags)}" for r in records]
        vectors, idf = _tfidf_vectors(docs)
        q_vec = _tfidf_query_vector(query, idf)
        scored = [(rec, _cosine(q_vec, vec)) for rec, vec in zip(records, vectors, strict=True)]
        ranked = sorted(
            (rs for rs in scored if rs[1] > min_score),
            key=lambda rs: rs[1],
            reverse=True,
        )
        return [rec for rec, _ in ranked[:max_results]]

    def get(self, record_id: str) -> PoolRecord | None:
        """Look up a record directly by record_id."""
        p = self._dir / f"{record_id}.json"
        return self._load(p) if p.is_file() else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save(self, rec: PoolRecord) -> None:
        p = self._dir / f"{rec.record_id}.json"
        p.write_text(
            json.dumps(
                {
                    "record_id": rec.record_id,
                    "kind": rec.kind.value,
                    "topic_tags": rec.topic_tags,
                    "summary": rec.summary,
                    "provenance_ref": rec.provenance_ref,
                    "timestamp": rec.timestamp,
                    "data": rec.data,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _load(path: Path) -> PoolRecord:
        d = json.loads(path.read_text(encoding="utf-8"))
        return PoolRecord(
            record_id=d["record_id"],
            kind=PoolRecordKind(d["kind"]),
            topic_tags=d["topic_tags"],
            summary=d["summary"],
            provenance_ref=d.get("provenance_ref"),
            timestamp=d["timestamp"],
            data=d.get("data", {}),
        )
