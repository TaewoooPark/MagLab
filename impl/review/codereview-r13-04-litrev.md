# Code Review R13 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 13 (fresh independent re-audit of R12-CLEAN)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND** — 1 finding, severity LOW.

All 24 Python files were re-audited from scratch. One genuine defect was found in `auto_draft.py`: a double-write pattern that leaves a wrong-titled entry on disk if the second write fails. No regressions to R12-confirmed fixes were found. No new HIGH or MEDIUM issues identified.

---

## Findings

### F-01 — LOW | `maglab/lab/notebook/auto_draft.py:94–106` | Double-write creates wrong-titled entry under I/O failure

**Defect**

`draft_from_fit_result` writes the entry to disk **twice**:

1. `notebook.create_entry(body, ...)` (line 94) — internally calls `_save()`. At this point, `entry.title` is auto-extracted from the first line of `body`, which is `"## Auto-Draft — {eff} Fitting Result"` (the Markdown heading with the `##` prefix). This is persisted to disk as the title.
2. `entry.title = title` (line 105) — overrides with the correct `"[Auto-Draft] {eff} Fitting — {date}"` string.
3. `notebook.save_entry(entry)` (line 106) — second write with correct title.
4. `return entry` (line 108) — caller receives entry with correct title.

In the **normal case** (both writes succeed) the final on-disk state and the returned object are correct. The defect is triggered only when the second `save_entry()` call raises an exception (e.g., disk full, permission error after the first write):

- The first write has already succeeded. The entry is on disk with `title = "## Auto-Draft — {eff} Fitting Result"`.
- The caller receives the exception (no valid return value).
- On subsequent `list_entries()` calls, the entry is returned with `title = ""` — because `from_markdown()` parses the `# title` line from the body text, but the body starts with the template (`## Observations\n\n...`) so `re.match(r"^#\s+(.+)\n", body_text)` finds no match, and `entry.title` stays empty. The actual title string `"# ## Auto-Draft…"` is buried in the body as raw text.

**Impact**: Entry silently appears with an empty title in all future notebook listings. The `entry_id`, sample, tags, and all other fields are intact. Manually fixable by editing the markdown file.

**Concrete fix**: Set the title *before* the first write by constructing the full title string ahead of `create_entry()` and passing it as a body prefix, or by restructuring to a single-save pattern:

```python
# Option A: construct entry manually for a single write
title = f"[Auto-Draft] {eff} Fitting — {date.today().isoformat()}"
entry = ELNEntry(
    date=date.today(),
    title=title,
    sample=sample,
    instrument=instrument,
    measurement_type=_infer_measurement_type(eff),
    tags=tags,
    datapoint_ids=datapoint_ids or [],
    body=_TEMPLATES.get(_infer_measurement_type(eff), "") + "\n" + body,
    provenance_entity_ids=provenance_entity_ids or [],
    is_draft=True,
)
notebook.save_entry(entry)
return entry
```

This eliminates the intermediate wrong-state write entirely.

---

## Non-Findings

Items investigated in depth and dismissed:

**`auto_draft.py` double-write — normal operation**: In the common case (no I/O error), both writes succeed, the second write atomically replaces the first (POSIX `write`+`rename`), and all state is correct. The defect only manifests under exceptional I/O failure conditions between the two writes.

**`ELNEntry.from_markdown()` `_extract` regex anchor**: `^{re.escape(key)}:\s*(.+)$` with `re.MULTILINE` anchors to start-of-line. Verified that `entry_id` does not match `test_entry_id` (the `^` requires start of line). No prefix-match false positives.

**`ELNEntry.from_markdown()` array regex greedy match**: `r'^{key}:\s*(\[.*\])\s*$'` with `re.MULTILINE`. The greedy `.*` within `\[...\]` matches to the last `]` on the line, correctly capturing arrays with embedded `]` characters (e.g., `["item with ] inside"]`). `json.loads` succeeds on the captured group. No DOTALL flag needed since `json.dumps` always writes arrays on a single line.

**`ELNEntry.from_markdown()` array key name consistency**: `to_markdown()` writes keys `sample`, `instrument`, `tags`, `datapoints`, `provenance_entities`. `from_markdown()` searches for the same key names. No mismatch.

**`ELNEntry.from_markdown()` invalid `measurement_type`**: Wrapped in `contextlib.suppress(ValueError)` — silently defaults to `MeasurementType.GENERAL`. Correct graceful degradation.

**`ELNEntry.from_markdown()` `is_draft` boolean parsing**: `v.lower() == "true"` — works for all values produced by `to_markdown()` (`"true"` / `"false"`). Values never written by `to_markdown()` (e.g., `"yes"`) are treated as `False` — acceptable for non-programmatic edits.

**`CorpusRAG._cosine_similarities()` zero-norm vectors**: `q_norm = math.sqrt(...) or 1e-9` guards against zero-norm query. Same for `v_norm`. All-zero vectors produce `sim = 0.0 / (1e-9 * 1e-9) = 0.0` — no crash.

**`CorpusRAG` BM25 pool size**: `bm25_pool = len(self._bm25._pending) if allowed_ids is not None else top_k * 2`. When `allowed_ids` is set, widens to full corpus count for the BM25 search so author-specific chunks are not dropped before the author filter. When `_pending` is empty, `max(0, top_k * 2) = top_k * 2` — correct. Private attribute access (`_bm25._pending`) is intra-module; not an encapsulation defect.

**`CorpusRAG._bm25._pending` never cleared**: `_pending` accumulates all chunks and is used both as the BM25 corpus for rebuild and as the pool-size denominator. Memory grows with corpus size; this is a performance concern only, not a correctness defect.

**`CorpusRAG` DOI validation with `doi=None`**: `chunk.doi.strip()` would crash with `AttributeError` if `doi=None`. The `CorpusChunk` dataclass declares `doi: str` — callers are type-checked. Not a genuine defect in a typed codebase.

**`LiteratureRAG._load_from_db()` year NaN handling**: `year_raw != year_raw` correctly catches IEEE 754 NaN (float). `np.nan` behaves identically. `None` is caught by the `is not None` check. `year=0` stored as `0`/`0.0` produces `None` on reload (falsy `and year_raw` clause) — by design, as year 0 AD is unrealistic for spintronics papers.

**`CorpusDB.search()` `author LIKE` query**: LIKE wildcards (`%`, `_`) in user-provided `author` string are passed through without escaping. Since the query is parameterized (no SQL injection), and the operation is read-only, any wildcard effect is limited to overly-broad matching — acceptable for a single-user CLI. No security risk.

**`connectors.py _reconstruct_abstract()` duplicate positions**: If the OpenAlex inverted index has two different words at the same position, they are sorted alphabetically by word — deterministic but may differ from the original abstract. This is a data quality issue from the API, not a code defect.

**`keywords.py extract_yake_keywords()` score inversion**: `max_score = max(..., default=1.0) + 1e-9` prevents division by zero. All-zero scores produce all-1.0 inverted scores. Negative YAKE scores are theoretically possible but YAKE never returns them.

**`meta_reviewer.py synthesize()` `statistics.mean` on empty collections**: `statistics.mean(mean_scores.values()) if mean_scores else 0.0` — empty dict is falsy, guard is correct. `statistics.mean(values) if values else 0.0` — inner `values` is non-empty by construction (populated from `dim_scores` entries). No unguarded `StatisticsError` path.

**`graph.py report_property()` `_paper_node_id` redefined per iteration**: The inner function is pure (no closure over loop variables). Redefinition on each iteration is wasteful but not incorrect.

**`loop_a.py` `if not engine.is_active(): break` (line 230)**: This check is dead code when threshold is not met — `engine.step()` has not yet been called in this iteration, so `is_active()` cannot have changed from the while-condition check. Harmless but superfluous.

**`loop_a.py` `final_score / 10.0`**: Divisor is the constant literal `10.0` — no division-by-zero possible.

**`disclosure.py check_fabricated_citations()` with `verified_dois=None`**: When `verified_dois=None`, individual DOIs are not validated against a verified set — only DOI *presence* is checked. This is explicit in the docstring and intentional API design.

**`disclosure.py` `_OPTOUT_REGISTRY` module-level load (R12 non-finding re-verified)**: Correct. In-process changes via `register_optout()` are immediately reflected. Cross-process changes require process restart — acceptable for a single-user CLI.

**All R12 non-findings**: Re-examined and confirmed still correct. No regressions found.
