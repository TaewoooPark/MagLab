"""Base class and shared guardrails for all comms agents (§16.3).

Every communications agent:
    - Outputs text carrying ``HUMAN REVIEW REQUIRED`` on the first line.
    - Never auto-sends — all output is returned as a string for the
      researcher to review, edit, and send manually.
    - Marks blanks that need human personalisation with ``[FILL]`` tokens.
    - Refuses to fabricate data or citations.

Research integrity rule (§3.3):
    AI structures and polishes; the researcher's own results and sentences
    are the primary input.  The AI must not invent new findings or claims.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

# Human review marker — must appear in every output.
HUMAN_REVIEW_HEADER = "HUMAN REVIEW REQUIRED\n\n"

# Placeholder token for fields requiring direct human input.  Accepts both the
# bare ``[FILL]`` form and the labelled ``[FILL: description]`` form; detection
# keys on the ``[FILL`` prefix.
FILL_MARKER = "[FILL]"
_FILL_PREFIX = "[FILL"


class MissingFillMarkerError(Exception):
    """Raised when a final draft is missing required ``[FILL]`` placeholders.

    Comms outputs that omit ``[FILL]`` markers (e.g. the editor's name,
    institutional details) indicate the AI fabricated personal information,
    which is forbidden.
    """


@dataclass
class CommsResult:
    """Structured output of a comms agent draft call.

    Attributes
    ----------
    text:
        Full draft text including ``HUMAN REVIEW REQUIRED`` header.
    fill_markers:
        List of positions (contextual labels) where ``[FILL]`` markers appear
        — the researcher must replace these before use.
    word_count:
        Approximate word count of the draft body (excluding the header).
    """

    text: str
    fill_markers: list[str] = field(default_factory=list)
    word_count: int = 0

    def has_fill_markers(self) -> bool:
        """Return True if the draft contains at least one ``[FILL]`` marker."""
        return _FILL_PREFIX in self.text

    def is_ready_for_review(self) -> bool:
        """Return True if the header is present (HUMAN REVIEW REQUIRED)."""
        return self.text.startswith("HUMAN REVIEW REQUIRED")


def _count_words(text: str) -> int:
    """Approximate word count (splits on whitespace)."""
    return len(text.split())


def _add_header(text: str) -> str:
    """Prepend ``HUMAN REVIEW REQUIRED`` header if absent."""
    if text.startswith("HUMAN REVIEW REQUIRED"):
        return text
    return HUMAN_REVIEW_HEADER + text


def _validate_fill_markers(text: str, *, required_fills: int = 1) -> list[str]:
    """Return a list of ``[FILL]`` occurrences (raw context snippets).

    Parameters
    ----------
    text:
        Draft text.
    required_fills:
        Minimum number of ``[FILL]`` markers required.  If fewer than
        ``required_fills`` are present, a :exc:`MissingFillMarkerError` is
        raised.
    """
    # Plain string scan (no regex) — extract a brief context window around
    # each [FILL] occurrence.  Avoids any regex backtracking risk.
    markers: list[str] = []
    idx = text.find(_FILL_PREFIX)
    while idx != -1:
        start = max(0, idx - 30)
        end = min(len(text), idx + 40)
        markers.append(text[start:end].strip())
        idx = text.find(_FILL_PREFIX, idx + len(_FILL_PREFIX))

    if len(markers) < required_fills:
        raise MissingFillMarkerError(
            f"Draft contains {len(markers)} [FILL] marker(s) but at least "
            f"{required_fills} is required.  The AI must not fabricate "
            f"personal or institutional information — mark it [FILL] instead."
        )
    return markers


class BaseCommsAgent(ABC):
    """Abstract base class for all comms agents.

    Subclasses implement ``_generate_draft`` and ``_required_fill_count``
    to define the agent's logic and minimum fill-marker requirement.

    Parameters
    ----------
    llm_fn:
        LLM callable: ``(system_prompt, user_prompt) → str``.
    """

    def __init__(self, llm_fn: Callable[[str, str], str]) -> None:
        self._llm: Callable[[str, str], str] = llm_fn

    @property
    def required_fill_count(self) -> int:
        """Minimum number of ``[FILL]`` markers required in the output."""
        return 1  # subclasses override as needed

    def draft(self, inputs: dict) -> CommsResult:
        """Generate a draft from *inputs* and validate guardrails.

        Parameters
        ----------
        inputs:
            Agent-specific input dictionary.

        Returns
        -------
        ``CommsResult`` with the validated draft text.

        Raises
        ------
        MissingFillMarkerError
            If the generated draft is missing required ``[FILL]`` markers.
        """
        raw = self._generate_draft(inputs)
        text = _add_header(raw)
        fills = _validate_fill_markers(text, required_fills=self.required_fill_count)
        return CommsResult(
            text=text,
            fill_markers=fills,
            word_count=_count_words(text),
        )

    @abstractmethod
    def _generate_draft(self, inputs: dict) -> str:
        """Generate the raw draft text (without the HUMAN REVIEW header).

        Subclasses call ``self._llm(system, user)`` and must ensure the
        output contains at least ``self.required_fill_count`` ``[FILL]``
        markers.
        """
        ...
