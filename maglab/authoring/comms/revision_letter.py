"""Revision letter agent — point-by-point reviewer response letter (§16.3).

Input:
    - review_decision:   Journal decision letter text.
    - manuscript_orig:   Original manuscript (text or path reference).
    - manuscript_rev:    Revised manuscript (text or path reference).
    - comment_notes:     Per-comment author notes (list of strings).
    - tone:              One of "formal" | "respectful" | "assertive".

Output:
    - Point-by-point response letter.
    - Each reviewer comment is quoted verbatim → response → change location
      (page/line number as ``[FILL]`` if not specified).
    - ``HUMAN REVIEW REQUIRED`` header.
"""

from __future__ import annotations

from maglab.authoring.comms.base import BaseCommsAgent


class RevisionLetterAgent(BaseCommsAgent):
    """Draft a reviewer revision response letter (§16.3).

    Required inputs (dict keys)
    ---------------------------
    review_decision : str
        Full journal decision letter containing reviewer comments.
    comment_notes : list[str] | str
        Per-comment author notes.  May be empty; AI will insert [FILL].
    tone : str, optional
        "formal" (default) | "respectful" | "assertive".
    manuscript_orig : str, optional
        Original manuscript excerpt (for context).
    manuscript_rev : str, optional
        Revised manuscript excerpt (for context).
    """

    _SYSTEM = (
        "You are a senior academic writing assistant helping an author respond "
        "to journal peer reviewers.\n\n"
        "RULES:\n"
        "1. Quote each reviewer comment verbatim before responding.\n"
        "2. After each response, add a 'Change location: [FILL]' line for the "
        "   author to fill in the page and line number.\n"
        "3. Do NOT invent experimental data or new results.\n"
        "4. Keep the tone specified by the author.\n"
        "5. Insert [FILL] wherever the author must personalise content "
        "   (editor name, page numbers, new data references, etc.).\n"
        "6. Begin the letter with '[FILL: Editor name and salutation]'.\n"
    )

    @property
    def required_fill_count(self) -> int:
        return 2  # at minimum: editor salutation + change locations

    def _generate_draft(self, inputs: dict) -> str:
        decision = inputs.get("review_decision", "")
        notes = inputs.get("comment_notes", [])
        tone = inputs.get("tone", "formal")
        orig = inputs.get("manuscript_orig", "")
        rev = inputs.get("manuscript_rev", "")

        if isinstance(notes, list):
            notes_text = "\n".join(f"- Comment {i + 1}: {n}" for i, n in enumerate(notes))
        else:
            notes_text = str(notes)

        user = (
            f"Tone: {tone}\n\n"
            f"REVIEW DECISION LETTER:\n{decision}\n\n"
            f"AUTHOR NOTES PER COMMENT:\n{notes_text or '[FILL: add your notes]'}\n\n"
        )
        if orig:
            user += f"ORIGINAL MANUSCRIPT EXCERPT:\n{orig[:2000]}\n\n"
        if rev:
            user += f"REVISED MANUSCRIPT EXCERPT:\n{rev[:2000]}\n\n"
        user += (
            "Draft a point-by-point revision response letter.  "
            "Quote each reviewer comment verbatim, then respond, then add "
            "'Change location: [FILL]' after each response."
        )

        return self._llm(self._SYSTEM, user)
