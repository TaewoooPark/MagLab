# Code Review R6 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 6 (post-R5-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND** — 1 finding, severity LOW.

---

## R5 Fix Verification

**R5 F-01 confirmed fixed.** `corpus.py:149–153` (`get_by_doi`) and `corpus.py:219–228` (`update_retraction_status`) both now apply a three-prefix SQL `REPLACE` chain:

```python
"WHERE LOWER(REPLACE(REPLACE(REPLACE(doi, 'https://doi.org/', ''), 'http://doi.org/', ''), 'doi:', '')) = ?"
```

The Python-side normalization at lines 149 and 219–224 also correctly applies all three prefixes. End-to-end round-trip verified: a DOI stored as `doi:10.1103/physrevb.103.014412` produces `doi_norm = '10.1103/physrevb.103.014412'` from Python, and the SQL expression strips the `doi:` prefix from the stored value, yielding a match.

`graph.py:558–570` (`set_retraction_cache`) and `graph.py:500–506` (`check_retraction`) also apply correct three-prefix normalization. All R4/R5 fixes confirmed in place.

---

## Findings

### F-01 — LOW | `maglab/literature/connectors.py:668`

**Defect**: `ArXivConnector._result_to_record` normalizes `result.doi` with `.lower().replace("https://doi.org/", "")` but does **not** strip the `"http://doi.org/"` prefix. All other connectors apply both prefixes.

**Trace**:
- `OpenAlexConnector._work_to_record` (line 406): strips both `https://doi.org/` and `http://doi.org/` → correct.
- `SemanticScholarConnector._paper_to_record` (line 550): receives bare DOIs from S2 (`externalIds["DOI"]`), applies `.lower()` only — no prefix to strip, correct.
- `CrossRefConnector._item_to_record` (line 744): habanero returns bare DOIs, `.lower()` only — correct.
- `ArXivConnector._result_to_record` (line 668): **only** strips `https://doi.org/`. If `result.doi` is `"http://doi.org/10.1103/PhysRevB.103.014412"`, the stored `LiteratureRecord.doi` becomes `"http://doi.org/10.1103/physrevb.103.014412"`, violating the docstring invariant (`"DOI (normalized: lowercase, leading 'https://doi.org/' removed)"`).

**Impact**: Direct `.doi` field access on arXiv records returns `"http://doi.org/..."` instead of the bare DOI. The SQL `REPLACE` chain in `get_by_doi` and `update_retraction_status` already handles `http://doi.org/` prefix stripping, so **corpus lookups are unaffected**. `normalized_doi()` and `dedup_key()` also handle this correctly. However, any caller that reads `record.doi` directly (e.g., to display or compare) would get a prefixed string. The arXiv Python library uses `http://doi.org/` for some papers (particularly those crosslisted before 2022 when the API began favoring `https://doi.org/`), making this a realistic edge case.

**Fix** (one line):
```python
# connectors.py line 668 — change:
doi = str(result.doi).lower().replace("https://doi.org/", "")
# to:
doi = str(result.doi).lower().replace("https://doi.org/", "").replace("http://doi.org/", "")
```

---

## Non-Findings

- **R5 F-01 (DOI `REPLACE` chain)**: Confirmed fully fixed in `corpus.py` and `graph.py`. All three prefix variants (`https://doi.org/`, `http://doi.org/`, `doi:`) now handled in SQL and Python normalization.
- **R4 F-01 (`PersonaSpec.verified_dois` default)**: `verified_dois: set[str] | None = None` at `panel.py:55`. Safeguard ③ correctly skips per-DOI whitelist check when `None`. Confirmed.
- **R4 F-02 (`KnowledgeGraph.set_retraction_cache` normalization)**: `graph.py:558–570` applies all three-prefix normalization. Confirmed.
- **`CorpusDB.search()` SQL injection via LIKE**: All `LIKE` parameters are passed as bound parameters (`params.append(f"%{author}%")`). SQLite parameterized queries prevent SQL injection; `%` and `_` in user input become LIKE wildcards (expected behavior for a CLI search tool). Not a vulnerability.
- **`path_search` BFS break-on-depth correctness**: `if len(path) > max_depth: break` fires only after all paths at depth ≤ `max_depth` have been processed, by the BFS FIFO guarantee. Paths reaching `end_id` at exactly depth `max_depth` are appended before the break. Correct.
- **`report_property` contradiction detection with NaN values**: `max(abs(NaN), abs(v))` returns NaN; `NaN >= CONTRADICTION_THRESHOLD` is False, so NaN-valued measurements produce no contradiction flag. Silent but acceptable; NaN inputs represent measurement failures and should not trigger false contradiction flags.
- **`calibrate()` division-by-zero**: All four ratio computations (`precision`, `recall`, `fpr`, `fnr`) are guarded with `if (a + b) > 0 else 0.0`. Safe for empty record lists.
- **`SweepSpec.step_size` division safety**: `max(self.steps - 1, 1)` ensures denominator ≥ 1. No div-by-zero for any `steps` value. Confirmed.
- **`_CorpusBM25Index._pending` growth**: `_pending` accumulates all historical (chunk_id, text) pairs; each `_rebuild_if_dirty` processes the full list. Memory is O(n_total). For expected CLI scale (hundreds of chunks), this is within acceptable bounds. Not a defect.
- **`MeasurementPlanner` prerequisite formula**: `step_id=f"step_{i+1:02d}_{effect_name}"` and `prerequisites=[f"step_{i:02d}_{effects[i-1][0]}"]` — for i=1, prereq references `step_01_X` which matches the previous step's id. Verified correct by manual trace.
- **`_name_similar` single-word false positive**: A single-word `profile.name` (e.g., `"Smith"`) matches any author whose name contains `"Smith"` because `min(2, 1) = 1` token overlap suffices. This affects only S2 cross-enrichment (non-primary data). OpenAlex returns full names in practice; single-name profiles are extremely rare in academic contexts. Not filing as defect.
- **`ELNEntry.from_markdown` tag splitting on comma**: Tags containing a literal comma (e.g., `"spin, wave"`) would be split into two tags on parse. Tags are generated by application code (UUID-free simple strings, underscores substituted for spaces in `auto_draft.py`). Comma-containing tags are not produced by any code path in this codebase. Edge case only; not filing.
- **`ELNNotebook._entry_path` path traversal via parsed `entry_id`**: A malicious `.md` file placed in the notebook directory with `entry_id: ../../../../../etc/passwd` could yield an out-of-tree path if `save_entry` is called on the parsed entry. However: (1) `create_entry` always generates UUID4 IDs; (2) `save_entry` is only called on entries created by `create_entry` or explicitly by the user; (3) an attacker with write access to the notebook directory can write files directly. Threat model does not apply to a single-user CLI tool.
- **`_OPTOUT_REGISTRY` module-level load and thread safety**: Loaded at import time from JSON; exceptions are caught and return empty set. Non-atomic file writes could cause corruption under concurrent access, but single-user CLI deployment makes concurrent process access negligible. Not a defect.
- **`_with_backoff` + non-retriable exception swallowing**: Non-retriable exceptions are caught inside connector methods (`except Exception`) and converted to `None`/`[]` returns. The decorator only sees re-raised retriable exceptions. No retry amplification occurs for non-retriable errors.
- **`LiteratureRAG._load_from_db` year=0 sentinel**: `c.year or 0` stores `None` as `0`; the load expression `and year_raw` converts `0` back to `None`. Correct roundtrip confirmed.
- **`find_authoritative_authors` cache with nested `LiteratureRecord`**: `model_dump()` serializes nested Pydantic models to dicts; `AuthorProfile(**dict)` reconstruction correctly coerces `recent_papers: list[dict]` back to `list[LiteratureRecord]` via Pydantic. No data loss.
- **`PersonaGuard` double opt-out check**: `check_author_eligibility()` and `guard()` both call `check_optout()`. Redundant but correct; no false negatives.
- **Loop A `rounds_completed` on success path**: `current_round = engine.state.iteration + 1` before `engine.step("<promise>DONE</promise>")` correctly reflects completed rounds. Confirmed.
- **`JournalMetrics.as_display()` forbidden label check**: The check iterates over dict keys (source label strings), not values. Source label strings (`"SJR (SCImago)"`, `"OpenAlex 2yr_mean_citedness"`, `"Eigenfactor"`) do not contain any of the forbidden substrings. `validate_no_jcr_label()` also confirms source label fields. Correct.
