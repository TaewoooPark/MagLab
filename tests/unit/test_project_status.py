"""Tests for project report/provenance/task status helpers."""

from __future__ import annotations

import json
from pathlib import Path

from maglab.core.checkpoint import CheckpointStore, StepStatus
from maglab.project_status import (
    discover_provenance_artifacts,
    discover_report_artifacts,
    list_checkpoint_tasks,
    summarize_provenance_db,
    summarize_task_checkpoints,
    task_scaffold_inventory,
    write_task_scaffold,
)
from maglab.provenance.store import ProvenanceStore


def test_report_inventory_finds_known_output_dirs(tmp_path: Path) -> None:
    out = tmp_path / "maglab_write" / "prl"
    out.mkdir(parents=True)
    (out / "main.tex").write_text("\\documentclass{revtex4-2}\n", encoding="utf-8")

    records = discover_report_artifacts(tmp_path)

    assert len(records) == 1
    assert records[0].path == "maglab_write/prl/main.tex"
    assert records[0].kind == "manuscript"


def test_provenance_inventory_and_db_summary(tmp_path: Path) -> None:
    sidecar = tmp_path / "sample_fit_provenance.json"
    sidecar.write_text(json.dumps([{"id": "dp-1"}]), encoding="utf-8")
    db = tmp_path / "prov.sqlite"
    store = ProvenanceStore(db)
    store.add_entity("dp-1", attributes={"provenance_type": "MEASURED", "units": "T"})
    store.close()

    records = discover_provenance_artifacts(tmp_path)
    summary = summarize_provenance_db(db)

    assert records[0].path == "sample_fit_provenance.json"
    assert records[0].detail == "1 json records"
    assert summary["exists"] is True
    assert summary["records"] >= 1
    assert summary["by_kind"]["entity"] == 1


def test_task_checkpoint_summary_and_scaffold(tmp_path: Path) -> None:
    db = tmp_path / "checkpoint.db"
    store = CheckpointStore(db_path=db)
    store.save(
        task_id="task-1",
        idempotency_key="load-data",
        status=StepStatus.DONE,
        payload={"path": "data.csv"},
        provenance_id="prov:dp-1",
    )
    store.save(
        task_id="task-1",
        idempotency_key="fit",
        status=StepStatus.RUNNING,
        payload={},
    )
    store.close()

    tasks = list_checkpoint_tasks(db)
    summary = summarize_task_checkpoints("task-1", db_path=db)
    scaffold = write_task_scaffold("Fit ST-FMR linewidth", root=tmp_path, task_id="task-1")
    inventory = task_scaffold_inventory(tmp_path)

    assert tasks[0]["task_id"] == "task-1"
    assert summary.checkpoint_count == 2
    assert summary.by_status["done"] == 1
    assert summary.by_status["running"] == 1
    assert summary.provenance_ids == ["prov:dp-1"]
    assert scaffold.name == "task-1.md"
    assert inventory[0].kind == "task-scaffold"
