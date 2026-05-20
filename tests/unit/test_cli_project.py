"""CLI tests for report/prov/task project surface."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from maglab.cli import app
from maglab.core.checkpoint import CheckpointStore, StepStatus

runner = CliRunner()


def test_report_inventory_command_lists_existing_artifact() -> None:
    with runner.isolated_filesystem():
        out = Path("maglab_write/prl")
        out.mkdir(parents=True)
        (out / "main.tex").write_text("article", encoding="utf-8")

        result = runner.invoke(app, ["report", "inventory", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifacts"][0]["path"] == "maglab_write/prl/main.tex"
    assert payload["artifacts"][0]["kind"] == "manuscript"


def test_prov_summary_command_lists_sidecar() -> None:
    with runner.isolated_filesystem():
        Path("fit_provenance.json").write_text('[{"id": "dp-1"}]', encoding="utf-8")

        result = runner.invoke(app, ["prov", "summary", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sidecars"][0]["path"] == "fit_provenance.json"
    assert payload["sidecars"][0]["kind"] == "provenance-json"


def test_task_status_command_reads_checkpoint_db(tmp_path: Path) -> None:
    db = tmp_path / "checkpoint.db"
    store = CheckpointStore(db_path=db)
    store.save(
        task_id="task-42",
        idempotency_key="simulate",
        status=StepStatus.DONE,
        payload={},
        provenance_id="prov:sim-1",
    )
    store.close()

    result = runner.invoke(app, ["task", "status", "task-42", "--db", str(db), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["checkpoint_count"] == 1
    assert payload["by_status"]["done"] == 1
    assert payload["provenance_ids"] == ["prov:sim-1"]


def test_task_scaffold_command_writes_markdown() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["task", "scaffold", "Analyze spin Hall angle", "--id", "spin-hall", "--json"],
        )
        path = Path(".maglab/tasks/spin-hall.md")
        exists = path.is_file()

    assert result.exit_code == 0, result.output
    assert exists


def test_skill_create_command_writes_workspace_skill() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["skill", "create", "Spin Hall Skill", "--description", "Spin Hall workflow."],
        )
        path = Path(".maglab/skills/spin-hall-skill/SKILL.md")
        exists = path.is_file()

    assert result.exit_code == 0, result.output
    assert exists


def test_figure_primitive_ingest_command_writes_catalog_package() -> None:
    with runner.isolated_filesystem():
        source = Path("hall.svg")
        source.write_text(
            '<svg width="20" height="10" xmlns="http://www.w3.org/2000/svg"></svg>',
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            [
                "figure",
                "primitives",
                "ingest",
                str(source),
                "--description",
                "Hall bar primitive.",
                "--tag",
                "hall",
                "--json",
            ],
        )
        package_exists = Path(".maglab/figure/primitives/catalog/hall/primitive.json").is_file()

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["name"] == "hall"
    assert package_exists
