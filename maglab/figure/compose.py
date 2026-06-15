"""Multi-panel composition and layout (§12.3-④).

``FigureComposer`` implements the grid layout specification of ``FigureSpec``
using matplotlib ``GridSpec`` / ``subfigures``.

Key features:
- Creates GridSpec according to ``FigureSpec.layout``.
- Automatically inserts panel labels (a/b/c/d) in journal style.
- Computes figure dimensions to match journal column widths.
- Handles shared color scales, alignment, and padding via StyleProfile logic.
- Combines the axes returned by each panel renderer (``DataPlotRenderer``).
"""

# ruff: noqa: E402

from __future__ import annotations

import string
from typing import Any, cast

from maglab.figure.runtime import ensure_matplotlib_runtime_env

ensure_matplotlib_runtime_env()

import matplotlib
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

from maglab.figure.renderers.dataplot import DataPlotRenderer
from maglab.figure.renderers.schematic import SchematicRenderer
from maglab.figure.renderers.simviz import SimVizRenderer
from maglab.figure.spec import FigureSpec, PanelSpec, PanelType
from maglab.figure.styles import StyleProfile, load_style
from maglab.provenance.datapoint import DataPoint

# Force headless backend
matplotlib.use("Agg")

# Panel label alphabet sequence
_PANEL_LABELS = list(string.ascii_lowercase)


class FigureComposer:
    """Multi-panel figure composer.

    Parameters
    ----------
    style:
        ``StyleProfile`` instance. If ``None``, auto-loaded from ``FigureSpec.journal``.
    """

    def __init__(self, style: StyleProfile | None = None) -> None:
        self._style: StyleProfile | None = style
        self._schematic_renderer = SchematicRenderer()
        self._simviz_renderer = SimVizRenderer()

    def compose(
        self,
        spec: FigureSpec,
        ledger: dict[str, DataPoint],
    ) -> plt.Figure:
        """Render a ``FigureSpec`` and return a matplotlib Figure.

        Parameters
        ----------
        spec:
            ``FigureSpec`` IR.
        ledger:
            DataPoint ID → DataPoint lookup dictionary.

        Returns
        -------
        matplotlib.figure.Figure
            Fully rendered figure.

        Raises
        ------
        IntegrityError
            When a data-plot panel has missing DataPoint bindings.
        ValueError
            When a panel's GridSpec position is outside the layout bounds.
        """
        style = self._style or load_style(spec.journal.value)
        column = spec.column_width.value  # "single" or "double"
        rcparams = style.rcparams(column=column)

        figsize = style.figure_size(column=column)
        nrows = spec.layout.nrows
        ncols = spec.layout.ncols

        with plt.rc_context(cast(Any, rcparams)):
            fig = plt.figure(figsize=figsize)
            try:
                gs = gridspec.GridSpec(
                    nrows,
                    ncols,
                    figure=fig,
                    hspace=spec.layout.hspace,
                    wspace=spec.layout.wspace,
                )

                renderer = DataPlotRenderer(style_rcparams=rcparams)

                for idx, panel in enumerate(spec.panels):
                    ax = self._make_axes(fig, gs, panel, nrows, ncols)
                    self._render_panel(renderer, panel, ax, ledger)
                    self._add_panel_label(ax, idx, style, rcparams)
            except Exception:
                # HIGH-2 fix: close the figure on any rendering error so that
                # matplotlib's internal figure manager does not hold an orphaned
                # reference, preventing memory leaks in long-running sessions.
                plt.close(fig)
                raise

        return fig

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_axes(
        self,
        fig: plt.Figure,
        gs: gridspec.GridSpec,
        panel: PanelSpec,
        nrows: int,
        ncols: int,
    ) -> plt.Axes:
        """Create an Axes corresponding to the panel position and span in GridSpec."""
        pos = panel.grid_position
        row_end = pos.row + pos.row_span
        col_end = pos.col + pos.col_span

        if pos.row >= nrows or pos.col >= ncols:
            raise ValueError(
                f"Panel '{panel.panel_id}': grid_position (row={pos.row}, col={pos.col}) "
                f"is outside the layout ({nrows}×{ncols})."
            )
        # MEDIUM-2 fix: also validate that the span end stays within bounds.
        if row_end > nrows or col_end > ncols:
            raise ValueError(
                f"Panel '{panel.panel_id}': span [{pos.row}:{row_end}, {pos.col}:{col_end}] "
                f"exceeds layout bounds ({nrows}×{ncols})."
            )
        return fig.add_subplot(gs[pos.row : row_end, pos.col : col_end])

    def _render_panel(
        self,
        renderer: DataPlotRenderer,
        panel: PanelSpec,
        ax: plt.Axes,
        ledger: dict[str, DataPoint],
    ) -> None:
        """Dispatch rendering based on panel type."""
        import logging

        log = logging.getLogger(__name__)

        if panel.panel_type is PanelType.DATA_PLOT:
            renderer.render_panel(panel, ax, ledger)
        elif panel.panel_type is PanelType.SCHEMATIC:
            try:
                svg_string = self._schematic_renderer.render_panel(panel)
                import io

                import matplotlib.image as mpimg
                import numpy as np

                # Rasterize SVG to embed in the composed axes
                try:
                    import cairosvg

                    png_bytes = cairosvg.svg2png(bytestring=svg_string.encode("utf-8"))
                    img = mpimg.imread(io.BytesIO(png_bytes))  # type: ignore[arg-type]
                except Exception:  # noqa: BLE001
                    # Fallback: plain grey placeholder when cairosvg is unavailable
                    img = np.full((100, 100, 3), 0.9)
                ax.imshow(img, aspect="equal")
                ax.axis("off")
                if panel.title:
                    ax.set_title(panel.title)
            except Exception as exc:  # noqa: BLE001
                log.warning("SchematicRenderer failed for panel %r: %s", panel.panel_id, exc)
                ax.axis("off")
                ax.text(
                    0.5,
                    0.5,
                    f"[schematic error: {exc}]",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=7,
                    color="red",
                )
        elif panel.panel_type is PanelType.SIM_VIZ:
            try:
                self._simviz_renderer.render_panel(panel, ax)
            except Exception as exc:  # noqa: BLE001
                log.warning("SimVizRenderer failed for panel %r: %s", panel.panel_id, exc)
                ax.axis("off")
                ax.text(
                    0.5,
                    0.5,
                    f"[sim-viz error: {exc}]",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=7,
                    color="red",
                )

    def _add_panel_label(
        self,
        ax: plt.Axes,
        idx: int,
        style: StyleProfile,
        rcparams: dict[str, Any],
    ) -> None:
        """Insert a panel label (a/b/c/…) at the upper-left corner."""
        if idx >= len(_PANEL_LABELS):
            return
        label = _PANEL_LABELS[idx]
        fontsize = style.font_size("panel_label")
        ax.text(
            -0.12,
            1.05,
            label,
            transform=ax.transAxes,
            fontsize=fontsize,
            fontweight="bold",
            va="bottom",
            ha="left",
        )
