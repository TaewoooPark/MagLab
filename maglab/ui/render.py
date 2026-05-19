"""Main render pattern module.

rich-based rendering:
- Panel (ROUNDED) wrapper
- Streaming response (rich.live.Live)
- Tool call display (Panel + Tree, status icons ⟳/✓/✗)
- DataPoint badges ([SIM] cyan · [MEAS] green · [FIT] magenta · [PRED] yellow · [LIT] grey)
- thinking panel (dim, MINIMAL)
- diff (Syntax)
- error / warning panels
- progress (Progress)

Badges are implemented as self-contained renderers that accept a
provenance_type string.
This module does not import other maglab/ sub-modules (ui is self-contained).

Accessibility: NO_COLOR · TERM=dumb · non-TTY → rich removes colour codes automatically.

Design rationale: §7.6 (plan/02-delivery.md).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.box import MINIMAL, ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

if TYPE_CHECKING:
    from rich.live import Live

# ---------------------------------------------------------------------------
# Console factory
# ---------------------------------------------------------------------------


def make_console(
    *,
    force_terminal: bool = False,
    width: int | None = None,
    no_color: bool | None = None,
) -> Console:
    """Create a Console for rendering.

    Automatically falls back to ``no_color=True, highlight=False`` in
    non-TTY environments.

    :param force_terminal: If True, treat as a terminal even in non-TTY environments.
    :param width: Force a specific width.  Auto-detected if None.
    :param no_color: Suppress colour.  Auto-detected from the environment if None.
    :returns: Console instance.
    """
    _no_color = no_color
    if _no_color is None:
        _no_color = "NO_COLOR" in os.environ or os.environ.get("TERM", "") == "dumb"

    # Non-TTY (pipe, etc.) — strip colour unless force_terminal is set
    is_tty = sys.stdout.isatty()
    if not is_tty and not force_terminal:
        _no_color = True

    kwargs: dict = {
        "highlight": False,
        "no_color": _no_color,
    }
    if force_terminal:
        kwargs["force_terminal"] = True
    if width is not None:
        kwargs["width"] = width
    return Console(**kwargs)


# Module-level default console
_console = make_console()


def get_console() -> Console:
    """Return the default Console."""
    return _console


# ---------------------------------------------------------------------------
# DataPoint badges
# ---------------------------------------------------------------------------

#: provenance_type → (badge label, rich colour name or hex)
_BADGE_MAP: dict[str, tuple[str, str]] = {
    "SIMULATED": ("[SIM]", "cyan"),
    "SIM": ("[SIM]", "cyan"),
    "MEASURED": ("[MEAS]", "green"),
    "MEAS": ("[MEAS]", "green"),
    "FITTED": ("[FIT]", "bright_magenta"),
    "FIT": ("[FIT]", "bright_magenta"),
    "PREDICTED": ("[PRED]", "yellow"),
    "PRED": ("[PRED]", "yellow"),
    "LITERATURE": ("[LIT]", "bright_black"),
    "LIT": ("[LIT]", "bright_black"),
    "THEORY": ("[LIT]", "bright_black"),
}


def badge_text(provenance_type: str) -> Text:
    """Convert a provenance_type string to a coloured badge ``rich.Text``.

    Returns plain label text (no colour) in ``NO_COLOR`` environments.

    :param provenance_type: Provenance type string (e.g. 'SIMULATED', 'MEASURED').
    :returns: Badge ``rich.Text`` object.
    """
    key = provenance_type.upper().strip()
    label, color = _BADGE_MAP.get(key, (f"[{key}]", "white"))

    no_color = "NO_COLOR" in os.environ or not sys.stdout.isatty()
    if no_color:
        return Text(label)

    text = Text()
    text.append(label, style=f"bold {color}")
    return text


def badge_str(provenance_type: str) -> str:
    """Convert a provenance_type string to a rich markup badge string.

    :param provenance_type: Provenance type string.
    :returns: rich markup string.
    """
    key = provenance_type.upper().strip()
    label, color = _BADGE_MAP.get(key, (f"[{key}]", "white"))
    return f"[bold {color}]{label}[/]"


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------


def info_panel(
    content: str,
    title: str = "",
    *,
    console: Console | None = None,
) -> None:
    """Print a ROUNDED border information panel.

    :param content: Panel body (rich markup allowed).
    :param title: Panel title.
    :param console: Console to use.  Uses the default Console if None.
    """
    con = console or _console
    con.print(Panel(content, title=title, box=ROUNDED))


def error_panel(
    message: str,
    title: str = "Error",
    *,
    console: Console | None = None,
) -> None:
    """Print an error panel (rose colour).

    :param message: Error message.
    :param title: Panel title.
    :param console: Console to use.  Uses the default Console if None.
    """
    con = console or _console
    con.print(Panel(f"[bold red]{message}[/]", title=f"[bold red]{title}[/]", box=ROUNDED))


def warning_panel(
    message: str,
    title: str = "Warning",
    *,
    console: Console | None = None,
) -> None:
    """Print a warning panel (amber colour).

    :param message: Warning message.
    :param title: Panel title.
    :param console: Console to use.  Uses the default Console if None.
    """
    con = console or _console
    con.print(Panel(f"[bold yellow]{message}[/]", title=f"[bold yellow]{title}[/]", box=ROUNDED))


def thinking_panel(
    content: str,
    title: str = "thinking",
    *,
    console: Console | None = None,
) -> None:
    """Print a thinking panel (dim, MINIMAL box).

    :param content: Panel body.
    :param title: Panel title.
    :param console: Console to use.  Uses the default Console if None.
    """
    con = console or _console
    con.print(Panel(f"[dim]{content}[/]", title=f"[dim]{title}[/]", box=MINIMAL))


# ---------------------------------------------------------------------------
# Tool call display
# ---------------------------------------------------------------------------

_STATUS_ICONS: dict[str, str] = {
    "running": "⟳",
    "success": "✓",
    "failure": "✗",
}

_STATUS_COLORS: dict[str, str] = {
    "running": "cyan",
    "success": "green",
    "failure": "red",
}


def tool_call_panel(
    tool_name: str,
    args: dict | None = None,
    status: str = "running",
    result: str | None = None,
    *,
    console: Console | None = None,
) -> None:
    """Display a tool call as a Panel + Tree.

    :param tool_name: Tool name.
    :param args: Tool argument dictionary.
    :param status: 'running' | 'success' | 'failure'.
    :param result: Result summary string.
    :param console: Console to use.  Uses the default Console if None.
    """
    con = console or _console
    icon = _STATUS_ICONS.get(status, "?")
    color = _STATUS_COLORS.get(status, "white")

    tree = Tree(f"[{color}]{icon}[/] [bold]{tool_name}[/]")
    if args:
        for key, val in args.items():
            tree.add(f"[dim]{key}[/] = {val!r}")
    if result is not None:
        tree.add(f"[bold {color}]result:[/] {result}")

    con.print(Panel(tree, box=ROUNDED, border_style=color))


# ---------------------------------------------------------------------------
# Diff render
# ---------------------------------------------------------------------------


def diff_panel(
    diff_text: str,
    title: str = "diff",
    *,
    console: Console | None = None,
) -> None:
    """Print diff text with Syntax highlighting.

    :param diff_text: Diff-format text.
    :param title: Panel title.
    :param console: Console to use.  Uses the default Console if None.
    """
    con = console or _console
    syn = Syntax(diff_text, "diff", theme="ansi_dark", line_numbers=False)
    con.print(Panel(syn, title=title, box=ROUNDED))


# ---------------------------------------------------------------------------
# Streaming response
# ---------------------------------------------------------------------------


@contextmanager
def streaming_response(
    title: str = "Response",
    *,
    console: Console | None = None,
) -> Generator[_StreamContext, None, None]:
    """Streaming response context manager.

    Uses ``rich.live.Live`` to update the panel on each token batch.
    In non-TTY / suppressed environments, writes sequentially without Live.

    Example usage::

        with streaming_response("LLM response") as ctx:
            for chunk in llm_stream():
                ctx.append(chunk)

    :param title: Panel title.
    :param console: Console to use.  Uses the default Console if None.
    :yields: _StreamContext instance.
    """
    con = console or _console
    no_live = (
        "NO_COLOR" in os.environ
        or os.environ.get("TERM", "") == "dumb"
        or bool(os.environ.get("MAGLAB_SCREEN_READER", ""))
        or not sys.stdout.isatty()
    )

    ctx = _StreamContext(title=title, console=con, no_live=no_live)
    if no_live:
        yield ctx
        ctx._flush()
    else:
        from rich.live import Live
        from rich.markdown import Markdown

        with Live(
            Panel(Markdown(ctx._buffer), title=title, box=ROUNDED),
            console=con,
            refresh_per_second=12,
        ) as live:
            ctx._live = live
            yield ctx


class _StreamContext:
    """Streaming context helper.

    :param title: Panel title.
    :param console: Rendering Console.
    :param no_live: If True, writes sequentially without Live.
    """

    def __init__(self, title: str, console: Console, no_live: bool) -> None:
        self._title = title
        self._console = console
        self._no_live = no_live
        self._buffer = ""
        self._live: Live | None = None

    def append(self, chunk: str) -> None:
        """Add a token/chunk to the buffer and update Live.

        :param chunk: New text fragment.
        """
        from rich.markdown import Markdown

        self._buffer += chunk
        if self._live is not None:
            self._live.update(Panel(Markdown(self._buffer), title=self._title, box=ROUNDED))

    def _flush(self) -> None:
        """Output the final buffer in no_live mode."""
        if self._no_live:
            from rich.markdown import Markdown

            self._console.print(Panel(Markdown(self._buffer), title=self._title, box=ROUNDED))


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------


@contextmanager
def progress_bar(
    description: str = "In progress",
    total: int | None = None,
    *,
    console: Console | None = None,
) -> Generator[Progress, None, None]:
    """Progress bar context manager.

    :param description: Task description.
    :param total: Total number of steps.  Indeterminate if None.
    :param console: Console to use.  Uses the default Console if None.
    :yields: Progress instance (update via ``task_id``).
    """
    con = console or _console
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=con,
        transient=True,
    ) as progress:
        progress.add_task(description, total=total)
        yield progress


# ---------------------------------------------------------------------------
# Spin lattice rule (magnetic motif separator)
# ---------------------------------------------------------------------------


def spin_rule(
    *,
    console: Console | None = None,
    width: int = 40,
) -> None:
    """Print a magnetic spin-lattice separator (↑↑↑│↓↓↓).

    :param console: Console to use.  Uses the default Console if None.
    :param width: Output width (default 40).
    """
    con = console or _console
    half = width // 2
    rule_text = "↑" * half + "│" + "↓" * half
    con.print(f"[dim]{rule_text}[/]")


# ---------------------------------------------------------------------------
# Token output shorthand
# ---------------------------------------------------------------------------


def print_tokens(
    tokens: Iterable[str],
    *,
    console: Console | None = None,
) -> None:
    """Print a token iterable sequentially (non-streaming fallback).

    :param tokens: String iterable.
    :param console: Console to use.  Uses the default Console if None.
    """
    con = console or _console
    for tok in tokens:
        con.print(tok, end="")
    con.print()  # final newline
