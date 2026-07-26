"""Render pattern tests.

Validates badges, panels, streaming, and tool call rendering deterministically.
Output is made deterministic via rich Console force_terminal and width settings.

Validation principle: no LLM-as-judge — decisions are made solely by checking
for expected substrings in the output.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console
from rich.text import Text

from maglab.ui import render

# ---------------------------------------------------------------------------
# Helper — force_terminal Console + StringIO capture
# ---------------------------------------------------------------------------


def _console(width: int = 80, no_color: bool = True) -> tuple[Console, io.StringIO]:
    """Create a (Console, StringIO) pair for output capture."""
    buf = io.StringIO()
    con = Console(file=buf, force_terminal=True, width=width, no_color=no_color)
    return con, buf


# ---------------------------------------------------------------------------
# Tests: badge_text — 5 provenance types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ptype", "expected_label"),
    [
        ("SIMULATED", "[SIM]"),
        ("MEASURED", "[MEAS]"),
        ("FITTED", "[FIT]"),
        ("PREDICTED", "[PRED]"),
        ("LITERATURE", "[LIT]"),
    ],
)
def test_badge_text_label(ptype: str, expected_label: str) -> None:
    """The correct badge label is generated for each provenance_type."""
    result = render.badge_text(ptype)
    assert isinstance(result, Text)
    assert expected_label in result.plain


@pytest.mark.parametrize("ptype", ["SIM", "MEAS", "FIT", "PRED", "LIT"])
def test_badge_text_short_alias(ptype: str) -> None:
    """Short aliases (SIM, MEAS, ...) also produce the correct badge."""
    result = render.badge_text(ptype)
    assert isinstance(result, Text)
    assert "[" in result.plain


def test_badge_text_unknown_type() -> None:
    """Unknown provenance_type generates a badge using the type name."""
    result = render.badge_text("CUSTOM_XYZ")
    assert "CUSTOM_XYZ" in result.plain


def test_badge_text_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Label text is still present in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    result = render.badge_text("SIMULATED")
    assert "[SIM]" in result.plain


# ---------------------------------------------------------------------------
# Tests: badge_str — rich markup string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ptype", "label"),
    [
        ("SIMULATED", "[SIM]"),
        ("MEASURED", "[MEAS]"),
        ("FITTED", "[FIT]"),
        ("PREDICTED", "[PRED]"),
        ("LITERATURE", "[LIT]"),
    ],
)
def test_badge_str_contains_label(ptype: str, label: str) -> None:
    """badge_str contains the label string."""
    result = render.badge_str(ptype)
    assert label in result


# ---------------------------------------------------------------------------
# Tests: info_panel
# ---------------------------------------------------------------------------


def test_info_panel_contains_content() -> None:
    """info_panel includes content in the output."""
    con, buf = _console()
    render.info_panel("test content", title="Info", console=con)
    output = buf.getvalue()
    assert "test content" in output


def test_info_panel_contains_title() -> None:
    """info_panel includes the title in the output."""
    con, buf = _console()
    render.info_panel("content", title="title test", console=con)
    output = buf.getvalue()
    assert "title test" in output


# ---------------------------------------------------------------------------
# Tests: error_panel
# ---------------------------------------------------------------------------


def test_error_panel_contains_message() -> None:
    """error_panel includes the error message in the output."""
    con, buf = _console()
    render.error_panel("fatal error occurred", console=con)
    output = buf.getvalue()
    assert "fatal error occurred" in output


def test_error_panel_default_title() -> None:
    """error_panel default title is 'Error'."""
    con, buf = _console()
    render.error_panel("msg", console=con)
    output = buf.getvalue()
    assert "Error" in output


# ---------------------------------------------------------------------------
# Tests: warning_panel
# ---------------------------------------------------------------------------


def test_warning_panel_contains_message() -> None:
    """warning_panel includes the warning message in the output."""
    con, buf = _console()
    render.warning_panel("warning message XYZ", console=con)
    output = buf.getvalue()
    assert "warning message XYZ" in output


def test_warning_panel_default_title() -> None:
    """warning_panel default title is 'Warning'."""
    con, buf = _console()
    render.warning_panel("w", console=con)
    output = buf.getvalue()
    assert "Warning" in output


# ---------------------------------------------------------------------------
# Tests: thinking_panel
# ---------------------------------------------------------------------------


def test_thinking_panel_contains_content() -> None:
    """thinking_panel includes the content in the output."""
    con, buf = _console()
    render.thinking_panel("reasoning in progress...", console=con)
    output = buf.getvalue()
    assert "reasoning in progress" in output


# ---------------------------------------------------------------------------
# Tests: tool_call_panel
# ---------------------------------------------------------------------------


def test_tool_call_panel_tool_name() -> None:
    """tool_call_panel includes the tool name in the output."""
    con, buf = _console()
    render.tool_call_panel("physics_compute", console=con)
    output = buf.getvalue()
    assert "physics_compute" in output


def test_tool_call_panel_running_icon() -> None:
    """The ⟳ icon is present in the running state."""
    con, buf = _console(no_color=False)
    render.tool_call_panel("tool_x", status="running", console=con)
    output = buf.getvalue()
    assert "⟳" in output


def test_tool_call_panel_success_icon() -> None:
    """The ✓ icon is present in the success state."""
    con, buf = _console(no_color=False)
    render.tool_call_panel("tool_x", status="success", result="OK", console=con)
    output = buf.getvalue()
    assert "✓" in output


def test_tool_call_panel_failure_icon() -> None:
    """The ✗ icon is present in the failure state."""
    con, buf = _console(no_color=False)
    render.tool_call_panel("tool_x", status="failure", console=con)
    output = buf.getvalue()
    assert "✗" in output


def test_tool_call_panel_args() -> None:
    """tool_call_panel includes the args dictionary in the output."""
    con, buf = _console()
    render.tool_call_panel("tool_y", args={"param": "value_123"}, console=con)
    output = buf.getvalue()
    assert "param" in output
    assert "value_123" in output


# ---------------------------------------------------------------------------
# Tests: diff_panel
# ---------------------------------------------------------------------------


def test_diff_panel_contains_diff_text() -> None:
    """diff_panel includes the diff content in the output."""
    con, buf = _console()
    diff = "- old line\n+ new line"
    render.diff_panel(diff, console=con)
    output = buf.getvalue()
    assert "old line" in output
    assert "new line" in output


# ---------------------------------------------------------------------------
# Tests: spin_rule
# ---------------------------------------------------------------------------


def test_spin_rule_contains_arrows() -> None:
    """spin_rule contains ↑ and ↓."""
    con, buf = _console()
    render.spin_rule(console=con)
    output = buf.getvalue()
    assert "↑" in output
    assert "↓" in output


def test_spin_rule_contains_separator() -> None:
    """spin_rule contains the │ separator."""
    con, buf = _console()
    render.spin_rule(console=con)
    output = buf.getvalue()
    assert "│" in output


# ---------------------------------------------------------------------------
# Tests: make_console
# ---------------------------------------------------------------------------


def test_make_console_returns_console() -> None:
    """make_console returns a Console instance."""
    con = render.make_console()
    assert isinstance(con, Console)


def test_make_console_force_terminal() -> None:
    """A Console created with force_terminal=True has the force_terminal attribute set to True."""
    con = render.make_console(force_terminal=True, width=80)
    assert con.is_terminal or con.force_terminal  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests: print_tokens
# ---------------------------------------------------------------------------


def test_print_tokens_joins_output() -> None:
    """print_tokens outputs tokens in order."""
    con, buf = _console()
    render.print_tokens(["Hello", " ", "World"], console=con)
    output = buf.getvalue()
    assert "Hello" in output
    assert "World" in output


class TestPanelsSurviveBracketedText:
    """These panels render text from elsewhere — an exception, a model answer.

    Rich reads ``[/path]`` as a closing tag and raises MarkupError, so an
    unescaped panel would fail on exactly the message it was asked to report.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "cannot read [/etc/maglab/config]",
            "wrote [/Users/me/Desktop/fig.svg]",
            "stray [/bold] marker",
        ],
    )
    def test_error_panel_renders(self, text: str) -> None:
        buf = io.StringIO()
        render.error_panel(text, console=Console(file=buf, force_terminal=False, width=100))
        assert "etc" in buf.getvalue() or "Users" in buf.getvalue() or "bold" in buf.getvalue()

    def test_warning_panel_renders(self) -> None:
        buf = io.StringIO()
        render.warning_panel(
            "check [/dev/ttyUSB0]", console=Console(file=buf, force_terminal=False, width=100)
        )
        assert "ttyUSB0" in buf.getvalue()

    def test_thinking_panel_renders(self) -> None:
        buf = io.StringIO()
        render.thinking_panel(
            "considering [/tmp/a.json]", console=Console(file=buf, force_terminal=False, width=100)
        )
        assert "a.json" in buf.getvalue()

    def test_bracketed_title_is_safe_too(self) -> None:
        buf = io.StringIO()
        render.error_panel(
            "body", title="[/weird]", console=Console(file=buf, force_terminal=False, width=100)
        )
        assert "weird" in buf.getvalue()
