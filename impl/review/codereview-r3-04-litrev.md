# Code Review R3 — Literature / Reviewer / Lab Domain

**Reviewer:** Claude Code (Round 3 automated re-audit)
**Date:** 2026-05-19
**Domain:** `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Scope:** Independent re-audit of patched code. Not a plan-conformance check.

---

## Verdict

**ISSUES FOUND**

Six genuine defects found: two HIGH and four MEDIUM.

---

## Findings

### F1 — HIGH | `maglab/reviewer/panel.py:214`

**Safeguard ③ arXiv citation validation always bypassed via `or None` logic**

`_review_single()` constructs `PersonaGuard` with:

```python
guard = PersonaGuard(
    verified_dois=persona.verified_dois,
    verified_arxivs=persona.verified_arxivs or None,   # ← bug
)
```

`PersonaSpec.verified_arxivs` defaults to `set()` (empty set). An empty set is falsy in Python, so `set() or None` evaluates to `None`. This is passed to `PersonaGuard.__init__` as `verified_arxivs=None`.

In `disclosure.py:342`, `check_fabricated_citations()` contains:
```python
if verified_arxivs is not None:
    # validate arXiv IDs in text against verified set
```

Because `None` is passed, arXiv ID validation is **never triggered** regardless of what arXiv IDs appear in the review text. Any fabricated arXiv citation passes unchecked.

Note the asymmetry: `verified_dois=persona.verified_dois` passes the empty set directly (not `or None`), so DOI validation **does** fire for empty sets (flagging any DOI as unverified). arXiv validation is silently skipped.

**Fix:** Remove `or None` — pass the set directly:
```python
verified_arxivs=persona.verified_arxivs,
```
If the intent is to skip arXiv validation when no arXiv papers exist, use `verified_arxivs=persona.verified_arxivs if persona.verified_arxivs else None` — but this asymmetry should be explicit and documented.

---

### F2 — HIGH | `maglab/literature/graph.py:487–492`

**Retraction cache has no TTL — stale `ok` status persists indefinitely**

`check_retraction()` queries the `retraction_cache` table:

```python
cached = self._conn.execute(
    "SELECT status FROM retraction_cache WHERE doi = ?", (doi_norm,)
).fetchone()
if cached:
    status = cached["status"]    # ← no TTL check
```

The `retraction_cache` table stores a `checked_at` timestamp column, but this column is never compared to `time.time()`. Any cached row is used indefinitely.

**Impact:** A paper verified as `ok` on day 0 will remain `ok` in the cache forever, even if retracted on day 30. The §14.6 integrity block — described as a non-negotiable guarantee — silently fails for papers that were clean at first check but subsequently retracted.

**Fix:** Add a TTL check (e.g., 7 days) when reading from cache:
```python
cached = self._conn.execute(
    "SELECT status, checked_at FROM retraction_cache WHERE doi = ?", (doi_norm,)
).fetchone()
_TTL_S = 7 * 86400
if cached and (time.time() - cached["checked_at"] < _TTL_S):
    status = cached["status"]
else:
    status = self._fetch_retraction_status_from_oa(doi_norm)
    # INSERT OR REPLACE to refresh
```

---

### F3 — MEDIUM | `maglab/literature/corpus.py:212–219`

**`update_retraction_status()` DOI normalization mismatch — zero rows matched**

Records are stored via `add()` using `record.doi`, which is sourced from connector normalizations that strip the `https://doi.org/` prefix (e.g., stored as `"10.1234/test"`).

`update_retraction_status()` normalizes with only `doi.lower()`:
```python
doi_norm = doi.lower()    # ← no prefix stripping
self._conn.execute(
    "UPDATE records SET retraction_status = ? WHERE doi = ?",
    (status, doi_norm),
)
```

A call like `update_retraction_status("https://doi.org/10.1234/test", "retracted")` generates `WHERE doi = "https://doi.org/10.1234/test"`, which matches zero rows (stored key is `"10.1234/test"`). The update silently succeeds with 0 rows affected.

Compare: `get_by_doi()` (line 149) applies full normalization including `https://`, `http://`, and `doi:` prefix stripping, plus an additional SQL `REPLACE` expression.

**Fix:** Apply the same normalization as `get_by_doi()`:
```python
doi_norm = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").replace("doi:", "")
```

---

### F4 — MEDIUM | `maglab/literature/rag.py:493`

**`int(NaN)` crash in `_load_from_db` aborts all chunk loading**

In `_load_from_db()`:
```python
year=int(row["year"]) if row.get("year") else None,
```

pandas returns `float("nan")` for SQL NULL values (not Python `None`). `float("nan")` is truthy, so the condition `if row.get("year")` evaluates to `True`, and `int(float("nan"))` raises `ValueError`.

This `ValueError` propagates from inside the `for _, row in rows.iterrows()` loop to the outer `except Exception` at line 504, which logs and returns. All chunks loaded before the bad row are discarded and `self._chunks` remains empty — the entire RAG index falls back to memory-only mode, losing all persisted data.

`_persist_chunks()` stores year as `c.year or 0`, so a `None` year becomes `0`. `int(0)` is fine and `0` is falsy, so this specific path (year stored as `0`) would not trigger the bug. However, if rows were inserted externally or via an older code path with SQL NULL, NaN would arise.

**Fix:**
```python
import math
year_raw = row.get("year")
year = int(year_raw) if year_raw is not None and not (isinstance(year_raw, float) and math.isnan(year_raw)) and year_raw else None
```
Or more cleanly using pandas:
```python
import pandas as pd
year = int(row["year"]) if pd.notna(row.get("year")) and row.get("year") else None
```

---

### F5 — MEDIUM | `maglab/literature/graph.py:484`

**`check_retraction()` only strips `https://` DOI prefix, not `http://` or `doi:` prefix**

```python
doi_norm = doi.lower().replace("https://doi.org/", "")
```

This is inconsistent with `corpus.py:get_by_doi()` (line 149), which strips three prefixes:
```python
doi_norm = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").replace("doi:", "")
```

An `http://doi.org/10.x` input is cached as `"http://doi.org/10.x"` in `retraction_cache`. A subsequent lookup with `https://doi.org/10.x` is cached as `"10.x"`. The same paper has two independent cache entries, potentially with different statuses. Worse, a paper retracted under the `http://` key would not be blocked when looked up via the `https://` form.

**Fix:** Apply the same three-prefix normalization used by `corpus.py:get_by_doi()`.

---

### F6 — MEDIUM | `maglab/literature/graph.py:445–460`

**Empty DOI causes all DOI-less contradictions to share `node_id = "paper:unknown"`**

In `report_property()`:
```python
node_a_id = f"paper:{row['doi'] or 'unknown'}"
node_b_id = f"paper:{doi or 'unknown'}"
edge_id = f"contra_{node_a_id}_{node_b_id}_{property_name}"
```

When `doi == ""` (paper has no DOI), both `node_a_id` and `node_b_id` collapse to `"paper:unknown"`. The `edge_id` becomes `"contra_paper:unknown_paper:unknown_{property_name}"`. Since `edge_id` is a PRIMARY KEY, the first undocumented contradiction for each property is recorded; all subsequent ones are silently dropped by `add_edge()`'s `IntegrityError` handler. Multiple distinct papers are conflated into a single graph node.

**Fix:** Use a content-based unique fallback when DOI is absent. Options:
- Hash the title + authors: `f"paper:{hashlib.md5(title.encode()).hexdigest()[:12]}"`
- Use `row["id"]` (the autoincrement PK of `property_reports`) for existing rows

---

## Low-Severity Observations (not findings)

- `maglab/literature/rag.py` `_vector_search()`: LanceDB is used for persistence only; actual vector search iterates over all `self._chunks` in memory (O(N) brute force). LanceDB's ANN index is never queried. This is functional for small corpora but will not scale.
- `CorpusDB`, `KnowledgeGraph`, `EvidenceMatrix`: each has `close()` but no `__enter__`/`__exit__`, making them inconvenient to use as context managers. The module-level singletons (`_default_corpus`, etc.) are never closed. Low risk for a CLI tool.
- `maglab/reviewer/loop_a.py:217–219`: the early-success path calls `engine.step()` then returns immediately, bypassing the checkpoint save at lines 276–278. The final successful state is not written to disk when `state_path` is set. Low severity — the result is returned in-memory.

---

## Summary Table

| ID | Severity | File:Line | Defect |
|---|---|---|---|
| F1 | HIGH | `reviewer/panel.py:214` | `verified_arxivs or None` bypasses safeguard ③ arXiv validation |
| F2 | HIGH | `literature/graph.py:487–492` | Retraction cache has no TTL — stale status persists indefinitely |
| F3 | MEDIUM | `literature/corpus.py:212–219` | `update_retraction_status()` does not strip DOI prefix — zero rows matched |
| F4 | MEDIUM | `literature/rag.py:493` | `int(NaN)` crash aborts all chunk loading from LanceDB persistence |
| F5 | MEDIUM | `literature/graph.py:484` | `check_retraction()` only strips `https://` prefix, not `http://` or `doi:` |
| F6 | MEDIUM | `literature/graph.py:445–460` | Empty-DOI contradiction nodes all collapse to `paper:unknown`, losing records |
