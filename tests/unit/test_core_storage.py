"""Runtime storage fallback tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from maglab.core.budget import BudgetTracker
from maglab.core.checkpoint import CheckpointStore, StepStatus
from maglab.core.memory import SessionMemory
from maglab.core.storage import connect_writable_sqlite


def _ensure_probe_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS probe (id TEXT PRIMARY KEY)")
    conn.commit()


def test_connect_writable_sqlite_falls_back_to_workspace_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bad_primary = tmp_path / "primary-is-directory"
    bad_primary.mkdir()

    conn, path = connect_writable_sqlite(
        bad_primary,
        fallback_filename="probe.db",
        ensure_schema=_ensure_probe_schema,
    )
    try:
        assert path == tmp_path / ".maglab" / "runtime" / "probe.db"
        conn.execute("INSERT INTO probe (id) VALUES ('ok')")
        conn.commit()
    finally:
        conn.close()


def test_session_memory_uses_workspace_runtime_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bad_primary = tmp_path / "readonly-sessions"
    bad_primary.mkdir()
    monkeypatch.setattr("maglab.core.memory._sessions_db_path", lambda: bad_primary)

    memory = SessionMemory(session_id="fallback-session")
    try:
        memory.set("status", "ok")
        assert memory.get("status") == "ok"
        assert memory._db_path == tmp_path / ".maglab" / "runtime" / "sessions.db"
    finally:
        memory.close()


def test_budget_tracker_uses_workspace_runtime_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bad_primary = tmp_path / "readonly-budget"
    bad_primary.mkdir()
    monkeypatch.setattr("maglab.core.budget._default_db_path", lambda: bad_primary)

    tracker = BudgetTracker(session_id="fallback-budget")
    try:
        tracker.record_tool(label="workspace_tree", wall_time=0.01)
        assert tracker.session_summary().tool_calls == 1
        assert tracker._db_path == tmp_path / ".maglab" / "runtime" / "budget.db"
    finally:
        tracker.close()


def test_checkpoint_store_uses_workspace_runtime_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bad_primary = tmp_path / "readonly-checkpoint"
    bad_primary.mkdir()
    monkeypatch.setattr("maglab.core.checkpoint._default_db_path", lambda: bad_primary)

    store = CheckpointStore()
    try:
        store.save(task_id="task", idempotency_key="step", status=StepStatus.DONE, payload={})
        assert store.is_done("task", "step") is True
        assert store._db_path == tmp_path / ".maglab" / "runtime" / "checkpoint.db"
    finally:
        store.close()
