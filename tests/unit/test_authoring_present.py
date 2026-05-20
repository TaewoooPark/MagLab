"""Unit tests for maglab/authoring/present/ — SlidesDrafter, PosterDrafter,
and the present/templates/ directory structure (T-P6-23)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.authoring.data_vault import DataVault
from maglab.authoring.present.catalog import (
    get_presentation_template,
    list_presentation_templates,
)
from maglab.authoring.present.poster_drafter import (
    _TEMPLATES_DIR as _POSTER_TEMPLATES_DIR,
)
from maglab.authoring.present.poster_drafter import (
    PosterDrafter,
)
from maglab.authoring.present.slide_drafter import (
    _TEMPLATES_DIR as _SLIDES_TEMPLATES_DIR,
)
from maglab.authoring.present.slide_drafter import (
    SlideDeck,
    SlideFormat,
    SlidesDrafter,
    SlideSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(response: str):
    """Return a mock LLM that always returns *response*."""

    def _llm(system: str, user: str) -> str:  # noqa: ARG001
        return response

    return _llm


_DUMMY_SLIDES_JSON = """{
  "slides": [
    {"title": "Introduction", "bullets": ["Context [FILL]"], "figure_placeholder": null, "notes": ""},
    {"title": "Results", "bullets": ["Metric: {{dp:HALL_RES}} Ω"], "figure_placeholder": "{{figure:SPEC}}", "notes": ""}
  ]
}"""

_DUMMY_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="841mm" height="1189mm">'
    "<text>[FILL: title]</text>"
    "</svg>"
)


# ---------------------------------------------------------------------------
# Template directory existence (T-P6-23)
# ---------------------------------------------------------------------------


class TestPresentTemplatesDirectory:
    """present/templates/ subdirectory and key files must exist."""

    @pytest.mark.parametrize(
        "subdir",
        ["beamer", "pptx", "marp", "beamerposter", "svg"],
    )
    def test_template_subdir_exists(self, subdir: str) -> None:
        """Each required present/templates/ subdirectory exists."""
        path = _SLIDES_TEMPLATES_DIR / subdir
        assert path.is_dir(), f"Missing present/templates/{subdir}/"

    def test_beamer_template_tex_exists(self) -> None:
        """beamer/template.tex exists."""
        assert (_SLIDES_TEMPLATES_DIR / "beamer" / "template.tex").is_file()

    def test_marp_template_md_exists(self) -> None:
        """marp/template.md exists."""
        assert (_SLIDES_TEMPLATES_DIR / "marp" / "template.md").is_file()

    def test_beamerposter_template_tex_exists(self) -> None:
        """beamerposter/template.tex exists."""
        assert (_SLIDES_TEMPLATES_DIR / "beamerposter" / "template.tex").is_file()

    def test_svg_template_exists(self) -> None:
        """svg/template.svg exists."""
        assert (_POSTER_TEMPLATES_DIR / "svg" / "template.svg").is_file()

    def test_poster_templates_dir_matches_slides_templates_dir(self) -> None:
        """SlidesDrafter and PosterDrafter share the same templates directory."""
        assert _SLIDES_TEMPLATES_DIR == _POSTER_TEMPLATES_DIR

    def test_beamer_template_contains_placeholder_tokens(self) -> None:
        """beamer/template.tex contains %%TITLE%%, %%AUTHOR%%, %%SLIDES%% tokens."""
        src = (_SLIDES_TEMPLATES_DIR / "beamer" / "template.tex").read_text(encoding="utf-8")
        for token in ("%%TITLE%%", "%%AUTHOR%%", "%%SLIDES%%"):
            assert token in src, f"Token {token!r} missing from beamer/template.tex"

    def test_marp_template_contains_placeholder_tokens(self) -> None:
        """marp/template.md contains %%TITLE%% and %%SLIDES%% tokens."""
        src = (_SLIDES_TEMPLATES_DIR / "marp" / "template.md").read_text(encoding="utf-8")
        for token in ("%%TITLE%%", "%%SLIDES%%"):
            assert token in src, f"Token {token!r} missing from marp/template.md"

    def test_svg_template_contains_human_review(self) -> None:
        """svg/template.svg contains HUMAN REVIEW REQUIRED."""
        src = (_POSTER_TEMPLATES_DIR / "svg" / "template.svg").read_text(encoding="utf-8")
        assert "HUMAN REVIEW REQUIRED" in src

    def test_beamer_template_contains_human_review_comment(self) -> None:
        """beamer/template.tex contains HUMAN REVIEW REQUIRED."""
        src = (_SLIDES_TEMPLATES_DIR / "beamer" / "template.tex").read_text(encoding="utf-8")
        assert "HUMAN REVIEW REQUIRED" in src


class TestPresentationTemplateCatalog:
    """Template profiles expose plan-level slide/poster references."""

    def test_catalog_lists_aps_and_beamerposter_profiles(self) -> None:
        names = {entry.name for entry in list_presentation_templates()}
        assert "aps-12min" in names
        assert "seminar" in names
        assert "aps-march-poster" in names
        assert "beamerposter-a0" in names

    def test_catalog_kind_filter(self) -> None:
        entries = list_presentation_templates("poster")
        assert entries
        assert all(entry.kind == "poster" for entry in entries)

    def test_catalog_alias_resolves_march_meeting(self) -> None:
        entry = get_presentation_template("march-meeting")
        assert entry.name == "aps-12min"
        assert "APS March Meeting" in entry.use_case

    def test_catalog_records_public_references(self) -> None:
        entry = get_presentation_template("aps-march-poster")
        assert entry.reference_urls
        assert any("aps.org" in url for url in entry.reference_urls)


# ---------------------------------------------------------------------------
# SlideDeck.to_beamer_tex — template loading
# ---------------------------------------------------------------------------


class TestSlidesDeckBeamer:
    """SlideDeck.to_beamer_tex uses the bundled template when present."""

    def _make_deck(self) -> SlideDeck:
        return SlideDeck(
            slides=[
                SlideSpec(title="Intro", bullets=["Item A"]),
                SlideSpec(
                    title="Results", bullets=["Item B"], figure_placeholder="{{figure:SPEC}}"
                ),
            ],
            format=SlideFormat.BEAMER,
        )

    def test_to_beamer_tex_loads_template(self) -> None:
        """to_beamer_tex output includes the template's \\usetheme{Madrid} line."""
        deck = self._make_deck()
        tex = deck.to_beamer_tex(title="My Talk", author="A. Researcher")
        # The bundled beamer/template.tex uses \usetheme{Madrid}
        assert "\\usetheme{Madrid}" in tex

    def test_to_beamer_tex_substitutes_title(self) -> None:
        """%%TITLE%% token is replaced by the supplied title."""
        deck = self._make_deck()
        tex = deck.to_beamer_tex(title="Spintronics Results")
        assert "Spintronics Results" in tex

    def test_to_beamer_tex_substitutes_slides(self) -> None:
        """Slide frames appear in the rendered output."""
        deck = self._make_deck()
        tex = deck.to_beamer_tex(title="Talk")
        assert "\\begin{frame}" in tex
        assert "Intro" in tex

    def test_to_beamer_tex_is_string(self) -> None:
        """to_beamer_tex returns a string."""
        deck = self._make_deck()
        assert isinstance(deck.to_beamer_tex(), str)


# ---------------------------------------------------------------------------
# SlideDeck.to_marp_markdown — template loading
# ---------------------------------------------------------------------------


class TestSlidesDeckMarp:
    """SlideDeck.to_marp_markdown uses the bundled marp template when present."""

    def _make_deck(self) -> SlideDeck:
        return SlideDeck(
            slides=[SlideSpec(title="Intro", bullets=["Point A"])],
            format=SlideFormat.MARP,
        )

    def test_to_marp_markdown_loads_template(self) -> None:
        """to_marp_markdown includes the marp: true frontmatter from the template."""
        deck = self._make_deck()
        md = deck.to_marp_markdown(title="My Presentation")
        assert "marp: true" in md

    def test_to_marp_markdown_substitutes_title(self) -> None:
        """%%TITLE%% token is replaced by the supplied title."""
        deck = self._make_deck()
        md = deck.to_marp_markdown(title="Spin Waves")
        assert "Spin Waves" in md

    def test_to_marp_markdown_is_string(self) -> None:
        """to_marp_markdown returns a string."""
        deck = self._make_deck()
        assert isinstance(deck.to_marp_markdown(), str)


# ---------------------------------------------------------------------------
# SlidesDrafter.draft_slides — end-to-end
# ---------------------------------------------------------------------------


class TestSlidesDrafter:
    """SlidesDrafter.draft_slides returns a SlideDeck."""

    def test_draft_slides_returns_deck(self, tmp_path: Path) -> None:
        """draft_slides with a valid JSON LLM response returns a SlideDeck."""
        vault = DataVault()
        drafter = SlidesDrafter(vault=vault, llm_fn=_make_llm(_DUMMY_SLIDES_JSON))
        deck = drafter.draft_slides("Hall resistivity: 1.2 Ω", fmt="beamer")
        assert isinstance(deck, SlideDeck)
        assert len(deck.slides) >= 1

    def test_draft_slides_fallback_on_bad_json(self, tmp_path: Path) -> None:
        """draft_slides falls back to a single-slide deck on JSON parse failure."""
        vault = DataVault()
        drafter = SlidesDrafter(vault=vault, llm_fn=_make_llm("NOT JSON"))
        deck = drafter.draft_slides("some results")
        assert len(deck.slides) == 1

    def test_export_beamer_writes_tex(self, tmp_path: Path) -> None:
        """export writes a .tex file when format is beamer."""
        vault = DataVault()
        drafter = SlidesDrafter(vault=vault, llm_fn=_make_llm(_DUMMY_SLIDES_JSON))
        deck = drafter.draft_slides("results", fmt="beamer")
        out = drafter.export(deck, tmp_path, title="Test Talk")
        assert out.suffix == ".tex"
        assert out.is_file()
        content = out.read_text(encoding="utf-8")
        assert "\\documentclass" in content or "\\usetheme" in content

    def test_export_writes_human_review_marker(self, tmp_path: Path) -> None:
        """export always writes HUMAN_REVIEW_REQUIRED.txt."""
        vault = DataVault()
        drafter = SlidesDrafter(vault=vault, llm_fn=_make_llm(_DUMMY_SLIDES_JSON))
        deck = drafter.draft_slides("results")
        drafter.export(deck, tmp_path)
        marker = tmp_path / "HUMAN_REVIEW_REQUIRED.txt"
        assert marker.is_file()
        assert "HUMAN REVIEW REQUIRED" in marker.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# PosterDrafter — SVG template loading
# ---------------------------------------------------------------------------


class TestPosterDrafter:
    """PosterDrafter loads svg/template.svg when available."""

    def test_draft_poster_uses_svg_template(self, tmp_path: Path) -> None:
        """draft_poster writes a .svg file that contains the template's SVG root."""
        vault = DataVault()

        # LLM should NOT be called when the SVG template exists
        def _should_not_be_called(s: str, u: str) -> str:
            raise AssertionError("LLM called even though SVG template exists")

        drafter = PosterDrafter(vault=vault, llm_fn=_should_not_be_called)
        poster = drafter.draft_poster(
            "Hall resistivity 1.2 Ω",
            title="Spintronics Poster",
            fmt="svg",
            output_dir=tmp_path,
        )
        assert poster.format == "svg"
        assert poster.path.is_file()
        content = poster.path.read_text(encoding="utf-8")
        assert "<svg" in content

    def test_draft_poster_substitutes_title(self, tmp_path: Path) -> None:
        """Title token %%TITLE%% is replaced in the SVG output."""
        vault = DataVault()
        drafter = PosterDrafter(vault=vault, llm_fn=_make_llm(_DUMMY_SVG))
        poster = drafter.draft_poster(
            "results",
            title="My Poster Title",
            fmt="svg",
            output_dir=tmp_path,
        )
        content = poster.path.read_text(encoding="utf-8")
        assert "My Poster Title" in content

    def test_draft_poster_writes_human_review_marker(self, tmp_path: Path) -> None:
        """draft_poster always writes HUMAN_REVIEW_REQUIRED.txt."""
        vault = DataVault()
        drafter = PosterDrafter(vault=vault, llm_fn=_make_llm(_DUMMY_SVG))
        drafter.draft_poster("results", fmt="svg", output_dir=tmp_path)
        marker = tmp_path / "HUMAN_REVIEW_REQUIRED.txt"
        assert marker.is_file()
        assert "HUMAN REVIEW REQUIRED" in marker.read_text(encoding="utf-8")

    def test_draft_poster_pdf_uses_template_then_converts_or_falls_back(
        self, tmp_path: Path
    ) -> None:
        """When fmt='pdf', the SVG template is used before PDF conversion fallback."""
        vault = DataVault()
        drafter = PosterDrafter(vault=vault, llm_fn=_make_llm(_DUMMY_SVG))
        # PDF conversion will likely fail (no cairosvg/Inkscape in CI)
        # but the method should not raise an unhandled exception
        poster = drafter.draft_poster("results", fmt="pdf", output_dir=tmp_path)
        # Either pdf or svg fallback is acceptable
        assert poster.path.is_file()

    def test_draft_poster_beamerposter_writes_tex(self, tmp_path: Path) -> None:
        """fmt='beamerposter' writes an A0 LaTeX poster source."""
        vault = DataVault()

        def _should_not_be_called(s: str, u: str) -> str:
            raise AssertionError("LLM called for beamerposter template")

        drafter = PosterDrafter(vault=vault, llm_fn=_should_not_be_called)
        poster = drafter.draft_poster(
            "A verified damping-like torque result.",
            title="Spin Torque Poster",
            fmt="beamerposter",
            output_dir=tmp_path,
        )
        assert poster.format == "beamerposter"
        assert poster.path.name == "poster.tex"
        content = poster.path.read_text(encoding="utf-8")
        assert "\\documentclass[final]{beamer}" in content
        assert "Spin Torque Poster" in content
        assert "A verified damping-like torque result." in content

    def test_draft_poster_aps_march_template_uses_8ft_board(self, tmp_path: Path) -> None:
        """APS March poster profile writes a 96 x 48 inch SVG canvas."""
        vault = DataVault()

        def _should_not_be_called(s: str, u: str) -> str:
            raise AssertionError("LLM called for APS March SVG template")

        drafter = PosterDrafter(vault=vault, llm_fn=_should_not_be_called)
        poster = drafter.draft_poster(
            "Verified result.",
            title="APS Poster",
            fmt="svg",
            template="aps-march-poster",
            output_dir=tmp_path,
        )
        content = poster.path.read_text(encoding="utf-8")
        assert 'width="96in" height="48in"' in content
        assert "APS Poster" in content
