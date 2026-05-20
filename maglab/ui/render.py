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
import threading
import time
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich.box import MINIMAL, ROUNDED
from rich.console import Console
from rich.live import Live
from rich.markup import escape
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

from maglab.ui.spinner import PRECESSION_FRAMES, STATIC_SYMBOL, _no_animation

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


def _compact_refs(refs: Iterable[str], *, max_refs: int = 5) -> str:
    """Return a compact display string for reference paths."""
    items = [escape(str(ref)) for ref in refs if str(ref).strip()]
    if not items:
        return ""
    visible = items[:max_refs]
    suffix = f"  [dim]+{len(items) - max_refs} more[/]" if len(items) > max_refs else ""
    return " · ".join(f"[dim]{item}[/]" for item in visible) + suffix


def trace_event_line(
    event: dict[str, Any],
    *,
    console: Console | None = None,
) -> None:
    """Render one real-time LLM/tool trace event.

    The trace is intentionally compact so researchers can see which model,
    Python tool file, and workspace artifacts were touched without losing the
    conversational flow.
    """
    con = console or _console
    kind = str(event.get("kind", ""))
    if kind == "llm_start":
        model = escape(str(event.get("model") or "default"))
        stage = escape(str(event.get("stage") or "default"))
        tool_count = event.get("tool_count", 0)
        con.print(
            f"\n[dim]────[/] 🧠 [bold cyan]LLM[/] stage={stage} model={model} tools={tool_count}"
        )
        return
    if kind == "llm_done":
        elapsed = float(event.get("elapsed_sec") or 0.0)
        tool_calls = int(event.get("tool_calls") or 0)
        tokens = int(event.get("prompt_tokens") or 0) + int(event.get("completion_tokens") or 0)
        con.print(
            f"[dim]     [/][green]✓[/] answer frame received · {elapsed:.2f}s · "
            f"{tool_calls} tool call(s) · {tokens} token(s)"
        )
        return
    if kind == "llm_error":
        con.print(f"[red]✗ LLM error:[/] {escape(str(event.get('error') or 'unknown'))}")
        return
    if kind in {"tool_start", "tool_done", "tool_blocked"}:
        tool = escape(str(event.get("tool") or "unknown_tool"))
        source = escape(str(event.get("source") or "unknown source"))
        refs = _compact_refs(event.get("references") or [])
        if kind == "tool_start":
            con.print(f"[dim]  ├─[/] 🔧 [bold]{tool}[/]  [dim]py:[/] {source}")
            if refs:
                con.print(f"[dim]  │   📄 refs:[/] {refs}")
            return
        if kind == "tool_done":
            con.print(f"[dim]  └─[/] ✅ [green]{tool} complete[/]")
            if refs:
                con.print(f"[dim]      📄 touched:[/] {refs}")
            return
        reason = escape(str(event.get("reason") or "blocked"))
        con.print(f"[dim]  └─[/] ⛔ [yellow]{tool} blocked[/]  [dim]{reason}[/]")
        return


class ReplTraceRenderer:
    """Stateful real-time renderer for REPL LLM/tool activity."""

    _FRAMES = tuple(PRECESSION_FRAMES)

    def __init__(self, *, console: Console | None = None) -> None:
        self._console = console or _console
        self._live: Live | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started = 0.0
        self._started_label = ""
        self._message = ""

    def emit(self, event: dict[str, Any]) -> None:
        """Render one orchestrator trace event."""
        kind = str(event.get("kind", ""))
        if kind == "llm_start":
            model = escape(str(event.get("model") or "default"))
            stage = escape(str(event.get("stage") or "default"))
            tool_count = int(event.get("tool_count") or 0)
            self._start_activity(
                f"LLM working · stage={stage} · model={model} · tools={tool_count}"
            )
            return
        if kind == "tool_start":
            tool = escape(str(event.get("tool") or "unknown_tool"))
            source = escape(str(event.get("source") or "unknown source"))
            refs = _compact_refs(event.get("references") or [], max_refs=3)
            detail = f"tool running · {tool} · py:{source}"
            if refs:
                detail += f" · refs:{refs}"
            self._start_activity(detail)
            return
        if kind in {"llm_done", "llm_error", "tool_done", "tool_blocked"}:
            self._stop_activity()
        trace_event_line(event, console=self._console)

    def close(self) -> None:
        """Stop any active spinner."""
        self._stop_activity()

    def _start_activity(self, message: str) -> None:
        self._stop_activity()
        if not self._console.is_terminal or _no_animation():
            started = datetime.now().strftime("%H:%M:%S")
            self._console.print(
                f"\n[dim]────[/] {STATIC_SYMBOL} {message} · started {started} · stop Ctrl+C"
            )
            return
        self._message = message
        self._started = time.monotonic()
        self._started_label = datetime.now().strftime("%H:%M:%S")
        self._stop = threading.Event()
        self._live = Live(
            self._activity_line(0),
            console=self._console,
            refresh_per_second=8,
            transient=True,
        )
        self._live.__enter__()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _stop_activity(self) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=0.5)
            self._thread = None
        if self._live is not None:
            self._live.__exit__(None, None, None)
            self._live = None

    def _spin(self) -> None:
        idx = 0
        while not self._stop.wait(0.12):
            live = self._live
            if live is None:
                return
            idx += 1
            live.update(self._activity_line(idx))

    def _activity_line(self, frame_idx: int) -> str:
        frame = self._FRAMES[frame_idx % len(self._FRAMES)]
        elapsed = time.monotonic() - self._started if self._started else 0.0
        return (
            f"[cyan]{frame}[/] [bold]{self._message}[/]  "
            f"[dim]started {self._started_label} · elapsed {elapsed:0.1f}s · stop Ctrl+C[/]"
        )


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
