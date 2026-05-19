"""Communications agent suite — 6 agents for academic correspondence (§16.3).

Available agents:
    RevisionLetterAgent    — point-by-point reviewer response letter.
    CoverLetterAgent       — ≤250 word journal submission cover letter.
    AcademicEmailAgent     — ≤200 word professional academic email.
    ConferenceAbstractAgent — within character-limit conference abstract.
    GrantTextAgent         — section-by-section grant proposal text.
    RebuttalAgent          — ≤1-page conference rebuttal.

All agents:
    - Output ``HUMAN REVIEW REQUIRED`` on the first line.
    - Never auto-send — output is a string for human review.
    - Mark personalisation blanks with ``[FILL]``.
    - Do not fabricate data, results, or citations.
"""

from __future__ import annotations

from maglab.authoring.comms.academic_email import AcademicEmailAgent
from maglab.authoring.comms.base import (
    FILL_MARKER,
    HUMAN_REVIEW_HEADER,
    BaseCommsAgent,
    CommsResult,
    MissingFillMarkerError,
)
from maglab.authoring.comms.conference_abstract import ConferenceAbstractAgent
from maglab.authoring.comms.cover_letter import CoverLetterAgent
from maglab.authoring.comms.grant_text import GrantTextAgent
from maglab.authoring.comms.rebuttal import RebuttalAgent
from maglab.authoring.comms.revision_letter import RevisionLetterAgent

__all__ = [
    "BaseCommsAgent",
    "CommsResult",
    "FILL_MARKER",
    "HUMAN_REVIEW_HEADER",
    "MissingFillMarkerError",
    "RevisionLetterAgent",
    "CoverLetterAgent",
    "AcademicEmailAgent",
    "ConferenceAbstractAgent",
    "GrantTextAgent",
    "RebuttalAgent",
]
