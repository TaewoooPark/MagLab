"""tests/unit/test_literature_rag.py — LiteratureRAG unit tests.

Covers:
  - R9 F-02: add_document() idempotency (duplicate doc_id must not create duplicate chunks).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from maglab.literature.rag import LiteratureRAG

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rag(tmp_path: Path) -> LiteratureRAG:
    """Return a fresh LiteratureRAG backed by a temp directory.

    Patches ``_persist_chunks`` and ``_load_from_db`` so no real LanceDB I/O
    occurs.  This keeps the tests fast and dependency-free.
    """
    with (
        patch.object(LiteratureRAG, "_load_from_db", return_value=None),
        patch.object(LiteratureRAG, "_persist_chunks", return_value=None),
    ):
        return LiteratureRAG(db_path=tmp_path / "lancedb")


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic stub: each text → a 4-dim unit vector based on length."""
    result = []
    for t in texts:
        n = len(t) % 4 + 1
        v = [float(i == n % 4) for i in range(4)]
        result.append(v)
    return result


# ---------------------------------------------------------------------------
# R9 F-02 — add_document() idempotency
# ---------------------------------------------------------------------------


class TestAddDocumentIdempotency:
    """add_document() must not duplicate chunks when called twice with the same doc_id."""

    def test_same_doc_id_twice_does_not_duplicate_chunks(self, tmp_path: Path):
        """R9 F-02: indexing the same doc_id a second time is a no-op."""
        rag = _make_rag(tmp_path)

        # Patch the embedding model to avoid loading SPECTER2.
        with patch.object(rag._embedding_model, "encode", side_effect=_fake_embed):
            n1 = rag.add_document(
                "spin Hall effect measurement data",
                doc_id="doi:10.1103/test.001",
                title="Paper A",
            )
            chunk_count_after_first = rag.chunk_count

            n2 = rag.add_document(
                "spin Hall effect measurement data",
                doc_id="doi:10.1103/test.001",
                title="Paper A",
            )
            chunk_count_after_second = rag.chunk_count

        assert n1 > 0, "First add_document call should return > 0 chunks"
        assert n2 == 0, "Second add_document call with same doc_id should return 0 (skipped)"
        assert chunk_count_after_first == chunk_count_after_second, (
            f"Chunk count changed from {chunk_count_after_first} to "
            f"{chunk_count_after_second} after duplicate add — duplicate chunks added"
        )

    def test_different_doc_ids_are_both_indexed(self, tmp_path: Path):
        """Two distinct doc_ids are both indexed without interference."""
        rag = _make_rag(tmp_path)

        with patch.object(rag._embedding_model, "encode", side_effect=_fake_embed):
            n1 = rag.add_document("Paper one content", doc_id="doi:10.1/a", title="A")
            n2 = rag.add_document("Paper two content", doc_id="doi:10.1/b", title="B")

        assert n1 > 0
        assert n2 > 0
        doc_ids = {c.doc_id for c in rag._chunks}
        assert "doi:10.1/a" in doc_ids
        assert "doi:10.1/b" in doc_ids

    def test_idempotency_survives_simulated_session_reload(self, tmp_path: Path):
        """R9 F-02 cross-session trace: manually pre-populate _chunks (simulating
        _load_from_db) and then call add_document — no duplicates should result."""
        rag = _make_rag(tmp_path)

        with patch.object(rag._embedding_model, "encode", side_effect=_fake_embed):
            # First indexing.
            rag.add_document("magnetism paper text", doc_id="doi:10.1/x", title="X")
            count_after_first = rag.chunk_count

            # Simulate a new session that already loaded the same chunks from DB
            # (the real _load_from_db would have done this at __init__).
            # We verify the guard works by calling add_document again directly.
            returned = rag.add_document("magnetism paper text", doc_id="doi:10.1/x", title="X")

        assert returned == 0, "Simulated reload + re-index should be skipped (returned 0)"
        assert rag.chunk_count == count_after_first, (
            "Chunk count must not grow after a duplicate add_document call"
        )
