"""tests/unit/test_figure_compose.py — Multi-panel composition unit tests."""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

from maglab.figure.compose import FigureComposer
from maglab.figure.spec import (
    ColumnWidth,
    FigureSpec,
    GridLayout,
    GridPosition,
    JournalTarget,
    PanelSpec,
    PanelType,
    PlotKind,
)
from maglab.figure.styles import load_style
from maglab.provenance.datapoint import DataPoint, ProvenanceType

_MM_TO_INCH = 1 / 25.4

JOURNAL_WIDTHS = {
    "nature": {"single": 89.0, "double": 183.0},
    "aps": {"single": 86.0, "double": 178.0},
    "ieee": {"single": 88.9, "double": 182.0},
    "elsevier": {"single": 90.0, "double": 190.0},
}


def _dp(value: list[float], dp_id: str) -> DataPoint:
    return DataPoint(
        id=dp_id,
        value=value,
        units="1",
        provenance_type=ProvenanceType.MEASURED,
        source_ref="test",
    )


def _data_panel(
    panel_id: str,
    dp_ids: list[str],
    row: int = 0,
    col: int = 0,
    kind: PlotKind = PlotKind.XY,
) -> PanelSpec:
    return PanelSpec(
        panel_id=panel_id,
        panel_type=PanelType.DATA_PLOT,
        plot_kind=kind,
        data_point_ids=dp_ids,
        grid_position=GridPosition(row=row, col=col),
    )


# ---------------------------------------------------------------------------
# Basic compose behavior
# ---------------------------------------------------------------------------


class TestCompose:
    def test_single_panel_compose(self):
        """A single-panel FigureSpec is rendered into a Figure."""
        dp_x = _dp([0.0, 1.0], "cx")
        dp_y = _dp([0.0, 1.0], "cy")
        panel = _data_panel("p1", [dp_x.id, dp_y.id])
        spec = FigureSpec(
            figure_id="single",
            journal=JournalTarget.NATURE,
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        fig = composer.compose(spec, ledger)
        assert fig is not None
        axes = fig.get_axes()
        assert len(axes) == 1
        plt.close(fig)

    def test_two_by_two_panel_compose(self):
        """A 2×2 panel FigureSpec creates 4 axes."""
        panels = []
        ledger: dict[str, DataPoint] = {}
        for i in range(4):
            row, col = divmod(i, 2)
            dp_x = _dp([0.0, 1.0], f"x{i}")
            dp_y = _dp([0.0, 1.0], f"y{i}")
            ledger[dp_x.id] = dp_x
            ledger[dp_y.id] = dp_y
            panels.append(_data_panel(f"p{i}", [dp_x.id, dp_y.id], row=row, col=col))

        spec = FigureSpec(
            figure_id="2x2",
            journal=JournalTarget.APS,
            panels=panels,
            layout=GridLayout(nrows=2, ncols=2),
        )
        composer = FigureComposer()
        fig = composer.compose(spec, ledger)
        axes = fig.get_axes()
        assert len(axes) == 4
        plt.close(fig)

    def test_out_of_bounds_raises(self):
        """A panel outside the grid bounds raises ValueError."""
        dp_x = _dp([0.0], "oob-x")
        dp_y = _dp([0.0], "oob-y")
        panel = PanelSpec(
            panel_id="oob",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x.id, dp_y.id],
            grid_position=GridPosition(row=5, col=0),  # exceeds bounds
        )
        spec = FigureSpec(
            figure_id="oob-fig",
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        with pytest.raises(ValueError, match="outside"):
            composer.compose(spec, ledger)


# ---------------------------------------------------------------------------
# Panel labels (a/b/c/d)
# ---------------------------------------------------------------------------


class TestPanelLabels:
    def test_panel_labels_a_b_c_d(self):
        """A 2×2 panel figure has a/b/c/d labels."""
        panels = []
        ledger: dict[str, DataPoint] = {}
        for i in range(4):
            row, col = divmod(i, 2)
            dp_x = _dp([0.0, 1.0], f"lx{i}")
            dp_y = _dp([0.0, 1.0], f"ly{i}")
            ledger[dp_x.id] = dp_x
            ledger[dp_y.id] = dp_y
            panels.append(_data_panel(f"lp{i}", [dp_x.id, dp_y.id], row=row, col=col))

        spec = FigureSpec(
            figure_id="label-fig",
            panels=panels,
            layout=GridLayout(nrows=2, ncols=2),
        )
        composer = FigureComposer()
        fig = composer.compose(spec, ledger)

        # Find a, b, c, d labels among all text objects
        all_texts = [t.get_text() for ax in fig.get_axes() for t in ax.texts]
        found = set(all_texts) & {"a", "b", "c", "d"}
        plt.close(fig)
        assert found == {"a", "b", "c", "d"}, f"Missing panel labels. Found: {found}"

    def test_single_panel_label_a(self):
        """A single-panel figure has the label 'a'."""
        dp_x = _dp([0.0], "slx")
        dp_y = _dp([0.0], "sly")
        panel = _data_panel("sl1", [dp_x.id, dp_y.id])
        spec = FigureSpec(figure_id="sl-fig", panels=[panel])
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        fig = composer.compose(spec, ledger)
        all_texts = [t.get_text() for ax in fig.get_axes() for t in ax.texts]
        plt.close(fig)
        assert "a" in all_texts


# ---------------------------------------------------------------------------
# Journal column width conformance
# ---------------------------------------------------------------------------


class TestJournalDimensions:
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
    def test_figsize_matches_journal_spec(self, journal: str, col: str, expected_mm: float):
        """The composed figure width matches the journal column width (mm) within ±0.2 mm."""
        jt = JournalTarget(journal)
        cw = ColumnWidth(col)
        dp_x = _dp([0.0, 1.0], f"dim-x-{journal}-{col}")
        dp_y = _dp([0.0, 1.0], f"dim-y-{journal}-{col}")
        panel = _data_panel("dim-p", [dp_x.id, dp_y.id])
        spec = FigureSpec(
            figure_id=f"dim-{journal}-{col}",
            journal=jt,
            column_width=cw,
            panels=[panel],
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        style = load_style(journal)
        composer = FigureComposer(style=style)
        fig = composer.compose(spec, ledger)
        width_inch = fig.get_size_inches()[0]
        width_mm = width_inch / _MM_TO_INCH
        plt.close(fig)
        assert abs(width_mm - expected_mm) < 0.2, (
            f"{journal}/{col}: {width_mm:.1f} mm vs {expected_mm} mm"
        )


# ---------------------------------------------------------------------------
# SCHEMATIC and SIM_VIZ panel rendering (FIX 2)
# ---------------------------------------------------------------------------


def _schematic_panel(panel_id: str, row: int = 0, col: int = 0) -> PanelSpec:
    """Create a SCHEMATIC panel spec."""
    return PanelSpec(
        panel_id=panel_id,
        panel_type=PanelType.SCHEMATIC,
        grid_position=GridPosition(row=row, col=col),
        extra={"query": "hall bar measurement geometry"},
    )


def _simviz_panel(panel_id: str, row: int = 0, col: int = 0) -> PanelSpec:
    """Create a SIM_VIZ panel spec without an OVF path (no-OVF fallback path)."""
    return PanelSpec(
        panel_id=panel_id,
        panel_type=PanelType.SIM_VIZ,
        grid_position=GridPosition(row=row, col=col),
        extra={"render_type": "hsl"},  # no ovf_path → renderer uses placeholder text
    )


class TestSchematicPanelCompose:
    """SCHEMATIC panel rendering tests (FIX 2 — compose wiring)."""

    def test_schematic_panel_does_not_emit_placeholder_text(self):
        """A composed SCHEMATIC panel must not emit the old placeholder string '[schematic — P4]'."""
        panel = _schematic_panel("schem-1")
        spec = FigureSpec(
            figure_id="schem-fig",
            journal=JournalTarget.NATURE,
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        composer = FigureComposer()
        fig = composer.compose(spec, {})
        all_texts = [t.get_text() for ax in fig.get_axes() for t in ax.texts]
        plt.close(fig)
        assert "[schematic — P4]" not in all_texts, (
            "Placeholder text '[schematic — P4]' still emitted — SchematicRenderer not wired."
        )

    def test_schematic_panel_produces_axes(self):
        """A figure with a SCHEMATIC panel produces exactly one Axes."""
        panel = _schematic_panel("schem-2")
        spec = FigureSpec(
            figure_id="schem-fig-2",
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        composer = FigureComposer()
        fig = composer.compose(spec, {})
        axes = fig.get_axes()
        plt.close(fig)
        assert len(axes) == 1

    def test_mixed_data_and_schematic_panels(self):
        """A figure with both DATA_PLOT and SCHEMATIC panels renders without error."""
        dp_x = _dp([0.0, 1.0], "ms-x")
        dp_y = _dp([0.0, 1.0], "ms-y")
        data_panel = _data_panel("dp-mixed", [dp_x.id, dp_y.id], row=0, col=0)
        schem_panel = _schematic_panel("schem-mixed", row=0, col=1)
        spec = FigureSpec(
            figure_id="mixed-fig",
            panels=[data_panel, schem_panel],
            layout=GridLayout(nrows=1, ncols=2),
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        fig = composer.compose(spec, ledger)
        axes = fig.get_axes()
        plt.close(fig)
        assert len(axes) == 2


class TestSimVizPanelCompose:
    """SIM_VIZ panel rendering tests (FIX 2 — compose wiring)."""

    def test_simviz_panel_does_not_emit_placeholder_text(self):
        """A composed SIM_VIZ panel must not emit the old placeholder string '[sim-viz — P3]'."""
        panel = _simviz_panel("simviz-1")
        spec = FigureSpec(
            figure_id="simviz-fig",
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        composer = FigureComposer()
        fig = composer.compose(spec, {})
        all_texts = [t.get_text() for ax in fig.get_axes() for t in ax.texts]
        plt.close(fig)
        assert "[sim-viz — P3]" not in all_texts, (
            "Placeholder text '[sim-viz — P3]' still emitted — SimVizRenderer not wired."
        )

    def test_simviz_panel_produces_axes(self):
        """A figure with a SIM_VIZ panel produces exactly one Axes."""
        panel = _simviz_panel("simviz-2")
        spec = FigureSpec(
            figure_id="simviz-fig-2",
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        composer = FigureComposer()
        fig = composer.compose(spec, {})
        axes = fig.get_axes()
        plt.close(fig)
        assert len(axes) == 1


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 1, domain 03)
# ---------------------------------------------------------------------------


class TestHigh2FigureLeakOnRenderError:
    """HIGH-2: FigureComposer.compose() must close the figure on render error (no leak)."""

    def test_no_figure_leak_when_render_raises(self):
        """Matplotlib figure count must not increase when compose() raises an error."""
        from maglab.figure.renderers.dataplot import IntegrityError

        # A DATA_PLOT panel with no ledger entry will raise IntegrityError
        dp_x = _dp([0.0, 1.0], "leak-x")
        dp_y = _dp([0.0, 1.0], "leak-y")
        panel = _data_panel("leak-p", [dp_x.id, dp_y.id])
        spec = FigureSpec(
            figure_id="leak-fig",
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        # Empty ledger → IntegrityError during render
        before = len(plt.get_fignums())
        composer = FigureComposer()
        with pytest.raises(IntegrityError):
            composer.compose(spec, {})  # ledger is empty, render must fail
        after = len(plt.get_fignums())
        assert after == before, (
            f"Figure leak detected: {before} figures before, {after} after a failed compose(). "
            "FigureComposer must close the figure on error."
        )

    def test_figure_returned_on_success_is_not_closed(self):
        """A successful compose() must return an open (non-closed) figure."""
        dp_x = _dp([0.0, 1.0], "ok-x2")
        dp_y = _dp([0.0, 1.0], "ok-y2")
        panel = _data_panel("ok-p2", [dp_x.id, dp_y.id])
        spec = FigureSpec(
            figure_id="ok-fig2",
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=1),
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        fig = composer.compose(spec, ledger)
        assert fig.number in plt.get_fignums(), "Returned figure must still be open."
        plt.close(fig)


class TestMedium2SpanOverflowDetected:
    """MEDIUM-2: _make_axes must raise ValueError when row/col span overflows grid bounds."""

    def test_row_span_overflow_raises(self):
        """row=0, row_span=3 in a nrows=2 grid must raise ValueError."""
        dp_x = _dp([0.0], "span-x")
        dp_y = _dp([0.0], "span-y")
        panel = PanelSpec(
            panel_id="span-p",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x.id, dp_y.id],
            grid_position=GridPosition(row=0, col=0, row_span=3),  # spans past row 1
        )
        spec = FigureSpec(
            figure_id="span-fig",
            panels=[panel],
            layout=GridLayout(nrows=2, ncols=1),
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        with pytest.raises(ValueError, match="span"):
            composer.compose(spec, ledger)

    def test_col_span_overflow_raises(self):
        """col=0, col_span=3 in a ncols=2 grid must raise ValueError."""
        dp_x = _dp([0.0], "cspan-x")
        dp_y = _dp([0.0], "cspan-y")
        panel = PanelSpec(
            panel_id="cspan-p",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x.id, dp_y.id],
            grid_position=GridPosition(row=0, col=0, col_span=3),  # spans past col 1
        )
        spec = FigureSpec(
            figure_id="cspan-fig",
            panels=[panel],
            layout=GridLayout(nrows=1, ncols=2),
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        with pytest.raises(ValueError, match="span"):
            composer.compose(spec, ledger)

    def test_valid_span_does_not_raise(self):
        """row=0, row_span=2 in a nrows=2 grid is valid and must succeed."""
        dp_x = _dp([0.0, 1.0], "vspan-x")
        dp_y = _dp([0.0, 1.0], "vspan-y")
        panel = PanelSpec(
            panel_id="vspan-p",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[dp_x.id, dp_y.id],
            grid_position=GridPosition(row=0, col=0, row_span=2),
        )
        spec = FigureSpec(
            figure_id="vspan-fig",
            panels=[panel],
            layout=GridLayout(nrows=2, ncols=1),
        )
        ledger = {dp_x.id: dp_x, dp_y.id: dp_y}
        composer = FigureComposer()
        fig = composer.compose(spec, ledger)
        plt.close(fig)
