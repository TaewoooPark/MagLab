# Code Review R4 — Literature / Reviewer / Lab
**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 4 (post-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND**

---

## Findings

### F-01 — MEDIUM | `maglab/reviewer/panel.py:55` + `maglab/reviewer/disclosure.py:276`

**Defect**: `PersonaSpec.verified_dois` defaults to `set()` (empty set), not `None`. This causes safeguard ③ (`check_fabricated_citations`) to treat every `10.xxx` DOI found in a real LLM review text as a fabricated citation — because `verified_dois is not None` triggers per-DOI validation against an empty whitelist.

**Trace**:
- `PersonaSpec(author_id="x")` → `verified_dois = set()` (from `field(default_factory=set)`)
- `PersonaGuard.__init__(verified_dois=set())` → `self._verified_dois = set()`
- `guard.guard(review_text)` → `check_fabricated_citations(text, verified_dois=set(), …)`
- In `check_fabricated_citations`: `if verified_dois is not None:` → True for `set()`
- `verified_lower = {}` (empty)
- For every `10.xxx/...` DOI found in review text: `clean.lower() not in {}` → always `True`
- → `FABRICATED_CITATION` violation appended for every cited DOI

**Impact**: Any real LLM review that properly cites papers with DOIs (the expected behavior) would be blocked by `PersonaDisclosureError` when `verified_dois` is not explicitly populated from RAG results. The test suite avoids this by only using `arXiv` IDs (not `10.xxx` DOIs) in the `verified_dois=set()` test cases.

**Fix**: Change `PersonaSpec.verified_dois` default from `set()` to `None`:
```python
verified_dois: set[str] | None = None
verified_arxivs: set[str] | None = None
```
When `None`, `check_fabricated_citations` skips per-DOI whitelist validation (only checks presence), which is the correct lenient default before RAG results are populated. Alternatively, add a docstring warning that callers MUST populate `verified_dois` from RAG retrieval results before using a real LLM function.

---

### F-02 — LOW | `maglab/literature/graph.py:558-565`

**Defect**: `KnowledgeGraph.set_retraction_cache(doi, status)` normalizes `doi` with only `.lower()` — it does not strip the `https://doi.org/`, `http://doi.org/`, or `doi:` prefixes. `check_retraction()` (the reader) applies full three-prefix normalization. Consequently, calling `set_retraction_cache("https://doi.org/10.xxx/test", "retracted")` stores the key `"https://doi.org/10.xxx/test"` in the cache, but `check_retraction("https://doi.org/10.xxx/test")` looks up the normalized key `"10.xxx/test"` — a cache miss, causing an unnecessary OpenAlex re-fetch.

**Location**: `graph.py` lines 558–565.

**Current code**:
```python
def set_retraction_cache(self, doi: str, status: str) -> None:
    """For testing/manual use: set the retraction cache entry directly."""
    doi_norm = doi.lower()   # BUG: only lowercases, does not strip prefix
    self._conn.execute(
        "INSERT OR REPLACE INTO retraction_cache (doi, status, checked_at) VALUES (?,?,?)",
        (doi_norm, status, time.time()),
    )
```

**Impact**: Current test suite uses bare DOIs with `set_retraction_cache`, so tests pass. Manual use with prefixed DOIs (e.g. from user-facing APIs that accept full DOI URLs) would silently bypass the cache.

**Fix**: Apply the same three-prefix normalization used in `check_retraction`:
```python
doi_norm = (
    doi.lower()
    .replace("https://doi.org/", "")
    .replace("http://doi.org/", "")
    .replace("doi:", "")
)
```

---

### F-03 — LOW | `maglab/literature/corpus.py:212-229`

**Defect**: `CorpusDB.update_retraction_status(doi, status)` normalizes the input `doi` (strips prefix) but the SQL query uses `WHERE doi = ?` — a plain equality match. The companion method `get_by_doi` applies `REPLACE` inside the SQL to strip prefixes from the stored column value. This inconsistency means: if a `LiteratureRecord` was added with `doi="https://doi.org/10.xxx/test"` (user-created record with unprefixed DOI not yet stripped), `update_retraction_status("https://doi.org/10.xxx/test", "retracted")` normalizes to `"10.xxx/test"` and the `WHERE doi = '10.xxx/test'` predicate finds zero rows — the update silently no-ops.

**Location**: `corpus.py` lines 219–228.

**Impact**: Low in practice because all connectors (`OpenAlexConnector`, `SemanticScholarConnector`, `ArXivConnector`, `CrossRefConnector`) normalize DOIs at parse time before storing. Affects only manually constructed `LiteratureRecord(doi="https://doi.org/...")` objects. No return value or exception signals the silent failure.

**Fix**: Use `REPLACE` in the SQL the same way `get_by_doi` does:
```python
self._conn.execute(
    "UPDATE records SET retraction_status = ? "
    "WHERE LOWER(REPLACE(REPLACE(doi, 'https://doi.org/', ''), 'http://doi.org/', '')) = ?",
    (status, doi_norm),
)
```

---

## Non-Findings (reviewed and dismissed)

- **`_with_backoff` + `_is_retriable` interaction**: Retriable exceptions are correctly re-raised to the decorator which retries; non-retriable exceptions are caught and return safe defaults. No defect.
- **`_cache_get` falsy check (`if cached:`)**: Stored values are always dicts or lists, never bare integers. The `int(0)` falsy edge case is unreachable.
- **BFS `path_search` `break` on `len(path) > max_depth`**: Correct for BFS since all remaining queue entries have equal or greater depth at that point.
- **`_CorpusBM25Index._rebuild_if_dirty`**: Rebuilds from the full `_pending` list (not just new items), ensuring no data loss. Correct.
- **`CorpusRAG` DOI enforcement**: `add_chunk`/`add_chunks` correctly raise `ValueError` for chunks without DOI before any indexing occurs.
- **Loop A `rounds_completed`**: `engine.state.iteration` after the normal termination path correctly reflects completed rounds. Verified against `RalphEngine.step()` which increments before checking `max_iterations`.
- **`PersonaGuard.check_optout` called twice**: Redundant (once in `check_author_eligibility`, once in `guard()`), but harmless extra safety check.
- **`EvidenceMatrix` tier validation**: `_row_to_entry` uses `type: ignore[arg-type]` for the `tier` literal, which is valid since the DB schema constrains the value to `T1/T2/T3`.
- **`KnowledgeGraph.report_property` contradiction edges**: Distinct `edge_id` per (doi_a, doi_b, property_name) pair; DOI-less papers use MD5 hash fallback — correctly prevents collision.
- **`LiteratureRAG._load_from_db` ImportError**: Caught by the `except Exception` wrapper; gracefully degrades to memory-only mode. No resource leak.
- **Thread safety of module-level singletons** (`_default_corpus`, `_default_graph`, `_default_rag`): Expected limitation for single-threaded CLI use; no defect for the target deployment.
