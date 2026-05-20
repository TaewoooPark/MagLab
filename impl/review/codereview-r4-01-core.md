# Code Review — Round 4, Core Domain

**Reviewer:** automated adversarial audit  
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`  
**Date:** 2026-05-19  
**Basis:** Independent fresh re-audit of the current code after R1, R2, and R3 patches.

---

## R3 Fixes — Verification Status

| R3 Finding | Status |
|---|---|
| F1 — `ReportBuilder.build()` discards violations when `raise_on_violation=False` | **FIXED** — `gate_result = run_gate(...)` now captures the return value and `violations.extend(gate_result.violations)` propagates them |
| F2 — `reflection_physics_check` false-positive `"0 k"` substring match | **FIXED** — `_ABSOLUTE_ZERO_RE = re.compile(r"(?<!\d)0\s*k(?!\w)", re.IGNORECASE)` is now defined at module level; empirically confirmed that `100 K`, `200 K`, `300 K`, `10 K` do not match |

---

## Verdict

**ISSUES FOUND** — 2 genuine defects: 1 MEDIUM (spurious `OUT_OF_VAULT_VALUE` violations for explicitly-registered DataPoints), 1 MEDIUM (Ralph `detached_loop` always terminates after ~4 iterations regardless of `max_iterations`).

---

## Findings

### FINDING 1 — MEDIUM: `ReportBuilder.build()` produces false `OUT_OF_VAULT_VALUE` violations for DataPoints the caller explicitly registered

**File:** `maglab/report/reporting.py:226-241`

**Defect:**

```python
known_ids: set[str] = {e.dp.id for e in self._entries}  # DataPoint IDs added via .add()
combined_text = self._narrative

if combined_text.strip():
    gate_result = run_gate(
        combined_text,
        known_dp_ids=known_ids,
        vault_ids=vault_ids,          # ← vault_ids is caller-supplied, does NOT include known_ids
        ...
    )
```

Inside `run_gate`, when `vault_ids is not None`, `check_vault_references(text, vault_ids)` is called (line 507–509 of `honesty_gate.py`). That function scans `text` for UUID patterns and flags any UUID not present in `vault_ids`. The DataPoint IDs in `known_ids` — which the caller explicitly registered via `builder.add(dp)` — are **not merged into `vault_ids`** before the call.

**Consequence:** Any narrative that contains DataPoint UUID strings (the intended provenance-tagging pattern: `f"The result {dp.id} confirms..."`) will generate spurious `OUT_OF_VAULT_VALUE` violations for those UUIDs if the caller provides a non-`None` `vault_ids` argument. The violations propagate into `Report.violations` and `Report.passed_gate` returns `False` for a correctly-constructed, fully-provenanced report — silently treating correct DataPoint usage as an integrity violation.

**Evidence:**
```python
# Scenario:
dp = DataPoint(value=8e5, units="A/m", provenance_type=ProvenanceType.MEASURED)
builder = ReportBuilder("Ms result")
builder.add(dp)
builder.narrative(f"Measured Ms = 8e5 A/m [{dp.id}], within the expected range.")
report = builder.build(vault_ids={"some-external-vault-id"})  # dp.id NOT in vault_ids
# report.violations contains OUT_OF_VAULT_VALUE for dp.id
# report.passed_gate == False  ← WRONG
```

**Fix:** Merge `known_ids` into an effective vault IDs set before calling `run_gate`, but only when `vault_ids` is not `None` (preserving the existing semantics where `vault_ids=None` skips the vault check entirely):

```python
# In ReportBuilder.build(), replace:
gate_result = run_gate(
    combined_text,
    known_dp_ids=known_ids,
    vault_ids=vault_ids,
    ...
)
# With:
effective_vault_ids = (vault_ids | known_ids) if vault_ids is not None else None
gate_result = run_gate(
    combined_text,
    known_dp_ids=known_ids,
    vault_ids=effective_vault_ids,
    ...
)
```

---

### FINDING 2 — MEDIUM: `RalphEngine.detached_loop()` always terminates after ~4 iterations regardless of `max_iterations`

**File:** `maglab/core/ralph.py:601`

**Defect:**

```python
def detached_loop(self, agent_fn: Any, *args: Any, ...) -> list[str]:
    ...
    while self._state.active and self._state.iteration < self._state.max_iterations:
        ...
        output = agent_fn(self._state, *args, **kwargs)
        outputs.append(output)
        reason = self.step(output, score=0.5)   # ← score is hardcoded to 0.5 every iteration
        ...
```

`engine.step()` calls `self._circuit.record_output(output, score)`, which computes `delta = abs(score - self.last_score)`. With a constant `score=0.5`:

| Iteration | `last_score` before | `delta` | `no_progress_count` | Triggered |
|---|---|---|---|---|
| 1 | `None` | (skipped — first call) | 0 | — |
| 2 | `0.5` | `0.0 < 0.01` | 1 | — |
| 3 | `0.5` | `0.0 < 0.01` | 2 | — |
| 4 | `0.5` | `0.0 < 0.01` | 3 ≥ limit | `NO_PROGRESS` |

The loop is hard-terminated at **iteration 4** by the `NO_PROGRESS` circuit breaker, regardless of what `max_iterations` is set to. A caller who configures `RalphEngine(max_iterations=20, ...)` and calls `detached_loop()` will receive only 4 iterations of output. `MAX_ITERATIONS_OVERNIGHT = 50` is entirely unreachable.

**Empirically confirmed:**
```python
cb = CircuitBreakerState()
for i in range(1, 10):
    r = cb.record_output(f"iteration {i} unique output", 0.5)
    if r:
        print(f"Stopped at iteration {i}: {r}")  # → "Stopped at iteration 4: NO_PROGRESS"
        break
```

**Impact:** All callers of `detached_loop()` (external users and any future internal callers) get at most 4 iterations. The method's docstring claims "calls `agent_fn` on each iteration" up to `max_iterations` times, which is false. The `git_commit` handoff mechanism (§6.2) is similarly limited: at most 4 commits are ever made by a detached loop.

**Fix:** Allow the `agent_fn` to return a `(output, score)` tuple, or add a `score_fn` parameter, or default the score to a value that changes each iteration (e.g. normalize iteration index). The simplest backward-compatible fix that preserves the existing API:

```python
# Option A: reset no_progress_count before calling record_output in detached mode
# (detached loops handle external progress signals differently from in-session loops)
self._circuit.reset_no_progress()
reason = self._circuit.record_output(output, score)
```

Or better:

```python
# Option B: expose a score_fn parameter
def detached_loop(
    self,
    agent_fn: Any,
    *args: Any,
    git_commit: bool = False,
    score_fn: Callable[[str, int], float] | None = None,  # (output, iteration) -> score
    **kwargs: Any,
) -> list[str]:
    ...
    score = score_fn(output, self._state.iteration) if score_fn else 0.5
    reason = self.step(output, score=score)
```

Until fixed, callers who need more than 4 iterations should **not** use `detached_loop()` and should instead call `engine.step()` directly with a meaningful score.

---

## Non-Findings (investigated and dismissed)

- **Conversation history gap from empty assistant turns** (`orchestrator.py:527`): The filter `if m.get("content")` silently drops `content=""` assistant turns from the LLM message list. Empty content only occurs on degenerate API responses (no text, no tool_calls), which LLMs never produce under normal conditions. Confirmed as pre-existing design weakness (R3 non-finding); not introduced by any R3 patch.
- **`ProvenanceLedger` resource leak when `store=None`** (`provenance/ledger.py:32`): The default `ProvenanceStore()` uses `:memory:` (in-memory SQLite). In-memory connections are reclaimed by the Python GC and leave no file handles. File-backed stores must be injected by callers who control their lifecycle. Not a defect.
- **`DelegatedCLIBackend` potential `OSError` on very long prompts** (`llm/backends/delegated_cli.py:110`): The prompt is appended as a list argument to subprocess, so no shell injection risk. Very long prompts could exceed `ARG_MAX`, but this is a runtime error that propagates naturally; no silent data loss.
- **`detached_loop` `git add -A` includes untracked files** (`core/ralph.py:644`): Intentional per §6.2 design (full working-tree snapshot). Not a defect.
- **`_REGISTRY` global mutable dict in `llm/tools.py`**: Module-level registry is initialised once at import time; concurrent registration would require `@tool` decorators to run in parallel threads at import time, which Python's GIL prevents. Not a defect.
- **`check_vault_references` O(n×m) set creation** (`report/honesty_gate.py:324`): `{v.lower() for v in vault_ids}` is rebuilt for every UUID found in the text. A performance concern for very large vaults but not a correctness defect; outside scope of this review.
