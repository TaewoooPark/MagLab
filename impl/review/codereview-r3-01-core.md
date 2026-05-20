# Code Review — Round 3, Core Domain

**Reviewer:** automated adversarial audit  
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`  
**Date:** 2026-05-19  
**Basis:** Independent fresh re-audit of the current code after R1 and R2 patches. All four R2 findings were verified as genuinely fixed before searching for new defects.

---

## R2 Fixes — Verification Status

| R2 Finding | Status |
|---|---|
| F1 — `_PROMISE_RE` fires on passive/third-person constructions | **FIXED** — now requires explicit `I` or `we` subject; passive constructions no longer match |
| F2 — `_parse_critic_response` false PASSED on substring | **FIXED** — checks last non-empty line with `\bPASSED\b` boundary and excludes `NOT PASSED`/`FAILED` |
| F3 — `ResearchPool.query()` / `semantic_query()` crash on corrupt pool file | **FIXED** — both iterating loops now wrap `_load()` in `try/except` with log + skip |
| F4 — `repl.py` did not call `Orchestrator.close()` | **FIXED** — `try/finally` block added; `close()` called via `getattr` check regardless of how REPL exits |

---

## Verdict

**ISSUES FOUND** — 2 genuine defects: 1 HIGH (honesty gate bypassed by default), 1 MEDIUM (false physics invalidity for any hypothesis mentioning a temperature ending in `0 K`).

---

## Findings

### FINDING 1 — HIGH: `ReportBuilder.build()` silently discards all violations when `raise_on_violation=False` (the default)

**File:** `maglab/report/reporting.py:232-240`

**Defect:**

```python
def build(self, run_honesty_gate=True, raise_on_violation=False, ...) -> Report:
    violations: list[Violation] = []
    if run_honesty_gate and (self._narrative or self._entries):
        known_ids = {e.dp.id for e in self._entries}
        combined_text = self._narrative
        if combined_text.strip():
            try:
                run_gate(                          # ← return value NOT captured
                    combined_text,
                    known_dp_ids=known_ids,
                    vault_ids=vault_ids,
                    verified_citations=verified_citations,
                    raise_on_violation=raise_on_violation,  # False by default
                )
            except HonestyViolation as exc:        # ← never triggered when raise=False
                violations.extend(exc.violations)  # ← never executed
    return Report(..., violations=violations)      # ← violations always []
```

When `raise_on_violation=False` (the default for both `ReportBuilder.build()` and the convenience `build_report()` function), `run_gate()` returns a `GateResult` object instead of raising. The return value is **never captured** and the `except HonestyViolation` branch is **never reached**. The `violations` list stays empty for the lifetime of the call.

Consequence: `Report.violations` is always `[]` and `Report.passed_gate` always returns `True` when using the default `raise_on_violation=False`, regardless of how many untagged numbers, unverified citations, or first-person attribution patterns are present in the narrative. The HonestyGate is effectively **completely bypassed** for every caller that uses the default API.

**Confirmed by code inspection:** `run_gate()` signature is:
```python
def run_gate(..., raise_on_violation: bool = True) -> GateResult:
```
When called with `raise_on_violation=False`, it returns a populated `GateResult(passed=False, violations=[...])` but the caller discards it.

**Fix:** Capture the gate result and extend violations from it:

```python
if combined_text.strip():
    try:
        gate_result = run_gate(
            combined_text,
            known_dp_ids=known_ids,
            vault_ids=vault_ids,
            verified_citations=verified_citations,
            raise_on_violation=raise_on_violation,
        )
        violations.extend(gate_result.violations)   # always capture
    except HonestyViolation as exc:
        violations.extend(exc.violations)
```

This way violations are populated whether or not `raise_on_violation` is set.

---

### FINDING 2 — MEDIUM: `reflection_physics_check` flags valid hypotheses as physically invalid via false-positive `'0 k'` substring match

**File:** `maglab/core/reasoning.py:1083-1086`

**Defect:**

```python
full_text = f"{candidate.idea} {candidate.novelty_rationale}".lower()
...
if oracle_check_fn is not None:
    params: dict[str, Any] = {}
    if "absolute zero" in full_text or "0 k" in full_text:   # ← broken pattern
        params["T"] = 0.0
    if params:
        result = oracle_check_fn(params)   # oracle says T=0.0 is invalid (T <= 0)
        ...
        return ReflectionResult(valid=False, ...)
```

The substring `"0 k"` (lowercase) appears in any hypothesis text that mentions a temperature whose digit representation ends in `0` followed by a space and the unit `k` (for Kelvin). This includes every temperature of the form `100 K`, `200 K`, `300 K`, `10 K`, `400 K`, etc.

**Confirmed empirically:**
```python
full_text = "topological hall effect in YBa2Cu3O7 at 300 K shows transition".lower()
"0 k" in full_text  # → True   ('30[0 k]')

full_text = "spin transport measurement at 100 K below the curie temperature".lower()
"0 k" in full_text  # → True   ('10[0 k]')

full_text = "magnon-drag at 10 K in dilution refrigerator".lower()
"0 k" in full_text  # → True   ('1[0 k]')
```

When the match fires, `params["T"] = 0.0` is set and `oracle.check({"T": 0.0})` returns `ok=False` (because `check_temperature` rejects `T <= 0`). `reflection_physics_check` then returns `ReflectionResult(valid=False, ...)`. In `D1HypothesisEngine.run()`, this sets `rh.physical_valid = False` for every ranked hypothesis that mentions any of the common temperatures above.

**Impact:** The D1 hypothesis engine's physical validity reflection pass (§5.10, T-P6-37) incorrectly marks a large fraction of valid hypotheses as physically invalid. Any hypothesis mentioning `100 K`, `200 K`, `300 K`, etc. receives `physical_valid=False` and a spurious `physics_contradiction` message, undermining the scientific credibility of the engine output.

**Fix:** Require a word boundary before the `0` and after the `k`, and add a space requirement to prevent the substring match from spanning across unrelated words. The most robust fix is to match the full phrase `"at 0 k"` or to restrict the check to known unphysical absolute-zero phrases:

```python
# Replace the broad substring check with a word-boundary pattern
import re as _re
_ABSOLUTE_ZERO_RE = _re.compile(r'\b0\s*k\b', _re.IGNORECASE)
_ABS_ZERO_PHRASES = {"absolute zero", "0 kelvin", "zero kelvin"}

has_zero_temp = any(ph in full_text for ph in _ABS_ZERO_PHRASES) or bool(
    _ABSOLUTE_ZERO_RE.search(full_text)
)
```

Even simpler: just remove the `"0 k"` check and rely on the explicit textual pattern `"below absolute zero"` (which is already checked in the `contradictions` list above the oracle block) plus the `"absolute zero"` substring — which is specific enough.

---

## Non-Findings (investigated and dismissed)

- **`generate_candidates` shuffle vs. comment contradiction** (`reasoning.py:879`): R2 explicitly dismissed this as negligible. Re-examined: with default `n=5` and 5 seed templates, all seeds are returned in a random order regardless. With `n < 5`, the comment "matching seeds come first" is indeed false after `rng.shuffle()`, but the R2 reviewer's assessment stands — the seed pool is small enough that the quality degradation is negligible. Not a correctness bug.
- **`_tool_loop` missing ASSISTANT message before TOOL messages** (`orchestrator.py:598-599`): When `response.content` is `None` (pure tool-call response), no `ASSISTANT` message is added before the `TOOL` messages. The correctness of this depends on LiteLLM's normalization behaviour, which internally may reconstruct the ASSISTANT turn. The codebase documents this case in a comment. Marked as non-finding pending evidence of actual API rejection.
- **`SubagentDef` extra frontmatter fields silently dropped** (`subagents.py:109`): The dict comprehension `{k: v for k, v in fm.items() if k in SubagentDef.model_fields}` discards keys not in `model_fields` before Pydantic validation, making `model_config = {"extra": "allow"}` unreachable. This is a design inconsistency but does not cause crashes or data loss — no caller relies on extra subagent frontmatter fields.
- **`APIBackend._call_litellm` sleeps after last retry** (`llm/backends/api.py:147`): The exponential backoff `time.sleep(delay)` runs even on the final iteration. Confirmed from R1 as negligible.
- **`BudgetTracker.is_over_budget()` with `max_usd <= 0`** (`core/budget.py:368`): `self._max_usd > 0` guard means zero/negative budget disables the gate entirely. This is intentional and documented (`0 = disabled`). Not a defect.
- **`ProvenanceStore._flush_to_db` O(n²) serialization** (`provenance/store.py:315`): Every add calls `_serialize_doc(self._doc)` which serializes the full document. Performance degrades quadratically with document size. A genuine performance concern but not a logic or correctness defect.
- **`ConfigModel.ui.theme` mutable during REPL session** (`repl.py:142`): `config.ui.theme = name` mutation is intentional (in-session theme change propagation). Config is a regular Pydantic `BaseModel` (not frozen), so mutation succeeds. Not a defect.
