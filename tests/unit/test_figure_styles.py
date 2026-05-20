"""tests/unit/test_figure_styles.py — Journal style profile unit tests."""

from __future__ import annotations

import pytest

from maglab.figure.styles import StyleProfile, available_journals, load_style

# Appendix G canonical dimensions (mm)
JOURNAL_WIDTHS = {
    "nature": {"single": 89.0, "double": 183.0},
    "aps": {"single": 86.0, "double": 178.0},
    "ieee": {"single": 88.9, "double": 182.0},
    "elsevier": {"single": 90.0, "double": 190.0},
}

_MM_TO_INCH = 1 / 25.4


# ---------------------------------------------------------------------------
# Journal YAML loading
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("journal", ["nature", "aps", "ieee", "elsevier"])
def test_load_style_returns_profile(journal: str):
    """Each journal YAML is loaded as a StyleProfile."""
    profile = load_style(journal)
    assert isinstance(profile, StyleProfile)
    assert profile.journal == journal


def test_load_style_unknown_raises():
    """An unknown journal raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_style("nonexistent_journal_xyz")


def test_available_journals():
    """available_journals() includes 4 journals."""
    journals = available_journals()
    assert set(journals) >= {"nature", "aps", "ieee", "elsevier"}


# ---------------------------------------------------------------------------
# Appendix G dimension conformance verification (normative source)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "journal,col,expected_mm",
    [
        ("nature", "single", 89.0),
        ("nature", "double", 183.0),
        ("aps", "single", 86.0),
        ("aps", "double", 178.0),
        ("ieee", "single", 88.9),
        ("ieee", "double", 182.0),
        ("elsevier", "single", 90.0),
        ("elsevier", "double", 190.0),
    ],
)
def test_column_width_mm(journal: str, col: str, expected_mm: float):
    """Column width (mm) matches the Appendix G reference value."""
    profile = load_style(journal)
    assert abs(profile.column_width_mm(col) - expected_mm) < 0.1, (
        f"{journal}/{col}: {profile.column_width_mm(col)} != {expected_mm} mm"
    )


@pytest.mark.parametrize(
    "journal,col,expected_mm",
    [
        ("nature", "single", 89.0),
        ("aps", "double", 178.0),
        ("ieee", "single", 88.9),
        ("elsevier", "double", 190.0),
    ],
)
def test_column_width_inch(journal: str, col: str, expected_mm: float):
    """Column width (inch) conversion is correct."""
    profile = load_style(journal)
    expected_inch = expected_mm * _MM_TO_INCH
    assert abs(profile.column_width_inch(col) - expected_inch) < 0.01


# ---------------------------------------------------------------------------
# figure_size()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("journal", ["nature", "aps", "ieee", "elsevier"])
def test_figure_size_shape(journal: str):
    """figure_size() returns a (width, height) tuple."""
    profile = load_style(journal)
    w, h = profile.figure_size("single")
    assert w > 0 and h > 0
    # width must match the single column width in inches
    expected_w = JOURNAL_WIDTHS[journal]["single"] * _MM_TO_INCH
    assert abs(w - expected_w) < 0.01


@pytest.mark.parametrize("ratio", [0.5, 0.75, 1.0])
def test_figure_size_aspect_ratio(ratio: float):
    """aspect_ratio is reflected in h/w."""
    profile = load_style("nature")
    w, h = profile.figure_size("single", aspect_ratio=ratio)
    assert abs(h / w - ratio) < 1e-6


# ---------------------------------------------------------------------------
# rcParams generation
# ---------------------------------------------------------------------------


def test_rcparams_includes_figure_size():
    """rcparams() result includes figure.figsize."""
    profile = load_style("nature")
    rc = profile.rcparams("single")
    assert "figure.figsize" in rc


def test_rcparams_fonttype_42():
    """pdf.fonttype=42 is set in rcparams (§12.3-⑥)."""
    profile = load_style("aps")
    rc = profile.rcparams("single")
    assert rc.get("pdf.fonttype") == 42, "pdf.fonttype is not 42 (font embedding requirement)."


def test_rcparams_svg_fonttype_none():
    """svg.fonttype='none' is set in rcparams."""
    profile = load_style("nature")
    rc = profile.rcparams("single")
    assert rc.get("svg.fonttype") == "none"


def test_rcparams_injected_to_matplotlib():
    """rcparams() result can be injected into matplotlib rc_context."""
    import matplotlib.pyplot as plt

    profile = load_style("elsevier")
    rc = profile.rcparams("double")
    with plt.rc_context(rc):
        fig, ax = plt.subplots()
        figsize = fig.get_size_inches()
    plt.close(fig)
    expected_w = JOURNAL_WIDTHS["elsevier"]["double"] * _MM_TO_INCH
    assert abs(figsize[0] - expected_w) < 0.01


# ---------------------------------------------------------------------------
# Palette, font sizes, line widths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("journal", ["nature", "aps", "ieee", "elsevier"])
def test_palette_nonempty(journal: str):
    """Palette is not empty."""
    profile = load_style(journal)
    assert len(profile.palette) >= 6


@pytest.mark.parametrize("journal", ["nature", "aps", "ieee", "elsevier"])
def test_font_size_positive(journal: str):
    """Font size is positive."""
    profile = load_style(journal)
    for key in ["label", "tick", "title", "panel_label"]:
        assert profile.font_size(key) > 0


@pytest.mark.parametrize("journal", ["nature", "aps", "ieee", "elsevier"])
def test_line_width_positive(journal: str):
    """Line width is positive."""
    profile = load_style(journal)
    assert profile.line_width("data") > 0
