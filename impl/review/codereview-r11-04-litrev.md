# Code Review R11 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 11 (post-R10-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND** — 1 finding, max severity LOW.

---

## R10 Fix Verification

### R10 F-01: `ELNEntry` list-field serialization — CONFIRMED FIXED

`entry.py:94–117` (`to_markdown()`) now serializes all three list fields using `json.dumps`:

```python
f"tags: {json.dumps(self.tags)}\n"
f"datapoints: {json.dumps(self.datapoint_ids)}\n"
f"provenance_entities: {json.dumps(self.provenance_entity_ids)}\n"
```

`from_markdown():163–171` parses them back with `json.loads` via the regex `rf"^{key}:\s*(\[.*\])\s*$"` which captures the full JSON array from a single frontmatter line. The `json.dumps` output is guaranteed to be single-line (no `indent` argument), so the single-line regex is correct. `json.loads` then correctly round-trips double-quotes, backslashes, commas, brackets, and unicode. Verified by manual test against representative values:

- `json.dumps(['tag[bracket]', 'hello'])` → `'["tag[bracket]", "hello"]'` → regex captures → `json.loads` → `['tag[bracket]', 'hello']` ✓
- `json.dumps(['path\\to\\file'])` → `'["path\\\\to\\\\file"]'` → `json.loads` → `['path\\to\\file']` ✓

The R10 F-01 defect (double-quote values corrupted by `re.findall`) is fully resolved. The R10 non-finding about further escaping (R9-era escape-in-value concern) is also correctly addressed: `json.dumps` handles all embedded quote and backslash cases automatically.

---

## Findings

### F-01 — LOW | `maglab/lab/notebook/entry.py:106–107, 141–143`

**Defect**: `ELNEntry.to_markdown()` serializes the `sample` and `instrument` scalar fields without escaping embedded double-quote characters:

```python
f'sample: "{self.sample}"\n'
f'instrument: "{self.instrument}"\n'
```

`from_markdown()` then parses them back with `v.strip('"')`:

```python
entry.sample = v.strip('"')
entry.instrument = v.strip('"')
```

`str.strip(chars)` removes **all** leading and trailing occurrences of characters in the `chars` argument from both ends of the string. This causes two failure modes:

**Failure mode A — unescaped internal quotes break the frontmatter line:**
- `self.sample = 'Sample "A"'`
- Serialized: `sample: "Sample "A""`
- `_extract()` regex `r'^sample:\s*(.+)$'` captures `'"Sample "A""'`
- `strip('"')` → `'Sample "A'` (last char dropped)

**Failure mode B — sample/instrument starting or ending with a quote character:**
- `self.sample = '"quoted"'` (name that is itself a quoted string)
- Serialized: `sample: ""quoted""`
- `strip('"')` → `'quoted'` (surrounding quotes silently dropped)

**Trace for the concrete failing case:**

```python
sample = 'hello"'               # value ends with a double-quote
# to_markdown() line 106:
line = f'sample: "{sample}"'   # → 'sample: "hello""'
# from_markdown() _extract():
v = '"hello""'                  # .strip() of the line captured by regex
# line 141:
result = v.strip('"')           # → 'hello'   ← BUG: trailing quote dropped
# sample == result → False
```

**Impact**: Round-trip fidelity breaks for `sample` and `instrument` field values that contain or end with a double-quote character. In the default auto-draft and CLI workflow, sample IDs use magnetism stack notation (`Ta(5)/CoFeB(1)/MgO(2)`, `Pt/Co/AlOx`) which never contain double-quotes. Researchers using the API directly with sample names that include quoted strings (e.g., `'"Batch 1"'`, `'Label "A"'`) would experience silent data corruption on the next read.

This is the scalar-field analogue of the R10 F-01 list-field defect (which has been fixed). The list fields were upgraded to `json.dumps`/`json.loads`; the scalar fields were not.

**Concrete fix**: Serialize sample and instrument as JSON strings (which handles embedded quotes and backslashes automatically):

```python
# In to_markdown():
f"sample: {json.dumps(self.sample)}\n"
f"instrument: {json.dumps(self.instrument)}\n"
```

And parse back with `json.loads` instead of `strip`:

```python
# In from_markdown():
if v := _extract("sample"):
    with contextlib.suppress((json.JSONDecodeError, ValueError)):
        entry.sample = json.loads(v)
if v := _extract("instrument"):
    with contextlib.suppress((json.JSONDecodeError, ValueError)):
        entry.instrument = json.loads(v)
```

This is exactly the same approach used for the list fields after the R10 fix.

---

## Non-Findings

- **R10 F-01 JSON round-trip for list fields**: Confirmed fully fixed and correct for all value contents including embedded quotes, backslashes, brackets, unicode, and commas. `json.dumps` output is always single-line; the single-line `\[.*\]` regex in `from_markdown()` is correct.

- **`sample`/`instrument` normal-workflow impact**: Standard physics stack notation (`Ta(5)/CoFeB(1)/MgO(2)`) and instrument names (`Lock-in amplifier`, `VNA`) never contain double-quotes. The defect (F-01) is LOW severity: it only triggers on unusual user-supplied values containing double-quotes.

- **`ELNNotebook.list_entries()` exception swallowing**: `except Exception: continue` silently skips malformed files during search. No data is lost on disk. Acceptable for a search function.

- **`draft_from_fit_result()` double-save**: `create_entry()` saves internally, then `save_entry()` overwrites with the title update. Final file is always correct; the wasted I/O is a minor inefficiency, not a correctness defect.

- **`graph.py:path_search()` `break` exits BFS queue prematurely**: Traced carefully. In BFS (FIFO queue), all paths of length k are dequeued before any path of length k+1. When the first path of length `max_depth + 1` is dequeued, all remaining queued paths also have length ≥ `max_depth + 1`. The `break` is therefore correct.

- **`graph.py:report_property()` NaN/inf in stored property values**: `nan >= CONTRADICTION_THRESHOLD` evaluates to `False` in Python, so NaN rel-diff silently skips contradiction detection. No crash or data corruption; benign for a physics lab workflow.

- **`graph.py:report_property()` self-loop `contradicts` edge for two DOI-less, title-less papers**: Both produce the same `node_id = 'paper:noid-d41d8cd98f00'`. The edge `source_id == target_id` is stored but represents a degenerate case. No CLI path reaches this; all four connectors populate at least a title. Dismissed.

- **`CorpusDB` / `KnowledgeGraph` / `EvidenceMatrix` persistent connections not closed**: All three expose `close()` but use a singleton pattern without a context manager. SQLite connections survive process exit gracefully in a single-user CLI. Acceptable design choice.

- **`CorpusDB.get_by_doi()` triple-REPLACE SQL**: The nested `REPLACE(REPLACE(REPLACE(doi, 'https://doi.org/', ''), 'http://doi.org/', ''), 'doi:', ''))` correctly normalizes all stored DOI prefix forms before comparison. Consistent with `update_retraction_status()`. Correct.

- **`LiteratureRecord.dedup_key()` `doi:` prefix**: The `doi:` in the returned string `f"doi:{normalized_doi}"` is a key namespace label, not a DOI prefix. It is distinct from the `doi:` DOI prefix stripped by `normalized_doi()`. Semantically correct.

- **`_with_backoff()` retries ALL exceptions, not only retriable ones**: The inner connector methods catch non-retriable exceptions internally and return `None`/`[]`; only retriable exceptions are re-raised to `_with_backoff`. The decorator therefore only retries retriable exceptions in practice. After `max_retries`, it raises `RuntimeError`, which `fetch_by_doi_multi()` catches. Correct.

- **`CorpusRAG.add_chunk()` duplicate `chunk_id` — no dedup guard in `_author_chunks`**: If called twice with the same `chunk_id`, `_author_chunks[author_id]` gets a duplicate entry. `author_chunk_count()` would return an inflated count. The main `search()` path deduplicates via `allowed_ids = set(cids)` before filtering. Per-session fresh `CorpusRAG()` in `loop_a.py` never calls `add_chunk()` twice for the same chunk. Dismissed as a pre-existing non-finding.

- **`CorpusRAG` BM25 pool widening (`_bm25._pending`)**: Confirmed correct. `len(self._bm25._pending)` is the total number of accumulated chunk entries (used as pool size when author-scoping). The `_rebuild_if_dirty()` method builds the index from the full `_pending` list. The pool-widening logic ensures all author chunks are reachable before filtering.

- **`MetaReviewer.synthesize()` division-by-zero guards**: `statistics.mean(values)` is only called when `values` is non-empty. All divisions are protected by explicit guards. Confirmed correct.

- **`MeasurementPlanner.plan()` prerequisites index**: For step `i`, `step_id = f'step_{i+1:02d}_{effect}'` and `prerequisites = [f'step_{i:02d}_{effects[i-1][0]}']`. At `i=1`: prerequisite = `'step_01_{effects[0][0]}'` which matches `step_id` of `i=0`. Verified by simulation. Correct.

- **`PersonaGuard.guard()` double `check_optout()` call**: `check_author_eligibility()` at the `panel.py` call site raises before `guard()` if opted out, making the second `check_optout()` inside `guard()` unreachable after a true opt-out. Redundant but harmless.

- **`check_fabricated_citations()` arXiv version suffix handling**: `_ARXIV_RE` matches `arXiv:NNNN.NNNNN` without the version suffix (`v2`). Both serialization and lookup strip the suffix consistently, so validation is consistent within the system.

- **`ELNEntry.from_markdown()` multiline JSON arrays**: `json.dumps` always produces a single-line string (no `indent` argument), so the single-line regex `\[.*\]` with `re.MULTILINE` and default `re.DOTALL=False` correctly captures the entire array. Confirmed by test.

- **`_name_similar()` empty name guard**: Returns `False` immediately when either name is empty (fixed in prior rounds). Confirmed present at `authors.py:136–140`.

- **`Theorist._simple_linear_fit()` denominator**: Uses `np.std(x) < 1e-9` guard before `np.cov/np.var` division. `valid.sum() < 2` guard prevents single-point calls. Correct.

- **`LiteratureRAG._load_from_db()` NaN year handling**: `year_raw != year_raw` is the correct IEEE 754 NaN identity test. Converts valid years to `int`, assigns `None` otherwise. Correct.
