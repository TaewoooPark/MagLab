"""Conference abstract agent — within character/word limit (§16.3).

Numerical values come only from DataVault DataPoints.
Character limit enforced; exceeding it raises an error.
"""

from __future__ import annotations

from maglab.authoring.comms.base import BaseCommsAgent
from maglab.authoring.data_vault import AuthoringBlockedError, DataVault


class ConferenceAbstractAgent(BaseCommsAgent):
    """Draft a conference abstract within the specified character limit (§16.3).

    Required inputs (dict keys)
    ---------------------------
    conference : str
        Name of the conference.
    char_limit : int
        Character limit for the abstract body.
    results_context : str
        Researcher-provided summary of results (may include {{dp:KEY}} placeholders).
    vault : DataVault, optional
        ``DataVault`` for resolving ``{{dp:KEY}}`` placeholders.
    """

    _SYSTEM = (
        "You are an academic writing assistant drafting a conference abstract.\n\n"
        "RULES:\n"
        "1. The abstract must respect the character limit provided.\n"
        "2. Numerical values must be expressed as {{dp:KEY}} placeholders.\n"
        "3. Do NOT invent numbers or citations.\n"
        "4. Structure: background → methods → key result → conclusion.\n"
        "5. Insert [FILL] for any content the author must personalise.\n"
    )

    @property
    def required_fill_count(self) -> int:
        return 1

    def _generate_draft(self, inputs: dict) -> str:
        conference = inputs.get("conference", "[FILL: conference name]")
        char_limit = int(inputs.get("char_limit", 1750))
        context = inputs.get("results_context", "[FILL: results summary]")
        vault: DataVault | None = inputs.get("vault")

        user = (
            f"Conference: {conference}\n"
            f"Character limit: {char_limit}\n\n"
            f"Results context:\n{context}\n\n"
            f"Draft a conference abstract within {char_limit} characters."
        )

        draft = self._llm(self._SYSTEM, user)

        # Resolve data vault placeholders if vault is provided
        if vault is not None:
            missing = vault.validate_draft(draft)
            if missing:
                raise AuthoringBlockedError(
                    f"Conference abstract blocked: missing DataPoint(s) for "
                    f"placeholder(s): {missing}."
                )
            draft = vault.inject_into_draft(draft)

        # Character limit check
        if len(draft) > char_limit:
            raise ValueError(
                f"Conference abstract exceeds character limit: "
                f"{len(draft)} > {char_limit} characters."
            )

        return draft
