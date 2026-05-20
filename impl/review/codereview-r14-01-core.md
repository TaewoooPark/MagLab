# Code Review — Round 14, Core Domain

**Reviewer:** automated adversarial audit
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`
**Date:** 2026-05-20
**Basis:** Independent fresh re-audit. R13 found CLEAN. This round investigates angles not examined in prior rounds: `run_loop_b` double `step()` calls per failure iteration, `detached_loop` `reset_no_progress` timing vs `record_output` accumulation, `APIBackend._call_litellm` `last_exc` and `finally` env-restore correctness, `ContextEngine.compact` token accounting, `HookRegistry.set_plan_mode` hook reordering security, `ResearchPool.semantic_query` empty-query behavior and `zip(strict=True)` invariant, `ProvenanceStore._flush_to_db` entity duplication semantics, `RalphState.from_markdown` field-order-dependent parsing, `BudgetTracker.max_usd=0` gate semantics, `SkillLoader.discover` error dict key collision, `check_vault_references` UUID case-folding, `check_untagged_numbers` 400-char window boundary, `check_promises` session-level tool_log accumulation, `Orchestrator.run` context growth and resource leak on unguarded exception, `Verifier` contract in `_process_node`, D1/D2 engine mutations and fallback logic, and `_BADGE_MAP` THEORY badge inconsistency (re-confirmed).

---

## Verdict

**CLEAN** — zero genuine defects found.

---

## R13 Fix Verification

R13 found CLEAN (zero findings). R11 fix (F1 — `run_gate` called with `raise_on_violation=False` in `reporting.py`) remains intact at `reporting.py:237–250`. No regression from any prior fix.

---

## Findings

None.

---

## Non-Findings

Items investigated in depth and dismissed this round.

### core/ralph.py — `run_loop_b` double `step()` calls per failure iteration

When `code_improver_fn` raises, `engine.step()` is called twice in a single `while` loop iteration: once for the test failure (error_key from pytest output) and once for the code_improver exception. This causes `engine.state.iteration` to advance by 2 per while-loop cycle. This is correct design — both the test failure and the code_improver failure are independent circuit-breaker events that should each count toward `error_limit`. The REPEATED_ERROR breaker fires after 5 same-key calls (from either source). No defect.

### core/ralph.py — `detached_loop` `reset_no_progress()` timing vs `record_output` accumulation

`reset_no_progress()` is called BEFORE `self.step()` in the `score_fn is None` branch. Inside `step()`, `record_output(output, 0.5)` is called. If `last_score == 0.5`, `delta = 0.0 < threshold`, incrementing `no_progress_count` from 0 to 1. On the next iteration, `reset_no_progress()` brings it back to 0, then `record_output` raises it to 1 again. Count never accumulates to 3. OUTPUT_SIMILARITY still fires on repeated identical output. Correct.

### core/ralph.py — `run_loop_b`/`run_loop_d`/`run_loop_e` final return operator precedence

The expression `engine.state.stop_reason or StopReason.MAX_ITERATIONS.value if engine.state else StopReason.EXTERNAL.value` parses as `(engine.state.stop_reason or StopReason.MAX_ITERATIONS.value) if engine.state else StopReason.EXTERNAL.value` because Python's ternary has lower precedence than `or`. Since `engine.start()` always sets `engine.state`, and all break paths call `_stop()` which sets `stop_reason`, the `or MAX_ITERATIONS.value` fallback is dead code but harmless. Confirmed via Python interpreter.

### core/ralph.py — `run_loop_b` tempfile cleanup on early return

A `return` inside a `with tempfile.TemporaryDirectory()` block triggers `__exit__`, ensuring cleanup. All early returns from within the `with` block are safe. Correct.

### core/ralph.py — `RalphEngine.step()` MAX_ITERATIONS off-by-one

`step()` increments `iteration` THEN checks `>= max_iterations`. With `max_iterations=10`, iteration reaches 10 at step 10. DONE_SIGNAL is checked first (higher priority than MAX_ITERATIONS). Both `detached_loop`'s while-condition guard and `step()`'s MAX_ITERATIONS check are belt-and-suspenders. Correct.

### core/ralph.py — `RalphState.from_markdown` field-order-dependent parsing

`_extract()` uses `re.search` (not `re.match`), which could match a field value that contains `**key**: value` patterns. However, fields are written in a fixed order in `to_markdown()`, and `re.search` returns the FIRST match. The mode field appears before the goal field in the markdown, so a goal value containing `**mode**: x` would NOT override the real mode match (which appears first). Fragile but not defective given the deterministic write order. Not a defect.

### llm/backends/api.py — `_call_litellm` `last_exc` and `finally` env-restore

`last_exc` is always set when the retry loop runs (at least one attempt via `max(1, max_retries)`). The `finally` block restores env vars from `old_env` which is populated before the try block — so even on `ImportError` from `import litellm`, env restore is correct. The `or RuntimeError(...)` fallback at line 161 is dead code. Correct.

### llm/backends/api.py — sleep on last retry attempt

`time.sleep(delay)` executes before the final attempt AND before re-raising the exception. Unnecessary latency on failure, not a correctness defect. Carried forward as acknowledged (R11).

### core/context.py — `ContextEngine.compact` token accounting

After compaction, `working.token_count` is reset to summary tokens. `_system_tokens` is unchanged. If the system prompt itself is >85% of the context window, compaction would trigger immediately after the next message — but system prompts are far smaller than 170,000 tokens in practice. Not a defect.

### core/context.py — `WorkingContext.compact` preserve-key retention

`compact()` copies all `provenance_ids`, `job_ids`, and `param_names` from the old context into the new one AND appends any missing ones to the summary text as annotations. Keys are preserved across compaction. Correct.

### core/hooks.py — `HookRegistry.set_plan_mode` hook reordering

`set_plan_mode(active)` unregisters `plan_mode_hook` and re-registers it at the END of the chain (after `irreversibility_hook`). In `autonomous` mode, `irreversibility_hook` allows T2 tools, but `plan_mode_hook` (now last) still runs and blocks them. The `is_allowed` logic returns the LAST hook result. Since hooks stop on first BLOCK, any earlier BLOCK is also caught. The reordering does not create a security gap. Correct.

### core/memory.py — `ResearchPool.semantic_query` empty-query behavior

When the query contains only tokens not in the IDF table, `q_vec = {}` and `_cosine({}, ...)` returns 0.0 for all records. With default `min_score=0.0`, the filter `rs[1] > 0.0` drops all records (0.0 is not > 0.0), returning `[]`. This is semantically correct — no matching evidence. The `zip(strict=True)` invariant holds because `len(vectors) == len(docs) == len(records)` always. Correct.

### core/memory.py — `ResearchPool.semantic_query` `zip(strict=True)` invariant

`_tfidf_vectors(docs)` returns a list of vectors of the same length as `docs`. `docs` is built from `records` in a list comprehension with 1:1 mapping. `strict=True` never raises. Correct.

### provenance/store.py — `_flush_to_db` entity duplication in PROV document

Calling `add_entity()` twice with the same `local_id` results in two entity calls to the prov library and an `INSERT OR REPLACE` in `prov_records` (deduplicating the row). The PROV document may contain duplicate entity stubs, but `list_entities()` and `get_entity_lineage()` both query `prov_records` where the ID is the primary key. No observable duplication in query results. Not a defect.

### core/budget.py — `BudgetTracker.max_usd=0` gate semantics

`is_over_budget()` returns `max_usd > 0 and total_usd >= max_usd`. When `max_usd=0`: gate is disabled (unlimited spending). `_check_budget()` uses `ratio = total_usd / max_usd if max_usd > 0 else 0.0` — consistent, no zero-division. Correct.

### core/skills.py — `SkillLoader.discover` error dict key collision

`self._errors` uses `skill_dir.name` (directory name) as key. If two skills in different search paths share the same directory name AND both fail to load, the second error overwrites the first. Minor observability loss, not a correctness defect.

### report/honesty_gate.py — `check_vault_references` UUID case-folding

`{v.lower() for v in vault_ids}` is rebuilt on every call to `check_vault_references` for each found UUID in text. R13 noted this as a performance concern. The case-insensitive comparison itself is correct: UUIDs from `_DP_ID_RE.findall()` are compared lowercased against lowercased vault IDs. Correct.

### report/honesty_gate.py — `check_untagged_numbers` 400-char window boundary

Context window: `text[max(0, m.start()-200) : min(len(text), m.end()+200)]`. A UUID at exactly `m.start()-200` IS in the window (Python slice is inclusive of start). A UUID at exactly `m.end()+200` is NOT in the window (Python slice end is exclusive). Boundary behavior is correct.

### report/honesty_gate.py — `check_promises` session-level `tool_log` accumulation

`self._tool_log` in `Orchestrator` accumulates all tool calls across turns. `check_promises` computes `write_tools` from the full session log. A later turn claiming "I executed X" is not flagged if ANY write-tier tool ran earlier in the session. This is an acknowledged design choice (session-level attestation, not per-turn). Not a defect.

### core/orchestrator.py — `Orchestrator.run` context growth without compaction

`_process_node` adds user/assistant message pairs to `self._context`. Compaction is only checked in `respond()`, not in `run()`. With `max_nodes=20`, total context growth is bounded. Performance concern only; no correctness impact.

### core/orchestrator.py — `Orchestrator.run` resource leak on unguarded `_process_node` exception

If `_process_node` raises, SQLite connections (budget, checkpoint, session_memory) remain open until `Orchestrator.close()` is called. The `__enter__`/`__exit__` context manager correctly closes them. The REPL's `finally` block calls `close()`. The `run()` method does not need an internal try/finally because it is the caller's responsibility to manage the context manager. Not a defect.

### core/reasoning.py — D2 `AnomalyExplainer._fallback_candidates` always returns 2 items

`min_candidates` defaults to 2. When `len(raw_candidates) < min_candidates`, the fallback appends 2 candidates. If `raw_candidates` has 1 item, the fallback adds 2, making 3 total — more than `min_candidates`. The cap `raw_candidates[: max(self._min_candidates, 5)]` in the conversion step handles overshoot. No off-by-one defect.

### core/reasoning.py — D1 `rank_by_elo` in-place mutation of candidates

`elo_rating` is mutated in-place on `HypothesisCandidate` objects. Callers holding references to the original `candidates` list observe updated Elo ratings — this is intentional. `HypothesisResult` holds `RankedHypothesis` objects that wrap the same mutated candidates. No hidden state corruption.

### ui/render.py — `THEORY` badge maps to `[LIT]` while `datapoint.py` maps `THEORY` to `PRED`

`_BADGE_MAP["THEORY"] → ("[LIT]", "bright_black")` while `BADGE_LABEL[ProvenanceType.THEORY] = "PRED"`. This inconsistency exists in a display-only utility path (`badge_text`). `DataPoint.badge` uses `BADGE_LABEL` and is the canonical badge. R13 established this as a display policy choice. Confirmed still present; still not a correctness defect in any computational or integrity path.

### mcp_client.py — all R13 non-findings

`disable_server()` asyncio path, `get_registry()` singleton docstring accuracy, `get_entity_lineage` LIKE pattern with non-UUID local_id, and `disable_server` in-memory mutation before `_save()` — all confirmed CLEAN with no regression.

### core/checkpoint.py — `CheckpointStore.save` SELECT-then-UPDATE/INSERT

Upsert pattern is correct for single-process use (no TOCTOU in single-threaded context). Confirmed no regression.

### llm/auth.py — double `_ensure_auth_json_secure()` and explicit `chmod`

Belt-and-suspenders pattern. Confirmed no regression.

### core/orchestrator.py — all R13 non-findings

`_tool_loop` `stage_model` kwarg forwarding, `ResearchTree.best_pending()` O(n) scan, `_apply_honesty_gate` exception isolation, `_notify_gateway` fire-and-forget — all confirmed CLEAN.

### core/ralph.py — all R13 non-findings

`_parse_pytest_failures` state machine, `engine.step("<promise>DONE</promise>")` return value, `_HYPOTHESIS_SEEDS` immutability, `verify_loop` max-iterations+1 call pattern — all confirmed CLEAN.

---

## Verification

**ruff check** on all domain files: `All checks passed!`

**mypy** on full package: `Success: no issues found in 195 source files`

**pytest** (core unit tests + integrity suite):
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
tests/unit/test_provenance_store.py
tests/integrity/
→ 561 passed in 2.86s
```
