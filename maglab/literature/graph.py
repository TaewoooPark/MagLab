"""Magnetism knowledge graph · typed citation lineage · literature integrity checks (§14.6).

Nodes: material, phenomenon, property, method, device.
Edges: extends / applies / evaluates / contradicts / uses.
Literature integrity: retraction checks + contradiction detection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

import platformdirs
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
_APP = "maglab"

# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

NodeType = Literal["material", "phenomenon", "property", "method", "device", "paper"]
EdgeType = Literal["extends", "applies", "evaluates", "contradicts", "uses", "reports"]


# ---------------------------------------------------------------------------
# Graph schema
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """Knowledge graph node."""

    node_id: str
    """Unique node ID."""
    node_type: NodeType
    """Node type."""
    label: str
    """Display label (material name, phenomenon name, etc.)."""
    properties: dict[str, Any] = Field(default_factory=dict)
    """Additional attributes (values, units, DOI, etc.)."""


class GraphEdge(BaseModel):
    """Knowledge graph edge — includes citation lineage type."""

    edge_id: str
    """Unique edge ID."""
    source_id: str
    """Source node ID."""
    target_id: str
    """Target node ID."""
    edge_type: EdgeType
    """Relationship type."""
    evidence_doi: str = ""
    """DOI of the paper reporting this relationship."""
    evidence_title: str = ""
    """Title of the paper reporting this relationship."""
    properties: dict[str, Any] = Field(default_factory=dict)
    """Additional attributes."""


class ContradictionFlag(BaseModel):
    """Contradiction detection result."""

    node_id: str
    """Property value node ID."""
    property_name: str
    """Property name (e.g. 'Ms', 'alpha')."""
    material: str
    """Target material."""
    value_a: float
    """First reported value."""
    doi_a: str
    """First paper DOI."""
    value_b: float
    """Second reported value."""
    doi_b: str
    """Second paper DOI."""
    relative_diff: float
    """Relative difference = |a-b|/max(|a|,|b|)."""
    flagged: bool = True


# ---------------------------------------------------------------------------
# Integrity check result
# ---------------------------------------------------------------------------


class IntegrityResult(BaseModel):
    """Integrity check result for a single paper."""

    doi: str
    retraction_status: str = "unknown"
    is_blocked: bool = False
    warnings: list[str] = Field(default_factory=list)
    contradiction_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Graph DB
# ---------------------------------------------------------------------------


def _graph_db_path() -> Path:
    d = Path(platformdirs.user_data_dir(_APP)) / "literature"
    d.mkdir(parents=True, exist_ok=True)
    return d / "knowledge_graph.db"


class KnowledgeGraph:
    """Magnetism knowledge graph — SQLite-based adjacency list.

    Parameters
    ----------
    db_path:
        SQLite file path (None uses the default path).
    """

    # Retraction statuses that cause a block
    BLOCKED_RETRACTION_STATUSES = frozenset({"retracted", "withdrawn"})
    # Contradiction detection threshold (relative difference %)
    CONTRADICTION_THRESHOLD = 0.5

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _graph_db_path()
        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                node_id     TEXT PRIMARY KEY,
                node_type   TEXT NOT NULL,
                label       TEXT NOT NULL,
                properties  TEXT NOT NULL DEFAULT '{}',
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                edge_id       TEXT PRIMARY KEY,
                source_id     TEXT NOT NULL,
                target_id     TEXT NOT NULL,
                edge_type     TEXT NOT NULL,
                evidence_doi  TEXT NOT NULL DEFAULT '',
                evidence_title TEXT NOT NULL DEFAULT '',
                properties    TEXT NOT NULL DEFAULT '{}',
                created_at    REAL NOT NULL,
                FOREIGN KEY (source_id) REFERENCES nodes(node_id),
                FOREIGN KEY (target_id) REFERENCES nodes(node_id)
            );
            CREATE TABLE IF NOT EXISTS retraction_cache (
                doi             TEXT PRIMARY KEY,
                status          TEXT NOT NULL DEFAULT 'unknown',
                checked_at      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS property_reports (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                material      TEXT NOT NULL,
                property_name TEXT NOT NULL,
                value         REAL NOT NULL,
                unit          TEXT NOT NULL DEFAULT '',
                doi           TEXT NOT NULL DEFAULT '',
                title         TEXT NOT NULL DEFAULT '',
                reported_at   REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
            CREATE INDEX IF NOT EXISTS idx_prop_material ON property_reports(material, property_name);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Node API
    # ------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> bool:
        """Add a node. Returns False if it already exists."""
        try:
            self._conn.execute(
                "INSERT INTO nodes (node_id, node_type, label, properties, created_at) "
                "VALUES (?,?,?,?,?)",
                (
                    node.node_id,
                    node.node_type,
                    node.label,
                    json.dumps(node.properties),
                    time.time(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_node(self, node_id: str) -> GraphNode | None:
        """Retrieve a node by ID."""
        row = self._conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if row is None:
            return None
        return GraphNode(
            node_id=row["node_id"],
            node_type=row["node_type"],  # type: ignore[arg-type]
            label=row["label"],
            properties=json.loads(row["properties"]),
        )

    def find_nodes(self, label_query: str, node_type: NodeType | None = None) -> list[GraphNode]:
        """Search nodes by label."""
        if node_type:
            rows = self._conn.execute(
                "SELECT * FROM nodes WHERE label LIKE ? AND node_type = ?",
                (f"%{label_query}%", node_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM nodes WHERE label LIKE ?",
                (f"%{label_query}%",),
            ).fetchall()
        return [
            GraphNode(
                node_id=r["node_id"],
                node_type=r["node_type"],  # type: ignore[arg-type]
                label=r["label"],
                properties=json.loads(r["properties"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Edge API
    # ------------------------------------------------------------------

    def add_edge(self, edge: GraphEdge) -> bool:
        """Add an edge."""
        try:
            self._conn.execute(
                "INSERT INTO edges "
                "(edge_id, source_id, target_id, edge_type, evidence_doi, "
                "evidence_title, properties, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    edge.edge_id,
                    edge.source_id,
                    edge.target_id,
                    edge.edge_type,
                    edge.evidence_doi,
                    edge.evidence_title,
                    json.dumps(edge.properties),
                    time.time(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_neighbors(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
        direction: Literal["out", "in", "both"] = "both",
    ) -> list[tuple[GraphEdge, GraphNode]]:
        """Return neighboring nodes and edges for a given node."""
        results: list[tuple[GraphEdge, GraphNode]] = []

        def _fetch(sql: str, params: tuple) -> None:
            for row in self._conn.execute(sql, params).fetchall():
                neighbor_id = row["target_id"] if row["source_id"] == node_id else row["source_id"]
                neighbor = self.get_node(neighbor_id)
                if neighbor:
                    e = GraphEdge(
                        edge_id=row["edge_id"],
                        source_id=row["source_id"],
                        target_id=row["target_id"],
                        edge_type=row["edge_type"],  # type: ignore[arg-type]
                        evidence_doi=row["evidence_doi"],
                        evidence_title=row["evidence_title"],
                        properties=json.loads(row["properties"]),
                    )
                    results.append((e, neighbor))

        if direction in ("out", "both"):
            sql = "SELECT * FROM edges WHERE source_id = ?"
            params: tuple = (node_id,)
            if edge_type:
                sql += " AND edge_type = ?"
                params = (node_id, edge_type)
            _fetch(sql, params)

        if direction in ("in", "both"):
            sql = "SELECT * FROM edges WHERE target_id = ?"
            params = (node_id,)
            if edge_type:
                sql += " AND edge_type = ?"
                params = (node_id, edge_type)
            _fetch(sql, params)

        return results

    def citation_lineage(self, doi: str) -> list[GraphEdge]:
        """Return citation lineage edges for a given paper DOI."""
        rows = self._conn.execute("SELECT * FROM edges WHERE evidence_doi = ?", (doi,)).fetchall()
        return [
            GraphEdge(
                edge_id=r["edge_id"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                edge_type=r["edge_type"],  # type: ignore[arg-type]
                evidence_doi=r["evidence_doi"],
                evidence_title=r["evidence_title"],
                properties=json.loads(r["properties"]),
            )
            for r in rows
        ]

    def contradicts_edges(self) -> list[GraphEdge]:
        """Return all contradicts-type edges."""
        rows = self._conn.execute("SELECT * FROM edges WHERE edge_type = 'contradicts'").fetchall()
        return [
            GraphEdge(
                edge_id=r["edge_id"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                edge_type="contradicts",
                evidence_doi=r["evidence_doi"],
                evidence_title=r["evidence_title"],
                properties=json.loads(r["properties"]),
            )
            for r in rows
        ]

    def path_search(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 4,
    ) -> list[list[str]]:
        """BFS path search between two nodes.

        Returns
        -------
        List of node ID paths (multiple paths possible).
        """
        from collections import deque  # noqa: PLC0415

        queue: deque[list[str]] = deque([[start_id]])
        visited: set[str] = {start_id}
        paths: list[list[str]] = []

        while queue:
            path = queue.popleft()
            if len(path) > max_depth:
                break
            current = path[-1]
            neighbors = self.get_neighbors(current, direction="out")
            for _, neighbor in neighbors:
                nid = neighbor.node_id
                if nid == end_id:
                    paths.append(path + [nid])
                elif nid not in visited:
                    visited.add(nid)
                    queue.append(path + [nid])

        return paths

    # ------------------------------------------------------------------
    # Property value reporting (for contradiction detection)
    # ------------------------------------------------------------------

    def report_property(
        self,
        material: str,
        property_name: str,
        value: float,
        unit: str = "",
        doi: str = "",
        title: str = "",
    ) -> list[ContradictionFlag]:
        """Record a property value and detect contradictions with existing reports.

        Parameters
        ----------
        material:
            Material name.
        property_name:
            Property name (e.g. 'Ms', 'alpha').
        value:
            Reported value.
        unit:
            Unit.
        doi:
            Source DOI.
        title:
            Source paper title.

        Returns
        -------
        List of detected contradiction flags.
        """
        # Query existing reported values
        existing = self._conn.execute(
            "SELECT * FROM property_reports WHERE material = ? AND property_name = ?",
            (material, property_name),
        ).fetchall()

        # Save new reported value
        self._conn.execute(
            "INSERT INTO property_reports "
            "(material, property_name, value, unit, doi, title, reported_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (material, property_name, value, unit, doi, title, time.time()),
        )
        self._conn.commit()

        # Detect contradictions
        flags: list[ContradictionFlag] = []
        for row in existing:
            existing_val = row["value"]
            max_abs = max(abs(value), abs(existing_val))
            if max_abs == 0:
                continue
            rel_diff = abs(value - existing_val) / max_abs
            if rel_diff >= self.CONTRADICTION_THRESHOLD:
                flag = ContradictionFlag(
                    node_id=f"{material}_{property_name}",
                    property_name=property_name,
                    material=material,
                    value_a=existing_val,
                    doi_a=row["doi"],
                    value_b=value,
                    doi_b=doi,
                    relative_diff=rel_diff,
                )
                flags.append(flag)
                # Create a contradicts edge.  F6: DOI-less papers must not all
                # collapse to "paper:unknown" (that would cause every DOI-less
                # contradiction to share the same edge_id and be silently
                # dropped).  Use a 12-hex-char MD5 of the title as a unique
                # fallback when DOI is absent.
                def _paper_node_id(d: str, t: str) -> str:
                    if d:
                        return f"paper:{d}"
                    h = hashlib.md5(t.encode()).hexdigest()[:12]
                    return f"paper:noid-{h}"

                node_a_id = _paper_node_id(row["doi"], row["title"])
                node_b_id = _paper_node_id(doi, title)

                # Ensure both paper nodes exist in the nodes table so that
                # get_neighbors() can resolve them during graph traversal.
                # INSERT OR IGNORE avoids overwriting existing richer node data
                # (e.g. nodes added explicitly via add_node()).
                self._conn.execute(
                    "INSERT OR IGNORE INTO nodes "
                    "(node_id, node_type, label, properties, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (node_a_id, "paper", row["title"] or row["doi"] or node_a_id,
                     "{}", time.time()),
                )
                self._conn.execute(
                    "INSERT OR IGNORE INTO nodes "
                    "(node_id, node_type, label, properties, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (node_b_id, "paper", title or doi or node_b_id,
                     "{}", time.time()),
                )
                # Commit the node rows immediately so they are durable regardless
                # of whether add_edge() succeeds or raises IntegrityError (duplicate
                # edge).  Without this commit, a duplicate-edge IntegrityError in
                # add_edge() would silently roll back the INSERT OR IGNORE node rows,
                # leaving the graph in an inconsistent state where an edge references
                # nodes that do not exist in the nodes table.
                self._conn.commit()

                edge = GraphEdge(
                    edge_id=f"contra_{node_a_id}_{node_b_id}_{property_name}",
                    source_id=node_b_id,
                    target_id=node_a_id,
                    edge_type="contradicts",
                    evidence_doi=doi,
                    evidence_title=title,
                    properties={
                        "property": property_name,
                        "material": material,
                        "relative_diff": rel_diff,
                    },
                )
                self.add_edge(edge)
                log.warning(
                    "Contradiction detected: %s '%s' — existing %.3g (%s) vs new %.3g (%s), diff=%.0f%%",
                    material,
                    property_name,
                    existing_val,
                    row["doi"],
                    value,
                    doi,
                    rel_diff * 100,
                )
        return flags

    # ------------------------------------------------------------------
    # Literature integrity checks (§14.6)
    # ------------------------------------------------------------------

    # Cache TTL: 7 days in seconds.  After this period a cached entry is
    # considered stale and the retraction status is re-fetched from OpenAlex.
    _RETRACTION_CACHE_TTL_S: int = 7 * 86400

    def check_retraction(self, doi: str) -> IntegrityResult:
        """Retraction check — block or warn on retracted/corrected papers.

        1. Check local cache (respects a 7-day TTL — stale entries are
           re-fetched so a paper retracted after its first check is caught).
        2. Query OpenAlex ``retraction_status`` (if pyalex is available).
        3. Set ``is_blocked=True`` if status is a blocked status.
        """
        # F5: apply the same three-prefix normalization as corpus.py:get_by_doi()
        doi_norm = (
            doi.lower()
            .replace("https://doi.org/", "")
            .replace("http://doi.org/", "")
            .replace("doi:", "")
        )
        result = IntegrityResult(doi=doi_norm)

        # Check cache — include checked_at for TTL evaluation (F2)
        cached = self._conn.execute(
            "SELECT status, checked_at FROM retraction_cache WHERE doi = ?", (doi_norm,)
        ).fetchone()
        if cached and (time.time() - cached["checked_at"] < self._RETRACTION_CACHE_TTL_S):
            # Cache hit within TTL window — use stored status
            status = cached["status"]
        else:
            # Cache miss or stale entry — re-fetch from OpenAlex
            status = self._fetch_retraction_status_from_oa(doi_norm)
            self._conn.execute(
                "INSERT OR REPLACE INTO retraction_cache (doi, status, checked_at) VALUES (?,?,?)",
                (doi_norm, status, time.time()),
            )
            self._conn.commit()

        result.retraction_status = status
        if status in self.BLOCKED_RETRACTION_STATUSES:
            result.is_blocked = True
            result.warnings.append(
                f"[Integrity blocked] DOI '{doi_norm}' has status '{status}'. "
                f"Entry into the KB and authoring citation pipeline is blocked (§14.6)."
            )
            log.warning("Retraction blocked: doi=%s, status=%s", doi_norm, status)

        return result

    def check_integrity_batch(self, dois: list[str]) -> list[IntegrityResult]:
        """Perform integrity checks on multiple DOIs in bulk."""
        return [self.check_retraction(doi) for doi in dois]

    @staticmethod
    def _fetch_retraction_status_from_oa(doi: str) -> str:
        """Query retraction status from OpenAlex."""
        try:
            import pyalex  # noqa: PLC0415

            work = pyalex.Works()[f"https://doi.org/{doi}"]
            if work is None:
                return "unknown"
            if work.get("is_retracted"):
                return "retracted"
            return "ok"
        except ImportError:
            return "unknown"
        except Exception as exc:  # noqa: BLE001
            log.debug("OpenAlex retraction lookup failed (doi=%s): %s", doi, exc)
            return "unknown"

    def set_retraction_cache(self, doi: str, status: str) -> None:
        """For testing/manual use: set the retraction cache entry directly."""
        doi_norm = (
            doi.lower()
            .replace("https://doi.org/", "")
            .replace("http://doi.org/", "")
            .replace("doi:", "")
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO retraction_cache (doi, status, checked_at) VALUES (?,?,?)",
            (doi_norm, status, time.time()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """Return graph statistics."""
        n_nodes = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        n_edges = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        n_contra = self._conn.execute(
            "SELECT COUNT(*) FROM edges WHERE edge_type='contradicts'"
        ).fetchone()[0]
        n_retracted = self._conn.execute(
            "SELECT COUNT(*) FROM retraction_cache WHERE status='retracted'"
        ).fetchone()[0]
        return {
            "nodes": n_nodes,
            "edges": n_edges,
            "contradicts_edges": n_contra,
            "retracted_cached": n_retracted,
        }

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Module-level default instance
# ---------------------------------------------------------------------------

_default_graph: KnowledgeGraph | None = None


def get_graph(db_path: Path | None = None) -> KnowledgeGraph:
    """Return the default KnowledgeGraph instance."""
    global _default_graph
    if db_path is not None:
        return KnowledgeGraph(db_path)
    if _default_graph is None:
        _default_graph = KnowledgeGraph()
    return _default_graph
