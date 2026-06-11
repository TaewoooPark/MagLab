"""CLI tests for report/prov/task project surface."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from maglab.cli import app
from maglab.core.checkpoint import CheckpointStore, StepStatus
from tests.harness.cli_runner import isolated_filesystem

runner = CliRunner()


def test_report_inventory_command_lists_existing_artifact() -> None:
    with isolated_filesystem(runner):
        out = Path("maglab_write/prl")
        out.mkdir(parents=True)
        (out / "main.tex").write_text("article", encoding="utf-8")

        result = runner.invoke(app, ["report", "inventory", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifacts"][0]["path"] == "maglab_write/prl/main.tex"
    assert payload["artifacts"][0]["kind"] == "manuscript"


def test_prov_summary_command_lists_sidecar() -> None:
    with isolated_filesystem(runner):
        Path("fit_provenance.json").write_text('[{"id": "dp-1"}]', encoding="utf-8")

        result = runner.invoke(app, ["prov", "summary", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sidecars"][0]["path"] == "fit_provenance.json"
    assert payload["sidecars"][0]["kind"] == "provenance-json"


def test_prov_lineage_reads_store(tmp_path: Path) -> None:
    from maglab.provenance.datapoint import DataPoint, ProvenanceType
    from maglab.provenance.ledger import ProvenanceLedger
    from maglab.provenance.store import ProvenanceStore

    db = tmp_path / "prov.db"
    ledger = ProvenanceLedger(ProvenanceStore(db))
    parent = DataPoint(value=[1.0, 2.0], units="A/m", provenance_type=ProvenanceType.MEASURED)
    ledger.record_datapoint(parent, activity_description="load")
    child = DataPoint(value=0.12, units="1", provenance_type=ProvenanceType.FITTED)
    child_id = ledger.record_datapoint(
        child, derived_from_ids=[parent.id], activity_description="fit"
    )

    result = runner.invoke(app, ["prov", "lineage", child_id, "--db", str(db), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["datapoint_id"] == child_id
    kinds = {rec["kind"] for rec in payload["lineage"]}
    assert "entity" in kinds and "relation" in kinds


def test_prov_lineage_without_db_errors() -> None:
    result = runner.invoke(app, ["prov", "lineage", "some-id"])
    assert result.exit_code == 2
    assert "PROV store is required" in result.output


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
    with isolated_filesystem(runner):
        result = runner.invoke(
            app,
            ["task", "scaffold", "Analyze spin Hall angle", "--id", "spin-hall", "--json"],
        )
        path = Path(".maglab/tasks/spin-hall.md")
        exists = path.is_file()

    assert result.exit_code == 0, result.output
    assert exists


def test_skill_create_command_writes_workspace_skill() -> None:
    with isolated_filesystem(runner):
        result = runner.invoke(
            app,
            ["skill", "create", "Spin Hall Skill", "--description", "Spin Hall workflow."],
        )
        path = Path(".maglab/skills/spin-hall-skill/SKILL.md")
        exists = path.is_file()

    assert result.exit_code == 0, result.output
    assert exists


def test_workspace_tree_summary_deduplicates_high_signal_paths() -> None:
    with isolated_filesystem(runner):
        Path("MAGLAB.md").write_text("# Project\n", encoding="utf-8")
        Path("README.md").write_text("# Demo\n", encoding="utf-8")
        Path("pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
        Path("plan").mkdir()
        Path("src").mkdir()
        Path("src/run.py").write_text("print('ok')\n", encoding="utf-8")
        Path(".maglab").mkdir()
        Path(".maglab/runtime.db").write_text("hidden\n", encoding="utf-8")

        result = runner.invoke(
            app,
            ["workspace", "tree", "--summary", "--max-depth", "2", "--max", "20"],
        )

    assert result.exit_code == 0, result.output
    assert result.output.count("README.md") == 1
    assert result.output.count("pyproject.toml") == 1
    assert "Additional visible entries" in result.output
    assert "src/run.py" in result.output
    assert ".maglab" not in result.output


def test_figure_primitive_ingest_command_writes_catalog_package() -> None:
    with isolated_filesystem(runner):
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
