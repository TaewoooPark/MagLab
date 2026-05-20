# Code Review R1-04 — literature / reviewer / lab domains

**Reviewer**: Claude Sonnet 4.6 (automated adversarial audit)
**Date**: 2026-05-19
**Scope**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Method**: Read-only static analysis + targeted `python -c` probes

---

## Verdict

**ISSUES FOUND**

---

## Findings

### F-01 — HIGH | `connectors.py` lines 247–263, 265–284, etc. | `@_with_backoff` is dead code on all connector fetch methods

**Defect**: Every API method decorated with `@_with_backoff()` also wraps its network call in a bare `except Exception` that swallows all exceptions and returns `None` (or `[]`). The backoff wrapper catches exceptions raised by the wrapped function; because the inner handler never re-raises, the wrapper's retry logic can never trigger. The decorator is inert for:
- `OpenAlexConnector.fetch_by_doi`, `.search`, `.fetch_top_authors_by_topic`, `.get_venue_metrics`
- `SemanticScholarConnector.fetch_by_doi`, `.search`, `.fetch_author_papers`
- `ArXivConnector.search`, `.fetch_by_arxiv_id`
- `CrossRefConnector.fetch_by_doi`
- `find_authoritative_authors` in `authors.py`

**Impact**: Transient HTTP 429 / 503 failures are silently returned as `None`/`[]` with no retry. The claimed exponential-backoff protection does not operate.

**Fix**: Either move the exception handling to the caller side (let the decorated function raise), or call `time.sleep` / retry internally, or change the inner catch to re-raise retriable errors (e.g. `requests.exceptions.HTTPError` with status 429/5xx) and only suppress non-retriable ones.

---

### F-02 — HIGH | `reviewer/disclosure.py:314–324` | `check_fabricated_citations` does not normalize DOI case before set lookup → systematic false positives

**Defect**: `_DOI_RE` extracts DOIs from review text preserving their original case (e.g. `10.1103/PhysRevLett.132.156801`). The verified set (`verified_dois`) is built from `CorpusChunk.doi` strings which are stored in lowercase by connectors. The membership check `if clean not in verified_dois` is case-sensitive: a correctly-cited mixed-case DOI that exists in the verified set under its lowercase form is flagged as `FABRICATED_CITATION`.

```python
# current (line 315-318):
for doi in dois_found:
    clean = doi.rstrip(".,;")
    if clean not in verified_dois:  # case-sensitive!
```

**Proven** by probe: `'10.1103/PhysRevLett.132.156801' not in {'10.1103/physrevlett.132.156801'}` → `True` → spurious violation.

**Fix**: Normalize before comparison: `if clean.lower() not in {d.lower() for d in verified_dois}` (or pre-normalize `verified_dois` at construction time).

---

### F-03 — HIGH | `literature/rag.py:448–475` | LanceDB persistence is write-only — `_chunks` in-memory state is lost on process restart

**Defect**: `LiteratureRAG` accumulates chunks in `self._chunks` (a plain Python list). `_persist_chunks` writes to LanceDB but there is no corresponding read-back method. Both `_vector_search` (line 376–390) and BM25 are driven exclusively from `self._chunks`. After a process restart `self._chunks` is empty, so `search()` immediately returns `[]` regardless of what was persisted to LanceDB. The LanceDB write (`tbl.add(...)`) produces data that is never consumed.

**Fix**: Add a `_load_from_db()` method called in `__init__` (or lazily on first search) that queries the LanceDB table and repopulates `self._chunks`. Until then, the LanceDB dependency can be removed to avoid the misleading write.

---

### F-04 — HIGH | `reviewer/panel.py:267` | Dummy score always returned even when `llm_review_fn` is provided

**Defect**: In `_review_single`, when `llm_review_fn` is not `None`, `raw_review` is correctly populated from the LLM. However, the score is unconditionally set to a dummy value:

```python
# line 267 — always executed regardless of llm_fn:
score = self._make_dummy_score(persona)
validation_errors = score.validate(self._rubric)
```

When an `llm_review_fn` is wired in production, `PersonaReview.score` always contains hardcoded values (6.0/7.0/6.0/7.0/6.5) and `validation_errors` is meaningless. Callers (e.g. `MetaReviewer.synthesize`) receive incorrect scores, causing wrong recommendations.

**Fix**: Parse the structured score from the LLM output when `llm_fn` is provided, or at minimum require `llm_review_fn` to return `(review_text, ReviewScore)` instead of only text.

---

### F-05 — MEDIUM | `literature/keywords.py:316–380` | `merge_keyword_scores` produces duplicate `WeightedKeyword` entries for the same concept in different cases

**Defect**: `_normalize_scores` preserves the original keyword string as the dict key. `all_keywords` is built from these original-case keys. The normalization (`_normalize_keyword`) is applied only when constructing the output `WeightedKeyword`, not during deduplication. Two source strings that normalize to the same keyword — e.g. `"Spin Hall Effect"` (from TF-IDF) and `"spin hall effect"` (from KeyBERT) — produce two `WeightedKeyword(keyword="spin hall effect", ...)` objects in the output list. Substring suppression does not catch this because `candidate.keyword == kept.keyword` → the second is not "dominated" and both survive.

**Proven** by probe: `all_keywords = {'spin hall effect', 'Spin Hall Effect'}` → two iterations → two identical `WeightedKeyword.keyword` values.

**Fix**: Build `all_keywords` by iterating the union of normalized keyword strings and accumulating scores from all source dicts; or deduplicate the `results` list by normalized keyword before substring suppression.

---

### F-06 — MEDIUM | `reviewer/disclosure.py:292–326` | arXiv IDs in review text are never validated against `verified_dois`

**Defect**: When `verified_dois` is provided, `check_fabricated_citations` validates that every DOI found in the text (`dois_found`) is in the verified set — but `arxivs_found` is used only to determine whether *any* reference exists (to avoid the "citation with no ID" violation). arXiv IDs are never individually checked against `verified_dois`. A persona reviewer that invents an arXiv ID not in the corpus will pass safeguard ③.

**Impact**: Integrity violation — fabricated arXiv citations bypass the no-fabrication safeguard.

**Fix**: When `verified_dois` is provided, iterate `arxivs_found` and flag any arXiv ID not in the verified set (after stripping the `arXiv:` prefix if needed, or maintaining a parallel `verified_arxivs` set).

---

### F-07 — MEDIUM | `lab/planning/state.py:82–84` | `conditions_array` freezes column set to first measured point's keys

**Defect**:
```python
# line 82-84:
keys = sorted(self.measured_points[0].conditions.keys())
rows = [[p.conditions.get(k, 0.0) for k in keys] for p in self.measured_points]
```
If any measured point added after the first contains additional condition parameters (e.g. the active-learning loop introduces temperature after initial field sweeps), those dimensions are silently dropped to `0.0`. The returned array has wrong shape, causing `Theorist.fit` and `_compute_variance_reduction` to operate in a reduced and incorrect feature space.

**Fix**: Compute `keys` as the union of all condition key sets: `keys = sorted(set().union(*(p.conditions.keys() for p in self.measured_points)))`.

---

### F-08 — LOW | `literature/connectors.py:100–145` | Cache connection leaks on TTL-expired entries; stale rows accumulate unboundedly

**Defect**: `_cache_get` opens a new SQLite connection each call and closes it after the query. When a cached entry exists but is past its TTL, the function returns `None` without deleting the stale row. Over time, the cache table accumulates expired rows that are never pruned, growing without bound.

**Note**: Connection handling is correct (explicit `conn.close()` on happy path; swallowed exceptions avoid leak on error path). The issue is only stale-data accumulation.

**Fix**: Add `conn.execute("DELETE FROM literature_cache WHERE key = ?", (key,))` before returning `None` on TTL expiry, or run a periodic `DELETE WHERE cached_at < ?` cleanup.

---

### F-09 — LOW | `literature/authors.py:129–133` | `_name_similar` returns `True` for any empty author name

**Defect**:
```python
def _name_similar(a: str, b: str) -> bool:
    a_parts = set(a.lower().split())
    b_parts = set(b.lower().split())
    return len(a_parts & b_parts) >= min(2, len(a_parts))
```
When `a = ""`: `a_parts = set()`, `min(2, 0) = 0`, `len(set() & b_parts) = 0 >= 0` → `True`. An empty `profile.name` matches *any* S2 candidate, overwriting the profile's `h_index` and `s2_id` with incorrect data.

**Mitigated** by: `find_authoritative_authors` guards with `if enrich_s2 and profile.name:` before calling `_enrich_with_s2`. The function `_name_similar` itself remains logically broken and dangerous if called elsewhere.

**Fix**: Add an early guard: `if not a_parts or not b_parts: return False`.

---

### F-10 — LOW | `literature/corpus.py:141–145` | `CorpusDB.get_by_doi` may fail to find records whose DOI was stored with a URL prefix

**Defect**: `get_by_doi` normalizes the query DOI (strips `https://doi.org/` prefix, lowercases) then queries `WHERE doi = ?`. The `doi` column stores `record.doi` verbatim. Connectors like `OpenAlexConnector` strip the prefix before storing, but a `LiteratureRecord` constructed directly with `doi="https://doi.org/10.xxx"` stores the prefixed form. The normalized lookup then finds no match even though the record exists, silently returning `None`.

**Fix**: Either normalize `record.doi` at `LiteratureRecord` construction time (via a Pydantic validator), or query with `WHERE LOWER(REPLACE(doi, 'https://doi.org/', '')) = ?`.

---

## Non-Issues (investigated and cleared)

- **graph.py `path_search` `break`**: In BFS, once a dequeued path exceeds `max_depth`, all remaining queue entries are at least as long (BFS processes depth-monotonically). The `break` is correct.
- **Contradiction detection sign handling**: `rel_diff = |a−b| / max(|a|, |b|)` correctly handles opposite-sign values (produces rel_diff up to 2.0, which exceeds the 0.5 threshold). The docstring field description "relative difference" is slightly imprecise but the logic is sound.
- **Disclosure label regex**: `_DISCLOSURE_LABEL_RE` reliably matches the output of `build_disclosure_label`. `add_disclosure` + `guard` chain is safe.
- **`auto_draft.py` ternary**: `for k, v in (params.items() if isinstance(params, dict) else {}.items())` is valid Python; silent empty iteration on non-dict is intentional defensive behavior.
- **`_with_backoff` on `find_authoritative_authors`**: The decorator is equally inert (inner catch swallows), but this function is classified under F-01.
