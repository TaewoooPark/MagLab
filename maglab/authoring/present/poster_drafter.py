"""Poster drafter — A0 single-layout academic poster (§16.6).

Generates an SVG poster layout via LLM-authored SVG code (no raster AI models, §2.4).
All claims go through the honesty gate.  The researcher is the presenter.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from maglab.authoring.data_vault import DataVault

log = logging.getLogger(__name__)

HUMAN_REVIEW_MARKER = (
    "HUMAN REVIEW REQUIRED\n\n"
    "AI draft — the presenter bears full responsibility.\n"
    "Vector layout only — no raster AI image generation (§2.4).\n"
)

#: Directory containing bundled poster templates.
_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class PosterFile:
    """Result of a poster draft call."""

    path: Path
    format: str  # "svg" or "pdf"
    human_review_required: bool = True


class PosterDrafter:
    """Draft an A0 academic poster (§16.6).

    Parameters
    ----------
    vault:
        ``DataVault`` for placeholder resolution.
    llm_fn:
        LLM callable: ``(system_prompt, user_prompt) → str``.
    """

    _SYSTEM = (
        "You are an SVG poster layout designer for an academic conference poster.\n\n"
        "RULES:\n"
        "1. Produce valid SVG code for an A0 poster (841×1189 mm).\n"
        "2. Sections: Title/Authors → Introduction → Methods → Results → Conclusion.\n"
        "3. Use placeholder text {{figure:SPEC}} where figures should appear.\n"
        "4. Use {{dp:KEY}} for numerical values from the data vault.\n"
        "5. Do NOT invent numbers, results, or graphics.\n"
        "6. Raster AI image generation is prohibited (§2.4).\n"
        "7. Mark author names and affiliations with [FILL].\n"
    )

    def __init__(self, vault: DataVault, llm_fn: Callable[[str, str], str]) -> None:
        self._vault = vault
        self._llm = llm_fn

    @staticmethod
    def _load_template_file(subdir: str, filename: str) -> str | None:
        """Load a bundled poster template file.

        Returns the file contents as a string, or ``None`` if the file is
        absent (caller falls back to inline/LLM generation).
        """
        path = _TEMPLATES_DIR / subdir / filename
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return None

    def draft_poster(
        self,
        results: str,
        *,
        size: str = "A0",
        fmt: str = "svg",
        output_dir: Path | None = None,
        title: str = "[FILL: poster title]",
    ) -> PosterFile:
        """Draft a poster SVG layout.

        Parameters
        ----------
        results:
            Researcher-provided results summary.
        size:
            Poster size (default "A0").
        fmt:
            Output format: "svg" (default) or "pdf" (requires cairosvg/Inkscape).
        output_dir:
            Directory to write output files.
        title:
            Poster title.

        Returns
        -------
        ``PosterFile``.
        """
        import datetime
        import tempfile

        if output_dir is None:
            _tmp = tempfile.mkdtemp(prefix="maglab_poster_")
            output_dir = Path(_tmp)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write HUMAN_REVIEW_REQUIRED marker
        (output_dir / "HUMAN_REVIEW_REQUIRED.txt").write_text(HUMAN_REVIEW_MARKER, encoding="utf-8")

        # Try loading the bundled SVG template first (T-P6-23).
        # Fall back to LLM inline generation if the template is absent.
        template_src = self._load_template_file("svg", "template.svg")
        if template_src is not None and fmt == "svg":
            log.debug("PosterDrafter: using svg/template.svg")
            today = datetime.date.today().isoformat()
            svg_raw = (
                template_src.replace("%%TITLE%%", title)
                .replace("%%DATE%%", today)
            )
        else:
            user = (
                f"Poster size: {size}\n"
                f"Title: {title}\n\n"
                f"Results:\n{results}\n\n"
                "Produce a valid SVG poster layout with section panels for "
                "Introduction, Methods, Results, and Conclusion.  "
                "Use placeholder text for figures and mark author info with [FILL]."
            )
            svg_raw = self._llm(self._SYSTEM, user)

        # Resolve data vault placeholders in the SVG
        missing = self._vault.validate_draft(svg_raw)
        if missing:
            log.warning("Poster draft: DataVault missing keys %s — leaving placeholders.", missing)
        else:
            svg_raw = self._vault.inject_into_draft(svg_raw)

        # Ensure the output is wrapped in SVG tags if the LLM omitted them
        svg_content = self._ensure_svg_wrapper(svg_raw, size)

        svg_path = output_dir / "poster.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        if fmt == "pdf":
            pdf_path = self._convert_to_pdf(svg_path, output_dir)
            if pdf_path is not None:
                return PosterFile(path=pdf_path, format="pdf")
            log.warning("PDF conversion failed — returning SVG.")

        return PosterFile(path=svg_path, format="svg")

    @staticmethod
    def _ensure_svg_wrapper(raw: str, size: str) -> str:
        """Wrap raw content in SVG tags if not already present."""
        import re

        if re.search(r"<svg", raw, re.IGNORECASE):
            return raw
        # A0 dimensions in mm → converted to px at 96 dpi
        # A0: 841 × 1189 mm → 3179 × 4493 px at 96 dpi
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="841mm" height="1189mm" '
            'viewBox="0 0 3179 4493">\n'
            f"<!-- MagLab AI draft poster — {size} — HUMAN REVIEW REQUIRED -->\n"
            f"{raw}\n"
            "</svg>\n"
        )

    @staticmethod
    def _convert_to_pdf(svg_path: Path, output_dir: Path) -> Path | None:
        """Convert SVG to PDF using cairosvg or Inkscape CLI."""
        pdf_path = output_dir / "poster.pdf"

        # Try cairosvg first
        try:
            import cairosvg  # type: ignore[import-untyped]

            cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
            return pdf_path
        except ImportError:
            pass
        except Exception as exc:
            log.warning("cairosvg conversion failed: %s", exc)

        # Try Inkscape CLI
        import subprocess

        try:
            result = subprocess.run(
                ["inkscape", str(svg_path), "--export-type=pdf", f"--export-filename={pdf_path}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and pdf_path.is_file():
                return pdf_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None
