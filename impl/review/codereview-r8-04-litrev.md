# Code Review R8 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 8 (post-R7-patch re-audit)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**ISSUES FOUND** — 2 findings, max severity LOW.

---

## R7 Fix Verification

**R7 F-01 confirmed fixed.** `keywords.py:100–116` (`extract_texts_from_folder`) now:

1. Accepts `Path | str` via `folder = Path(folder)` at line 114.
2. Guards with `if not folder.is_dir(): return []` at lines 115–116 before calling `sorted(folder.iterdir())`.

The docstring at lines 111–113 also explicitly documents this behavior: "Returns `[]` when *folder* does not exist or is not a directory, consistent with the empty-folder case." Fix matches both R7 Option A recommendation and the type-signature expansion. Confirmed.

---

## Findings

### F-01 — LOW | `maglab/lab/notebook/entry.py:153`

**Defect**: `ELNEntry.from_markdown()` uses the regex `[^\]]*` to parse the square-bracket list fields (`tags`, `datapoints`, `provenance_entities`). The character class `[^\]]` stops at the first `]` character. When a tag or datapoint ID itself contains a literal `]` character, the regex terminates early, silently truncating the value.

**Trace**:
- `to_markdown()` writes: `tags: ["spin]hall", "CoFeB"]`
- `from_markdown()` applies regex `^tags:\s*\[([^\]]*)\]` → matches `"spin` (stops at the `]` inside the value).
- Parsed result: `['spin']` instead of `['spin]hall', 'CoFeB']`.
- Same issue affects `datapoints:` and `provenance_entities:` fields via the shared loop at lines 148–157.

**Impact**: Roundtrip fidelity is broken for any tag, datapoint ID, or provenance entity ID containing `]`. Realistic examples: `sample[A]`, `sot[run1]`, `datapoint[2024-01-15]`. All three list fields silently lose data on reload. Severity LOW because the CLI does not currently generate `]` in these fields through its own code paths (effect names from `_QUANTITY_TO_EFFECT` contain no brackets), but user-supplied or free-form IDs can include them.

**Concrete fix**: Use a non-greedy alternative that handles escaped quotes rather than stopping at `]`:

```python
# Replace the regex pattern for all three fields:
# Old:
m2 = re.search(rf"^{key}:\s*\[([^\]]*)\]", fm_text, re.MULTILINE)
# New (matches up to the first unquoted ]):
m2 = re.search(rf'^{key}:\s*\[([^\]]*(?:"[^"]*"[^\]]*)*)\]', fm_text, re.MULTILINE)
```

Or, simpler: strip the outer brackets and split on `", "` after stripping outer whitespace, avoiding bracket-dependent character classes entirely:

```python
m2 = re.search(rf"^{key}:\s*\[(.+?)\]\s*$", fm_text, re.MULTILINE)
```

Using `(.+?)` (non-greedy) and anchoring to end-of-line (`\s*$`) ensures the regex captures the full bracketed content up to the final `]` on the line.

---

### F-02 — LOW | `maglab/lab/notebook/entry.py:122`

**Defect**: `ELNEntry.from_markdown()` writes `created_at` to the YAML frontmatter via `to_markdown()` (line 110: `f"created_at: {self.created_at.isoformat()}\n"`) but never reads it back. There is no `_extract("created_at")` call in `from_markdown()`. On every load of a saved entry, `created_at` is silently reset to `datetime.now()` (the dataclass field default), discarding the originally stored timestamp.

**Trace**:
- `to_markdown()` serializes `created_at` to frontmatter.
- `from_markdown()` calls `_extract()` for: `entry_id`, `date`, `sample`, `instrument`, `measurement_type`, `is_draft` — but not `created_at`.
- Round-trip: write `2024-01-15T10:30:00` → read → `datetime.now()` (different value).
- `ELNNotebook.list_entries()`, `get_entry()`, and `grep()` all reconstruct entries via `from_markdown()`, so every loaded entry has a wrong `created_at`.

**Impact**: `created_at` is not used in any search or filter path, so operational correctness is unaffected. The field is cosmetically present in stored files but non-functional after the first reload. FAIR JSON-LD export (`to_fair_json_ld()`) uses `self.date.isoformat()` (not `created_at`), so export is unaffected. Severity LOW — functional impact is minimal, but the field is misleading (stored but silently reset on load).

**Concrete fix**: Add parsing for `created_at` in `from_markdown()` after the `is_draft` block:

```python
if v := _extract("created_at"):
    with contextlib.suppress(ValueError):
        entry.created_at = datetime.fromisoformat(v)
```

---

## Non-Findings

- **R7 F-01 (keywords.py missing-folder guard)**: Confirmed fixed at `keywords.py:114–116`. Both `Path | str` acceptance and `is_dir()` guard are in place.
- **`_reconstruct_abstract` duplicate positions**: Multiple words at the same position are the correct behavior per OpenAlex inverted-index spec. Not a defect.
- **`_with_backoff` retry scope**: Only retriable exceptions propagate out of connector methods (inner `if _is_retriable(exc): raise` guard); the decorator retries only those. Non-retriable exceptions are caught and silently logged, returning `None`/`[]`. Correct.
- **`CorpusDB.search()` SQL injection risk**: `clauses` list contains hardcoded SQL fragments only; all user values go as positional `?` parameters. No injection surface.
- **`corpus.py get_by_doi()` LIKE special chars**: Uses `=` equality (not `LIKE`) in the SQL predicate; `%` and `_` in DOIs are treated as literals. Safe.
- **`draft_from_fit_result` line 61 ternary in for-loop**: `for k, v in params.items() if isinstance(params, dict) else {}.items():` is valid Python — the `if/else` is a ternary expression, not a comprehension filter. Handles `None` and non-dict params correctly (falls back to empty dict).
- **`ELNEntry.from_markdown()` entry_id not validated as UUID**: `entry_id` is stored as whatever string was parsed. Non-UUID strings are accepted. Acceptable for a local CLI notebook — no external trust boundary.
- **`report_property` `_paper_node_id` inner function redefined in loop**: The function is defined and called in the same iteration with explicit args; no late-binding closure issue.
- **`path_search()` BFS max_depth termination**: The `break` when `len(path) > max_depth` is correct because BFS processes paths in monotonically non-decreasing length order; no shorter paths remain once the threshold is crossed.
- **`path_search()` start == end corner case**: If start equals end and a self-loop edge exists, a path is found. Knowledge graphs do not have self-loops in practice. Not a defect.
- **`check_fabricated_citations()` arXiv ID strip**: `re.sub(r"(?i)^arxiv:", "", arxiv_ref)` correctly handles all-caps `ARXIV:` prefix. Lowercase comparison to `verified_arxivs_lower` is correct.
- **`PersonaGuard.guard()` calls `check_optout()` a second time**: Called both via `check_author_eligibility()` at the top of `_review_single()` and again inside `guard()` at safeguard ⑥. Double-check is redundant but not harmful — the first call already raises `PersonaDisclosureError` before `guard()` is reached if the author is opted out.
- **`_OPTOUT_REGISTRY` module-level mutable set**: Not thread-safe, but this is a single-user CLI; concurrent write risk is absent. Acceptable.
- **`loop_a.py` redundant `if not engine.is_active(): break` at line 230**: The while-loop guard at line 176 already prevents entering the body when `is_active()` is False. The inner check at line 230 is unreachable in practice. Harmless dead code, not a defect.
- **`loop_a.py` success-path `engine.step()` before early return**: `engine.step()` internally calls `save_state()`; the checkpoint at line 277 is not reached on early return, but state is saved by the step call. No state loss.
- **`MeasurementPlanner.plan()` step prerequisites step_id alignment**: When `i=1`, `prerequisites=[f"step_{i:02d}_{effects[i-1][0]}"]` = `"step_01_<effect>"`, which matches the previous step's `step_id = f"step_{i:02d}_{effect_name}"` where the previous step was built at `i=0`: `f"step_{0+1:02d}_<effect>"` = `"step_01_<effect>"`. Correct alignment.
- **`MeasurementPlanner._build_doe` `partial_factorial` fallthrough**: Passes through to `simple_grid`. Pre-existing non-finding from R7; call sites use `latin_hypercube`. Dismissed.
- **`OpenAlexConnector._work_to_record` `.replace()` before `.lower()` ordering**: OpenAlex always returns lowercase `https://doi.org/` prefix; uppercase mismatch is purely theoretical. `normalized_doi()` provides a second defense. Dismissed.
- **`EvidenceMatrix.update_verification` silent no-op on missing ref_key**: Zero-row UPDATE is acceptable for CLI where user controls ref_key. Dismissed.
- **`CorpusDB`, `KnowledgeGraph`, `EvidenceMatrix` persistent connections without `__del__`**: GC closes SQLite connections on object destruction. Acceptable for a single-user CLI. Not a resource leak in practice.
