"""`maglab harness` — manifest-driven workflow planning and execution (§5.16, §14.7).

The read-only commands (`doctor`, `compile`, `run --dry-run`, `worker`,
`pi-tool`) are fully deterministic: they render from
:mod:`maglab.harness.plan` without contacting a provider, so their output is
reproducible and safe to run anywhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

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


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_worker_row(table: Table, index: int | None, step: Any) -> None:
    """Add one worker step to a plan table."""
    skills = ", ".join(step.skills_found) or "—"
    if step.skills_missing:
        skills += f" [red](missing: {', '.join(step.skills_missing)})[/]"
    mcp = ", ".join(step.mcp_registered) or "—"
    if step.mcp_unregistered:
        mcp += f" [red](unregistered: {', '.join(step.mcp_unregistered)})[/]"
    table.add_row(
        "" if index is None else str(index),
        escape(step.agent),
        f"{escape(step.model)} → {escape(step.resolved_model or 'inherit')}",
        str(step.max_turns),
        escape(", ".join(step.tools)) or "—",
        skills,
        mcp,
    )


def _plan_table(plan: Any) -> Table:
    table = Table(title=f"{plan.name} — {len(plan.steps)} step(s)", show_lines=False)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Agent", style="cyan")
    table.add_column("Model")
    table.add_column("Turns", justify="right")
    table.add_column("Tools")
    table.add_column("Skills")
    table.add_column("MCP")
    for i, step in enumerate(plan.steps, start=1):
        _render_worker_row(table, i, step)
    return table


def _print_blockers(blockers: list[str], warnings: list[str] | None = None) -> None:
    """Report hard blockers and soft warnings as the distinct things they are."""
    if blockers:
        console.print(f"[red]Not ready — {len(blockers)} blocker(s):[/]")
        for blocker in blockers:
            console.print(f"  [red]•[/] {escape(blocker)}")
    for warning in warnings or []:
        console.print(f"  [yellow]![/] {escape(warning)}")
    if blockers or warnings:
        console.print("[dim]Run `maglab harness doctor` for the full readiness report.[/]")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@harness_app.command("run")
def harness_run(
    workflow: Annotated[str, typer.Argument(help="Workflow name or alias.")],
    topic: Annotated[
        str, typer.Option("--topic", help="Research topic the workflow acts on.")
    ] = "",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the execution plan without running it.")
    ] = False,
    execute_local: Annotated[
        bool,
        typer.Option("--execute-local", help="Run the workflow locally, step by step, without PI."),
    ] = False,
    execute_pi: Annotated[
        bool, typer.Option("--execute-pi", help="Run the generated PI handoff (requires PI).")
    ] = False,
    pi_handoff: Annotated[
        bool, typer.Option("--pi-handoff", help="Also emit the concrete PI handoff command.")
    ] = False,
    local_max_steps: Annotated[
        int | None,
        typer.Option(
            "--local-max-steps",
            min=1,
            help=(
                "Stop local execution after N steps. MagLab's subagent runner issues one "
                "completion per step, so this caps steps rather than turns within a step."
            ),
        ),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="Output format: text or json.")] = "json",
    record_provenance: Annotated[
        bool, typer.Option("--record-provenance", help="Record the prepared run as W3C PROV.")
    ] = False,
    provenance_db: Annotated[
        Path | None, typer.Option("--provenance-db", help="PROV store path.")
    ] = None,
    pi_flow_id: Annotated[
        str, typer.Option("--pi-flow-id", help="PI flow id to cross-link in the result.")
    ] = "",
) -> None:
    """Plan — and optionally run — a manifest workflow.

    Without --execute-local or --execute-pi this is a dry run: nothing executes
    and no provider is contacted.
    """
    from maglab.harness.plan import build_workflow_plan

    if execute_local and execute_pi:
        console.print("[red]Choose one execution path:[/] --execute-local or --execute-pi.")
        raise typer.Exit(2)

    try:
        plan = build_workflow_plan(workflow, topic=topic)
    except HarnessPlanError as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        raise typer.Exit(1) from exc

    as_json = output.strip().lower() != "text"
    payload: dict[str, Any] = plan.to_dict()
    payload["mode"] = (
        "execute-local" if execute_local else "execute-pi" if execute_pi else "dry-run"
    )
    cross_links: dict[str, Any] = {"pi_flow_id": pi_flow_id or None, "provenance_activity": None}

    # PI handoff — generated on request, and always when handing off to PI.
    if pi_handoff or execute_pi:
        from maglab.harness.pi import build_handoff

        handoff = build_handoff(plan)
        payload["pi_handoff"] = handoff.to_dict()

    # Provenance is recorded for the *prepared* run, before anything executes,
    # so an interrupted execution still leaves a record of what was attempted.
    if record_provenance:
        from maglab.harness.record import record_run

        activity = record_run(plan, db_path=provenance_db, pi_flow_id=pi_flow_id)
        cross_links["provenance_activity"] = activity

    if execute_local:
        if not plan.ready:
            _print_blockers(plan.blockers, plan.warnings)
            console.print("[red]Refusing to execute a plan with unresolved blockers.[/]")
            raise typer.Exit(1)
        from maglab.harness.local import execute_locally

        result = execute_locally(plan, max_steps=local_max_steps)
        payload["execution"] = result
    elif execute_pi:
        from maglab.harness.pi import PiUnavailableError, build_handoff, execute_handoff

        try:
            payload["execution"] = execute_handoff(build_handoff(plan))
        except PiUnavailableError as exc:
            console.print(f"[red]PI handoff unavailable:[/] {escape(str(exc))}")
            console.print(
                "[dim]The handoff command is still in the --pi-handoff output; "
                "use --execute-local to run without PI.[/]"
            )
            raise typer.Exit(1) from exc

    payload["cross_links"] = cross_links

    if as_json:
        emit_json(payload)
        return

    if plan.description:
        console.print(f"[dim]{escape(plan.description)}[/]")
    console.print(_plan_table(plan))
    _print_blockers(plan.blockers, plan.warnings)
    if "pi_handoff" in payload:
        from maglab.harness.pi import build_handoff

        console.print("\n[bold]PI handoff[/]")
        console.print(f"  [dim]{escape(build_handoff(plan).shell_command()[:400])}[/]")
    execution = payload.get("execution")
    if isinstance(execution, dict) and "steps" in execution:
        console.print("\n[bold]Execution[/]")
        for entry in execution["steps"]:
            mark = "[green]✓[/]" if entry.get("ok") else "[red]✗[/]"
            console.print(
                f"  {mark} {escape(entry['agent'])} "
                f"[dim]({entry.get('verify_status', 'unknown')})[/]"
            )
    if not execute_local and not execute_pi:
        console.print(
            "\n[dim]Dry run — nothing executed. "
            "Add --execute-local to run it here, or --pi-handoff for the PI command.[/]"
        )


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------


@harness_app.command("worker")
def harness_worker(
    agent: Annotated[str, typer.Argument(help="Subagent name declared in the manifest.")],
    task: Annotated[str, typer.Option("--task", help="Task payload for the worker.")] = "",
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Show the execution plan for a single subagent."""
    from maglab.harness.plan import build_worker_plan

    try:
        plan = build_worker_plan(agent, task=task)
    except HarnessPlanError as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        raise typer.Exit(1) from exc

    if json_output:
        emit_json(plan.to_dict())
        return

    if plan.description:
        console.print(f"[dim]{escape(plan.description)}[/]")
    table = Table(title=f"{plan.agent} — worker plan", show_lines=False)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Agent", style="cyan")
    table.add_column("Model")
    table.add_column("Turns", justify="right")
    table.add_column("Tools")
    table.add_column("Skills")
    table.add_column("MCP")
    _render_worker_row(table, None, plan)
    console.print(table)
    if plan.definition_path:
        console.print(f"[dim]definition: {escape(plan.definition_path)}[/]")
    if not plan.ready:
        console.print("[yellow]Worker is not ready — see the missing entries above.[/]")


# ---------------------------------------------------------------------------
# pi-tool
# ---------------------------------------------------------------------------


@harness_app.command("pi-tool")
def harness_pi_tool(
    payload_json: Annotated[
        str,
        typer.Option("--payload-json", help='PI payload, e.g. {"workflow":"survey","input":"..."}'),
    ],
    output: Annotated[str, typer.Option("--output", help="Output format: text or json.")] = "json",
) -> None:
    """Resolve a PI-callable payload into a MagLab plan.

    This is the wrapper PI itself invokes: minimal request in, full plan out.
    """
    from maglab.harness.pi import pi_tool_payload

    try:
        result = pi_tool_payload(payload_json)
    except HarnessPlanError as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        raise typer.Exit(1) from exc

    if output.strip().lower() != "text":
        emit_json(result)
        raise typer.Exit(0 if result["ok"] else 1)

    console.print(
        f"[bold]{escape(result['workflow'])}[/] ← {escape(result['input'] or '(no input)')}"
    )
    for i, step in enumerate(result["payload"]["steps"], start=1):
        console.print(f"  {i}. [cyan]{escape(step['agent'])}[/] [dim]{escape(step['model'])}[/]")
    _print_blockers(result["blockers"], result.get("warnings"))
    raise typer.Exit(0 if result["ok"] else 1)
