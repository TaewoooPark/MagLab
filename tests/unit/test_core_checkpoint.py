"""maglab.core.checkpoint unit tests — deterministic, no network/LLM."""

from __future__ import annotations

import threading
import time
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


# ---------------------------------------------------------------------------
# Concurrent resume — the upsert must not race
# ---------------------------------------------------------------------------


def test_concurrent_save_of_same_key_does_not_raise(tmp_path: Path) -> None:
    """Two workers resuming the same step must not trip the UNIQUE constraint.

    Each worker owns its own connection, as two ``maglab`` invocations resuming
    the same task would. A SELECT-then-INSERT pair lets both observe "no row"
    and both INSERT; the loser raises sqlite3.IntegrityError, crashing the very
    loop that idempotency keys exist to make safe.
    """
    db = tmp_path / "ckpt.db"
    n_workers = 4
    errors: list[BaseException] = []
    barrier = threading.Barrier(n_workers)

    def _save(idx: int) -> None:
        try:
            worker_store = CheckpointStore(db_path=db)
            try:
                barrier.wait(timeout=10)
                worker_store.save(
                    task_id="task-race",
                    idempotency_key="step-1",
                    status=StepStatus.DONE,
                    payload={"worker": idx},
                )
            finally:
                worker_store.close()
        except BaseException as exc:  # noqa: BLE001 - recorded and re-asserted below
            errors.append(exc)

    threads = [threading.Thread(target=_save, args=(i,)) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"concurrent save raised: {errors!r}"

    reader = CheckpointStore(db_path=db)
    try:
        rows = reader.list_task("task-race")
        assert len(rows) == 1, "duplicate checkpoints created for one idempotency key"
        assert rows[0].status is StepStatus.DONE
    finally:
        reader.close()


def test_repeated_save_preserves_identity_and_creation_time(store: CheckpointStore) -> None:
    """An upsert must behave like the previous UPDATE: same id, original ts_created."""
    first = store.save(
        task_id="task-2",
        idempotency_key="step-1",
        status=StepStatus.RUNNING,
        payload={"n": 1},
    )
    time.sleep(0.01)
    second = store.save(
        task_id="task-2",
        idempotency_key="step-1",
        status=StepStatus.DONE,
        payload={"n": 2},
        provenance_id="prov-9",
    )

    assert second.checkpoint_id == first.checkpoint_id, "upsert must not mint a new id"
    assert second.ts_created == first.ts_created, "ts_created must survive the update"
    assert second.ts_updated >= first.ts_updated
    assert second.status is StepStatus.DONE
    assert second.payload == {"n": 2}
    assert second.provenance_id == "prov-9"
    assert len(store.list_task("task-2")) == 1
