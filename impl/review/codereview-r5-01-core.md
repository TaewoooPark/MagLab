# Code Review — Round 5, Core Domain

**Reviewer:** automated adversarial audit  
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`  
**Date:** 2026-05-19  
**Basis:** Independent fresh re-audit of the current code after R1–R4 patches.

---

## R4 Fixes — Verification Status

| R4 Finding | Status |
|---|---|
| F1 — `ReportBuilder.build()` false `OUT_OF_VAULT_VALUE` for registered DataPoints | **FIXED** — `effective_vault_ids = (vault_ids | known_ids) if vault_ids is not None else None` correctly merges builder-registered IDs before calling `run_gate` |
| F2 — `RalphEngine.detached_loop()` always terminates after ~4 iterations | **FIXED** — `score_fn=None` path now calls `self._circuit.reset_no_progress()` before `self.step()`, suppressing the NO_PROGRESS breaker; loop runs to `max_iterations`; empirically verified with 10-iteration test |

---

## Verdict

**ISSUES FOUND** — 1 genuine defect: MEDIUM severity (entity attributes irreversibly stripped from `ProvenanceStore.get_entity_lineage()` return value).

---

## Findings

### FINDING 1 — MEDIUM: `ProvenanceStore.get_entity_lineage()` returns `prov_json={id, kind}` only — entity attributes (provenance_type, units, source_ref, timestamp) are inaccessible from the lineage API

**File:** `maglab/provenance/store.py:315–344` (`_flush_to_db`) and `maglab/provenance/store.py:238–281` (`get_entity_lineage`)

**Defect:**

`_flush_to_db` stores a minimal stub in the `prov_records.prov_json` column:

```python
record_json = json.dumps({"id": record_id, "kind": kind})
```

When `add_entity('dp-uuid', attributes={'provenance_type': 'MEASURED', 'units': 'A/m', 'source_ref': 'DOI:10.1234/x', 'timestamp': '...'})` is called, the attributes are registered in the in-memory `ProvDocument` (`self._doc`) and serialised to `prov_graph.graph_json`. However, `prov_records.prov_json` for that entity row stores only `{"id": "ml:dp-uuid", "kind": "entity"}`.

`get_entity_lineage()` queries `prov_records` and returns rows including the `prov_json` column. Each row's `prov_json` is therefore useless — it duplicates the `id` and `kind` columns and contains no attribute data:

```python
# Empirically verified:
store = ProvenanceStore()
store.add_entity('dp-123', attributes={'provenance_type': 'MEASURED', 'units': 'A/m', 'source_ref': 'DOI:10.1234/x', 'timestamp': '2025-01-01...'})
lineage = store.get_entity_lineage('dp-123')
# lineage[0]['prov_json'] == '{"id": "ml:dp-123", "kind": "entity"}'
# provenance_type, units, source_ref, timestamp: ALL ABSENT
```

The full attributes ARE present in `prov_graph.graph_json` (the full PROV-JSON document export) but `get_entity_lineage()` does not query that table.

**Impact:**

`ProvenanceLedger.lineage()` delegates directly to `store.get_entity_lineage()`. The MCP server's `provenance_query` tool (used by external callers) returns:

```python
{"datapoint": {...}, "lineage": lineage}
```

where `lineage` elements contain only `{id, kind, prov_json: {id, kind}, created_at}`. Callers inspecting the lineage receive no provenance attributes — the primary purpose of the provenance system (§17: "every output carries Provenance") is not fulfilled by this API.

**Root cause:** The R3 fix to the LIKE-query false-positive problem stripped `prov_json` down to `{id, kind}` to prevent the old full-document dump from causing false LIKE matches. The fix was more aggressive than necessary — the LIKE patterns in `get_entity_lineage()` match on the `id` column (not `prov_json`), so stripping `prov_json` was not required to fix the LIKE issue.

**Fix:**

Store the per-record attributes in `prov_json` instead of the full document dump (old bug) or a stub (current bug). In `_flush_to_db`, serialize only the attributes that belong to this specific record:

```python
def _flush_to_db(self, qn: pm.QualifiedName, kind: str, attributes: dict | None = None) -> None:
    record_id = str(qn)
    # Store per-record data (not the full document, not a minimal stub)
    record_json = json.dumps({"id": record_id, "kind": kind, **(attributes or {})})
    ...
```

And pass `attributes` from the callers (`add_entity`, `add_activity`, `add_agent`). Alternatively, query `prov_graph.graph_json` in `get_entity_lineage()` and extract the entity-specific attributes from the full PROV-JSON document:

```python
def get_entity_lineage(self, local_id: str) -> list[dict[str, Any]]:
    # (existing LIKE query to get rows...)
    # Then enrich with attributes from prov_graph:
    cur = self._conn.execute("SELECT graph_json FROM prov_graph WHERE id='current'")
    graph_row = cur.fetchone()
    if graph_row:
        full_graph = json.loads(graph_row[0])
        qn_str = _qname(local_id)
        entity_attrs = full_graph.get("entity", {}).get(qn_str, {})
        # Inject into the relevant row's prov_json
    ...
```

---

## Non-Findings (investigated and dismissed)

- **`_tool_loop` drops ASSISTANT message when `response.content is None` before TOOL messages:** The tool-results handling path is currently unreachable — `_tool_loop` never passes `tools=` to `backend.complete()`, so `response.tool_calls` is always `[]` in practice. The architecture issue (missing `tool_calls` field on `Message`) would cause API-format violations if tools were ever enabled, but it is a latent dead-code defect, not a currently reachable bug. Severity would be HIGH if tools are wired up; as-is, LOW.

- **`_check_promises` global write-tool suppression (any write tool in log suppresses all promise violations):** Design choice that accepts false negatives to avoid false positives on promise-check. Not a logic error.

- **`APIBackend.max_retries` counts attempts, not retries (3 → 3 attempts, not 3+1):** Minor docstring naming inconsistency; the exponential backoff and retry logic are functionally correct.

- **`BudgetTracker.is_over_budget()` is O(n) on `_session_steps`:** Performance concern only; no correctness impact.

- **`RalphState.from_markdown()` roundtrip for complex goal strings (metacharacters, dashes):** Empirically verified correct — all tested goal strings round-trip without loss.

- **`_ABSOLUTE_ZERO_RE` regex in `reasoning.py`:** R3 fix is correctly in place at line 42. Verified that `100 K`, `200 K`, `10 K` do not match; `0 K`, `0K`, `at 0K` do match.

- **`ProvenanceStore` LIKE patterns with UUID-formatted entity IDs:** Empirically verified correct — `wdf-%-{uuid}` patterns correctly isolate derivation relations for UUID local IDs without false positives under normal usage.

- **`summarize_datapoints` with empty list or array-only DataPoints:** Both edge cases handled correctly — `scalar_stats` absent when no scalar DataPoints; no division by zero.

- **`DataPoint.scalar()` / `summarize_datapoints` with `ddof=1` single-value std:** Guard `if len(values) > 1 else 0.0` prevents the `n-1 = 0` denominator case.

- **`ReportBuilder.build()` — gate not called when narrative is empty (entries only):** Intentional design — the gate runs on narrative text; the `if combined_text.strip()` guard is correct.

- **`Orchestrator.close()` resource management:** Correctly implemented with `__enter__`/`__exit__`; `repl.py` uses `try/finally` to guarantee `close()` on exit.
