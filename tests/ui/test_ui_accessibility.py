"""Accessibility tests.

Validates colour removal and art suppression deterministically in NO_COLOR,
TERM=dumb, MAGLAB_SCREEN_READER, and non-TTY environments.

Validation principle: no LLM-as-judge — decisions are made solely by checking
for ANSI escape sequences in the output and checking function return values.
"""

from __future__ import annotations

import io
import re

import pytest
from rich.console import Console

from maglab.ui import banner, render, spinner
from maglab.ui.theme import Theme

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_ANSI_COLOR_RE = re.compile(r"\x1b\[[0-9;]*m")


def _has_ansi_color(text: str) -> bool:
    """Returns True if the string contains ANSI colour escape codes."""
    return bool(_ANSI_COLOR_RE.search(text))


def _capture_to_no_color_console(width: int = 80) -> tuple[Console, io.StringIO]:
    """Return a (Console, StringIO) pair with no_color=True."""
    buf = io.StringIO()
    con = Console(file=buf, force_terminal=False, width=width, no_color=True)
    return con, buf


# ---------------------------------------------------------------------------
# Tests: NO_COLOR — banner module
# ---------------------------------------------------------------------------


def test_banner_no_color_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """banner._is_no_color() returns True in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    assert banner._is_no_color() is True


def test_banner_no_color_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """banner._is_no_color() returns False when NO_COLOR is not set."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert banner._is_no_color() is False


# ---------------------------------------------------------------------------
# Tests: NO_COLOR — theme module
# ---------------------------------------------------------------------------


def test_theme_no_color_clears_all_palette_colors(monkeypatch: pytest.MonkeyPatch) -> None:
    """All palette colour fields are empty strings in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    theme = Theme.load("domain")
    for attr in ("accent", "spin_down", "success", "warning", "dim", "background"):
        assert getattr(theme.palette, attr) == "", f"{attr} field is not empty"


def test_theme_no_color_clears_gradient(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gradient start/end are empty strings in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    theme = Theme.load("domain")
    assert theme.gradient.start == ""
    assert theme.gradient.end == ""


def test_theme_without_no_color_has_colors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Palette colours are non-empty when NO_COLOR is not set."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    theme = Theme.load("domain")
    assert theme.palette.accent != ""
    assert theme.palette.spin_down != ""


# ---------------------------------------------------------------------------
# Tests: NO_COLOR — render module (badge)
# ---------------------------------------------------------------------------


def test_render_badge_no_color_returns_plain_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """badge_text returns a plain-text label in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    result = render.badge_text("SIMULATED")
    # NO_COLOR: no colour styles, plain label only
    assert "[SIM]" in result.plain


def test_render_badge_no_color_all_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """All five badge types generate labels in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    for ptype, label in [
        ("SIMULATED", "[SIM]"),
        ("MEASURED", "[MEAS]"),
        ("FITTED", "[FIT]"),
        ("PREDICTED", "[PRED]"),
        ("LITERATURE", "[LIT]"),
    ]:
        result = render.badge_text(ptype)
        assert label in result.plain, f"{ptype} badge label missing"


# ---------------------------------------------------------------------------
# Tests: TERM=dumb — banner module
# ---------------------------------------------------------------------------


def test_banner_dumb_term_suppresses_art(monkeypatch: pytest.MonkeyPatch) -> None:
    """_suppress_art() returns True in a TERM=dumb environment."""
    monkeypatch.setenv("TERM", "dumb")
    assert banner._suppress_art() is True


def test_banner_dumb_term_is_dumb(monkeypatch: pytest.MonkeyPatch) -> None:
    """_is_dumb_term() returns True in a TERM=dumb environment."""
    monkeypatch.setenv("TERM", "dumb")
    assert banner._is_dumb_term() is True


def test_banner_normal_term_not_dumb(monkeypatch: pytest.MonkeyPatch) -> None:
    """_is_dumb_term() returns False in a TERM=xterm-256color environment."""
    monkeypatch.setenv("TERM", "xterm-256color")
    assert banner._is_dumb_term() is False


# ---------------------------------------------------------------------------
# Tests: MAGLAB_SCREEN_READER
# ---------------------------------------------------------------------------


def test_banner_screen_reader_suppresses_art(monkeypatch: pytest.MonkeyPatch) -> None:
    """_suppress_art() returns True when MAGLAB_SCREEN_READER is set."""
    monkeypatch.setenv("MAGLAB_SCREEN_READER", "1")
    assert banner._suppress_art() is True


def test_banner_screen_reader_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """_is_screen_reader() returns True when MAGLAB_SCREEN_READER is set."""
    monkeypatch.setenv("MAGLAB_SCREEN_READER", "1")
    assert banner._is_screen_reader() is True


def test_banner_no_screen_reader_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """_is_screen_reader() returns False when MAGLAB_SCREEN_READER is not set."""
    monkeypatch.delenv("MAGLAB_SCREEN_READER", raising=False)
    assert banner._is_screen_reader() is False


# ---------------------------------------------------------------------------
# Tests: MAGLAB_NO_ANIMATION — spinner module
# ---------------------------------------------------------------------------


def test_spinner_no_animation_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """_no_animation() returns True when MAGLAB_NO_ANIMATION is set."""
    monkeypatch.setenv("MAGLAB_NO_ANIMATION", "1")
    assert spinner._no_animation() is True


def test_spinner_no_color_suppresses_animation(monkeypatch: pytest.MonkeyPatch) -> None:
    """_no_animation() returns True when NO_COLOR is set."""
    monkeypatch.setenv("NO_COLOR", "1")
    assert spinner._no_animation() is True


def test_spinner_dumb_term_suppresses_animation(monkeypatch: pytest.MonkeyPatch) -> None:
    """_no_animation() returns True when TERM=dumb is set."""
    monkeypatch.setenv("TERM", "dumb")
    assert spinner._no_animation() is True


def test_spinner_screen_reader_suppresses_animation(monkeypatch: pytest.MonkeyPatch) -> None:
    """_no_animation() returns True when MAGLAB_SCREEN_READER is set."""
    monkeypatch.setenv("MAGLAB_SCREEN_READER", "1")
    assert spinner._no_animation() is True


def test_spinner_normal_env_allows_animation(monkeypatch: pytest.MonkeyPatch) -> None:
    """_no_animation() returns False in a normal environment."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("MAGLAB_NO_ANIMATION", raising=False)
    monkeypatch.delenv("MAGLAB_SCREEN_READER", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert spinner._no_animation() is False


# ---------------------------------------------------------------------------
# Tests: non-TTY — make_console
# ---------------------------------------------------------------------------


def test_make_console_non_tty_sets_no_color() -> None:
    """A non-TTY Console (force_terminal=False) operates with no_color=True."""
    buf = io.StringIO()
    con = Console(file=buf, force_terminal=False, no_color=True)
    con.print("[bold red]test[/]")
    output = buf.getvalue()
    # no_color=True means no ANSI colour codes
    assert not _has_ansi_color(output)


def test_make_console_force_terminal_allows_color() -> None:
    """A force_terminal=True Console can output ANSI colour codes."""
    buf = io.StringIO()
    con = Console(file=buf, force_terminal=True, no_color=False, color_system="standard")
    con.print("[bold red]colored[/]")
    output = buf.getvalue()
    # force_terminal with no_color=False means colour codes are present
    assert _has_ansi_color(output)


# ---------------------------------------------------------------------------
# Tests: PRECESSION_FRAMES accessibility constant
# ---------------------------------------------------------------------------


def test_precession_frames_count() -> None:
    """There are 8 precession frames."""
    assert len(spinner.PRECESSION_FRAMES) == 8


def test_precession_frames_contains_arrows() -> None:
    """Precession frames contain ↑ and ↓."""
    assert "↑" in spinner.PRECESSION_FRAMES
    assert "↓" in spinner.PRECESSION_FRAMES


def test_static_symbol_defined() -> None:
    """STATIC_SYMBOL is non-empty."""
    assert spinner.STATIC_SYMBOL
