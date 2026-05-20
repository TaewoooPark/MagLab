"""Writable runtime storage helpers for global installs.

MagLab is a global command, but some environments make the platform data
directory read-only: sandboxed shells, locked-down lab machines, or read-only
network homes. Runtime SQLite stores should then fall back to the active
workspace under ``.maglab/runtime`` instead of aborting startup.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def workspace_runtime_path(filename: str) -> Path:
    """Return the per-workspace fallback runtime DB path."""
    from maglab.workspace import workspace_info

    runtime_dir = workspace_info().local_state_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir / filename


def connect_writable_sqlite(
    primary_path: Path,
    *,
    fallback_filename: str,
    ensure_schema: Callable[[sqlite3.Connection], None],
    row_factory: Any | None = None,
    allow_fallback: bool = True,
) -> tuple[sqlite3.Connection, Path]:
    """Connect to a writable SQLite DB, falling back to workspace runtime storage.

    Args:
        primary_path: Preferred SQLite file.
        fallback_filename: Filename to use under ``.maglab/runtime``.
        ensure_schema: Function that creates/updates the schema and commits.
        row_factory: Optional SQLite row factory.
        allow_fallback: When false, raise the primary connection error.

    Returns:
        ``(connection, resolved_path)``.
    """
    paths = [primary_path]
    if allow_fallback:
        fallback = workspace_runtime_path(fallback_filename)
        if fallback != primary_path:
            paths.append(fallback)

    last_error: Exception | None = None
    for path in paths:
        conn: sqlite3.Connection | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path))
            if row_factory is not None:
                conn.row_factory = row_factory
            ensure_schema(conn)
            _probe_sqlite_writable(conn)
            return conn, path
        except sqlite3.Error as exc:
            last_error = exc
            if conn is not None:
                conn.close()
            log.debug("SQLite runtime store unavailable at %s: %s", path, exc)
            if not allow_fallback:
                break

    raise RuntimeError(f"No writable SQLite runtime store available: {last_error}") from last_error


def _probe_sqlite_writable(conn: sqlite3.Connection) -> None:
    """Perform a small persistent write to prove the DB is actually writable."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS __maglab_write_probe (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            ts REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO __maglab_write_probe (id, ts)
        VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET ts=excluded.ts
        """,
        (time.time(),),
    )
    conn.commit()
