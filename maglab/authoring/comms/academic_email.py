"""Academic email agent — ≤200 word professional academic email (§16.3).

Email types: collaboration | question | interview | recommendation | application

No auto-send — output is a string for the researcher to review and send.
"""

from __future__ import annotations

from maglab.authoring.comms.base import BaseCommsAgent, _count_words

_EMAIL_TYPES = frozenset(
    {"collaboration", "question", "interview", "recommendation", "application"}
)

WORD_LIMIT = 200


class AcademicEmailAgent(BaseCommsAgent):
    """Draft a ≤200 word academic email with subject line and follow-up (§16.3).

    Required inputs (dict keys)
    ---------------------------
    email_type : str
        One of: collaboration | question | interview | recommendation | application.
    recipient : str
        Recipient's name or title (e.g. "Professor Smith").
    topic : str
        Main purpose of the email.
    related_papers : list[str], optional
        Relevant papers by the author or recipient.
    """

    _SYSTEM = (
        "You are an academic writing assistant drafting a professional email.\n\n"
        "RULES:\n"
        "1. Body must be ≤200 words.\n"
        "2. Include a subject line on the first line: 'Subject: [concise subject]'.\n"
        "3. Mark personalisation fields with [FILL]: greeting, sender name/affiliation.\n"
        "4. Do NOT invent results or make claims beyond what the author provided.\n"
        "5. Include a 'Follow-up: [FILL: suggested date/action]' at the end.\n"
        "6. Auto-send is prohibited — this is a draft for human review only.\n"
    )

    @property
    def required_fill_count(self) -> int:
        return 2  # greeting + sender sign-off

    def _generate_draft(self, inputs: dict) -> str:
        email_type = inputs.get("email_type", "question").lower()
        if email_type not in _EMAIL_TYPES:
            email_type = "question"

        recipient = inputs.get("recipient", "[FILL: recipient name]")
        topic = inputs.get("topic", "[FILL: topic]")
        papers = inputs.get("related_papers", [])

        papers_text = (
            "\n".join(f"• {p}" for p in papers) if papers else "[FILL: relevant papers if any]"
        )

        type_hints = {
            "collaboration": "Express interest in a research collaboration on the shared topic.",
            "question": "Ask a specific technical or scientific question politely.",
            "interview": "Request a meeting or informational interview.",
            "recommendation": "Request a letter of recommendation, providing context.",
            "application": "Express interest in a position, program, or grant.",
        }
        hint = type_hints.get(email_type, "Write a professional email.")

        user = (
            f"Email type: {email_type}\n"
            f"Recipient: {recipient}\n"
            f"Topic: {topic}\n"
            f"Related papers:\n{papers_text}\n\n"
            f"Instruction: {hint}\n"
            f"Draft a ≤{WORD_LIMIT} word email with subject line and follow-up action."
        )

        draft = self._llm(self._SYSTEM, user)

        body_words = _count_words(draft)
        if body_words > WORD_LIMIT:
            import logging

            logging.getLogger(__name__).warning(
                "Academic email word count %d exceeds limit %d.", body_words, WORD_LIMIT
            )
        return draft
