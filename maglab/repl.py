"""MagLab interactive REPL.

``run_repl(config)`` — renders banner → session panel → prompt loop.

P0 smoke tests can start and exit without a backend (backend is optional).

Slash commands:
  /help    — display help
  /theme   — switch theme (/theme <name>)
  /skill   — list skills

Design rationale: §7.1, §7.5, §7.6, §7.7 (plan/02-delivery.md).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maglab.config import Config


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_SLASH_HELP = """\
[bold]Slash commands[/]
  [cyan]/help[/]              This help message
  [cyan]/theme <name>[/]      Switch theme (domain·mono·moke·light)
  [cyan]/skill[/]             List skills
  [cyan]/quit[/] · [cyan]/exit[/]     Quit

[bold]General usage[/]
  Type a query and the orchestrator will respond.
  Ctrl+C — cancel current input
  Ctrl+D — quit
"""


# ---------------------------------------------------------------------------
# Session panel
# ---------------------------------------------------------------------------


def _session_panel(config: Config, backend: object | None) -> None:
    """Print the session information panel."""
    import os

    from rich.box import ROUNDED
    from rich.console import Console
    from rich.panel import Panel

    con = Console()

    # backend label
    if backend is not None:
        backend_label = getattr(backend, "default_model", str(type(backend).__name__))
    else:
        mode = config.backend.mode
        if mode == "api":
            backend_label = f"{config.backend.api.model} · API"
        elif mode == "delegated_cli":
            backend_label = f"{config.backend.delegated_cli.tool} · delegated CLI"
        else:
            backend_label = f"{config.backend.local.model} · local"

    # skill count
    try:
        from maglab.core.skills import SkillLoader

        loader = SkillLoader()
        skill_count = len(loader.list_meta())
    except Exception:
        skill_count = 0

    cwd = os.getcwd()
    theme_name = config.ui.theme

    content = (
        f"  [dim]backend[/]   {backend_label}\n"
        f"  [dim]cwd[/]       {cwd}\n"
        f"  [dim]theme[/]     {theme_name}\n"
        f"  [dim]skills[/]    {skill_count} loaded          "
        f"[dim]gateway[/]   off"
    )
    con.print(Panel(content, title="session", box=ROUNDED))


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------


def _handle_slash(line: str, config: Config) -> bool:
    """Handle a slash command.

    Returns:
        True to continue the loop; False to exit the REPL.
    """
    from rich.console import Console

    con = Console()
    parts = line.strip().split()
    cmd = parts[0].lower()

    if cmd in ("/quit", "/exit"):
        return False

    if cmd == "/help":
        con.print(_SLASH_HELP)
        return True

    if cmd == "/skill":
        try:
            from maglab.core.skills import SkillLoader

            loader = SkillLoader()
            metas = loader.list_meta()
            if not metas:
                con.print("[dim]No skills found[/]")
            else:
                for m in metas:
                    con.print(f"  [cyan]{m.name}[/]  — {m.description[:60]}")
        except Exception as exc:
            con.print(f"[red]Skill load error:[/] {exc}")
        return True

    if cmd == "/theme":
        if len(parts) < 2:
            from maglab.ui.theme import Theme

            con.print(f"Available themes: {', '.join(Theme.available_themes())}")
            return True
        name = parts[1]
        try:
            from maglab.ui.theme import Theme

            Theme.load(name)  # validate
            # update config (within session)
            config.ui.theme = name
            con.print(f"[green]✓[/] Theme switched to [bold]{name}[/].")
        except FileNotFoundError:
            con.print(f"[red]Unknown theme:[/] {name!r}")
        return True

    con.print(f"[yellow]Unknown slash command:[/] {cmd!r}  (use /help for a list)")
    return True


# ---------------------------------------------------------------------------
# Response generation
# ---------------------------------------------------------------------------


def _get_response(user_msg: str, orchestrator: object | None) -> str:
    """Retrieve a response from the orchestrator.

    If no orchestrator is available, returns a startup guidance message.
    """
    if orchestrator is not None:
        try:
            respond = getattr(orchestrator, "respond", None)
            if respond is not None:
                return str(respond(user_msg))
        except Exception as exc:
            return f"[Orchestrator error] {exc}"
    return (
        "[dim]P0 smoke mode: no backend connected. "
        "Set an API key with `maglab auth set <provider> <api_key>`.[/]"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_repl(config: Config) -> None:
    """Run the interactive REPL.

    Sequence:
    1. Render banner (immediately)
    2. Load theme
    3. Print session panel
    4. Spin-lattice rule separator
    5. Prompt input loop (safe exit via Ctrl+C / Ctrl+D)

    Args:
        config: Global configuration object.
    """
    from rich.console import Console

    con = Console()

    # --- 1. Banner ---
    try:
        from maglab.ui.banner import render as render_banner
        from maglab.ui.theme import Theme

        theme = Theme.load(config.ui.theme)
        render_banner(theme=theme)
    except Exception:
        # Fallback to plain text if banner rendering fails
        con.print("MAGLAB — magnetism · spintronics research copilot")

    # --- 2. Session panel ---
    backend: object | None = None
    orchestrator: object | None = None

    try:
        from maglab.core.orchestrator import Orchestrator

        orchestrator = Orchestrator(config=config, backend=None)
    except Exception:
        orchestrator = None

    _session_panel(config, backend)

    # --- 3. Spin-lattice rule separator ---
    try:
        from maglab.ui.render import spin_rule

        spin_rule(console=con)
    except Exception:
        con.print("─" * 40)

    # --- 4. Prompt hint ---
    con.print()
    con.print("  [cyan]⇡[/] How can I help?   ( /help · /theme · /skill )")
    con.print()

    # --- 5. Input loop ---
    is_tty = sys.stdin.isatty()

    if is_tty:
        try:
            from maglab.ui.prompt import build_session, prompt_input

            session = build_session()
        except Exception:
            session = None
    else:
        session = None

    while True:
        try:
            if is_tty and session is not None:
                try:
                    from maglab.ui.prompt import prompt_input

                    user_input = prompt_input(session=session, placeholder="Enter a query…")
                except ImportError:
                    user_input = input("⇡ ")
            else:
                user_input = input()

        except KeyboardInterrupt:
            con.print()
            con.print("[dim]Interrupted (Ctrl+C). Press Ctrl+D or type /quit to exit.[/]")
            continue
        except EOFError:
            con.print()
            con.print("[dim]Goodbye. (MagLab)[/]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Slash command
        if user_input.startswith("/"):
            should_continue = _handle_slash(user_input, config)
            if not should_continue:
                con.print("[dim]Goodbye. (MagLab)[/]")
                break
            continue

        # General query → orchestrator
        response = _get_response(user_input, orchestrator)

        try:
            from maglab.ui.render import streaming_response

            with streaming_response("MagLab", console=con) as ctx:
                ctx.append(response)
        except Exception:
            con.print(response)
