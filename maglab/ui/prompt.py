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


def _leaf(values: tuple[str, ...] | list[str]) -> dict[str, None]:
    """Return a NestedCompleter leaf mapping."""
    return dict.fromkeys(values)


def _provider_model_tree(provider: str) -> dict[str, None]:
    """Return model completion leaves for a direct API provider."""
    try:
        from maglab.llm.providers import model_choices

        return _leaf(model_choices(provider))
    except Exception:
        return {}


def _api_provider_tree() -> dict[str, dict[str, None]]:
    """Return provider -> model completion tree for /connect api."""
    try:
        from maglab.llm.providers import api_provider_keys

        return {provider: _provider_model_tree(provider) for provider in api_provider_keys()}
    except Exception:
        return {}


def _delegated_model_tree(tool: str) -> dict[str, None]:
    """Return model completion leaves for delegated CLI tools."""
    try:
        from maglab.llm.providers import delegated_model_choices

        return _leaf(delegated_model_choices(tool))
    except Exception:
        return {}


def _slash_commands() -> dict[str, Any]:
    """Build the slash completion tree, including dynamic model choices."""
    from maglab.commands.tree import base_slash_commands

    commands = base_slash_commands()
    commands["/auth"].update(
        {
            "anthropic": _provider_model_tree("anthropic"),
            "grok": _provider_model_tree("grok"),
            "deepseek": _provider_model_tree("deepseek"),
            "qwen": _provider_model_tree("qwen"),
            "kimi": _provider_model_tree("kimi"),
            "gemini": _provider_model_tree("gemini"),
            "openai": _provider_model_tree("openai"),
            "codex": _delegated_model_tree("codex"),
            "claude": _delegated_model_tree("claude"),
            "gemini-cli": _delegated_model_tree("gemini"),
        }
    )
    commands["/connect"].update(
        {
            "codex": _delegated_model_tree("codex"),
            "claude": _delegated_model_tree("claude"),
            "gemini-cli": _delegated_model_tree("gemini"),
            "anthropic": _provider_model_tree("anthropic"),
            "grok": _provider_model_tree("grok"),
            "deepseek": _provider_model_tree("deepseek"),
            "qwen": _provider_model_tree("qwen"),
            "kimi": _provider_model_tree("kimi"),
            "gemini": _provider_model_tree("gemini"),
            "openai": _provider_model_tree("openai"),
            "openai-compatible": _provider_model_tree("openai-compatible"),
            "api": _api_provider_tree(),
        }
    )
    return commands


#: Top-level slash commands (NestedCompleter tree)
SLASH_COMMANDS: dict[str, Any] = _slash_commands()

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


def _prompt_choice(
    title: str,
    choices: tuple[str, ...],
    *,
    default: str | None,
    explicit_value: str | None,
    allow_blank: bool,
) -> str | None:
    """Prompt for a model using a prompt_toolkit completion menu."""
    if explicit_value is not None or not sys.stdin.isatty():
        return explicit_value
    if not choices:
        return explicit_value
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.application.current import get_app
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import HTML
    except Exception:
        return explicit_value

    completer = WordCompleter(list(choices), ignore_case=True, sentence=True)
    session = PromptSession(completer=completer, complete_while_typing=True)

    def _show_completions() -> None:
        try:
            get_app().current_buffer.start_completion(select_first=False)
        except Exception:
            return

    suffix = " (blank = official CLI default)" if allow_blank else ""
    value = session.prompt(
        HTML(f"<ansicyan>{title} model{suffix}</ansicyan> "),
        default=default or "",
        pre_run=_show_completions,
    )
    selected = value.strip()
    if selected:
        return selected
    if allow_blank:
        return None
    return default


def prompt_model_choice(provider: str, explicit_model: str | None = None) -> str | None:
    """Prompt for a direct API provider model, showing supported choices first."""
    try:
        from maglab.llm.providers import get_provider_profile, model_choices

        profile = get_provider_profile(provider)
        return _prompt_choice(
            profile.title,
            model_choices(provider),
            default=profile.default_model,
            explicit_value=explicit_model,
            allow_blank=False,
        )
    except Exception:
        return explicit_model


def prompt_delegated_model_choice(tool: str, explicit_model: str | None = None) -> str | None:
    """Prompt for an optional delegated CLI model."""
    try:
        from maglab.llm.providers import delegated_model_choices

        choices = delegated_model_choices(tool)
        return _prompt_choice(
            tool,
            choices,
            default=None,
            explicit_value=explicit_model,
            allow_blank=True,
        )
    except Exception:
        return explicit_model


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
