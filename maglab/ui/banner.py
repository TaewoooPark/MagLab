"""MagLab terminal banner.

Applies a magnetisation gradient (blue→red) to the bold solid block wordmark
"MAGLAB".  Three responsive tiers: width ≥ 100 → ansi_shadow / ≥ 60 → slant /
< 60 → short wordmark.

The gradient is implemented directly using rich ``Color`` / ``Style`` / ``Text``
by interpolating hex colours across the width (no rich-gradient dependency).

Design rationale: §7.4, §7.5 (plan/02-delivery.md).
Accessibility: NO_COLOR · TERM=dumb · MAGLAB_SCREEN_READER → suppress art and
colour, plain text.  Non-TTY → rich removes colour codes automatically.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.text import Text

    from maglab.ui.theme import Theme

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_WORDMARK_FULL = "MAGLAB"
_WORDMARK_SHORT = "▐ MAGLAB ▌"  # short wordmark for < 60 columns
_SUBTITLE = "magnetism · spintronics research copilot"

_FONT_FULL = "ansi_shadow"
_FONT_MID = "slant"


# ---------------------------------------------------------------------------
# Accessibility / environment checks
# ---------------------------------------------------------------------------


def _is_no_color() -> bool:
    """Return True if the ``NO_COLOR`` environment variable is set."""
    return "NO_COLOR" in os.environ


def _is_dumb_term() -> bool:
    """Return True if ``TERM=dumb``."""
    return os.environ.get("TERM", "").lower() == "dumb"


def _is_screen_reader() -> bool:
    """Return True if ``MAGLAB_SCREEN_READER`` is set."""
    return bool(os.environ.get("MAGLAB_SCREEN_READER", ""))


def _suppress_art() -> bool:
    """Return True if art/animation should be suppressed."""
    return _is_dumb_term() or _is_screen_reader()


# ---------------------------------------------------------------------------
# Gradient helpers
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert a hex string to an (R, G, B) integer tuple.

    :param hex_str: Hex colour string in '#RRGGBB' format.
    :returns: (r, g, b) integer tuple in the range 0–255.
    """
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp_rgb(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colours.

    :param c1: Start colour (R, G, B).
    :param c2: End colour (R, G, B).
    :param t: Interpolation factor (0.0–1.0).
    :returns: Interpolated (R, G, B).
    """
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _apply_gradient(text_str: str, start_hex: str, end_hex: str) -> Text:
    """Return a ``rich.Text`` with a hex gradient applied to ``text_str``.

    Each character position is linearly interpolated relative to the total
    width.  Spaces receive the same colour treatment.

    :param text_str: Source string to colourise.
    :param start_hex: Start colour hex.
    :param end_hex: End colour hex.
    :returns: ``rich.Text`` object with the gradient applied.
    """
    from rich.text import Text  # deferred import

    c1 = _hex_to_rgb(start_hex)
    c2 = _hex_to_rgb(end_hex)
    n = max(len(text_str) - 1, 1)

    result = Text()
    for i, ch in enumerate(text_str):
        t = i / n
        r, g, b = _lerp_rgb(c1, c2, t)
        result.append(ch, style=f"rgb({r},{g},{b})")
    return result


def _apply_gradient_multiline(
    block: str,
    start_hex: str,
    end_hex: str,
) -> Text:
    """Apply a per-line gradient to a multi-line block of text.

    Each line is processed independently so that block characters render
    correctly in the vertical dimension.

    :param block: Multi-line string (e.g. figlet output).
    :param start_hex: Start colour hex.
    :param end_hex: End colour hex.
    :returns: Combined ``rich.Text`` object.
    """
    from rich.text import Text

    lines = block.splitlines()
    result = Text()
    for idx, line in enumerate(lines):
        result.append_text(_apply_gradient(line, start_hex, end_hex))
        if idx < len(lines) - 1:
            result.append("\n")
    return result


# ---------------------------------------------------------------------------
# Font & width selection
# ---------------------------------------------------------------------------


def _pick_font(width: int) -> str | None:
    """Select a pyfiglet font based on terminal width.

    :param width: Terminal width in columns.
    :returns: Font name, or None to use the short wordmark.
    """
    if width >= 100:
        return _FONT_FULL
    if width >= 60:
        return _FONT_MID
    return None


def _render_figlet(font: str) -> str:
    """Generate the wordmark block string using pyfiglet.

    Falls back to an ASCII font when Unicode characters cannot be rendered.

    :param font: pyfiglet font name.
    :returns: Block character string.
    """
    import pyfiglet  # deferred import

    text = pyfiglet.figlet_format(_WORDMARK_FULL, font=font)
    # Retry with ASCII font if Unicode block characters are broken
    if "?" in text and "?" not in _WORDMARK_FULL:
        try:
            text = pyfiglet.figlet_format(_WORDMARK_FULL, font="banner")
        except pyfiglet.FontNotFound:
            text = _WORDMARK_FULL
    return text.rstrip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(theme: Theme | None = None, width: int | None = None) -> None:
    """Render the banner immediately and write it to stdout.

    Accessibility / environment checks:
    - ``NO_COLOR`` → plain text without gradient.
    - ``TERM=dumb`` / ``MAGLAB_SCREEN_READER`` → short plain-text wordmark.
    - Non-TTY → rich Console strips colour codes automatically.

    :param theme: Theme object.  Loaded automatically if None.
    :param width: Force a specific width.  Uses ``shutil.get_terminal_size()`` if None.
    """
    from rich.console import Console

    console = Console()

    # Dumb terminal / screen reader → plain short wordmark
    if _suppress_art():
        console.print(_WORDMARK_SHORT)
        console.print(_SUBTITLE)
        return

    # Detect width
    cols = width if width is not None else shutil.get_terminal_size(fallback=(80, 24)).columns

    font = _pick_font(cols)

    # Load theme
    if theme is None:
        from maglab.ui.theme import Theme

        theme = Theme.load()

    # Colour-less environment (NO_COLOR)
    if _is_no_color():
        if font is None:
            console.print(_WORDMARK_SHORT)
        else:
            block = _render_figlet(font)
            console.print(block)
        console.print(_SUBTITLE)
        return

    # Gradient banner
    start_hex = theme.gradient.start or "#38bdf8"
    end_hex = theme.gradient.end or "#f43f5e"

    if font is None:
        # Short wordmark (< 60 columns)
        gradient_text = _apply_gradient(_WORDMARK_SHORT, start_hex, end_hex)
        console.print(gradient_text)
    else:
        block = _render_figlet(font)
        gradient_text = _apply_gradient_multiline(block, start_hex, end_hex)
        console.print(gradient_text)

    # Subtitle
    dim_color = theme.palette.dim or "#64748b"
    console.print(f"[{dim_color}]{_SUBTITLE}[/]")
