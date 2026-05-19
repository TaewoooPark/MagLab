"""Grant text agent — section-by-section grant proposal text (§16.3).

Supports NSF / DOE / generic mechanisms.
Numbers and literature enter only via DataVault and verified cite-keys.
"""

from __future__ import annotations

from maglab.authoring.comms.base import BaseCommsAgent

_AGENCIES = frozenset({"nsf", "doe", "nih", "other"})


class GrantTextAgent(BaseCommsAgent):
    """Draft grant proposal sections within specified length constraints (§16.3).

    Required inputs (dict keys)
    ---------------------------
    agency : str
        Funding agency: nsf | doe | nih | other.
    mechanism : str
        Mechanism or program (e.g. "NSF CAREER", "DOE Early Career").
    specific_aims : str
        Researcher-provided specific aims narrative.
    page_limit : int, optional
        Page limit (default 2 pages).
    verified_cite_keys : list[str], optional
        Verified BibTeX cite-keys the agent may reference.
    """

    _SYSTEM = (
        "You are an academic writing assistant helping a researcher draft "
        "a grant proposal.\n\n"
        "RULES:\n"
        "1. Respect the page/word limit.  Flag if exceeded.\n"
        "2. Use only cite-keys from the provided verified list.\n"
        "3. Insert [FILL] for budget figures, co-investigator names, "
        "   institutional details, and any content the author must provide.\n"
        "4. Do NOT invent data, results, or citations.\n"
        "5. Produce clearly labelled sections: Background, Objectives, "
        "   Approach, Broader Impact / Significance.\n"
    )

    @property
    def required_fill_count(self) -> int:
        return 3  # budget, personnel, institutional details at minimum

    def _generate_draft(self, inputs: dict) -> str:
        agency = inputs.get("agency", "other").lower()
        mechanism = inputs.get("mechanism", "[FILL: mechanism]")
        aims = inputs.get("specific_aims", "[FILL: specific aims]")
        page_limit = int(inputs.get("page_limit", 2))
        cite_keys = inputs.get("verified_cite_keys", [])

        cite_block = (
            f"Verified cite-keys you may reference: {', '.join(cite_keys)}\n\n"
            if cite_keys
            else "No citation list provided — use [FILL] for any references.\n\n"
        )

        agency_hints = {
            "nsf": "Follow NSF formatting: Project Summary + Project Description + References.",
            "doe": "Follow DOE SC structure: Executive Summary + Technical Narrative.",
            "nih": "Follow NIH structure: Specific Aims + Research Strategy.",
            "other": "Use a generic structure: Background + Objectives + Approach.",
        }
        hint = agency_hints.get(agency, agency_hints["other"])

        user = (
            f"Agency: {agency.upper()}\n"
            f"Mechanism: {mechanism}\n"
            f"Page limit: {page_limit} pages\n\n"
            f"{cite_block}"
            f"Specific aims provided by the researcher:\n{aims}\n\n"
            f"{hint}\n\n"
            "Draft the grant text sections. Mark budget figures, co-PI names, "
            "and institutional details with [FILL]."
        )

        return self._llm(self._SYSTEM, user)
