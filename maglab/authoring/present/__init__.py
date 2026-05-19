"""Presentation drafters — slides and posters (§16.6).

Modules:
    slide_drafter  — Beamer / python-pptx / Marp structured deck.
    poster_drafter — A0 SVG poster layout.
"""

from __future__ import annotations

from maglab.authoring.present.poster_drafter import PosterDrafter, PosterFile
from maglab.authoring.present.slide_drafter import SlideDeck, SlideFormat, SlidesDrafter

__all__ = [
    "SlidesDrafter",
    "SlideDeck",
    "SlideFormat",
    "PosterDrafter",
    "PosterFile",
]
