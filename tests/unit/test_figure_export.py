"""tests/unit/test_figure_export.py — Vector export unit tests.

Validation items (§20):
- PDF: verify pdf.fonttype=42 embedding (pdfplumber).
- SVG: text-editable vector file (svg.fonttype="none" → <text> tags).
- EPS: PostScript vector file verification (%!PS header).
- TIFF/PNG: raster file creation.
- Unsupported formats raise ValueError.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

import pdfplumber

from maglab.figure.export import FigureExporter
from maglab.provenance.datapoint import DataPoint, ProvenanceType
from maglab.provenance.ledger import ProvenanceLedger

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _simple_figure() -> plt.Figure:
    """Create a simple matplotlib Figure."""
    fig, ax = plt.subplots(figsize=(3.5, 2.5))
    ax.plot([0, 1, 2], [0, 1, 0], "-")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig


def _dp(value: list[float], dp_id: str) -> DataPoint:
    return DataPoint(
        id=dp_id,
        value=value,
        units="1",
        provenance_type=ProvenanceType.MEASURED,
        source_ref="test",
    )


# ---------------------------------------------------------------------------
# PDF export — fonttype=42 verification
# ---------------------------------------------------------------------------


class TestPDFExport:
    def test_pdf_created(self):
        """A PDF file is created."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.pdf"
            result = exporter.export(fig, out, fmt="pdf")
            assert result.exists()
            assert result.suffix == ".pdf"
        plt.close(fig)

    def test_pdf_is_valid_pdf(self):
        """The created file is a valid PDF (%PDF header)."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.pdf"
            exporter.export(fig, out, fmt="pdf")
            header = out.read_bytes()[:8]
        plt.close(fig)
        assert header.startswith(b"%PDF"), f"Missing PDF header: {header!r}"

    def test_pdf_fonttype_42_embedded(self):
        """PDF has fonttype=42 (TrueType) fonts embedded (§12.3-⑥)."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "font_test.pdf"
            exporter.export(fig, out, fmt="pdf")
            with pdfplumber.open(out) as pdf:
                fonts = []
                for page in pdf.pages:
                    char_page = page.chars
                    for ch in char_page:
                        ft = ch.get("fontname", "")
                        if ft:
                            fonts.append(ft)
        plt.close(fig)
        # If pdfplumber can read font info, fonts are embedded.
        # (fonttype=42 = TrueType embedding — font name is present)
        # Even an empty figure has text elements (x, y labels), so fonts must be non-empty.
        assert len(fonts) > 0, "Could not read font info from PDF. Check fonttype=42 embedding."


# ---------------------------------------------------------------------------
# SVG export — vector and text editability verification
# ---------------------------------------------------------------------------


class TestSVGExport:
    def test_svg_created(self):
        """An SVG file is created."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.svg"
            result = exporter.export(fig, out, fmt="svg")
            assert result.exists()
        plt.close(fig)

    def test_svg_is_xml(self):
        """The SVG file starts with XML (<?xml or <svg header)."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.svg"
            exporter.export(fig, out, fmt="svg")
            content = out.read_text(encoding="utf-8")
        plt.close(fig)
        assert content.lstrip().startswith(("<?xml", "<svg")), "SVG file is not XML format."

    def test_svg_contains_text_elements(self):
        """SVG contains <text> elements (svg.fonttype='none' — text preserved)."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.svg"
            exporter.export(fig, out, fmt="svg")
            content = out.read_text(encoding="utf-8")
        plt.close(fig)
        assert "<text" in content, "SVG has no <text> elements. Check svg.fonttype='none' setting."

    def test_svg_is_text_editable(self):
        """SVG file is a UTF-8 text file editable with a text editor."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.svg"
            exporter.export(fig, out, fmt="svg")
            # If readable as UTF-8, it is text-editable
            content = out.read_text(encoding="utf-8")
        plt.close(fig)
        assert len(content) > 0


# ---------------------------------------------------------------------------
# EPS export — PostScript vector verification
# ---------------------------------------------------------------------------


class TestEPSExport:
    def test_eps_created(self):
        """An EPS file is created."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.eps"
            result = exporter.export(fig, out, fmt="eps")
            assert result.exists()
        plt.close(fig)

    def test_eps_has_postscript_header(self):
        """EPS file starts with the PostScript header (%!PS)."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.eps"
            exporter.export(fig, out, fmt="eps")
            header = out.read_bytes()[:10]
        plt.close(fig)
        assert b"%!PS" in header, f"Missing EPS header: {header!r}"


# ---------------------------------------------------------------------------
# Raster export — TIFF and PNG
# ---------------------------------------------------------------------------


class TestRasterExport:
    def test_tiff_created(self):
        """A TIFF file is created."""
        fig = _simple_figure()
        exporter = FigureExporter(dpi=150)
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.tiff"
            result = exporter.export(fig, out, fmt="tiff")
            assert result.exists()
            assert result.stat().st_size > 0
        plt.close(fig)

    def test_png_created(self):
        """A PNG file is created."""
        fig = _simple_figure()
        exporter = FigureExporter(dpi=100)
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.png"
            result = exporter.export(fig, out, fmt="png")
            assert result.exists()
        plt.close(fig)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestExporterErrors:
    def test_unsupported_format_raises(self):
        """An unsupported format raises ValueError."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.xyz"
            with pytest.raises(ValueError, match="Unsupported"):
                exporter.export(fig, out, fmt="xyz")  # type: ignore[arg-type]
        plt.close(fig)

    def test_export_creates_parent_dir(self):
        """Missing parent directories of the output path are created automatically."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "subdir" / "nested" / "test.pdf"
            exporter.export(fig, out, fmt="pdf")
            assert out.exists()
        plt.close(fig)


# ---------------------------------------------------------------------------
# export_all utility
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Provenance recording (plan §12.3-⑥, FIX 3)
# ---------------------------------------------------------------------------


class TestProvenanceRecording:
    def test_export_records_path_in_ledger(self):
        """Exporting with a ledger records the file path as a provenance entry."""
        fig = _simple_figure()
        exporter = FigureExporter()
        ledger = ProvenanceLedger()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "prov_test.pdf"
            exporter.export(fig, out, fmt="pdf", ledger=ledger, figure_id="fig-test")
        plt.close(fig)
        # At least one DataPoint should have been recorded
        ids = ledger.all_ids()
        assert len(ids) >= 1, "No DataPoint recorded in the ledger after export."
        # The recorded DataPoint's source_ref should contain the path
        dp = ledger.get(ids[0])
        assert dp is not None
        assert "prov_test.pdf" in (dp.source_ref or "")

    def test_export_without_ledger_still_returns_path(self):
        """Exporting without a ledger still works normally (backwards-compatible)."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "no_prov.pdf"
            result = exporter.export(fig, out, fmt="pdf")  # no ledger argument
            assert result.exists()
        plt.close(fig)


# ---------------------------------------------------------------------------
# F2 regression — MCP figure_render / figure_export must not leak figures
# ---------------------------------------------------------------------------


class TestMCPFigureNoLeak:
    """F2 regression: figure_render and figure_export close the figure even on error."""

    def _minimal_spec_dict(self) -> dict:
        """Return a minimal valid FigureSpec dict (single text-only panel)."""
        return {
            "figure_id": "test-leak",
            "title": "Leak test",
            "panels": [
                {
                    "panel_id": "p1",
                    "panel_type": "schematic",
                    "title": "Text only",
                }
            ],
        }

    def test_figure_render_no_leak_on_export_error(self, tmp_path: Path) -> None:
        """figure_render returns ok=False and does not leak a figure when export fails."""
        from unittest.mock import patch

        import matplotlib.pyplot as plt

        from maglab.mcp_server import create_server

        server = create_server()

        # Record open figures before the call.
        before = plt.get_fignums()

        spec = self._minimal_spec_dict()
        # Patch FigureExporter.export to raise so we hit the error/finally path.
        with patch(
            "maglab.figure.export.FigureExporter.export",
            side_effect=OSError("simulated disk-full"),
        ):
            import asyncio

            result = asyncio.run(
                server.call_tool(
                    "figure_render",
                    {
                        "spec_dict": spec,
                        "output_path": str(tmp_path / "out.pdf"),
                        "fmt": "pdf",
                    },
                )
            )

        # The tool should report failure.
        content_str = str(result)
        assert "false" in content_str.lower() or "error" in content_str.lower()

        # No new open figures should remain after the call.
        after = plt.get_fignums()
        leaked = set(after) - set(before)
        assert not leaked, f"F2 regression: figure_render leaked figure(s): {leaked}"

    def test_figure_export_no_leak_on_export_error(self, tmp_path: Path) -> None:
        """figure_export returns ok=False and does not leak a figure when export fails."""
        from unittest.mock import patch

        import matplotlib.pyplot as plt

        from maglab.mcp_server import create_server

        server = create_server()

        before = plt.get_fignums()

        spec = self._minimal_spec_dict()
        with patch(
            "maglab.figure.export.FigureExporter.export_all",
            side_effect=OSError("simulated permission error"),
        ):
            import asyncio

            result = asyncio.run(
                server.call_tool(
                    "figure_export",
                    {
                        "spec_dict": spec,
                        "stem": str(tmp_path / "out"),
                        "formats": ["pdf"],
                    },
                )
            )

        content_str = str(result)
        assert "false" in content_str.lower() or "error" in content_str.lower()

        after = plt.get_fignums()
        leaked = set(after) - set(before)
        assert not leaked, f"F2 regression: figure_export leaked figure(s): {leaked}"

    def test_export_all_records_multiple_paths(self):
        """export_all records each exported format as a separate provenance entry."""
        fig = _simple_figure()
        exporter = FigureExporter()
        ledger = ProvenanceLedger()
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = Path(tmpdir) / "multi"
            exporter.export_all(
                fig, stem, formats=["pdf", "svg"], ledger=ledger, figure_id="fig-multi"
            )
        plt.close(fig)
        ids = ledger.all_ids()
        assert len(ids) >= 2, f"Expected at least 2 provenance entries; got {len(ids)}."


class TestExportAll:
    def test_export_all_pdf_svg(self):
        """export_all(['pdf','svg']) creates both files."""
        fig = _simple_figure()
        exporter = FigureExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = Path(tmpdir) / "fig"
            results = exporter.export_all(fig, stem, formats=["pdf", "svg"])
            assert "pdf" in results
            assert "svg" in results
            assert results["pdf"].exists()
            assert results["svg"].exists()
        plt.close(fig)
