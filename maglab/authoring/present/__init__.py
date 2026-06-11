"""Presentation drafters — slides and posters (§16.6).

Modules:
    catalog        — Source-backed presentation template profiles.
    slide_drafter  — Beamer / python-pptx / Marp structured deck.
    poster_drafter — SVG/PDF/beamerposter poster layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Lazy public API (PEP 562). The slide/poster drafters need optional extras
# (python-pptx, pylatex); the catalog does not. Resolving names lazily lets
# `maglab present templates` list templates without dragging in those extras.
if TYPE_CHECKING:
    from maglab.authoring.present.catalog import PresentationTemplate, list_presentation_templates
    from maglab.authoring.present.poster_drafter import PosterDrafter, PosterFile
    from maglab.authoring.present.slide_drafter import SlideDeck, SlideFormat, SlidesDrafter

_LAZY_IMPORTS: dict[str, str] = {
    "PresentationTemplate": "catalog",
    "list_presentation_templates": "catalog",
    "PosterDrafter": "poster_drafter",
    "PosterFile": "poster_drafter",
    "SlideDeck": "slide_drafter",
    "SlideFormat": "slide_drafter",
    "SlidesDrafter": "slide_drafter",
}


def __getattr__(name: str):  # noqa: N807 - PEP 562 module-level hook
    submodule = _LAZY_IMPORTS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f"{__name__}.{submodule}")
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "PresentationTemplate",
    "list_presentation_templates",
    "SlidesDrafter",
    "SlideDeck",
    "SlideFormat",
    "PosterDrafter",
    "PosterFile",
]
