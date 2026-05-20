"""maglab.core.checkpoint unit tests — deterministic, no network/LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.core.checkpoint import CheckpointRecord, CheckpointStore, StepStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> CheckpointStore:
    s = CheckpointStore(db_path=tmp_path / "ckpt.db")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Basic save and retrieval
# ---------------------------------------------------------------------------


def test_save_and_get(store: CheckpointStore) -> None:
    rec = store.save(
        task_id="task-1",
        idempotency_key="step-a",
        status=StepStatus.DONE,
        payload={"result": 42},
    )
    assert isinstance(rec, CheckpointRecord)
    assert rec.task_id == "task-1"
    assert rec.idempotency_key == "step-a"
    assert rec.status == StepStatus.DONE
    assert rec.payload == {"result": 42}

    fetched = store.get("task-1", "step-a")
    assert fetched is not None
    assert fetched.checkpoint_id == rec.checkpoint_id
    assert fetched.payload == {"result": 42}


def test_get_nonexistent_returns_none(store: CheckpointStore) -> None:
    result = store.get("no-task", "no-step")
    assert result is None


def test_get_by_id(store: CheckpointStore) -> None:
    rec = store.save(task_id="t", idempotency_key="k", status=StepStatus.PENDING, payload={})
    fetched = store.get_by_id(rec.checkpoint_id)
    assert fetched is not None
    assert fetched.checkpoint_id == rec.checkpoint_id


# ---------------------------------------------------------------------------
# Idempotency — update on same key
# ---------------------------------------------------------------------------


def test_idempotent_save_updates_status(store: CheckpointStore) -> None:
    store.save(task_id="t", idempotency_key="k", status=StepStatus.RUNNING, payload={})
    updated = store.save(task_id="t", idempotency_key="k", status=StepStatus.DONE, payload={"x": 1})
    assert updated.status == StepStatus.DONE
    assert updated.payload == {"x": 1}
    # only one record should exist in the DB
    records = store.list_task("t")
    assert len(records) == 1


# ---------------------------------------------------------------------------
# is_done
# ---------------------------------------------------------------------------


def test_is_done_true_when_done(store: CheckpointStore) -> None:
    store.save(task_id="t", idempotency_key="k", status=StepStatus.DONE, payload={})
    assert store.is_done("t", "k") is True


def test_is_done_false_when_running(store: CheckpointStore) -> None:
    store.save(task_id="t", idempotency_key="k", status=StepStatus.RUNNING, payload={})
    assert store.is_done("t", "k") is False


def test_is_done_false_when_not_exists(store: CheckpointStore) -> None:
    assert store.is_done("t", "missing") is False


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


def test_update_status(store: CheckpointStore) -> None:
    rec = store.save(task_id="t", idempotency_key="k", status=StepStatus.PENDING, payload={})
    store.update_status(rec.checkpoint_id, StepStatus.DONE)
    fetched = store.get("t", "k")
    assert fetched is not None
    assert fetched.status == StepStatus.DONE


# ---------------------------------------------------------------------------
# list_task
# ---------------------------------------------------------------------------


def test_list_task_returns_all_steps(store: CheckpointStore) -> None:
    for i in range(3):
        store.save(
            task_id="big-task", idempotency_key=f"step-{i}", status=StepStatus.DONE, payload={}
        )
    records = store.list_task("big-task")
    assert len(records) == 3
    keys = {r.idempotency_key for r in records}
    assert keys == {"step-0", "step-1", "step-2"}


def test_list_task_empty_for_unknown_task(store: CheckpointStore) -> None:
    assert store.list_task("ghost") == []


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


def test_restore_returns_keyed_map(store: CheckpointStore) -> None:
    store.save(task_id="rt", idempotency_key="alpha", status=StepStatus.DONE, payload={"v": 1})
    store.save(task_id="rt", idempotency_key="beta", status=StepStatus.FAILED, payload={"v": 2})
    restored = store.restore("rt")
    assert "alpha" in restored
    assert "beta" in restored
    assert restored["alpha"].status == StepStatus.DONE
    assert restored["beta"].status == StepStatus.FAILED


# ---------------------------------------------------------------------------
# provenance_id association
# ---------------------------------------------------------------------------


def test_provenance_id_stored(store: CheckpointStore) -> None:
    store.save(
        task_id="t",
        idempotency_key="k",
        status=StepStatus.DONE,
        payload={},
        provenance_id="prov:abc123",
    )
    fetched = store.get("t", "k")
    assert fetched is not None
    assert fetched.provenance_id == "prov:abc123"


# ---------------------------------------------------------------------------
# Restart simulation — restore via new connection
# ---------------------------------------------------------------------------


def test_restore_after_reconnect(tmp_path: Path) -> None:
    db = tmp_path / "ckpt2.db"
    s1 = CheckpointStore(db_path=db)
    s1.save(
        task_id="run-99", idempotency_key="fit-step", status=StepStatus.DONE, payload={"lr": 0.01}
    )
    s1.close()

    s2 = CheckpointStore(db_path=db)
    restored = s2.restore("run-99")
    assert "fit-step" in restored
    assert restored["fit-step"].payload == {"lr": 0.01}
    s2.close()


# ---------------------------------------------------------------------------
# StepStatus enum
# ---------------------------------------------------------------------------


def test_step_status_values() -> None:
    assert StepStatus.PENDING.value == "pending"
    assert StepStatus.RUNNING.value == "running"
    assert StepStatus.DONE.value == "done"
    assert StepStatus.FAILED.value == "failed"
    assert StepStatus.SKIPPED.value == "skipped"
