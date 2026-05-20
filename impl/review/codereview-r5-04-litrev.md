# Code Review R5 — Literature / Reviewer / Lab
**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 5 (post-R4-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND**

---

## Findings

### F-01 — LOW | `maglab/literature/corpus.py:149-153` and `corpus.py:219-228`

**Defect**: The SQL `REPLACE` chain in both `get_by_doi()` and `update_retraction_status()` strips only two DOI prefixes (`https://doi.org/` and `http://doi.org/`) from the stored `doi` column, while the Python normalization (`doi_norm`) applied to the *input* argument strips all three prefixes including `doi:`. This creates a silent mismatch if any `LiteratureRecord` is ever stored with a `doi` value containing the `doi:` prefix.

**Trace**:
- `LiteratureRecord.doi` docstring states "normalized: lowercase, leading `https://doi.org/` removed" — `doi:` prefix removal is not mentioned and not enforced by a Pydantic validator.
- `CorpusDB.add(record)` stores `record.doi` verbatim at line 115 without calling `record.normalized_doi()`.
- If a user constructs `LiteratureRecord(doi='doi:10.1103/physrevb.103.014412')`, the stored DB value is `'doi:10.1103/physrevb.103.014412'`.
- `get_by_doi('doi:10.1103/physrevb.103.014412')`: Python normalizes input to `'10.1103/physrevb.103.014412'`. SQL tests `LOWER(REPLACE(REPLACE('doi:10.1103/...', 'https://doi.org/', ''), 'http://doi.org/', ''))` → `'doi:10.1103/...'` ≠ `'10.1103/...'` → **miss**.
- `update_retraction_status('doi:10.1103/...', 'retracted')`: same mismatch → **silent no-op**.

**Context from R4**: R4 F-03 added the `REPLACE` SQL expression to `update_retraction_status` and `get_by_doi`, but the fix included only two `REPLACE` calls, omitting the `doi:` prefix. The fix is incomplete.

**Practical impact**: LOW. All four connectors (`OpenAlexConnector`, `SemanticScholarConnector`, `ArXivConnector`, `CrossRefConnector`) normalize DOIs at parse time and none produce the `doi:` prefix. The gap only activates if external code constructs a `LiteratureRecord` with a `doi:` prefix, which can occur if callers follow common library conventions (e.g., Habanero returns bare DOIs, but Zotero-style exports use `doi:` prefix).

**Fix**: Add a third `REPLACE` for `'doi:'` in both SQL expressions, matching the Python normalization:

```python
# get_by_doi (line 151) and update_retraction_status (line 227):
"WHERE LOWER(REPLACE(REPLACE(REPLACE(doi, 'https://doi.org/', ''), 'http://doi.org/', ''), 'doi:', '')) = ?"
```

Alternatively, enforce normalization at storage time by calling `record.normalized_doi()` in `CorpusDB.add()` before inserting:
```python
# In CorpusDB.add(), line 115:
record.doi,  # current
# -> change to:
record.normalized_doi(),  # normalized at storage
```

---

## Non-Findings (reviewed and dismissed)

- **`PersonaSpec.verified_dois` default (R4 F-01)**: Confirmed fixed — `verified_dois: set[str] | None = None` at `panel.py:55`. Safeguard ③ correctly skips per-DOI whitelist validation when `None`.
- **`KnowledgeGraph.set_retraction_cache` normalization (R4 F-02)**: Confirmed fixed — `graph.py:560-565` now applies all three-prefix normalization.
- **`_CorpusBM25Index._pending` growth**: The `_pending` list accumulates all chunks ever added and is never cleared after `_rebuild_if_dirty()`. This means memory usage is O(n) for n total chunks and each rebuild processes the full historical list. This is a resource concern but not a correctness defect — the rebuild is intentional and produces a correct full index. For the expected CLI usage scale (hundreds of chunks per author corpus), this is within acceptable bounds. Not filing as a defect.
- **`_with_backoff` + retriable `RuntimeError` wrapping**: After exhausting retries, `_with_backoff` raises `RuntimeError("... failed after N retries: <original_exc>")`. If the wrapped message contains `" 429 "`, `_is_retriable` would classify the `RuntimeError` as retriable — but only callers external to the decorator see this `RuntimeError`. `fetch_by_doi_multi` catches it via `except Exception` and logs/returns `None`. No retry amplification occurs. Not a defect.
- **`CorpusDB`/`LiteratureRAG` module-level singleton thread safety**: Known limitation for single-threaded CLI; R4 explicitly dismissed this as non-defect for target deployment.
- **`check_fabricated_citations` `\(\d{4}\)` pattern false positives**: The `\(\d{4}\)` pattern matches any 4-digit year in parentheses, including non-citation uses. This is intentional — the safeguard requires a DOI for any author-year style reference. By design.
- **`MeasurementPlanner` prerequisite formula**: `step_{i:02d}_{effects[i-1][0]}` for step `i` (0-indexed) correctly references the previous step whose ID is `step_{i:02d}_{...}` (since step IDs use `i+1` padding). Verified correct.
- **`LiteratureRAG._load_from_db` year=0 sentinel**: `c.year or 0` stores `None` as `0`; the NaN check `and year_raw` on load correctly converts `0` back to `None`. Correct roundtrip.
- **`find_authoritative_authors` cache with nested `LiteratureRecord`**: `model_dump()` serializes nested Pydantic models to dicts; `AuthorProfile(**dict)` reconstruction correctly coerces `recent_papers: list[dict]` back to `list[LiteratureRecord]` via Pydantic. No data loss.
- **`PersonaGuard` double opt-out check**: Redundant but correct double-check (once in `check_author_eligibility`, once in `guard()`). Harmless.
- **Loop A `rounds_completed`**: `current_round` is captured as `engine.state.iteration + 1` before the final `engine.step()`, so the returned value correctly reflects completed rounds for both success and failure paths.
- **`SweepSpec.step_size` div-by-zero**: `max(self.steps - 1, 1)` ensures denominator ≥ 1. No div-by-zero for any `steps` value including 0 or 1.
