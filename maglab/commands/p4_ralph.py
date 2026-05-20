"""P4 ralph CLI — start · status · cancel.

Wires the ``maglab ralph`` sub-app to the real RalphEngine in
``maglab.core.ralph``.  Heavy imports (RalphEngine, RalphState, …) are
deferred into callback bodies so that ``maglab --help`` always works.

Commands
--------
ralph start  -- launch a Ralph loop (in-session or detached mode).
ralph status -- read the state file and render a rich summary table.
ralph cancel -- stop an active loop by writing the stopped state.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Sub-app
# ---------------------------------------------------------------------------

ralph_app = typer.Typer(
    name="ralph",
    help="[P4] Ralph autonomous loop engine — start · status · cancel.",
    no_args_is_help=True,
)

console = Console()

# ---------------------------------------------------------------------------
# Default state-file location (mirrors core/ralph.py)
# ---------------------------------------------------------------------------

_DEFAULT_STATE_PATH = Path(".maglab") / "ralph.local.md"


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
    """Attach the P4 ralph command to the root maglab app."""
    app.add_typer(ralph_app)


# ---------------------------------------------------------------------------
# ralph start
# ---------------------------------------------------------------------------


@ralph_app.command("start")
def ralph_start(
    goal: Annotated[str, typer.Argument(help="Goal description for this Ralph loop.")],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Execution mode: in-session or detached.",
        ),
    ] = "in-session",
    max_iterations: Annotated[
        int,
        typer.Option(
            "--max-iter",
            "-n",
            help="Maximum number of loop iterations (capped at 50).",
        ),
    ] = 20,
    loop_type: Annotated[
        str,
        typer.Option(
            "--loop-type",
            "-t",
            help="Loop type identifier: A, B, C, D, E, or custom string.",
        ),
    ] = "",
    state_file: Annotated[
        str | None,
        typer.Option(
            "--state-file",
            "-s",
            help="Path to the Ralph state file (default: .maglab/ralph.local.md).",
        ),
    ] = None,
) -> None:
    """Start a new Ralph loop.

    Initialises a RalphState, writes it to the state file, and prints a
    confirmation table.  In detached mode the state file is the primary
    handoff mechanism between external process invocations.
    """
    from maglab.core.ralph import RalphEngine, RalphMode

    # Resolve and validate mode
    try:
        ralph_mode = RalphMode(mode)
    except ValueError:
        console.print(f"[red]Unknown mode:[/] {mode!r}. Valid values: in-session, detached.")
        raise typer.Exit(1) from None

    state_path = Path(state_file) if state_file else _DEFAULT_STATE_PATH

    engine = RalphEngine(
        mode=ralph_mode,
        max_iterations=max_iterations,
        goal=goal,
        loop_type=loop_type,
        state_path=state_path,
    )

    state = engine.start()

    table = Table(title="Ralph Loop Started", show_lines=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Run ID", state.run_id)
    table.add_row("Goal", state.goal[:120])
    table.add_row("Mode", state.mode.value)
    table.add_row("Loop Type", state.loop_type or "(none)")
    table.add_row("Max Iterations", str(state.max_iterations))
    table.add_row("State File", str(state_path))
    table.add_row("Active", str(state.active))

    console.print(table)
    console.print(
        f"[green]Ralph loop started.[/]  "
        f"Track progress with: [bold]maglab ralph status --state-file {state_path}[/]"
    )


# ---------------------------------------------------------------------------
# ralph status
# ---------------------------------------------------------------------------


@ralph_app.command("status")
def ralph_status(
    state_file: Annotated[
        str | None,
        typer.Option(
            "--state-file",
            "-s",
            help="Path to the Ralph state file (default: .maglab/ralph.local.md).",
        ),
    ] = None,
) -> None:
    """Show the current status of a Ralph loop from its state file.

    Reads the state file and renders a rich summary table including
    iteration count, mode, goal, active/stopped, stop reason, and
    circuit-breaker information.
    """
    from maglab.core.ralph import load_state

    state_path = Path(state_file) if state_file else _DEFAULT_STATE_PATH

    state = load_state(state_path)
    if state is None:
        console.print(
            f"[red]No Ralph state file found at:[/] {state_path}\n"
            "Start a loop first with: [bold]maglab ralph start <goal>[/]"
        )
        raise typer.Exit(1)

    # Compute elapsed time
    elapsed_s = time.time() - state.created_at
    elapsed_str = _format_elapsed(elapsed_s)

    active_display = "[green]active[/]" if state.active else "[dim]stopped[/]"
    stop_reason_display = state.stop_reason or "[dim]—[/]"

    table = Table(title=f"Ralph Loop Status — {state_path}", show_lines=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Run ID", state.run_id)
    table.add_row("Goal", state.goal[:120] or "[dim](no goal)[/]")
    table.add_row("Mode", state.mode.value)
    table.add_row("Loop Type", state.loop_type or "[dim]—[/]")
    table.add_row("Status", active_display)
    table.add_row("Iteration", f"{state.iteration} / {state.max_iterations}")
    table.add_row("Completion Promise", str(state.completion_promise))
    table.add_row("Stop Reason", stop_reason_display)
    table.add_row("Elapsed", elapsed_str)
    table.add_row("State File", str(state_path))

    console.print(table)


# ---------------------------------------------------------------------------
# ralph cancel
# ---------------------------------------------------------------------------


@ralph_app.command("cancel")
def ralph_cancel(
    state_file: Annotated[
        str | None,
        typer.Option(
            "--state-file",
            "-s",
            help="Path to the Ralph state file (default: .maglab/ralph.local.md).",
        ),
    ] = None,
) -> None:
    """Cancel an active Ralph loop.

    Reads the state file, marks the loop as stopped (reason: external),
    and writes the updated state back.  Safe to call on an already-stopped
    loop — it reports the current state without error.
    """
    from maglab.core.ralph import StopReason, load_state, save_state

    state_path = Path(state_file) if state_file else _DEFAULT_STATE_PATH

    state = load_state(state_path)
    if state is None:
        console.print(f"[red]No Ralph state file found at:[/] {state_path}\nNothing to cancel.")
        raise typer.Exit(1)

    if not state.active:
        console.print(
            f"[yellow]Ralph loop is already stopped.[/]  "
            f"Run ID: {state.run_id}  |  Stop reason: {state.stop_reason or '(unknown)'}"
        )
        return

    # Write the stopped state
    state.active = False
    state.stop_reason = StopReason.EXTERNAL.value
    save_state(state, state_path)

    console.print(
        f"[green]Ralph loop cancelled.[/]  "
        f"Run ID: {state.run_id}  |  Iteration: {state.iteration}/{state.max_iterations}"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_elapsed(seconds: float) -> str:
    """Return a human-readable elapsed-time string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"
