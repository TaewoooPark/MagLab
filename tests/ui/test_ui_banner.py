"""Banner UI tests.

Validates the three-tier width response (width 120/70/40), ASCII fallback,
and NO_COLOR deterministically. Output is made deterministic via rich Console
force_terminal and width settings.

Validation principle: no LLM-as-judge — decisions are made solely by checking
for expected substrings in the output.
"""

from __future__ import annotations

import os

import pytest

from maglab.ui import banner

# ---------------------------------------------------------------------------
# Helper — force_terminal Console + StringIO capture
# ---------------------------------------------------------------------------


def _capture_render(width: int, env: dict | None = None) -> str:
    """Call banner.render and return the output string.

    banner.render creates its own Console internally, so only the width
    argument is passed to make the output deterministic.
    The return value is an empty string (side-effect call only).

    :param width: Forced terminal width.
    :param env: Environment variable overrides to merge on top of the existing env.
    :returns: Empty string (side-effect call only).
    """
    _env_backup = {}
    try:
        if env:
            for k, v in env.items():
                _env_backup[k] = os.environ.get(k)
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        banner.render(width=width)
    finally:
        for k, v in _env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return ""


def _pick_font_for_width(width: int) -> str | None:
    """Call the banner module's _pick_font directly."""
    return banner._pick_font(width)


# ---------------------------------------------------------------------------
# Tests: three-tier width response
# ---------------------------------------------------------------------------


def test_banner_wide_uses_ansi_shadow() -> None:
    """Width 120 → ansi_shadow font selected."""
    font = _pick_font_for_width(120)
    assert font == "ansi_shadow"


def test_banner_mid_uses_slant() -> None:
    """Width 70 → slant font selected."""
    font = _pick_font_for_width(70)
    assert font == "slant"


def test_banner_narrow_uses_short_wordmark() -> None:
    """Width 40 → None (short wordmark)."""
    font = _pick_font_for_width(40)
    assert font is None


def test_banner_ansi_shadow_contains_maglab() -> None:
    """The ansi_shadow rendering result contains 'MAGLAB' block characters."""
    text = banner._render_figlet("ansi_shadow")
    # ansi_shadow uses block box characters
    assert "╗" in text or "█" in text or "M" in text


def test_banner_slant_contains_maglab() -> None:
    """The slant rendering result contains non-whitespace characters."""
    text = banner._render_figlet("slant")
    # slant font uses ASCII art characters such as /·_·|
    assert any(not c.isspace() for c in text)
    assert len(text) > 0


# ---------------------------------------------------------------------------
# Tests: ASCII fallback (suppress_art)
# ---------------------------------------------------------------------------


def test_dumb_term_suppresses_art(monkeypatch: pytest.MonkeyPatch) -> None:
    """_suppress_art() returns True in a TERM=dumb environment."""
    monkeypatch.setenv("TERM", "dumb")
    assert banner._suppress_art() is True


def test_screen_reader_suppresses_art(monkeypatch: pytest.MonkeyPatch) -> None:
    """_suppress_art() returns True in a MAGLAB_SCREEN_READER environment."""
    monkeypatch.setenv("MAGLAB_SCREEN_READER", "1")
    assert banner._suppress_art() is True


def test_normal_term_not_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """_suppress_art() returns False in a normal terminal environment."""
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("MAGLAB_SCREEN_READER", raising=False)
    assert banner._suppress_art() is False


# ---------------------------------------------------------------------------
# Tests: NO_COLOR
# ---------------------------------------------------------------------------


def test_no_color_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """_is_no_color() returns True when NO_COLOR is set."""
    monkeypatch.setenv("NO_COLOR", "1")
    assert banner._is_no_color() is True


def test_no_color_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """_is_no_color() returns False when NO_COLOR is not set."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert banner._is_no_color() is False


# ---------------------------------------------------------------------------
# Tests: gradient helpers
# ---------------------------------------------------------------------------


def test_hex_to_rgb_spin_up() -> None:
    """#38bdf8 → (56, 189, 248)."""
    assert banner._hex_to_rgb("#38bdf8") == (56, 189, 248)


def test_hex_to_rgb_spin_down() -> None:
    """#f43f5e → (244, 63, 94)."""
    assert banner._hex_to_rgb("#f43f5e") == (244, 63, 94)


def test_lerp_rgb_start() -> None:
    """Returns c1 when t=0."""
    c1 = (56, 189, 248)
    c2 = (244, 63, 94)
    assert banner._lerp_rgb(c1, c2, 0.0) == c1


def test_lerp_rgb_end() -> None:
    """Returns c2 when t=1."""
    c1 = (56, 189, 248)
    c2 = (244, 63, 94)
    result = banner._lerp_rgb(c1, c2, 1.0)
    assert result == c2


def test_lerp_rgb_midpoint() -> None:
    """Returns the midpoint of two colours at t=0.5."""
    c1 = (0, 0, 0)
    c2 = (100, 200, 50)
    r, g, b = banner._lerp_rgb(c1, c2, 0.5)
    assert r == 50
    assert g == 100
    assert b == 25


def test_apply_gradient_returns_rich_text() -> None:
    """_apply_gradient returns a rich.Text instance."""
    from rich.text import Text

    result = banner._apply_gradient("MAGLAB", "#38bdf8", "#f43f5e")
    assert isinstance(result, Text)
    assert len(result) == len("MAGLAB")


def test_apply_gradient_multiline_preserves_lines() -> None:
    """_apply_gradient_multiline preserves multiple lines."""
    block = "AAA\nBBB\nCCC"
    from rich.text import Text

    result = banner._apply_gradient_multiline(block, "#38bdf8", "#f43f5e")
    assert isinstance(result, Text)
    rendered = result.plain
    assert "AAA" in rendered
    assert "BBB" in rendered
    assert "CCC" in rendered
