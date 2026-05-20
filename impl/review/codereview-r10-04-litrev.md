# Code Review R10 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 10 (post-R9-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND** — 1 finding, max severity LOW.

---

## R9 Fix Verification

### R9 F-01: `ELNEntry.from_markdown()` list-field regex — CONFIRMED FIXED

`entry.py:178` now uses:

```python
items = re.findall(r'"([^"]*)"', raw)
```

This replaces the naive `raw.split(",")` from R8. The `re.findall` approach extracts all content between double-quote pairs, correctly handling commas inside quoted values (e.g., `"spin-orbit, coupling"`). Verified: `to_markdown()` always serialises list items as double-quoted strings, so this approach is exact for the CLI-generated output.

### R9 F-02: `LiteratureRAG.add_document()` idempotency guard — CONFIRMED FIXED

`rag.py:288–291` now contains:

```python
existing_doc_ids = {c.doc_id for c in self._chunks}
if doc_id in existing_doc_ids:
    log.debug("Document already indexed, skipping: %s", doc_id)
    return 0
```

The docstring at lines 278–287 correctly documents the idempotency contract. The guard prevents duplicate chunks in both in-memory state and LanceDB across multiple sessions.

### R9 F-03: `CorpusRAG.search()` BM25 candidate pool widening — CONFIRMED FIXED

`corpus_rag.py:265–266` now contains:

```python
bm25_pool = len(self._bm25._pending) if allowed_ids is not None else top_k * 2
bm25_results = self._bm25.search(query, top_k=max(bm25_pool, top_k * 2))
```

When `allowed_ids` is set (author-scope search), the BM25 candidate pool is widened to the total number of indexed chunks, ensuring all author chunks are reachable before filtering. The comment at lines 258–264 correctly explains the design rationale.

---

## Findings

### F-01 — LOW | `maglab/lab/notebook/entry.py:93–96`

**Defect**: `ELNEntry.to_markdown()` serialises list fields without escaping embedded double-quote characters in values. `from_markdown()` then uses `re.findall(r'"([^"]*)"', raw)` which treats every `"` as a delimiter. If a tag (or datapoint ID, or provenance entity ID) contains a literal double-quote character, both the serialised frontmatter and the parsed result are silently corrupted.

**Trace**:
- `self.tags = ['say "hi"', 'AHE']`
- `to_markdown()` line 95: `tags_str = ', '.join(f'"{t}"' for t in self.tags)` produces `'"say "hi"", "AHE"'`
- Frontmatter line: `tags: ["say "hi"", "AHE"]`  ← inner quotes unescaped
- `from_markdown()` line 178: `re.findall(r'"([^"]*)"', raw)` on `'say "hi"", "AHE"'`
- Matches: `['say ', 'hi', '', 'AHE']` — **4 items** instead of 2; `"say "hi""` is split at inner quotes.

**Impact**: Round-trip fidelity breaks for any list field value containing a double-quote character. The auto-draft workflow (`draft_from_fit_result`) generates tags from effect registry keys (`'auto-draft'`, `'fitting'`, `'sot_harmonic_hall'`) which never contain double-quotes. Direct API callers who supply pathological tags (e.g., from raw user input containing quotes) would silently corrupt the entry on the next load. No data loss in the default CLI workflow; defect only triggers with unusual user-supplied input.

**Concrete fix**: Escape double-quotes when serialising list fields in `to_markdown()`:

```python
# In to_markdown():
def _escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')

tags_str = ", ".join(f'"{_escape(t)}"' for t in self.tags)
dp_ids_str = ", ".join(f'"{_escape(d)}"' for d in self.datapoint_ids)
prov_ids_str = ", ".join(f'"{_escape(p)}"' for p in self.provenance_entity_ids)
```

And update `from_markdown()` to unescape after extraction:

```python
items = [s.replace('\\"', '"').replace('\\\\', '\\') for s in re.findall(r'"((?:[^"\\]|\\.)*)"', raw)]
```

Or use the `csv` module's `reader` which handles standard CSV quoting automatically.

---

## Non-Findings

- **R9 F-01 re.findall regex**: Confirmed correct for all values without embedded double-quotes. The auto-draft and normal CLI workflow never produce double-quotes in tags, datapoint IDs, or provenance entity IDs. The remaining defect (F-01 above) is limited to the `to_markdown()` side not escaping — a separate, narrower issue.

- **R9 F-02 idempotency guard**: Confirmed correct. The set comprehension `{c.doc_id for c in self._chunks}` correctly checks before any append or persist.

- **R9 F-03 BM25 pool widening**: Confirmed correct. `len(self._bm25._pending)` is a valid proxy for the total number of chunks in the BM25 index (since `_pending` accumulates all chunks since the last rebuild and `_rebuild_if_dirty()` creates a fresh index from the full `_pending` list).

- **`_CorpusBM25Index._pending` private attribute access from `CorpusRAG`**: Both classes are defined in the same file (`corpus_rag.py`). Accessing `self._bm25._pending` from `CorpusRAG` is intra-module access, not a cross-module encapsulation violation. Accepted.

- **`CorpusRAG.add_chunk()` duplicate `chunk_id` — `_author_chunks` append without dedup guard**: If `add_chunk()` is called twice with the same `chunk_id`, `self._author_chunks[author_id]` gets a duplicate entry, and `_bm25._pending` accumulates a duplicate text. The main `search()` path is unaffected because `allowed_ids = set(cids)` deduplicates before filtering. Only `author_chunk_count()` would return an inflated count. The typical workflow (per-session fresh `CorpusRAG()` in `loop_a.py`) never calls `add_chunk()` twice for the same chunk. Not flagged as a finding at this severity.

- **`graph.py:report_property()` self-loop `contradicts` edge for two DOI-less, title-less papers**: Both produce `node_id = 'paper:noid-{md5("")[:12]}'` = `'paper:noid-d41d8cd98f00'`. The edge's `source_id == target_id`. This is semantically a self-contradiction but only reachable when `report_property()` is called with `doi=""` and `title=""` for two different numerical values. No CLI path produces this combination; all four connectors populate at least a title. Dismissed.

- **`graph.py:path_search()` `break` exits full BFS queue prematurely**: In a BFS (FIFO queue), all paths of length ≤ k are fully processed before any path of length k+1 is dequeued. The `break` at `len(path) > max_depth` therefore only triggers after all valid-depth paths have been explored. Correct behavior confirmed by trace.

- **`_with_backoff` retries only retriable exceptions**: Inner connector methods catch non-retriable exceptions internally and return `None`/`[]`. Only retriable exceptions escape via `raise`, causing the decorator to retry. Non-retriable exceptions return `None` on the first attempt without retry loops. Control flow is correct.

- **`LiteratureRAG._rrf_fusion()` with empty vector or BM25 results**: `v_max = max(..., default=1.0) or 1.0` correctly handles empty result sets. Missing-rank penalty `len(results) + k` is correct RRF convention. Confirmed correct.

- **`CorpusDB.search()` LIKE injection with `%` and `_` wildcards**: User-supplied `author`, `venue`, and `query` strings are passed as `%{value}%` LIKE parameters. Additional `%` or `_` in user input produce false positives (over-matching) but no data corruption or SQL injection. For a single-user CLI, acceptable.

- **`LiteratureRecord.dedup_key()` collision for empty `doi` and `title`**: Returns `'title:'` (degenerate key). A second empty-title, empty-DOI record would be silently rejected by `CorpusDB.add()`. All four API connectors populate at least a title from real API data; this collision only occurs via direct API calls with default `LiteratureRecord()`. Not flagged.

- **`draft_from_fit_result()` double-save**: `create_entry()` saves the entry internally, then `save_entry(entry)` saves it again after the title override. The second save overwrites the first. The final file is always correct. The wasted I/O is a minor inefficiency, not a correctness defect.

- **`loop_a.py` empty `CorpusRAG`**: `rag = CorpusRAG()` is created empty at line 167; the comment acknowledges the corpus is not populated from `personas.verified_dois`. The code correctly degrades to BM25-only with no results (search returns `[]`). This is a documented design gap, not a hidden bug.

- **`_fetch_retraction_status_from_oa()` no retry on transient errors**: A transient network failure caches `status='unknown'` for 7 days. `'unknown'` does not block, so safety is preserved (a retracted paper would require an actual `'retracted'` status from OpenAlex). Design tradeoff, not a code bug.

- **`MetaReviewer.synthesize()` division-by-zero guards**: `statistics.mean(values)` is guarded by `if values else 0.0`. All divisions are protected. Confirmed correct.

- **`PersonaGuard.guard()` double `check_optout()` call**: `check_author_eligibility()` at line 216 and `check_optout()` inside `guard()` at line 543 both check the same condition. Double-check is redundant but harmless; the first call raises before `guard()` runs if opted out, so the second call in `guard()` can never add a new `OPTED_OUT_AUTHOR` violation.

- **`_OPTOUT_REGISTRY` module-level singleton**: Loaded from disk at import time. In a single-user CLI context, there is no concurrent modification risk. Multi-process scenarios are outside the design target. Accepted.

- **`ELNNotebook.list_entries()` exception swallowing**: `except Exception: continue` silently skips malformed or unreadable files during search. No data is lost (files on disk remain). Acceptable for a search function.

- **`MeasurementPlanner.plan()` prerequisites index**: At step `i`, `prerequisites = [f'step_{i:02d}_{effects[i-1][0]}']` correctly references the immediately preceding step (step_id format is `step_{i+1:02d}_...`, so `i:02d` for the prerequisite matches the `(i+1-1):02d = i:02d` format of the previous step). Verified by simulation. Correct.
