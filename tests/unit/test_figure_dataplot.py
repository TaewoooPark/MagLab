"""tests/unit/test_figure_dataplot.py — Data-plot renderer unit tests.

Key validations (§20):
- Input DataPoint values and plotted data values must match **exactly** (value-level, not pixel-level).
  Data is extracted from matplotlib Line2D and compared numerically against original DataPoint.value.
- Panels without DataPoint binding are blocked with IntegrityError.
- Overlay DataPoints are also rendered exactly.
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.use("Agg")

from maglab.figure.renderers.dataplot import DataPlotRenderer, IntegrityError
from maglab.figure.spec import AxisSpec, PanelSpec, PanelType, PlotKind
from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# DataPoint factory for tests
# ---------------------------------------------------------------------------


def _dp(
    value: float | list[float],
    units: str = "1",
    ptype: ProvenanceType = ProvenanceType.MEASURED,
    dp_id: str | None = None,
) -> DataPoint:
    """Create a DataPoint for testing."""
    kwargs: dict = {
        "value": value,
        "units": units,
        "provenance_type": ptype,
        "source_ref": "test-ref",
    }
    if dp_id:
        kwargs["id"] = dp_id
    return DataPoint(**kwargs)


def _ledger(*dps: DataPoint) -> dict[str, DataPoint]:
    """Convert a list of DataPoints to an ID→DP dictionary."""
    return {dp.id: dp for dp in dps}


def _panel(
    kind: PlotKind,
    dp_ids: list[str],
    overlay: list[str] | None = None,
    panel_id: str = "p1",
) -> PanelSpec:
    """Create a PanelSpec for testing."""
    return PanelSpec(
        panel_id=panel_id,
        panel_type=PanelType.DATA_PLOT,
        plot_kind=kind,
        data_point_ids=dp_ids,
        overlay=overlay or [],
    )


# ---------------------------------------------------------------------------
# Value accuracy validation — Line2D data extraction comparison
# ---------------------------------------------------------------------------


class TestDataValueAccuracy:
    """Core: input DataPoint values and rendered data values must match exactly."""

    def _render_get_lines(
        self,
        panel: PanelSpec,
        ledger: dict[str, DataPoint],
    ) -> list[matplotlib.lines.Line2D]:
        """Render a panel and return all Line2D objects."""
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        renderer.render_panel(panel, ax, ledger)
        lines = ax.get_lines()
        plt.close(fig)
        return lines

    # --- Array XY pair (dps[0]=x, dps[1]=y) ---

    def test_xy_array_values_exact(self):
        """XY plot: x and y arrays are recorded exactly in Line2D."""
        x_vals = [0.0, 0.5, 1.0, 1.5, 2.0]
        y_vals = [1.0, 2.0, 1.5, 3.0, 2.5]
        dp_x = _dp(x_vals, units="T", dp_id="x-001")
        dp_y = _dp(y_vals, units="Omega", dp_id="y-001")
        panel = _panel(PlotKind.XY, [dp_x.id, dp_y.id])
        ledger = _ledger(dp_x, dp_y)

        lines = self._render_get_lines(panel, ledger)
        assert len(lines) >= 1
        xdata, ydata = lines[0].get_xdata(), lines[0].get_ydata()
        np.testing.assert_array_almost_equal(xdata, x_vals, decimal=10)
        np.testing.assert_array_almost_equal(ydata, y_vals, decimal=10)

    def test_hysteresis_values_exact(self):
        """Hysteresis: x(H) and y(M) arrays match exactly."""
        h = [-1.0, -0.5, 0.0, 0.5, 1.0]
        m = [-1.0, -0.8, 0.0, 0.8, 1.0]
        dp_h = _dp(h, units="T", dp_id="h-001")
        dp_m = _dp(m, units="dimensionless", dp_id="m-001")
        panel = _panel(PlotKind.HYSTERESIS, [dp_h.id, dp_m.id])
        ledger = _ledger(dp_h, dp_m)

        lines = self._render_get_lines(panel, ledger)
        np.testing.assert_array_almost_equal(lines[0].get_xdata(), h, decimal=10)
        np.testing.assert_array_almost_equal(lines[0].get_ydata(), m, decimal=10)

    def test_hall_values_exact(self):
        """Hall plot: x and y values match exactly."""
        h = [-2.0, -1.0, 0.0, 1.0, 2.0]
        rho = [-5.0, -4.0, 0.0, 4.0, 5.0]
        dp_h = _dp(h, units="T", dp_id="hall-h")
        dp_r = _dp(rho, units="uOhm.cm", dp_id="hall-r")
        panel = _panel(PlotKind.HALL, [dp_h.id, dp_r.id])
        ledger = _ledger(dp_h, dp_r)

        lines = self._render_get_lines(panel, ledger)
        np.testing.assert_array_almost_equal(lines[0].get_xdata(), h, decimal=10)
        np.testing.assert_array_almost_equal(lines[0].get_ydata(), rho, decimal=10)

    def test_fmr_values_exact(self):
        """FMR plot: values match exactly."""
        h = [0.05, 0.10, 0.15, 0.20]
        dpdh = [0.1, 0.5, 0.8, 0.3]
        dp_h = _dp(h, units="T", dp_id="fmr-h")
        dp_dpdh = _dp(dpdh, units="a.u.", dp_id="fmr-dpdh")
        panel = _panel(PlotKind.FMR, [dp_h.id, dp_dpdh.id])
        ledger = _ledger(dp_h, dp_dpdh)

        lines = self._render_get_lines(panel, ledger)
        np.testing.assert_array_almost_equal(lines[0].get_xdata(), h, decimal=10)
        np.testing.assert_array_almost_equal(lines[0].get_ydata(), dpdh, decimal=10)

    def test_dispersion_values_exact(self):
        """Dispersion plot: values match exactly."""
        k = [1e6, 2e6, 3e6, 4e6]
        omega = [5.0, 8.0, 10.0, 11.0]
        dp_k = _dp(k, units="rad/m", dp_id="disp-k")
        dp_om = _dp(omega, units="GHz", dp_id="disp-om")
        panel = _panel(PlotKind.DISPERSION, [dp_k.id, dp_om.id])
        ledger = _ledger(dp_k, dp_om)

        lines = self._render_get_lines(panel, ledger)
        np.testing.assert_array_almost_equal(lines[0].get_xdata(), k, decimal=0)
        np.testing.assert_array_almost_equal(lines[0].get_ydata(), omega, decimal=10)

    def test_single_array_dp(self):
        """A single DataPoint (array value) is plotted as index vs value."""
        vals = [3.14, 2.71, 1.41]
        dp = _dp(vals, dp_id="single-arr")
        panel = _panel(PlotKind.XY, [dp.id])
        ledger = _ledger(dp)

        lines = self._render_get_lines(panel, ledger)
        np.testing.assert_array_almost_equal(lines[0].get_ydata(), vals, decimal=10)
        np.testing.assert_array_almost_equal(lines[0].get_xdata(), [0, 1, 2], decimal=10)

    def test_overlay_values_exact(self):
        """Overlay DataPoint is rendered exactly as the second Line2D."""
        x1 = [0.0, 1.0, 2.0]
        y1 = [0.0, 1.0, 0.0]
        x2 = [0.0, 1.0, 2.0]
        y2 = [0.5, 1.5, 0.5]
        dp_x1 = _dp(x1, dp_id="ox1")
        dp_y1 = _dp(y1, dp_id="oy1")
        dp_x2 = _dp(x2, dp_id="ox2")
        dp_y2 = _dp(y2, dp_id="oy2")

        panel = PanelSpec(
            panel_id="overlay-p",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x1.id, dp_y1.id],
            overlay=[dp_x2.id, dp_y2.id],
        )
        ledger = _ledger(dp_x1, dp_y1, dp_x2, dp_y2)

        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        renderer.render_panel(panel, ax, ledger)
        lines = ax.get_lines()
        plt.close(fig)

        assert len(lines) >= 2
        np.testing.assert_array_almost_equal(lines[0].get_xdata(), x1, decimal=10)
        np.testing.assert_array_almost_equal(lines[0].get_ydata(), y1, decimal=10)
        np.testing.assert_array_almost_equal(lines[1].get_xdata(), x2, decimal=10)
        np.testing.assert_array_almost_equal(lines[1].get_ydata(), y2, decimal=10)


# ---------------------------------------------------------------------------
# Integrity blocking — honesty gate
# ---------------------------------------------------------------------------


class TestIntegrityGate:
    """Verify that unbound data figure creation is blocked (§12.6)."""

    def test_empty_data_point_ids_blocked_at_spec_level(self):
        """At PanelSpec level: data_point_ids=[] raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="data_point_ids"):
            PanelSpec(
                panel_id="bad",
                panel_type=PanelType.DATA_PLOT,
                plot_kind=PlotKind.XY,
                data_point_ids=[],
            )

    def test_missing_dp_in_ledger_raises_integrity_error(self):
        """Referencing a DataPoint ID not in the ledger raises IntegrityError."""
        panel = PanelSpec(
            panel_id="p-miss",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=["does-not-exist"],
        )
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        with pytest.raises(IntegrityError, match="ledger"):
            renderer.render_panel(panel, ax, {})
        plt.close(fig)

    def test_simulated_datapoint_accepted(self):
        """SIMULATED type DataPoints are rendered normally."""
        dp_x = _dp([0.0, 1.0], units="T", ptype=ProvenanceType.SIMULATED, dp_id="sim-x")
        dp_y = _dp([0.5, 1.5], units="1", ptype=ProvenanceType.SIMULATED, dp_id="sim-y")
        panel = _panel(PlotKind.XY, [dp_x.id, dp_y.id])
        ledger = _ledger(dp_x, dp_y)

        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        renderer.render_panel(panel, ax, ledger)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Axis spec application
# ---------------------------------------------------------------------------


class TestAxisSpec:
    """AxisSpec is correctly applied to matplotlib Axes."""

    def test_xlabel_applied(self):
        """Setting x_axis.label is reflected in xlabel."""
        dp_x = _dp([0.0, 1.0], dp_id="ax-x")
        dp_y = _dp([0.0, 1.0], dp_id="ax-y")
        panel = PanelSpec(
            panel_id="lbl",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x.id, dp_y.id],
            x_axis=AxisSpec(label="μ₀H (T)"),
            y_axis=AxisSpec(label="M (A/m)"),
        )
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        renderer.render_panel(panel, ax, ledger)
        assert ax.get_xlabel() == "μ₀H (T)"
        assert ax.get_ylabel() == "M (A/m)"
        plt.close(fig)

    def test_log_scale_applied(self):
        """Setting x_axis.scale='log' makes the x axis logarithmic."""
        dp_x = _dp([1.0, 10.0, 100.0], dp_id="log-x")
        dp_y = _dp([1.0, 2.0, 3.0], dp_id="log-y")
        panel = PanelSpec(
            panel_id="logp",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x.id, dp_y.id],
            x_axis=AxisSpec(scale="log"),
        )
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        renderer.render_panel(panel, ax, ledger)
        assert ax.get_xscale() == "log"
        plt.close(fig)

    def test_xlim_applied(self):
        """x_axis.lim is reflected in the axes xlim."""
        dp_x = _dp([0.0, 1.0, 2.0], dp_id="lim-x")
        dp_y = _dp([0.0, 1.0, 0.0], dp_id="lim-y")
        panel = PanelSpec(
            panel_id="limp",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x.id, dp_y.id],
            x_axis=AxisSpec(lim=[-0.5, 2.5]),
        )
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        renderer.render_panel(panel, ax, ledger)
        xlim = ax.get_xlim()
        assert abs(xlim[0] - (-0.5)) < 1e-9
        assert abs(xlim[1] - 2.5) < 1e-9
        plt.close(fig)


# ---------------------------------------------------------------------------
# render_single utility
# ---------------------------------------------------------------------------


def test_render_single_returns_fig_and_ax():
    """render_single() returns a (Figure, Axes) pair."""
    dp_x = _dp([0.0, 1.0], dp_id="rs-x")
    dp_y = _dp([0.0, 1.0], dp_id="rs-y")
    panel = _panel(PlotKind.XY, [dp_x.id, dp_y.id])
    ledger = _ledger(dp_x, dp_y)

    renderer = DataPlotRenderer()
    fig, ax = renderer.render_single(panel, ledger)
    assert fig is not None
    assert ax is not None


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 14, domain 03)
# ---------------------------------------------------------------------------


class TestR14Finding1ExtractXYShapeMismatch:
    """R14-F1 (MEDIUM): _extract_xy() must raise a clear ValueError when the two
    DataPoints in a 2-DataPoint panel have incompatible shapes (list vs. scalar),
    instead of passing mismatched arrays to matplotlib and producing a cryptic
    internal assertion.

    When dps[0].value is a list of N elements and dps[1].value is a scalar,
    the previous code produced x.shape=(N,) and y.shape=(1,), which caused
    matplotlib to raise a hard-to-diagnose ValueError("x and y must have same
    first dimension").  The fix raises a clear ValueError before matplotlib is
    ever invoked.
    """

    def _make_panel(self, dp_ids: list[str]) -> PanelSpec:
        return PanelSpec(
            panel_id="mismatch-test",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=dp_ids,
        )

    def test_list_x_scalar_y_raises_clear_error(self) -> None:
        """dps[0]=list(3), dps[1]=scalar must raise ValueError with a descriptive message."""
        dp_x = _dp([1.0, 2.0, 3.0], dp_id="r14-x-list")
        dp_y = _dp(5.0, dp_id="r14-y-scalar")
        panel = self._make_panel([dp_x.id, dp_y.id])
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            with pytest.raises(ValueError, match="shape mismatch"):
                renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)

    def test_scalar_x_list_y_raises_clear_error(self) -> None:
        """dps[0]=scalar, dps[1]=list(3) must raise ValueError with a descriptive message."""
        dp_x = _dp(2.0, dp_id="r14-x-scalar")
        dp_y = _dp([4.0, 5.0, 6.0], dp_id="r14-y-list")
        panel = self._make_panel([dp_x.id, dp_y.id])
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            with pytest.raises(ValueError, match="shape mismatch"):
                renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)

    def test_list_x_list_y_same_length_no_error(self) -> None:
        """dps[0]=list(3), dps[1]=list(3) must succeed (no shape mismatch)."""
        dp_x = _dp([1.0, 2.0, 3.0], dp_id="r14-x-list3")
        dp_y = _dp([4.0, 5.0, 6.0], dp_id="r14-y-list3")
        panel = self._make_panel([dp_x.id, dp_y.id])
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)

    def test_scalar_x_scalar_y_no_error(self) -> None:
        """dps[0]=scalar, dps[1]=scalar must succeed — single point plot."""
        dp_x = _dp(1.0, dp_id="r14-x-s1")
        dp_y = _dp(2.0, dp_id="r14-y-s1")
        panel = self._make_panel([dp_x.id, dp_y.id])
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)

    def test_mismatched_list_lengths_raises_clear_error(self) -> None:
        """dps[0]=list(3), dps[1]=list(5) must raise ValueError with a descriptive message."""
        dp_x = _dp([1.0, 2.0, 3.0], dp_id="r14-x-list3b")
        dp_y = _dp([1.0, 2.0, 3.0, 4.0, 5.0], dp_id="r14-y-list5")
        panel = self._make_panel([dp_x.id, dp_y.id])
        ledger = _ledger(dp_x, dp_y)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            with pytest.raises(ValueError, match="shape mismatch"):
                renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 15, domain 03)
# ---------------------------------------------------------------------------


class TestR15Finding1ExtractXYEmptyListMultiDP:
    """R15-F1 (MEDIUM): _extract_xy() must raise a clear ValueError when a DataPoint
    in a 3+-DataPoint panel holds an empty list value instead of silently raising
    an IndexError with no diagnostic context.

    In the multi-DataPoint fallback branch (len(dps) >= 3), the code previously called
    dp.value[0] on any list-valued DataPoint to extract a single representative value.
    When dp.value == [], this raised IndexError('list index out of range') with no
    mention of the DataPoint ID, panel ID, or the nature of the binding error.

    The fix adds a pre-index guard that raises a clear ValueError identifying the
    offending DataPoint before the index is attempted.
    """

    def _make_3dp_panel(self, dp_ids: list[str]) -> PanelSpec:
        """Create a 3-DataPoint XY panel."""
        return PanelSpec(
            panel_id="r15-3dp-test",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=dp_ids,
        )

    def test_empty_list_in_3dp_branch_raises_clear_error(self) -> None:
        """A DataPoint with value=[] in a 3-DP panel must raise ValueError (not IndexError)."""
        dp_a = _dp(1.0, dp_id="r15-3dp-a")
        dp_b = _dp([], dp_id="r15-3dp-b-empty")  # empty list — the defect trigger
        dp_c = _dp(3.0, dp_id="r15-3dp-c")
        panel = self._make_3dp_panel([dp_a.id, dp_b.id, dp_c.id])
        ledger = _ledger(dp_a, dp_b, dp_c)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            with pytest.raises(ValueError, match="empty list"):
                renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)

    def test_empty_list_message_contains_dp_id(self) -> None:
        """The ValueError message must identify the offending DataPoint by ID."""
        dp_a = _dp(1.0, dp_id="r15-id-a")
        dp_b = _dp([], dp_id="r15-id-b-empty")
        dp_c = _dp(2.0, dp_id="r15-id-c")
        panel = self._make_3dp_panel([dp_a.id, dp_b.id, dp_c.id])
        ledger = _ledger(dp_a, dp_b, dp_c)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            with pytest.raises(ValueError, match="r15-id-b-empty"):
                renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)

    def test_nonempty_list_in_3dp_branch_warns_and_succeeds(self) -> None:
        """A DataPoint with a non-empty list in a 3-DP panel issues a warning and plots
        using only the first element (existing behavior, not broken by the fix)."""
        dp_a = _dp(1.0, dp_id="r15-ne-a")
        dp_b = _dp([10.0, 20.0], dp_id="r15-ne-b-list")  # non-empty list
        dp_c = _dp(3.0, dp_id="r15-ne-c")
        panel = self._make_3dp_panel([dp_a.id, dp_b.id, dp_c.id])
        ledger = _ledger(dp_a, dp_b, dp_c)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            with pytest.warns(UserWarning, match="r15-ne-b-list"):
                renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)

    def test_all_scalars_in_3dp_branch_succeeds(self) -> None:
        """Three scalar DataPoints in the 3-DP fallback path must succeed without error."""
        dp_a = _dp(1.0, dp_id="r15-s3-a")
        dp_b = _dp(2.0, dp_id="r15-s3-b")
        dp_c = _dp(3.0, dp_id="r15-s3-c")
        panel = self._make_3dp_panel([dp_a.id, dp_b.id, dp_c.id])
        ledger = _ledger(dp_a, dp_b, dp_c)
        renderer = DataPlotRenderer()
        fig, ax = plt.subplots()
        try:
            renderer.render_panel(panel, ax, ledger)
        finally:
            plt.close(fig)
