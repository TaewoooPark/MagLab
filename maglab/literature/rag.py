"""Literature RAG — LanceDB vector index + BM25 hybrid search (§14·§15.3).

SPECTER2 embeddings (`sentence-transformers`) + BM25 (scikit-learn TF-IDF based).
The `literature/` and `reviewer/` corpora share this index.

Dependencies: lancedb, sentence-transformers, pdfplumber (``[literature]`` extra).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

log = logging.getLogger(__name__)
_APP = "maglab"

# SPECTER2 model (specialized for academic document embeddings)
_SPECTER2_MODEL = "allenai/specter2_base"
_EMBEDDING_DIM = 768


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """Chunk text by word boundaries.

    Parameters
    ----------
    text:
        Input text.
    chunk_size:
        Maximum number of words per chunk.
    overlap:
        Number of overlapping words between chunks.
    """
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Chunk metadata
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """Single document chunk.

    Attributes
    ----------
    chunk_id:
        Unique chunk ID (doc_id + sequence number).
    doc_id:
        Source document ID (DOI or dedup_key).
    doi:
        DOI (if available).
    title:
        Document title.
    authors:
        Author list (as string).
    year:
        Publication year.
    venue:
        Journal or conference.
    namespace:
        Index namespace (e.g. 'literature', 'reviewer/Smith').
    text:
        Chunk text.
    chunk_index:
        Chunk sequence number.
    embedding:
        Embedding vector (for LanceDB storage).
    """

    chunk_id: str
    doc_id: str
    doi: str
    title: str
    authors: str
    year: int | None
    venue: str
    namespace: str
    text: str
    chunk_index: int
    embedding: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------


class EmbeddingModel:
    """SPECTER2 embedding model wrapper."""

    def __init__(self, model_name: str = _SPECTER2_MODEL) -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load(self) -> None:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # noqa: PLC0415

                self._model = SentenceTransformer(self._model_name)
                log.info("SPECTER2 model loaded: %s", self._model_name)
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers not installed — pip install 'maglab[literature]'"
                ) from exc

    def encode(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Encode a list of texts into embedding vectors."""
        self._load()
        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]

    def encode_one(self, text: str) -> list[float]:
        """Encode a single text into an embedding vector."""
        return self.encode([text])[0]


# ---------------------------------------------------------------------------
# BM25 index (TF-IDF based)
# ---------------------------------------------------------------------------


class BM25Index:
    """BM25-like search index based on TF-IDF.

    Uses TF-IDF instead of true BM25 (scikit-learn dependency only).
    """

    def __init__(self) -> None:
        self._vectorizer: Any = None
        self._matrix: Any = None
        self._chunk_ids: list[str] = []

    def build(self, chunks: list[Chunk]) -> None:
        """Build the BM25 index from a list of chunks."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("scikit-learn not installed") from exc

        if not chunks:
            return

        texts = [c.text for c in chunks]
        self._chunk_ids = [c.chunk_id for c in chunks]
        self._vectorizer = TfidfVectorizer(max_features=50000, ngram_range=(1, 2))
        self._matrix = self._vectorizer.fit_transform(texts)
        log.debug("BM25 index built (%d chunks)", len(chunks))

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """BM25 search — returns (chunk_id, score) list."""
        if self._vectorizer is None or self._matrix is None:
            return []
        try:
            import numpy as np  # noqa: PLC0415

            q_vec = self._vectorizer.transform([query])
            scores = (self._matrix @ q_vec.T).toarray().flatten()
            top_indices = np.argsort(scores)[::-1][:top_k]
            return [(self._chunk_ids[i], float(scores[i])) for i in top_indices if scores[i] > 0]
        except Exception as exc:  # noqa: BLE001
            log.warning("BM25 search failed: %s", exc)
            return []

    @property
    def is_built(self) -> bool:
        return self._matrix is not None


# ---------------------------------------------------------------------------
# LanceDB vector index
# ---------------------------------------------------------------------------


def _lancedb_path() -> Path:
    d = Path(platformdirs.user_data_dir(_APP)) / "literature" / "lancedb"
    d.mkdir(parents=True, exist_ok=True)
    return d


class LiteratureRAG:
    """Literature RAG index — LanceDB vector + BM25 hybrid search.

    Parameters
    ----------
    db_path:
        LanceDB path (None uses the default XDG path).
    model_name:
        Embedding model name.
    table_name:
        LanceDB table name.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        model_name: str = _SPECTER2_MODEL,
        table_name: str = "chunks",
    ) -> None:
        self._db_path = db_path or _lancedb_path()
        self._table_name = table_name
        self._embedding_model = EmbeddingModel(model_name)
        self._bm25 = BM25Index()
        self._chunks: list[Chunk] = []
        self._db: Any = None
        self._table: Any = None

    def _open_db(self) -> Any:
        if self._db is None:
            try:
                import lancedb  # noqa: PLC0415

                self._db = lancedb.connect(str(self._db_path))
            except ImportError as exc:
                raise ImportError(
                    "lancedb not installed — pip install 'maglab[literature]'"
                ) from exc
        return self._db

    def add_document(
        self,
        text: str,
        *,
        doc_id: str,
        doi: str = "",
        title: str = "",
        authors: list[str] | None = None,
        year: int | None = None,
        venue: str = "",
        namespace: str = "literature",
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> int:
        """Chunk, embed, and index a document.

        Returns
        -------
        Number of chunks added.
        """
        raw_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        if not raw_chunks:
            return 0

        embeddings = self._embedding_model.encode(raw_chunks)
        new_chunks: list[Chunk] = []
        for i, (chunk_text_str, emb) in enumerate(zip(raw_chunks, embeddings, strict=False)):
            chunk = Chunk(
                chunk_id=f"{doc_id}_{i:04d}",
                doc_id=doc_id,
                doi=doi,
                title=title,
                authors=", ".join(authors or []),
                year=year,
                venue=venue,
                namespace=namespace,
                text=chunk_text_str,
                chunk_index=i,
                embedding=emb,
            )
            new_chunks.append(chunk)

        self._chunks.extend(new_chunks)
        self._persist_chunks(new_chunks)
        # Rebuild BM25 (full rebuild for incremental updates)
        self._bm25.build(self._chunks)
        log.debug("Document indexed: %s (%d chunks)", title[:50] or doc_id, len(new_chunks))
        return len(new_chunks)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        namespace: str | None = None,
        hybrid_weight: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Hybrid search (vector + BM25 RRF fusion).

        Parameters
        ----------
        query:
            Search query.
        top_k:
            Maximum number of results to return.
        namespace:
            Namespace filter (None searches all).
        hybrid_weight:
            Vector weight [0, 1]. (1 - hybrid_weight) = BM25 weight.

        Returns
        -------
        [{'chunk_id', 'doc_id', 'doi', 'title', 'authors', 'year', 'venue',
          'namespace', 'text', 'score', 'vector_score', 'bm25_score'}, ...].
        """
        if not self._chunks:
            log.debug("No indexed chunks — empty search result")
            return []

        # Vector search
        vector_results = self._vector_search(query, top_k=top_k * 2, namespace=namespace)
        # BM25 search
        bm25_results = self._bm25.search(query, top_k=top_k * 2)

        # BM25 namespace filter
        if namespace:
            chunk_map = {c.chunk_id: c for c in self._chunks}
            bm25_results = [
                (cid, sc)
                for cid, sc in bm25_results
                if chunk_map.get(cid, Chunk("", "", "", "", "", None, "", "", "", 0)).namespace
                == namespace
            ]

        # RRF fusion
        return self._rrf_fusion(
            vector_results,
            bm25_results,
            top_k=top_k,
            vector_weight=hybrid_weight,
        )

    def vector_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        namespace: str | None = None,
    ) -> list[tuple[str, float]]:
        """Vector-only search — returns (chunk_id, score) list."""
        return self._vector_search(query, top_k=top_k, namespace=namespace)

    def _vector_search(
        self,
        query: str,
        top_k: int = 10,
        namespace: str | None = None,
    ) -> list[tuple[str, float]]:
        """Vector search — returns (chunk_id, score)."""
        if not self._chunks:
            return []
        try:
            query_emb = self._embedding_model.encode_one(query)
            import numpy as np  # noqa: PLC0415

            q = np.array(query_emb)
            scored: list[tuple[str, float]] = []
            for c in self._chunks:
                if namespace and c.namespace != namespace:
                    continue
                if not c.embedding:
                    continue
                v = np.array(c.embedding)
                norm = np.linalg.norm(q) * np.linalg.norm(v)
                sim = float(np.dot(q, v) / norm) if norm > 0 else 0.0
                scored.append((c.chunk_id, sim))
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]
        except Exception as exc:  # noqa: BLE001
            log.warning("Vector search failed: %s", exc)
            return []

    def _rrf_fusion(
        self,
        vector_results: list[tuple[str, float]],
        bm25_results: list[tuple[str, float]],
        *,
        top_k: int = 10,
        vector_weight: float = 0.5,
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """Fuse vector and BM25 results using Reciprocal Rank Fusion."""
        chunk_map = {c.chunk_id: c for c in self._chunks}

        vector_rank = {cid: i + 1 for i, (cid, _) in enumerate(vector_results)}
        bm25_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25_results)}

        # Score normalization
        v_max = max((sc for _, sc in vector_results), default=1.0) or 1.0
        b_max = max((sc for _, sc in bm25_results), default=1.0) or 1.0

        v_scores = {cid: sc / v_max for cid, sc in vector_results}
        b_scores = {cid: sc / b_max for cid, sc in bm25_results}

        all_ids = set(vector_rank) | set(bm25_rank)
        fused: list[tuple[str, float, float, float]] = []
        for cid in all_ids:
            vr = vector_rank.get(cid, len(vector_results) + k)
            br = bm25_rank.get(cid, len(bm25_results) + k)
            rrf = vector_weight * (1.0 / (k + vr)) + (1 - vector_weight) * (1.0 / (k + br))
            fused.append((cid, rrf, v_scores.get(cid, 0.0), b_scores.get(cid, 0.0)))

        fused.sort(key=lambda x: x[1], reverse=True)

        results = []
        for cid, rrf_score, v_sc, b_sc in fused[:top_k]:
            c = chunk_map.get(cid)
            if c is None:
                continue
            results.append(
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "doi": c.doi,
                    "title": c.title,
                    "authors": c.authors,
                    "year": c.year,
                    "venue": c.venue,
                    "namespace": c.namespace,
                    "text": c.text,
                    "score": rrf_score,
                    "vector_score": v_sc,
                    "bm25_score": b_sc,
                }
            )
        return results

    def _persist_chunks(self, chunks: list[Chunk]) -> None:
        """Persist chunks to LanceDB (falls back to memory-only if unavailable)."""
        try:
            import pyarrow as pa  # noqa: PLC0415

            db = self._open_db()
            data = {
                "chunk_id": [c.chunk_id for c in chunks],
                "doc_id": [c.doc_id for c in chunks],
                "doi": [c.doi for c in chunks],
                "title": [c.title for c in chunks],
                "authors": [c.authors for c in chunks],
                "year": [c.year or 0 for c in chunks],
                "venue": [c.venue for c in chunks],
                "namespace": [c.namespace for c in chunks],
                "text": [c.text for c in chunks],
                "chunk_index": [c.chunk_index for c in chunks],
                "vector": [c.embedding for c in chunks],
            }
            table = pa.table(data)
            if self._table_name in db.table_names():
                tbl = db.open_table(self._table_name)
                tbl.add(table)
            else:
                db.create_table(self._table_name, data=table)
            log.debug("LanceDB persisted (%d chunks)", len(chunks))
        except Exception as exc:  # noqa: BLE001
            log.debug("LanceDB persist failed (memory-only): %s", exc)

    @property
    def chunk_count(self) -> int:
        """Number of indexed chunks."""
        return len(self._chunks)


# ---------------------------------------------------------------------------
# Module-level default instance
# ---------------------------------------------------------------------------

_default_rag: LiteratureRAG | None = None


def get_rag(db_path: Path | None = None) -> LiteratureRAG:
    """Return the default LiteratureRAG instance."""
    global _default_rag
    if db_path is not None:
        return LiteratureRAG(db_path=db_path)
    if _default_rag is None:
        _default_rag = LiteratureRAG()
    return _default_rag
