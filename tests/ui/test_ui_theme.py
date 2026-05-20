"""Theme system tests.

Validates loading and auto-detection of the four bundled theme YAML files
deterministically.

Validation principle: no LLM-as-judge — decisions are made solely by checking
palette values, names, and path existence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.ui.theme import Gradient, Palette, Theme

# ---------------------------------------------------------------------------
# Tests: loading the four bundled themes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("theme_name", ["domain", "mono", "moke", "light"])
def test_bundle_theme_loads(theme_name: str) -> None:
    """All four bundled themes load successfully."""
    theme = Theme.load(theme_name)
    assert theme.name == theme_name


@pytest.mark.parametrize("theme_name", ["domain", "mono", "moke", "light"])
def test_bundle_theme_has_palette(theme_name: str) -> None:
    """All four bundled themes have a valid palette."""
    theme = Theme.load(theme_name)
    assert isinstance(theme.palette, Palette)
    assert theme.palette.accent  # must not be empty


@pytest.mark.parametrize("theme_name", ["domain", "mono", "moke", "light"])
def test_bundle_theme_has_gradient(theme_name: str) -> None:
    """All four bundled themes have valid gradient information."""
    theme = Theme.load(theme_name)
    assert isinstance(theme.gradient, Gradient)
    assert theme.gradient.start
    assert theme.gradient.end


@pytest.mark.parametrize("theme_name", ["domain", "mono", "moke", "light"])
def test_bundle_theme_has_mode(theme_name: str) -> None:
    """All four bundled themes have a mode field."""
    theme = Theme.load(theme_name)
    assert theme.mode in ("dark", "light")


# ---------------------------------------------------------------------------
# Tests: domain theme palette values
# ---------------------------------------------------------------------------


def test_domain_theme_accent_color() -> None:
    """The domain theme accent colour is spin-up blue #38bdf8."""
    theme = Theme.load("domain")
    assert theme.palette.accent.lower() == "#38bdf8"


def test_domain_theme_spin_down_color() -> None:
    """The domain theme spin_down colour is rose #f43f5e."""
    theme = Theme.load("domain")
    assert theme.palette.spin_down.lower() == "#f43f5e"


def test_domain_gradient_start_end() -> None:
    """The domain theme gradient start and end colours are correct."""
    theme = Theme.load("domain")
    assert theme.gradient.start.lower() == "#38bdf8"
    assert theme.gradient.end.lower() == "#f43f5e"


# ---------------------------------------------------------------------------
# Tests: auto-detection (MAGLAB_THEME env)
# ---------------------------------------------------------------------------


def test_auto_detect_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """MAGLAB_THEME environment variable is used for auto-detection."""
    monkeypatch.setenv("MAGLAB_THEME", "mono")
    theme = Theme.load()
    assert theme.name == "mono"


def test_auto_detect_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default domain theme is loaded when MAGLAB_THEME is not set."""
    monkeypatch.delenv("MAGLAB_THEME", raising=False)
    theme = Theme.load()
    assert theme.name == "domain"


def test_env_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """MAGLAB_THEME=light selects the light theme."""
    monkeypatch.setenv("MAGLAB_THEME", "light")
    theme = Theme.load()
    assert theme.name == "light"


# ---------------------------------------------------------------------------
# Tests: NO_COLOR fallback
# ---------------------------------------------------------------------------


def test_no_color_fallback_clears_palette(monkeypatch: pytest.MonkeyPatch) -> None:
    """All palette colour fields are empty strings in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    theme = Theme.load("domain")
    assert theme.palette.accent == ""
    assert theme.palette.spin_down == ""
    assert theme.palette.success == ""
    assert theme.palette.warning == ""
    assert theme.palette.dim == ""


def test_no_color_fallback_clears_gradient(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gradient colours are empty strings in a NO_COLOR environment."""
    monkeypatch.setenv("NO_COLOR", "1")
    theme = Theme.load("domain")
    assert theme.gradient.start == ""
    assert theme.gradient.end == ""


# ---------------------------------------------------------------------------
# Tests: theme file existence
# ---------------------------------------------------------------------------


def test_bundle_yaml_files_exist() -> None:
    """All four bundled theme YAML files exist on disk."""
    bundle_dir = Path(__file__).parent.parent.parent / "themes"
    for name in ("domain", "mono", "moke", "light"):
        assert (bundle_dir / f"{name}.yaml").is_file(), f"{name}.yaml not found"


def test_available_themes_includes_all_four() -> None:
    """available_themes() returns all four themes."""
    themes = Theme.available_themes()
    for name in ("domain", "mono", "moke", "light"):
        assert name in themes


# ---------------------------------------------------------------------------
# Tests: non-existent theme
# ---------------------------------------------------------------------------


def test_nonexistent_theme_raises() -> None:
    """Loading a non-existent theme name raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        Theme.load("nonexistent_theme_xyz")


# ---------------------------------------------------------------------------
# Tests: Palette.get()
# ---------------------------------------------------------------------------


def test_palette_get_accent() -> None:
    """Palette.get('accent') returns the accent value."""
    p = Palette(accent="#aabbcc")
    assert p.get("accent") == "#aabbcc"


def test_palette_get_unknown_key_returns_empty() -> None:
    """Palette.get() returns an empty string for unknown keys."""
    p = Palette()
    assert p.get("unknown_key") == ""
