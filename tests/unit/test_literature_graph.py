"""tests/unit/test_literature_graph.py — Knowledge graph, retraction, and contradiction detection tests.

Zero network calls. All OpenAlex calls mocked.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from maglab.literature.graph import (
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
)


@pytest.fixture
def tmp_graph(tmp_path: Path) -> KnowledgeGraph:
    """Return a temporary file-backed KnowledgeGraph."""
    db = tmp_path / "test_graph.db"
    return KnowledgeGraph(db_path=db)


# ---------------------------------------------------------------------------
# Node API
# ---------------------------------------------------------------------------


class TestGraphNode:
    def test_add_and_get_node(self, tmp_graph: KnowledgeGraph):
        node = GraphNode(
            node_id="mat:CoFeB",
            node_type="material",
            label="CoFeB",
            properties={"Ms_Am": 1.1e6},
        )
        assert tmp_graph.add_node(node) is True
        retrieved = tmp_graph.get_node("mat:CoFeB")
        assert retrieved is not None
        assert retrieved.label == "CoFeB"
        assert retrieved.properties["Ms_Am"] == pytest.approx(1.1e6)

    def test_add_duplicate_node_returns_false(self, tmp_graph: KnowledgeGraph):
        node = GraphNode(node_id="mat:Ta", node_type="material", label="Ta")
        tmp_graph.add_node(node)
        result = tmp_graph.add_node(node)
        assert result is False

    def test_get_nonexistent_node_returns_none(self, tmp_graph: KnowledgeGraph):
        assert tmp_graph.get_node("mat:Nonexistent") is None

    def test_find_nodes_by_label(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(
            GraphNode(node_id="n1", node_type="material", label="IrMn antiferromagnet")
        )
        tmp_graph.add_node(GraphNode(node_id="n2", node_type="phenomenon", label="Exchange Bias"))
        nodes = tmp_graph.find_nodes("IrMn")
        assert any(n.node_id == "n1" for n in nodes)

    def test_find_nodes_by_type_filter(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="m1", node_type="material", label="Co"))
        tmp_graph.add_node(GraphNode(node_id="p1", node_type="phenomenon", label="Co effect"))
        materials = tmp_graph.find_nodes("Co", node_type="material")
        phenomena = tmp_graph.find_nodes("Co", node_type="phenomenon")
        assert all(n.node_type == "material" for n in materials)
        assert all(n.node_type == "phenomenon" for n in phenomena)


# ---------------------------------------------------------------------------
# Edge API
# ---------------------------------------------------------------------------


class TestGraphEdge:
    def test_add_and_retrieve_edge(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="A", node_type="paper", label="Paper A"))
        tmp_graph.add_node(GraphNode(node_id="B", node_type="paper", label="Paper B"))
        edge = GraphEdge(
            edge_id="e1",
            source_id="A",
            target_id="B",
            edge_type="extends",
            evidence_doi="10.1234/test",
        )
        assert tmp_graph.add_edge(edge) is True

    def test_get_neighbors_outgoing(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="src", node_type="paper", label="Src"))
        tmp_graph.add_node(GraphNode(node_id="dst", node_type="paper", label="Dst"))
        edge = GraphEdge(
            edge_id="e_out",
            source_id="src",
            target_id="dst",
            edge_type="applies",
            evidence_doi="10.0/x",
        )
        tmp_graph.add_edge(edge)
        neighbors = tmp_graph.get_neighbors("src", direction="out")
        assert len(neighbors) == 1
        e, n = neighbors[0]
        assert n.node_id == "dst"
        assert e.edge_type == "applies"

    def test_edge_type_filter(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="X", node_type="paper", label="X"))
        tmp_graph.add_node(GraphNode(node_id="Y", node_type="paper", label="Y"))
        tmp_graph.add_node(GraphNode(node_id="Z", node_type="paper", label="Z"))
        tmp_graph.add_edge(
            GraphEdge(
                edge_id="e1", source_id="X", target_id="Y", edge_type="extends", evidence_doi=""
            )
        )
        tmp_graph.add_edge(
            GraphEdge(
                edge_id="e2", source_id="X", target_id="Z", edge_type="contradicts", evidence_doi=""
            )
        )

        extends = tmp_graph.get_neighbors("X", edge_type="extends", direction="out")
        assert len(extends) == 1
        assert extends[0][1].node_id == "Y"

    def test_citation_lineage_by_doi(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="PA", node_type="paper", label="PA"))
        tmp_graph.add_node(GraphNode(node_id="PB", node_type="paper", label="PB"))
        doi = "10.1234/lineage"
        edge = GraphEdge(
            edge_id="el1", source_id="PA", target_id="PB", edge_type="extends", evidence_doi=doi
        )
        tmp_graph.add_edge(edge)
        lineage = tmp_graph.citation_lineage(doi)
        assert len(lineage) == 1
        assert lineage[0].evidence_doi == doi


# ---------------------------------------------------------------------------
# Contradiction detection (§14.6)
# ---------------------------------------------------------------------------


class TestContradictionDetection:
    def test_no_contradiction_first_report(self, tmp_graph: KnowledgeGraph):
        flags = tmp_graph.report_property("CoFeB", "Ms_Am", 1.1e6, unit="A/m", doi="10.1234/a")
        assert flags == []

    def test_contradiction_detected_on_large_diff(self, tmp_graph: KnowledgeGraph):
        tmp_graph.report_property("Ta", "theta_SH", -0.15, doi="10.1103/a")
        flags = tmp_graph.report_property("Ta", "theta_SH", -0.07, doi="10.1103/b")
        assert len(flags) >= 1
        flag = flags[0]
        assert flag.material == "Ta"
        assert flag.property_name == "theta_SH"
        assert flag.flagged is True
        assert flag.relative_diff >= 0.5

    def test_no_contradiction_small_diff(self, tmp_graph: KnowledgeGraph):
        tmp_graph.report_property("Py", "alpha", 0.007, doi="10.1234/x")
        flags = tmp_graph.report_property("Py", "alpha", 0.0072, doi="10.1234/y")
        # 2% difference → below 50% threshold → no contradiction
        assert flags == []

    def test_contradicts_edge_created(self, tmp_graph: KnowledgeGraph):
        tmp_graph.report_property("Pt", "theta_SH", 0.08, doi="10.1103/a")
        tmp_graph.report_property("Pt", "theta_SH", 0.03, doi="10.1103/b")
        edges = tmp_graph.contradicts_edges()
        assert len(edges) >= 1
        assert all(e.edge_type == "contradicts" for e in edges)


# ---------------------------------------------------------------------------
# Retraction check (§14.6)
# ---------------------------------------------------------------------------


class TestRetractionCheck:
    @patch.object(KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="ok")
    def test_ok_paper_not_blocked(self, mock_oa, tmp_graph: KnowledgeGraph):
        result = tmp_graph.check_retraction("10.1234/ok-paper")
        assert result.is_blocked is False
        assert result.retraction_status == "ok"
        assert result.warnings == []

    @patch.object(KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="retracted")
    def test_retracted_paper_blocked(self, mock_oa, tmp_graph: KnowledgeGraph):
        result = tmp_graph.check_retraction("10.1234/retracted-paper")
        assert result.is_blocked is True
        assert result.retraction_status == "retracted"
        assert len(result.warnings) > 0

    def test_manual_cache_retracted(self, tmp_graph: KnowledgeGraph):
        doi = "10.9999/manual-retracted"
        tmp_graph.set_retraction_cache(doi, "retracted")
        # Should read from cache — blocked without OA call
        with patch.object(
            KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="ok"
        ) as mock_oa:
            result = tmp_graph.check_retraction(doi)
            # Cache takes priority → OA not called
            mock_oa.assert_not_called()
        assert result.is_blocked is True

    def test_manual_cache_ok(self, tmp_graph: KnowledgeGraph):
        doi = "10.9999/manual-ok"
        tmp_graph.set_retraction_cache(doi, "ok")
        with patch.object(
            KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="retracted"
        ) as mock_oa:
            result = tmp_graph.check_retraction(doi)
            mock_oa.assert_not_called()
        assert result.is_blocked is False

    @patch.object(KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="unknown")
    def test_unknown_status_not_blocked(self, mock_oa, tmp_graph: KnowledgeGraph):
        result = tmp_graph.check_retraction("10.1234/unknown")
        assert result.is_blocked is False
        assert result.retraction_status == "unknown"

    @patch.object(KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="retracted")
    def test_batch_integrity_check(self, mock_oa, tmp_graph: KnowledgeGraph):
        dois = ["10.1234/retracted", "10.5678/good"]
        results = tmp_graph.check_integrity_batch(dois)
        assert len(results) == 2

    def test_withdrawn_also_blocked(self, tmp_graph: KnowledgeGraph):
        doi = "10.9999/withdrawn"
        tmp_graph.set_retraction_cache(doi, "withdrawn")
        result = tmp_graph.check_retraction(doi)
        assert result.is_blocked is True


# ---------------------------------------------------------------------------
# Path search
# ---------------------------------------------------------------------------


class TestPathSearch:
    def test_direct_path(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="A", node_type="material", label="A"))
        tmp_graph.add_node(GraphNode(node_id="B", node_type="phenomenon", label="B"))
        tmp_graph.add_edge(
            GraphEdge(
                edge_id="e_AB", source_id="A", target_id="B", edge_type="uses", evidence_doi=""
            )
        )
        paths = tmp_graph.path_search("A", "B", max_depth=3)
        assert any("B" in p for p in paths)

    def test_no_path_returns_empty(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="X", node_type="material", label="X"))
        tmp_graph.add_node(GraphNode(node_id="Y", node_type="material", label="Y"))
        paths = tmp_graph.path_search("X", "Y", max_depth=3)
        assert paths == []


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestGraphStats:
    def test_stats_empty(self, tmp_graph: KnowledgeGraph):
        s = tmp_graph.stats()
        assert s["nodes"] == 0
        assert s["edges"] == 0
        assert s["contradicts_edges"] == 0

    def test_stats_after_insert(self, tmp_graph: KnowledgeGraph):
        tmp_graph.add_node(GraphNode(node_id="n1", node_type="material", label="Co"))
        tmp_graph.add_node(GraphNode(node_id="n2", node_type="material", label="Fe"))
        tmp_graph.add_edge(
            GraphEdge(
                edge_id="e1", source_id="n1", target_id="n2", edge_type="uses", evidence_doi=""
            )
        )
        s = tmp_graph.stats()
        assert s["nodes"] == 2
        assert s["edges"] == 1


# ---------------------------------------------------------------------------
# Regression tests — F2: retraction cache must respect a TTL
# ---------------------------------------------------------------------------


class TestF2RetractionCacheTTL:
    """Regression tests for F2: the retraction_cache table stores checked_at
    but previously that timestamp was never compared to the current time, so a
    cached 'ok' entry persisted indefinitely — even if the paper was later
    retracted.

    After the fix, a cache entry older than _RETRACTION_CACHE_TTL_S is treated
    as stale and the status is re-fetched from OpenAlex.
    """

    def test_fresh_cache_entry_not_refetched(self, tmp_graph: KnowledgeGraph) -> None:
        """A cache entry written seconds ago is still fresh — OA is not called."""
        doi = "10.9999/ttl-fresh"
        tmp_graph.set_retraction_cache(doi, "ok")  # writes checked_at = now
        with patch.object(
            KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="retracted"
        ) as mock_oa:
            result = tmp_graph.check_retraction(doi)
            mock_oa.assert_not_called()
        assert result.is_blocked is False, (
            "Fresh cache entry should be used — OA should not have been called."
        )

    def test_stale_cache_entry_triggers_refetch(self, tmp_graph: KnowledgeGraph) -> None:
        """A cache entry older than the TTL is stale — OA is re-called.

        Inject a row with checked_at set far in the past (8 days ago) directly
        into the DB to simulate a stale entry without sleeping.
        """
        doi = "10.9999/ttl-stale"
        doi_norm = doi.lower()
        stale_ts = time.time() - 8 * 86400  # 8 days ago — beyond the 7-day TTL

        # Write a stale 'ok' entry directly into the cache table
        tmp_graph._conn.execute(
            "INSERT OR REPLACE INTO retraction_cache (doi, status, checked_at) VALUES (?,?,?)",
            (doi_norm, "ok", stale_ts),
        )
        tmp_graph._conn.commit()

        # OA now says the paper is retracted — must be returned after re-fetch
        with patch.object(
            KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="retracted"
        ) as mock_oa:
            result = tmp_graph.check_retraction(doi)
            mock_oa.assert_called_once_with(doi_norm)

        assert result.is_blocked is True, (
            "Stale cache entry was used instead of re-fetching from OA. "
            "The F2 TTL fix may be missing."
        )
        assert result.retraction_status == "retracted"

    def test_stale_ok_paper_now_retracted_is_blocked(self, tmp_graph: KnowledgeGraph) -> None:
        """End-to-end: paper initially 'ok', cache goes stale, paper is now
        retracted — check_retraction must return is_blocked=True.
        """
        doi = "10.9999/stale-then-retracted"
        doi_norm = doi.lower()

        # Simulate a first check that happened 10 days ago (stale)
        past_ts = time.time() - 10 * 86400
        tmp_graph._conn.execute(
            "INSERT OR REPLACE INTO retraction_cache (doi, status, checked_at) VALUES (?,?,?)",
            (doi_norm, "ok", past_ts),
        )
        tmp_graph._conn.commit()

        with patch.object(
            KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="retracted"
        ):
            result = tmp_graph.check_retraction(doi)

        assert result.is_blocked is True, (
            "Paper retracted after its first check must be blocked once the "
            "cache entry expires (F2 TTL regression)."
        )


# ---------------------------------------------------------------------------
# Regression tests — F5: check_retraction normalizes all DOI prefix forms
# ---------------------------------------------------------------------------


class TestF5RetractionDOINormalization:
    """Regression tests for F5: check_retraction only stripped the https://
    prefix before the fix.  http:// and doi: forms were cached separately,
    allowing the same paper to have two independent (potentially conflicting)
    cache entries.
    """

    @patch.object(KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="ok")
    def test_https_prefix_stripped(self, mock_oa, tmp_graph: KnowledgeGraph) -> None:
        result = tmp_graph.check_retraction("https://doi.org/10.1234/f5-test")
        assert result.doi == "10.1234/f5-test"

    @patch.object(KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="ok")
    def test_http_prefix_stripped(self, mock_oa, tmp_graph: KnowledgeGraph) -> None:
        result = tmp_graph.check_retraction("http://doi.org/10.1234/f5-test")
        assert result.doi == "10.1234/f5-test"

    @patch.object(KnowledgeGraph, "_fetch_retraction_status_from_oa", return_value="ok")
    def test_doi_colon_prefix_stripped(self, mock_oa, tmp_graph: KnowledgeGraph) -> None:
        result = tmp_graph.check_retraction("doi:10.1234/f5-test")
        assert result.doi == "10.1234/f5-test"

    def test_all_prefix_forms_share_cache_entry(self, tmp_graph: KnowledgeGraph) -> None:
        """All three prefix variants of the same DOI must hit the same cache row."""
        doi_bare = "10.9999/f5-shared"
        tmp_graph.set_retraction_cache(doi_bare, "retracted")

        call_count = 0

        def counting_oa(doi: str) -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        with patch.object(
            KnowledgeGraph, "_fetch_retraction_status_from_oa", side_effect=counting_oa
        ):
            r1 = tmp_graph.check_retraction(f"https://doi.org/{doi_bare}")
            r2 = tmp_graph.check_retraction(f"http://doi.org/{doi_bare}")
            r3 = tmp_graph.check_retraction(f"doi:{doi_bare}")

        # All three must read the same cache row — OA must not be called at all
        assert call_count == 0, (
            f"OA was called {call_count} time(s); all three prefix forms should "
            "resolve to the same cache entry (F5 normalization fix)."
        )
        assert r1.retraction_status == r2.retraction_status == r3.retraction_status == "retracted"


# ---------------------------------------------------------------------------
# Regression tests — F6: DOI-less contradictions get unique node IDs
# ---------------------------------------------------------------------------


class TestF6DoiLessContraNodeIds:
    """Regression tests for F6: when doi is empty, report_property previously
    created node_id='paper:unknown' for every DOI-less paper, so all
    contradictions between DOI-less papers shared the same edge_id and were
    silently dropped after the first one.
    """

    def test_doi_less_contradictions_are_not_dropped(self, tmp_graph: KnowledgeGraph) -> None:
        """Two pairs of DOI-less contradicting papers must each produce an edge."""
        # First contradiction: Paper-A vs Paper-B (both no DOI, different titles)
        tmp_graph.report_property("Pt", "theta_SH", 0.08, doi="", title="Paper-A Pt measurement")
        tmp_graph.report_property("Pt", "theta_SH", 0.02, doi="", title="Paper-B Pt measurement")

        # Second contradiction: Paper-C vs Paper-D (different property, different titles)
        tmp_graph.report_property("Pt", "theta_SH", 0.09, doi="", title="Paper-C Pt higher")

        edges = tmp_graph.contradicts_edges()
        # Before F6 fix: only 1 edge (subsequent ones silently dropped by IntegrityError).
        # After fix: at least 2 edges for the two distinct contradictions.
        assert len(edges) >= 2, (
            f"Expected at least 2 contradiction edges for DOI-less papers, got {len(edges)}. "
            "The F6 unique-node-id fix may be missing."
        )

    def test_doi_present_and_doi_less_papers_dont_collapse(self, tmp_graph: KnowledgeGraph) -> None:
        """A paper with a DOI must not share a node with a DOI-less paper."""
        tmp_graph.report_property("CoFeB", "Ms_Am", 1.1e6, doi="10.1103/a", title="Paper with DOI")
        flags = tmp_graph.report_property(
            "CoFeB", "Ms_Am", 3.0e6, doi="", title="Paper without DOI"
        )
        assert len(flags) >= 1
        flag = flags[0]
        # doi_a should be the DOI from the first paper, doi_b should be empty
        assert flag.doi_a == "10.1103/a"
        assert flag.doi_b == ""

        edges = tmp_graph.contradicts_edges()
        assert len(edges) >= 1
        edge = edges[0]
        # The DOI-less paper's node must not be "paper:unknown"
        doi_less_side = edge.source_id if edge.target_id == "paper:10.1103/a" else edge.target_id
        assert doi_less_side != "paper:unknown", (
            "DOI-less paper node collapsed to 'paper:unknown' (F6 bug)."
        )
        assert doi_less_side.startswith("paper:noid-"), (
            f"Expected DOI-less node to start with 'paper:noid-', got: {doi_less_side}"
        )


# ---------------------------------------------------------------------------
# Regression tests — R14: report_property auto-creates paper nodes
# ---------------------------------------------------------------------------


class TestR14ContradictionPaperNodesCreated:
    """Regression tests for R14: report_property() previously inserted contradiction
    edges whose source_id/target_id referenced paper nodes that did not exist in the
    nodes table.  get_neighbors() silently returned [] for those node IDs because
    get_node() returned None.

    After the fix, report_property() uses INSERT OR IGNORE to create the paper nodes
    before adding the edge, so graph traversal finds the expected neighbors.
    """

    def test_contradiction_paper_nodes_exist_in_nodes_table(
        self, tmp_graph: KnowledgeGraph
    ) -> None:
        """After a contradiction is detected, both paper nodes must exist in the
        nodes table so that get_node() returns a non-None result."""
        tmp_graph.report_property("CoFeB", "Ms_Am", 1.1e6, doi="10.1234/r14-a", title="Paper R14-A")
        flags = tmp_graph.report_property(
            "CoFeB", "Ms_Am", 3.0e6, doi="10.1234/r14-b", title="Paper R14-B"
        )
        assert len(flags) == 1, "Expected exactly one contradiction flag"

        node_a = tmp_graph.get_node("paper:10.1234/r14-a")
        node_b = tmp_graph.get_node("paper:10.1234/r14-b")
        assert node_a is not None, (
            "Paper node 'paper:10.1234/r14-a' not found — report_property() must "
            "auto-create paper nodes before adding contradiction edges (R14 fix)."
        )
        assert node_b is not None, (
            "Paper node 'paper:10.1234/r14-b' not found — report_property() must "
            "auto-create paper nodes before adding contradiction edges (R14 fix)."
        )
        assert node_a.node_type == "paper"
        assert node_b.node_type == "paper"

    def test_get_neighbors_traverses_contradiction_edges(self, tmp_graph: KnowledgeGraph) -> None:
        """get_neighbors() on a paper node created via report_property() must
        return the connected contradicting paper — not [] as before the fix."""
        tmp_graph.report_property("Ta", "theta_SH", -0.15, doi="10.1103/r14-x", title="Paper X")
        flags = tmp_graph.report_property(
            "Ta", "theta_SH", -0.05, doi="10.1103/r14-y", title="Paper Y"
        )
        assert len(flags) == 1

        # Paper X's node should be reachable as a neighbor of Paper Y via the
        # 'contradicts' edge (source=paper-Y, target=paper-X).
        neighbors = tmp_graph.get_neighbors(
            "paper:10.1103/r14-y", edge_type="contradicts", direction="out"
        )
        assert len(neighbors) == 1, (
            f"Expected 1 neighbor for 'paper:10.1103/r14-y' via 'contradicts', "
            f"got {len(neighbors)}.  The R14 paper-node auto-create fix may be missing."
        )
        _edge, neighbor_node = neighbors[0]
        assert neighbor_node.node_id == "paper:10.1103/r14-x"

    def test_existing_richer_node_not_overwritten(self, tmp_graph: KnowledgeGraph) -> None:
        """INSERT OR IGNORE must not overwrite an existing paper node that was
        added with richer metadata via add_node()."""
        from maglab.literature.graph import GraphNode

        # Add the node explicitly with richer properties first
        richer_node = GraphNode(
            node_id="paper:10.9999/rich",
            node_type="paper",
            label="Rich Paper Label",
            properties={"citation_count": 500, "venue": "PRL"},
        )
        tmp_graph.add_node(richer_node)

        # Report a contradiction that would trigger INSERT OR IGNORE for the same node
        tmp_graph.report_property("Py", "alpha", 0.005, doi="10.9999/rich", title="Fallback Label")
        flags = tmp_graph.report_property(
            "Py", "alpha", 0.020, doi="10.9999/other", title="Other Paper"
        )
        assert len(flags) == 1

        # The richer node must be unchanged
        retrieved = tmp_graph.get_node("paper:10.9999/rich")
        assert retrieved is not None
        assert retrieved.label == "Rich Paper Label", (
            f"Rich paper node label was overwritten: got {retrieved.label!r}"
        )
        assert retrieved.properties.get("citation_count") == 500, (
            "Rich paper node properties were lost after INSERT OR IGNORE."
        )

    def test_doi_less_paper_nodes_created_for_contradiction(
        self, tmp_graph: KnowledgeGraph
    ) -> None:
        """DOI-less papers (using noid-hash node IDs) must also have nodes created."""
        tmp_graph.report_property("Pt", "theta_SH", 0.08, doi="", title="Noid-Paper-Alpha")
        flags = tmp_graph.report_property("Pt", "theta_SH", 0.02, doi="", title="Noid-Paper-Beta")
        assert len(flags) == 1

        # Both noid nodes must exist
        edges = tmp_graph.contradicts_edges()
        assert len(edges) == 1
        edge = edges[0]
        node_src = tmp_graph.get_node(edge.source_id)
        node_tgt = tmp_graph.get_node(edge.target_id)
        assert node_src is not None, f"Source node {edge.source_id!r} missing"
        assert node_tgt is not None, f"Target node {edge.target_id!r} missing"


# ---------------------------------------------------------------------------
# Regression tests — R15: INSERT OR IGNORE paper nodes are committed before
#                          add_edge() so they survive a duplicate-edge failure
# ---------------------------------------------------------------------------


class TestR15NodeCommitBeforeAddEdge:
    """Regression tests for R15: report_property() previously inserted paper
    nodes with INSERT OR IGNORE but did not commit them before calling
    add_edge().  When add_edge() raised IntegrityError (duplicate edge_id),
    it returned False without calling commit(), causing SQLite to roll back
    the uncommitted INSERT OR IGNORE rows.  The result was that a paper node
    could re-appear as missing even though report_property() ran without error.

    After the fix, self._conn.commit() is called immediately after the two
    INSERT OR IGNORE statements and before add_edge(), so the node rows are
    durable regardless of whether the edge insertion succeeds or fails.
    """

    def test_paper_nodes_committed_even_when_edge_is_duplicate(
        self, tmp_graph: KnowledgeGraph
    ) -> None:
        """If the same contradiction is reported twice (duplicate edge_id) and
        the nodes are missing, the second call must still persist both nodes."""
        # First contradiction — nodes and edge committed successfully.
        tmp_graph.report_property("Pt", "theta_SH", 0.08, doi="10.1103/r15-a", title="Paper R15-A")
        tmp_graph.report_property("Pt", "theta_SH", 0.02, doi="10.1103/r15-b", title="Paper R15-B")
        assert tmp_graph.get_node("paper:10.1103/r15-b") is not None

        # Manually remove node_b to create an inconsistent state.
        tmp_graph._conn.execute("DELETE FROM nodes WHERE node_id = ?", ("paper:10.1103/r15-b",))
        tmp_graph._conn.commit()
        assert tmp_graph.get_node("paper:10.1103/r15-b") is None, "Setup: node_b should be gone"

        # Report the identical contradiction a second time.
        # add_edge() will fail with IntegrityError (duplicate edge_id).
        # Before fix: INSERT OR IGNORE node_b was rolled back -> still missing.
        # After fix: INSERT OR IGNORE node_b is committed first -> durable.
        tmp_graph.report_property("Pt", "theta_SH", 0.08, doi="10.1103/r15-a", title="Paper R15-A")
        tmp_graph.report_property("Pt", "theta_SH", 0.02, doi="10.1103/r15-b", title="Paper R15-B")

        node_b = tmp_graph.get_node("paper:10.1103/r15-b")
        assert node_b is not None, (
            "Paper node 'paper:10.1103/r15-b' was rolled back when add_edge() failed with "
            "IntegrityError (duplicate edge_id). The R15 commit-before-add_edge fix may be missing."
        )
        assert node_b.node_type == "paper"

    def test_get_neighbors_works_after_duplicate_edge_report(
        self, tmp_graph: KnowledgeGraph
    ) -> None:
        """get_neighbors() must return results after the duplicate-edge scenario.

        Uses values that produce ≥50% relative difference to guarantee a
        contradiction (1.0e6 vs 3.0e6 → 66.7% ≥ threshold=50%).
        """
        # Establish initial contradiction (1e6 vs 3e6 → 66.7% → above threshold).
        tmp_graph.report_property("Fe", "Ms_Am", 1.0e6, doi="10.1103/r15-c", title="Paper R15-C")
        tmp_graph.report_property("Fe", "Ms_Am", 3.0e6, doi="10.1103/r15-d", title="Paper R15-D")
        assert tmp_graph.get_node("paper:10.1103/r15-c") is not None

        # Delete both nodes to simulate inconsistency.
        tmp_graph._conn.execute("DELETE FROM nodes")
        tmp_graph._conn.commit()
        assert tmp_graph.get_node("paper:10.1103/r15-c") is None, "Setup: nodes should be gone"

        # Re-report only the FIRST value so the second call later detects a contradiction
        # against it.  This avoids the edge-duplicate path: we need at least one call
        # where add_edge() would fail (same edge_id) while the target node is missing.
        tmp_graph.report_property("Fe", "Ms_Am", 1.0e6, doi="10.1103/r15-c", title="Paper R15-C")

        # Delete node_c again — it was just created by the re-report above.
        # Now report r15-d against the PREVIOUSLY STORED rows which include the
        # old 1e6 row AND the new 1e6 row.  The contradiction edge for the *first*
        # pair (old r15-c vs r15-d) has edge_id = contra_r15-d_r15-c_Ms_Am and still
        # exists in the edges table, so add_edge() will fail.
        # The nodes for both r15-c and r15-d must be committed before add_edge().
        tmp_graph._conn.execute("DELETE FROM nodes WHERE node_id = ?", ("paper:10.1103/r15-c",))
        tmp_graph._conn.commit()

        tmp_graph.report_property("Fe", "Ms_Am", 3.0e6, doi="10.1103/r15-d", title="Paper R15-D")

        # Both nodes must be present and traversable.
        node_c = tmp_graph.get_node("paper:10.1103/r15-c")
        node_d = tmp_graph.get_node("paper:10.1103/r15-d")
        assert node_c is not None, (
            "paper:10.1103/r15-c was rolled back when add_edge() raised IntegrityError — "
            "the R15 commit-before-add_edge fix may be missing."
        )
        assert node_d is not None, "paper:10.1103/r15-d was not created"

        neighbors = tmp_graph.get_neighbors(
            "paper:10.1103/r15-d", edge_type="contradicts", direction="out"
        )
        assert len(neighbors) >= 1, (
            "get_neighbors() returned [] even though both paper nodes exist — "
            "the R15 commit fix may not have persisted the nodes correctly."
        )
