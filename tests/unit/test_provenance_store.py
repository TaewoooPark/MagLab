"""tests/unit/test_provenance_store.py — ProvenanceStore and ProvenanceLedger tests."""

from __future__ import annotations

import json
import sqlite3

import pytest

import maglab.provenance.store as store_mod
from maglab.provenance.datapoint import DataPoint, ProvenanceType
from maglab.provenance.ledger import ProvenanceLedger
from maglab.provenance.store import ProvenanceStore

# ---------------------------------------------------------------------------
# ProvenanceStore — basic behaviour
# ---------------------------------------------------------------------------


class TestProvenanceStore:
    """ProvenanceStore basic PROV recording and retrieval tests."""

    @pytest.fixture()
    def store(self) -> ProvenanceStore:
        return ProvenanceStore(":memory:")

    def test_add_entity(self, store: ProvenanceStore):
        qn = store.add_entity("entity-001")
        assert "ml:entity-001" in str(qn)

    def test_add_activity(self, store: ProvenanceStore):
        qn = store.add_activity("activity-001")
        assert qn is not None

    def test_add_agent(self, store: ProvenanceStore):
        qn = store.add_agent("custom-agent")
        assert qn is not None

    def test_was_generated_by(self, store: ProvenanceStore):
        store.add_entity("result-entity")
        store.add_activity("compute-activity")
        store.was_generated_by("result-entity", "compute-activity")
        lineage = store.get_entity_lineage("result-entity")
        assert len(lineage) >= 1

    def test_was_derived_from(self, store: ProvenanceStore):
        store.add_entity("source-entity")
        store.add_entity("derived-entity")
        store.was_derived_from("derived-entity", "source-entity")
        lineage = store.get_entity_lineage("derived-entity")
        assert len(lineage) >= 1

    def test_was_attributed_to(self, store: ProvenanceStore):
        store.add_entity("my-entity")
        store.was_attributed_to("my-entity")  # default MagLab agent
        lineage = store.get_entity_lineage("my-entity")
        assert len(lineage) >= 1

    def test_list_entities(self, store: ProvenanceStore):
        store.add_entity("ent-a")
        store.add_entity("ent-b")
        entities = store.list_entities()
        assert "ent-a" in entities
        assert "ent-b" in entities

    def test_record_llm_call(self, store: ProvenanceStore):
        store.add_entity("llm-result")
        qn = store.record_llm_call(
            model="claude-3-5-sonnet",
            prompt_summary="exchange length calculation request",
            result_entity_id="llm-result",
        )
        assert qn is not None

    def test_context_manager(self):
        with ProvenanceStore(":memory:") as s:
            s.add_entity("test-entity")
        # Cannot reuse after close (ProgrammingError or OperationalError)
        import sqlite3

        with pytest.raises((sqlite3.ProgrammingError, sqlite3.OperationalError)):
            s.add_entity("after-close")


# ---------------------------------------------------------------------------
# JSON-LD export
# ---------------------------------------------------------------------------


class TestProvenanceStoreExport:
    """PROV-JSON (W3C PROV compatible) export tests."""

    @pytest.fixture()
    def populated_store(self) -> ProvenanceStore:
        s = ProvenanceStore(":memory:")
        s.add_entity("entity-1", attributes={"type": "DataPoint"})
        s.add_entity("entity-2")
        s.add_activity("activity-1")
        s.add_agent("researcher-agent")
        s.was_generated_by("entity-2", "activity-1")
        s.was_derived_from("entity-2", "entity-1")
        s.was_attributed_to("entity-2", "researcher-agent")
        return s

    def test_export_json_is_dict(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert isinstance(result, dict)

    def test_export_json_str_is_string(self, populated_store: ProvenanceStore):
        result = populated_store.export_json_str()
        assert isinstance(result, str)
        # Must be parseable JSON
        obj = json.loads(result)
        assert isinstance(obj, dict)

    def test_export_has_entity_key(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert "entity" in result

    def test_export_has_activity_key(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert "activity" in result

    def test_export_has_agent_key(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert "agent" in result

    def test_export_has_was_generated_by(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert "wasGeneratedBy" in result

    def test_export_has_was_derived_from(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert "wasDerivedFrom" in result

    def test_export_has_was_attributed_to(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert "wasAttributedTo" in result

    def test_export_has_prefix(self, populated_store: ProvenanceStore):
        result = populated_store.export_json()
        assert "prefix" in result
        # Check MagLab namespace
        assert "ml" in result["prefix"]

    def test_full_lineage_roundtrip(self, populated_store: ProvenanceStore):
        """Verify that Entity 2's lineage includes Entity 1 and Activity 1."""
        lineage = populated_store.get_entity_lineage("entity-2")
        assert len(lineage) >= 1

    def test_snapshot_returns_document(self, populated_store: ProvenanceStore):
        doc = populated_store.snapshot()
        import prov.model as pm

        assert isinstance(doc, pm.ProvDocument)


# ---------------------------------------------------------------------------
# ProvenanceLedger — high-level API
# ---------------------------------------------------------------------------


class TestProvenanceLedger:
    """ProvenanceLedger high-level API tests."""

    @pytest.fixture()
    def ledger(self) -> ProvenanceLedger:
        return ProvenanceLedger()

    def _make_dp(
        self, value: float = 1.0, ptype: ProvenanceType = ProvenanceType.SIMULATED
    ) -> DataPoint:
        return DataPoint(
            value=value,
            units="T",
            provenance_type=ptype,
            source_ref="10.1000/test" if ptype is ProvenanceType.LITERATURE else "test-ref",
        )

    def test_record_datapoint_returns_id(self, ledger: ProvenanceLedger):
        dp = self._make_dp()
        dp_id = ledger.record_datapoint(dp)
        assert dp_id == dp.id

    def test_get_cached_datapoint(self, ledger: ProvenanceLedger):
        dp = self._make_dp(value=3.14)
        ledger.record_datapoint(dp)
        retrieved = ledger.get(dp.id)
        assert retrieved is dp

    def test_get_unknown_returns_none(self, ledger: ProvenanceLedger):
        assert ledger.get("nonexistent-id") is None

    def test_record_with_derived_from(self, ledger: ProvenanceLedger):
        dp1 = self._make_dp(value=1.0)
        dp2 = self._make_dp(value=2.0)
        ledger.record_datapoint(dp1)
        ledger.record_datapoint(dp2, derived_from_ids=[dp1.id])
        # Lineage record must exist
        lineage = ledger.lineage(dp2.id)
        assert len(lineage) >= 1

    def test_chain_linear(self, ledger: ProvenanceLedger):
        dp1 = self._make_dp(value=1.0)
        dp2 = self._make_dp(value=2.0)
        dp3 = self._make_dp(value=3.0)
        ids = ledger.chain(dp1, dp2, dp3, activity_description="sequential derivation")
        assert ids == [dp1.id, dp2.id, dp3.id]
        # All must be in the cache
        for did in ids:
            assert ledger.get(did) is not None

    def test_query_by_type(self, ledger: ProvenanceLedger):
        dp_sim = self._make_dp(ptype=ProvenanceType.SIMULATED)
        dp_meas = DataPoint(value=1.0, units="T", provenance_type=ProvenanceType.MEASURED)
        ledger.record_datapoint(dp_sim)
        ledger.record_datapoint(dp_meas)
        sim_list = ledger.query_by_type(ProvenanceType.SIMULATED)
        assert dp_sim in sim_list
        assert dp_meas not in sim_list

    def test_query_by_units(self, ledger: ProvenanceLedger):
        dp_t = DataPoint(value=1.0, units="T", provenance_type=ProvenanceType.SIMULATED)
        dp_am = DataPoint(value=1e5, units="A/m", provenance_type=ProvenanceType.SIMULATED)
        ledger.record_datapoint(dp_t)
        ledger.record_datapoint(dp_am)
        assert dp_t in ledger.query_by_units("T")
        assert dp_am not in ledger.query_by_units("T")

    def test_all_ids(self, ledger: ProvenanceLedger):
        dp1 = self._make_dp(value=1.0)
        dp2 = self._make_dp(value=2.0)
        ledger.record_datapoint(dp1)
        ledger.record_datapoint(dp2)
        ids = ledger.all_ids()
        assert dp1.id in ids
        assert dp2.id in ids

    def test_record_llm_call(self, ledger: ProvenanceLedger):
        dp = self._make_dp()
        ledger.record_datapoint(dp)
        act_id = ledger.record_llm_call(
            model="claude-3-5-sonnet",
            prompt_summary="analysis request",
            result_datapoint_id=dp.id,
        )
        assert act_id is not None

    def test_export_json(self, ledger: ProvenanceLedger):
        dp = self._make_dp()
        ledger.record_datapoint(dp)
        result = ledger.export_json()
        assert isinstance(result, dict)
        assert "entity" in result

    def test_export_json_str(self, ledger: ProvenanceLedger):
        dp = self._make_dp()
        ledger.record_datapoint(dp)
        s = ledger.export_json_str()
        obj = json.loads(s)
        assert "entity" in obj

    def test_store_property(self, ledger: ProvenanceLedger):
        assert isinstance(ledger.store, ProvenanceStore)

    def test_custom_store_injection(self):
        custom_store = ProvenanceStore(":memory:")
        ledger = ProvenanceLedger(store=custom_store)
        assert ledger.store is custom_store


# ---------------------------------------------------------------------------
# PROV lineage W3C schema validation
# ---------------------------------------------------------------------------


class TestProvenanceW3CCompliance:
    """Check that generated JSON conforms to the W3C PROV-JSON key structure."""

    def test_w3c_prov_json_structure(self):
        store = ProvenanceStore(":memory:")
        store.add_entity("data-e1")
        store.add_activity("sim-run-1")
        store.add_agent("researcher")
        store.was_generated_by("data-e1", "sim-run-1")
        store.was_attributed_to("data-e1", "researcher")

        doc = store.export_json()
        # W3C PROV-JSON mandatory top-level keys
        assert "prefix" in doc
        assert "entity" in doc
        assert "activity" in doc
        assert "agent" in doc
        assert "wasGeneratedBy" in doc
        assert "wasAttributedTo" in doc

    def test_namespace_prefix_is_maglab(self):
        store = ProvenanceStore(":memory:")
        store.add_entity("test-ns")
        doc = store.export_json()
        # ml namespace must be present
        prefixes = doc.get("prefix", {})
        assert "ml" in prefixes
        assert "maglab" in prefixes["ml"].lower()


# ---------------------------------------------------------------------------
# REGRESSION TESTS — Finding 1: lineage must not return unrelated entities
# ---------------------------------------------------------------------------


class TestLineageAccuracy:
    """Regression tests for Finding 1 — ProvenanceStore.get_entity_lineage precision.

    Before the fix, every prov_records row stored the full serialised ProvDocument.
    A LIKE '%ml:eX%' query would match ALL rows once entity eX appeared anywhere in
    the document, returning unrelated relations (e.g. wasDerivedFrom(e2, e1) when
    querying lineage for e3).  The fix stores per-record IDs so the query is precise.
    """

    def test_lineage_does_not_bleed_to_unrelated_entity(self):
        """querying lineage for e3 must NOT return the wdf(e2, e1) relation row."""
        store = ProvenanceStore(":memory:")
        store.add_entity("e1")
        store.add_entity("e2")
        store.add_entity("e3")
        store.was_derived_from("e2", "e1")  # wdf-e2-e1 relation; has nothing to do with e3

        lineage_e3 = store.get_entity_lineage("e3")
        # e3 lineage must contain only e3's own record — not the e2/e1 relation
        ids = [row["id"] for row in lineage_e3]
        assert not any("wdf-e2-e1" in rid or "wdf" in rid for rid in ids), (
            f"lineage(e3) must not include wdf-e2-e1, but got: {ids}"
        )

    def test_lineage_returns_own_relation_rows(self):
        """querying lineage for e2 must include the wdf(e2, e1) relation."""
        store = ProvenanceStore(":memory:")
        store.add_entity("e1")
        store.add_entity("e2")
        store.was_derived_from("e2", "e1")

        lineage_e2 = store.get_entity_lineage("e2")
        ids = [row["id"] for row in lineage_e2]
        assert any("wdf-e2-e1" in rid for rid in ids), (
            f"lineage(e2) must include wdf-e2-e1, got: {ids}"
        )

    def test_lineage_returns_source_entity_relation(self):
        """querying lineage for e1 (the used source) includes the wdf(e2, e1) row."""
        store = ProvenanceStore(":memory:")
        store.add_entity("e1")
        store.add_entity("e2")
        store.was_derived_from("e2", "e1")

        lineage_e1 = store.get_entity_lineage("e1")
        ids = [row["id"] for row in lineage_e1]
        assert any("wdf" in rid and "e1" in rid for rid in ids), (
            f"lineage(e1) must include wdf relation, got: {ids}"
        )

    def test_lineage_was_generated_by_precision(self):
        """wasGeneratedBy row for (result, activity) appears only in result's lineage."""
        store = ProvenanceStore(":memory:")
        store.add_entity("result")
        store.add_entity("unrelated")
        store.add_activity("compute")
        store.was_generated_by("result", "compute")

        lineage_result = store.get_entity_lineage("result")
        lineage_unrelated = store.get_entity_lineage("unrelated")

        result_ids = [row["id"] for row in lineage_result]
        unrelated_ids = [row["id"] for row in lineage_unrelated]

        assert any("wgb-result-compute" in rid for rid in result_ids), (
            f"lineage(result) must include wgb-result-compute, got: {result_ids}"
        )
        assert not any("wgb-result-compute" in rid for rid in unrelated_ids), (
            f"lineage(unrelated) must not include wgb-result-compute, got: {unrelated_ids}"
        )

    def test_lineage_was_attributed_to_precision(self):
        """wasAttributedTo for (entity, agent) appears only in entity's lineage."""
        store = ProvenanceStore(":memory:")
        store.add_entity("my-entity")
        store.add_entity("other-entity")
        store.was_attributed_to("my-entity")

        lineage_mine = store.get_entity_lineage("my-entity")
        lineage_other = store.get_entity_lineage("other-entity")

        mine_ids = [row["id"] for row in lineage_mine]
        other_ids = [row["id"] for row in lineage_other]

        assert any("wat-my-entity" in rid for rid in mine_ids), (
            f"lineage(my-entity) must include wat-my-entity, got: {mine_ids}"
        )
        assert not any("wat-my-entity" in rid for rid in other_ids), (
            f"lineage(other-entity) must not include wat-my-entity, got: {other_ids}"
        )


# ---------------------------------------------------------------------------
# REGRESSION TESTS — Finding 1 R5: prov_json must carry entity attributes
# ---------------------------------------------------------------------------


class TestLineageAttributesInProvJson:
    """Regression tests for R5 Finding 1.

    After _flush_to_db was fixed to store per-record attributes in prov_json,
    get_entity_lineage() must return the entity's provenance_type / units /
    source_ref / timestamp, AND the LIKE-query false-positive isolation test
    must still pass (no cross-entity bleed).
    """

    def test_entity_attributes_present_in_lineage_prov_json(self):
        """prov_json for the entity row must contain provenance_type, units, source_ref, timestamp."""
        store = ProvenanceStore(":memory:")
        attrs = {
            "provenance_type": "MEASURED",
            "units": "A/m",
            "source_ref": "DOI:10.1234/x",
            "timestamp": "2025-01-01T00:00:00+00:00",
        }
        store.add_entity("dp-123", attributes=attrs)

        lineage = store.get_entity_lineage("dp-123")
        assert len(lineage) >= 1, "lineage must contain at least the entity row"

        # Find the entity row itself
        entity_rows = [row for row in lineage if row["id"] == "ml:dp-123"]
        assert len(entity_rows) == 1, f"entity row missing, got ids: {[r['id'] for r in lineage]}"

        prov_data = json.loads(entity_rows[0]["prov_json"])
        assert prov_data.get("provenance_type") == "MEASURED", (
            f"provenance_type missing/wrong in prov_json: {prov_data}"
        )
        assert prov_data.get("units") == "A/m", f"units missing/wrong in prov_json: {prov_data}"
        assert prov_data.get("source_ref") == "DOI:10.1234/x", (
            f"source_ref missing/wrong in prov_json: {prov_data}"
        )
        assert prov_data.get("timestamp") == "2025-01-01T00:00:00+00:00", (
            f"timestamp missing/wrong in prov_json: {prov_data}"
        )

    def test_activity_attributes_present_in_lineage_prov_json(self):
        """prov_json for the activity row must contain its attributes."""
        store = ProvenanceStore(":memory:")
        store.add_activity(
            "act-001",
            attributes={"description": "field sweep", "model": "OOMMF"},
        )

        lineage = store.get_entity_lineage("act-001")
        assert len(lineage) >= 1

        activity_rows = [row for row in lineage if row["id"] == "ml:act-001"]
        assert len(activity_rows) == 1

        prov_data = json.loads(activity_rows[0]["prov_json"])
        assert prov_data.get("description") == "field sweep"
        assert prov_data.get("model") == "OOMMF"

    def test_no_attribute_bleed_to_unrelated_entity(self):
        """Attributes stored in prov_json must NOT cause false-positive LIKE matches.

        When entity 'dp-abc' has attributes in prov_json, querying lineage for
        an unrelated entity 'dp-xyz' must NOT return dp-abc's row, even though
        dp-abc's prov_json now contains attribute text.
        """
        store = ProvenanceStore(":memory:")
        store.add_entity("dp-abc", attributes={"provenance_type": "MEASURED", "units": "T"})
        store.add_entity("dp-xyz", attributes={"provenance_type": "SIMULATED", "units": "A/m"})
        store.was_derived_from("dp-abc", "dp-xyz")

        # querying lineage for an entirely unrelated third entity
        store.add_entity("dp-zzz")
        lineage_zzz = store.get_entity_lineage("dp-zzz")
        ids_zzz = [row["id"] for row in lineage_zzz]

        assert not any("dp-abc" in rid or "dp-xyz" in rid or "wdf" in rid for rid in ids_zzz), (
            f"lineage(dp-zzz) must not include dp-abc or dp-xyz rows, got: {ids_zzz}"
        )

    def test_ledger_record_datapoint_lineage_has_attributes(self):
        """ProvenanceLedger.lineage() must return rows with provenance attributes in prov_json."""
        ledger = ProvenanceLedger()
        from maglab.provenance.datapoint import DataPoint, ProvenanceType

        dp = DataPoint(
            value=42.0,
            units="T",
            provenance_type=ProvenanceType.MEASURED,
            source_ref="DOI:10.9999/test",
        )
        ledger.record_datapoint(dp)

        lineage = ledger.lineage(dp.id)
        entity_rows = [row for row in lineage if row["id"] == f"ml:{dp.id}"]
        assert len(entity_rows) == 1, (
            f"entity row for dp.id={dp.id} missing; got: {[r['id'] for r in lineage]}"
        )

        prov_data = json.loads(entity_rows[0]["prov_json"])
        assert prov_data.get("provenance_type") == ProvenanceType.MEASURED.value, (
            f"provenance_type missing in prov_json: {prov_data}"
        )
        assert prov_data.get("units") == "T", f"units missing in prov_json: {prov_data}"
        assert prov_data.get("source_ref") == "DOI:10.9999/test", (
            f"source_ref missing in prov_json: {prov_data}"
        )


# ---------------------------------------------------------------------------
# Recording cost — the export snapshot must not be rebuilt per record
# ---------------------------------------------------------------------------


class TestRecordingDoesNotRescanTheWholeDocument:
    """Guards the O(N²) regression: recording re-serialised the full document.

    ``_flush_to_db`` used to dump the entire (growing) ProvDocument on *every*
    entity, activity and relation, so a session of N records cost O(N²) — about
    0.5 ms/record at 25 records but 2.8 ms/record at 200. The snapshot is
    export-only, so it is now refreshed on export and on close instead.
    """

    def test_recording_never_serialises_the_document(self, monkeypatch) -> None:
        calls: list[int] = []
        real = store_mod._serialize_doc

        def counting(doc):
            calls.append(1)
            return real(doc)

        monkeypatch.setattr(store_mod, "_serialize_doc", counting)

        store = ProvenanceStore()
        for i in range(25):
            store.add_entity(f"dp-{i}", attributes={"units": "T"})
            store.was_attributed_to(f"dp-{i}")

        assert calls == [], "recording must not serialise the full PROV document"
        store.close()

    def test_export_serialises_exactly_once(self, monkeypatch) -> None:
        calls: list[int] = []
        real = store_mod._serialize_doc

        def counting(doc):
            calls.append(1)
            return real(doc)

        store = ProvenanceStore()
        store.add_entity("dp-1", attributes={"units": "T"})
        monkeypatch.setattr(store_mod, "_serialize_doc", counting)

        store.export_json_str()

        assert len(calls) == 1, "export must not dump the document twice"
        store.close()

    def test_snapshot_is_persisted_on_export(self) -> None:
        store = ProvenanceStore()
        store.add_entity("dp-1", attributes={"units": "T"})
        exported = store.export_json_str()

        row = store._conn.execute("SELECT graph_json FROM prov_graph WHERE id='current'").fetchone()
        assert row is not None, "prov_graph snapshot missing after export"
        assert row["graph_json"] == exported
        store.close()

    def test_snapshot_is_persisted_on_close(self, tmp_path) -> None:
        db = tmp_path / "prov.db"
        store = ProvenanceStore(db)
        store.add_entity("dp-x", attributes={"units": "T"})
        store.close()

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT graph_json FROM prov_graph WHERE id='current'").fetchone()
            assert row is not None, "prov_graph snapshot missing after close"
            assert "dp-x" in row["graph_json"]
        finally:
            conn.close()

    def test_close_survives_an_unwritable_database(self, tmp_path) -> None:
        """Teardown must not raise just because the snapshot cannot be written."""
        store = ProvenanceStore(tmp_path / "prov.db")
        store.add_entity("dp-1")
        store._conn.close()  # simulate a DB that has gone away

        store.close()  # must not raise

    def test_lineage_still_resolves_after_the_change(self) -> None:
        store = ProvenanceStore()
        store.add_entity("dp-child", attributes={"units": "T"})
        store.add_entity("dp-parent", attributes={"units": "T"})
        store.was_derived_from("dp-child", "dp-parent")
        store.was_attributed_to("dp-child")

        ids = {row["id"] for row in store.get_entity_lineage("dp-child")}
        assert "ml:dp-child" in ids
        assert "ml:wdf-dp-child-dp-parent" in ids
        assert "ml:wat-dp-child-maglab-system" in ids
        store.close()
