# Code Review R14 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 14 (fresh independent re-audit of R13-FIXED)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**FIXED** — 1 defect found and patched.

All 24 Python files were audited from scratch. One genuine MEDIUM-severity defect
was found in `graph.py`: `report_property()` inserted contradiction edges whose
`source_id`/`target_id` referenced paper nodes that did not exist in the `nodes`
table, silently making `get_neighbors()` return `[]` for those IDs. Fixed by
auto-creating the paper nodes with `INSERT OR IGNORE` before adding the edge.
No other genuine defects were found.

---

## R13 Fix Verification

**Confirmed.** `maglab/lab/notebook/auto_draft.py:draft_from_fit_result()` now
constructs the `ELNEntry` with the correct `title` (`"[Auto-Draft] {eff} Fitting
— {date}"`) before any write, calls `notebook.save_entry(entry)` exactly once,
and returns immediately. The old double-write pattern (first write via
`create_entry()` with wrong title, second write via `save_entry()` with correct
title) is fully eliminated. The three R13 regression tests (`test_draft_from_fit_result_on_disk_title_is_correct`,
`test_draft_from_fit_result_from_markdown_parses_nonempty_title`,
`test_draft_from_fit_result_single_write`) all pass.

---

## Findings & Fixes

### F-01 — MEDIUM | `maglab/literature/graph.py:456–471` | `report_property()` contradiction edges reference non-existent paper nodes → `get_neighbors()` silently returns `[]`

**Defect**

`report_property()` calls `self.add_edge(edge)` where `edge.source_id` and
`edge.target_id` are paper node IDs of the form `"paper:10.1234/x"` or
`"paper:noid-{hash}"`. These IDs are constructed internally by `_paper_node_id()`
but the corresponding rows are never inserted into the `nodes` table. SQLite does
not enforce `FOREIGN KEY` constraints by default (`PRAGMA foreign_keys` is `OFF`
unless explicitly set), so the `INSERT` into `edges` succeeds silently.

Consequence: `get_neighbors(node_id)` calls `self.get_node(neighbor_id)` for
each edge endpoint. `get_node()` issues `SELECT * FROM nodes WHERE node_id = ?`
and returns `None` for any ID not in `nodes`. The guard `if neighbor: results.append(…)`
silently drops the result. The entire `get_neighbors()` call returns `[]` for
paper nodes created only through `report_property()`.

Similarly, `path_search()` traverses neighbors via `get_neighbors()`, so paths
through contradiction paper nodes are also silently missed.

`contradicts_edges()` and `stats()` still return correct results because they
query the `edges` table directly, not through `get_node()`. The inconsistency
is therefore between the edge data and the node data.

**Confirmed with**:
```python
kg.report_property('CoFeB', 'Ms', 1e6, doi='10.1234/a', title='Paper A')
kg.report_property('CoFeB', 'Ms', 2e6, doi='10.1234/b', title='Paper B')
kg.stats()
# {'nodes': 0, 'edges': 1, ...}  ← nodes empty, but edge references them
kg.get_neighbors('paper:10.1234/b')
# []  ← silently empty instead of returning 'paper:10.1234/a'
```

**Fix applied** (`maglab/literature/graph.py`):

In the contradiction-detection loop inside `report_property()`, after computing
`node_a_id` and `node_b_id`, insert both paper nodes using `INSERT OR IGNORE`
(which preserves any richer existing node data added via `add_node()`) before
calling `add_edge()`:

```python
self._conn.execute(
    "INSERT OR IGNORE INTO nodes "
    "(node_id, node_type, label, properties, created_at) "
    "VALUES (?,?,?,?,?)",
    (node_a_id, "paper", row["title"] or row["doi"] or node_a_id, "{}", time.time()),
)
self._conn.execute(
    "INSERT OR IGNORE INTO nodes "
    "(node_id, node_type, label, properties, created_at) "
    "VALUES (?,?,?,?,?)",
    (node_b_id, "paper", title or doi or node_b_id, "{}", time.time()),
)
```

After the fix:
```python
kg.stats()
# {'nodes': 2, 'edges': 1, ...}  ← paper nodes now in table
kg.get_neighbors('paper:10.1234/b')
# [(<contradicts edge>, GraphNode(node_id='paper:10.1234/a', ...))]  ← correct
```

**Regression tests added** (`tests/unit/test_literature_graph.py`, class
`TestR14ContradictionPaperNodesCreated`):

1. `test_contradiction_paper_nodes_exist_in_nodes_table` — after a contradiction
   is detected, both paper nodes must be retrievable via `get_node()`.
2. `test_get_neighbors_traverses_contradiction_edges` — `get_neighbors()` on the
   source paper node must return the target paper node via the `contradicts` edge.
3. `test_existing_richer_node_not_overwritten` — `INSERT OR IGNORE` must not
   overwrite an existing paper node added with richer metadata via `add_node()`.
4. `test_doi_less_paper_nodes_created_for_contradiction` — DOI-less paper nodes
   (using `noid-{hash}` IDs) must also be created so traversal works for them.

---

## Non-Findings

Items investigated in depth and dismissed:

**`auto_draft.py` R13 fix**: Confirmed correct. Single-write, correct title. All three R13 regression tests pass.

**`planner.py:335` prerequisite generation**: `prerequisites=[f'step_{i:02d}_{effects[i-1][0]}'] if i > 0 else []` is correct — for step at index `i` (step_id uses `i+1`), the prerequisite references the previous step (`i` = `i+1-1`). Verified with multi-step plans.

**`planner.py` full_factorial with `levels_per_param=1` guard**: `max(2, int(n_points**(1/n_params)))` ensures at least 2 levels even when `n_points=1`. Verified.

**`path_search` BFS `break` on `max_depth`**: Correct. BFS guarantees monotonically increasing path lengths; once `len(path) > max_depth`, all remaining queued paths are also longer. The `break` is sound.

**`path_search` max_depth semantics**: `max_depth=4` yields paths with up to 4 node IDs (3 hops from source to target). Consistent with the BFS implementation and the default `max_depth=4`. Not a bug.

**`Theorist._simple_linear_fit` with zero-column conditions**: When all `MeasurementPoint.conditions` are `{}`, `conditions_array()` returns shape `(n, 0)`. `_simple_linear_fit` guards `if conditions.shape[1] == 0: return {'intercept': mean}`. Correct.

**`_compute_model_disagreement` population variance**: Uses `/ len(preds)` (population variance). Correct for a spread metric; sample variance (`/ (n-1)`) would be wrong for n=2. Correct.

**`LiteratureRAG._rrf_fusion` v_max/b_max zero guard**: `max(scores, default=1.0) or 1.0` correctly handles both empty and all-zero score sequences. No division by zero.

**`CorpusRAG.search()` BM25 pool size**: `bm25_pool = len(self._bm25._pending)` correctly widens the BM25 search to all indexed chunks when filtering by `author_id` so no author chunks are silently dropped. Non-finding.

**`CorpusRAG._cosine_similarities` vector-length mismatch**: `strict=False` in `zip` silently truncates mismatched vectors. Cannot occur in practice (all vectors from same embedding model). Non-finding.

**`LiteratureRAG.add_document` O(n) idempotency set rebuild**: Rebuilds `{c.doc_id for c in self._chunks}` on each call. Performance concern only. Non-finding.

**`CorpusDB` and `KnowledgeGraph` persistent connection resource leak**: Python's GC will close the SQLite connection when the object is collected. Acceptable for a CLI tool with the same pattern across all DB classes. Non-finding.

**`dedup_key()` collision on empty title and empty DOI**: Both `LiteratureRecord(doi='', title='')` and `LiteratureRecord(doi='', title='   ')` produce `"title:"`. Two truly indistinguishable records (no DOI, no title) correctly collapse to one entry. Acceptable by design. Non-finding.

**`graph.py` self-loop edge when both doi='' and title='' for two different papers**: `_paper_node_id('', '')` produces the same hash for both. After R14 fix, a self-loop node would be created. Practically impossible (two real contradicting papers would have at least a title). Non-finding.

**`_OPTOUT_REGISTRY` module-level load**: Correct. In-process changes via `register_optout()` are immediate. Cross-process changes require restart — acceptable for a single-user CLI.

**`disclosure.py check_fabricated_citations` with `verified_arxivs=None`**: When `None`, arXiv IDs in text are not validated against a set; only presence is checked. Documented behavior. Non-finding.

**`loop_a.py` line 230 dead-code check**: `if not engine.is_active(): break` is always False when reached (the `while engine.is_active()` guard at the top just passed, and `engine.step()` has not yet been called). Harmless dead code. Non-finding (confirmed from R13).

**`meta_reviewer.py statistics.mean` on empty collections**: Both call sites are guarded. Non-finding (confirmed from R13).

**`BM25Index._dirty` flag invariant**: `_dirty=True` with `_pending=[]` is impossible in normal usage (only `add()` sets the flag). Non-finding.

**`_with_backoff` + `_is_retriable` re-raise pattern in connectors**: Retriable exceptions are re-raised inside the decorated method's `except` block, which propagates to the backoff wrapper for retry. Non-retriable exceptions are caught and return `None`. Correct flow. Non-finding.

**All R12/R13 non-findings**: Re-examined and confirmed still correct. No regressions found.

---

## Verification

```
ruff check maglab/literature/ maglab/reviewer/ maglab/lab/
# All checks passed!

mypy maglab/literature/ maglab/reviewer/ maglab/lab/ --ignore-missing-imports
# Success: no issues found in 24 source files

python -B -m pytest tests/unit/test_lab_notebook.py tests/unit/test_lab_planning.py \
  tests/unit/test_literature_connectors.py tests/unit/test_literature_corpus.py \
  tests/unit/test_literature_graph.py tests/unit/test_literature_journals.py \
  tests/unit/test_literature_keywords.py tests/unit/test_literature_rag.py \
  tests/unit/test_reviewer_corpus_rag.py tests/unit/test_reviewer_panel.py \
  tests/unit/test_reviewer_rubrics.py --timeout=120
# 256 passed in 4.50s  (252 pre-existing + 4 new R14 regression tests)
```
