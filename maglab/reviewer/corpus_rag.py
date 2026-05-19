"""Author corpus RAG — SPECTER2 embeddings·LanceDB + BM25 hybrid search (§15.3).

Author ID (S2/arXiv) → paper chunks → SPECTER2 embeddings → LanceDB vector index.
Maintains a parallel BM25 index and performs hybrid search via RRF fusion.
No fabricated citations — must return verbatim chunk excerpts + DOI only.

BM25 index is shared with ``maglab.literature.rag.BM25Index`` — no duplicate
implementation (plan §14.7 / §15.3 "literature/ and reviewer/ corpus share this index").
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from maglab.literature.rag import BM25Index as _LiteratureBM25Index

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunk data structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusChunk:
    """Single text chunk from the author paper corpus.

    Attributes
    ----------
    chunk_id:
        Unique chunk identifier.
    author_id:
        Author ID (S2 or arXiv format).
    doi:
        Paper DOI — required field to prevent fabricated citations.
    title:
        Paper title.
    text:
        Chunk text (verbatim excerpt).
    section:
        Paper section this chunk belongs to.
    embedding:
        SPECTER2 embedding vector (lazy, None if not yet embedded).
    """

    chunk_id: str
    author_id: str
    doi: str
    title: str
    text: str
    section: str = ""
    embedding: tuple[float, ...] | None = None


@dataclass
class SearchResult:
    """Hybrid search result.

    Attributes
    ----------
    chunk:
        Retrieved chunk.
    score:
        RRF fusion score (higher = more relevant).
    vector_rank:
        Vector search rank (None if not retrieved by vector search).
    bm25_rank:
        BM25 search rank (None if not retrieved by BM25 search).
    """

    chunk: CorpusChunk
    score: float
    vector_rank: int | None = None
    bm25_rank: int | None = None


# ---------------------------------------------------------------------------
# BM25 index adapter — wraps literature.rag.BM25Index for incremental use
# ---------------------------------------------------------------------------


class _CorpusBM25Index:
    """Incremental BM25 adapter backed by ``literature.rag.BM25Index``.

    ``CorpusRAG`` adds chunks one-by-one; the underlying
    ``_LiteratureBM25Index`` uses a batch TF-IDF build.  This adapter
    accumulates chunks incrementally and rebuilds the index lazily on the
    first ``search()`` call after a new ``add()``.

    Shares the BM25 implementation with ``maglab.literature.rag.BM25Index``
    (plan §14.7 / §15.3: "literature/ and reviewer/ corpus share this index").
    """

    def __init__(self) -> None:
        self._index = _LiteratureBM25Index()
        self._pending: list[tuple[str, str]] = []  # (chunk_id, text) awaiting rebuild
        self._dirty: bool = False

    def add(self, chunk_id: str, text: str) -> None:
        """Add a document to the index (rebuilt lazily on next search)."""
        self._pending.append((chunk_id, text))
        self._dirty = True

    def _rebuild_if_dirty(self) -> None:
        """Rebuild the underlying TF-IDF BM25 index if new chunks were added."""
        if not self._dirty:
            return

        # Build a minimal duck-typed object list: BM25Index.build() only uses
        # .chunk_id and .text from each element.
        class _MinimalChunk:
            __slots__ = ("chunk_id", "text")

            def __init__(self, cid: str, txt: str) -> None:
                self.chunk_id = cid
                self.text = txt

        chunks = [_MinimalChunk(cid, txt) for cid, txt in self._pending]
        self._index = _LiteratureBM25Index()
        self._index.build(chunks)  # type: ignore[arg-type]
        self._dirty = False

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return the top k chunk IDs by BM25 score."""
        if not self._pending:
            return []
        self._rebuild_if_dirty()
        return self._index.search(query, top_k=top_k)


# ---------------------------------------------------------------------------
# Corpus RAG index
# ---------------------------------------------------------------------------


class CorpusRAG:
    """Author corpus RAG index (§15.3).

    Hybrid vector+BM25 search index with per-author namespaces.
    Combines vector search and BM25 search via RRF (Reciprocal Rank Fusion).

    Uses LanceDB·SPECTER2 embeddings when the optional ``[reviewer]`` extra
    is installed; falls back to BM25-only mode otherwise.

    Parameters
    ----------
    rrf_k:
        RRF constant k (default 60).
    embedding_fn:
        Embedding function ``(texts: list[str]) -> list[list[float]]``.
        None enables BM25-only mode.
    """

    def __init__(
        self,
        rrf_k: int = 60,
        embedding_fn: Any | None = None,
    ) -> None:
        self._rrf_k = rrf_k
        self._embed_fn = embedding_fn
        self._chunks: dict[str, CorpusChunk] = {}  # chunk_id → chunk
        self._author_chunks: dict[str, list[str]] = defaultdict(list)  # author_id → [chunk_id]
        self._bm25 = _CorpusBM25Index()
        self._vectors: dict[str, list[float]] = {}  # chunk_id → embedding

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def add_chunk(self, chunk: CorpusChunk) -> None:
        """Add a chunk to the index.

        Chunks without a DOI are rejected per the no-fabricated-citations policy.
        """
        if not chunk.doi.strip():
            raise ValueError(
                f"No fabricated citations: chunks without a DOI cannot be added. chunk_id={chunk.chunk_id!r}"
            )
        self._chunks[chunk.chunk_id] = chunk
        self._author_chunks[chunk.author_id].append(chunk.chunk_id)
        self._bm25.add(chunk.chunk_id, chunk.text)

        if self._embed_fn is not None and chunk.embedding is None:
            try:
                vecs = self._embed_fn([chunk.text])
                if vecs:
                    self._vectors[chunk.chunk_id] = vecs[0]
            except Exception as exc:  # noqa: BLE001
                log.warning("Embedding error (chunk_id=%s): %s", chunk.chunk_id, exc)
        elif chunk.embedding is not None:
            self._vectors[chunk.chunk_id] = list(chunk.embedding)

    def add_chunks(self, chunks: list[CorpusChunk]) -> None:
        """Add multiple chunks in bulk."""
        texts = []
        ids = []
        for chunk in chunks:
            if not chunk.doi.strip():
                raise ValueError(
                    f"No fabricated citations: chunk without DOI rejected chunk_id={chunk.chunk_id!r}"
                )
            self._chunks[chunk.chunk_id] = chunk
            self._author_chunks[chunk.author_id].append(chunk.chunk_id)
            self._bm25.add(chunk.chunk_id, chunk.text)
            if chunk.embedding is not None:
                self._vectors[chunk.chunk_id] = list(chunk.embedding)
            elif self._embed_fn is not None:
                texts.append(chunk.text)
                ids.append(chunk.chunk_id)

        if texts and self._embed_fn is not None:
            try:
                vecs = self._embed_fn(texts)
                for cid, vec in zip(ids, vecs, strict=False):
                    self._vectors[cid] = vec
            except Exception as exc:  # noqa: BLE001
                log.warning("Batch embedding error: %s", exc)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        author_id: str | None = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Hybrid search (vector + BM25 RRF) returning the top k chunks.

        Parameters
        ----------
        query:
            Search query text.
        author_id:
            Restrict search to a specific author. None searches the full corpus.
        top_k:
            Number of top results to return.

        Returns
        -------
        list[SearchResult]
            Results always include the DOI field (prevents fabricated citations).
        """
        allowed_ids: set[str] | None = None
        if author_id is not None:
            cids = self._author_chunks.get(author_id, [])
            if not cids:
                return []
            allowed_ids = set(cids)

        # BM25 search
        bm25_results = self._bm25.search(query, top_k=top_k * 2)
        if allowed_ids is not None:
            bm25_results = [(cid, s) for cid, s in bm25_results if cid in allowed_ids]

        bm25_ranks: dict[str, int] = {cid: i + 1 for i, (cid, _) in enumerate(bm25_results)}

        # Vector search
        vec_ranks: dict[str, int] = {}
        if self._vectors and self._embed_fn is not None:
            try:
                q_vecs = self._embed_fn([query])
                q_vec = q_vecs[0] if q_vecs else None
            except Exception as exc:  # noqa: BLE001
                log.warning("Query embedding error: %s", exc)
                q_vec = None

            if q_vec is not None:
                sims = self._cosine_similarities(q_vec, allowed_ids)
                sims.sort(key=lambda x: -x[1])
                vec_ranks = {cid: i + 1 for i, (cid, _) in enumerate(sims[: top_k * 2])}

        # RRF fusion
        all_ids = set(bm25_ranks) | set(vec_ranks)
        rrf_scores: dict[str, float] = {}
        for cid in all_ids:
            score = 0.0
            if cid in bm25_ranks:
                score += 1.0 / (self._rrf_k + bm25_ranks[cid])
            if cid in vec_ranks:
                score += 1.0 / (self._rrf_k + vec_ranks[cid])
            rrf_scores[cid] = score

        ranked = sorted(rrf_scores.items(), key=lambda x: -x[1])[:top_k]

        results = []
        for cid, score in ranked:
            chunk = self._chunks.get(cid)
            if chunk is None:
                continue
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    vector_rank=vec_ranks.get(cid),
                    bm25_rank=bm25_ranks.get(cid),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Author statistics
    # ------------------------------------------------------------------

    def author_chunk_count(self, author_id: str) -> int:
        """Return the number of indexed chunks for a specific author."""
        return len(self._author_chunks.get(author_id, []))

    def total_chunks(self) -> int:
        """Return the total number of indexed chunks."""
        return len(self._chunks)

    def list_authors(self) -> list[str]:
        """Return the list of indexed author IDs."""
        return list(self._author_chunks.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cosine_similarities(
        self,
        q_vec: list[float],
        allowed_ids: set[str] | None,
    ) -> list[tuple[str, float]]:
        """Compute cosine similarities between the query vector and index vectors."""
        results = []
        q_norm = math.sqrt(sum(x * x for x in q_vec)) or 1e-9
        for cid, vec in self._vectors.items():
            if allowed_ids is not None and cid not in allowed_ids:
                continue
            dot = sum(a * b for a, b in zip(q_vec, vec, strict=False))
            v_norm = math.sqrt(sum(x * x for x in vec)) or 1e-9
            sim = dot / (q_norm * v_norm)
            results.append((cid, sim))
        return results
