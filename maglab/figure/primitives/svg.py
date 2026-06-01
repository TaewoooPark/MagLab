"""Shared SVG helpers for MagLab schematic primitives.

The catalog primitives intentionally stay dependency-light, but raw f-strings
make it easy to repeat escaping, number formatting, and style mistakes.  This
module centralizes the small pieces every primitive needs while still returning
plain SVG strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from math import isfinite
from typing import Any

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_NAMED_COLOR_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$")


@dataclass(frozen=True)
class SchematicStyle:
    """Visual tokens for schematic primitives.

    The values are SVG user units rather than points.  Renderers can map them to
    journal-specific output sizes by adjusting the outer viewBox.
    """

    font_family: str = "Arial, Helvetica, sans-serif"
    label_size: float = 9.0
    small_label_size: float = 7.0
    stroke_width: float = 0.8
    callout_width: float = 0.6
    arrow_width: float = 1.4
    axis_width: float = 1.2
    label_gap: float = 12.0
    palette: dict[str, str] | None = None

    def color(self, role: str, fallback: str) -> str:
        """Return a palette color for *role* or the fallback."""
        palette = self.palette or {}
        return palette.get(role, fallback)


@dataclass(frozen=True)
class SchematicFrame:
    """Named rectangular region for layout-first schematic drawing."""

    x: float
    y: float
    width: float
    height: float

    def inset(
        self,
        left: float = 0.0,
        top: float = 0.0,
        right: float = 0.0,
        bottom: float = 0.0,
    ) -> SchematicFrame:
        """Return a smaller frame inset from this one."""
        return SchematicFrame(
            self.x + left,
            self.y + top,
            max(0.0, self.width - left - right),
            max(0.0, self.height - top - bottom),
        )

    def point(self, x_frac: float, y_frac: float) -> tuple[float, float]:
        """Return a point inside the frame using fractional coordinates."""
        return self.x + self.width * x_frac, self.y + self.height * y_frac

    def anchor(self, name: str) -> tuple[float, float]:
        """Return a common compass/center anchor point."""
        anchors = {
            "center": (0.5, 0.5),
            "n": (0.5, 0.0),
            "e": (1.0, 0.5),
            "s": (0.5, 1.0),
            "w": (0.0, 0.5),
            "ne": (1.0, 0.0),
            "se": (1.0, 1.0),
            "sw": (0.0, 1.0),
            "nw": (0.0, 0.0),
        }
        frac_x, frac_y = anchors.get(name.lower(), anchors["center"])
        return self.point(frac_x, frac_y)


_BASE_PALETTE = {
    "heavy_metal": "#8f969e",
    "ferromagnet": "#c43c39",
    "oxide": "#eeeeee",
    "substrate": "#d9e8f6",
    "cap": "#7f858b",
    "current": "#c43c39",
    "voltage": "#237a4b",
    "field": "#275dad",
    "neutral": "#333333",
}


_STYLE_PROFILES = {
    "nature": SchematicStyle(palette=_BASE_PALETTE),
    "aps": SchematicStyle(label_size=8.5, small_label_size=7.0, palette=_BASE_PALETTE),
    "ieee": SchematicStyle(label_size=8.0, small_label_size=6.5, palette=_BASE_PALETTE),
    "elsevier": SchematicStyle(label_size=9.0, small_label_size=7.0, palette=_BASE_PALETTE),
}


def schematic_style(style: str = "nature") -> SchematicStyle:
    """Return a schematic style profile by journal key."""
    return _STYLE_PROFILES.get(str(style).lower(), _STYLE_PROFILES["nature"])


def normalize_frame(
    frame: object,
    *,
    canvas_width: float,
    canvas_height: float,
) -> SchematicFrame | None:
    """Normalize a frame spec into absolute SVG user units.

    A four-item frame whose values are all <= 1 is treated as fractions of the
    target canvas.  Larger values are treated as already being SVG user units.
    """
    if not isinstance(frame, (list, tuple)) or len(frame) != 4:
        return None
    try:
        x, y, width, height = [float(value) for value in frame]
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    if max(abs(x), abs(y), abs(width), abs(height)) <= 1.0:
        return SchematicFrame(
            x * canvas_width,
            y * canvas_height,
            width * canvas_width,
            height * canvas_height,
        )
    return SchematicFrame(x, y, width, height)


def fmt(value: float, digits: int = 1) -> str:
    """Format a finite SVG number compactly."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if not isfinite(number):
        number = 0.0
    text = f"{number:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def attr(value: Any) -> str:
    """Escape a value for an SVG attribute."""
    return escape(str(value), quote=True)


def text(value: Any) -> str:
    """Escape a value for SVG text node content."""
    return escape(str(value), quote=False)


def positive_float(
    params: dict[str, Any],
    name: str,
    default: float,
    *,
    minimum: float = 0.1,
    maximum: float | None = None,
) -> float:
    """Read a finite positive float from params and clamp to a sane range."""
    try:
        value = float(params.get(name, default))
    except (TypeError, ValueError):
        value = default
    if not isfinite(value):
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def color_value(raw: Any, fallback: str) -> str:
    """Return a safe SVG color value.

    Invalid user-supplied color strings fall back to the requested default.  The
    returned string is escaped for attribute insertion.
    """
    value = str(raw if raw is not None else fallback).strip()
    if not (_HEX_COLOR_RE.match(value) or _NAMED_COLOR_RE.match(value)):
        value = fallback
    return attr(value)


def tag(name: str, attrs: dict[str, Any], content: str | None = None) -> str:
    """Build a simple SVG/XML tag with escaped attributes."""
    attr_text = " ".join(
        f'{key.replace("_", "-")}="{attr(value)}"'
        for key, value in attrs.items()
        if value is not None
    )
    if content is None:
        return f"<{name} {attr_text}/>"
    return f"<{name} {attr_text}>{content}</{name}>"
