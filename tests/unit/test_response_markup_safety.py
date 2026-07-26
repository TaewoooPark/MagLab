"""Model output must never be parsed as Rich markup.

Rich reads ``[...]`` as markup, so a perfectly ordinary answer — "wrote it to
[/Users/me/fig.svg]" — parses as a closing tag and raises ``MarkupError``. For a
tool whose answers are full of file paths that turned a successful command into
a traceback, and took the REPL session down with it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import maglab.cli as cli_module
from maglab.cli import app
from maglab.repl import _get_response

runner = CliRunner()

BRACKETED = [
    "I wrote the figure to [/Users/me/Desktop/fig.svg] as requested.",
    "See [/tmp/report.pdf] for the fit summary.",
    "Files: [/a] and [/b].",
    "Closing tag lookalike: [/bold] in prose.",
]


class _Orchestrator:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def respond(self, prompt: str) -> str:
        return self._reply

    def close(self) -> None:
        return None


class _FailingOrchestrator:
    def __init__(self, message: str) -> None:
        self._message = message

    def respond(self, prompt: str) -> str:
        raise RuntimeError(self._message)

    def close(self) -> None:
        return None


class TestOneShotPrompt:
    @pytest.mark.parametrize("reply", BRACKETED)
    def test_bracketed_reply_does_not_crash(self, reply: str) -> None:
        with patch.object(cli_module, "_build_orchestrator", return_value=_Orchestrator(reply)):
            result = runner.invoke(app, ["-p", "make a figure"])

        assert result.exception is None, f"raised {result.exception!r}"
        assert result.exit_code == 0

    def test_the_path_is_still_visible_in_the_output(self) -> None:
        reply = "Saved to [/Users/me/Desktop/fig.svg]"
        with patch.object(cli_module, "_build_orchestrator", return_value=_Orchestrator(reply)):
            result = runner.invoke(app, ["-p", "make a figure"])

        plain = "".join(ch for ch in result.output if ch.isprintable())
        assert "fig.svg" in plain
        assert "[" in plain, "the brackets were swallowed rather than shown"


class TestReplResponse:
    @staticmethod
    def _render(text: str) -> str:
        """Render through Rich exactly as the REPL does; must not raise."""
        import io

        from rich.console import Console

        buffer = io.StringIO()
        Console(file=buffer, force_terminal=False, width=100).print(text)
        return buffer.getvalue()

    @pytest.mark.parametrize("reply", BRACKETED)
    def test_response_is_renderable(self, reply: str) -> None:
        assert self._render(_get_response("q", _Orchestrator(reply)))

    def test_orchestrator_error_is_renderable(self) -> None:
        text = _get_response("q", _FailingOrchestrator("missing [/etc/maglab/config]"))

        assert "Orchestrator error" in text
        assert "/etc/maglab/config" in self._render(text)

    def test_maglab_own_guidance_keeps_its_markup(self) -> None:
        """Only model text is escaped — our own strings still style normally."""
        text = _get_response("q", None)
        assert "[dim]" in text, "MagLab's own guidance lost its markup"
