"""Loop C — authoring Ralph loop (§16.5, §6.3-C).

Drafting order: Methods → Results → Discussion → Conclusion →
    Intro → Abstract → Title.

Each iteration:
    1. Draft section (``SectionDrafter``).
    2. Domain-aware critic (sub-agent or LLM call) reviews physics/logic.
    3. Revise based on critic feedback.
    4. Compile with ``tectonic``.
    5. PDF readback (vision model or heuristic).
    6. Pre-section gate (citation + data vault) must pass.

Maximum 6 iterations (§16.5).  Each section requires human sign-off (Tier 2
gate).  Circuit breaker and budget gate from ``RalphEngine`` are inherited.

Uses the ``RalphEngine`` API — does NOT modify ``core/ralph.py``.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.authoring.bib_manager import BibManager
from maglab.authoring.citation_auditor import (
    PreSectionFinalizeHook,
    SemanticFinding,
    VerifiedCitePool,
)
from maglab.authoring.data_vault import AuthoringBlockedError, DataVault
from maglab.authoring.section_drafter import (
    DRAFTING_ORDER,
    HUMAN_REVIEW_MARKER,
    CompileResult,
    DraftResult,
    SectionDrafter,
    compile_draft,
    readback_pdf,
)
from maglab.authoring.templates import JournalTemplate
from maglab.core.ralph import (
    RalphEngine,
    RalphMode,
    StopReason,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Loop C result
# ---------------------------------------------------------------------------

_AI_DISCLOSURE_FOOTER = (
    "\n\n"
    "%%% AI USAGE DISCLOSURE (§16.5) %%%\n"
    "%%% This manuscript was drafted with MagLab AI writing assistance.\n"
    "%%% HUMAN REVIEW REQUIRED — the named authors bear full responsibility\n"
    "%%% for all content, data, and citations.\n"
    "%%% Per COPE guidelines, AI tools are not listed as authors.\n"
    "%%% END DISCLOSURE %%%\n"
)


@dataclass
class LoopCResult:
    """Result of the Loop C authoring Ralph loop.

    Attributes
    ----------
    success:
        True if the loop completed without a circuit-breaker stop.
    iterations:
        Total number of Ralph iterations run.
    stop_reason:
        Why the loop stopped.
    section_drafts:
        Final accepted draft for each section (in drafting order).
    compile_result:
        Final ``tectonic`` compilation result (if compilation was attempted).
    compile_log:
        Accumulated compilation log text.
    human_review_required:
        Always ``True`` — hard-coded research integrity requirement.
    """

    success: bool
    iterations: int
    stop_reason: str
    section_drafts: dict[str, DraftResult] = field(default_factory=dict)
    compile_result: CompileResult | None = None
    compile_log: str = ""
    human_review_required: bool = True


# ---------------------------------------------------------------------------
# Loop C orchestrator
# ---------------------------------------------------------------------------


def run_loop_c(
    *,
    goal: str,
    results_context: str,
    vault: DataVault,
    bib_manager: BibManager,
    llm_fn: Callable[[str, str], str],
    critic_fn: Callable[[str, str], str] | None = None,
    verified_cite_pool: VerifiedCitePool | None = None,
    semantic_classify_fn: Callable[[str, str, str], SemanticFinding] | None = None,
    full_text_pool: dict[str, str] | None = None,
    journal_template: JournalTemplate | None = None,
    output_dir: Path | None = None,
    human_gate_fn: Callable[[str, DraftResult], bool] | None = None,
    max_iterations: int = 6,
    budget_tracker: Any = None,
    state_path: Path | None = None,
    compile_tex: bool = False,
) -> LoopCResult:
    """Run Loop C — the authoring Ralph loop (§16.5).

    Parameters
    ----------
    goal:
        Loop goal string (used by ``RalphEngine``).
    results_context:
        Researcher-provided results summary passed to every section drafter.
    vault:
        ``DataVault`` with locked ``DataPoint`` values.
    bib_manager:
        Verified ``BibManager``.
    llm_fn:
        LLM callable: ``(system_prompt, user_prompt) → str``.
    critic_fn:
        Domain-aware critic: ``(section_name, draft_tex) → feedback_str``.
        ``None`` skips the critic step.
    verified_cite_pool:
        Pre-flight citation pool (§16.4).
    semantic_classify_fn:
        Semantic citation classifier (mocked in tests).
    full_text_pool:
        Mapping cite-key → paper text for semantic verification.
    journal_template:
        ``JournalTemplate`` supplying style constraints (word limits, etc.).
    output_dir:
        Directory to write final ``.tex`` files.  If ``None``, a temp dir
        is used.
    human_gate_fn:
        Human sign-off callable: ``(section_name, draft_result) → bool``.
        ``True`` means approved, ``False`` means rejected (loop aborts).
        ``None`` auto-approves (non-interactive mode).
    max_iterations:
        Maximum Ralph loop iterations (§16.5 cap = 6).
    budget_tracker:
        ``BudgetTracker`` for cost gating.
    state_path:
        Ralph state file path.
    compile_tex:
        If ``True``, run ``tectonic`` compilation at the end of each iteration.

    Returns
    -------
    ``LoopCResult``.
    """
    max_iterations = min(max_iterations, 6)  # §16.5 hard cap

    engine = RalphEngine(
        mode=RalphMode.IN_SESSION,
        max_iterations=max_iterations,
        goal=goal,
        loop_type="C",
        budget_tracker=budget_tracker,
        state_path=state_path or Path(".maglab") / "ralph_loop_c.md",
    )
    engine.start()

    abstract_limit = journal_template.abstract_word_limit if journal_template else None
    drafter = SectionDrafter(
        vault=vault,
        bib_manager=bib_manager,
        llm_fn=llm_fn,
        abstract_word_limit=abstract_limit,
    )
    gate = PreSectionFinalizeHook(
        bib_manager=bib_manager,
        vault=vault,
        full_text_pool=full_text_pool,
        semantic_classify_fn=semantic_classify_fn,
    )

    # Manage output directory
    _tmp_dir = None
    if output_dir is None:
        _tmp_dir = tempfile.mkdtemp(prefix="maglab_loop_c_")
        effective_dir = Path(_tmp_dir)
    else:
        effective_dir = output_dir
        effective_dir.mkdir(parents=True, exist_ok=True)

    section_drafts: dict[str, DraftResult] = {}
    last_compile: CompileResult | None = None
    compile_log = ""

    try:
        for section_type in DRAFTING_ORDER:
            if not engine.is_active():
                break

            section_name = section_type.value
            draft_result: DraftResult | None = None
            approved = False

            # Inner iteration for a single section (up to remaining budget)
            while engine.is_active() and not approved:
                # Step 1: Draft
                try:
                    draft_result = drafter.draft_section(
                        section_type,
                        context=results_context,
                        verified_cite_pool=verified_cite_pool,
                    )
                except AuthoringBlockedError as exc:
                    err_key = f"AuthoringBlockedError:{section_name}"
                    reason = engine.step("", score=0.0, error_key=err_key)
                    log.warning("[Loop C] Authoring blocked on %s: %s", section_name, exc)
                    if reason is not None:
                        break
                    continue

                # Step 2: Domain critic
                if critic_fn is not None:
                    feedback = critic_fn(section_name, draft_result.tex)
                    # Revise if critic provided substantive feedback
                    if feedback and len(feedback.strip()) > 10:
                        revision_prompt = (
                            f"Critic feedback for {section_name}:\n{feedback}\n\n"
                            f"Revise the following draft:\n{draft_result.tex}"
                        )
                        revised_tex = llm_fn(
                            "Revise the section per critic feedback.", revision_prompt
                        )
                        draft_result.tex = HUMAN_REVIEW_MARKER + revised_tex

                # Step 3: Pre-section gate
                try:
                    gate.run(draft_result.tex, section=section_name)
                except AuthoringBlockedError as exc:
                    err_key = f"GateBlocked:{section_name}"
                    reason = engine.step("", score=0.0, error_key=err_key)
                    log.warning("[Loop C] Gate blocked %s: %s", section_name, exc)
                    if reason is not None:
                        break
                    continue

                # Step 4: Compile (optional)
                if compile_tex:
                    _write_section_tex(effective_dir, section_name, draft_result.tex)
                    assembled = _assemble_full_document(
                        effective_dir, section_drafts, draft_result, journal_template
                    )
                    main_tex = effective_dir / "main.tex"
                    main_tex.write_text(assembled, encoding="utf-8")
                    last_compile = compile_draft(effective_dir)
                    compile_log += last_compile.log + "\n"

                    if not last_compile.success:
                        err_key = "TectonicFailure"
                        reason = engine.step(
                            last_compile.log[:200],
                            score=0.0,
                            error_key=err_key,
                        )
                        if reason is not None:
                            break
                        continue

                    # Step 5: PDF readback
                    if last_compile.pdf_path:
                        feedback_pdf = readback_pdf(last_compile.pdf_path)
                        if not feedback_pdf.layout_ok:
                            score = 0.5
                            issues_summary = "; ".join(feedback_pdf.issues[:3])
                            reason = engine.step(issues_summary, score=score)
                            if reason is not None:
                                break
                            continue

                # Step 6: Human gate (Tier 2 sign-off, §5.15)
                if human_gate_fn is not None:
                    approved = human_gate_fn(section_name, draft_result)
                else:
                    approved = True  # auto-approve in non-interactive mode

                if approved:
                    section_drafts[section_name] = draft_result
                    reason = engine.step(f"Section {section_name} approved.", score=0.7)
                    if reason is not None:
                        break
                else:
                    # Human gate rejected the section — abort the loop (§5.15).
                    # The human reviewer holds final authority; a rejection is
                    # an external stop request, not a retry signal.  Without
                    # this branch the inner ``while`` never advances the engine
                    # and spins forever.
                    log.warning(
                        "[Loop C] Human gate rejected %s — aborting loop.", section_name
                    )
                    engine.step(f"Section {section_name} rejected by human gate.", score=0.0)
                    engine.stop(StopReason.EXTERNAL)
                    break

        # Final: write AI disclosure and HUMAN REVIEW REQUIRED file
        _write_output_files(effective_dir, section_drafts, journal_template)

    finally:
        if _tmp_dir:
            # Keep temp dir if output_dir was None — user can find artifacts
            pass  # intentionally not cleaned up so caller can inspect

    state = engine.state
    success = (
        state is not None and (state.stop_reason in (None, StopReason.DONE_SIGNAL.value))
    ) or len(section_drafts) == len(DRAFTING_ORDER)

    if engine.is_active():
        engine.stop(StopReason.DONE_SIGNAL)

    return LoopCResult(
        success=success,
        iterations=state.iteration if state else 0,
        stop_reason=state.stop_reason or StopReason.DONE_SIGNAL.value if state else "",
        section_drafts=section_drafts,
        compile_result=last_compile,
        compile_log=compile_log,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_section_tex(directory: Path, section_name: str, tex: str) -> None:
    """Write a section's LaTeX content to a dedicated file."""
    path = directory / f"{section_name}.tex"
    path.write_text(tex, encoding="utf-8")


def _assemble_full_document(
    directory: Path,
    completed_sections: dict[str, DraftResult],
    current_draft: DraftResult,
    template: JournalTemplate | None,
) -> str:
    """Assemble a minimal compilable LaTeX document from section drafts."""
    preamble = template.preamble if template else _MINIMAL_PREAMBLE
    body_parts: list[str] = []

    for section_type in DRAFTING_ORDER:
        name = section_type.value
        if name in completed_sections:
            body_parts.append(f"% --- {name.upper()} ---\n{completed_sections[name].tex}\n")
        elif name == current_draft.section.value:
            body_parts.append(f"% --- {name.upper()} ---\n{current_draft.tex}\n")

    body = "\n".join(body_parts)
    return (
        preamble + "\n\\begin{document}\n\n" + body + _AI_DISCLOSURE_FOOTER + "\n\\end{document}\n"
    )


def _write_output_files(
    directory: Path,
    section_drafts: dict[str, DraftResult],
    template: JournalTemplate | None,
) -> None:
    """Write final output files and the HUMAN_REVIEW_REQUIRED marker."""
    # Write HUMAN_REVIEW_REQUIRED.txt
    review_marker = directory / "HUMAN_REVIEW_REQUIRED.txt"
    review_marker.write_text(
        "HUMAN REVIEW REQUIRED\n\n"
        "This manuscript was drafted with MagLab AI writing assistance.\n"
        "The named authors bear full responsibility for all content, "
        "data, and citations.\n\n"
        "DO NOT SUBMIT without human review and approval.\n"
        "Per COPE guidelines, AI tools are not listed as authors.\n",
        encoding="utf-8",
    )

    # Write assembled main.tex if not already done
    main_tex = directory / "main.tex"
    if not main_tex.is_file() and section_drafts:
        # Create a minimal assembled draft
        dummy_result = next(iter(section_drafts.values()))
        assembled = _assemble_full_document(directory, section_drafts, dummy_result, template)
        main_tex.write_text(assembled, encoding="utf-8")


_MINIMAL_PREAMBLE = (
    "\\documentclass{article}\n"
    "\\usepackage{graphicx}\n"
    "\\usepackage{amsmath}\n"
    "\\usepackage{siunitx}\n"
)
