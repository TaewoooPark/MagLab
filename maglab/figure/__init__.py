"""maglab.figure — Figure production engine (§12).

Public API:
- ``FigureSpec`` : Declarative figure IR.
- ``FigureComposer`` : Multi-panel composition.
- ``FigureExporter`` : Vector export.
- ``DataPlotRenderer`` : matplotlib data-plot renderer.
- ``load_style`` : Journal style profile loader.
"""

from __future__ import annotations

from maglab.figure.compose import FigureComposer
from maglab.figure.export import FigureExporter
from maglab.figure.renderers.dataplot import DataPlotRenderer, IntegrityError
from maglab.figure.spec import (
    AxisSpec,
    ColumnWidth,
    FigureSpec,
    GridLayout,
    GridPosition,
    JournalTarget,
    PanelSpec,
    PanelType,
    PlotKind,
)
from maglab.figure.styles import StyleProfile, load_style

__all__ = [
    "FigureSpec",
    "PanelSpec",
    "PanelType",
    "PlotKind",
    "JournalTarget",
    "ColumnWidth",
    "GridLayout",
    "GridPosition",
    "AxisSpec",
    "FigureComposer",
    "FigureExporter",
    "DataPlotRenderer",
    "IntegrityError",
    "StyleProfile",
    "load_style",
]
