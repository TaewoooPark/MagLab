# Code Review R12 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 12 (post-R11-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**CLEAN**

All 24 Python files across the three domains were audited. No genuine defects were found beyond the items investigated and dismissed below. The R11 fix is correctly in place.

---

## R11 Fix Verification

### R11 F-01: `ELNEntry` scalar-field serialization — CONFIRMED FIXED

`entry.py:108–109` (`to_markdown()`) now serializes `sample` and `instrument` using `json.dumps`:

```python
f"sample: {json.dumps(self.sample)}\n"
f"instrument: {json.dumps(self.instrument)}\n"
```

`from_markdown():142–151` parses them back with `json.loads`, with a graceful fallback to `v.strip('"')` for old-format compatibility:

```python
if v := _extract("sample"):
    try:
        entry.sample = json.loads(v)
    except (json.JSONDecodeError, ValueError):
        entry.sample = v.strip('"')
```

Verified by live execution of five round-trip tests:

- Normal value (`Ta(5)/CoFeB(1)/MgO(2)`) — correct
- Embedded double-quotes (`Sample "A"`) — correct (R11 failure case)
- Trailing double-quote (`hello"`) — correct (R11 failure case)
- Empty string (`""`) — `json.dumps("")` = `'""'`; regex captures `'""'`; `json.loads('""')` = `""` — correct
- JSON list fields (`tags`, `datapoints`, `provenance_entities`) — unaffected — correct

The fallback `strip('"')` path is now only reachable for entries written by the pre-R11 code, and only when those entries have no embedded quotes (which were already corrupt in old format). All new files written by R11+ code always produce valid JSON, so `json.loads` always succeeds and the fallback is dead code for new entries.

---

## Findings

*No findings.*

---

## Non-Findings

All items below were investigated in depth and dismissed as non-defects.

**R11 F-01 scalar-field fix**: Confirmed fully correct. `json.dumps` produces valid single-line JSON; `json.loads` round-trips all values including embedded quotes, backslashes, and unicode. The old-format fallback `strip('"')` is unreachable for new files.

**`ELNEntry.from_markdown()` empty-string sample/instrument**: `json.dumps("")` = `'""'`; the regex `(.+)` matches `""` (two chars ≥ 1); `json.loads('""')` = `""`. Empty string round-trips correctly.

**`planner.py:335` prerequisites index**: At `i=1`, `prerequisites = [f'step_{1:02d}_{effects[0][0]}']` = `['step_01_<effects[0]>']`, which matches `step_id` of `i=0` (`f'step_{1:02d}_...'`). Traced for all `i` values and verified correct by simulation.

**`rag.py:534` `year or 0` persist → NaN-load round-trip**: `None` stored as `0`, loaded as `None` (correct). `year=0` stored as `0`, loaded as `None` (year 0 AD is physically unrealistic in the domain; no correctness defect for spintronics research papers).

**`CorpusDB.add()` SELECT+INSERT TOCTOU**: Race condition between the `SELECT` dedup check and the `INSERT` is not exploitable in a single-user sequential CLI. SQLite serializes concurrent writers with a 10-second timeout. No parallelism in `add_many()`.

**`rag.py _rrf_fusion` score normalization**: `v_max = max(..., default=1.0) or 1.0` correctly handles all-zero scores (0.0 is falsy → `or 1.0` yields 1.0; normalized scores are all 0.0 with no division by zero). Empty `vector_results` uses `default=1.0`. Verified analytically.

**`active_learning.py select_precision` empty ladder**: `ladder = precision_ladder or PRECISION_LADDER` — an empty `[]` argument is falsy, so `PRECISION_LADDER` (3 elements) is used. If `affordable = []` (all levels too expensive), `return ladder[0]` returns the cheapest level by design (PRECISION_LADDER is sorted ascending by cost: low < medium < high).

**`graph.py path_search` BFS `break`**: Confirmed correct in R11. `end_id` is not added to `visited`, allowing all paths to be collected. The `break` on `len(path) > max_depth` is correct because BFS is FIFO (level-by-level); all remaining queued paths are of equal or greater length.

**`graph.py report_property` duplicate contradiction edge**: Second call with the same `(doi_a, doi_b, property_name)` produces the same `edge_id`. `add_edge()` catches `sqlite3.IntegrityError` and returns `False`. The `ContradictionFlag` is still appended to the return list. Consistent and correct.

**`connectors.py _with_backoff` exception propagation**: Inner methods catch non-retriable exceptions and `return None/[]`; only retriable exceptions propagate to the decorator. `fetch_by_doi_multi` wraps each connector call in `try/except Exception`, catching the `RuntimeError` raised after max retries. No unhandled exception path.

**`disclosure.py check_fabricated_citations` arXiv version suffix**: `_ARXIV_RE = re.compile(r'arXiv:\d{4}\.\d{4,}', re.IGNORECASE)` matches `arXiv:2305.00001` from `arXiv:2305.00001v2` because `v2` is not digits. The extracted ID is then stripped of `arXiv:` prefix and compared to `verified_arxivs`. Version suffixes are correctly ignored in both extraction and lookup. Verified by test.

**`disclosure.py` opt-out registry module-level load**: `_OPTOUT_REGISTRY` is loaded once at import. In-process changes via `register_optout()` are immediately reflected. Cross-process changes (e.g., another terminal) are not reflected until the next process start — acceptable for a single-user CLI tool.

**`auto_draft.py:61` ternary in for-loop**: `for k, v in params.items() if isinstance(params, dict) else {}.items()` is valid Python (ternary expression as iterable). Non-dict `params` correctly produces an empty iteration.

**`planner.py _build_doe full_factorial`**: `levels_per_param = max(2, int(n_points**(1/n_params)))` is always ≥ 2; the step denominator `levels_per_param - 1` is always ≥ 1; no division by zero. Verified by systematic test.

**`planner.py _build_doe simple_grid`**: `range(min(n_points, 5))` produces an empty range when `n_points <= 0`. `t = i / max(n_points - 1, 1)` guards against `n_points = 1` (denominator = max(0, 1) = 1). No division by zero.

**`keywords.py merge_keyword_scores` substring suppression**: Correct by design. Higher-scored items are processed first (sorted descending); shorter keywords that are substrings of already-kept longer ones are suppressed. This intentionally prefers longer multi-word phrases in the magnetism domain.

**`rag.py LiteratureRAG.add_document` idempotency**: `existing_doc_ids = {c.doc_id for c in self._chunks}` includes chunks loaded from LanceDB on startup, so the dedup check is session-persistent. An empty `doc_id=""` would be added to `existing_doc_ids` only if a chunk with `doc_id=""` was persisted, which cannot happen through the normal API (doc_id is always a DOI or dedup_key).

**`rubrics.py calibrate()` division guards**: All four divisions (precision, recall, FPR, FNR) are individually guarded by `if (denominator) > 0 else 0.0`. No division by zero in any degenerate confusion matrix.

**`ELNEntry._entry_path` path traversal**: If `entry_id` contains `../`, `_entry_path()` could write outside `notebook_dir`. However: (1) `create_entry()` always generates `uuid.uuid4()`; (2) `from_markdown()` reads from `_dir.rglob("*.md")` which only traverses inside `notebook_dir`; (3) no CLI command path accepts an arbitrary `entry_id` from user input. Exploiting this would require attacker write access to `notebook_dir` — which already implies full file-system access. Dismissed for single-user CLI context.

**`ELNNotebook.list_entries()` / `get_entry()` / `grep()` exception swallowing**: `except Exception: continue` silently skips malformed files during search. No data is lost on disk. Acceptable for a search/read function.

**`Theorist._simple_linear_fit` NaN conditions**: If all `conditions[:, 0]` values are NaN, `np.std(nan_array) = NaN`, `NaN < 1e-9` is `False`, `np.cov` is called and produces NaN slopes. Result is `{'slope': NaN, 'intercept': NaN}`. No crash; propagated NaN in `current_best_model` is benign (data was already invalid). Unreachable in normal workflow.

**`MetaReviewer.synthesize()` division-by-zero guards**: `statistics.mean(values)` only called when `values` is non-empty (populated from `dim_scores` which requires at least one review). `statistics.mean(mean_scores.values())` guarded by `if mean_scores`. All safe.

**`LiteratureRAG._load_from_db()` NaN year**: `year_raw != year_raw` is the correct IEEE 754 NaN identity test, confirmed again in R12. Converts valid years to `int`, assigns `None` otherwise.

**`PersonaGuard.guard()` double `check_optout()` call**: `check_author_eligibility()` at the `panel.py` call site raises `PersonaDisclosureError` before `guard()` is reached if the author is opted out. The second `check_optout()` inside `guard()` is redundant but harmless (it would just add a second violation record to an empty violations list, but the execution never reaches `guard()` for an opted-out author via the normal panel path).

**`_DOI_RE` conservative matching**: The pattern `r'10\.\d{4,}/[a-zA-Z0-9_./-]+'` may miss DOIs containing `(`, `:`, or other rare characters. This produces false positives in the fabrication check (legitimate DOI not matched → citation flagged as potentially fabricated). Conservative direction; no security risk.

**`CorpusDB` / `KnowledgeGraph` / `EvidenceMatrix` open connections**: All three expose `close()` but use a singleton pattern without a context manager. SQLite connections survive process exit gracefully. Acceptable for a single-user CLI.
