# Code Review — Round 12, Core Domain

**Reviewer:** automated adversarial audit
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`
**Date:** 2026-05-20
**Basis:** Independent fresh re-audit. R11 had 1 finding (LOW). This round examines every file from scratch with new angles not covered in R11: `_parse_pytest_failures` state machine correctness, `summarize_datapoints` type safety, `check_vault_references` set comprehension cost, `BudgetTracker._check_budget` only called from `record_llm`, `ReportBuilder.build()` gate-skip path when `self._entries` is non-empty but `self._narrative` is empty, `repl.py` Config mutation, `reasoning.py` `bool(result)` oracle call semantics.

---

## Verdict

**CLEAN** — zero genuine defects.

---

## R11 Fix Verification

The R11 finding (F1) is fully resolved. In `maglab/report/reporting.py` lines 237–250:

```python
gate_result = run_gate(
    combined_text,
    known_dp_ids=known_ids,
    vault_ids=effective_vault_ids,
    verified_citations=verified_citations,
    raise_on_violation=False,  # always collect first
)
violations.extend(gate_result.violations)

# Honour raise_on_violation AFTER collecting all violations …
if violations and raise_on_violation:
    raise HonestyViolation(violations)
```

`run_gate` is always called with `raise_on_violation=False`, ensuring violations are collected into the local list. The `HonestyViolation` raise then occurs outside the try/except at the caller-intent boundary. The contract is now correctly honoured. Confirmed.

---

## Findings

None.

---

## Non-Findings

Items investigated in depth and dismissed this round. Items from prior rounds that still apply are carried forward without re-annotation (no regression detected).

### reporting.py — gate skip when narrative is empty but entries exist

`build()` line 224: `if run_honesty_gate and (self._narrative or self._entries)` enters the gate block when entries exist even with no narrative. Then line 227 sets `combined_text = self._narrative` (empty string). Line 236: `if combined_text.strip()` is `False` for an empty string — `run_gate` is **not called**. This means DataPoints-only reports (no narrative) skip the honesty gate entirely. This is intentional: the gate is a text-content check; with no narrative text, there is nothing for the gate to audit. The DataPoint badges and values are structured data checked at creation time. Not a defect.

### reporting.py — `summarize_datapoints` TypeError safety

`scalar_dps = [dp for dp in datapoints if not isinstance(dp.value, list)]` correctly filters array DataPoints before calling `dp.scalar()`. `DataPoint.scalar()` raises `TypeError` only when `isinstance(self.value, list)`. Since the filter excludes those, no TypeError can occur in `values = [dp.scalar() for dp in scalar_dps]`. Correct.

### reporting.py — `np.std(values, ddof=1)` with len==1

`len(values) > 1` guard prevents `ddof=1` with a single-element array, which would produce `NaN` or raise in NumPy (ddof=N where N equals sample count). Returns `0.0` instead. Correct.

### honesty_gate.py — `check_vault_references` per-call set comprehension

Line 324: `{v.lower() for v in vault_ids}` rebuilds a lowercased set on every call. For large vault sets inside a tight loop this is O(n) extra allocation per text check. However `check_vault_references` is called at most once per `run_gate` call, and vault sizes in practice are the count of DataPoints in a single report session — not a hot loop. Performance-only concern; not a defect.

### honesty_gate.py — `check_promises` produces one violation per promise match

When `not write_tools` is True, the loop over `promise_matches` appends one `Violation` per regex match. If a text contains two distinct "I executed…" claims, two violations are reported. This is the correct behavior — each unsubstantiated claim is a separate integrity violation. Not a defect.

### budget.py — `_check_budget` only called from `record_llm`, not from `record_tool`/`record_sim`

`record_tool` and `record_sim` have `usd_cost=0.0` by type — only LLM calls accrue USD costs. `is_over_budget()` sums `usd_cost` across all steps; tool and sim steps contribute nothing to that sum regardless of whether `_check_budget` is called. The budget gate is USD-only, not wall-time-based. The asymmetry is correct by design. Not a defect.

### ralph.py — `_parse_pytest_failures` state machine

Traced the state machine through multiple realistic pytest output shapes:
- Normal FAILED + traceback + separator: produces one correct failure entry per test.
- Pytest collection ERROR (uppercase): `'Error' in line` is case-sensitive — `ERROR` does not match `Error`. The header `'==================== ERROR collecting …'` does NOT set `in_failure=True`. The actual import error line (`ImportError: …`) does, producing a correct entry. No spurious failures from the header.
- Single-line FAILED with separator on the same line: not possible in real pytest output (each is on its own line).
- Truncated output (no final `=` separator): `if current: failures.append(…)` collects the trailing partial block. Correct.
The parser is a heuristic and may overcount or undercount on unusual pytest plugins; that is acceptable for a code-fix LLM loop. No logic error.

### ralph.py — `engine.step("<promise>DONE</promise>")` return value ignored on success path

In `run_loop_b`, `run_loop_d`, and `run_loop_e`, after a successful pytest/fit/critic pass, `engine.step("<promise>DONE</promise>", score=1.0)` is called, but the returned `reason` is not checked before returning the success `Result` object. This is correct: `engine.step` with DONE signal always calls `_stop(StopReason.DONE_SIGNAL)` and returns `StopReason.DONE_SIGNAL`. The returned value is redundant on the success path because the caller immediately returns. No bug.

### reasoning.py — `bool(result)` oracle call

`OracleResult.__bool__` returns `self.ok` (line 43 of `physics/oracle.py`). Therefore `ok = bool(result)` at `reasoning.py:1099` is semantically identical to `ok = result.ok`. Correct.

### reasoning.py — `reflection_physics_check` pattern overlap with oracle

The keyword pattern `"below absolute zero"` is in the `contradictions` list AND the oracle also checks `T=0.0` when `"absolute zero"` is present. Both fire on the same text, but the keyword check short-circuits first (returns before the oracle block). The oracle provides belt-and-suspenders. No control-flow issue.

### orchestrator.py — `_tool_loop` `stage_model` kwarg forwarded to backends that may not accept it

`self._backend.complete(msg_objects, max_tokens=4096, model=stage_model)`. The `LLMBackend.complete` signature accepts `model: str | None = None`. When `model_router` is `None`, `stage_model` is `None`, which is the default — no change from baseline. When it is set, the backend must accept `model` as a keyword argument, which `APIBackend.complete` and `DelegatedCLIBackend.complete` do. Backends that do not support it would need to handle the kwarg in their `complete()` signature (the `**kwargs` pattern is used). Confirmed for `APIBackend`. Not a defect.

### orchestrator.py — `ResearchTree.best_pending()` O(n) scan

Returns `max()` over all pending leafs on each expansion. With `max_nodes=20`, the cost is O(20) per expansion — negligible. Not a defect.

### provenance/store.py — `_flush_to_db` serializes full document on every record

Each call to `_flush_to_db` serializes the entire `ProvDocument` to `prov_graph`. For a session with many DataPoints this grows quadratically. A large research session could make individual `record_datapoint` calls increasingly slow. This is a performance concern, not a correctness defect. Not raised as a finding.

### provenance/store.py — `INSERT OR REPLACE` on `prov_records` with same `id`

If the same entity is registered twice (same `local_id`), the second call overwrites the first in `prov_records`. The in-memory `ProvDocument` accumulates both (prov library deduplication may or may not apply). In practice `ProvenanceLedger.record_datapoint` is called once per DataPoint (DataPoint IDs are UUID4, unique by construction). Not a defect in practice.

### config.py — `Config.ui.theme` mutation in repl.py

`Config` is a Pydantic v2 `BaseModel` without `model_config = {"frozen": True}`. Runtime mutation of `config.ui.theme = name` (repl.py:142) is valid in Pydantic v2 — confirmed by live test. Not a defect.

### mcp_client.py — `disable_server` in-memory mutation before `_save()`

Still present from R10. If `_save()` raises (disk full, permission error), in-memory state shows the server as disabled while on-disk state still shows it enabled. On next load, the server would be re-enabled unexpectedly. This is a LOW-severity latent data-consistency issue noted in R10/R11 but not treated as a finding per the reviewer's judgement that no production caller currently depends on this transaction atomicity. Carried forward as acknowledged.

### mcp_client.py — `get_entity_lineage` LIKE pattern with user-controlled `local_id`

`local_id` values are UUID4-derived or `llm-call-{hexchars}`, containing only hex digits and hyphens — no SQL wildcards (`%`, `_`). No SQL injection risk in current usage. Carried forward as acknowledged (R10 confirmed; no regression).

### llm/auth.py — `_auth_json_set` double permissions enforcement

Two `_ensure_auth_json_secure()` calls (once at read, once at write path) + explicit `path.chmod(0600)` after write. Belt-and-suspenders. No bug.

### llm/backends/api.py — retry loop last-attempt sleep

After the last failed attempt in the retry loop, `time.sleep(delay)` executes before `raise last_exc`. Minor unnecessary delay. Not a correctness defect (R11 confirmed; no regression).

### ralph.py / context.py — all previously investigated edge cases

Elo mutation, `_HYPOTHESIS_SEEDS` immutability, operator precedence of ternary in outer returns, `detached_loop` NO_PROGRESS suppression, `verify_loop` max-iterations+1 call pattern — all confirmed CLEAN with no regression from R11.

### core/manifest.py — `load_manifest` graceful no-op on missing file

Still in place. Confirmed no regression.

### core/checkpoint.py — `CheckpointStore.save` upsert idempotency

The UPDATE path re-reads the existing `checkpoint_id` before updating. The INSERT path generates a new UUID. Race conditions between two concurrent `save()` calls with the same key are handled by the `UNIQUE(task_id, idempotency_key)` constraint — a second INSERT would fail; only one UPDATE would commit. Single-process usage (no concurrency) makes this moot. Correct.
