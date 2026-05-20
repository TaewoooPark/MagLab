"""tests/unit/test_figure_spec.py — FigureSpec IR unit tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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

# ---------------------------------------------------------------------------
# FigureSpec serialization and deserialization identity
# ---------------------------------------------------------------------------


def _make_panel(panel_id: str = "p1") -> PanelSpec:
    """Factory function for a data-plot panel."""
    return PanelSpec(
        panel_id=panel_id,
        panel_type=PanelType.DATA_PLOT,
        plot_kind=PlotKind.XY,
        data_point_ids=["dp-001"],
    )


def test_figurespec_roundtrip_json():
    """FigureSpec preserves identity after serialization and deserialization."""
    spec = FigureSpec(
        figure_id="fig-test",
        journal=JournalTarget.NATURE,
        column_width=ColumnWidth.SINGLE,
        panels=[_make_panel("p1")],
        layout=GridLayout(nrows=1, ncols=1),
        caption="Test caption",
    )
    dumped = spec.model_dump(mode="json")
    restored = FigureSpec.model_validate(dumped)
    assert restored.figure_id == spec.figure_id
    assert restored.journal == spec.journal
    assert restored.column_width == spec.column_width
    assert len(restored.panels) == 1
    assert restored.panels[0].panel_id == "p1"
    assert restored.caption == spec.caption


def test_figurespec_roundtrip_model_dump():
    """model_dump() and model_validate() maintain round-trip consistency."""
    spec = FigureSpec(
        figure_id="fig-multi",
        journal=JournalTarget.APS,
        column_width=ColumnWidth.DOUBLE,
        panels=[_make_panel("a"), _make_panel("b")],
        layout=GridLayout(nrows=1, ncols=2),
    )
    d = spec.model_dump()
    restored = FigureSpec.model_validate(d)
    assert len(restored.panels) == 2
    panel_ids = [p.panel_id for p in restored.panels]
    assert "a" in panel_ids and "b" in panel_ids


# ---------------------------------------------------------------------------
# honesty gate — blocking unbound data-plot panels
# ---------------------------------------------------------------------------


def test_data_plot_requires_data_point_ids():
    """A DATA_PLOT panel with empty data_point_ids raises ValidationError."""
    with pytest.raises(ValidationError, match="data_point_ids"):
        PanelSpec(
            panel_id="unbound",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=PlotKind.XY,
            data_point_ids=[],  # empty → blocked
        )


def test_data_plot_requires_plot_kind():
    """A DATA_PLOT panel must specify plot_kind."""
    with pytest.raises(ValidationError, match="plot_kind"):
        PanelSpec(
            panel_id="no-kind",
            panel_type=PanelType.DATA_PLOT,
            plot_kind=None,
            data_point_ids=["dp-001"],
        )


def test_schematic_panel_no_binding_required():
    """A SCHEMATIC panel can be created without data_point_ids."""
    panel = PanelSpec(
        panel_id="sch1",
        panel_type=PanelType.SCHEMATIC,
        data_point_ids=[],
    )
    assert panel.panel_type is PanelType.SCHEMATIC


def test_figurespec_has_unbound_data_panels_false():
    """A properly bound spec returns has_unbound_data_panels() == False."""
    spec = FigureSpec(
        figure_id="fig-ok",
        panels=[_make_panel()],
    )
    assert not spec.has_unbound_data_panels()


# ---------------------------------------------------------------------------
# provenance_ids auto-collection
# ---------------------------------------------------------------------------


def test_provenance_ids_auto_collected():
    """When provenance_ids is None, it is auto-collected from panels."""
    p1 = PanelSpec(
        panel_id="p1",
        panel_type=PanelType.DATA_PLOT,
        plot_kind=PlotKind.HYSTERESIS,
        data_point_ids=["dp-001", "dp-002"],
    )
    p2 = PanelSpec(
        panel_id="p2",
        panel_type=PanelType.DATA_PLOT,
        plot_kind=PlotKind.HALL,
        data_point_ids=["dp-003"],
        overlay=["dp-004"],
    )
    spec = FigureSpec(figure_id="fig-prov", panels=[p1, p2])
    assert set(spec.provenance_ids or []) == {"dp-001", "dp-002", "dp-003", "dp-004"}


def test_all_data_point_ids():
    """all_data_point_ids() includes all panels and overlays."""
    p1 = _make_panel("p1")
    spec = FigureSpec(figure_id="fig-ids", panels=[p1])
    assert "dp-001" in spec.all_data_point_ids()


# ---------------------------------------------------------------------------
# Various JournalTarget and ColumnWidth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "journal",
    [JournalTarget.NATURE, JournalTarget.APS, JournalTarget.IEEE, JournalTarget.ELSEVIER],
)
def test_journal_targets(journal: JournalTarget):
    """FigureSpec can be created for all JournalTargets."""
    spec = FigureSpec(
        figure_id="fig-j",
        journal=journal,
        panels=[_make_panel()],
    )
    assert spec.journal == journal


def test_journal_alias_normalizes_to_style_target():
    spec = FigureSpec(
        figure_id="fig-prl",
        journal="prl",
        panels=[_make_panel()],
    )

    assert spec.journal == JournalTarget.APS


@pytest.mark.parametrize("col", [ColumnWidth.SINGLE, ColumnWidth.DOUBLE])
def test_column_widths(col: ColumnWidth):
    """Both SINGLE and DOUBLE column widths are handled."""
    spec = FigureSpec(figure_id="fig-col", column_width=col, panels=[_make_panel()])
    assert spec.column_width == col


# ---------------------------------------------------------------------------
# GridPosition and GridLayout
# ---------------------------------------------------------------------------


def test_grid_position_defaults():
    """GridPosition defaults are row=0, col=0, span=1×1."""
    gp = GridPosition()
    assert gp.row == 0 and gp.col == 0
    assert gp.row_span == 1 and gp.col_span == 1


def test_grid_layout_defaults():
    """GridLayout default is 1×1."""
    gl = GridLayout()
    assert gl.nrows == 1 and gl.ncols == 1


# ---------------------------------------------------------------------------
# PlotKind enum
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [PlotKind.HYSTERESIS, PlotKind.HALL, PlotKind.FMR, PlotKind.DISPERSION, PlotKind.XY],
)
def test_all_plot_kinds(kind: PlotKind):
    """PanelSpec can be created with all PlotKinds."""
    panel = PanelSpec(
        panel_id="pk",
        panel_type=PanelType.DATA_PLOT,
        plot_kind=kind,
        data_point_ids=["dp-x"],
    )
    assert panel.plot_kind == kind
