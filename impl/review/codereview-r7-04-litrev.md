# Code Review R7 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 7 (post-R6-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND** — 1 finding, severity LOW.

---

## R6 Fix Verification

**R6 F-01 confirmed fixed.** `connectors.py:668–673` (`ArXivConnector._result_to_record`) now applies a two-step chain:

```python
doi = (
    str(result.doi)
    .lower()
    .replace("https://doi.org/", "")
    .replace("http://doi.org/", "")
)
```

Both `https://doi.org/` and `http://doi.org/` are stripped before the normalized DOI is stored in `LiteratureRecord.doi`. The fix matches the R6 recommendation verbatim and is consistent with `OpenAlexConnector._work_to_record` (line 406). Confirmed.

---

## Findings

### F-01 — LOW | `maglab/literature/keywords.py:110`

**Defect**: `extract_texts_from_folder` calls `sorted(folder.iterdir())` at line 110 with no prior existence check. If `folder` does not exist or is not a directory, `Path.iterdir()` raises `FileNotFoundError` (or `NotADirectoryError`), which propagates uncaught through the function and through its only call site, `extract_keywords_from_folder` (line 468), which also has no guard.

**Trace**:
- `extract_texts_from_folder(folder)` → `sorted(folder.iterdir())` → `FileNotFoundError` if `folder` is absent.
- `extract_keywords_from_folder(folder)` at line 468 calls `extract_texts_from_folder(folder)` with no `try/except`. The exception propagates to the CLI command handler.
- Contrast: an *empty* folder returns `[]` cleanly (the for-loop body is never entered). A *missing* folder raises. This behavioral inconsistency violates the principle of least surprise.

**Impact**: Any CLI invocation of `maglab lab plan` (or any caller of `extract_keywords_from_folder`) with a non-existent folder path receives an unhandled Python traceback instead of a user-friendly error or empty result. Severity LOW because the error is ultimately surfaced to the user (not silently swallowed), but the presentation is poor.

**Concrete fix** (one of two options):

Option A — guard at the function entry point:
```python
# keywords.py line 109 — insert before the for loop:
def extract_texts_from_folder(
    folder: Path, extensions: tuple[str, ...] = (".pdf", ".txt")
) -> list[tuple[Path, str]]:
    if not folder.is_dir():
        return []
    results: list[tuple[Path, str]] = []
    for f in sorted(folder.iterdir()):
        ...
```

Option B — guard at the call site:
```python
# keywords.py line 468 — in extract_keywords_from_folder:
file_texts = extract_texts_from_folder(folder)
# becomes:
if not folder.is_dir():
    log.warning("Folder does not exist or is not a directory (%s)", folder)
    return []
file_texts = extract_texts_from_folder(folder)
```

Option A is preferred — it fixes the contract at the source and prevents the exception from reaching any other future call sites.

---

## Non-Findings

- **R6 F-01 (ArXivConnector http://doi.org/ stripping)**: Confirmed fully fixed at `connectors.py:668–673`. Both `https://doi.org/` and `http://doi.org/` are now stripped in the correct order (`.lower()` first, then both `.replace()` calls).
- **R5 F-01 / R4 F-01 (three-prefix DOI normalization)**: `corpus.py:149–153` and `corpus.py:219–228` both apply three-prefix SQL `REPLACE` chain and Python-side normalization. `graph.py:500–506` and `graph.py:558–570` (`check_retraction`, `set_retraction_cache`) apply the same three-prefix normalization. All confirmed in place.
- **OpenAlex `_work_to_record` `.replace()` before `.lower()` ordering (line 406)**: `doi_raw.replace("https://doi.org/", "").replace("http://doi.org/", "").lower()` applies `.lower()` after replace. In theory, uppercase URL prefixes would not be stripped. In practice, OpenAlex always returns lowercase `https://doi.org/` URLs. The `normalized_doi()` method provides a second defense. Investigated and dismissed as theoretical only.
- **`_with_backoff` retry scope**: Non-retriable exceptions are caught and swallowed inside each connector method before they reach the decorator. The decorator only retries on re-raised retriable exceptions. No spurious retry amplification occurs. Confirmed correct.
- **`CorpusDB`, `KnowledgeGraph`, `EvidenceMatrix` persistent connections**: All three use a long-lived `self._conn` opened in `__init__`. No `__del__` or context manager. Python's GC closes SQLite connections on object destruction. For a single-user CLI that exits normally, this is acceptable. Not a resource leak in practice.
- **`CorpusDB.get_corpus()` singleton never closed**: The module-level `_default_corpus` singleton is not explicitly closed. Acceptable for a CLI tool; OS/GC cleanup on exit. Not a defect.
- **`check_fabricated_citations` arXiv-only text (no bracket patterns)**: When `citations_found` is empty but `arxivs_found` is non-empty, the early-exit guard correctly does not fire. If `verified_arxivs` is provided, each arXiv ID is individually validated. Logic is correct for all combinations of `verified_dois`/`verified_arxivs` being `None` or a set.
- **`_DOI_RE` conservative regex**: The pattern `10\.\d{4,}/[a-zA-Z0-9_./-]+` may miss DOIs containing parentheses or other RFC-3986 characters. For the persona reviewer context, all DOIs originate from corpus RAG chunks which are API-normalized (no special characters). Conservative matching is safe here.
- **`MetaReviewer.synthesize()` empty/single-reviewer panel**: Empty-review guard returns `N/A` result. `statistics.pstdev([x])` is guarded with `len > 1`. `statistics.mean([])` is guarded with `if mean_scores`. All edge cases handled correctly.
- **`CorpusRAG.add_chunk` whitespace-only DOI**: `if not chunk.doi.strip()` correctly rejects DOIs that are whitespace-only. Confirmed.
- **`_CorpusBM25Index._rebuild_if_dirty` full-rebuild**: Rebuilds from accumulated `_pending` list on every dirty search. O(n_total) per search, but for expected CLI scale (hundreds of chunks per author) this is within acceptable bounds. Not a defect.
- **`MeasurementPlanner._build_doe` with `partial_factorial` doe_type**: The `partial_factorial` branch has no explicit `elif`, causing silent fallthrough to the `simple_grid` return. The docstring lists it as a valid option. This is a documentation/implementation mismatch but not a runtime error; the call site provides `doe_type='latin_hypercube'` as default. Dismissed as non-defect.
- **`MeasurementPlanner._build_doe` with empty `parameters`**: The only call site (`planner.py:344–345`) guards with `if parameters and len(parameters) > 1`. So `n_params == 0` is unreachable via the public API. Dismissed.
- **`run_loop_a` `rounds_completed` metric mismatch on all-error path**: If `panel.review()` always raises, `rounds_completed` reflects `engine.state.iteration` (which counts `engine.step()` calls including error-path calls) while `round_reviews` is empty. This is a semantic discrepancy in the diagnostic metric, not a correctness issue; `success=False` is correctly returned. Dismissed.
- **`extract_texts_from_folder` `sorted()` on `iterdir()` return**: `Path.iterdir()` returns a generator; `sorted()` fully materializes it. For a typical papers folder (tens to hundreds of files), this is acceptable. Not a performance defect.
- **`LiteratureRAG._load_from_db` year NaN sentinel roundtrip**: `c.year or 0` stores `None` as `0`; `(year_raw := row.get("year")) is not None and not (isinstance(year_raw, float) and year_raw != year_raw) and year_raw` correctly converts `0` back to `None`. Confirmed.
- **`EvidenceMatrix.update_verification` silent no-op**: Updating a non-existent `ref_key` executes `UPDATE ... WHERE ... AND ref_key=?` that affects 0 rows without raising. Acceptable for a CLI tool where the user controls the ref_key. Dismissed.
- **`select_precision` with empty affordable ladder**: `affordable = [lvl for lvl in ladder if lvl.cost <= budget_remaining]`. If none are affordable, returns `ladder[0]` (cheapest). Safe fallback. Confirmed.
- **`Theorist._simple_linear_fit` with single-column conditions**: `conditions.shape[1] == 0` guard handles zero-column arrays. `np.std(x) < 1e-9` handles constant x. Correct.
- **`SweepSpec.step_size` division safety**: `max(self.steps - 1, 1)` ensures denominator ≥ 1. No division by zero for any `steps` value. Confirmed (also confirmed in R5/R6).
