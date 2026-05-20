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

import shlex
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

    from maglab.config import Config


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_TURN_SEPARATOR = "------"


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
        try:
            from maglab.llm.backends.factory import backend_label as _backend_label

            backend_label = _backend_label(config)
        except Exception:
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
    try:
        parts = shlex.split(line.strip())
    except ValueError as exc:
        con.print(f"[red]Slash command parse error:[/] {exc}")
        return True
    if not parts:
        return True
    cmd = parts[0].lower()

    if cmd in ("/quit", "/exit"):
        return False

    if cmd == "/help":
        from maglab.commands.tree import render_area_help, render_quick_help, render_slash_help

        target = parts[1].lower() if len(parts) >= 2 else "quick"
        if target == "all":
            render_slash_help(con)
        elif target == "quick":
            render_quick_help(con)
        elif not render_area_help(target, con):
            con.print(f"[yellow]Unknown help area:[/] {target!r}. Use /help quick or /help all.")
        return True

    if cmd == "/clear":
        con.clear()
        return True

    if cmd == "/reset":
        _handle_reset(parts, config)
        return True

    if cmd in ("/connect", "/backend"):
        _handle_connect(parts, config)
        return True

    if cmd == "/setup" or cmd.startswith("/setup-"):
        _handle_setup(parts, cmd)
        return True

    if cmd == "/skill" and (len(parts) == 1 or parts[1] == "list"):
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
        if parts[1] == "list":
            from maglab.ui.theme import Theme

            con.print(f"Available themes: {', '.join(Theme.available_themes())}")
            return True
        name = parts[2] if len(parts) >= 3 and parts[1] == "set" else parts[1]
        try:
            from maglab.config import save_config
            from maglab.ui.theme import Theme

            Theme.load(name)  # validate
            config.ui.theme = name
            saved = save_config(config)
            con.print(f"[green]✓[/] Theme switched to [bold]{name}[/] and saved to {saved}.")
        except FileNotFoundError:
            con.print(f"[red]Unknown theme:[/] {name!r}")
        return True

    if _is_cli_slash_command(cmd):
        _run_cli_slash(parts, con)
        return True

    con.print(f"[yellow]Unknown slash command:[/] {cmd!r}  (use /help for a list)")
    return True


def _is_cli_slash_command(cmd: str) -> bool:
    """Return True when a slash command maps directly to a Typer CLI command."""
    from maglab.commands.tree import CLI_SLASH_ROOTS

    return cmd in CLI_SLASH_ROOTS


def _run_cli_slash(parts: list[str], con: Console) -> None:
    """Run a Typer command from the REPL slash surface."""
    import click
    from typer.main import get_command

    from maglab.cli import app

    root = parts[0].removeprefix("/")
    if root in {"ask", "run"} and len(parts) > 2:
        args = [root, " ".join(parts[1:])]
    elif root == "manual" and len(parts) >= 2 and parts[1] in {"en", "ko"}:
        args = [root, *parts[2:], "--lang", parts[1]]
    else:
        args = [root, *parts[1:]]
    command = get_command(app)
    try:
        command.main(args=args, prog_name="maglab", standalone_mode=False)
    except click.exceptions.Exit as exc:
        if exc.exit_code not in (0, None):
            con.print(f"[red]Command exited with code {exc.exit_code}[/]")
    except click.ClickException as exc:
        con.print(f"[red]{exc.format_message()}[/]")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code:
            con.print(f"[red]Command exited with code {code}[/]")


def _apply_config(config: Config, new_config: Config) -> None:
    """Mutate the active REPL config object to match a newly loaded config."""
    for field_name in type(new_config).model_fields:
        setattr(config, field_name, getattr(new_config, field_name))


def _handle_reset(parts: list[str], config: Config) -> None:
    """Handle config rollback/default reset slash commands."""
    from rich.console import Console

    from maglab.config import load_config, reset_config, restore_config

    con = Console()
    target = parts[1].lower() if len(parts) >= 2 else "config"
    if target in {"config", "restore", "last"}:
        try:
            path = restore_config()
        except FileNotFoundError as exc:
            con.print(f"[yellow]{exc}[/]")
            return
        _apply_config(config, load_config(path))
        con.print(f"[green]✓[/] Restored previous MagLab config: [bold]{path}[/]")
        return
    if target in {"defaults", "default", "factory"}:
        path = reset_config()
        _apply_config(config, load_config(path))
        con.print(f"[green]✓[/] Reset MagLab config to defaults: [bold]{path}[/]")
        return
    con.print("[yellow]Usage:[/] /reset config  or  /reset defaults")


def _handle_setup(parts: list[str], cmd: str) -> None:
    """Handle setup slash commands."""
    from rich.console import Console

    from maglab.setup import render_setup

    con = Console()
    if cmd.startswith("/setup-"):
        feature = cmd.removeprefix("/setup-")
    elif len(parts) >= 2:
        feature = parts[1]
    else:
        feature = "all"
    render_setup(feature, console=con)


def _handle_connect(parts: list[str], config: Config) -> None:
    """Handle backend connection slash commands."""
    from rich.console import Console

    con = Console()
    if len(parts) == 1:
        con.print(
            "[bold]Connect backend[/]\n"
            "  [cyan]/connect status[/]        Show current backend readiness\n"
            "  [cyan]/connect reset[/]         Restore previous backend/config selection\n"
            "  [cyan]/connect defaults[/]      Reset backend/config to defaults\n"
            "  [cyan]/connect codex[/]         Use official Codex CLI auth/session\n"
            "  [cyan]/connect claude[/]        Use official Claude CLI auth/session\n"
            "  [cyan]/connect gemini-cli[/]    Use official Gemini CLI auth/session\n"
            "  [cyan]/connect anthropic|grok|deepseek|qwen|kimi|gemini|openai [model][/]\n"
            "  [cyan]/connect api <provider> [model] [base_url][/]\n"
            "  [cyan]/connect ollama [model] [host][/]\n\n"
            "Connection changes are saved to config. Restart MagLab after switching backends."
        )
        return

    subcmd = parts[1].lower()
    if subcmd in {"reset", "restore", "defaults", "default"}:
        target = "defaults" if subcmd in {"defaults", "default"} else "config"
        _handle_reset(["/reset", target], config)
        return

    if subcmd == "status":
        from maglab.config import config_path
        from maglab.llm.backends.factory import backend_status

        status = backend_status(config)
        marker = "[green]✓[/]" if status.ok else "[red]✗[/]"
        con.print(f"{marker} [bold]{status.label}[/]")
        con.print(f"  config: {config_path()}")
        con.print(f"  detail: {status.detail}")
        if status.action:
            con.print(f"  next: {status.action}")
        return

    if subcmd in {"codex", "claude", "gemini-cli"}:
        from maglab.llm.connect import configure_delegated_cli
        from maglab.ui.prompt import prompt_delegated_model_choice

        tool = "gemini" if subcmd == "gemini-cli" else subcmd
        model = parts[2] if len(parts) >= 3 else None
        model = prompt_delegated_model_choice(tool, model)
        saved, exe_status = configure_delegated_cli(config, tool=tool, model=model)
        con.print(f"[green]✓[/] Saved [bold]{tool}[/] delegated CLI backend to {saved}.")
        if exe_status == "missing":
            con.print(
                f"[yellow]{tool} CLI was not found on PATH.[/] Install and authenticate "
                "the official CLI first."
            )
        con.print("Restart MagLab to load the new backend.")
        return

    if subcmd == "api":
        from maglab.llm.providers import api_provider_choices

        if len(parts) < 3:
            con.print(
                f"[yellow]Usage:[/] /connect api <{api_provider_choices()}> [model] [base_url]"
            )
            return
        provider = parts[2]
        model = parts[3] if len(parts) >= 4 else None
        base_url = parts[4] if len(parts) >= 5 else None
        _connect_api_provider(con, config, provider=provider, model=model, base_url=base_url)
        return

    try:
        from maglab.llm.providers import get_provider_profile, normalize_provider

        provider = normalize_provider(subcmd)
        get_provider_profile(provider)
    except ValueError:
        provider = ""

    if provider:
        model = parts[2] if len(parts) >= 3 else None
        base_url = parts[3] if provider == "openai-compatible" and len(parts) >= 4 else None
        _connect_api_provider(con, config, provider=provider, model=model, base_url=base_url)
        return

    if subcmd == "ollama":
        from maglab.llm.connect import configure_local_backend

        model = parts[2] if len(parts) >= 3 else config.backend.local.model
        host = parts[3] if len(parts) >= 4 else config.backend.local.host
        saved = configure_local_backend(config, model=model, host=host)
        con.print(f"[green]✓[/] Saved Ollama backend to {saved}.")
        con.print("Start Ollama with `ollama serve`, then restart MagLab.")
        return

    con.print(f"[yellow]Unknown connect target:[/] {subcmd!r}")


def _connect_api_provider(
    con: Console,
    config: Config,
    *,
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
) -> None:
    """Configure a direct API provider from the REPL."""
    import getpass

    from maglab.llm.auth import get_api_key, store_api_key
    from maglab.llm.connect import configure_api_backend
    from maglab.llm.providers import get_provider_profile, normalize_provider

    provider = normalize_provider(provider)
    profile = get_provider_profile(provider)
    if model is None:
        from maglab.ui.prompt import prompt_model_choice

        model = prompt_model_choice(provider)
    saved = configure_api_backend(config, provider=provider, model=model, base_url=base_url)
    existing = get_api_key(provider)
    suffix = "blank to keep existing" if existing else "blank to skip storing"
    key = getpass.getpass(f"{profile.title} API key ({suffix}): ")
    if key:
        location = store_api_key(provider, key)
        con.print(f"[green]✓[/] API key saved in {location}.")
    con.print(
        f"[green]✓[/] Saved [bold]{profile.title}[/] API backend to {saved}. "
        f"Model: [bold]{config.backend.api.model}[/]. Restart MagLab to load it."
    )


def _print_turn_separator(con: Console) -> None:
    """Print a readable separator between REPL turns."""
    try:
        con.print()
        con.print(f"[dim]{_TURN_SEPARATOR}[/]")
        con.print()
    except Exception:
        print(f"\n{_TURN_SEPARATOR}\n")


def _workspace_startup_note(max_entries: int = 12) -> str:
    """Return a short deterministic note about the active workspace."""
    try:
        from maglab.workspace import workspace_context

        context = workspace_context(max_entries=max_entries, max_maglab_chars=500)
    except Exception as exc:
        return f"[dim]Workspace context unavailable: {exc}[/]"

    marker = "MAGLAB.md loaded" if context.maglab_md else "MAGLAB.md missing"
    entry_count = len(context.entries)
    truncated = "+" if context.truncated else ""
    key_hint = ", ".join(context.key_paths[:4]) if context.key_paths else "no common project files"
    return (
        f"[dim]Workspace context:[/] {context.root} · {marker} · "
        f"{entry_count}{truncated} visible entries · {key_hint}"
    )


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
    workspace_note = _workspace_startup_note(max_entries=8)
    return (
        f"{workspace_note}\n"
        "[dim]No LLM backend is connected. Use `/connect codex`, `/connect <provider>`, "
        "`/connect api <provider>`, "
        "or `/connect ollama`.[/]"
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
        from maglab.llm.base import ModelRouter
        from maglab.llm.factory import backend_status, create_llm_backend

        status = backend_status(config)
        if status.ok:
            backend = create_llm_backend(config)
        else:
            con.print(f"[yellow]Backend not ready:[/] {status.detail}")
            if status.action:
                con.print(f"[dim]{status.action}[/]")
        orchestrator = Orchestrator(
            config=config,
            backend=backend,
            model_router=(
                ModelRouter(config.routing.model_dump()) if config.backend.mode == "api" else None
            ),
        )
    except Exception as exc:
        con.print(f"[yellow]Backend setup failed:[/] {exc}")
        orchestrator = None

    # Guarantee that Orchestrator SQLite connections are released on exit
    # (Finding 4 / R1-F6 completion).  close() is a no-op when orchestrator
    # is None, so the try/finally is always safe.
    try:
        _session_panel(config, backend)
        con.print(_workspace_startup_note())

        # --- 3. Spin-lattice rule separator ---
        try:
            from maglab.ui.render import spin_rule

            spin_rule(console=con)
        except Exception:
            con.print("─" * 40)

        # --- 4. Prompt hint ---
        con.print()
        con.print("  [cyan]⇡[/] How can I help?   ( /help · /connect · /theme · /skill )")
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
            _print_turn_separator(con)

            try:
                from maglab.ui.render import streaming_response

                with streaming_response("MagLab", console=con) as ctx:
                    ctx.append(response)
            except Exception:
                con.print(response)
            _print_turn_separator(con)

    finally:
        # Close Orchestrator connections regardless of how the REPL exits
        _close = getattr(orchestrator, "close", None)
        if callable(_close):
            _close()
