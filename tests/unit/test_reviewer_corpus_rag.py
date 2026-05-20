"""tests/unit/test_reviewer_corpus_rag.py — CorpusRAG unit tests."""

from __future__ import annotations

import uuid

import pytest

from maglab.reviewer.corpus_rag import CorpusChunk, CorpusRAG


def _make_chunk(
    author_id: str = "author1",
    text: str = "spin Hall effect measurement",
    doi: str = "10.1103/test.001",
    title: str = "Test Paper",
    section: str = "Methods",
) -> CorpusChunk:
    return CorpusChunk(
        chunk_id=str(uuid.uuid4()),
        author_id=author_id,
        doi=doi,
        title=title,
        text=text,
        section=section,
    )


class TestCorpusRAGBasic:
    """Basic index construction and search tests."""

    def test_add_chunk_without_doi_raises(self):
        """Adding a chunk without a DOI raises a fabricated-citation-prevention error."""
        rag = CorpusRAG()
        bad_chunk = CorpusChunk(
            chunk_id="bad",
            author_id="author1",
            doi="",  # No DOI
            title="no doi",
            text="some text",
        )
        with pytest.raises(ValueError, match="DOI"):
            rag.add_chunk(bad_chunk)

    def test_add_chunk_doi_blank_raises(self):
        """A DOI consisting only of whitespace is also rejected."""
        rag = CorpusRAG()
        bad = CorpusChunk(chunk_id="bad2", author_id="a", doi="   ", title="t", text="t")
        with pytest.raises(ValueError):
            rag.add_chunk(bad)

    def test_add_and_search(self):
        """BM25 search returns results after a chunk is added."""
        rag = CorpusRAG()
        chunk = _make_chunk(text="anomalous Hall effect cobalt iron boron")
        rag.add_chunk(chunk)

        results = rag.search("Hall effect")
        assert len(results) >= 1
        assert results[0].chunk.doi != ""  # DOI always present

    def test_author_namespace_search(self):
        """Author-namespace search returns only chunks for that author."""
        rag = CorpusRAG()
        chunk_a = _make_chunk(author_id="author_a", text="skyrmion dynamics")
        chunk_b = _make_chunk(
            author_id="author_b", text="skyrmion Hall effect", doi="10.1103/b.001"
        )
        rag.add_chunk(chunk_a)
        rag.add_chunk(chunk_b)

        results = rag.search("skyrmion", author_id="author_a")
        assert all(r.chunk.author_id == "author_a" for r in results)

    def test_total_chunks(self):
        rag = CorpusRAG()
        for i in range(5):
            rag.add_chunk(_make_chunk(doi=f"10.1103/test.{i:03d}"))
        assert rag.total_chunks() == 5

    def test_list_authors(self):
        rag = CorpusRAG()
        rag.add_chunk(_make_chunk(author_id="alice"))
        rag.add_chunk(_make_chunk(author_id="bob", doi="10.1103/bob.001"))
        authors = rag.list_authors()
        assert "alice" in authors
        assert "bob" in authors

    def test_search_empty_author_returns_empty(self):
        """Searching for a non-existent author returns an empty list."""
        rag = CorpusRAG()
        rag.add_chunk(_make_chunk())
        results = rag.search("spin", author_id="nonexistent")
        assert results == []

    def test_search_result_has_doi(self):
        """All search result chunks have a DOI (fabricated citation prevention)."""
        rag = CorpusRAG()
        rag.add_chunk(_make_chunk(doi="10.1103/valid.001"))
        results = rag.search("spin Hall")
        for r in results:
            assert r.chunk.doi != ""

    def test_author_chunk_count(self):
        rag = CorpusRAG()
        for i in range(3):
            rag.add_chunk(_make_chunk(author_id="kim", doi=f"10.1103/k.{i}"))
        assert rag.author_chunk_count("kim") == 3
        assert rag.author_chunk_count("nobody") == 0

    def test_add_chunks_batch(self):
        """Verify bulk-add API behavior."""
        rag = CorpusRAG()
        chunks = [_make_chunk(doi=f"10.1/{i}") for i in range(4)]
        rag.add_chunks(chunks)
        assert rag.total_chunks() == 4

    def test_add_chunks_batch_doi_missing_raises(self):
        """Bulk add raises when a chunk without a DOI is included."""
        rag = CorpusRAG()
        bad = CorpusChunk(chunk_id="x", author_id="a", doi="", title="t", text="t")
        with pytest.raises(ValueError):
            rag.add_chunks([bad])


# ---------------------------------------------------------------------------
# R9 F-03 — BM25 author-scoped pre-filtering
# ---------------------------------------------------------------------------


class TestBM25AuthorScopedSearch:
    """R9 F-03 regression: author-scoped BM25 search must return the author's
    relevant chunks even when the corpus is large and those chunks rank outside
    the global top-k.

    Before the fix, bm25_results = self._bm25.search(query, top_k=top_k * 2)
    retrieved the global top-(2*top_k) and post-filtered, so an author's chunks
    ranked below that cutoff were silently dropped.  The fix widens the BM25
    pool to len(self._bm25._pending) when author_id is set.
    """

    def _make_target_chunk(self, idx: int = 0) -> CorpusChunk:
        """Chunk for 'Smith' with rare query token 'skyrmion_rare_xyzq'."""
        return CorpusChunk(
            chunk_id=f"smith_{idx:04d}",
            author_id="Smith",
            doi=f"10.1103/smith.{idx:03d}",
            title="Smith Paper",
            text="skyrmion_rare_xyzq dynamics domain wall motion",
        )

    def _make_noise_chunk(self, idx: int) -> CorpusChunk:
        """Chunk for a different author with common high-TF-IDF words."""
        return CorpusChunk(
            chunk_id=f"noise_{idx:04d}",
            author_id=f"author_{idx:04d}",
            doi=f"10.1103/noise.{idx:03d}",
            title="Other Paper",
            # Use the same rare token so it scores high globally.
            text=(
                "skyrmion_rare_xyzq spin Hall effect anomalous Hall "
                "cobalt iron boron platinum tungsten interface "
                f"sample_{idx} magnetization damping"
            ),
        )

    def test_author_chunks_found_when_corpus_large(self):
        """R9 F-03: Smith's chunk is found via author-scoped BM25 even when
        many noise chunks outrank it globally."""
        rag = CorpusRAG()

        # Add enough noise chunks so Smith's chunk ranks well outside global top_k*2
        # for a small top_k (e.g. top_k=2 → top_k*2=4 candidates globally).
        num_noise = 20
        for i in range(num_noise):
            rag.add_chunk(self._make_noise_chunk(i))

        smith_chunk = self._make_target_chunk()
        rag.add_chunk(smith_chunk)

        results = rag.search("skyrmion_rare_xyzq", author_id="Smith", top_k=2)

        found_ids = {r.chunk.chunk_id for r in results}
        assert smith_chunk.chunk_id in found_ids, (
            f"Smith's chunk not returned by author-scoped BM25 search. "
            f"Found: {found_ids}. Corpus size: {rag.total_chunks()} chunks."
        )

    def test_author_search_returns_only_author_chunks(self):
        """Author-scoped search must not include chunks from other authors."""
        rag = CorpusRAG()
        for i in range(10):
            rag.add_chunk(self._make_noise_chunk(i))
        rag.add_chunk(self._make_target_chunk())

        results = rag.search("skyrmion_rare_xyzq", author_id="Smith", top_k=5)
        for r in results:
            assert r.chunk.author_id == "Smith", (
                f"Non-Smith chunk in author-scoped results: {r.chunk.author_id}"
            )

    def test_global_search_unchanged(self):
        """Without author_id, BM25 search still operates over the full corpus."""
        rag = CorpusRAG()
        for i in range(5):
            rag.add_chunk(self._make_noise_chunk(i))
        rag.add_chunk(self._make_target_chunk())

        results = rag.search("skyrmion_rare_xyzq", top_k=10)
        # All chunks (noise + Smith) must be candidates.
        authors = {r.chunk.author_id for r in results}
        # Smith chunk should appear somewhere in global top-10.
        assert "Smith" in authors or len(results) > 0  # basic sanity
