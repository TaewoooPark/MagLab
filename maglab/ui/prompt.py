"""Input prompt module.

Interactive input based on ``prompt_toolkit.PromptSession``:
- FileHistory (~/.maglab/history)
- FuzzyCompleter (slash commands)
- AutoSuggestFromHistory
- Dynamic bottom_toolbar (backend · tokens · status)
- Multiline (Meta+Enter)
- Ctrl+R history search
- Prompt glyph ``⇡``

Falls back to ``input()`` in non-TTY mode.

Design rationale: §7.7 (plan/02-delivery.md).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prompt_toolkit import PromptSession

# ---------------------------------------------------------------------------
# Slash command list
# ---------------------------------------------------------------------------

#: Top-level slash commands (NestedCompleter tree)
SLASH_COMMANDS: dict[str, Any] = {
    "/help": None,
    "/theme": {
        "domain": None,
        "mono": None,
        "moke": None,
        "light": None,
    },
    "/skill": {
        "list": None,
        "info": None,
    },
    "/physics": {
        "oracle": None,
        "compute": None,
        "units": None,
        "material": None,
    },
    "/cost": None,
    "/config": None,
    "/auth": {
        "list": None,
        "test": None,
    },
    "/mcp": {
        "list": None,
        "serve": None,
    },
    "/clear": None,
    "/quit": None,
    "/exit": None,
    "/verbose": None,
}

#: Prompt glyph
PROMPT_GLYPH = "⇡"

#: History file path
_HISTORY_PATH = Path.home() / ".maglab" / "history"


# ---------------------------------------------------------------------------
# Default toolbar text
# ---------------------------------------------------------------------------


def _default_toolbar() -> str:
    """Return the default bottom_toolbar text."""
    return " maglab  |  /help  |  Meta+Enter multiline  |  Ctrl+R history"


# ---------------------------------------------------------------------------
# PromptSession builder
# ---------------------------------------------------------------------------


def build_session(
    toolbar_fn: Callable[[], str] | None = None,
    extra_commands: dict[str, Any] | None = None,
) -> PromptSession:
    """Create a MagLab-specific PromptSession.

    :param toolbar_fn: Callback returning dynamic bottom_toolbar text.
                       Uses the default toolbar if None.
    :param extra_commands: Additional slash commands to merge into SLASH_COMMANDS.
    :returns: Configured PromptSession instance.
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import FuzzyCompleter, NestedCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings

    # Create history file directory
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history = FileHistory(str(_HISTORY_PATH))

    # Merge slash commands
    commands = dict(SLASH_COMMANDS)
    if extra_commands:
        commands.update(extra_commands)

    completer = FuzzyCompleter(NestedCompleter.from_nested_dict(commands))
    auto_suggest = AutoSuggestFromHistory()
    toolbar = toolbar_fn or _default_toolbar

    # Meta+Enter multiline key binding
    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _meta_enter(event: Any) -> None:  # noqa: ANN001
        """Insert a newline on Meta+Enter."""
        event.current_buffer.insert_text("\n")

    session: PromptSession = PromptSession(
        history=history,
        completer=completer,
        auto_suggest=auto_suggest,
        bottom_toolbar=toolbar,
        key_bindings=kb,
        multiline=False,  # single-line by default; Meta+Enter inserts manually
        enable_history_search=True,  # Ctrl+R
        complete_while_typing=True,
    )
    return session


# ---------------------------------------------------------------------------
# Single prompt input function
# ---------------------------------------------------------------------------


def prompt_input(
    session: PromptSession | None = None,
    placeholder: str = "",
) -> str:
    """Read a single line (or multiline) of user input.

    Falls back to ``input()`` in non-TTY environments.
    Propagates EOFError (Ctrl+D) and KeyboardInterrupt (Ctrl+C).

    :param session: PromptSession to use.  Created on the fly if None.
    :param placeholder: Placeholder text shown on empty input.
    :returns: The string entered by the user.
    :raises EOFError: When input is terminated with Ctrl+D.
    :raises KeyboardInterrupt: When interrupted with Ctrl+C.
    """
    # Non-TTY fallback
    if not sys.stdin.isatty():
        try:
            return input()
        except EOFError:
            raise

    if session is None:
        session = build_session()

    glyph = PROMPT_GLYPH
    no_unicode = os.environ.get("TERM", "").lower() == "dumb" or not sys.stdout.isatty()
    if no_unicode:
        glyph = ">"

    prompt_str = f"{glyph} "

    from prompt_toolkit import prompt as _pt_prompt
    from prompt_toolkit.formatted_text import HTML

    _ = _pt_prompt  # verify import

    return session.prompt(  # type: ignore[no-any-return]
        HTML(f"<ansicyan>{prompt_str}</ansicyan>"),
        placeholder=HTML(f"<ansibrightblack>{placeholder}</ansibrightblack>")
        if placeholder
        else None,
    )


# ---------------------------------------------------------------------------
# History file path exposure
# ---------------------------------------------------------------------------


def history_path() -> Path:
    """Return the history file path."""
    return _HISTORY_PATH
