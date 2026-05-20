# Code Review — Round 15, Core Domain

**Reviewer:** automated adversarial audit
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`
**Date:** 2026-05-20
**Basis:** Independent fresh re-audit. R14 found CLEAN. This round investigates fresh angles not covered in prior rounds: `run_gate()` call-sequence interactions between step 1 and step 6 when `is_figure=True`, `CircuitBreakerState.record_output` interaction between `last_score=None` sentinel and the no-progress counter on first-call scores, `run_loop_b/d/e` while-loop exit semantics under simultaneous max_iterations and error_key signals, `_parse_critic_response` PASSED detection regex edge cases with trailing punctuation and partial matches, `ResearchPool.semantic_query` TF-IDF single-document and zero-token-overlap edge cases, `BudgetTracker._check_budget` LLM-only call vs. tool/sim step coupling, `Verifier.verify_loop` generator call-count semantics at `max_iterations=0`, `HookRegistry` hook-exception propagation path, and `ReportBuilder.build` gate text scope (narrative-only vs. entry lines).

---

## Verdict

**FIXED** — one genuine defect found and fixed.

---

## Findings & Fixes

### F1 — `run_gate(is_figure=True)` produces duplicate `UNTAGGED_NUMBER` violations

**Severity:** Medium  
**File:Line:** `maglab/report/honesty_gate.py:494`

**Defect:** When `run_gate()` is called with `is_figure=True`, step 1 runs
`check_untagged_numbers(text, known_dp_ids)` unconditionally, then step 6 runs
`check_figure_data_tags(text, known_dp_ids)` which internally calls
`check_untagged_numbers(figure_text, known_dp_ids)` on the **same text**.
Every bare number in a text that contains a figure-context keyword
(e.g. "Figure", "Fig.") is flagged twice, doubling the `UNTAGGED_NUMBER`
violation count in the returned `GateResult.violations` list.

Concrete example before the fix:
```
run_gate("Figure 1 shows the value 3.14.", is_figure=True, raise_on_violation=False)
→ 4 violations  (UNTAGGED_NUMBER for '1' + UNTAGGED_NUMBER for '3.14' × 2)
```

Expected correct behavior:
```
→ 2 violations  (UNTAGGED_NUMBER for '1' + UNTAGGED_NUMBER for '3.14' × 1)
```

**Impact:** Callers that check `len(result.violations)` for exact counts (e.g.
downstream honesty-gate display logic and any test that compares a specific count)
see inflated numbers. `result.passed` is correctly False either way, so the
boolean gate decision is unaffected — but the violation list is corrupted with
semantically identical duplicates, violating the contract that `GateResult.violations`
is a deduplicated list of distinct findings.

**Root cause:** The design intent is that `is_figure=True` enables the
*figure-specific* tagging check (step 6) as an *alternative* code path for figure
body text. However the implementation kept step 1 active alongside step 6, causing
the identical check to run twice on the same input.

**Fix applied:** Guard step 1 with `if not is_figure:`. When `is_figure=True`, step 6
(`check_figure_data_tags`) entirely supersedes step 1: it calls
`check_untagged_numbers` on the same text if a figure-context keyword is present, and
returns `[]` otherwise — preserving the existing behaviour for texts without figure
context. For `is_figure=False` (the common path) nothing changes.

```python
# Before (maglab/report/honesty_gate.py ~line 494)
violations.extend(check_untagged_numbers(text, known_dp_ids))  # always

# After
if not is_figure:
    violations.extend(check_untagged_numbers(text, known_dp_ids))
# Step 6 (check_figure_data_tags) already calls check_untagged_numbers when
# is_figure=True, so no duplication occurs.
```

**Regression test added:**
`tests/integrity/test_honesty_gate.py` — class `TestFigureDuplicateViolationRegression`

Four test cases:
1. `test_no_duplicate_violations_with_is_figure_true` — asserts that the violation
   count from `run_gate(is_figure=True)` equals the count from `run_gate(is_figure=False)`
   on the same text. This is the primary regression guard: it would fail with the
   pre-fix code (4 vs 2 violations).
2. `test_figure_gate_detects_untagged_numbers` — asserts that figure-mode still
   detects bare numbers (step 6 must still run).
3. `test_figure_gate_no_figure_context_still_clean` — asserts that `is_figure=True`
   on text without a figure-context keyword produces zero untagged-number violations
   (step 6 returns `[]`; step 1 is skipped; net result: 0, same as before).
4. `test_is_figure_false_checks_numbers_in_all_text` — asserts that `is_figure=False`
   still flags bare numbers in any text (general path unchanged).

---

## Non-Findings

Items investigated in depth and dismissed this round.

### report/honesty_gate.py — `run_gate()` step 1 vs step 6 for non-figure text

When `is_figure=False`, only step 1 runs (step 6 is gated by `if is_figure`). No
duplication. The fix only affects the `is_figure=True` branch. Verified: `is_figure`
defaults to `False` in all calling sites found in `reporting.py` (which passes
`is_figure=False` implicitly). The `ReportBuilder.build()` path is unaffected.

### core/ralph.py — `CircuitBreakerState.record_output` last_score=None sentinel

When `score=0.0` is passed on the very first call, `last_score is None` so the
no-progress check is bypassed and `no_progress_count` is not incremented. On the
second call, `delta = abs(score_new - 0.0)`. If `score_new = 0.0`, delta = 0.0 <
threshold, incrementing the count to 1 (not triggering yet at limit=3). Correct.

### core/ralph.py — `run_loop_b/d/e` while-loop exit under simultaneous MAX_ITERATIONS + error

When `step()` is called from the `code_improver_fn`/`adjust_fn`/`apply_fixes_fn` error
handler and MAX_ITERATIONS fires inside `step()`, `_stop()` sets `_state.active=False`
and returns `StopReason.MAX_ITERATIONS`. The outer `if reason: break` branch executes,
exiting the while loop cleanly. The final `return LoopXResult(stop_reason=engine.state.stop_reason …)` correctly reflects the MAX_ITERATIONS reason. No off-by-one or orphaned state.

### core/ralph.py — `_parse_critic_response` PASSED detection edge cases

Tested: `"PASSED."`, `"ALL CHECKS PASSED."`, `"NOT PASSED"`, `"NOT PASSED."`,
`"PASSED AND FAILED"`, `"ITEMS NOT PASSED"`. The `\bPASSED\b` word-boundary pattern
handles trailing punctuation (`.`) correctly because `.` is a non-word character,
creating a word boundary between `D` and `.`. All cases behave as expected.

### core/memory.py — `ResearchPool.semantic_query` edge cases

Single-document pool: `idf[tok] = log(2/2)+1 = 1.0`, TF-IDF vectors are non-zero,
cosine similarity correctly positive for a matching query. Zero-token overlap (all-empty
docs or query not in idf): `q_vec = {}`, `_cosine({}, …) = 0.0`, filter `> min_score`
drops all records → `[]`. Both edges correct.

### core/budget.py — `BudgetTracker._check_budget` coupling to LLM steps only

`_check_budget()` is invoked only inside `record_llm()`, not in `record_tool()` or
`record_sim()`. Tool and sim steps have `usd_cost=0.0` so they don't affect the gate.
`is_over_budget()` sums all steps' `usd_cost` via `_session_steps` — same result.
Consistent and intentional. Not a defect.

### core/verify.py — `Verifier.verify_loop` generator call count at `max_iterations=0`

With `max_iterations=0`, `range(0)` is empty and the generator is never called.
The post-loop final verify runs on the original result. This is semantically correct
for "no re-generation allowed". With `max_iterations=1`, the generator is called once
(iteration 0), then the final verify runs on that result. Total: max_iterations+1 verifies,
max_iterations generator calls. Confirmed consistent with R14.

### core/hooks.py — `HookRegistry.run()` hook exception propagation

If a hook raises, the exception propagates through `is_allowed()` into `_tool_loop()`.
The backend call try/except in `_tool_loop()` does NOT cover `is_allowed()`. In practice
the oracle hook's lazy import of `maglab.physics.oracle` will always succeed (part of the
installed package). This is a defensive-hardening opportunity only — not a correctness
defect in the expected execution environment.

### report/reporting.py — `ReportBuilder.build()` gate scope (narrative only)

`combined_text = self._narrative`. The entry lines from `to_line()` are not included in
the gate check. This is intentional: `ReportEntry` lines always carry provenance
(DataPoint wrapper), so bare-number checks on them would be false positives. Only the
free-form narrative text needs checking. Correct design.

### core/orchestrator.py — tool loop context accumulation

Tool-call exchanges within `_tool_loop()` are local to that invocation (in `msg_objects`).
Only the final text response is persisted to `self._context`. Intermediate tool results
are not kept across turns. Confirmed consistent with R14 non-finding. Not a defect.

---

## Verification

**ruff check** on all domain files:
```
All checks passed!
```

**mypy** on full package:
```
Success: no issues found in 195 source files
```

**pytest** (core unit tests + integrity suite, including 4 new regression tests):
```
tests/unit/test_core_ralph.py
tests/unit/test_core_orchestrator.py
tests/unit/test_core_memory.py
tests/unit/test_core_checkpoint.py
tests/unit/test_core_context.py
tests/unit/test_core_hooks.py
tests/unit/test_core_autonomy.py
tests/unit/test_ralph_loops.py
tests/unit/test_reasoning_d1.py
tests/unit/test_reasoning_d2.py
tests/unit/test_core_subagents.py
tests/unit/test_core_verify.py
tests/integrity/test_citation_audit.py
tests/integrity/test_honesty_gate.py  ← 85 tests (4 new regression tests added)
tests/integrity/test_persona_disclosure.py
tests/integrity/test_scpi_safety.py
→ 506 passed in 3.08s
```
