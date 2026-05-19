"""matplotlib data-plot renderer (§12.3-②).

``DataPlotRenderer`` renders the data-plot panels of a ``FigureSpec`` into
matplotlib ``Axes``. Supported plot types:

- ``hysteresis``  : M-H hysteresis loop.
- ``hall``        : Hall resistivity ρ_xy vs H.
- ``fmr``         : FMR absorption / frequency dependence.
- ``dispersion``  : Dispersion relation ω-k.
- ``xy``          : Generic XY plot.

Core integrity rules (§12.6):
- Data comes **only** from ``DataPoint`` objects fetched from a ``ProvenanceLedger``.
- If the LLM inserts numbers directly or data_point_ids is empty, ``IntegrityError``
  is raised to block rendering.
- There is no code path in this file that calls raster generative image models.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure as MplFigure

from maglab.figure.spec import PanelSpec, PlotKind
from maglab.provenance.datapoint import DataPoint

# Force headless backend (server / CI)
matplotlib.use("Agg")


class IntegrityError(ValueError):
    """Data-plot integrity violation — attempted use of unbound data."""


def _require_datapoints(
    panel: PanelSpec,
    ledger: dict[str, DataPoint],
) -> list[DataPoint]:
    """Fetch the panel's DataPoints and verify integrity.

    Parameters
    ----------
    panel:
        Panel specification to render.
    ledger:
        DataPoint ID → DataPoint lookup dictionary (ProvenanceLedger cache or direct dict).

    Returns
    -------
    list[DataPoint]
        Bound DataPoint list.

    Raises
    ------
    IntegrityError
        - When ``data_point_ids`` is empty.
        - When a referenced ID is not present in the ledger.
    """
    if not panel.data_point_ids:
        raise IntegrityError(
            f"Panel '{panel.panel_id}': data_point_ids is empty. "
            "Data-plot panels must be bound to a DataPoint (§12.6)."
        )
    result: list[DataPoint] = []
    for dp_id in panel.data_point_ids:
        dp = ledger.get(dp_id)
        if dp is None:
            raise IntegrityError(
                f"Panel '{panel.panel_id}': DataPoint ID '{dp_id}' is not in the "
                "ledger. Register it first with ProvenanceLedger.record_datapoint()."
            )
        result.append(dp)
    return result


def _extract_xy(
    dps: list[DataPoint],
) -> tuple[np.ndarray, np.ndarray]:
    """Extract x and y arrays from a list of DataPoints.

    Interpretation rules:
    - Length 1 : if value is an array, plot index vs value; if scalar, single point.
    - Length 2 : dps[0] = x array, dps[1] = y array.
    - Length >= 2 with all scalars : x = index, y = value.
    """
    if len(dps) == 2:
        x_raw = dps[0].value
        y_raw = dps[1].value
        x = np.asarray(x_raw if isinstance(x_raw, list) else [x_raw], dtype=float)
        y = np.asarray(y_raw if isinstance(y_raw, list) else [y_raw], dtype=float)
        return x, y

    if len(dps) == 1:
        v = dps[0].value
        if isinstance(v, list):
            y = np.asarray(v, dtype=float)
            x = np.arange(len(y), dtype=float)
        else:
            y = np.array([float(v)])
            x = np.array([0.0])
        return x, y

    # Length >= 2 with all scalars: x = index, y = value
    xs: list[float] = []
    ys: list[float] = []
    for i, dp in enumerate(dps):
        if isinstance(dp.value, list):
            warnings.warn(
                f"DataPoint {dp.id} is an array; using only the first element.",
                UserWarning,
                stacklevel=3,
            )
            ys.append(float(dp.value[0]))
        else:
            ys.append(float(dp.value))
        xs.append(float(i))
    return np.array(xs), np.array(ys)


class DataPlotRenderer:
    """DataPoint-based matplotlib data-plot renderer.

    Parameters
    ----------
    style_rcparams:
        Journal style rcParams dictionary (result of ``StyleProfile.rcparams()``).
        If ``None``, uses matplotlib defaults.
    """

    def __init__(self, style_rcparams: dict[str, Any] | None = None) -> None:
        self._rcparams: dict[str, Any] = style_rcparams or {}

    def render_panel(
        self,
        panel: PanelSpec,
        ax: Axes,
        ledger: dict[str, DataPoint],
    ) -> Axes:
        """Render a single data-plot panel onto ``ax``.

        Parameters
        ----------
        panel:
            ``PanelSpec`` to render.
        ax:
            matplotlib ``Axes`` to draw on.
        ledger:
            DataPoint ID → DataPoint lookup dictionary.

        Returns
        -------
        Axes
            Fully rendered ``Axes`` (same object as ``ax``).

        Raises
        ------
        IntegrityError
            When DataPoint bindings are missing or unregistered.
        """
        dps = _require_datapoints(panel, ledger)
        overlay_dps = self._resolve_overlay(panel, ledger)

        kind = panel.plot_kind
        if kind is PlotKind.HYSTERESIS:
            self._plot_hysteresis(ax, dps, overlay_dps, panel)
        elif kind is PlotKind.HALL:
            self._plot_hall(ax, dps, overlay_dps, panel)
        elif kind is PlotKind.FMR:
            self._plot_fmr(ax, dps, overlay_dps, panel)
        elif kind is PlotKind.DISPERSION:
            self._plot_dispersion(ax, dps, overlay_dps, panel)
        else:
            # PlotKind.XY or default
            self._plot_xy(ax, dps, overlay_dps, panel)

        self._apply_axis_spec(ax, panel)
        return ax

    # ------------------------------------------------------------------
    # Per-plot-type renderers
    # ------------------------------------------------------------------

    def _plot_hysteresis(
        self,
        ax: Axes,
        dps: list[DataPoint],
        overlay: list[DataPoint],
        panel: PanelSpec,
    ) -> None:
        """M-H hysteresis loop plot."""
        x, y = _extract_xy(dps)
        ax.plot(x, y, "-", linewidth=self._rcparams.get("lines.linewidth", 1.0))
        if overlay:
            xo, yo = _extract_xy(overlay)
            ax.plot(xo, yo, "--", label="overlay")
        if not panel.x_axis.label:
            ax.set_xlabel("μ₀H (T)")
        if not panel.y_axis.label:
            ax.set_ylabel("M / M_s")

    def _plot_hall(
        self,
        ax: Axes,
        dps: list[DataPoint],
        overlay: list[DataPoint],
        panel: PanelSpec,
    ) -> None:
        """Hall resistivity ρ_xy vs H plot."""
        x, y = _extract_xy(dps)
        ax.plot(x, y, "-", linewidth=self._rcparams.get("lines.linewidth", 1.0))
        if overlay:
            xo, yo = _extract_xy(overlay)
            ax.plot(xo, yo, "--", label="overlay")
        if not panel.x_axis.label:
            ax.set_xlabel("μ₀H (T)")
        if not panel.y_axis.label:
            ax.set_ylabel("ρ_xy (Ω·cm)")

    def _plot_fmr(
        self,
        ax: Axes,
        dps: list[DataPoint],
        overlay: list[DataPoint],
        panel: PanelSpec,
    ) -> None:
        """FMR absorption / frequency dependence plot."""
        x, y = _extract_xy(dps)
        ax.plot(x, y, "-", linewidth=self._rcparams.get("lines.linewidth", 1.0))
        if overlay:
            xo, yo = _extract_xy(overlay)
            ax.plot(xo, yo, "--", label="overlay")
        if not panel.x_axis.label:
            ax.set_xlabel("μ₀H_res (T)")
        if not panel.y_axis.label:
            ax.set_ylabel("dP/dH (a.u.)")

    def _plot_dispersion(
        self,
        ax: Axes,
        dps: list[DataPoint],
        overlay: list[DataPoint],
        panel: PanelSpec,
    ) -> None:
        """Dispersion relation ω-k plot."""
        x, y = _extract_xy(dps)
        ax.plot(x, y, "-", linewidth=self._rcparams.get("lines.linewidth", 1.0))
        if overlay:
            xo, yo = _extract_xy(overlay)
            ax.plot(xo, yo, "--", label="overlay")
        if not panel.x_axis.label:
            ax.set_xlabel("k (rad/m)")
        if not panel.y_axis.label:
            ax.set_ylabel("ω / 2π (GHz)")

    def _plot_xy(
        self,
        ax: Axes,
        dps: list[DataPoint],
        overlay: list[DataPoint],
        panel: PanelSpec,
    ) -> None:
        """Generic XY plot."""
        x, y = _extract_xy(dps)
        ax.plot(x, y, "-", linewidth=self._rcparams.get("lines.linewidth", 1.0))
        if overlay:
            xo, yo = _extract_xy(overlay)
            ax.plot(xo, yo, "--", label="overlay")

    # ------------------------------------------------------------------
    # Axis specification application
    # ------------------------------------------------------------------

    def _apply_axis_spec(self, ax: Axes, panel: PanelSpec) -> None:
        """Apply the axis and title specification from ``PanelSpec`` to ``ax``."""
        if panel.x_axis.label:
            ax.set_xlabel(panel.x_axis.label)
        if panel.y_axis.label:
            ax.set_ylabel(panel.y_axis.label)
        if panel.x_axis.scale == "log":
            ax.set_xscale("log")
        if panel.y_axis.scale == "log":
            ax.set_yscale("log")
        if panel.x_axis.lim is not None:
            xlim = panel.x_axis.lim
            ax.set_xlim((xlim[0], xlim[1]))
        if panel.y_axis.lim is not None:
            ylim = panel.y_axis.lim
            ax.set_ylim((ylim[0], ylim[1]))
        if panel.title:
            ax.set_title(panel.title)

    # ------------------------------------------------------------------
    # Overlay DataPoint resolution
    # ------------------------------------------------------------------

    def _resolve_overlay(
        self,
        panel: PanelSpec,
        ledger: dict[str, DataPoint],
    ) -> list[DataPoint]:
        """Resolve overlay DataPoint IDs. Returns an empty list if none found."""
        result: list[DataPoint] = []
        for dp_id in panel.overlay:
            dp = ledger.get(dp_id)
            if dp is None:
                warnings.warn(
                    f"Panel '{panel.panel_id}': overlay DataPoint '{dp_id}' not found in ledger. Skipping.",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            result.append(dp)
        return result

    # ------------------------------------------------------------------
    # Standalone figure creation (utility)
    # ------------------------------------------------------------------

    def render_single(
        self,
        panel: PanelSpec,
        ledger: dict[str, DataPoint],
        figsize: tuple[float, float] | None = None,
    ) -> tuple[MplFigure, Axes]:
        """Create and render a single-panel figure.

        Parameters
        ----------
        panel:
            Panel to render.
        ledger:
            DataPoint lookup dictionary.
        figsize:
            Figure size in inches. If ``None``, uses rcParams default.

        Returns
        -------
        tuple[Figure, Axes]
            Fully rendered figure and axes pair.
        """
        with plt.rc_context(self._rcparams):
            fig, ax = plt.subplots(figsize=figsize)
            self.render_panel(panel, ax, ledger)
        return fig, ax
