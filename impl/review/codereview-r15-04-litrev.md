# Code Review R15 — Literature / Reviewer / Lab

**Domains**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Round**: 15 (fresh independent re-audit of R14-FIXED)
**Auditor**: Claude Sonnet 4.6

---

## Verdict

**FIXED** — 1 defect found and patched.

All 24 Python files were audited from scratch. One genuine LOW-MEDIUM-severity defect
was found in `graph.py`: `report_property()` did not commit the `INSERT OR IGNORE`
paper nodes before calling `add_edge()`. When `add_edge()` raised `sqlite3.IntegrityError`
(duplicate `edge_id`), it returned `False` without calling `commit()`, silently rolling
back the node insertions. Fixed by adding an explicit `self._conn.commit()` after the two
`INSERT OR IGNORE` statements and before `add_edge()`. No other genuine defects were found.

---

## R14 Fix Verification

**Confirmed.** `maglab/literature/graph.py:report_property()` now contains the R14 fix:
both `INSERT OR IGNORE INTO nodes` statements are present before `add_edge()`, using
`INSERT OR IGNORE` to avoid overwriting richer existing node data. Verified in-process:

```python
kg.report_property('CoFeB', 'Ms', 1e6, doi='10.1234/a', title='Paper A')
flags = kg.report_property('CoFeB', 'Ms', 2e6, doi='10.1234/b', title='Paper B')
kg.stats()
# {'nodes': 2, 'edges': 1, 'contradicts_edges': 1, 'retracted_cached': 0}
kg.get_node('paper:10.1234/a')
# GraphNode(node_id='paper:10.1234/a', node_type='paper', ...)
kg.get_neighbors('paper:10.1234/b')
# [(edge, GraphNode(node_id='paper:10.1234/a', ...))]
```

All four R14 regression tests pass.

---

## Findings & Fixes

### F-01 — LOW-MEDIUM | `maglab/literature/graph.py:459–491` | `report_property()` INSERT OR IGNORE paper nodes not committed before `add_edge()` → silent rollback when edge already exists

**Defect**

`report_property()` executes two `INSERT OR IGNORE INTO nodes` statements and then
calls `self.add_edge(edge)`. The `add_edge()` method calls `self._conn.commit()` on
success. However, when `add_edge()` raises `sqlite3.IntegrityError` (because an edge
with the same `edge_id` already exists), it catches the exception and returns `False`
**without calling `commit()`**.

SQLite operates in autocommit-off mode when using `sqlite3.connect()` (Python's default).
All DML statements execute within an implicit transaction. When the two `INSERT OR IGNORE`
statements succeed (inserting new rows) but `add_edge()` then fails, no `commit()` is ever
called. The next `conn.execute()` or `conn.commit()` from an unrelated operation will
begin a new transaction, and the uncommitted `INSERT OR IGNORE` rows from the current
transaction are silently rolled back.

**Consequence**: A paper node that was legitimately absent from the `nodes` table (e.g.
due to external deletion or a process restart) would not be re-created after the second
`report_property()` call for the same contradiction pair. `get_node()` would return `None`
and `get_neighbors()` would silently return `[]` for that paper — the same symptom the
R14 fix was meant to cure, now resurfacing via a different code path.

**Confirmed with**:
```python
# First contradiction — nodes and edge committed successfully.
kg.report_property('Pt', 'theta_SH', 0.08, doi='10.1103/a', title='Paper A')
kg.report_property('Pt', 'theta_SH', 0.02, doi='10.1103/b', title='Paper B')
# stats: nodes=2, edges=1

# Manually delete node_b to simulate inconsistency.
kg._conn.execute('DELETE FROM nodes WHERE node_id = ?', ('paper:10.1103/b',))
kg._conn.commit()

# Re-report the same contradiction.
# add_edge() raises IntegrityError (duplicate edge_id) → no commit.
kg.report_property('Pt', 'theta_SH', 0.08, doi='10.1103/a', title='Paper A')
kg.report_property('Pt', 'theta_SH', 0.02, doi='10.1103/b', title='Paper B')

kg.get_node('paper:10.1103/b')
# None  ← INSERT OR IGNORE was rolled back (before fix)
```

**Fix applied** (`maglab/literature/graph.py`):

After the two `INSERT OR IGNORE` statements and before calling `add_edge()`, add an
explicit `self._conn.commit()`:

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
# Commit the node rows immediately so they are durable regardless of whether
# add_edge() succeeds or raises IntegrityError (duplicate edge).
self._conn.commit()

edge = GraphEdge(...)
self.add_edge(edge)
```

After the fix:
```python
kg.get_node('paper:10.1103/b')
# GraphNode(node_id='paper:10.1103/b', node_type='paper', ...)  ← correctly persisted
```

**Regression tests added** (`tests/unit/test_literature_graph.py`, class
`TestR15NodeCommitBeforeAddEdge`):

1. `test_paper_nodes_committed_even_when_edge_is_duplicate` — when the same
   contradiction is reported twice and the node for the second paper is missing,
   the second call must still persist both paper nodes even though `add_edge()`
   returns `False` (duplicate `edge_id`).
2. `test_get_neighbors_works_after_duplicate_edge_report` — after the
   duplicate-edge scenario, `get_neighbors()` must return the connected paper
   node (not `[]`).

---

## Non-Findings

Items investigated in depth and dismissed:

**R14 fix commit sequencing**: The `INSERT OR IGNORE` calls inside `report_property()`
are now committed before `add_edge()` (F-01 fix). Pre-fix: if `add_edge()` succeeded,
it committed both the nodes and the edge correctly. The defect only surfaced when
`add_edge()` failed.

**`report_property()` transaction isolation for multiple contradictions in one loop**:
When a new value contradicts multiple existing values in one call, the loop processes each
pair sequentially. Each iteration calls `self._conn.commit()` (via the F-01 fix) and then
`add_edge()`. If two iterations generate the same `edge_id` (same pair, different loop
order), the second `add_edge()` fails with IntegrityError and returns `False`. The node
rows are committed by the explicit commit before `add_edge()`, so they survive. Non-finding.

**`auto_draft.py` R13 fix**: Confirmed correct. Single-write, correct title. All three R13
regression tests pass.

**`planner.py` prerequisite generation**: `prerequisites=[f'step_{i:02d}_{effects[i-1][0]}'] if i > 0 else []`
is correct for step at index `i`. Non-finding.

**`path_search` BFS `break` on `max_depth`**: BFS guarantees monotonically increasing
path lengths; `break` is sound once `len(path) > max_depth`. Non-finding.

**`_OPTOUT_REGISTRY` module-level load**: In-process changes via `register_optout()` are
immediate. Cross-process requires restart — acceptable for a CLI. Non-finding.

**`disclosure.py check_fabricated_citations` with `verified_arxivs=None`**: When `None`,
arXiv IDs are accepted if any reference ID is present. Documented behavior. Non-finding.

**`loop_a.py` line 230 dead-code check**: `if not engine.is_active(): break` is always
False when reached. Harmless dead code. Non-finding (confirmed from R13).

**`meta_reviewer.py statistics.mean` on empty collections**: Both call sites guarded.
Non-finding (confirmed from R13).

**`LiteratureRAG._rrf_fusion` v_max/b_max zero guard**: `max(scores, default=1.0) or 1.0`
correctly handles empty and all-zero score sequences. Non-finding.

**`CorpusRAG.search()` BM25 pool size**: `bm25_pool = len(self._bm25._pending)` correctly
widens the BM25 candidate pool for author-scoped searches. Non-finding.

**`BM25Index._dirty` flag invariant**: `_dirty=True` with `_pending=[]` is impossible in
normal usage. Non-finding.

**All R12/R13/R14 non-findings**: Re-examined and confirmed still correct. No regressions.

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
# 258 passed in 10.19s  (256 pre-existing + 2 new R15 regression tests)
```
