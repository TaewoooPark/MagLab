# Code Review — Round 11, Core Domain

**Reviewer:** automated adversarial audit
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`
**Date:** 2026-05-20
**Basis:** Independent fresh re-audit. R9 and R10 were both CLEAN. Especially rigorous re-examination of all files with fresh angles not previously explored: `report/reporting.py` `raise_on_violation` contract, `llm/backends/api.py` retry loop semantics, `core/reasoning.py` Elo mutation, `core/ralph.py` loop exit paths, `core/orchestrator.py` tool-loop edge cases.

---

## Verdict

**ISSUES FOUND** — 1 genuine defect, severity LOW.

---

## Findings

### F1 — LOW | `maglab/report/reporting.py:237–247` | `raise_on_violation=True` silently suppressed in `ReportBuilder.build()`

**Defect:**
`ReportBuilder.build(raise_on_violation=True)` is documented to raise `HonestyViolation` on any integrity violation, but the implementation silently swallows the exception. The code at lines 237–247:

```python
try:
    gate_result = run_gate(
        combined_text,
        ...
        raise_on_violation=raise_on_violation,   # True forwarded to run_gate
    )
    violations.extend(gate_result.violations)
except HonestyViolation as exc:
    violations.extend(exc.violations)            # caught — not re-raised
```

When `raise_on_violation=True`, `run_gate` raises `HonestyViolation`. The `except` clause catches it and stores the violations in the local list, then `build()` proceeds to return a `Report` object rather than propagating the exception. The caller who passes `raise_on_violation=True` expecting a raised exception will instead silently receive a `Report` with `violations` populated — their pipeline will continue past what they intended as a hard stop.

**Impact:**
Any caller who calls `build(raise_on_violation=True)` (or `build_report(..., raise_on_violation=True)`) to enforce a hard stop on integrity failures will not get the hard stop. The exception is silently converted to `Report.violations`. No current production call site passes `True` (the default is `False` everywhere), so this defect is latent rather than actively triggered — but it is a genuine API contract violation that will mislead future callers.

**Fix:**
Re-raise the exception after collecting violations, or remove the try/except and let the exception propagate naturally:

Option A (re-raise with violations attached):
```python
try:
    gate_result = run_gate(
        combined_text,
        ...
        raise_on_violation=False,   # always collect first
    )
    violations.extend(gate_result.violations)
except HonestyViolation as exc:
    violations.extend(exc.violations)

if violations and raise_on_violation:
    raise HonestyViolation(violations)
```

Option B (let run_gate propagate directly — no try/except):
```python
gate_result = run_gate(
    combined_text,
    ...
    raise_on_violation=raise_on_violation,
)
violations.extend(gate_result.violations)
```

Option A is safer because it always collects violations into the local list before deciding whether to raise.

---

## Non-Findings

Items investigated in depth and dismissed (fresh angles marked ★).

### ralph.py

- **★ `run_loop_b` outer return (lines 901–908) reachable only via `break` (adjust-fn error path).** At that point `engine.step()` already called `_stop()`, so `engine.state.stop_reason` is always set. The `or StopReason.MAX_ITERATIONS.value` branch is defensive dead code. Correct.
- **★ `run_loop_b` success path: `stop_reason` hardcoded to `DONE_SIGNAL`.** `engine.step('<promise>DONE</promise>')` always returns `DONE_SIGNAL` (checked before `MAX_ITERATIONS`). The hardcoded value matches reality. Correct.
- **★ `run_loop_d` outer return (lines 1173–1177): same analysis as Loop B.** `_stop()` is always called before the outer return is reachable. `last_fit_result` defaults to `{}` on first-iteration failure; `{}.get('params', current_kwargs)` returns `current_kwargs`. Correct.
- **★ `run_loop_e` `vision_critic_fn=None` path.** Returns on the first iteration after a successful render. `engine.state.iteration = 1` at that point. Correct.
- **★ `run_loop_e` `apply_fixes_fn` error with `reason=None`.** Continues the while loop without break; next iteration starts fresh with `render_fn()`. Correct.
- **★ `run_loop_e` `render_fn` repeated error path.** After 5 identical `error_key` values, `REPEATED_ERROR` fires; the `if reason: return` guard fires before the next `render_fn` call. Correct.
- **★ `detached_loop` `reset_no_progress()` before `step()` correctly suppresses `NO_PROGRESS` accumulation.** Counter is reset at start of each iteration; the count can only reach 1 during any single `step()` call, and is reset the following iteration. `NO_PROGRESS` breaker is effectively disabled. Correct per design.
- **★ Elo `_update_elo` modifies `candidates[i].elo_rating` in-place via list-element references.** Intentional; the final sort uses updated ratings. No aliasing bug.
- **★ `_HYPOTHESIS_SEEDS` not mutated.** `matching_group = list(matching)` and `nonmatching_group` are local copies; `rng.shuffle()` is called on copies. Module-level constant is safe. Correct.
- **★ Operator precedence of `... if engine.state else ...` ternary in Loop B/D/E outer return.** Verified via `ast.parse()`: parses as `(engine.state.stop_reason or STOP_VALUE) if engine.state else EXTERNAL_VALUE`. Correct (R10 confirmed; no regression).

### orchestrator.py

- **★ `_tool_loop`: all tools blocked by hooks → `tool_results` has `is_error=True` entries (not empty).** LLM receives feedback and can adjust. Correct.
- **★ `_tool_loop`: `response.tool_calls == []` (empty list).** `if not response.tool_calls` is True → returns `response.content or ''`. Correct.
- **★ `_tool_loop`: `response.content is None` when only tool calls present.** `if response.content:` guard skips ASSISTANT message injection. Matches API contract. Correct (no regression from R10).

### context.py

- **★ `ContextEngine(context_window=0)` would cause `ZeroDivisionError`.** Not reachable: `ContextEngine()` is only instantiated in `orchestrator.py:331` with no argument (uses default 200,000). Correct.
- **★ `WorkingContext.compact()` post-compaction token count.** `new_ctx.token_count = max(1, len(full_summary) // 4)` is the summary-only count; `needs_compaction()` adds `_system_tokens` separately. No under/over-counting. Correct.

### budget.py / checkpoint.py / memory.py

- **★ `BudgetTracker._persist`: single `execute + commit` → atomic per SQLite semantics.** Not a multi-row transaction; atomicity guaranteed by SQLite. Correct.
- **★ `SessionMemory._ensure_session` INSERT without `state` column.** SQL `DEFAULT '{}'` fills it. Correct (R10 confirmed; no regression).
- **★ `ResearchPool.semantic_query` `strict=True` zip.** `records` and `vectors` built from same list comprehension → lengths always equal. No `ValueError`. Correct.

### hooks.py / autonomy.py / verify.py

- **★ `verify_loop` max-iterations+1 total `verify()` calls.** Final call after exhausting PARTIAL rounds gives a fresh verdict on the last result. Intentional. Correct.
- **★ `oracle_hook` in `default_registry` prepended.** Physics validation runs before tier/plan-mode gates. Correct.

### honesty_gate.py

- **★ `check_promises` session-level write-tier tool check (lenient).** One write-tier tool suppresses all promise-match violations for the session. Intentional design.
- **★ `_PROMISE_RE` does not match negation.** `'I have not completed'` → no match (tested). Correct.
- **★ `_parse_critic_response` `\bPASSED\b` not triggered by `UNPASSED`.** `P` in `UNPASSED` is preceded by `N` (word char), so `\b` does not fire. Correct (R10 confirmed; no regression).
- **★ `check_untagged_numbers` `'study-3.14'` → `'3.14'` matched.** The `-` after `y` (word char) blocks the negative-number path; `3.14` is matched starting from `3`. This is a known heuristic false positive. Not a defect.

### reporting.py

- **★ `raise_on_violation=True` not called anywhere in current codebase.** All production call sites use the default `False`. The defect (F1 above) is latent, not currently triggered.

### llm/backends/api.py

- **★ `_call_litellm` retry loop: `max_retries` is total-attempts, not retry-count.** `for attempt in range(max(1, max_retries))` gives `max_retries` total attempts. The log message `attempt %d/%d` with `(attempt+1, max_retries)` is consistent with this interpretation. The parameter name is misleading (should be `max_attempts`) but the behavior is deterministic, bounded, and internally consistent. Documentation mismatch only — not a runtime defect.
- **★ `_call_litellm` final `time.sleep` after the last failed attempt.** The sleep executes after the last `except (RateLimitError, ServiceUnavailableError)` block before the loop exits, causing a brief unnecessary delay before `raise last_exc`. Efficiency overhead only, not a correctness bug.
- **★ `_inject_api_key` env-var injection + `try/finally` cleanup.** Restores original env-var value even on exception. No env-var leakage. Correct (R10 confirmed; no regression).

### llm/auth.py

- **★ `_auth_json_set` double `_ensure_auth_json_secure()` call.** First call creates and enforces 0600; write then rewrites with new content and re-enforces 0600 via `path.chmod()`. Correct (R10 confirmed; no regression).

### mcp_client.py

- **★ `disable_server` in-memory mutation before `_save()`.** If `_save()` raises, on-disk state is stale. Confirmed still LOW severity; no rollback added. No change from R10.
- **★ `get_entity_lineage` LIKE pattern.** `local_id` values in current usage are UUID4-derived (hex + hyphens) or `llm-call-{hexchars}`. No SQL wildcards. Latent only. Not a defect. (R10 confirmed; no regression.)

### provenance/ledger.py / provenance/store.py

- **★ `ProvenanceLedger.record_datapoint` without `activity_description` or `derived_from_ids`.** Only `was_attributed_to` is called; `wasGeneratedBy` is skipped. W3C PROV allows entities without generation activities. Correct (R10 confirmed; no regression).
- **★ `ProvenanceStore._flush_to_db` transaction atomicity.** Both INSERT statements inside `with self._conn:` — either both commit or both roll back. Correct.

### config.py / repl.py

- **★ `repl.py` `Orchestrator.close()` in `finally` block.** `getattr(orchestrator, "close", None)` + callable check → safe even when orchestrator is None. Correct.
- **★ `Config.model_validate(data)` with empty `data`.** All Pydantic fields have defaults; empty dict → all defaults applied. No validation errors. Correct.

### reasoning.py

- **★ `reflection_physics_check` oracle call for absolute zero.** `_ABSOLUTE_ZERO_RE` catches `0 K` patterns before oracle; oracle is belt-and-suspenders. Logic is correct.
- **★ `D1HypothesisEngine.run()` passes same `rng_seed` to both `generate_candidates` and `rank_by_elo`.** Reproducible behavior within a single engine run. Intended.

### subagents.py / skills.py / manifest.py

- **★ `SubagentRunner._resolve_model('inherit')` → `None` → backend falls back to default model.** Correct.
- **★ `SkillLoader.discover()` re-entrant (second call overwrites cache).** SKILL.md files are static at runtime; re-parsing yields identical results. No bug.
- **★ `load_manifest()` graceful no-op on missing file.** Still in place. No regression.
