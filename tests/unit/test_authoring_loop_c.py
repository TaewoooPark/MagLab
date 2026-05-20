"""Unit tests for maglab/authoring/loop_c.py (§16.5)."""

from __future__ import annotations

import re

from maglab.authoring.bib_manager import BibManager
from maglab.authoring.data_vault import DataVault
from maglab.authoring.loop_c import LoopCResult, run_loop_c
from maglab.provenance.datapoint import DataPoint, ProvenanceType


def _make_dp(value: float = 1.23, units: str = "T") -> DataPoint:
    return DataPoint(
        value=value,
        units=units,
        provenance_type=ProvenanceType.MEASURED,
        source_ref="test",
    )


def _make_llm():
    """Mock LLM that returns a minimal valid section draft."""

    def _llm(system: str, user: str) -> str:  # noqa: ARG001
        return (
            "This section describes the experimental methods. "
            "No numerical values or citations are fabricated. "
            "[FILL: details to be added by the researcher]"
        )

    return _llm


class TestLoopC:
    """Tests for run_loop_c."""

    def test_run_loop_c_returns_result(self, tmp_path) -> None:
        """run_loop_c returns a LoopCResult."""
        result = run_loop_c(
            goal="Draft AHE manuscript",
            results_context="AHE was measured in GdFeCo thin films.",
            vault=DataVault(),
            bib_manager=BibManager(),
            llm_fn=_make_llm(),
            output_dir=tmp_path,
            compile_tex=False,
            max_iterations=6,
        )
        assert isinstance(result, LoopCResult)

    def test_loop_c_max_iterations_six(self, tmp_path) -> None:
        """Loop C caps at 6 iterations even if requested more."""
        result = run_loop_c(
            goal="Draft",
            results_context="Results.",
            vault=DataVault(),
            bib_manager=BibManager(),
            llm_fn=_make_llm(),
            output_dir=tmp_path,
            compile_tex=False,
            max_iterations=20,  # should be capped to 6
        )
        # The loop should have run at most 6 ralph iterations
        assert result.iterations <= 6

    def test_loop_c_creates_human_review_marker(self, tmp_path) -> None:
        """Loop C writes HUMAN_REVIEW_REQUIRED.txt to the output directory."""
        run_loop_c(
            goal="Draft manuscript",
            results_context="Main result: large AHE.",
            vault=DataVault(),
            bib_manager=BibManager(),
            llm_fn=_make_llm(),
            output_dir=tmp_path,
            compile_tex=False,
        )
        marker_file = tmp_path / "HUMAN_REVIEW_REQUIRED.txt"
        assert marker_file.is_file()
        content = marker_file.read_text(encoding="utf-8")
        assert "HUMAN REVIEW REQUIRED" in content

    def test_loop_c_human_review_required_true(self, tmp_path) -> None:
        """LoopCResult.human_review_required is always True."""
        result = run_loop_c(
            goal="Draft",
            results_context="Results.",
            vault=DataVault(),
            bib_manager=BibManager(),
            llm_fn=_make_llm(),
            output_dir=tmp_path,
            compile_tex=False,
        )
        assert result.human_review_required is True

    def test_loop_c_section_drafts_produced(self, tmp_path) -> None:
        """Loop C produces at least one section draft."""
        result = run_loop_c(
            goal="Draft AHE paper",
            results_context="AHE measured at room temperature.",
            vault=DataVault(),
            bib_manager=BibManager(),
            llm_fn=_make_llm(),
            output_dir=tmp_path,
            compile_tex=False,
        )
        # At least one section should be drafted
        assert len(result.section_drafts) >= 1

    def test_loop_c_human_gate_can_reject(self, tmp_path) -> None:
        """A human gate that always rejects stops the loop after first section."""
        calls: list[str] = []

        def _rejecting_gate(section_name: str, draft) -> bool:
            calls.append(section_name)
            return False  # always reject

        result = run_loop_c(
            goal="Draft",
            results_context="Results.",
            vault=DataVault(),
            bib_manager=BibManager(),
            llm_fn=_make_llm(),
            human_gate_fn=_rejecting_gate,
            output_dir=tmp_path,
            compile_tex=False,
        )
        # Section drafts should be empty (all rejected)
        assert len(result.section_drafts) == 0


# ---------------------------------------------------------------------------
# Regression: Finding 1 — critic-revised drafts must have vault injection applied
# ---------------------------------------------------------------------------


class TestLoopCCriticRevisionVaultInjection:
    """Regression tests for Finding 1 (HIGH): critic-revised drafts bypass DataVault injection.

    The bug: after a critic revision the loop wrote the raw LLM text to
    draft_result.tex without calling vault.inject_into_draft, so
    {{dp:KEY}} placeholders could survive into output files.
    """

    _PLACEHOLDER_RE = re.compile(r"\{\{dp:[A-Za-z0-9_.-]+\}\}")

    def test_critic_revised_draft_has_no_dp_placeholders(self, tmp_path) -> None:
        """After critic revision, {{dp:KEY}} placeholders must be resolved in the output.

        A vault key 'B_field' is registered.  The first LLM call returns a draft
        containing the placeholder; the critic flags it; the second LLM call (revision)
        also returns the placeholder.  The fixed code must inject the vault value on
        the revised text so no {{dp:*}} survives.
        """
        vault = DataVault({"B_field": _make_dp(0.5, "T")})

        call_count: list[int] = [0]

        def _llm(system: str, user: str) -> str:
            call_count[0] += 1
            # Both the initial draft and the revision contain the placeholder
            return "Field strength is {{dp:B_field}} applied to the sample."

        def _critic(section_name: str, draft_tex: str) -> str:
            # Always return substantive feedback to trigger a revision
            return "Expand the description of the experimental setup (>10 chars)."

        result = run_loop_c(
            goal="Draft test manuscript",
            results_context="Magnetic field applied.",
            vault=vault,
            bib_manager=BibManager(),
            llm_fn=_llm,
            critic_fn=_critic,
            output_dir=tmp_path,
            compile_tex=False,
        )

        # The LLM was called at least twice (initial + revision) per section
        assert call_count[0] >= 2, "Critic must trigger at least one revision call"

        # No {{dp:KEY}} placeholder must survive in any section draft
        for section_name, draft_result in result.section_drafts.items():
            residual = self._PLACEHOLDER_RE.findall(draft_result.tex)
            assert not residual, (
                f"Finding 1 regression: {{{{dp:KEY}}}} placeholder survived in "
                f"critic-revised draft for section '{section_name}': {residual}"
            )

    def test_critic_revised_draft_contains_injected_value(self, tmp_path) -> None:
        """Vault-injected values (with provenance comment) must appear in revised tex.

        After the fix, vault.inject_into_draft runs on the revision output.
        The resolved text must contain the provenance comment marker '[prov:' that
        DataVault appends to every substitution.
        """
        vault = DataVault({"rho_AHE": _make_dp(1.0e-6, r"\ohm\cdot m")})

        def _llm(system: str, user: str) -> str:
            return "AHE resistivity {{dp:rho_AHE}} was measured."

        def _critic(section_name: str, draft_tex: str) -> str:
            return "Clarify the measurement conditions more explicitly."

        result = run_loop_c(
            goal="Draft AHE paper",
            results_context="AHE measured in GdFeCo.",
            vault=vault,
            bib_manager=BibManager(),
            llm_fn=_llm,
            critic_fn=_critic,
            output_dir=tmp_path,
            compile_tex=False,
        )

        # At least one section draft must exist
        assert result.section_drafts, "Expected at least one accepted section draft"

        # The provenance comment must be present, confirming vault injection ran
        for draft_result in result.section_drafts.values():
            assert "[prov:" in draft_result.tex, (
                "Finding 1 regression: vault provenance comment '[prov:' missing from "
                "critic-revised draft — vault.inject_into_draft was not called after revision."
            )


# ---------------------------------------------------------------------------
# R5-F3 regression: critic-revised sections must carry the AI disclosure footer
# ---------------------------------------------------------------------------


class TestLoopCCriticRevisionAIDisclosure:
    """R5-F3: critic-revised section drafts must carry the per-section _AI_DISCLOSURE.

    The initial-draft path in section_drafter.py appends _AI_DISCLOSURE to every
    LLM output.  When the domain critic triggers a revision in loop_c.py, the
    revised text must also carry the disclosure so that individual section .tex
    files comply with §16.5 (every AI-drafted output carries the disclosure).
    """

    def test_critic_revised_draft_carries_ai_disclosure(self, tmp_path) -> None:
        """After critic revision, each accepted section draft must contain _AI_DISCLOSURE.

        The disclosure sentinel string is the comment block appended by
        section_drafter._AI_DISCLOSURE: '% --- AI usage disclosure (§16.5) ---'.
        """
        # Extract a unique fragment from the disclosure that cannot appear by chance
        # in a normal LLM draft.
        disclosure_sentinel = "AI usage disclosure"

        vault = DataVault()

        def _llm(system: str, user: str) -> str:
            return "Draft text describing the experimental methods."

        def _critic(section_name: str, draft_tex: str) -> str:
            # Always return substantive feedback to trigger a revision on every section
            return "Please expand the methodology description with more detail (>10 chars)."

        result = run_loop_c(
            goal="Draft R5-F3 regression test manuscript",
            results_context="Spin Hall angle measured in W/Pt bilayers.",
            vault=vault,
            bib_manager=BibManager(),
            llm_fn=_llm,
            critic_fn=_critic,
            output_dir=tmp_path,
            compile_tex=False,
        )

        assert result.section_drafts, "Expected at least one accepted section draft"

        for section_name, draft_result in result.section_drafts.items():
            assert disclosure_sentinel in draft_result.tex, (
                f"R5-F3 regression: critic-revised section '{section_name}' is missing "
                f"the AI disclosure footer. The _AI_DISCLOSURE comment block must be "
                f"appended to every draft, including critic revisions (§16.5).\n"
                f"Draft tex (first 300 chars): {draft_result.tex[:300]!r}"
            )

    def test_critic_revised_draft_has_human_review_marker_and_disclosure(
        self, tmp_path
    ) -> None:
        """Critic-revised drafts must have both HUMAN_REVIEW_MARKER and _AI_DISCLOSURE.

        Verifies that both bookend markers are present in the same draft, consistent
        with the initial-draft format produced by section_drafter.draft_section.
        """
        vault = DataVault()

        def _llm(system: str, user: str) -> str:
            return "Methods: spin transport was measured."

        def _critic(section_name: str, draft_tex: str) -> str:
            return "Clarify the measurement protocol used (>10 chars of feedback)."

        result = run_loop_c(
            goal="Draft disclosure regression test",
            results_context="Large spin Hall angle in W/Pt.",
            vault=vault,
            bib_manager=BibManager(),
            llm_fn=_llm,
            critic_fn=_critic,
            output_dir=tmp_path,
            compile_tex=False,
        )

        assert result.section_drafts, "Expected at least one accepted section draft"

        for section_name, draft_result in result.section_drafts.items():
            tex = draft_result.tex
            assert "HUMAN REVIEW REQUIRED" in tex, (
                f"R5-F3: HUMAN_REVIEW_MARKER missing in critic-revised '{section_name}'"
            )
            assert "AI usage disclosure" in tex, (
                f"R5-F3: _AI_DISCLOSURE missing in critic-revised '{section_name}'"
            )
