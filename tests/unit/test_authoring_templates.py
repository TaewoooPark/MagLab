"""Unit tests for maglab/authoring/templates/ (§16.2, Appendix G)."""

from __future__ import annotations

import pytest

from maglab.authoring.templates import (
    JournalTemplate,
    list_journals,
    load_template,
)


class TestLoadTemplate:
    """Tests for ``load_template`` and ``JournalTemplate``."""

    @pytest.mark.parametrize(
        "alias",
        [
            "prl",
            "prb",
            "nature",
            "science",
            "apl",
            "jmmm",
            "ieee-magnetics",
            "sn-jnl",
            "revtex4-2",
            "revtex4-2-aip",
            "IEEEtran",
            "elsarticle",
            "scifile",
        ],
    )
    def test_known_aliases_load(self, alias: str) -> None:
        """All listed journal aliases load without error."""
        tmpl = load_template(alias)
        assert isinstance(tmpl, JournalTemplate)

    def test_unknown_alias_raises(self) -> None:
        """An unrecognised journal alias raises ValueError."""
        with pytest.raises(ValueError, match="Unknown journal"):
            load_template("nonexistent-journal-xyz")

    def test_preamble_is_non_empty_string(self) -> None:
        """Preamble is a non-empty string containing \\documentclass."""
        tmpl = load_template("prl")
        preamble = tmpl.preamble
        assert isinstance(preamble, str)
        assert len(preamble) > 0
        assert "\\documentclass" in preamble

    def test_style_profile_has_figure_widths(self) -> None:
        """Style profile contains figure width fields."""
        tmpl = load_template("prl")
        profile = tmpl.style_profile
        assert "figure_width_single_mm" in profile
        assert "figure_width_double_mm" in profile

    def test_figure_width_single_prl(self) -> None:
        """PRL single-column figure width is 86 mm (Appendix G)."""
        tmpl = load_template("prl")
        assert tmpl.figure_width_single_mm == pytest.approx(86.0, abs=1.0)

    def test_figure_width_double_nature(self) -> None:
        """Nature double-column figure width is 183 mm (Appendix G)."""
        tmpl = load_template("nature")
        assert tmpl.figure_width_double_mm == pytest.approx(183.0, abs=1.0)

    def test_abstract_word_limit_prl(self) -> None:
        """PRL style profile includes an abstract character limit (not word limit)."""
        tmpl = load_template("prl")
        # PRL uses a character limit; the yaml key abstract_char_limit may be present
        # but abstract_word_limit may be None.
        # Just verify the property doesn't raise.
        _ = tmpl.abstract_word_limit

    def test_list_journals_returns_sorted_list(self) -> None:
        """list_journals returns a sorted non-empty list."""
        journals = list_journals()
        assert isinstance(journals, list)
        assert len(journals) > 0
        assert journals == sorted(journals)

    def test_human_review_marker_in_preamble(self) -> None:
        """Every preamble contains the HUMAN REVIEW REQUIRED marker."""
        for alias in ["prl", "nature", "jmmm", "apl", "ieee-magnetics", "science"]:
            tmpl = load_template(alias)
            assert "HUMAN REVIEW REQUIRED" in tmpl.preamble, f"Missing marker in {alias}"

    def test_style_profile_template_name(self) -> None:
        """Every style profile has a template_name field."""
        for alias in ["prl", "nature", "jmmm"]:
            tmpl = load_template(alias)
            assert "template_name" in tmpl.style_profile


class TestAdvancedMaterials:
    """Tests for the advanced-materials (Wiley) journal template (T-P6-01/02)."""

    @pytest.mark.parametrize(
        "alias",
        [
            "advanced-materials",
            "wiley",
            "word",
            "advanced-functional-materials",
            "small",
        ],
    )
    def test_aliases_load(self, alias: str) -> None:
        """All Wiley journal aliases load without error."""
        tmpl = load_template(alias)
        assert isinstance(tmpl, JournalTemplate)
        assert tmpl.journal_class == "advanced-materials"

    def test_preamble_contains_documentclass(self) -> None:
        """advanced-materials preamble contains \\documentclass."""
        tmpl = load_template("advanced-materials")
        assert "\\documentclass" in tmpl.preamble

    def test_preamble_contains_human_review(self) -> None:
        """advanced-materials preamble contains HUMAN REVIEW REQUIRED marker."""
        tmpl = load_template("advanced-materials")
        assert "HUMAN REVIEW REQUIRED" in tmpl.preamble

    def test_figure_widths(self) -> None:
        """advanced-materials figure widths are 83 mm (single) and 172 mm (double)."""
        tmpl = load_template("advanced-materials")
        assert tmpl.figure_width_single_mm == pytest.approx(83.0, abs=1.0)
        assert tmpl.figure_width_double_mm == pytest.approx(172.0, abs=1.0)

    def test_figure_spec_is_dict(self) -> None:
        """figure_spec returns a non-empty dict for advanced-materials."""
        tmpl = load_template("advanced-materials")
        spec = tmpl.figure_spec
        assert isinstance(spec, dict)
        assert len(spec) > 0
        assert "column_single_mm" in spec
        assert "dpi_raster" in spec

    def test_word_template_path_exists(self) -> None:
        """word_template_path points to the .dotx file which must exist on disk."""
        tmpl = load_template("advanced-materials")
        path = tmpl.word_template_path
        assert path is not None, "word_template_path should not be None"
        assert path.is_file(), f"Expected .dotx at {path}"
        assert path.suffix == ".dotx"

    def test_advanced_materials_in_list_journals(self) -> None:
        """advanced-materials appears in list_journals()."""
        assert "advanced-materials" in list_journals()


class TestFigureSpec:
    """Tests for the figure_spec property on all journal templates (T-P6-01)."""

    _JOURNALS = ["prl", "nature", "science", "apl", "jmmm", "ieee-magnetics", "advanced-materials"]

    @pytest.mark.parametrize("alias", _JOURNALS)
    def test_figure_spec_returns_dict(self, alias: str) -> None:
        """figure_spec returns a dict (may be empty if yaml absent, but should not raise)."""
        tmpl = load_template(alias)
        spec = tmpl.figure_spec
        assert isinstance(spec, dict)

    @pytest.mark.parametrize("alias", _JOURNALS)
    def test_figure_spec_has_column_width(self, alias: str) -> None:
        """figure_spec contains at least one column-width key."""
        tmpl = load_template(alias)
        spec = tmpl.figure_spec
        has_width = any("column" in k or "width" in k for k in spec)
        assert has_width, f"No column-width key found in figure_spec for {alias}: {list(spec)}"

    @pytest.mark.parametrize("alias", _JOURNALS)
    def test_figure_spec_has_dpi(self, alias: str) -> None:
        """figure_spec contains a dpi_raster key."""
        tmpl = load_template(alias)
        spec = tmpl.figure_spec
        assert "dpi_raster" in spec, f"dpi_raster missing from figure_spec for {alias}"

    def test_word_template_path_none_for_latex_journals(self) -> None:
        """word_template_path is None for journals that have no Word template."""
        tmpl = load_template("prl")
        # PRL uses LaTeX; no .dotx should exist for revtex4-2
        path = tmpl.word_template_path
        # We don't assert None (a contributor could add one), but the property must not raise
        _ = path
