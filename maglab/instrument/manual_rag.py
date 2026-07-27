"""Manual PDF reading, structure-aware chunking, embedding, and index — `instrument/manual_rag.py`.

§13.2, T-P4-06·T-P4-07:
- Text and table extraction via `pdfplumber`.
- SCPI command section identification (header and colon-tree recognition).
- One chunk per SCPI command (cmd, page, section_path, params).
- Embedding: local `sentence-transformers` model (default: all-MiniLM-L6-v2).
- Index: sqlite-vec (lancedb alternative — within default [instr] extras scope).

Prioritizes sqlite-vec so it works without lancedb; lancedb is an optional backend.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.core.atomic import atomic_write_text

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SCPI chunk data structure
# ---------------------------------------------------------------------------


@dataclass
class SCPIChunk:
    """One-command SCPI chunk (§13.2 — one chunk per SCPI command)."""

    cmd: str
    """Base SCPI command string (e.g. ':SENS:VOLT:RANG')."""
    description: str
    """Command description (extracted from the manual)."""
    page: int
    """Source PDF page number."""
    section_path: str
    """Section path (e.g. '3 > SCPI Commands > Sense Commands')."""
    params: list[str] = field(default_factory=list)
    """List of parameter descriptions."""
    examples: list[str] = field(default_factory=list)
    """Usage examples."""
    return_type: str = ""
    """Return value type description."""
    limits: dict[str, Any] = field(default_factory=dict)
    """Parameter ranges and limits (when extractable)."""
    raw_text: str = ""
    """Original raw text block."""

    def to_embedding_text(self) -> str:
        """Generate the text used for embedding."""
        parts = [f"SCPI: {self.cmd}", self.description]
        if self.params:
            parts.append("Parameters: " + "; ".join(self.params))
        if self.examples:
            parts.append("Example: " + "; ".join(self.examples[:2]))
        return " | ".join(p for p in parts if p)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "cmd": self.cmd,
            "description": self.description,
            "page": self.page,
            "section_path": self.section_path,
            "params": self.params,
            "examples": self.examples,
            "return_type": self.return_type,
            "limits": self.limits,
            "raw_text": self.raw_text,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SCPIChunk:
        """Restore an SCPIChunk from a dictionary."""
        return cls(
            cmd=d["cmd"],
            description=d.get("description", ""),
            page=d.get("page", 0),
            section_path=d.get("section_path", ""),
            params=d.get("params", []),
            examples=d.get("examples", []),
            return_type=d.get("return_type", ""),
            limits=d.get("limits", {}),
            raw_text=d.get("raw_text", ""),
        )


# ---------------------------------------------------------------------------
# PDF text extraction & SCPI chunking
# ---------------------------------------------------------------------------

# SCPI command pattern: starts with colon or follows a standard SCPI tree pattern
_SCPI_CMD_RE = re.compile(
    r"(?:^|[\s\(])([:\*][A-Z][A-Z0-9:_\[\]]*(?:\?)?)",
    re.MULTILINE | re.IGNORECASE,
)

# Section header pattern (headings starting with digits, dots, and spaces)
_SECTION_HEADER_RE = re.compile(
    r"^(\d+(?:\.\d+)*)\s+(.+)$",
    re.MULTILINE,
)

# SCPI table header identification pattern
_SCPI_TABLE_HEADER_RE = re.compile(
    r"(?:Command|SCPI Command|Syntax|Mnemonic)",
    re.IGNORECASE,
)


class ManualExtractor:
    """Extracts SCPI commands from a PDF instrument manual."""

    def extract_chunks(self, pdf_path: Path) -> list[SCPIChunk]:
        """Extract a list of SCPI command chunks from a PDF.

        Args:
            pdf_path: Path to the manual PDF.

        Returns:
            List of SCPIChunk objects.

        Raises:
            ImportError: When pdfplumber is not installed.
            FileNotFoundError: When the PDF file does not exist.
        """
        try:
            import pdfplumber
        except ImportError as exc:
            raise ImportError("pdfplumber is required: uv pip install -e '.[instr]'") from exc

        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        chunks: list[SCPIChunk] = []
        section_stack: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []

                # Update section headers
                for m in _SECTION_HEADER_RE.finditer(text):
                    header_num = m.group(1)
                    header_text = m.group(2).strip()
                    depth = header_num.count(".")
                    # Manage the stack
                    while len(section_stack) > depth:
                        section_stack.pop()
                    section_stack.append(header_text)

                section_path = " > ".join(section_stack)

                # Extract SCPI commands from text
                text_chunks = self._extract_from_text(text, page_num, section_path)
                chunks.extend(text_chunks)

                # Extract SCPI commands from tables
                for table in tables:
                    if not table:
                        continue
                    # Check header row
                    header_row = table[0] if table else []
                    is_scpi_table = any(
                        _SCPI_TABLE_HEADER_RE.search(str(cell or "")) for cell in header_row
                    )
                    if is_scpi_table:
                        table_chunks = self._extract_from_table(table, page_num, section_path)
                        chunks.extend(table_chunks)

        # Deduplicate — keep only the first occurrence of each cmd
        seen_cmds: set[str] = set()
        unique: list[SCPIChunk] = []
        for chunk in chunks:
            key = chunk.cmd.upper()
            if key not in seen_cmds:
                seen_cmds.add(key)
                unique.append(chunk)

        log.info("SCPI chunk extraction complete: %d chunks (PDF: %s)", len(unique), pdf_path.name)
        return unique

    def _extract_from_text(
        self,
        text: str,
        page: int,
        section_path: str,
    ) -> list[SCPIChunk]:
        """Extract SCPI commands from a text block."""
        chunks: list[SCPIChunk] = []
        lines = text.splitlines()

        for i, line in enumerate(lines):
            # Search for SCPI command patterns
            for m in _SCPI_CMD_RE.finditer(line):
                cmd = m.group(1).strip()
                if len(cmd) < 3:  # Skip patterns that are too short
                    continue
                # Extract surrounding context (5 lines)
                ctx_start = max(0, i - 1)
                ctx_end = min(len(lines), i + 6)
                raw = "\n".join(lines[ctx_start:ctx_end])
                # Description: first non-blank line after the command line
                description = ""
                for j in range(i + 1, min(i + 4, len(lines))):
                    stripped = lines[j].strip()
                    if stripped and not _SCPI_CMD_RE.match(stripped):
                        description = stripped
                        break

                chunks.append(
                    SCPIChunk(
                        cmd=cmd,
                        description=description,
                        page=page,
                        section_path=section_path,
                        raw_text=raw,
                    )
                )
        return chunks

    def _extract_from_table(
        self,
        table: list[list[str | None]],
        page: int,
        section_path: str,
    ) -> list[SCPIChunk]:
        """Extract SCPI commands from a table."""
        chunks: list[SCPIChunk] = []
        if not table or len(table) < 2:
            return chunks

        # Detect Command/Description/Parameter column indices from the header
        header = [str(c or "").upper() for c in table[0]]
        cmd_col = next(
            (i for i, h in enumerate(header) if "COMMAND" in h or "MNEMONIC" in h or "SYNTAX" in h),
            0,
        )
        desc_col = next(
            (i for i, h in enumerate(header) if "DESC" in h or "FUNCTION" in h),
            min(1, len(header) - 1),
        )
        param_col = next(
            (i for i, h in enumerate(header) if "PARAM" in h or "ARGUMENT" in h),
            None,
        )

        for row in table[1:]:
            if not row or cmd_col >= len(row):
                continue
            cmd_raw = str(row[cmd_col] or "").strip()
            if not cmd_raw:
                continue
            # Verify command pattern
            if not _SCPI_CMD_RE.search(cmd_raw) and not cmd_raw.startswith("*"):
                continue
            # Normalize the command
            m = _SCPI_CMD_RE.search(cmd_raw)
            cmd = m.group(1) if m else cmd_raw

            desc = str(row[desc_col] or "").strip() if desc_col < len(row) else ""
            params = []
            if param_col is not None and param_col < len(row):
                param_str = str(row[param_col] or "").strip()
                if param_str:
                    params = [p.strip() for p in re.split(r"[,|]", param_str) if p.strip()]

            chunks.append(
                SCPIChunk(
                    cmd=cmd,
                    description=desc,
                    page=page,
                    section_path=section_path,
                    params=params,
                )
            )
        return chunks


# ---------------------------------------------------------------------------
# Embedding (sentence-transformers — local model)
# ---------------------------------------------------------------------------


class SCPIEmbedder:
    """SCPI chunk embedding generator.

    Default: all-MiniLM-L6-v2 (sentence-transformers).
    Falls back to TF-IDF-based sparse embeddings if not installed.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize the embedding model.

        Args:
            model_name: sentence-transformers model name.
        """
        self._model_name = model_name
        self._model: Any = None

    def _load_model(self) -> Any:
        """Lazily load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_name)
                log.info("sentence-transformers loaded: %s", self._model_name)
            except ImportError:
                log.warning(
                    "sentence-transformers not installed — using TF-IDF fallback embeddings. "
                    "Install with: pip install sentence-transformers for higher-quality embeddings."
                )
                self._model = _TFIDFFallback()
            except Exception as exc:  # noqa: BLE001 - model cache/network failures vary by backend
                log.warning(
                    "sentence-transformers model '%s' could not be loaded (%s) — "
                    "using TF-IDF fallback embeddings.",
                    self._model_name,
                    exc,
                )
                self._model = _TFIDFFallback()
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        model = self._load_model()
        if hasattr(model, "encode"):
            vecs = model.encode(texts, show_progress_bar=False)
            return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vecs]
        return model.embed(texts)


class _TFIDFFallback:
    """TF-IDF fallback embeddings used when sentence-transformers is not installed."""

    def __init__(self) -> None:
        self._fitted = False
        self._vocab: dict[str, int] = {}

    def encode(self, texts: list[str], **_kwargs: Any) -> list[list[float]]:
        return self.embed(texts)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return simple bag-of-words vectors."""
        if not self._fitted:
            all_words: list[str] = []
            for t in texts:
                all_words.extend(re.findall(r"\w+", t.lower()))
            vocab_set = sorted(set(all_words))[:512]
            self._vocab = {w: i for i, w in enumerate(vocab_set)}
            self._fitted = True

        results: list[list[float]] = []
        dim = max(len(self._vocab), 1)
        for text in texts:
            vec = [0.0] * dim
            words = re.findall(r"\w+", text.lower())
            for w in words:
                idx = self._vocab.get(w)
                if idx is not None:
                    vec[idx] += 1.0
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            results.append(vec)
        return results


# ---------------------------------------------------------------------------
# SQLite-based index (works without lancedb)
# ---------------------------------------------------------------------------


class SCPIIndex:
    """Embedding-based similarity search index for SCPI chunks.

    Works without lancedb using SQLite and serialized vectors.
    """

    def __init__(
        self,
        index_dir: Path,
        model_key: str,
        embedder: SCPIEmbedder | None = None,
    ) -> None:
        """Initialize the index.

        Args:
            index_dir: Directory for storing the index.
            model_key: Instrument model key.
            embedder: Embedding generator; defaults to a new SCPIEmbedder if None.
        """
        self._dir = index_dir
        self._model_key = model_key
        self._embedder = embedder or SCPIEmbedder()
        self._db_path = index_dir / f"{model_key}.db"
        self._chunks: list[SCPIChunk] = []
        self._vecs: list[list[float]] = []

    def build(self, chunks: list[SCPIChunk]) -> None:
        """Build the index from a list of chunks.

        Args:
            chunks: List of SCPIChunk objects.
        """
        if not chunks:
            log.warning("No chunks provided — leaving index empty.")
            return

        self._dir.mkdir(parents=True, exist_ok=True)
        self._chunks = chunks

        texts = [c.to_embedding_text() for c in chunks]
        self._vecs = self._embedder.embed(texts)

        # Determine embedder identity: class name and vector dimension.
        # These are stored in a meta table so load() can detect cross-class mismatches.
        model = self._embedder._load_model()
        embedder_class = type(model).__name__
        vec_dim = len(self._vecs[0]) if self._vecs else 0

        # Serialize and save to SQLite — use context manager so the
        # connection is always closed even if an exception occurs.
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, data TEXT, vec TEXT)"
            )
            # Persist embedder identity in a metadata table so load() can detect
            # cross-class mismatches (e.g. sentence-transformers build → TF-IDF load).
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("DELETE FROM chunks")
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('embedder_class', ?)",
                (embedder_class,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('vec_dim', ?)",
                (str(vec_dim),),
            )
            for i, (chunk, vec) in enumerate(zip(chunks, self._vecs, strict=False)):
                conn.execute(
                    "INSERT INTO chunks (id, data, vec) VALUES (?, ?, ?)",
                    (i, json.dumps(chunk.to_dict()), json.dumps(vec)),
                )
            # sqlite3 context manager commits on clean exit; explicit commit is
            # kept here for clarity and forward-compatibility with isolation_level
            # overrides.
            conn.commit()

        log.debug("Embedder metadata persisted: class=%s, dim=%d", embedder_class, vec_dim)

        # Persist the TF-IDF fallback vocabulary so that a new session can
        # restore it via load() and produce same-dimension query vectors.
        # Without this, load() would refit the vocab on the query alone
        # (dim=1–5) while stored vecs have corpus-sized dimension, causing
        # _cosine_similarity to truncate and return meaningless scores.
        # Duck-type check: any model exposing _vocab is a TF-IDF-style fallback.
        if hasattr(model, "_vocab") and hasattr(model, "_fitted"):
            vocab_path = self._db_path.with_suffix(".vocab.json")
            # Atomic: the restore path logs a warning and carries on with no
            # vocabulary, so a truncated file silently degrades search quality
            # rather than failing visibly.
            atomic_write_text(vocab_path, json.dumps(model._vocab))
            log.debug("TF-IDF vocabulary persisted: %d terms → %s", len(model._vocab), vocab_path)

        log.info("Index built: %d chunks → %s", len(chunks), self._db_path)

    def load(self) -> None:
        """Load the index from disk."""
        if not self._db_path.is_file():
            log.warning("Index file not found: %s", self._db_path)
            return
        # Use context manager so the connection is always closed, even if
        # sqlite3.OperationalError (e.g. DB locked) or another exception occurs.
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT data, vec FROM chunks ORDER BY id").fetchall()
            # Read persisted embedder metadata — absent in older indexes (degrade gracefully).
            try:
                meta_rows = conn.execute("SELECT key, value FROM meta").fetchall()
                stored_meta: dict[str, str] = dict(meta_rows)
            except Exception:  # noqa: BLE001 — table may not exist in older indexes
                stored_meta = {}

        self._chunks = [SCPIChunk.from_dict(json.loads(r[0])) for r in rows]
        self._vecs = [json.loads(r[1]) for r in rows]

        # Restore TF-IDF fallback vocabulary FIRST (R8-F1 fix: must happen before the
        # dimension probe so the probe reflects the corpus-size vocab, not the single-word
        # "probe" vocab that an unfitted _TFIDFFallback would fit on the probe text).
        # Without this ordering, a legitimate TF-IDF→TF-IDF cross-session reload emits a
        # spurious dimension-mismatch warning even though the sidecar guarantees correctness.
        # Older indexes that have no sidecar fall back gracefully — intentional for
        # backward compatibility.
        vocab_path = self._db_path.with_suffix(".vocab.json")
        if vocab_path.is_file():
            model = self._embedder._load_model()
            # Duck-type check: restore vocab into any model that exposes _vocab/_fitted
            # (i.e. _TFIDFFallback and compatible wrappers).
            if hasattr(model, "_vocab") and hasattr(model, "_fitted"):
                try:
                    vocab: dict[str, int] = json.loads(vocab_path.read_text(encoding="utf-8"))
                    model._vocab = vocab
                    model._fitted = True
                    log.debug("TF-IDF vocabulary restored: %d terms ← %s", len(vocab), vocab_path)
                except (json.JSONDecodeError, OSError) as exc:
                    log.warning("Could not restore TF-IDF vocabulary from %s: %s", vocab_path, exc)

        # Cross-class embedder mismatch check (R7-F2).
        # When the index was built with sentence-transformers (384-dim) and the
        # current session uses the TF-IDF fallback (low-dim), cosine similarity
        # truncates stored vectors and returns semantically meaningless results
        # without any error.  Emit a clear warning so the failure is visible.
        # NOTE: vocab restore above runs first so the dimension probe below is accurate
        # for TF-IDF→TF-IDF reloads (the restored corpus vocab gives the correct dim).
        if stored_meta:
            stored_class = stored_meta.get("embedder_class", "")
            stored_dim_str = stored_meta.get("vec_dim", "")
            current_model = self._embedder._load_model()
            current_class = type(current_model).__name__
            if stored_class and stored_class != current_class:
                log.warning(
                    "Embedder class mismatch: index was built with '%s' but the current "
                    "session uses '%s'. Search results will be incorrect. "
                    "Rebuild the index with the same embedder.",
                    stored_class,
                    current_class,
                )
            elif stored_dim_str:
                stored_dim = int(stored_dim_str)
                current_dim: int | None = None
                # Probe current embedder dimension with a short test text — cheaper than
                # embedding all chunks.  Only check when classes match (different classes
                # are already warned above).  The vocab sidecar (if present) is already
                # restored above, so the probe returns the corpus-sized dimension.
                try:
                    probe = self._embedder.embed(["probe"])
                    current_dim = len(probe[0]) if probe else None
                except Exception:  # noqa: BLE001
                    pass
                if current_dim is not None and stored_dim != current_dim:
                    log.warning(
                        "Embedder dimension mismatch: index has %d-dim vectors but the "
                        "current embedder produces %d-dim vectors. "
                        "Search results will be incorrect. "
                        "Rebuild the index with the same embedder.",
                        stored_dim,
                        current_dim,
                    )

        log.info("Index loaded: %d chunks ← %s", len(self._chunks), self._db_path)

    def search(self, query: str, k: int = 5) -> list[tuple[SCPIChunk, float]]:
        """Search for SCPI chunks similar to the query text.

        Args:
            query: Query text.
            k: Maximum number of results to return.

        Returns:
            List of (SCPIChunk, similarity score) tuples — highest score first.
        """
        if not self._chunks:
            self.load()
        if not self._chunks:
            return []

        q_vec = self._embedder.embed([query])[0]

        # Compute cosine similarity
        scored: list[tuple[float, int]] = []
        for i, v in enumerate(self._vecs):
            sim = _cosine_similarity(q_vec, v)
            scored.append((sim, i))

        scored.sort(key=lambda x: -x[0])
        return [(self._chunks[i], score) for score, i in scored[:k]]

    @property
    def chunk_count(self) -> int:
        """Number of chunks stored in the index."""
        return len(self._chunks)

    def exists(self) -> bool:
        """Check whether the index file exists."""
        return self._db_path.is_file()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute the cosine similarity between two vectors."""
    if len(a) != len(b):
        min_dim = min(len(a), len(b))
        a = a[:min_dim]
        b = b[:min_dim]
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Integrated pipeline
# ---------------------------------------------------------------------------

_DEFAULT_INDEX_ROOT = Path.home() / ".local" / "share" / "maglab" / "indexes"


class ManualRAGPipeline:
    """End-to-end pipeline: manual PDF → SCPI chunking → embedding → search.

    §13.2 T-P4-06·T-P4-07·T-P4-08.
    """

    def __init__(
        self,
        index_root: Path | None = None,
        embedder: SCPIEmbedder | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            index_root: Root directory for storing indexes.
            embedder: Embedding generator.
        """
        self._index_root = index_root or _DEFAULT_INDEX_ROOT
        self._embedder = embedder or SCPIEmbedder()
        self._extractor = ManualExtractor()
        self._indexes: dict[str, SCPIIndex] = {}

    def ingest(self, model_key: str, pdf_path: Path) -> SCPIIndex:
        """Ingest a PDF and build the index.

        Args:
            model_key: Instrument model key (index identifier).
            pdf_path: Path to the manual PDF.

        Returns:
            The built SCPIIndex.
        """
        log.info("Starting manual ingestion: %s (%s)", model_key, pdf_path)
        chunks = self._extractor.extract_chunks(pdf_path)
        index_dir = self._index_root / model_key
        index = SCPIIndex(index_dir, model_key, self._embedder)
        index.build(chunks)
        self._indexes[model_key] = index
        return index

    def get_index(self, model_key: str) -> SCPIIndex | None:
        """Retrieve an existing index, loading from disk if needed."""
        if model_key in self._indexes:
            return self._indexes[model_key]
        index_dir = self._index_root / model_key
        index = SCPIIndex(index_dir, model_key, self._embedder)
        if index.exists():
            index.load()
            self._indexes[model_key] = index
            return index
        return None

    def search(
        self,
        model_key: str,
        query: str,
        k: int = 5,
    ) -> list[tuple[SCPIChunk, float]]:
        """Search for SCPI commands.

        Args:
            model_key: Instrument model key.
            query: Search query text.
            k: Maximum number of results to return.

        Returns:
            List of (SCPIChunk, similarity score) tuples.
        """
        index = self.get_index(model_key)
        if index is None:
            log.warning("Index not found for: %s. Run `ingest()` first.", model_key)
            return []
        return index.search(query, k=k)
