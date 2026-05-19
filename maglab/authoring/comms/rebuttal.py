"""Rebuttal agent — 1-page conference rebuttal (§16.3).

Input:
    - reviews:      Conference review text(s).
    - author_notes: Author's rebuttal notes.

Output:
    - ≤1 page (~600 words) rebuttal.
    - Clarifies existing results only — no new data fabrication.
"""

from __future__ import annotations

from maglab.authoring.comms.base import FILL_MARKER, BaseCommsAgent, _count_words

REBUTTAL_WORD_LIMIT = 600


class RebuttalAgent(BaseCommsAgent):
    """Draft a ≤1-page conference rebuttal (§16.3).

    Required inputs (dict keys)
    ---------------------------
    reviews : str | list[str]
        Conference review text(s).
    author_notes : str
        Author's key rebuttal points.
    """

    _SYSTEM = (
        "You are an academic writing assistant drafting a conference rebuttal.\n\n"
        "RULES:\n"
        "1. Rebuttal must be ≤600 words (~1 page).\n"
        "2. Clarify existing results and methods only — do NOT introduce new "
        "   experimental data or make new claims.\n"
        "3. Address each major reviewer concern concisely.\n"
        "4. Insert [FILL] for any specific result the author needs to verify "
        "   before including.\n"
        "5. Keep tone respectful and professional.\n"
    )

    @property
    def required_fill_count(self) -> int:
        return 1

    def _generate_draft(self, inputs: dict) -> str:
        reviews = inputs.get("reviews", "")
        notes = inputs.get("author_notes", "")

        if isinstance(reviews, list):
            reviews_text = "\n\n---\n\n".join(reviews)
        else:
            reviews_text = str(reviews) or "[FILL: paste review text]"

        user = (
            f"CONFERENCE REVIEWS:\n{reviews_text}\n\n"
            f"AUTHOR NOTES:\n{notes or FILL_MARKER}\n\n"
            f"Draft a ≤{REBUTTAL_WORD_LIMIT} word rebuttal that clarifies "
            "existing results and addresses each major concern."
        )

        draft = self._llm(self._SYSTEM, user)

        body_words = _count_words(draft)
        if body_words > REBUTTAL_WORD_LIMIT:
            import logging

            logging.getLogger(__name__).warning(
                "Rebuttal word count %d exceeds limit %d.", body_words, REBUTTAL_WORD_LIMIT
            )
        return draft
