"""Checkpoint and resume — durable steps / idempotency keys / SQLite persistence (§5.8, §5.12).

Serializes research loop tree state and Ralph loop state to SQLite periodically.
Every step is identified by an **idempotency key** (`idempotency_key`) so that
resumption after restart is duplicate-free.

Backend for the ``maglab task status <id>`` CLI command.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import platformdirs

from maglab.core.storage import connect_writable_sqlite

_APP = "maglab"


# ---------------------------------------------------------------------------
# Step status
# ---------------------------------------------------------------------------


class StepStatus(StrEnum):
    """Execution status of an individual step."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Checkpoint record
# ---------------------------------------------------------------------------


@dataclass
class CheckpointRecord:
    """A single checkpoint record.

    ``idempotency_key`` is a stable, human-assigned key that identifies the same
    step across runs and prevents duplicate ingestion on resumption.
    """

    checkpoint_id: str
    """Auto-generated UUID4."""
    task_id: str
    """Task (research loop run or Ralph loop) ID."""
    idempotency_key: str
    """Idempotency key — prevents duplicate steps."""
    status: StepStatus
    """Current status."""
    payload: dict[str, Any]
    """Step state serialization data (free-form JSON)."""
    provenance_id: str | None = None
    """Associated provenance record ID (if any)."""
    ts_created: float = field(default_factory=time.time)
    """Creation timestamp."""
    ts_updated: float = field(default_factory=time.time)
    """Last-updated timestamp."""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _default_db_path() -> Path:
    data_dir = Path(platformdirs.user_data_dir(_APP))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "checkpoint.db"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id    TEXT PRIMARY KEY,
            task_id          TEXT NOT NULL,
            idempotency_key  TEXT NOT NULL,
            status           TEXT NOT NULL,
            payload          TEXT NOT NULL,
            provenance_id    TEXT,
            ts_created       REAL NOT NULL,
            ts_updated       REAL NOT NULL,
            UNIQUE(task_id, idempotency_key)
        )
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# CheckpointStore
# ---------------------------------------------------------------------------


class CheckpointStore:
    """SQLite-backed checkpoint store.

    Parameters
    ----------
    db_path:
        SQLite file path (None → default XDG path).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        primary_path = db_path or _default_db_path()
        self._conn, self._db_path = connect_writable_sqlite(
            primary_path,
            fallback_filename="checkpoint.db",
            ensure_schema=_ensure_schema,
            row_factory=sqlite3.Row,
            allow_fallback=db_path is None,
        )

    # ------------------------------------------------------------------
    # Save & update
    # ------------------------------------------------------------------

    def save(
        self,
        *,
        task_id: str,
        idempotency_key: str,
        status: StepStatus,
        payload: dict[str, Any],
        provenance_id: str | None = None,
    ) -> CheckpointRecord:
        """Save (or update) a step checkpoint.

        If an entry with the same (task_id, idempotency_key) already exists,
        its status and payload are updated.
        """
        now = time.time()
        # Check for an existing record
        cur = self._conn.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE task_id=? AND idempotency_key=?",
            (task_id, idempotency_key),
        )
        row = cur.fetchone()
        if row:
            cp_id = row["checkpoint_id"]
            self._conn.execute(
                """
                UPDATE checkpoints
                SET status=?, payload=?, provenance_id=?, ts_updated=?
                WHERE checkpoint_id=?
                """,
                (status.value, json.dumps(payload), provenance_id, now, cp_id),
            )
            self._conn.commit()
            return self._fetch_by_id(cp_id)
        else:
            cp_id = str(uuid.uuid4())
            self._conn.execute(
                """
                INSERT INTO checkpoints
                (checkpoint_id, task_id, idempotency_key, status, payload,
                 provenance_id, ts_created, ts_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cp_id,
                    task_id,
                    idempotency_key,
                    status.value,
                    json.dumps(payload),
                    provenance_id,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return self._fetch_by_id(cp_id)

    def update_status(self, checkpoint_id: str, status: StepStatus) -> None:
        """Update the status of a checkpoint."""
        self._conn.execute(
            "UPDATE checkpoints SET status=?, ts_updated=? WHERE checkpoint_id=?",
            (status.value, time.time(), checkpoint_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, task_id: str, idempotency_key: str) -> CheckpointRecord | None:
        """Look up a checkpoint by (task_id, idempotency_key)."""
        cur = self._conn.execute(
            "SELECT * FROM checkpoints WHERE task_id=? AND idempotency_key=?",
            (task_id, idempotency_key),
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def get_by_id(self, checkpoint_id: str) -> CheckpointRecord | None:
        """Look up a checkpoint by checkpoint_id."""
        return self._fetch_by_id(checkpoint_id)

    def list_task(self, task_id: str) -> list[CheckpointRecord]:
        """Return all checkpoints for a given task, ordered by creation time."""
        cur = self._conn.execute(
            "SELECT * FROM checkpoints WHERE task_id=? ORDER BY ts_created ASC",
            (task_id,),
        )
        return [self._row_to_record(row) for row in cur.fetchall()]

    def is_done(self, task_id: str, idempotency_key: str) -> bool:
        """Return True if the step is in DONE status — used to skip on resumption."""
        rec = self.get(task_id, idempotency_key)
        return rec is not None and rec.status == StepStatus.DONE

    # ------------------------------------------------------------------
    # Resume support
    # ------------------------------------------------------------------

    def restore(self, task_id: str) -> dict[str, CheckpointRecord]:
        """Return the full step map for task_id.

        Returns
        -------
        dict[idempotency_key, CheckpointRecord]
        """
        return {rec.idempotency_key: rec for rec in self.list_task(task_id)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_by_id(self, checkpoint_id: str) -> CheckpointRecord:
        cur = self._conn.execute(
            "SELECT * FROM checkpoints WHERE checkpoint_id=?",
            (checkpoint_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"checkpoint not found: {checkpoint_id}")
        return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> CheckpointRecord:
        return CheckpointRecord(
            checkpoint_id=row["checkpoint_id"],
            task_id=row["task_id"],
            idempotency_key=row["idempotency_key"],
            status=StepStatus(row["status"]),
            payload=json.loads(row["payload"]),
            provenance_id=row["provenance_id"],
            ts_created=row["ts_created"],
            ts_updated=row["ts_updated"],
        )

    def close(self) -> None:
        """Close the DB connection."""
        self._conn.close()
