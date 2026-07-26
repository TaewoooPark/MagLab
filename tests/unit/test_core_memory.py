"""maglab.core.memory unit tests — deterministic, no network/LLM."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from maglab.core.memory import (
    LongTermMemory,
    PoolRecordKind,
    ResearchPool,
    SessionMemory,
)

# ---------------------------------------------------------------------------
# Tier 2 — SessionMemory
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_mem(tmp_path: Path) -> SessionMemory:
    sm = SessionMemory(session_id="test-session", db_path=tmp_path / "sessions.db")
    yield sm
    sm.close()


def test_session_set_and_get(session_mem: SessionMemory) -> None:
    session_mem.set("key1", "value1")
    assert session_mem.get("key1") == "value1"


def test_session_get_default(session_mem: SessionMemory) -> None:
    assert session_mem.get("missing", default="fallback") == "fallback"


def test_session_overwrite(session_mem: SessionMemory) -> None:
    session_mem.set("k", 1)
    session_mem.set("k", 99)
    assert session_mem.get("k") == 99


def test_session_all_keys(session_mem: SessionMemory) -> None:
    session_mem.set("alpha", 1)
    session_mem.set("beta", 2)
    keys = session_mem.all_keys()
    assert "alpha" in keys
    assert "beta" in keys


def test_session_stores_complex_value(session_mem: SessionMemory) -> None:
    data = {"params": {"alpha": 0.01, "Ms": 8e5}, "status": "done"}
    session_mem.set("result", data)
    loaded = session_mem.get("result")
    assert loaded == data


def test_session_persists_across_connections(tmp_path: Path) -> None:
    db = tmp_path / "sess.db"
    sid = "persist-session"
    s1 = SessionMemory(session_id=sid, db_path=db)
    s1.set("checkpoint", {"step": 3})
    s1.close()

    s2 = SessionMemory(session_id=sid, db_path=db)
    loaded = s2.get("checkpoint")
    assert loaded == {"step": 3}
    s2.close()


def test_different_sessions_isolated(tmp_path: Path) -> None:
    db = tmp_path / "iso.db"
    s1 = SessionMemory(session_id="session-A", db_path=db)
    s2 = SessionMemory(session_id="session-B", db_path=db)
    s1.set("secret", "alpha")
    assert s2.get("secret") is None
    s1.close()
    s2.close()


# ---------------------------------------------------------------------------
# Tier 3 — LongTermMemory
# ---------------------------------------------------------------------------


@pytest.fixture()
def ltm(tmp_path: Path) -> LongTermMemory:
    return LongTermMemory(memories_dir=tmp_path / "memories")


def test_ltm_write_and_read(ltm: LongTermMemory) -> None:
    ltm.write("calibration-note", "# Calibration\n\nParameter α = 0.01.")
    content = ltm.read("calibration-note")
    assert content is not None
    assert "α = 0.01" in content


def test_ltm_read_nonexistent_returns_none(ltm: LongTermMemory) -> None:
    assert ltm.read("ghost-file") is None


def test_ltm_search_finds_text(ltm: LongTermMemory) -> None:
    ltm.write("memo-1", "Ms_CoFeB = 1.2e6 A/m")
    ltm.write("memo-2", "alpha_damping = 0.005")
    results = ltm.search("Ms_CoFeB")
    assert len(results) >= 1
    assert any("Ms_CoFeB" in r["text"] for r in results)


def test_ltm_search_case_insensitive(ltm: LongTermMemory) -> None:
    ltm.write("note", "Exchange stiffness A = 28 pJ/m")
    results = ltm.search("exchange stiffness")
    assert len(results) >= 1


def test_ltm_search_no_match(ltm: LongTermMemory) -> None:
    ltm.write("note", "DW width = 10 nm")
    results = ltm.search("xyz_impossible_term_12345")
    assert results == []


def test_ltm_list_files(ltm: LongTermMemory) -> None:
    ltm.write("file-a", "Content A")
    ltm.write("file-b", "Content B")
    files = ltm.list_files()
    assert "file-a.md" in files
    assert "file-b.md" in files


def test_ltm_overwrite(ltm: LongTermMemory) -> None:
    ltm.write("shared", "Version 1")
    ltm.write("shared", "Version 2")
    content = ltm.read("shared")
    assert content is not None
    assert "Version 2" in content


# ---------------------------------------------------------------------------
# research_pool
# ---------------------------------------------------------------------------


@pytest.fixture()
def pool(tmp_path: Path) -> ResearchPool:
    return ResearchPool(pool_dir=tmp_path / "pool")


def test_pool_add_and_get(pool: ResearchPool) -> None:
    rec = pool.add(
        kind=PoolRecordKind.CONFIRMED_RESULT,
        topic_tags=["CoFeB", "AHE"],
        summary="sigma_AHE = 100 Omega^-1 cm^-1 (T=5 K)",
        provenance_ref="prov:run-001",
    )
    fetched = pool.get(rec.record_id)
    assert fetched is not None
    assert fetched.kind == PoolRecordKind.CONFIRMED_RESULT
    assert "CoFeB" in fetched.topic_tags
    assert fetched.provenance_ref == "prov:run-001"


def test_pool_query_by_keyword(pool: ResearchPool) -> None:
    pool.add(
        kind=PoolRecordKind.CONFIRMED_RESULT,
        topic_tags=["GdFeCo"],
        summary="Compensation point T_comp = 280 K",
    )
    pool.add(
        kind=PoolRecordKind.FAILED_REGION,
        topic_tags=["YIG"],
        summary="Convergence failure for alpha > 0.1",
    )
    results = pool.query(keywords=["T_comp"])
    assert len(results) == 1
    assert "T_comp" in results[0].summary


def test_pool_query_by_kind(pool: ResearchPool) -> None:
    pool.add(
        kind=PoolRecordKind.CONFIRMED_RESULT,
        topic_tags=["x"],
        summary="Confirmed result A",
    )
    pool.add(
        kind=PoolRecordKind.ANOMALY,
        topic_tags=["y"],
        summary="Anomaly B",
    )
    results = pool.query(kind=PoolRecordKind.ANOMALY)
    assert all(r.kind == PoolRecordKind.ANOMALY for r in results)
    assert len(results) == 1


def test_pool_query_by_topic_tag(pool: ResearchPool) -> None:
    pool.add(kind=PoolRecordKind.CONFIRMED_RESULT, topic_tags=["SMR", "Pt/YIG"], summary="X")
    pool.add(kind=PoolRecordKind.CONFIRMED_RESULT, topic_tags=["AHE", "Py"], summary="Y")
    results = pool.query(topic_tag="SMR")
    assert len(results) == 1
    assert "SMR" in results[0].topic_tags


def test_pool_query_empty_on_no_match(pool: ResearchPool) -> None:
    pool.add(kind=PoolRecordKind.EFFECTIVE_CONFIG, topic_tags=["t"], summary="s")
    results = pool.query(keywords=["TOTALLY_NOT_HERE_XYZ"])
    assert results == []


def test_pool_get_nonexistent_returns_none(pool: ResearchPool) -> None:
    assert pool.get("nonexistent-id") is None


def test_pool_record_kinds() -> None:
    assert PoolRecordKind.CONFIRMED_RESULT.value == "confirmed_result"
    assert PoolRecordKind.FAILED_REGION.value == "failed_region"
    assert PoolRecordKind.ANOMALY.value == "anomaly"
    assert PoolRecordKind.EFFECTIVE_CONFIG.value == "effective_config"


def test_pool_persists_data_field(pool: ResearchPool) -> None:
    rec = pool.add(
        kind=PoolRecordKind.FAILED_REGION,
        topic_tags=["t"],
        summary="Failed region",
        data={"alpha_range": [0.5, 1.0], "reason": "divergence"},
    )
    fetched = pool.get(rec.record_id)
    assert fetched is not None
    assert fetched.data["alpha_range"] == [0.5, 1.0]


# ---------------------------------------------------------------------------
# research_pool — semantic_query (§5.13 vector search)
# ---------------------------------------------------------------------------


def test_pool_semantic_query_ranks_by_relevance(pool: ResearchPool) -> None:
    """semantic_query ranks the most relevant record first."""
    pool.add(
        kind=PoolRecordKind.CONFIRMED_RESULT,
        topic_tags=["damping", "FMR"],
        summary="Gilbert damping measured by ferromagnetic resonance",
    )
    pool.add(
        kind=PoolRecordKind.CONFIRMED_RESULT,
        topic_tags=["skyrmion"],
        summary="Skyrmion lattice imaged by Lorentz microscopy",
    )
    ranked = pool.semantic_query("ferromagnetic resonance damping")
    assert len(ranked) >= 1
    assert "damping" in ranked[0].summary.lower()


def test_pool_semantic_query_kind_filter(pool: ResearchPool) -> None:
    """semantic_query honors the kind filter."""
    pool.add(kind=PoolRecordKind.CONFIRMED_RESULT, topic_tags=["x"], summary="damping result")
    pool.add(kind=PoolRecordKind.ANOMALY, topic_tags=["y"], summary="damping anomaly")
    ranked = pool.semantic_query("damping", kind=PoolRecordKind.ANOMALY)
    assert all(r.kind == PoolRecordKind.ANOMALY for r in ranked)


def test_pool_semantic_query_empty_pool(pool: ResearchPool) -> None:
    """semantic_query on an empty pool returns an empty list."""
    assert pool.semantic_query("anything") == []


def test_pool_semantic_query_min_score_filters(pool: ResearchPool) -> None:
    """A min_score above any similarity returns nothing."""
    pool.add(kind=PoolRecordKind.CONFIRMED_RESULT, topic_tags=["t"], summary="exchange stiffness")
    assert pool.semantic_query("totally unrelated quantum gravity", min_score=0.5) == []


def test_pool_semantic_query_max_results(pool: ResearchPool) -> None:
    """semantic_query respects max_results."""
    for i in range(5):
        pool.add(
            kind=PoolRecordKind.CONFIRMED_RESULT,
            topic_tags=["damping"],
            summary=f"damping measurement number {i}",
        )
    ranked = pool.semantic_query("damping", max_results=3)
    assert len(ranked) == 3


# ---------------------------------------------------------------------------
# REGRESSION — Finding 3 (R2): a corrupt pool JSON file must be skipped, not
# crash query() or semantic_query().  Before the fix, _load() propagated
# KeyError / ValueError / json.JSONDecodeError from malformed files, which
# permanently broke the autonomous research loop.
# ---------------------------------------------------------------------------


class TestResearchPoolCorruptFile:
    """Corrupt pool files are skipped, not fatal (Finding 3 regression)."""

    def test_query_skips_corrupt_json_file(self, tmp_path: Path) -> None:
        """query() gracefully skips a file with invalid JSON."""
        pool_dir = tmp_path / "pool"
        p = ResearchPool(pool_dir=pool_dir)
        # Add one valid record
        p.add(
            kind=PoolRecordKind.CONFIRMED_RESULT,
            topic_tags=["AHE"],
            summary="Valid AHE measurement",
        )
        # Inject a corrupt JSON file directly into the pool directory
        corrupt = pool_dir / "corrupt-record.json"
        corrupt.write_text("{not valid json", encoding="utf-8")

        # Must not raise; valid record is still returned
        results = p.query(keywords=["AHE"])
        assert len(results) == 1
        assert "AHE" in results[0].summary

    def test_query_skips_missing_key_file(self, tmp_path: Path) -> None:
        """query() gracefully skips a file missing required keys."""
        pool_dir = tmp_path / "pool"
        p = ResearchPool(pool_dir=pool_dir)
        p.add(
            kind=PoolRecordKind.CONFIRMED_RESULT,
            topic_tags=["SMR"],
            summary="SMR measurement",
        )
        # Write a JSON file that is valid JSON but missing required fields
        incomplete = pool_dir / "incomplete-record.json"
        incomplete.write_text('{"record_id": "abc"}', encoding="utf-8")

        results = p.query(keywords=["SMR"])
        assert len(results) == 1
        assert "SMR" in results[0].summary

    def test_semantic_query_skips_corrupt_json_file(self, tmp_path: Path) -> None:
        """semantic_query() gracefully skips a corrupt file."""
        pool_dir = tmp_path / "pool"
        p = ResearchPool(pool_dir=pool_dir)
        p.add(
            kind=PoolRecordKind.CONFIRMED_RESULT,
            topic_tags=["damping"],
            summary="Gilbert damping measurement",
        )
        corrupt = pool_dir / "broken.json"
        corrupt.write_text("INVALID JSON !!!!", encoding="utf-8")

        results = p.semantic_query("damping")
        assert len(results) >= 1
        assert "damping" in results[0].summary.lower()

    def test_semantic_query_skips_missing_key_file(self, tmp_path: Path) -> None:
        """semantic_query() skips a file with valid JSON but missing required keys."""
        pool_dir = tmp_path / "pool"
        p = ResearchPool(pool_dir=pool_dir)
        p.add(
            kind=PoolRecordKind.CONFIRMED_RESULT,
            topic_tags=["YIG"],
            summary="YIG ferromagnetic resonance",
        )
        incomplete = pool_dir / "no-kind.json"
        incomplete.write_text('{"record_id": "xyz", "summary": "bad"}', encoding="utf-8")

        results = p.semantic_query("YIG ferromagnetic")
        assert len(results) >= 1
        assert "YIG" in results[0].summary

    def test_all_corrupt_returns_empty_list(self, tmp_path: Path) -> None:
        """When ALL files are corrupt, query returns [] rather than raising."""
        pool_dir = tmp_path / "pool"
        pool_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (pool_dir / f"bad-{i}.json").write_text("{{garbage}}", encoding="utf-8")

        p = ResearchPool(pool_dir=pool_dir)
        assert p.query(keywords=["anything"]) == []
        assert p.semantic_query("anything") == []


# ---------------------------------------------------------------------------
# Durability — a half-written record silently disappears from every query
# ---------------------------------------------------------------------------


class TestMemoryWriteDurability:
    """query()/semantic_query() skip records they cannot parse.

    That is the right call for a bulk search, but it means a truncated record is
    lost silently rather than loudly — so the write itself must be atomic.
    """

    def test_failed_pool_save_leaves_the_previous_record_intact(self, tmp_path: Path) -> None:
        pool = ResearchPool(pool_dir=tmp_path)
        rec = pool.add(
            kind=PoolRecordKind.CONFIRMED_RESULT,
            topic_tags=["dmi"],
            summary="interfacial DMI confirmed",
        )
        before = (tmp_path / f"{rec.record_id}.json").read_text(encoding="utf-8")

        with (
            mock.patch("maglab.core.memory.atomic_write_text", side_effect=OSError("disk full")),
            pytest.raises(OSError),
        ):
            pool.add(
                kind=PoolRecordKind.ANOMALY,
                topic_tags=["dmi"],
                summary="unexpected sign reversal",
            )

        assert (tmp_path / f"{rec.record_id}.json").read_text(encoding="utf-8") == before
        assert len(pool.query()) == 1, "the surviving record must still be queryable"

    def test_pool_save_leaves_no_scratch_files(self, tmp_path: Path) -> None:
        pool = ResearchPool(pool_dir=tmp_path)
        for i in range(3):
            pool.add(
                kind=PoolRecordKind.CONFIRMED_RESULT,
                topic_tags=["t"],
                summary=f"result {i}",
            )

        leftovers = [p.name for p in tmp_path.iterdir() if not p.name.endswith(".json")]
        assert leftovers == [], f"atomic write left scratch files behind: {leftovers}"
        assert len(pool.query()) == 3

    def test_overwriting_a_memory_does_not_leave_stale_tail_bytes(self, tmp_path: Path) -> None:
        mem = LongTermMemory(memories_dir=tmp_path)
        mem.write("notes", "a considerably longer earlier body of text")
        mem.write("notes", "short")

        assert mem.read("notes") == "short"

    def test_failed_memory_write_leaves_the_previous_body(self, tmp_path: Path) -> None:
        mem = LongTermMemory(memories_dir=tmp_path)
        mem.write("notes", "original body")

        with (
            mock.patch("maglab.core.memory.atomic_write_text", side_effect=OSError("disk full")),
            pytest.raises(OSError),
        ):
            mem.write("notes", "replacement body")

        assert mem.read("notes") == "original body"


class TestMemoryNameContainment:
    """A memory name is interpolated straight into a path — it must stay inside.

    ``write``/``read`` build ``<memories_dir>/<name>.md``, so a name carrying
    ``..`` or a separator reached outside the store entirely.
    """

    @pytest.mark.parametrize(
        "name", ["../escape", "../../etc/passwd", "sub/dir/file", "/tmp/absolute"]
    )
    def test_write_refuses_names_that_escape(self, tmp_path: Path, name: str) -> None:
        mem = LongTermMemory(memories_dir=tmp_path / "mem")
        with pytest.raises(ValueError, match="escapes"):
            mem.write(name, "content")

    @pytest.mark.parametrize("name", ["../escape", "sub/dir/file"])
    def test_read_refuses_names_that_escape(self, tmp_path: Path, name: str) -> None:
        mem = LongTermMemory(memories_dir=tmp_path / "mem")
        with pytest.raises(ValueError, match="escapes"):
            mem.read(name)

    def test_nothing_is_written_outside_the_store(self, tmp_path: Path) -> None:
        mem = LongTermMemory(memories_dir=tmp_path / "mem")
        with pytest.raises(ValueError):
            mem.write("../outside", "pwned")

        assert not (tmp_path / "outside.md").exists()

    def test_ordinary_names_still_work(self, tmp_path: Path) -> None:
        mem = LongTermMemory(memories_dir=tmp_path / "mem")
        written = mem.write("project-notes", "body")

        assert written.name == "project-notes.md"
        assert mem.read("project-notes") == "body"
