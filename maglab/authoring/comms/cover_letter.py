"""Cover letter agent — ≤250 word journal submission cover letter (§16.3).

Input:
    - journal:        Target journal name.
    - title:          Manuscript title.
    - key_results:    1–3 bullet-point key results (list[str] or str).
    - related_pubs:   Related published papers by the authors (list[str]).
"""

from __future__ import annotations

from maglab.authoring.comms.base import FILL_MARKER, BaseCommsAgent, _count_words


class CoverLetterAgent(BaseCommsAgent):
    """Draft a ≤250 word cover letter for journal submission (§16.3).

    Required inputs (dict keys)
    ---------------------------
    journal : str
        Target journal name (e.g. "Physical Review Letters").
    title : str
        Manuscript title.
    key_results : list[str] | str
        Key results to highlight.
    related_pubs : list[str], optional
        Related published works (for "novelty statement").
    """

    WORD_LIMIT = 250

    _SYSTEM = (
        "You are an academic writing assistant drafting a cover letter for "
        "a journal manuscript submission.\n\n"
        "RULES:\n"
        "1. The letter must be ≤250 words (body only, excluding salutation).\n"
        "2. Begin with '[FILL: Dear Editor-in-Chief / Dr. [FILL: editor name],'\n"
        "3. Include a novelty statement based only on the provided key results.\n"
        "4. Do NOT invent results or citations.\n"
        "5. End with '[FILL: Corresponding author name, affiliation, email]'.\n"
        "6. Mark any field that needs personalisation with [FILL].\n"
    )

    @property
    def required_fill_count(self) -> int:
        return 2  # at minimum: editor salutation + author sign-off

    def _generate_draft(self, inputs: dict) -> str:
        journal = inputs.get("journal", "[FILL: journal name]")
        title = inputs.get("title", "[FILL: manuscript title]")
        key_results = inputs.get("key_results", "")
        related = inputs.get("related_pubs", [])

        if isinstance(key_results, list):
            results_text = "\n".join(f"• {r}" for r in key_results)
        else:
            results_text = str(key_results) or FILL_MARKER

        related_text = (
            "\n".join(f"• {p}" for p in related)
            if related
            else "[FILL: related publications if any]"
        )

        user = (
            f"Target journal: {journal}\n"
            f"Manuscript title: {title}\n\n"
            f"Key results:\n{results_text}\n\n"
            f"Related publications by the authors:\n{related_text}\n\n"
            f"Draft a cover letter of ≤{self.WORD_LIMIT} words."
        )

        draft = self._llm(self._SYSTEM, user)

        # Word count check
        body_words = _count_words(draft)
        if body_words > self.WORD_LIMIT:
            import logging

            logging.getLogger(__name__).warning(
                "Cover letter word count %d exceeds limit %d.",
                body_words,
                self.WORD_LIMIT,
            )
        return draft
