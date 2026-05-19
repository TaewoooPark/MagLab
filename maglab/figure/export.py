"""Vector export engine (§12.3-⑥).

``FigureExporter`` saves a matplotlib Figure as a vector file suitable for
journal submission.

Supported formats:
- PDF  : ``pdf.fonttype=42`` (Type 42 font embedding) — most common.
- EPS  : PostScript vector — required by some journals.
- SVG  : ``svg.fonttype="none"`` preserves text as text objects.
- TIFF : Raster (supports parallel export with journal-specified DPI).

P1 scope: matplotlib native vector output only. Inkscape headless is for P4 schematics.

Plan §12.3-⑥: The exported file path is recorded in the provenance ledger when
an optional ``ledger`` argument is supplied to ``export()`` / ``export_all()``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import matplotlib
import matplotlib.pyplot as plt

# Force headless backend
matplotlib.use("Agg")

if TYPE_CHECKING:
    from maglab.provenance.ledger import ProvenanceLedger

log = logging.getLogger(__name__)

# Supported format type literal
ExportFormat = Literal["pdf", "eps", "svg", "tiff", "png"]


class FigureExporter:
    """matplotlib Figure vector exporter.

    Parameters
    ----------
    dpi:
        DPI for raster (TIFF/PNG) export. Has no effect on PDF/EPS/SVG.
    """

    def __init__(self, dpi: int = 300) -> None:
        self.dpi = dpi

    def export(
        self,
        fig: plt.Figure,
        path: str | Path,
        fmt: ExportFormat = "pdf",
        dpi: int | None = None,
        ledger: ProvenanceLedger | None = None,
        figure_id: str | None = None,
    ) -> Path:
        """Export a Figure to a file.

        Parameters
        ----------
        fig:
            matplotlib Figure to export.
        path:
            Output file path (including extension).
        fmt:
            Output format — ``"pdf"``, ``"eps"``, ``"svg"``, ``"tiff"``, ``"png"``.
        dpi:
            Raster export DPI. If ``None``, uses ``self.dpi``.
        ledger:
            Optional ``ProvenanceLedger``. When supplied, the saved file path is
            recorded as an export activity (plan §12.3-⑥).
        figure_id:
            Optional figure identifier recorded alongside the export event.

        Returns
        -------
        Path
            Path of the saved file.

        Raises
        ------
        ValueError
            When an unsupported format is specified.
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        effective_dpi = dpi if dpi is not None else self.dpi

        if fmt == "pdf":
            # pdf.fonttype=42 is set via rcParams (see StyleProfile.rcparams)
            with plt.rc_context({"pdf.fonttype": 42, "ps.fonttype": 42}):
                fig.savefig(
                    out,
                    format=fmt,
                    bbox_inches="tight",
                    backend="pdf",
                )

        elif fmt == "eps":
            with plt.rc_context({"ps.fonttype": 42}):
                fig.savefig(
                    out,
                    format=fmt,
                    bbox_inches="tight",
                    backend="ps",
                )

        elif fmt == "svg":
            with plt.rc_context({"svg.fonttype": "none"}):
                fig.savefig(
                    out,
                    format=fmt,
                    bbox_inches="tight",
                    backend="svg",
                )

        elif fmt in {"tiff", "png"}:
            fig.savefig(
                out,
                format=fmt,
                bbox_inches="tight",
                dpi=effective_dpi,
            )

        else:
            raise ValueError(f"Unsupported format: '{fmt}'. Supported: pdf, eps, svg, tiff, png")

        # Record the export in the provenance ledger (plan §12.3-⑥).
        if ledger is not None:
            _record_export_in_ledger(ledger, out, fmt=fmt, figure_id=figure_id)

        return out

    def export_all(
        self,
        fig: plt.Figure,
        stem: str | Path,
        formats: list[ExportFormat] | None = None,
        dpi: int | None = None,
        ledger: ProvenanceLedger | None = None,
        figure_id: str | None = None,
    ) -> dict[str, Path]:
        """Export to multiple formats at once.

        Parameters
        ----------
        fig:
            matplotlib Figure to export.
        stem:
            File path stem without extension (e.g. ``"output/fig1"``).
        formats:
            List of formats to export. If ``None``, defaults to ``["pdf", "svg"]``.
        dpi:
            Raster DPI.
        ledger:
            Optional ``ProvenanceLedger``. When supplied, each saved file path is
            recorded as an export activity (plan §12.3-⑥).
        figure_id:
            Optional figure identifier recorded alongside each export event.

        Returns
        -------
        dict[str, Path]
            Format → saved path dictionary.
        """
        if formats is None:
            formats = ["pdf", "svg"]
        stem_path = Path(stem)
        results: dict[str, Path] = {}
        for fmt in formats:
            out_path = stem_path.with_suffix(f".{fmt}")
            results[fmt] = self.export(
                fig, out_path, fmt=fmt, dpi=dpi, ledger=ledger, figure_id=figure_id
            )
        return results


# ---------------------------------------------------------------------------
# Provenance helper
# ---------------------------------------------------------------------------


def _record_export_in_ledger(
    ledger: ProvenanceLedger,
    out_path: Path,
    *,
    fmt: str,
    figure_id: str | None,
) -> None:
    """Record a figure export event in the provenance ledger (plan §12.3-⑥).

    Creates a lightweight DataPoint entity whose ``source_ref`` carries the
    exported file path and whose ``activity_description`` notes the export format.

    Parameters
    ----------
    ledger:
        ``ProvenanceLedger`` to write into.
    out_path:
        Absolute or relative path of the saved figure file.
    fmt:
        Export format string (e.g. ``"pdf"``).
    figure_id:
        Optional figure identifier for traceability.
    """
    from maglab.provenance.datapoint import DataPoint, ProvenanceType

    try:
        export_dp = DataPoint(
            value=0.0,
            units="1",
            provenance_type=ProvenanceType.THEORY,
            source_ref=str(out_path.resolve()),
            conditions={
                "event": "figure_export",
                "format": fmt,
                "figure_id": figure_id or "",
                "path": str(out_path),
            },
        )
        ledger.record_datapoint(
            export_dp,
            activity_description=(
                f"Figure export — format={fmt!r}, path={str(out_path)!r}"
                + (f", figure_id={figure_id!r}" if figure_id else "")
            ),
        )
        log.debug("Provenance: recorded figure export %s → %s", figure_id or "", out_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Provenance export recording failed: %s", exc)
