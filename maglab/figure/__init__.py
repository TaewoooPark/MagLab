"""maglab.figure — Figure production engine (§12).

Public API:
- ``FigureSpec`` : Declarative figure IR.
- ``FigureComposer`` : Multi-panel composition.
- ``FigureExporter`` : Vector export.
- ``DataPlotRenderer`` : matplotlib data-plot renderer.
- ``load_style`` : Journal style profile loader.
"""

from __future__ import annotations

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

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "FigureComposer": ("maglab.figure.compose", "FigureComposer"),
    "FigureExporter": ("maglab.figure.export", "FigureExporter"),
    "DataPlotRenderer": ("maglab.figure.renderers.dataplot", "DataPlotRenderer"),
    "IntegrityError": ("maglab.figure.renderers.dataplot", "IntegrityError"),
}


def __getattr__(name: str) -> object:
    """Load renderer/exporter classes only when callers ask for them."""
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module 'maglab.figure' has no attribute {name!r}")
    import importlib

    module_name, attr_name = _LAZY_ATTRS[name]
    value = getattr(importlib.import_module(module_name), attr_name)
    globals()[name] = value
    return value


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
