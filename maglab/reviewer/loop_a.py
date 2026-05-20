"""Loop A — review→patch→re-review Ralph loop (§15.5).

Implements Loop A using the RalphEngine API.
★ Uses (not modifies) the RalphEngine from core/ralph.py.

Loop A sequence:
  ① Panel instantiation
  ② Round 1 parallel review
  ③ Meta-review
  ④ Patch generation (citation grounding)
  ⑤ Human gate (Tier 3 — per-diff human approval)
  ⑥ Round 2 delta review
  ⑦ Terminate on score threshold or max rounds

Circuit breaker: halts on max_rounds exceeded, score convergence, or human-gate rejection.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.core.ralph import (
    RalphEngine,
    RalphMode,
    StopReason,
    save_state,
)
from maglab.reviewer.meta_reviewer import MetaReview, MetaReviewer
from maglab.reviewer.panel import PanelReview, PersonaSpec, ReviewPanel
from maglab.reviewer.rubrics import get_rubric

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Patch data structure
# ---------------------------------------------------------------------------


@dataclass
class ManuscriptPatch:
    """Manuscript patch proposal.

    Attributes
    ----------
    round_:
        Round number when the patch was generated.
    diff_text:
        Patch content (diff format or natural-language description).
    grounding_dois:
        DOI list grounding the patch (prevents fabricated citations).
    approved:
        Human-gate approval status (None = undecided).
    """

    round_: int
    diff_text: str
    grounding_dois: list[str] = field(default_factory=list)
    approved: bool | None = None


# ---------------------------------------------------------------------------
# Loop A result
# ---------------------------------------------------------------------------


@dataclass
class LoopAResult:
    """Loop A execution result.

    Attributes
    ----------
    success:
        True if the score threshold was reached.
    rounds_completed:
        Number of completed rounds.
    stop_reason:
        Reason for termination.
    round_reviews:
        PanelReview list per round.
    round_meta_reviews:
        MetaReview list per round.
    patches:
        List of generated patches.
    final_score:
        Overall mean score from the last round.
    """

    success: bool
    rounds_completed: int
    stop_reason: str
    round_reviews: list[PanelReview] = field(default_factory=list)
    round_meta_reviews: list[MetaReview] = field(default_factory=list)
    patches: list[ManuscriptPatch] = field(default_factory=list)
    final_score: float = 0.0


# ---------------------------------------------------------------------------
# Loop A execution
# ---------------------------------------------------------------------------


def run_loop_a(
    *,
    manuscript: str,
    personas: list[PersonaSpec],
    journal: str = "general",
    patch_generator_fn: Callable[[str, MetaReview], ManuscriptPatch] | None = None,
    human_gate_fn: Callable[[ManuscriptPatch], bool] | None = None,
    score_threshold: float = 7.5,
    max_rounds: int = 3,
    llm_review_fn: Any | None = None,
    budget_tracker: Any | None = None,
    state_path: Path | None = None,
) -> LoopAResult:
    """Loop A — review→patch→re-review Ralph loop.

    Parameters
    ----------
    manuscript:
        Initial manuscript text.
    personas:
        Panel persona specification list (typically 3).
    journal:
        Target journal identifier for evaluation.
    patch_generator_fn:
        Patch generation function: (manuscript, meta_review) -> ManuscriptPatch.
        None generates a dummy patch (test mode).
    human_gate_fn:
        Human-gate function: (patch) -> bool (True = approved).
        None auto-approves (test mode).
    score_threshold:
        Termination score threshold (success if overall mean reaches this value).
    max_rounds:
        Maximum number of review rounds.
    llm_review_fn:
        LLM review generation function (passed to ReviewPanel).
    budget_tracker:
        BudgetTracker instance.
    state_path:
        Ralph state file path.

    Returns
    -------
    LoopAResult
    """
    from maglab.reviewer.corpus_rag import CorpusRAG

    engine = RalphEngine(
        mode=RalphMode.IN_SESSION,
        max_iterations=max_rounds,
        goal=f"review→patch→re-review Loop A ({journal})",
        loop_type="A",
        budget_tracker=budget_tracker,
        state_path=state_path or Path(".maglab") / "ralph_loop_a.md",
    )
    engine.start()

    meta_reviewer = MetaReviewer()
    get_rubric(journal)  # Validate journal rubric (actual use is inside panel.review)

    # Empty RAG index (actual corpus is built from personas.verified_dois)
    rag = CorpusRAG()

    current_manuscript = manuscript
    round_reviews: list[PanelReview] = []
    round_meta_reviews: list[MetaReview] = []
    patches: list[ManuscriptPatch] = []
    final_score = 0.0
    stop_reason_str = StopReason.MAX_ITERATIONS.value

    while engine.is_active():
        current_round = engine.state.iteration + 1 if engine.state else 1
        log.info("[Loop A] Round %d starting", current_round)

        # ② Round parallel review
        try:
            panel = ReviewPanel(
                personas=personas,
                corpus_rag=rag,
                journal=journal,
                llm_review_fn=llm_review_fn,
            )
            panel_review = panel.review(current_manuscript)
        except Exception as exc:  # noqa: BLE001
            log.warning("[Loop A] Panel review error: %s", exc)
            reason = engine.step("", score=0.0, error_key=type(exc).__name__)
            if reason:
                stop_reason_str = reason.value
                break
            continue

        round_reviews.append(panel_review)

        # ③ Meta-review
        meta_review = meta_reviewer.synthesize(panel_review)
        round_meta_reviews.append(meta_review)

        # Compute overall mean score
        scores = list(meta_review.panel_mean_scores.values())
        final_score = sum(scores) / len(scores) if scores else 0.0

        log.info(
            "[Loop A] Round %d meta-review complete: mean_score=%.2f, dissents=%d",
            current_round,
            final_score,
            len(meta_review.dissents),
        )

        # Termination condition: score threshold reached
        if final_score >= score_threshold:
            log.info("[Loop A] Score threshold %.2f reached — successful exit", score_threshold)
            engine.step("<promise>DONE</promise>", score=1.0)
            stop_reason_str = StopReason.DONE_SIGNAL.value
            return LoopAResult(
                success=True,
                rounds_completed=current_round,
                stop_reason=stop_reason_str,
                round_reviews=round_reviews,
                round_meta_reviews=round_meta_reviews,
                patches=patches,
                final_score=final_score,
            )

        # If last round, terminate without patching
        if not engine.is_active():
            break

        # ④ Patch generation
        if patch_generator_fn is not None:
            try:
                patch = patch_generator_fn(current_manuscript, meta_review)
            except Exception as exc:  # noqa: BLE001
                log.warning("[Loop A] Patch generation error: %s", exc)
                patch = _dummy_patch(current_round, meta_review)
        else:
            patch = _dummy_patch(current_round, meta_review)

        # ⑤ Human gate (Tier 3 — per-diff human approval)
        approved = True
        if human_gate_fn is not None:
            try:
                approved = human_gate_fn(patch)
            except Exception as exc:  # noqa: BLE001
                log.warning("[Loop A] Human gate error: %s", exc)
                approved = False

        patch.approved = approved
        patches.append(patch)

        if not approved:
            log.info("[Loop A] Human gate rejected — loop halted")
            engine.stop(StopReason.EXTERNAL)
            stop_reason_str = StopReason.EXTERNAL.value
            return LoopAResult(
                success=False,
                rounds_completed=current_round,
                stop_reason="human_gate_rejected",
                round_reviews=round_reviews,
                round_meta_reviews=round_meta_reviews,
                patches=patches,
                final_score=final_score,
            )

        # Update manuscript (on human approval)
        current_manuscript = _apply_patch(current_manuscript, patch)

        # Circuit breaker check
        reason = engine.step(meta_review.overall_recommendation, score=final_score / 10.0)

        # Checkpoint: persist round state to disk so progress survives a process restart.
        if state_path is not None and engine.state is not None:
            save_state(engine.state, state_path)
            log.debug(
                "[Loop A] Checkpoint saved after round %d (state_path=%s)",
                current_round,
                state_path,
            )

        if reason is not None:
            stop_reason_str = reason.value
            log.info("[Loop A] Circuit breaker: %s", reason)
            break

    return LoopAResult(
        success=False,
        rounds_completed=engine.state.iteration if engine.state else 0,
        stop_reason=stop_reason_str,
        round_reviews=round_reviews,
        round_meta_reviews=round_meta_reviews,
        patches=patches,
        final_score=final_score,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dummy_patch(round_: int, meta_review: MetaReview) -> ManuscriptPatch:
    """Generate a dummy patch for testing."""
    consensus_notes = "; ".join(
        f"{c.dimension.value}: {c.common_rationale[:40]}" for c in meta_review.consensus[:2]
    )
    return ManuscriptPatch(
        round_=round_,
        diff_text=f"Round {round_} patch proposal:\n{consensus_notes or 'No revisions'}",
        grounding_dois=[],
    )


def _apply_patch(manuscript: str, patch: ManuscriptPatch) -> str:
    """Apply a patch to the manuscript (actual diff application is implemented in P6 authoring)."""
    return manuscript + f"\n\n<!-- Patch Round {patch.round_}: {patch.diff_text[:100]} -->"
