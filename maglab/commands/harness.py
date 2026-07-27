"""`maglab harness` — manifest-driven workflow planning and execution (§5.16, §14.7).

The read-only commands (`doctor`, `compile`, `run --dry-run`, `worker`,
`pi-tool`) are fully deterministic: they render from
:mod:`maglab.harness.plan` without contacting a provider, so their output is
reproducible and safe to run anywhere.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from maglab.harness.plan import HarnessPlanError
from maglab.ui.json_output import emit_json

console = Console()

harness_app = typer.Typer(
    name="harness",
    help="[P6] Manifest-driven agent workflows — readiness, compilation, planning, execution.",
    no_args_is_help=True,
)


def register(app: typer.Typer) -> None:
    """Attach the harness command group to the root Typer app."""
    app.add_typer(harness_app)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@harness_app.command("doctor")
def harness_doctor(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Report what would stop a harness workflow from running right now."""
    from maglab.harness.doctor import run_doctor

    report = run_doctor()
    if json_output:
        emit_json(report.to_dict())
        raise typer.Exit(0 if report.ok else 1)

    table = Table(title="MagLab harness readiness", show_lines=False)
    table.add_column("Check", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Detail")
    for check in report.checks:
        if check.ok:
            status = "[green]ok[/]"
        elif check.blocking:
            status = "[red]fail[/]"
        else:
            status = "[yellow]warn[/]"
        table.add_row(check.name, status, escape(check.detail))
    console.print(table)

    if report.ok:
        console.print("[green]✓[/] Harness is ready. Try `maglab harness run survey --dry-run`.")
    else:
        blocking = [c for c in report.failures if c.blocking]
        console.print(f"[red]✗[/] {len(blocking)} blocking issue(s) — see the Detail column.")
    raise typer.Exit(0 if report.ok else 1)


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------


@harness_app.command("compile")
def harness_compile(
    workflow: Annotated[
        str | None,
        typer.Argument(help="Workflow to compile (default: every declared workflow)."),
    ] = None,
    write: Annotated[
        bool, typer.Option("--write", help="Write the artifacts to .pi/workflows/.")
    ] = False,
    check: Annotated[
        bool, typer.Option("--check", help="Fail if a committed artifact has drifted.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Compile manifest workflows into .pi/workflows/*.json drift artifacts.

    With neither --write nor --check, the compiled document is printed.
    """
    from maglab.harness.compile import (
        check_artifacts,
        compile_workflow,
        render,
        workflow_targets,
        write_artifacts,
    )

    try:
        if check:
            drift = check_artifacts(workflow)
            if json_output:
                emit_json({"ok": all(d.ok for d in drift), "results": [d.to_dict() for d in drift]})
                raise typer.Exit(0 if all(d.ok for d in drift) else 1)
            table = Table(title="Workflow artifact drift", show_lines=False)
            table.add_column("Workflow", style="cyan")
            table.add_column("Status", justify="center")
            table.add_column("Path")
            for entry in drift:
                colour = "green" if entry.ok else "red"
                table.add_row(entry.workflow, f"[{colour}]{entry.status}[/]", escape(entry.path))
            console.print(table)
            stale = [d for d in drift if not d.ok]
            if stale:
                console.print(
                    f"[red]✗[/] {len(stale)} artifact(s) out of date — "
                    "run `maglab harness compile --write`."
                )
            else:
                console.print("[green]✓[/] All workflow artifacts match the manifest.")
            raise typer.Exit(0 if not stale else 1)

        if write:
            paths = write_artifacts(workflow)
            if json_output:
                emit_json({"ok": True, "written": [str(p) for p in paths]})
                return
            for path in paths:
                console.print(f"[green]✓[/] {escape(str(path))}")
            console.print(f"[dim]{len(paths)} workflow artifact(s) written.[/]")
            return

        targets = workflow_targets(workflow)
        documents = [compile_workflow(name) for name in targets]
        if json_output:
            emit_json(documents[0] if len(documents) == 1 else documents)
            return
        for document in documents:
            console.print(escape(render(document)))
    except HarnessPlanError as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        raise typer.Exit(1) from exc
