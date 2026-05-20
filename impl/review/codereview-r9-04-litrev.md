# Code Review R9 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 9 (post-R8-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND** — 3 findings, max severity LOW.

---

## R8 Fix Verification

### R8 F-01: `from_markdown()` list-field regex — CONFIRMED FIXED

`entry.py:171` now uses:

```python
m2 = re.search(rf"^{key}:\s*\[(.+?)\]\s*$", fm_text, re.MULTILINE)
```

The non-greedy `(.+?)` combined with the end-of-line anchor `\s*$` correctly captures the full bracketed content regardless of `]` characters inside values (e.g., `"sample[A]"`, `"sot[run1]"`). Verified by manual simulation: `tags: ["spin]hall", "CoFeB", "sample[A]"]` correctly parses to `['spin]hall', 'CoFeB', 'sample[A]']`.

### R8 F-02: `from_markdown()` `created_at` parsing — CONFIRMED FIXED

`entry.py:146–148` now includes:

```python
if v := _extract("created_at"):
    with contextlib.suppress(ValueError):
        entry.created_at = datetime.fromisoformat(v)
```

The fix correctly parses `created_at` via `datetime.fromisoformat()` with graceful fallback (leaving the default `datetime.now()`) on missing or malformed values. Confirmed present and correct.

---

## Findings

### F-01 — LOW | `maglab/lab/notebook/entry.py:174`

**Defect**: `ELNEntry.from_markdown()` parses list fields (`tags`, `datapoints`, `provenance_entities`) by splitting the captured content on `,`:

```python
items = [i.strip().strip('"') for i in raw.split(",") if i.strip()]
```

This is correct for simple values but breaks when a list item value itself contains a comma. The R8 fix corrected the `]`-truncation problem by using a non-greedy end-of-line-anchored regex, but the downstream comma-split remains naive.

**Trace**:
- `to_markdown()` writes: `tags: ["spin-orbit, coupling", "AHE"]`
- `from_markdown()` non-greedy regex correctly captures `raw = '"spin-orbit, coupling", "AHE"'`
- `raw.split(",")` splits on ALL commas: `['"spin-orbit', ' coupling"', ' "AHE"']`
- After strip: `['spin-orbit', 'coupling', 'AHE']` — **3 items** instead of 2; `"spin-orbit, coupling"` is silently split into two fragments.

**Impact**: Round-trip fidelity breaks for any tag, datapoint ID, or provenance entity ID containing a comma. The auto-generated paths (`draft_from_fit_result`, `MeasurementPlanner`) never produce commas in these fields (effect names, UUIDs), so the default CLI workflow is safe. The defect only triggers when a caller passes user-supplied tags containing commas directly to `create_entry()`.

**Concrete fix**: Replace the naive `split(",")` with Python's `csv` module (handles quoted commas) or a regex that respects quoted strings:

```python
import csv
items = list(csv.reader([raw]))[0]
items = [i.strip().strip('"') for i in items if i.strip()]
```

Or with a regex:
```python
items = re.findall(r'"([^"]*)"', raw)
```
The `re.findall(r'"([^"]*)"', raw)` approach captures everything between double quotes, which is exactly what `to_markdown()` writes, and handles commas inside values correctly.

---

### F-02 — LOW | `maglab/literature/rag.py:304–307`

**Defect**: `LiteratureRAG.add_document()` has no idempotency check. Every call to `add_document()` for the same `doc_id` unconditionally appends new chunks to `self._chunks` (line 304: `self._chunks.extend(new_chunks)`) and persists them to LanceDB (line 305: `self._persist_chunks(new_chunks)`). Because `_load_from_db()` is called at `__init__` and loads ALL rows from LanceDB unconditionally, each new process restart then loads the previously persisted chunks before any new `add_document()` call duplicates them again.

**Trace**:
1. Session 1: `rag.add_document(text, doc_id="doi:10.1/x", ...)` → 8 chunks added, persisted to LanceDB.
2. Session 2: new `LiteratureRAG()` → `_load_from_db()` loads 8 existing chunks into `self._chunks`.
3. Session 2: `rag.add_document(text, doc_id="doi:10.1/x", ...)` called again → 8 MORE chunks appended to `self._chunks` (now 16) and ANOTHER 8 rows appended to LanceDB (now 16 rows total).
4. BM25 rebuilds on 16 chunks (8 duplicates), double-weighting this document.
5. Vector search returns the same chunk at ranks #1 and #2 after enough re-indexing.

**Impact**: Over multiple sessions with repeated indexing, RAG search result quality degrades: the most frequently re-indexed documents are disproportionately weighted, and the top-k results may be filled by duplicate chunks from the same document. The in-memory state also grows unboundedly. There is no data loss or corruption, only quality degradation.

**Concrete fix**: Check for existing `doc_id` before persisting, or use `chunk_id` as a unique key in LanceDB and use `INSERT OR IGNORE` semantics:

```python
# At the start of add_document():
existing_ids = {c.doc_id for c in self._chunks}
if doc_id in existing_ids:
    log.debug("Document already indexed, skipping: %s", doc_id)
    return 0
```

Alternatively, enforce chunk uniqueness at the LanceDB schema level by checking existing `chunk_id` values before adding.

---

### F-03 — LOW | `maglab/reviewer/corpus_rag.py:258–261`

**Defect**: `CorpusRAG.search()` performs BM25 search over the **entire corpus** and then filters results to the requested `author_id` (post-filter), while vector search correctly **pre-filters** by `allowed_ids` before computing similarities.

```python
# BM25 path: global search, then filter (may miss author-specific chunks)
bm25_results = self._bm25.search(query, top_k=top_k * 2)
if allowed_ids is not None:
    bm25_results = [(cid, s) for cid, s in bm25_results if cid in allowed_ids]

# Vector path: pre-filtered correctly (line 275)
sims = self._cosine_similarities(q_vec, allowed_ids)
```

**Trace**: Suppose the corpus has 1000 chunks (200 authors × 5 each). A query with `author_id="Smith"` (5 chunks) requests `top_k=5`. BM25 returns top `top_k*2=10` from all 1000 chunks. If Smith's 5 chunks are ranked 11–15 by BM25 globally (plausible in a large corpus with many strong matches from other authors), they are filtered out. `bm25_results` is empty after filtering. The RRF fusion has no BM25 contribution for Smith, and results are vector-only. The vector search, however, correctly pre-filters to Smith's 5 chunks and returns them all.

**Impact**: In a small corpus (typical reviewer workflow with 10–30 authors), BM25 top-10 almost certainly includes the author's chunks. The defect manifests at scale. For the current design (reviewer uses a small per-session corpus built from a few authors), this is low severity. However, the design intent ("per-author namespaces") is not correctly honoured by the BM25 path.

**Concrete fix**: Pre-filter BM25 candidates to the author's chunk IDs before scoring, or build per-author BM25 sub-indexes:

```python
if allowed_ids is not None:
    # Build a temporary BM25 index from author-filtered chunks only
    author_chunks = [c for c in self._chunks.values() if c.chunk_id in allowed_ids]
    # ... search on this subset
else:
    bm25_results = self._bm25.search(query, top_k=top_k * 2)
```

A simpler immediate fix is to increase the BM25 search breadth: `top_k=len(self._chunks)` when `allowed_ids` is set, ensuring all author chunks are reachable.

---

## Non-Findings

- **R8 F-01 regex fix**: Confirmed correct; the non-greedy `(.+?)\s*$` anchor works for `]`-containing values. See R8 Fix Verification above.
- **R8 F-02 `created_at` fix**: Confirmed correct; `datetime.fromisoformat()` with `contextlib.suppress(ValueError)` is present. See R8 Fix Verification above.
- **`_with_backoff` retries only retriable exceptions**: Non-retriable exceptions are caught inside each connector method's inner `except` block and return `None`/`[]` without being re-raised to the decorator. The decorator only retries exceptions that escape the inner handler (retriable ones re-raised by `if _is_retriable(exc): raise`). Control flow is correct.
- **`CorpusDB.search()` LIKE injection with `%` / `_`**: User-supplied `author`, `venue`, and `query` strings become LIKE `%{value}%` parameters. The `%` inserted by the code flanks the user value so additional `%` in user input produce over-matching (false positives) but not data corruption or SQL injection. The `_` wildcard causes false positives but not security issues. For a single-user CLI this is acceptable. (R8 confirmed for get_by_doi; extended analysis for search() confirms same verdict.)
- **`check_fabricated_citations()` arXiv ID case handling**: `re.sub(r"(?i)^arxiv:", "", arxiv_ref)` correctly handles all-caps prefix; comparison to `verified_arxivs_lower` is consistent.
- **`_DISCLOSURE_LABEL_RE` matching dummy review in panel.py**: `_dummy_review()` includes `[AI Reviewer — Corpus Model]`; the pattern matches on `AI Reviewer`. `add_disclosure()` correctly detects existing label and does not double-prepend.
- **`MetaReviewer.synthesize()` division-by-zero guards**: All divisions (mean, final_score) are guarded by `if values else 0.0` or equivalent. Correct.
- **`from_markdown()` body extraction `lstrip("\n")`**: `text[body_start:].lstrip("\n")` correctly skips blank lines between frontmatter end and the title/body. No truncation risk.
- **`ELNNotebook.list_entries()` rglob exception swallowing**: `except Exception: continue` silently skips malformed or unreadable files. Acceptable for a search function; errors are not propagated to the caller but no data is lost.
- **`_entry_path()` date-based filename with user-supplied entry_id**: Path traversal requires the attacker to have already written malicious `.md` files into the notebook directory; for a single-user local CLI there is no trust boundary violation.
- **`keywords.py merge_keyword_scores` substring suppression order**: The algorithm checks whether the candidate is a substring of any already-kept keyword, which is the correct direction for suppressing less-specific n-grams.
- **`select_precision()` with empty `affordable` list**: If no level is affordable, `ladder[0]` (cheapest) is returned correctly. The loop guard `if not affordable: return ladder[0]` handles this.
- **`StandardState.conditions_array()` missing condition keys filled with 0.0**: Intentional; the docstring documents this. Correct for the RBF variance reduction use case.
- **`Theorist._simple_linear_fit()` single-column conditions**: Falls back to intercept-only model when `conditions.shape[1] == 0`; this is an unreachable branch since `conditions_array()` always produces at least one column when `measured_points` is non-empty, but is a safe guard.
- **`LiteratureRAG._persist_chunks()` `year or 0`**: Stores `year=0` when `year` is `None` to avoid LanceDB `null` type issues; `_load_from_db()` converts `0` back to `None` via the NaN/falsy check. Round-trip is correct (0 is not a valid publication year).
- **`_CorpusBM25Index` rebuild wipes and replaces the underlying `_LiteratureBM25Index`**: The `_pending` list accumulates all chunks ever added; on `_rebuild_if_dirty()` it creates a fresh `_LiteratureBM25Index` from the full `_pending` list. Incremental additions are correctly included. No chunk loss.
- **`PersonaGuard.guard()` double `check_optout()` call**: Also called at the top of `_review_single()` via `check_author_eligibility()`. The double call is redundant but correct; the first call raises before `guard()` is reached if opted out. Harmless.
- **`report_property()` saves new value BEFORE checking for contradictions**: The `INSERT` at line 417 runs before the contradiction detection loop. This means the new value is immediately visible to future calls but does NOT affect the current call's contradiction check (which queries `existing` values fetched before the insert). Correct.
- **`EvidenceMatrix` and `KnowledgeGraph` no `__del__`**: SQLite connections closed by GC. Acceptable for a single-user CLI. Not a resource leak in practice.
