"""FigureSpec IR — Declarative figure specification (§12.3-①).

``FigureSpec`` is the declarative intermediate representation (IR) for
multi-panel figures. When an LLM or user writes this specification, the
renderer, compose, and export pipeline deterministically produces a vector
figure.

Core principles (§12.1·§12.6):
- Data-plot panels must bind at least one ``DataPoint`` ID in ``data_point_ids``.
- Unbound data-plot panels raise ``ValidationError`` (honesty gate).
- There is no code path that allows the LLM to inject numbers or data directly.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class PanelType(StrEnum):
    """Panel type enumeration.

    - DATA_PLOT  : matplotlib data plot (implemented in P1).
    - SCHEMATIC  : SVG schematic / primitive composition (implemented in P4).
    - SIM_VIZ    : OVF / micromagnetic visualization (implemented in P3).
    """

    DATA_PLOT = "data-plot"
    SCHEMATIC = "schematic"
    SIM_VIZ = "sim-viz"


class PlotKind(StrEnum):
    """Data-plot sub-type.

    - HYSTERESIS : M-H hysteresis loop.
    - HALL       : Hall resistivity ρ_xy vs H.
    - FMR        : FMR absorption / frequency dependence.
    - DISPERSION : Dispersion relation ω-k.
    - XY         : Generic XY plot.
    """

    HYSTERESIS = "hysteresis"
    HALL = "hall"
    FMR = "fmr"
    DISPERSION = "dispersion"
    XY = "xy"


class JournalTarget(StrEnum):
    """Journal target enumeration (Appendix G).

    Determines column width, font, line width, and palette.
    """

    NATURE = "nature"
    APS = "aps"
    IEEE = "ieee"
    ELSEVIER = "elsevier"


class ColumnWidth(StrEnum):
    """Journal column width selection.

    - SINGLE : Single column.
    - DOUBLE : Double column.
    """

    SINGLE = "single"
    DOUBLE = "double"


class GridPosition(BaseModel):
    """Panel position within GridSpec (row, column, and span).

    Parameters
    ----------
    row:
        Starting row index (0-based).
    col:
        Starting column index (0-based).
    row_span:
        Number of rows occupied (default 1).
    col_span:
        Number of columns occupied (default 1).
    """

    row: int = 0
    col: int = 0
    row_span: int = 1
    col_span: int = 1


class AxisSpec(BaseModel):
    """Single axis specification.

    Parameters
    ----------
    label:
        Axis label (including units recommended, e.g. ``"μ₀H (T)"``).
    scale:
        Scale — ``"linear"`` or ``"log"``.
    lim:
        [min, max] range. ``None`` for matplotlib auto-scaling.
    """

    label: str = ""
    scale: Literal["linear", "log"] = "linear"
    lim: list[float] | None = None


class PanelSpec(BaseModel):
    """Single panel specification.

    Parameters
    ----------
    panel_id:
        Unique panel ID (must be unique within the figure).
    panel_type:
        Panel type (``PanelType`` enum).
    plot_kind:
        Data-plot sub-type. Required when panel_type == DATA_PLOT.
    data_point_ids:
        List of ``DataPoint`` IDs referenced by this panel.
        **At least one required** when ``panel_type == DATA_PLOT`` (honesty gate).
    grid_position:
        Position and span within GridSpec.
    x_axis:
        x-axis specification.
    y_axis:
        y-axis specification.
    title:
        Panel title (optional).
    overlay:
        Overlay DataPoint ID list (e.g. simulation + experiment superimposed).
    extra:
        Renderer-specific additional parameters (free dictionary).
    """

    panel_id: str
    panel_type: PanelType
    plot_kind: PlotKind | None = None
    data_point_ids: list[str] = Field(default_factory=list)
    grid_position: GridPosition = Field(default_factory=GridPosition)
    x_axis: AxisSpec = Field(default_factory=AxisSpec)
    y_axis: AxisSpec = Field(default_factory=AxisSpec)
    title: str = ""
    overlay: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _data_plot_requires_binding(self) -> PanelSpec:
        """Data-plot panels require DataPoint binding (§12.6 honesty gate).

        Unbound panels raise ``ValidationError`` to block creation.
        """
        if self.panel_type is PanelType.DATA_PLOT and not self.data_point_ids:
            raise ValueError(
                f"Panel '{self.panel_id}': data-plot panels must bind at least one "
                "DataPoint ID in data_point_ids (§12.6). "
                "Creating a figure without bound data is a violation of the integrity principle."
            )
        return self

    @model_validator(mode="after")
    def _data_plot_requires_plot_kind(self) -> PanelSpec:
        """Data-plot panels must specify a plot_kind."""
        if self.panel_type is PanelType.DATA_PLOT and self.plot_kind is None:
            raise ValueError(
                f"Panel '{self.panel_id}': data-plot panels must specify plot_kind."
            )
        return self


class GridLayout(BaseModel):
    """Multi-panel grid layout specification.

    Parameters
    ----------
    nrows:
        Number of rows.
    ncols:
        Number of columns.
    hspace:
        Row spacing (matplotlib hspace, default 0.4).
    wspace:
        Column spacing (matplotlib wspace, default 0.3).
    """

    nrows: int = 1
    ncols: int = 1
    hspace: float = 0.4
    wspace: float = 0.3


# Positive integer constraint type (reusable type hint)
_PositiveInt = Annotated[int, Field(ge=1)]


class FigureSpec(BaseModel):
    """Declarative multi-panel figure IR (§12.3-①).

    When an LLM or user writes this specification, the render pipeline
    deterministically produces a vector figure.

    Parameters
    ----------
    figure_id:
        Unique figure ID.
    journal:
        Journal target (determines column width and style).
    column_width:
        Single or double column selection.
    panels:
        List of panels. Order determines labels (a/b/c/…).
    layout:
        GridSpec layout.
    caption:
        Figure caption text.
    provenance_ids:
        Complete list of DataPoint IDs associated with this figure (aggregated).
        If ``None``, auto-collected from panels.
    """

    figure_id: str
    journal: JournalTarget = JournalTarget.NATURE
    column_width: ColumnWidth = ColumnWidth.SINGLE
    panels: list[PanelSpec] = Field(default_factory=list)
    layout: GridLayout = Field(default_factory=GridLayout)
    caption: str = ""
    provenance_ids: list[str] | None = None

    model_config = {"frozen": False}

    @model_validator(mode="after")
    def _collect_provenance(self) -> FigureSpec:
        """Auto-collect provenance_ids from panels when None."""
        if self.provenance_ids is None:
            ids: list[str] = []
            for p in self.panels:
                ids.extend(p.data_point_ids)
                ids.extend(p.overlay)
            self.provenance_ids = list(dict.fromkeys(ids))
        return self

    def all_data_point_ids(self) -> list[str]:
        """Return all DataPoint IDs bound to this figure."""
        ids: list[str] = []
        for p in self.panels:
            ids.extend(p.data_point_ids)
            ids.extend(p.overlay)
        return list(dict.fromkeys(ids))

    def has_unbound_data_panels(self) -> bool:
        """Return True if any DATA_PLOT panel has empty data_point_ids."""
        return any(
            p.panel_type is PanelType.DATA_PLOT and not p.data_point_ids for p in self.panels
        )
