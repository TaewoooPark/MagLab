"""Terminal theme system.

Loads the four bundled themes (domain · mono · moke · light) from
``themes/*.yaml`` and supports auto-detection
(``MAGLAB_THEME`` env → default domain).

Design rationale: §7.8 (plan/02-delivery.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import yaml

# ---------------------------------------------------------------------------
# Palette & gradient
# ---------------------------------------------------------------------------


@dataclass
class Palette:
    """Theme colour palette.

    All colours are returned as empty strings in ``NO_COLOR`` environments.
    """

    accent: str = "#38bdf8"
    spin_down: str = "#f43f5e"
    success: str = "#10b981"
    warning: str = "#f59e0b"
    dim: str = "#64748b"
    background: str = "#0f172a"

    def get(self, key: str) -> str:
        """Return a palette value by key."""
        return getattr(self, key, "")


@dataclass
class Gradient:
    """Banner magnetisation gradient colours (start · end hex)."""

    start: str = "#38bdf8"
    end: str = "#f43f5e"


@dataclass
class LogoStyle:
    """Theme-specific wordmark texture and ornament choices."""

    fill: str = "█"
    shade: str = "▓"
    motif: str = "solid"
    ornament: str = "✦"


# ---------------------------------------------------------------------------
# Theme model
# ---------------------------------------------------------------------------


@dataclass
class Theme:
    """Full theme model.

    :param name: Theme name (e.g. domain, mono, moke, light).
    :param mode: 'dark' or 'light'.
    :param palette: Colour palette.
    :param gradient: Banner gradient.
    """

    name: str = "domain"
    mode: str = "dark"
    palette: Palette = field(default_factory=Palette)
    gradient: Gradient = field(default_factory=Gradient)
    logo: LogoStyle = field(default_factory=LogoStyle)

    # Bundled theme directory (relative to the package root)
    _BUNDLE_DIR: ClassVar[Path] = Path(__file__).parent.parent.parent / "themes"

    # ---------------------------------------------------------------------------
    # Factory
    # ---------------------------------------------------------------------------

    @classmethod
    def load(cls, name: str | None = None) -> Theme:
        """Load a theme by name.

        When ``name`` is ``None``, auto-detection order is:
        ``MAGLAB_THEME`` env → default ``domain``.
        In ``NO_COLOR`` environments the palette is replaced with a
        monochrome (empty) palette.

        :param name: Theme name.  Auto-detected if None.
        :raises FileNotFoundError: When the requested theme file is not found.
        :returns: Loaded Theme instance.
        """
        resolved = cls._resolve_name(name)
        theme = cls._load_yaml(resolved)

        # NO_COLOR fallback: replace palette with empty strings
        if cls._no_color():
            theme.palette = Palette(
                accent="",
                spin_down="",
                success="",
                warning="",
                dim="",
                background="",
            )
            theme.gradient = Gradient(start="", end="")

        return theme

    @classmethod
    def _resolve_name(cls, name: str | None) -> str:
        """Resolve the theme name (priority: argument > env > default)."""
        if name:
            return name
        env = os.environ.get("MAGLAB_THEME", "").strip()
        return env if env else "domain"

    @classmethod
    def _load_yaml(cls, name: str) -> Theme:
        """Load the bundled themes/<name>.yaml file."""
        yaml_path = cls._BUNDLE_DIR / f"{name}.yaml"
        if not yaml_path.is_file():
            raise FileNotFoundError(f"Theme file not found: {yaml_path}  (name: {name!r})")
        with yaml_path.open(encoding="utf-8") as fh:
            data: dict = yaml.safe_load(fh) or {}

        palette_data = data.get("palette", {})
        gradient_data = data.get("gradient", {})
        logo_data = data.get("logo", {})

        return cls(
            name=data.get("name", name),
            mode=data.get("mode", "dark"),
            palette=Palette(
                accent=palette_data.get("accent", "#38bdf8"),
                spin_down=palette_data.get("spin_down", "#f43f5e"),
                success=palette_data.get("success", "#10b981"),
                warning=palette_data.get("warning", "#f59e0b"),
                dim=palette_data.get("dim", "#64748b"),
                background=palette_data.get("background", "#0f172a"),
            ),
            gradient=Gradient(
                start=gradient_data.get("start", "#38bdf8"),
                end=gradient_data.get("end", "#f43f5e"),
            ),
            logo=LogoStyle(
                fill=logo_data.get("fill", "█"),
                shade=logo_data.get("shade", "▓"),
                motif=logo_data.get("motif", "solid"),
                ornament=logo_data.get("ornament", "✦"),
            ),
        )

    # ---------------------------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------------------------

    @staticmethod
    def _no_color() -> bool:
        """Return True if the ``NO_COLOR`` environment variable is set."""
        return "NO_COLOR" in os.environ

    @staticmethod
    def available_themes() -> list[str]:
        """Return the list of bundled theme names."""
        bundle_dir = Path(__file__).parent.parent.parent / "themes"
        return sorted(p.stem for p in bundle_dir.glob("*.yaml"))
