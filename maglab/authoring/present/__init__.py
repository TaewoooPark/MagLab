"""Presentation drafters — slides and posters (§16.6).

Modules:
    catalog        — Source-backed presentation template profiles.
    slide_drafter  — Beamer / python-pptx / Marp structured deck.
    poster_drafter — SVG/PDF/beamerposter poster layout.
"""

from __future__ import annotations

from maglab.authoring.present.catalog import PresentationTemplate, list_presentation_templates
from maglab.authoring.present.poster_drafter import PosterDrafter, PosterFile
from maglab.authoring.present.slide_drafter import SlideDeck, SlideFormat, SlidesDrafter

__all__ = [
    "PresentationTemplate",
    "list_presentation_templates",
    "SlidesDrafter",
    "SlideDeck",
    "SlideFormat",
    "PosterDrafter",
    "PosterFile",
]
