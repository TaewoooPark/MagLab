# Code Review — Round 7, Core Domain

**Reviewer:** automated adversarial audit
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`
**Date:** 2026-05-19
**Basis:** Independent fresh re-audit after R6 fix. Verified R6 fix then audited all domain files.

---

## Verdict

**ISSUES FOUND** — 1 genuine defect, MEDIUM severity: `ContextEngine.compact()` leaves a `role="system"` message inside `_working.messages`, so the next call to `get_messages_for_llm()` returns **two system-role messages** — the primary system prompt plus the compacted summary. This violates the Anthropic API contract (system role is forbidden in the `messages` array) and will cause an API error when a session exceeds 85 % of the context window.

---

## R6 Fix Verification

The R6 finding (LOW) was that `generate_candidates()` in `maglab/core/reasoning.py` shuffled the entire concatenated pool (`rng.shuffle(pool_shuffled)`), destroying the intended topic-matching priority.

**Status: FIXED and CONFIRMED.**

Live code at `maglab/core/reasoning.py:882–890`:

```python
# Matching seeds first (shuffled within group), then non-matching (shuffled within group).
# Shuffling each group separately preserves topic-priority while keeping intra-group
# randomness so the same topic doesn't always return identical candidate order.
matching_group = list(matching)
rng.shuffle(matching_group)
nonmatching_group = [s for s in _HYPOTHESIS_SEEDS if s not in matching]
rng.shuffle(nonmatching_group)
pool_shuffled = matching_group + nonmatching_group
raw_candidates.extend(pool_shuffled)
```

Each group is shuffled independently; concatenation preserves the invariant that topic-matched seeds precede non-matching seeds before the slice `raw_candidates[:n]`. The R6 fix is correctly in place.

---

## Findings

### FINDING 1 — MEDIUM: `ContextEngine.compact()` produces a double system-role message that violates the Anthropic API contract

**File:** `maglab/core/context.py:109–146` (WorkingContext.compact) and `maglab/core/context.py:257–263` (ContextEngine.get_messages_for_llm)

**Defect:**

`WorkingContext.compact()` replaces the conversation history with a single message whose role is hard-coded to `"system"`:

```python
new_ctx.messages = [{"role": "system", "content": full_summary}]
```

`ContextEngine.get_messages_for_llm()` always prepends a second system-role entry before returning:

```python
system_msg = {"role": "system", "content": self._system_prompt}
return [system_msg] + self._working.messages
```

After compaction the combined list is therefore:

```
[{"role": "system", "content": <full system prompt>},
 {"role": "system", "content": <compacted summary>},
 {"role": "user", ...}, ...]
```

**Impact:**

The Anthropic Messages API prohibits `role: "system"` inside the `messages` array. The system prompt must be passed as a separate top-level `system` parameter. LiteLLM's Anthropic adapter extracts the first system-role entry as the system parameter and passes the remainder of the array to the API as-is; a second system-role element in that remainder will cause the Anthropic API to return a `400 Bad Request` error.

This error is triggered whenever `ContextEngine.needs_compaction()` returns `True` (i.e., when `(system_tokens + working.token_count) / 200_000 >= 0.85`, approximately 170 K estimated tokens). The failing API call is the one immediately following compaction, inside `_tool_loop`. The exception is caught at `orchestrator.py:545` and returned as `"[Error] Backend call failed: ..."` — the REPL session silently degrades from that point onward.

With the Anthropic provider this is a hard failure on every call after compaction. With OpenAI the behaviour is provider-dependent (OpenAI currently accepts multiple system turns but does not guarantee it).

**Concrete fix:**

Option A — Change the compacted summary role from `"system"` to `"user"` so the compacted history becomes a user-turn context injection (the most straightforward fix):

```python
# In WorkingContext.compact():
new_ctx.messages = [{"role": "user", "content": f"[Context summary]\n{full_summary}"}]
```

Option B — Merge the compacted summary into the `ContextEngine._system_prompt` string directly instead of placing it in the working messages:

```python
# In ContextEngine.compact():
def compact(self, summary: str) -> None:
    new_working = self._working.compact(summary)
    # Merge the summary into the system prompt so working.messages stays empty
    merged_summary = new_working.messages[0]["content"] if new_working.messages else summary
    self._system_prompt = self._system_prompt + "\n\n## Session Summary (compacted)\n" + merged_summary
    new_working.messages = []
    self._working = new_working
    self._system_tokens = max(1, len(self._system_prompt) // 4)
```

Option A is preferred for minimal change; Option B is preferred for cleaner separation of concerns.

---

## Non-Findings

Items investigated and dismissed:

- **R6 fix: separate-shuffle in `generate_candidates`:** Confirmed in place at `reasoning.py:882–890`. No regression from R5/R6 patches.

- **`_stop()` return-type lie when `self._state is None`:** `_stop()` is annotated `-> RalphState` but returns `None` when `self._state is None` (suppressed with `type: ignore[return-value]`). All reachable callers (`step()`, `stop()` from `loop_a.py`, `loop_c.py`) are called after `start()` is confirmed, making `self._state` always non-None at those points. Not currently exploitable.

- **`run_loop_b` `reason` result from DONE-signal step is unchecked:** At line 863, `engine.step("<promise>DONE</promise>", score=1.0)` is called and the return value stored in `reason` but never read before the unconditional `return LoopBResult(...)` on line 864. The step is called solely to update engine state (mark iteration, set `completion_promise`, trigger `_stop`). Unconditional return is correct; no defect.

- **Double `engine.step()` calls per `run_loop_b` iteration:** When `code_improver_fn` fails (error path at line 895–899), a second `step()` is called in the same iteration. This is consistent with `max_iterations` counting `step()` invocations rather than loop passes. By design.

- **`ContextEngine.needs_compaction()` token estimate uses character/4 heuristic:** The estimate `max(1, len(content) // 4)` underestimates tokens for non-ASCII content and overestimates for code. This affects WHEN compaction fires, not the correctness of compaction itself. The threshold is conservative. Not a correctness defect.

- **`ProvenanceStore` docstring claim "If it already exists, the existing entity is returned":** The in-memory `_doc.entity()` call is not guarded for duplicates; the `_flush_to_db` upsert (`INSERT OR REPLACE`) correctly deduplicates in the DB. The prov library silently accepts duplicate entity registrations per W3C PROV semantics (entities are merged). No runtime error.

- **`check_promises` write-tool suppression applies globally:** One write-tier tool in the log suppresses ALL promise violations for the session. Accepted false-negative design tradeoff (R6 non-finding retained).

- **`APIBackend._inject_api_key` environment variable race:** Thread-safety hazard when two threads call `_call_litellm` simultaneously. Not exploitable — the entire codebase is single-threaded. R6 non-finding retained.

- **`ProvenanceStore.__init__` `check_same_thread=False` with non-thread-safe `ProvDocument`:** Latent defect for future multi-threaded use; not exploitable in current single-threaded architecture. R6 non-finding retained.

- **`_tool_loop` missing ASSISTANT message before TOOL messages:** When `response.content is None` and tool calls are present, no preceding ASSISTANT message is appended before TOOL messages. Currently unreachable because `backend.complete()` is never called with `tools=` argument, so `response.tool_calls` is always `[]`. R6 non-finding retained.

- **`LoopE` immediate PASSED when `vision_critic_fn is None`:** Deliberate design — without a critic, nothing to evaluate; returns after the first render. Correct.

- **`CircuitBreakerState.last_score` sentinel:** `None` on first call correctly prevents a spurious no-progress count when score=0.0 is returned on the first iteration. Confirmed still in place.

- **`_parse_critic_response` last-line PASSED detection:** Checks final non-empty line, requires `\bPASSED\b`, excludes `NOT PASSED` / `FAILED`. R5-era fix remains in place.

- **`ReportBuilder.build()` effective_vault_ids merge:** `(vault_ids | known_ids) if vault_ids is not None else None` at line 235 is confirmed still in place. R4 F1 fix intact.

- **`RalphEngine.detached_loop()` NO_PROGRESS suppression:** `reset_no_progress()` called before `step()` in the `score_fn is None` branch at line 621. R4 F2 fix intact.

- **`ProvenanceStore._flush_to_db` prov_json attributes:** `{"id": record_id, "kind": kind, **(attributes or {})}` correctly serialises per-record attributes. R5 fix verified still in place at line 342.

- **`BudgetTracker._check_budget` called only from `record_llm`:** `record_tool` and `record_sim` do not call `_check_budget`. The budget gate is only relevant to LLM spend; tool calls have no USD cost field populated and do not count toward the USD limit. By design.

- **`_ABSOLUTE_ZERO_RE` regex at `reasoning.py:42`:** R3 fix `(?<!\d)0\s*k(?!\w)` confirmed still in place.
