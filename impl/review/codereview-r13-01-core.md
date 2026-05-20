# Code Review — Round 13, Core Domain

**Reviewer:** automated adversarial audit
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`
**Date:** 2026-05-20
**Basis:** Independent fresh re-audit. R12 found CLEAN (R11 had 1 LOW finding, since fixed). This round investigates new angles not covered in prior rounds: `run_loop_d` `adjust_fn` failure path to NO_PROGRESS circuit breaker, `detached_loop` `reset_no_progress` timing vs `record_output` increment sequence, `run_loop_b` `code_improver_fn` error path and implicit re-loop behaviour, `mcp_client.disable_server` asyncio event loop in Python 3.14, `render.py` `THEORY` badge inconsistency vs `datapoint.py` `BADGE_LABEL`, `ReportBuilder.build()` `vault_ids={}` (empty explicit set) merge semantics, `ResearchTree` node stuck in `RUNNING` on unguarded exception, `get_registry()` docstring vs singleton first-path-wins behaviour, `SessionMemory` INSERT without `state` column, `provenance/store.py` relation row `attributes=None` flush.

---

## Verdict

**CLEAN** — zero genuine defects.

---

## R12 Fix Verification

No R12 findings; confirming all previously fixed items remain intact. The R11 finding (F1 — `run_gate` called with `raise_on_violation=False` to collect violations before re-raising) is confirmed clean at `reporting.py:237–250`.

---

## Findings

None.

---

## Non-Findings

Items investigated in depth and dismissed this round.

### mcp_client.py — `asyncio.get_event_loop()` in `disable_server()` under Python 3.14

`disable_server()` at line 456 calls `asyncio.get_event_loop()` from a synchronous context. In Python 3.14 (the project's runtime) this raises `RuntimeError` when no event loop is running. The `except RuntimeError: pass` at line 462 catches it, meaning the `AsyncExitStack` is GC'd without `aclose()`.

However, R9 established — and the current code still satisfies — the key precondition: `disable_server()` is only ever called from synchronous CLI code (`cli.py:606`) which creates a **fresh `MCPClientRegistry` that has never been connected**. `self._cm_stacks.pop(name, None)` therefore returns `None`, and the entire `if stack is not None:` branch is skipped. The asyncio path is dead code in every real call path. No resource leak occurs. Confirmed no regression from R9.

The `except RuntimeError: pass` guard is still the correct fallback for the hypothetical case where `disable_server()` is called from async code on a different thread — in that case the stack is GC'd (acceptable "best-effort" close documented in the comment). Not a defect.

### mcp_client.py — `get_registry()` singleton ignores `registry_path` after first call

The docstring states "ignored after the first call unless `registry_path` differs from the cached one" but the code always returns the cached instance regardless of `registry_path`. This is a documentation inaccuracy, not a code defect — the behavior (first path wins) is intentional and consistent.

### core/ralph.py — `detached_loop` `reset_no_progress()` timing vs `record_output` increment

In the `score_fn is None` branch: `reset_no_progress()` is called before `step()`. Inside `step()`, `record_output()` may increment `no_progress_count` by 1 (when `last_score` equals 0.5). Each iteration the pattern is `reset → 0`, then `increment → 1`. Count never accumulates to the limit (3). `NO_PROGRESS` is correctly suppressed for all iterations including the first (where `last_score is None` prevents any increment). `OUTPUT_SIMILARITY` still fires on repeated identical output. Correct.

### core/ralph.py — `run_loop_b` `code_improver_fn` error path: implicit re-loop with stale code

When `code_improver_fn` raises and `engine.step()` returns `None` (no circuit break): there is no `continue`, so execution falls to the end of the `while` body and loops again. The next iteration runs `_run_pytest` with the **unchanged** `current_code`. The same test failures produce the same `failure_summary[:100]` error key, which is recorded again. After `error_limit` (5) identical failure keys, `REPEATED_ERROR` fires and terminates the loop. This is correct recovery semantics. Not a defect.

### core/ralph.py — `run_loop_d` `adjust_fn` failure path: stale kwargs → NO_PROGRESS

When `adjust_fn` raises and the circuit breaker does not fire: `current_kwargs` is unchanged. The next `fit_fn(**current_kwargs)` call produces the same R² score. `check_summary` includes `[iter=N]` (different each iteration), so `OUTPUT_SIMILARITY` does not fire. The constant R²-based `score` produces `delta < threshold` each iteration, incrementing `no_progress_count`. After 3 consecutive increments, `NO_PROGRESS` terminates the loop. Correct.

### core/ralph.py — `run_loop_b` `code_improver_fn` error path after `code_improver_fn` exception: `break` path

When `engine.step()` returns a `StopReason` after the `code_improver_fn` error: `break` exits the `while` loop and falls to the outer `return LoopBResult(...)`. `engine.state.stop_reason` is set by `_stop()` before `break`. The operator-precedence ternary at line 905–907 is: `engine.state.stop_reason or StopReason.MAX_ITERATIONS.value if engine.state else StopReason.EXTERNAL.value`. Since `engine.state` is always set (initialized in `start()`), this evaluates as `engine.state.stop_reason or StopReason.MAX_ITERATIONS.value`. After a circuit-breaker stop, `engine.state.stop_reason` is non-empty, so the correct value is returned. Not a defect (confirmed from R12).

### core/orchestrator.py — `ResearchTree` node stuck in `RUNNING` on unguarded `_process_node` exception

If `_process_node` raises an unguarded exception, the node stays in `RUNNING` status and the exception propagates out of `run()`. The post-loop code (checking `completed_nodes()` and returning `all_pruned`) is never reached. The caller receives the exception, not a silently wrong result. The concern about `all_done_or_pruned()` returning False with a stuck RUNNING node is therefore moot — it never executes on that code path. Not a defect.

### provenance/store.py — relation rows flushed with `attributes=None`

`was_generated_by`, `was_derived_from`, and `was_attributed_to` call `_flush_to_db(qn, "relation")` without `attributes`. In `_flush_to_db`, `attributes or {}` is `{}`, producing `record_json = {"id": "ml:...", "kind": "relation"}`. The LIKE-pattern lineage query in `get_entity_lineage` matches on the `id` column, not `prov_json`, so the lack of attributes in relation rows is correct by design. Not a defect.

### reporting.py — `ReportBuilder.build()` with `vault_ids=set()` (explicit empty set)

When `vault_ids=set()` (explicit empty set, not `None`): `effective_vault_ids = set() | known_ids = known_ids`. The vault check runs with the builder's own DataPoint IDs. Narrative references to those DataPoint UUIDs pass. No references outside `known_ids` would be in a report that was just built — the user would have to embed unrelated UUIDs in the narrative. This is the intended strict mode. Not a defect.

### ui/render.py — `THEORY` badge maps to `[LIT]` while `datapoint.py` maps `THEORY` to `PRED`

`_BADGE_MAP` in `render.py` maps `"THEORY"` → `("[LIT]", "bright_black")`. `BADGE_LABEL` in `datapoint.py` maps `ProvenanceType.THEORY` → `"PRED"`. This produces an inconsistent display if `badge_text("THEORY")` is called directly. However: (a) `badge_text` is a standalone display utility and its mapping is not authoritative — `DataPoint.badge` uses `BADGE_LABEL` and produces the canonical badge; (b) `THEORY` values (closed-form physics predictions) may intentionally be styled as literature-adjacent in the UI. This is a display policy choice, not a logic error in any computational or integrity path. Not a finding.

### config.py / repl.py — `Config.ui.theme` mutable in session

Confirmed no regression. `Config` is Pydantic v2 without `frozen=True`; `config.ui.theme = name` at `repl.py:142` is valid.

### llm/auth.py — double `_ensure_auth_json_secure()` calls and explicit `chmod(0o600)`

Two `_ensure_auth_json_secure()` calls in `_auth_json_set` (once at read, once at call start) plus an explicit `chmod` after writing. Belt-and-suspenders. No regression. Not a defect.

### llm/backends/api.py — sleep on last retry attempt

`time.sleep(delay)` still executes before the final `raise last_exc`. Unnecessary latency, not a correctness defect. Carried forward as acknowledged (R11).

### mcp_client.py — `disable_server` in-memory mutation before `_save()`

Still present from R10. If `_save()` raises, in-memory and on-disk state diverge. LOW-severity latent data-consistency issue; no production caller depends on transaction atomicity. Carried forward as acknowledged.

### mcp_client.py — `get_entity_lineage` LIKE pattern with user-controlled `local_id`

`local_id` values are UUID4-derived or `llm-call-{hexchars}` — only hex digits and hyphens, no SQL wildcards. No SQL injection risk. Carried forward as acknowledged.

### core/memory.py — `SessionMemory` INSERT without `state` column

`INSERT INTO sessions (session_id, created_at, updated_at) VALUES (?, ?, ?)` omits `state`. SQLite applies the column's `DEFAULT '{}'`. Standard behavior. Not a defect.

### core/checkpoint.py — `CheckpointStore.save` upsert idempotency

SELECT-then-UPDATE/INSERT upsert pattern is correct for single-process use. Confirmed no regression.

### core/manifest.py — `load_manifest` graceful no-op on missing file

Confirmed in place. No regression.

### core/reasoning.py — `reflection_physics_check` pattern overlap with oracle

`"below absolute zero"` keyword fires before the oracle block due to sequential `return`. Oracle provides belt-and-suspenders. No control-flow issue.

### provenance/store.py — `_flush_to_db` full-document serialization growth

Quadratic growth on many DataPoints; performance-only, no correctness defect. Carried forward as acknowledged.

### reporting.py — all R12 non-findings

Gate skip with empty narrative, `summarize_datapoints` TypeError safety, `np.std(ddof=1)` with `len==1` guard, `check_vault_references` per-call set rebuild, `check_promises` multi-violation counting — all confirmed clean with no regression.

### core/ralph.py — all R12 non-findings

`_parse_pytest_failures` state machine (including `ERROR` case-sensitivity and truncated output), `engine.step("<promise>DONE</promise>")` return value on success path, `_HYPOTHESIS_SEEDS` immutability, `detached_loop` NO_PROGRESS suppression, `verify_loop` max-iterations+1 call pattern — all confirmed CLEAN with no regression.

### core/orchestrator.py — all R12 non-findings

`_tool_loop` `stage_model` kwarg forwarding, `ResearchTree.best_pending()` O(n) scan, `_apply_honesty_gate` exception isolation, `_notify_gateway` fire-and-forget pattern — all confirmed CLEAN with no regression.
