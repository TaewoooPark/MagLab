"""P0 project command surface: report, provenance, and task status."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from maglab.project_status import (
    artifact_records_to_dicts,
    discover_provenance_artifacts,
    discover_report_artifacts,
    list_checkpoint_tasks,
    summarize_provenance_db,
    summarize_task_checkpoints,
    task_scaffold_inventory,
    write_task_scaffold,
)

console = Console()

report_app = typer.Typer(
    name="report",
    help="Inspect generated report, manuscript, slide, and poster artifacts.",
    invoke_without_command=True,
)
prov_app = typer.Typer(
    name="prov",
    help="Inspect provenance sidecars and W3C PROV stores.",
    invoke_without_command=True,
)
task_app = typer.Typer(
    name="task",
    help="Inspect checkpointed research tasks and create task scaffolds.",
    invoke_without_command=True,
)


def register(app: typer.Typer) -> None:
    """Attach project-surface commands to the root Typer app."""
    app.add_typer(report_app)
    app.add_typer(prov_app)
    app.add_typer(task_app)


@report_app.callback(invoke_without_command=True)
def report_callback(ctx: typer.Context) -> None:
    """Show report inventory by default."""
    if ctx.invoked_subcommand is not None:
        return
    report_inventory()


@report_app.command("inventory")
def report_inventory(
    root: Annotated[
        Path,
        typer.Option("--root", "-r", help="Workspace root to inspect."),
    ] = Path("."),
    max_entries: Annotated[
        int,
        typer.Option("--max", "-n", min=1, help="Maximum artifacts to show."),
    ] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List existing report/manuscript/presentation artifacts."""
    records = discover_report_artifacts(root, max_entries=max_entries)
    if json_output:
        _print_json({"root": str(root), "artifacts": artifact_records_to_dicts(records)})
        return
    _print_artifact_table("MagLab report inventory", records)
    if not records:
        console.print("[dim]No generated report artifacts found in known MagLab output dirs.[/]")


@prov_app.callback(invoke_without_command=True)
def prov_callback(ctx: typer.Context) -> None:
    """Show provenance summary by default."""
    if ctx.invoked_subcommand is not None:
        return
    prov_summary()


@prov_app.command("summary")
def prov_summary(
    root: Annotated[
        Path,
        typer.Option("--root", "-r", help="Workspace root to inspect for provenance sidecars."),
    ] = Path("."),
    db_path: Annotated[
        Path | None,
        typer.Option("--db", help="Optional W3C PROV SQLite store path to summarize."),
    ] = None,
    max_entries: Annotated[
        int,
        typer.Option("--max", "-n", min=1, help="Maximum sidecars to show."),
    ] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Summarize real provenance artifacts already present on disk."""
    sidecars = discover_provenance_artifacts(root, max_entries=max_entries)
    db_summary = summarize_provenance_db(db_path) if db_path else None
    if json_output:
        _print_json(
            {
                "root": str(root),
                "sidecars": artifact_records_to_dicts(sidecars),
                "db": db_summary,
            }
        )
        return

    _print_artifact_table("MagLab provenance sidecars", sidecars)
    if not sidecars:
        console.print("[dim]No provenance sidecars found in this workspace.[/]")
    if db_summary:
        table = Table(title="W3C PROV store")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("db_path", escape(str(db_summary["db_path"])))
        table.add_row("exists", str(db_summary["exists"]))
        table.add_row("records", str(db_summary["records"]))
        table.add_row("by_kind", json.dumps(db_summary["by_kind"], sort_keys=True))
        if "error" in db_summary:
            table.add_row("error", escape(str(db_summary["error"])))
        console.print(table)


@prov_app.command("status")
def prov_status(
    root: Annotated[
        Path,
        typer.Option("--root", "-r", help="Workspace root to inspect for provenance sidecars."),
    ] = Path("."),
    db_path: Annotated[
        Path | None,
        typer.Option("--db", help="Optional W3C PROV SQLite store path to summarize."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Alias for ``prov summary``."""
    prov_summary(root=root, db_path=db_path, json_output=json_output)


@prov_app.command("lineage")
def prov_lineage(
    datapoint_id: Annotated[
        str,
        typer.Argument(help="DataPoint ID (local name) to trace lineage for."),
    ],
    db_path: Annotated[
        Path | None,
        typer.Option("--db", help="W3C PROV SQLite store path holding the lineage."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Show the W3C PROV lineage of a DataPoint (generation, derivation, attribution)."""
    if db_path is None:
        console.print(
            "[red]A PROV store is required.[/] Pass [bold]--db <path>[/] to the SQLite "
            "store (inspect one with `maglab prov summary --db <path>`)."
        )
        raise typer.Exit(2)
    if not db_path.exists():
        console.print(f"[red]PROV store not found:[/] {escape(str(db_path))}")
        raise typer.Exit(1)

    from maglab.provenance.store import ProvenanceStore

    try:
        records = ProvenanceStore(db_path).get_entity_lineage(datapoint_id)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not read lineage:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    if json_output:
        _print_json({"datapoint_id": datapoint_id, "db": str(db_path), "lineage": records})
        return

    if not records:
        console.print(
            f"[dim]No lineage records found for DataPoint {datapoint_id!r} in "
            f"{escape(str(db_path))}.[/]"
        )
        return

    table = Table(title=f"PROV lineage — {escape(datapoint_id)}")
    table.add_column("Record ID", style="cyan")
    table.add_column("Kind")
    table.add_column("Created")
    for rec in records:
        table.add_row(
            escape(str(rec.get("id", ""))),
            escape(str(rec.get("kind", ""))),
            escape(str(rec.get("created_at", ""))),
        )
    console.print(table)


@task_app.callback(invoke_without_command=True)
def task_callback(ctx: typer.Context) -> None:
    """List task scaffolds and checkpointed tasks by default."""
    if ctx.invoked_subcommand is not None:
        return
    task_list()


@task_app.command("list")
def task_list(
    root: Annotated[
        Path,
        typer.Option("--root", "-r", help="Workspace root to inspect for task scaffolds."),
    ] = Path("."),
    db_path: Annotated[
        Path | None,
        typer.Option("--db", help="Optional checkpoint SQLite DB path."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List task scaffold files and checkpoint task IDs."""
    scaffolds = task_scaffold_inventory(root)
    checkpoint_tasks = list_checkpoint_tasks(db_path)
    if json_output:
        _print_json(
            {
                "root": str(root),
                "scaffolds": artifact_records_to_dicts(scaffolds),
                "checkpoint_tasks": checkpoint_tasks,
            }
        )
        return

    _print_artifact_table("MagLab task scaffolds", scaffolds)
    if not scaffolds:
        console.print("[dim]No .maglab/tasks scaffolds found.[/]")

    table = Table(title="Checkpoint tasks")
    table.add_column("Task ID", style="cyan")
    table.add_column("Checkpoints", justify="right")
    table.add_column("Last updated")
    for item in checkpoint_tasks:
        table.add_row(
            escape(str(item["task_id"])),
            str(item["checkpoint_count"]),
            str(item["last_updated"]),
        )
    console.print(table)
    if not checkpoint_tasks:
        console.print("[dim]No checkpointed tasks found.[/]")


@task_app.command("status")
def task_status(
    task_id: Annotated[str, typer.Argument(help="Research-loop task ID.")],
    db_path: Annotated[
        Path | None,
        typer.Option("--db", help="Optional checkpoint SQLite DB path."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Show persisted checkpoint status for one task ID."""
    summary = summarize_task_checkpoints(task_id, db_path=db_path)
    if json_output:
        _print_json(
            {
                "task_id": summary.task_id,
                "checkpoint_count": summary.checkpoint_count,
                "by_status": summary.by_status,
                "last_updated": summary.last_updated,
                "provenance_ids": summary.provenance_ids,
                "checkpoints": summary.checkpoints,
            }
        )
        return

    table = Table(title=f"Task status: {task_id}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("checkpoints", str(summary.checkpoint_count))
    table.add_row("last_updated", str(summary.last_updated or "(none)"))
    table.add_row("provenance_ids", "\n".join(summary.provenance_ids) or "(none)")
    table.add_row(
        "by_status",
        ", ".join(f"{status}={count}" for status, count in summary.by_status.items()),
    )
    console.print(table)
    if summary.checkpoints:
        cp_table = Table(title="Checkpoints")
        cp_table.add_column("Step", style="cyan")
        cp_table.add_column("Status")
        cp_table.add_column("Provenance")
        cp_table.add_column("Updated")
        for checkpoint in summary.checkpoints:
            cp_table.add_row(
                escape(str(checkpoint["idempotency_key"])),
                escape(str(checkpoint["status"])),
                escape(str(checkpoint["provenance_id"] or "")),
                escape(str(checkpoint["updated"])),
            )
        console.print(cp_table)


@task_app.command("scaffold")
def task_scaffold(
    goal: Annotated[str, typer.Argument(help="Task goal or research objective.")],
    root: Annotated[
        Path,
        typer.Option("--root", "-r", help="Workspace root where .maglab/tasks is created."),
    ] = Path("."),
    task_id: Annotated[
        str | None,
        typer.Option("--id", help="Optional stable task ID for the scaffold."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Create a markdown task scaffold in the active workspace."""
    path = write_task_scaffold(goal, root=root, task_id=task_id)
    payload = {"path": str(path), "task_id": task_id, "goal": goal}
    if json_output:
        _print_json(payload)
        return
    console.print(f"[green]Task scaffold ready:[/] [bold]{escape(str(path))}[/]")


def _print_artifact_table(title: str, records: list[Any]) -> None:
    table = Table(title=title)
    table.add_column("Kind", style="cyan")
    table.add_column("Path")
    table.add_column("Bytes", justify="right")
    table.add_column("Modified")
    table.add_column("Detail")
    for record in records:
        table.add_row(
            escape(record.kind),
            escape(record.path),
            str(record.bytes),
            escape(record.modified),
            escape(record.detail),
        )
    console.print(table)


def _print_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
