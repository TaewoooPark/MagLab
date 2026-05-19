"""W3C PROV SQLite store — audit layer (§17).

Records all artefacts (Entity), activities (Activity), and agents (Agent) as
W3C PROV triples and persists them in SQLite.  Provides JSON-LD-compatible
export (PROV-JSON format).

Design principles:
- Attach ``wasGeneratedBy``, ``wasDerivedFrom``, and ``wasAttributedTo`` to
  every Entity.
- LLM calls are also recorded as first-class Activity entities.
- Deterministic — no LLM calls.
"""

from __future__ import annotations

import io
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import prov.model as pm
import prov.serializers.provjson as provjson

# Default MagLab namespace
_NS_URI = "https://maglab.science/prov/"
_NS_PREFIX = "ml"

# MagLab agent identifier (constant — system agent)
_MAGLAB_AGENT = "maglab-system"

# SQLite schema (single table: PROV JSON serialised and stored as chunks)
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prov_records (
    id          TEXT    PRIMARY KEY,
    kind        TEXT    NOT NULL,  -- entity | activity | agent | relation
    prov_json   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS prov_graph (
    id          TEXT    PRIMARY KEY,
    graph_json  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _fresh_document() -> pm.ProvDocument:
    """Initialise a new ProvDocument and register the MagLab namespace."""
    doc = pm.ProvDocument()
    doc.add_namespace(_NS_PREFIX, _NS_URI)
    return doc


def _qname(local: str) -> str:
    """Return the prefixed form of a local name."""
    return f"{_NS_PREFIX}:{local}"


def _serialize_doc(doc: pm.ProvDocument) -> str:
    """Serialise a ProvDocument to a PROV-JSON string."""
    buf = io.StringIO()
    s = provjson.ProvJSONSerializer(doc)
    s.serialize(buf)
    return buf.getvalue()


class ProvenanceStore:
    """SQLite-backed W3C PROV audit store.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Use ``:memory:`` for an in-memory DB.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        # Per-session ProvDocument — snapshot saved to DB on flush
        self._doc: pm.ProvDocument = _fresh_document()
        self._ns = pm.Namespace(_NS_PREFIX, _NS_URI)
        # Register MagLab system agent
        self._doc.agent(self._ns[_MAGLAB_AGENT])

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA_SQL)

    def _qn(self, local: str) -> pm.QualifiedName:
        """Local name → namespace-qualified ``QualifiedName``."""
        return self._ns[local]

    # ------------------------------------------------------------------
    # Public API — Entity / Activity / Agent registration
    # ------------------------------------------------------------------

    def add_entity(
        self,
        local_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> pm.QualifiedName:
        """Add a new Entity to the document and return its ID.

        Parameters
        ----------
        local_id:
            Local identifier.  If it already exists, the existing entity is returned.
        attributes:
            Additional PROV attribute dictionary to attach to the Entity.
        """
        qn = self._qn(local_id)
        attrs: list[tuple[pm.QualifiedName, Any]] = []
        if attributes:
            for k, v in attributes.items():
                attrs.append((self._qn(k), v))
        self._doc.entity(qn, other_attributes=attrs if attrs else None)
        self._flush_to_db(qn, "entity", attributes=attributes)
        return qn

    def add_activity(
        self,
        local_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> pm.QualifiedName:
        """Add a new Activity to the document."""
        qn = self._qn(local_id)
        attrs: list[tuple[pm.QualifiedName, Any]] = []
        if attributes:
            for k, v in attributes.items():
                attrs.append((self._qn(k), v))
        self._doc.activity(
            qn,
            startTime=start_time,
            endTime=end_time,
            other_attributes=attrs if attrs else None,
        )
        self._flush_to_db(qn, "activity", attributes=attributes)
        return qn

    def add_agent(
        self, local_id: str, attributes: dict[str, Any] | None = None
    ) -> pm.QualifiedName:
        """Add a new Agent to the document."""
        qn = self._qn(local_id)
        attrs: list[tuple[pm.QualifiedName, Any]] = []
        if attributes:
            for k, v in attributes.items():
                attrs.append((self._qn(k), v))
        self._doc.agent(qn, other_attributes=attrs if attrs else None)
        self._flush_to_db(qn, "agent", attributes=attributes)
        return qn

    # ------------------------------------------------------------------
    # Relationship recording
    # ------------------------------------------------------------------

    def was_generated_by(
        self,
        entity_id: str,
        activity_id: str,
        time: datetime | None = None,
    ) -> None:
        """Record that an Entity was generated by an Activity."""
        self._doc.wasGeneratedBy(
            self._qn(entity_id),
            self._qn(activity_id),
            time=time or datetime.now(UTC),
        )
        self._flush_to_db(self._qn(f"wgb-{entity_id}-{activity_id}"), "relation")

    def was_derived_from(self, generated_entity_id: str, used_entity_id: str) -> None:
        """Record that an Entity was derived from another Entity."""
        self._doc.wasDerivedFrom(
            self._qn(generated_entity_id),
            self._qn(used_entity_id),
        )
        self._flush_to_db(self._qn(f"wdf-{generated_entity_id}-{used_entity_id}"), "relation")

    def was_attributed_to(self, entity_id: str, agent_id: str = _MAGLAB_AGENT) -> None:
        """Attribute an Entity to an Agent."""
        self._doc.wasAttributedTo(
            self._qn(entity_id),
            self._qn(agent_id),
        )
        self._flush_to_db(self._qn(f"wat-{entity_id}-{agent_id}"), "relation")

    # ------------------------------------------------------------------
    # LLM call recording (first-class Activity)
    # ------------------------------------------------------------------

    def record_llm_call(
        self,
        model: str,
        prompt_summary: str,
        result_entity_id: str | None = None,
    ) -> pm.QualifiedName:
        """Record an LLM call as an Activity.

        Parameters
        ----------
        model:
            LLM model identifier (e.g. ``"claude-3-5-sonnet"``).
        prompt_summary:
            Summary of the prompt (storing the full prompt is prohibited —
            cost and privacy concerns).
        result_entity_id:
            Entity ID produced by the LLM output (if any); linked via
            ``wasGeneratedBy``.
        """
        call_id = f"llm-call-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        qn = self.add_activity(
            call_id,
            start_time=now,
            attributes={"model": model, "prompt_summary": prompt_summary, "kind": "llm-call"},
        )
        if result_entity_id:
            self.was_generated_by(result_entity_id, call_id, time=now)
            self.was_attributed_to(result_entity_id)
        return qn

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_entity_lineage(self, local_id: str) -> list[dict[str, Any]]:
        """Return all PROV records connected to the given Entity.

        Matches:
        - The entity row itself (``id = 'ml:<local_id>'``).
        - Relation rows whose ID encodes the entity's local name:
          ``wgb-<entity>-*``, ``wdf-<entity>-*``, ``wdf-*-<entity>``,
          ``wat-<entity>-*``.

        This replaces the former full-document LIKE scan, which returned
        unrelated rows because every row stored the entire graph snapshot.
        """
        qn_str = _qname(local_id)
        ns_prefix = f"{_NS_PREFIX}:"
        # Build relation ID prefix patterns for this entity's local name.
        # Relation IDs are stored as "ml:wgb-<eid>-<aid>" etc.
        relation_prefixes = [
            f"{ns_prefix}wgb-{local_id}-%",   # wasGeneratedBy: entity is subject
            f"{ns_prefix}wdf-{local_id}-%",   # wasDerivedFrom: entity was derived
            f"{ns_prefix}wdf-%-{local_id}",   # wasDerivedFrom: entity is the used source
            f"{ns_prefix}wat-{local_id}-%",   # wasAttributedTo: entity is subject
        ]
        rows: list[dict[str, Any]] = []
        # 1. The entity/activity/agent row itself
        cursor = self._conn.execute(
            "SELECT id, kind, prov_json, created_at FROM prov_records WHERE id = ?",
            (qn_str,),
        )
        rows.extend(dict(row) for row in cursor.fetchall())
        # 2. Relation rows that name this entity in their ID
        for pattern in relation_prefixes:
            cursor = self._conn.execute(
                "SELECT id, kind, prov_json, created_at FROM prov_records WHERE id LIKE ?",
                (pattern,),
            )
            rows.extend(dict(row) for row in cursor.fetchall())
        # Deduplicate while preserving order (row ids are unique)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for row in rows:
            if row["id"] not in seen:
                seen.add(row["id"])
                result.append(row)
        return result

    def list_entities(self) -> list[str]:
        """Return the list of registered Entity local IDs."""
        cursor = self._conn.execute("SELECT id FROM prov_records WHERE kind = 'entity'")
        prefix = f"{_NS_PREFIX}:"
        result = []
        for row in cursor.fetchall():
            rid = row["id"]
            if rid.startswith(prefix):
                result.append(rid[len(prefix) :])
        return result

    # ------------------------------------------------------------------
    # JSON-LD / PROV-JSON export
    # ------------------------------------------------------------------

    def export_json(self) -> dict[str, Any]:
        """Export the full current document as a PROV-JSON (W3C PROV-compatible) dictionary."""
        raw = _serialize_doc(self._doc)
        return json.loads(raw)

    def export_json_str(self) -> str:
        """Export the full current document as a PROV-JSON string."""
        return _serialize_doc(self._doc)

    def snapshot(self) -> pm.ProvDocument:
        """Return a snapshot of the current ProvDocument (read-only reference)."""
        return self._doc

    # ------------------------------------------------------------------
    # Internal: DB flush
    # ------------------------------------------------------------------

    def _flush_to_db(
        self,
        qn: pm.QualifiedName,
        kind: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Persist a record to the DB (upsert).

        ``prov_records`` stores only the IDs and attributes that are *directly*
        referenced by this record — not the full document snapshot.  The full
        document is kept in ``prov_graph`` for export-only use.

        The ``prov_json`` column for each row is a JSON object of the form
        ``{"id": "<qualified-name>", "kind": "entity|activity|agent|relation",
        **attributes}`` so that:
        - The lineage LIKE query matches only rows whose *own* ``id`` column
          matches the requested entity (no false positives from full-document
          dumps).
        - Callers of ``get_entity_lineage()`` receive the per-record attributes
          (``provenance_type``, ``units``, ``source_ref``, ``timestamp``, …)
          directly from the returned ``prov_json`` field — §17 invariant is met.
        """
        record_id = str(qn)
        # Store per-record JSON: id + kind + caller-supplied attributes.
        # The LIKE patterns in get_entity_lineage match on the *id* column, not
        # on prov_json, so including attributes here does NOT reintroduce the
        # old false-positive problem that was fixed in R3.
        record_json = json.dumps({"id": record_id, "kind": kind, **(attributes or {})})
        graph_json = _serialize_doc(self._doc)
        now = _now_iso()
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO prov_records (id, kind, prov_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, kind, record_json, now),
            )
            self._conn.execute(
                """
                INSERT OR REPLACE INTO prov_graph (id, graph_json, created_at)
                VALUES ('current', ?, ?)
                """,
                (graph_json, now),
            )

    def close(self) -> None:
        """Close the DB connection."""
        self._conn.close()

    def __enter__(self) -> ProvenanceStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
