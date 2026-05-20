# Code Review — Round 1, Core Domain
**Reviewer:** automated adversarial audit  
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`  
**Date:** 2026-05-19

---

## Verdict

**ISSUES FOUND** — 6 genuine defects identified: 1 HIGH (verifiable-orchestrator invariant broken), 2 HIGH (functional incorrectness / data integrity), 2 MEDIUM (logic errors / silent failures), 1 LOW (resource leak).

---

## Findings

### FINDING 1 — HIGH: ProvenanceStore lineage query returns incorrect data for unrelated entities

**File:** `maglab/provenance/store.py:279-298` (`_flush_to_db`) and `238-245` (`get_entity_lineage`)

**Defect:**  
`_flush_to_db` stores the **entire serialized `ProvDocument`** (full graph snapshot) as `prov_json` in every row of `prov_records`. Because every row's `prov_json` grows to contain the complete document, the LIKE query in `get_entity_lineage`:

```python
cursor = self._conn.execute(
    "SELECT id, kind, prov_json, created_at FROM prov_records WHERE prov_json LIKE ?",
    (f"%{qn_str}%",),
)
```

matches **every row in the table** as soon as the entity appears anywhere in the document. Querying the lineage of entity `e3` (which has no relations to `e1` or `e2`) returns the `wdf-e2-e1` relation row because that row's `prov_json` also contains `e3` (the whole graph).

**Confirmed:** empirically verified — `get_entity_lineage('e3')` returns the unrelated `wasDerivedFrom(e2, e1)` relation record.

**Impact:** This is a core verifiable-orchestrator invariant violation. The provenance audit trail (`ProvenanceLedger.lineage(dp_id)`) returns provably incorrect lineage data. Any downstream trust-chain verification relying on it is silently corrupted.

**Fix:** Store only the serialized representation of the **individual record** in `prov_json`, not the full document. Use a per-record attribute dict. The full document snapshot (currently in `prov_graph`) should remain for export only. Alternatively, maintain a separate `relations` table and join on entity ID for lineage rather than a full-text LIKE scan.

---

### FINDING 2 — HIGH: `check_promises` never flags a mismatch when any tool was executed

**File:** `maglab/report/honesty_gate.py:381-396` (`check_promises`)

**Defect:**  
The promise-check gate is designed to catch agents that claim they "executed" or "saved" something when no such tool call was logged. The logic is:

```python
for m in promise_matches:
    if not executed_tools:           # <-- only checks if the set is empty
        violations.append(...)
```

This means: when **any** tool (even a read-only `memory.read`) is in the log with a success status, `executed_tools` is non-empty, and **all** promise violations are silently suppressed — even if the specific tool the agent claims to have run was never called.

**Confirmed:** an agent text claiming `"I have already executed the simulation and saved the results."` against a log containing only `[{'tool': 'memory.read', 'status': 'success'}]` returns **zero violations**.

**Impact:** The HonestyGate promise-check is effectively disabled whenever any tool has run in the session. This directly undermines the verifiable-orchestrator design (§5.15): agents can claim execution without it.

**Fix:** Instead of checking `if not executed_tools`, extract the claimed tool or action verb from the context window around the match and verify it against `executed_tools`. At minimum, only suppress violations when a high-tier (T2+) tool was actually executed:

```python
# minimal fix: require at least one write-tier tool
write_tools = {t for t in executed_tools if t not in {'memory.read', 'pool.query', 'read'}}
if not write_tools:
    violations.append(...)
```

---

### FINDING 3 — HIGH: `Orchestrator._tool_loop` discards `tool_call_id` from tool results

**File:** `maglab/core/orchestrator.py:593-597`

**Defect:**  
When tool call results are added back to the message list for the next LLM turn:

```python
for tr in tool_results:
    msg_objects.append(Message(role=Role.TOOL, content=tr["content"]))
```

The `tool_call_id` (`tr["tool_call_id"]`) is silently dropped. The `Message` model (in `llm/base.py`) has no field for `tool_call_id`. OpenAI/Anthropic APIs require tool result messages to carry the originating `tool_call_id` to match results to requests; without it, the API either raises an error or misroutes results when multiple tool calls are issued in a single response.

**Impact:** Multi-tool-call responses (more than one tool requested per LLM turn) will silently break the conversation. The API will receive unmatched tool results, and subsequent turns will be based on corrupted context.

**Fix:** Add a `tool_call_id: str | None = None` field to `Message`, populate it when appending tool results, and include it in `Message.to_dict()`. `APIBackend._parse_response` already reads `tc.id` for outbound tool calls.

---

### FINDING 4 — MEDIUM: `AnomalyExplainer` minimum-candidates fallback branch is logically dead

**File:** `maglab/core/reasoning.py:373-374`

**Defect:**
```python
if len(raw_candidates) < self._min_candidates and not raw_candidates:
    raw_candidates = self._fallback_candidates(query)
```

The compound condition `len(raw_candidates) < min_candidates AND not raw_candidates` reduces to just `not raw_candidates` (empty list). When the LLM returns 1 candidate (satisfying `len < 2` but not `not []`), the condition evaluates to `False` and `_fallback_candidates` is never called. The `min_candidates` guarantee is violated whenever the LLM returns a non-zero-but-too-short list.

**Confirmed:** `AnomalyExplainer(llm_explain_fn=returns_1, min_candidates=2).explain(...)` returns 1 candidate, not 2.

**Fix:**
```python
if len(raw_candidates) < self._min_candidates:
    raw_candidates = raw_candidates + self._fallback_candidates(query)
```

---

### FINDING 5 — MEDIUM: `CircuitBreakerState.record_output` prematurely increments no-progress on first iteration

**File:** `maglab/core/ralph.py:149-157`

**Defect:**  
`CircuitBreakerState.last_score` is initialized to `0.0` (dataclass default). On the first call to `record_output` with `score=0.0` (a valid starting score), `delta = abs(0.0 - 0.0) = 0.0 < no_progress_threshold (0.01)`, so `no_progress_count` is incremented to 1. This happens regardless of whether real progress occurred — the comparison is against the initialization value, not a previous iteration score.

**Impact:** A loop that starts with score=0.0 for its first three iterations will be killed by the circuit breaker (`no_progress_count >= 3`) even if the task meaningfully progressed from the baseline. `Loop D` is particularly exposed since it initializes with `score = max(0, min(1, r2))` which is 0.0 on the first fit attempt.

**Fix:** Use a sentinel `last_score = None` (change field type to `float | None`) and skip the no-progress check on the first call:

```python
last_score: float | None = None

def record_output(self, output: str, score: float) -> StopReason | None:
    ...
    if self.last_score is not None:
        delta = abs(score - self.last_score)
        if delta < self.no_progress_threshold:
            self.no_progress_count += 1
            if self.no_progress_count >= self.no_progress_limit:
                return StopReason.NO_PROGRESS
        else:
            self.no_progress_count = 0
    self.last_score = score
```

---

### FINDING 6 — LOW: `BudgetTracker`, `CheckpointStore`, and `SessionMemory` SQLite connections are never closed by `Orchestrator`

**File:** `maglab/core/orchestrator.py:311-342` (`Orchestrator.__init__`)

**Defect:**  
`Orchestrator` constructs `BudgetTracker`, `CheckpointStore`, and `SessionMemory` — each opens a SQLite connection — but `Orchestrator` exposes no `close()` method and is not a context manager. The connections are left open until garbage collection (CPython) or process exit. On Windows or network filesystems, unclosed SQLite connections can prevent file access by other processes or cause locking errors across sessions.

**Fix:** Add a `close()` method and/or `__enter__`/`__exit__` to `Orchestrator`:

```python
def close(self) -> None:
    """Close all owned DB connections."""
    self._budget.close()
    self._checkpoint.close()
    self._session_memory.close()

def __enter__(self) -> Orchestrator:
    return self

def __exit__(self, *_: object) -> None:
    self.close()
```

`repl.py:215` constructs an `Orchestrator` with no cleanup path — this should use a context manager or `try/finally`.

---

## Non-Findings (investigated but dismissed)

- **`_stop()` returning `None`** (`ralph.py:606-618`): annotated as `-> RalphState` but returns `self._state` which is `None` when called before `start()`. The `# type: ignore` comment acknowledges this. Public `stop()` method always calls `_stop()` which by contract is only called after `start()` internally, so the null-return is only reachable via the (unguarded) private method. Logged as an annotation/type-system inconsistency, not a runtime defect.
- **`APIBackend` retry loop wastes a `sleep` on the last attempt**: real but very minor (negligible latency cost, no correctness impact).
- **`WorkingContext.compact()` token count reset**: correctly uses `len(full_summary) // 4` for the new context — no defect.
- **`AutonomyGate` Tier-3 block in `autonomous` mode**: docstring says Tier 3 always requires human approval; the code correctly calls `_request_approval` for Tier 3 in autonomous mode. No gap.
- **`Deny rule hook` ordering vs. `oracle_hook`**: `oracle_hook` is correctly prepended via `default_registry()` so it runs before tier checks. No bypass possible.
