"""Unit tests for maglab/authoring/comms/ agents (§16.3).

All LLM calls are mocked with deterministic stubs that return text containing
the required [FILL] markers.
"""

from __future__ import annotations

import pytest

from maglab.authoring.comms import (
    AcademicEmailAgent,
    CoverLetterAgent,
    GrantTextAgent,
    MissingFillMarkerError,
    RebuttalAgent,
    RevisionLetterAgent,
)
from maglab.authoring.comms.base import HUMAN_REVIEW_HEADER
from maglab.authoring.comms.conference_abstract import ConferenceAbstractAgent
from maglab.authoring.data_vault import DataVault

# ---------------------------------------------------------------------------
# Mock LLM factory
# ---------------------------------------------------------------------------


def _make_llm(response: str):
    """Return a mock LLM function that ignores its prompts and returns *response*."""

    def _llm(system: str, user: str) -> str:  # noqa: ARG001
        return response

    return _llm


_MINIMAL_RESPONSE_WITH_FILLS = (
    "[FILL: Dear Editor] Thank you for reviewing our manuscript.\n"
    "We measured the anomalous Hall resistivity.\n"
    "Change location: [FILL: page 3, line 12]\n"
    "[FILL: Corresponding Author]\n"
)

_COVER_LETTER_RESPONSE = (
    "[FILL: Dear Dr. Editor] We submit our manuscript titled [FILL: title].\n"
    "Our key finding is a large anomalous Hall effect.\n"
    "Yours sincerely,\n"
    "[FILL: Author name, affiliation, email]\n"
)

_EMAIL_RESPONSE = (
    "Subject: Research Collaboration Inquiry\n"
    "[FILL: Dear Professor Smith,]\n"
    "I am writing to inquire about a potential collaboration.\n"
    "Follow-up: [FILL: suggested date]\n"
    "[FILL: Your name]\n"
)

_GRANT_RESPONSE = (
    "Background: [FILL: funding agency context]\n"
    "Objectives: Investigate AHE in thin films.\n"
    "Budget: [FILL: budget figures]\n"
    "Co-PI: [FILL: co-investigator name]\n"
    "Institutional details: [FILL: university name]\n"
)

_REBUTTAL_RESPONSE = (
    "[FILL: Reviewer concern 1] We clarify that our AHE measurement follows...\n"
    "No new data is presented — this is a clarification of existing results.\n"
    "Follow-up: [FILL: action item]\n"
)


class TestRevisionLetterAgent:
    """Tests for RevisionLetterAgent."""

    def test_draft_returns_comms_result(self) -> None:
        """draft() returns a CommsResult."""
        from maglab.authoring.comms import CommsResult

        agent = RevisionLetterAgent(_make_llm(_MINIMAL_RESPONSE_WITH_FILLS))
        result = agent.draft({"review_decision": "Accept with revisions.", "comment_notes": []})
        assert isinstance(result, CommsResult)

    def test_draft_has_human_review_header(self) -> None:
        """Draft text starts with HUMAN REVIEW REQUIRED."""
        agent = RevisionLetterAgent(_make_llm(_MINIMAL_RESPONSE_WITH_FILLS))
        result = agent.draft({"review_decision": "Minor revision.", "comment_notes": ["OK"]})
        assert result.text.startswith("HUMAN REVIEW REQUIRED")

    def test_draft_contains_fill_markers(self) -> None:
        """Draft contains at least one [FILL] marker."""
        agent = RevisionLetterAgent(_make_llm(_MINIMAL_RESPONSE_WITH_FILLS))
        result = agent.draft({"review_decision": "Revision required.", "comment_notes": []})
        assert result.has_fill_markers()

    def test_draft_without_fill_raises(self) -> None:
        """A response lacking [FILL] markers raises MissingFillMarkerError."""
        no_fill_response = "We appreciate the reviewers' comments and have revised accordingly."
        agent = RevisionLetterAgent(_make_llm(no_fill_response))
        with pytest.raises(MissingFillMarkerError):
            agent.draft({"review_decision": "Accept.", "comment_notes": []})


class TestCoverLetterAgent:
    """Tests for CoverLetterAgent."""

    def test_draft_word_count_reasonable(self) -> None:
        """Draft word count is reported (may exceed limit with mock but field exists)."""
        agent = CoverLetterAgent(_make_llm(_COVER_LETTER_RESPONSE))
        result = agent.draft(
            {
                "journal": "PRL",
                "title": "AHE in GdFeCo",
                "key_results": ["Large AHE", "Room temperature"],
            }
        )
        assert result.word_count > 0

    def test_draft_has_fill_markers(self) -> None:
        """Cover letter contains [FILL] markers."""
        agent = CoverLetterAgent(_make_llm(_COVER_LETTER_RESPONSE))
        result = agent.draft({"journal": "PRL", "title": "Test", "key_results": "Large AHE"})
        assert result.has_fill_markers()

    def test_draft_header_present(self) -> None:
        """HUMAN REVIEW REQUIRED header is present."""
        agent = CoverLetterAgent(_make_llm(_COVER_LETTER_RESPONSE))
        result = agent.draft({"journal": "PRL", "title": "Test", "key_results": "Finding"})
        assert result.is_ready_for_review()


class TestAcademicEmailAgent:
    """Tests for AcademicEmailAgent."""

    @pytest.mark.parametrize(
        "email_type",
        ["collaboration", "question", "interview", "recommendation", "application"],
    )
    def test_all_email_types_produce_result(self, email_type: str) -> None:
        """All five email types produce a CommsResult."""
        agent = AcademicEmailAgent(_make_llm(_EMAIL_RESPONSE))
        result = agent.draft({"email_type": email_type, "recipient": "Prof. Kim", "topic": "AHE"})
        assert result is not None
        assert result.has_fill_markers()

    def test_invalid_email_type_defaults_gracefully(self) -> None:
        """An unrecognised email type defaults to 'question' without crashing."""
        agent = AcademicEmailAgent(_make_llm(_EMAIL_RESPONSE))
        result = agent.draft(
            {"email_type": "unknown_type", "recipient": "Prof. Lee", "topic": "DMI"}
        )
        assert result is not None


class TestGrantTextAgent:
    """Tests for GrantTextAgent."""

    def test_draft_has_three_fill_markers(self) -> None:
        """Grant text has at least 3 [FILL] markers."""
        agent = GrantTextAgent(_make_llm(_GRANT_RESPONSE))
        result = agent.draft(
            {"agency": "nsf", "mechanism": "CAREER", "specific_aims": "Measure AHE."}
        )
        fills = result.fill_markers
        assert len(fills) >= 3

    def test_draft_for_doe(self) -> None:
        """DOE grant text is produced without errors."""
        agent = GrantTextAgent(_make_llm(_GRANT_RESPONSE))
        result = agent.draft({"agency": "doe", "mechanism": "Early Career", "specific_aims": "..."})
        assert result.is_ready_for_review()


class TestRebuttalAgent:
    """Tests for RebuttalAgent."""

    def test_draft_has_fill_markers(self) -> None:
        """Rebuttal contains [FILL] markers."""
        agent = RebuttalAgent(_make_llm(_REBUTTAL_RESPONSE))
        result = agent.draft(
            {"reviews": "Reviewer 1: Clarify the method.", "author_notes": "We will clarify."}
        )
        assert result.has_fill_markers()

    def test_draft_is_ready_for_review(self) -> None:
        """Rebuttal passes is_ready_for_review()."""
        agent = RebuttalAgent(_make_llm(_REBUTTAL_RESPONSE))
        result = agent.draft(
            {"reviews": "Concern about validity.", "author_notes": "It is valid because..."}
        )
        assert result.is_ready_for_review()


class TestConferenceAbstractAgent:
    """Tests for ConferenceAbstractAgent."""

    def test_draft_within_char_limit(self) -> None:
        """Abstract stays within the character limit."""
        # Mock returns a short response that fits in 1750 chars
        short_response = (
            "This study investigates anomalous Hall effect in GdFeCo thin films. "
            "Large Hall resistivity is observed at room temperature. "
            "[FILL: conference-specific closing]\n"
        )
        agent = ConferenceAbstractAgent(_make_llm(short_response))
        result = agent.draft(
            {
                "conference": "APS March Meeting",
                "char_limit": 1750,
                "results_context": "AHE measured at 300K.",
            }
        )
        assert len(result.text) <= 1750 + len(HUMAN_REVIEW_HEADER)

    def test_draft_exceeds_limit_raises(self) -> None:
        """Abstract exceeding the character limit raises ValueError."""
        long_response = "A" * 2000 + " [FILL: something]"
        agent = ConferenceAbstractAgent(_make_llm(long_response))
        with pytest.raises(ValueError, match="exceeds character limit"):
            agent.draft(
                {
                    "conference": "APS March Meeting",
                    "char_limit": 500,
                    "results_context": "Measurement results.",
                }
            )

    def test_data_vault_missing_blocks(self) -> None:
        """Abstract with missing DataVault placeholder raises AuthoringBlockedError."""
        from maglab.authoring.data_vault import AuthoringBlockedError

        response_with_placeholder = (
            "AHE resistivity {{dp:rho_AHE}} was measured. [FILL: conclusion]\n"
        )
        agent = ConferenceAbstractAgent(_make_llm(response_with_placeholder))
        vault = DataVault()  # empty vault
        with pytest.raises(AuthoringBlockedError, match="rho_AHE"):
            agent.draft(
                {
                    "conference": "APS",
                    "char_limit": 2000,
                    "results_context": "AHE in GdFeCo.",
                    "vault": vault,
                }
            )

    # --- Regression test for F1 (key mismatch silently discarded user input) ---

    def test_results_context_key_used_not_discarded(self) -> None:
        """F1 regression: the LLM prompt must include the researcher-supplied results text.

        The CLI calls agent.draft({"results_context": "<user text>"}).
        If the agent reads a different key (e.g. "results"), the user's input is
        silently replaced by the fallback sentinel.  This test captures the actual
        user-supplied string in the LLM prompt and asserts it appears there.
        """
        captured_user_prompts: list[str] = []

        def _recording_llm(system: str, user: str) -> str:  # noqa: ARG001
            captured_user_prompts.append(user)
            return "This abstract describes key results. [FILL: conclusion]\n"

        agent = ConferenceAbstractAgent(llm_fn=_recording_llm)
        user_results = "Hall resistivity plateau at 300 K: rho_AHE = 1.23 Ohm"
        agent.draft(
            {
                "conference": "APS March Meeting",
                "char_limit": 2000,
                "results_context": user_results,
            }
        )

        assert captured_user_prompts, "LLM was never called"
        combined_prompt = " ".join(captured_user_prompts)
        assert user_results in combined_prompt, (
            f"User-supplied results_context was NOT forwarded to the LLM.\n"
            f"Expected to find: {user_results!r}\n"
            f"LLM received: {combined_prompt!r}"
        )
