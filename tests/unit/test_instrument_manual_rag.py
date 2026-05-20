"""tests/unit/test_instrument_manual_rag.py — manual RAG unit tests."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from maglab.instrument.manual_rag import (
    ManualRAGPipeline,
    SCPIChunk,
    SCPIEmbedder,
    SCPIIndex,
    _cosine_similarity,
    _TFIDFFallback,
)

# ---------------------------------------------------------------------------
# SCPIChunk
# ---------------------------------------------------------------------------


def test_scpi_chunk_to_embedding_text():
    """to_embedding_text() should return a non-empty string."""
    chunk = SCPIChunk(
        cmd=":SENS:VOLT:RANG",
        description="Set the voltage measurement range.",
        page=5,
        section_path="3 > SCPI > Sense",
        params=["<range>: 0.1|1|10|100|1000"],
    )
    text = chunk.to_embedding_text()
    assert ":SENS:VOLT:RANG" in text
    assert "voltage" in text.lower()


def test_scpi_chunk_serialization():
    """to_dict() / from_dict() round-trip serialization should work."""
    chunk = SCPIChunk(
        cmd=":SOUR:VOLT",
        description="Set the voltage source.",
        page=10,
        section_path="4 > Source Commands",
    )
    d = chunk.to_dict()
    restored = SCPIChunk.from_dict(d)
    assert restored.cmd == chunk.cmd
    assert restored.description == chunk.description
    assert restored.page == chunk.page


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical():
    """Similarity of identical vectors should be 1.0."""
    v = [1.0, 0.0, 0.0]
    assert _cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    """Similarity of orthogonal vectors should be 0.0."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    assert _cosine_similarity(v1, v2) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector():
    """Should return 0.0 for a zero vector input."""
    v1 = [0.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert _cosine_similarity(v1, v2) == 0.0


def test_cosine_similarity_different_lengths():
    """Should handle vectors of different lengths (truncates to shortest)."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0]
    # Should return without raising
    result = _cosine_similarity(v1, v2)
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# _TFIDFFallback
# ---------------------------------------------------------------------------


def test_tfidf_fallback_embed():
    """TF-IDF fallback embedding should return a list."""
    fallback = _TFIDFFallback()
    texts = ["SCPI voltage measurement", "current source command"]
    vecs = fallback.embed(texts)
    assert len(vecs) == 2
    assert all(isinstance(v, list) for v in vecs)


def test_tfidf_fallback_similar_texts_higher_similarity():
    """Similar texts should have higher similarity than dissimilar texts."""
    fallback = _TFIDFFallback()
    texts = [
        "voltage measurement range",
        "voltage source range",
        "current frequency phase",
    ]
    vecs = fallback.embed(texts)
    sim_same = _cosine_similarity(vecs[0], vecs[1])
    sim_diff = _cosine_similarity(vecs[0], vecs[2])
    assert sim_same >= sim_diff


# ---------------------------------------------------------------------------
# SCPIEmbedder
# ---------------------------------------------------------------------------


def test_scpi_embedder_returns_list():
    """SCPIEmbedder should return a list."""
    embedder = SCPIEmbedder()
    texts = ["SCPI voltage", "current measurement"]
    vecs = embedder.embed(texts)
    assert len(vecs) == 2
    assert all(isinstance(v, list) for v in vecs)


# ---------------------------------------------------------------------------
# SCPIIndex
# ---------------------------------------------------------------------------


def test_scpi_index_build_and_search():
    """Search should work after building the index."""
    chunks = [
        SCPIChunk(cmd=":SENS:VOLT", description="Voltage measurement", page=1, section_path="3 > Sense"),
        SCPIChunk(cmd=":SOUR:CURR", description="Current source", page=2, section_path="4 > Source"),
        SCPIChunk(
            cmd=":FREQ:CENT", description="Frequency center", page=3, section_path="5 > Frequency"
        ),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        index_dir = Path(tmpdir) / "test_index"
        index = SCPIIndex(index_dir, "test-model")
        index.build(chunks)

        # Search
        results = index.search("voltage measure", k=2)
        assert len(results) <= 2
        assert all(isinstance(r[0], SCPIChunk) for r in results)
        assert all(isinstance(r[1], float) for r in results)

        # Flexible check: any result returned is OK
        assert len(results) > 0


def test_scpi_index_save_and_load():
    """The index should be saved and reloaded correctly."""
    chunks = [
        SCPIChunk(cmd=":MEAS:VOLT?", description="Voltage measurement query", page=1, section_path=""),
        SCPIChunk(cmd=":CONF:CURR", description="Current measurement configuration", page=2, section_path=""),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        index_dir = Path(tmpdir) / "idx"
        index = SCPIIndex(index_dir, "model1")
        index.build(chunks)

        # Load with a new instance
        index2 = SCPIIndex(index_dir, "model1")
        index2.load()
        assert index2.chunk_count == 2
        results = index2.search("current", k=1)
        assert len(results) == 1


def test_scpi_index_empty_build():
    """Building an index from an empty chunk list should not raise."""
    with tempfile.TemporaryDirectory() as tmpdir:
        index = SCPIIndex(Path(tmpdir), "empty")
        index.build([])
        results = index.search("anything", k=5)
        assert results == []


def test_scpi_index_exists():
    """Should correctly report whether the index file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        index = SCPIIndex(Path(tmpdir) / "idx", "model")
        assert not index.exists()
        index.build([SCPIChunk(cmd="*RST", description="Reset", page=1, section_path="")])
        assert index.exists()


# ---------------------------------------------------------------------------
# ManualRAGPipeline (tested with mock chunks — no PDF required)
# ---------------------------------------------------------------------------


def test_manual_rag_pipeline_get_nonexistent_index():
    """A nonexistent index should return None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = ManualRAGPipeline(index_root=Path(tmpdir))
        result = pipeline.get_index("nonexistent-model")
        assert result is None


def test_manual_rag_pipeline_search_empty():
    """Should return an empty list when no index is available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = ManualRAGPipeline(index_root=Path(tmpdir))
        results = pipeline.search("nonexistent-model", "voltage", k=5)
        assert results == []


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 5)
# ---------------------------------------------------------------------------


class TestR5Finding1SqliteConnectionSafety:
    """R5-F1 (MEDIUM): SQLite connection must be closed even when an exception
    occurs inside SCPIIndex.build() or SCPIIndex.load().

    The fix uses ``with sqlite3.connect(...) as conn:`` so the context manager
    guarantees cleanup on both normal exit and exception paths.
    """

    def test_build_closes_connection_on_insert_error(self) -> None:
        """Connection is released when an INSERT raises sqlite3.OperationalError."""
        import sqlite3
        from unittest.mock import MagicMock, patch

        chunks = [
            SCPIChunk(cmd=":SENS:VOLT", description="Voltage", page=1, section_path=""),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SCPIIndex(Path(tmpdir) / "idx", "model")

            # Patch sqlite3.connect to return a context-manager-aware mock that
            # raises OperationalError on execute("DELETE FROM chunks").
            class _FakeConn:
                """Mimics the sqlite3 connection context-manager protocol."""

                def __init__(self) -> None:
                    self._closed = False

                def execute(self, sql: str, *args: object) -> MagicMock:  # type: ignore[override]
                    if "DELETE" in sql:
                        raise sqlite3.OperationalError("simulated disk full")
                    return MagicMock()

                def commit(self) -> None:
                    pass

                def rollback(self) -> None:
                    pass

                def close(self) -> None:
                    self._closed = True

                def __enter__(self) -> _FakeConn:
                    return self

                def __exit__(self, *_: object) -> None:
                    self.close()

            fake_conn = _FakeConn()

            def _fake_connect(path: object, **kw: object) -> _FakeConn:
                return fake_conn

            with (
                patch("maglab.instrument.manual_rag.sqlite3.connect", side_effect=_fake_connect),
                pytest.raises(sqlite3.OperationalError, match="simulated disk full"),
            ):
                index.build(chunks)

            # The context manager must have called close() exactly once
            assert fake_conn._closed, (
                "sqlite3 connection was NOT closed after OperationalError in build()"
            )

    def test_load_closes_connection_on_execute_error(self) -> None:
        """Connection is released when SELECT raises sqlite3.OperationalError."""
        import sqlite3
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"
            index_dir.mkdir(parents=True)
            db_path = index_dir / "model.db"
            # Create a real (but empty) file so is_file() passes in load()
            db_path.touch()

            index = SCPIIndex(index_dir, "model")

            class _FakeConn:
                def __init__(self) -> None:
                    self._closed = False

                def execute(self, sql: str, *args: object) -> None:  # type: ignore[override]
                    raise sqlite3.OperationalError("simulated read error")

                def rollback(self) -> None:
                    pass

                def close(self) -> None:
                    self._closed = True

                def __enter__(self) -> _FakeConn:
                    return self

                def __exit__(self, *_: object) -> None:
                    self.close()

            fake_conn = _FakeConn()

            with (
                patch(
                    "maglab.instrument.manual_rag.sqlite3.connect", return_value=fake_conn
                ),
                pytest.raises(sqlite3.OperationalError, match="simulated read error"),
            ):
                index.load()

            assert fake_conn._closed, (
                "sqlite3 connection was NOT closed after OperationalError in load()"
            )


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 6, domain 03)
# ---------------------------------------------------------------------------


class TestR6Finding2TFIDFFallbackVocabPersistence:
    """R6-F2 (LOW): _TFIDFFallback vocabulary must be persisted as a JSON sidecar
    alongside the SQLite index during build() and restored during load() so that
    cross-session searches produce same-dimension vectors and meaningful similarity
    scores.

    Without the fix, load() creates a fresh unfitted _TFIDFFallback that refits on
    the query alone (dim=1-5) while stored vecs have corpus-sized dimension N,
    causing _cosine_similarity to truncate to min(N, 1-5) and return wrong scores.

    Tests inject a ``_NoEncodeFallback`` wrapper (which hides ``encode()`` so that
    ``SCPIEmbedder.embed()`` routes to the ``embed()`` path rather than the numpy
    ``model.encode()`` → ``.tolist()`` path used for real SentenceTransformer models).
    This simulates a session where sentence-transformers is absent without needing
    sys.modules patching.
    """

    def _make_corpus_chunks(self) -> list[SCPIChunk]:
        """Return a diverse set of chunks to build a multi-term vocabulary."""
        return [
            SCPIChunk(cmd=":SENS:VOLT:RANG", description="Set the voltage measurement range", page=1, section_path="3 > Sense"),
            SCPIChunk(cmd=":SENS:CURR:RANG", description="Set the current measurement range", page=2, section_path="3 > Sense"),
            SCPIChunk(cmd=":SOUR:VOLT", description="Set source voltage output level", page=3, section_path="4 > Source"),
            SCPIChunk(cmd=":SOUR:CURR", description="Set source current output level", page=4, section_path="4 > Source"),
            SCPIChunk(cmd=":FREQ:CENT", description="Set center frequency for sweep", page=5, section_path="5 > Frequency"),
            SCPIChunk(cmd=":TRIG:SOUR", description="Select trigger source", page=6, section_path="6 > Trigger"),
            SCPIChunk(cmd=":DISP:UPD", description="Update display refresh", page=7, section_path="7 > Display"),
            SCPIChunk(cmd=":MEAS:POW?", description="Query measured power level", page=8, section_path="8 > Measure"),
        ]

    @staticmethod
    def _make_index_with_fallback(
        index_dir: Path,
        model_key: str,
        fb: _TFIDFFallback,
    ) -> tuple[SCPIIndex, SCPIEmbedder]:
        """Return an (SCPIIndex, SCPIEmbedder) pair backed by ``fb``.

        ``SCPIEmbedder.embed()`` dispatches to ``model.embed()`` only when the
        model has no ``encode`` attribute.  ``_TFIDFFallback`` does have ``encode``,
        so we wrap it in ``_NoEncodeFallback`` to force the correct dispatch branch.
        Both ``_load_model()`` and the ``embed()`` method are monkey-patched on the
        embedder instance so that ``SCPIIndex.build()``/``load()`` see ``fb`` for
        the vocab-persist duck-type check (``hasattr(model, "_vocab")``).
        """
        from unittest.mock import patch as _patch

        class _NoEncodeFallback:
            """Wrapper around _TFIDFFallback that omits encode() to force embed() path."""

            def __init__(self, inner: _TFIDFFallback) -> None:
                self._inner = inner

            @property
            def _vocab(self) -> dict[str, int]:
                return self._inner._vocab

            @_vocab.setter
            def _vocab(self, v: dict[str, int]) -> None:
                self._inner._vocab = v

            @property
            def _fitted(self) -> bool:
                return self._inner._fitted

            @_fitted.setter
            def _fitted(self, v: bool) -> None:
                self._inner._fitted = v

            def embed(self, texts: list[str]) -> list[list[float]]:
                return self._inner.embed(texts)

        wrapper = _NoEncodeFallback(fb)
        embedder = SCPIEmbedder()
        # Override _load_model at the instance level; build()/load() call this
        # to get the model object for the vocab-persist duck-type check.
        embedder._load_model = lambda: wrapper  # type: ignore[method-assign]

        def _embed_method(self_e: SCPIEmbedder, texts: list[str]) -> list[list[float]]:
            # Route through wrapper.embed() (no encode()) rather than the
            # numpy .tolist() path that SCPIEmbedder.embed() uses for SentenceTransformer.
            return self_e._load_model().embed(texts)

        with _patch.object(SCPIEmbedder, "embed", _embed_method):
            index = SCPIIndex(index_dir, model_key, embedder=embedder)
        return index, embedder

    def _build_with_fallback(
        self, index_dir: Path, model_key: str, chunks: list[SCPIChunk]
    ) -> tuple[SCPIIndex, _TFIDFFallback]:
        """Build index with _TFIDFFallback and return (index, fallback)."""
        from unittest.mock import patch as _patch

        fb = _TFIDFFallback()
        index, embedder = self._make_index_with_fallback(index_dir, model_key, fb)

        def _embed_method(self_e: SCPIEmbedder, texts: list[str]) -> list[list[float]]:
            return self_e._load_model().embed(texts)

        with _patch.object(SCPIEmbedder, "embed", _embed_method):
            index.build(chunks)
        return index, fb

    def _load_with_fallback(
        self, index_dir: Path, model_key: str
    ) -> tuple[SCPIIndex, _TFIDFFallback]:
        """Load index with a fresh _TFIDFFallback and return (index, fallback)."""
        from unittest.mock import patch as _patch

        fb = _TFIDFFallback()
        index, embedder = self._make_index_with_fallback(index_dir, model_key, fb)

        def _embed_method(self_e: SCPIEmbedder, texts: list[str]) -> list[list[float]]:
            return self_e._load_model().embed(texts)

        with _patch.object(SCPIEmbedder, "embed", _embed_method):
            index.load()
        return index, fb

    def test_vocab_sidecar_created_on_build(self) -> None:
        """build() must write a .vocab.json sidecar when using _TFIDFFallback."""
        chunks = self._make_corpus_chunks()

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"
            index, fb = self._build_with_fallback(index_dir, "model", chunks)

            vocab_path = index_dir / "model.vocab.json"
            assert vocab_path.is_file(), (
                "build() did not create a .vocab.json sidecar when using _TFIDFFallback"
            )
            vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
            assert isinstance(vocab, dict), "vocab sidecar must be a JSON object"
            assert len(vocab) > 1, "vocab sidecar must contain more than one term"

    def test_load_restores_vocab_dimension(self) -> None:
        """After build→load in a fresh embedder, vector dimension must match corpus dimension."""
        chunks = self._make_corpus_chunks()

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            # Session A: build
            index_a, fb_a = self._build_with_fallback(index_dir, "model", chunks)
            corpus_dim = len(index_a._vecs[0])
            assert corpus_dim > 5, (
                f"Corpus vocab dimension too small ({corpus_dim}). Diversify chunks."
            )

            # Session B: fresh fallback, load
            _index_b, fb_b = self._load_with_fallback(index_dir, "model")

            # fb_b._vocab must now contain the corpus vocab (restored from sidecar)
            assert fb_b._fitted, "Fallback must be marked as fitted after load()"
            assert len(fb_b._vocab) == corpus_dim, (
                f"Restored vocab size {len(fb_b._vocab)} != corpus_dim {corpus_dim}. "
                "Vocab sidecar was not correctly restored."
            )

            # Embed a query using the restored vocab — must produce corpus_dim vector
            query_vec = fb_b.embed(["voltage range"])[0]
            assert len(query_vec) == corpus_dim, (
                f"Query vector dim {len(query_vec)} != corpus_dim {corpus_dim} after load."
            )

    def test_load_yields_stable_similarity_scores(self) -> None:
        """build→load round-trip must yield same top-1 result as in-session search."""
        chunks = self._make_corpus_chunks()

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            from unittest.mock import patch as _patch

            def _embed_method(self_e: SCPIEmbedder, texts: list[str]) -> list[list[float]]:
                return self_e._load_model().embed(texts)

            # Session A: build and search in-session
            fb_a = _TFIDFFallback()
            index_a, _ = self._make_index_with_fallback(index_dir, "model", fb_a)
            with _patch.object(SCPIEmbedder, "embed", _embed_method):
                index_a.build(chunks)
                results_a = index_a.search("voltage range", k=1)

            assert results_a, "In-session search returned no results"
            top_cmd_a = results_a[0][0].cmd

            # Session B: fresh fallback, load, search
            fb_b = _TFIDFFallback()
            index_b, _ = self._make_index_with_fallback(index_dir, "model", fb_b)
            with _patch.object(SCPIEmbedder, "embed", _embed_method):
                index_b.load()
                results_b = index_b.search("voltage range", k=1)

            assert results_b, "Cross-session search returned no results"
            top_cmd_b = results_b[0][0].cmd

            assert top_cmd_a == top_cmd_b, (
                f"Cross-session top-1 result changed: in-session={top_cmd_a!r}, "
                f"after-load={top_cmd_b!r}. Vocabulary may not have been restored."
            )

    def test_load_without_sidecar_does_not_crash(self) -> None:
        """load() on an index with no .vocab.json sidecar must not raise (older indexes)."""
        chunks = [
            SCPIChunk(cmd=":RST", description="Reset", page=1, section_path=""),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            # Build with whatever embedder is available (no forced fallback here)
            embedder_a = SCPIEmbedder()
            index_a = SCPIIndex(index_dir, "model", embedder=embedder_a)
            index_a.build(chunks)

            # Remove sidecar if present — simulates an older index that pre-dates the fix
            vocab_path = index_dir / "model.vocab.json"
            if vocab_path.is_file():
                vocab_path.unlink()

            # Load with a fresh embedder — must not raise even without sidecar
            embedder_b = SCPIEmbedder()
            index_b = SCPIIndex(index_dir, "model", embedder=embedder_b)
            try:
                index_b.load()
            except Exception as exc:
                raise AssertionError(
                    f"load() raised {type(exc).__name__} when .vocab.json sidecar is absent: {exc}"
                ) from exc
            assert index_b.chunk_count == 1, "Chunks must be loaded even without vocab sidecar"


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 7, domain 03)
# ---------------------------------------------------------------------------


class TestR7Finding2EmbedderMismatchWarning:
    """R7-F2 (LOW): When an index is built with one embedder class and loaded
    in a session with an incompatible embedder (different class name or vector
    dimension), SCPIIndex.load() must emit a logging.warning rather than
    silently returning wrong search results.

    The fix persists the embedder class name and vector dimension in a SQLite
    ``meta`` table at build() time, and compares against the current embedder
    at load() time.
    """

    def _make_corpus_chunks(self) -> list[SCPIChunk]:
        return [
            SCPIChunk(cmd=":SENS:VOLT", description="Voltage measurement range", page=1, section_path=""),
            SCPIChunk(cmd=":SOUR:CURR", description="Current source level", page=2, section_path=""),
            SCPIChunk(cmd=":TRIG:SOUR", description="Trigger source selection", page=3, section_path=""),
        ]

    def test_meta_table_written_on_build(self) -> None:
        """build() must write embedder_class and vec_dim into the meta table."""
        import sqlite3

        chunks = self._make_corpus_chunks()
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"
            index = SCPIIndex(index_dir, "model")
            index.build(chunks)

            db_path = index_dir / "model.db"
            assert db_path.is_file(), "SQLite index file must exist after build()"

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute("SELECT key, value FROM meta").fetchall()

            meta = dict(rows)
            assert "embedder_class" in meta, "meta table must contain 'embedder_class'"
            assert "vec_dim" in meta, "meta table must contain 'vec_dim'"
            assert meta["embedder_class"], "embedder_class must not be empty"
            assert int(meta["vec_dim"]) > 0, "vec_dim must be a positive integer"

    def test_class_mismatch_emits_warning(self) -> None:
        """load() must emit a warning when embedder class differs from the stored class."""
        import sqlite3

        chunks = self._make_corpus_chunks()
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            # Build with the default embedder (whatever class it picks).
            index_a = SCPIIndex(index_dir, "model")
            index_a.build(chunks)

            # Manually overwrite the stored embedder_class to a synthetic name that
            # cannot match any real embedder class — simulates "built with X, loaded with Y".
            db_path = index_dir / "model.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "UPDATE meta SET value='FakeEmbedderClassThatDoesNotExist' WHERE key='embedder_class'"
                )
                conn.commit()

            # Load in a new SCPIIndex with a fresh embedder — class will differ.
            index_b = SCPIIndex(index_dir, "model")

            # Capture logging.WARNING messages from the manual_rag module.
            rag_logger = logging.getLogger("maglab.instrument.manual_rag")
            captured: list[str] = []

            class _CapHandler(logging.Handler):
                def emit(self, record: logging.LogRecord) -> None:
                    if record.levelno >= logging.WARNING:
                        captured.append(record.getMessage())

            handler = _CapHandler()
            rag_logger.addHandler(handler)
            try:
                index_b.load()
            finally:
                rag_logger.removeHandler(handler)

            mismatch_warnings = [m for m in captured if "mismatch" in m.lower()]
            assert mismatch_warnings, (
                "load() did not emit a warning when embedder class mismatches the stored class. "
                f"All captured warnings: {captured!r}"
            )

    def test_dim_mismatch_emits_warning(self) -> None:
        """load() must emit a warning when stored vec_dim differs from the current embedder dim."""
        import sqlite3

        chunks = self._make_corpus_chunks()
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            # Build normally.
            index_a = SCPIIndex(index_dir, "model")
            index_a.build(chunks)

            # Overwrite vec_dim to a value the current embedder will never produce,
            # while keeping embedder_class unchanged so only the dim branch fires.
            db_path = index_dir / "model.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE meta SET value='9999' WHERE key='vec_dim'")
                conn.commit()

            index_b = SCPIIndex(index_dir, "model")
            rag_logger = logging.getLogger("maglab.instrument.manual_rag")
            captured: list[str] = []

            class _CapHandler(logging.Handler):
                def emit(self, record: logging.LogRecord) -> None:
                    if record.levelno >= logging.WARNING:
                        captured.append(record.getMessage())

            handler = _CapHandler()
            rag_logger.addHandler(handler)
            try:
                index_b.load()
            finally:
                rag_logger.removeHandler(handler)

            mismatch_warnings = [m for m in captured if "mismatch" in m.lower()]
            assert mismatch_warnings, (
                "load() did not emit a warning when vec_dim mismatches. "
                f"All captured warnings: {captured!r}"
            )

    def test_load_without_meta_table_does_not_crash(self) -> None:
        """load() on an older index without a meta table must not raise."""
        import sqlite3

        chunks = self._make_corpus_chunks()
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            # Build normally, then drop the meta table to simulate an older index.
            index_a = SCPIIndex(index_dir, "model")
            index_a.build(chunks)

            db_path = index_dir / "model.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("DROP TABLE IF EXISTS meta")
                conn.commit()

            index_b = SCPIIndex(index_dir, "model")
            try:
                index_b.load()
            except Exception as exc:
                raise AssertionError(
                    f"load() raised {type(exc).__name__} on an index with no meta table: {exc}"
                ) from exc
            assert index_b.chunk_count == len(chunks), (
                "Chunks must be loaded correctly even without meta table"
            )


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 8, domain 03)
# ---------------------------------------------------------------------------


class TestR8Finding1TFIDFDimProbeOrder:
    """R8-F1 (LOW): SCPIIndex.load() must restore the TF-IDF vocab sidecar BEFORE
    probing the embedder dimension.  The previous ordering ran the probe on an
    unfitted _TFIDFFallback (dim=1), compared it to the stored corpus dim (N), and
    emitted a spurious dimension-mismatch warning even though the search results
    were correct.

    Fix: vocab restore now precedes the dimension probe so the probe returns the
    correct corpus-sized dimension for a TF-IDF→TF-IDF cross-session reload.

    Two scenarios are covered:
    1. Legitimate TF-IDF→TF-IDF reload with sidecar: NO warning expected.
    2. Genuine mismatch (class differs or stored dim deliberately corrupted): warning
       MUST still fire to verify that the fix does not suppress real alerts.
    """

    def _make_corpus_chunks(self) -> list[SCPIChunk]:
        return [
            SCPIChunk(cmd=":SENS:VOLT:RANG", description="Set the voltage measurement range", page=1, section_path="3 > Sense"),
            SCPIChunk(cmd=":SENS:CURR:RANG", description="Set the current measurement range", page=2, section_path="3 > Sense"),
            SCPIChunk(cmd=":SOUR:VOLT", description="Set source voltage output level", page=3, section_path="4 > Source"),
            SCPIChunk(cmd=":SOUR:CURR", description="Set source current output level", page=4, section_path="4 > Source"),
            SCPIChunk(cmd=":FREQ:CENT", description="Set center frequency for sweep", page=5, section_path="5 > Frequency"),
            SCPIChunk(cmd=":TRIG:SOUR", description="Select trigger source", page=6, section_path="6 > Trigger"),
            SCPIChunk(cmd=":DISP:UPD", description="Update display refresh", page=7, section_path="7 > Display"),
            SCPIChunk(cmd=":MEAS:POW?", description="Query measured power level", page=8, section_path="8 > Measure"),
        ]

    @staticmethod
    def _capture_rag_warnings() -> tuple[list[str], logging.Handler]:
        """Return (captured_list, handler) — caller must remove handler when done."""
        rag_logger = logging.getLogger("maglab.instrument.manual_rag")
        captured: list[str] = []

        class _CapHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if record.levelno >= logging.WARNING:
                    captured.append(record.getMessage())

        handler = _CapHandler()
        rag_logger.addHandler(handler)
        return captured, handler

    @staticmethod
    def _remove_handler(handler: logging.Handler) -> None:
        logging.getLogger("maglab.instrument.manual_rag").removeHandler(handler)

    @staticmethod
    def _make_index_with_fallback(
        index_dir: Path,
        model_key: str,
        fb: _TFIDFFallback,
    ) -> SCPIIndex:
        """Build an SCPIIndex backed by a _TFIDFFallback, following the same
        _NoEncodeFallback wrapper pattern used in TestR6Finding2."""
        from unittest.mock import patch as _patch

        class _NoEncodeFallback:
            def __init__(self, inner: _TFIDFFallback) -> None:
                self._inner = inner

            @property
            def _vocab(self) -> dict[str, int]:
                return self._inner._vocab

            @_vocab.setter
            def _vocab(self, v: dict[str, int]) -> None:
                self._inner._vocab = v

            @property
            def _fitted(self) -> bool:
                return self._inner._fitted

            @_fitted.setter
            def _fitted(self, v: bool) -> None:
                self._inner._fitted = v

            def embed(self, texts: list[str]) -> list[list[float]]:
                return self._inner.embed(texts)

        wrapper = _NoEncodeFallback(fb)
        embedder = SCPIEmbedder()
        embedder._load_model = lambda: wrapper  # type: ignore[method-assign]

        def _embed_method(self_e: SCPIEmbedder, texts: list[str]) -> list[list[float]]:
            return self_e._load_model().embed(texts)

        with _patch.object(SCPIEmbedder, "embed", _embed_method):
            index = SCPIIndex(index_dir, model_key, embedder=embedder)
        return index

    def test_legitimate_tfidf_reload_no_spurious_warning(self) -> None:
        """A TF-IDF build→load with vocab sidecar must NOT emit a dimension-mismatch warning.

        Regression for R8-F1: before the fix the probe ran on an unfitted fallback
        (dim=1) and falsely warned "index has N-dim vectors but current produces 1-dim".
        After the fix the sidecar is restored first so the probe returns dim=N.
        """
        from unittest.mock import patch as _patch

        chunks = self._make_corpus_chunks()

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            def _embed_method(self_e: SCPIEmbedder, texts: list[str]) -> list[list[float]]:
                return self_e._load_model().embed(texts)

            # Session A — build with TF-IDF fallback
            fb_a = _TFIDFFallback()
            index_a = self._make_index_with_fallback(index_dir, "model", fb_a)
            with _patch.object(SCPIEmbedder, "embed", _embed_method):
                index_a.build(chunks)

            # Verify sidecar was written
            vocab_path = index_dir / "model.vocab.json"
            assert vocab_path.is_file(), "Sidecar must exist for this test to be meaningful"

            # Session B — fresh TF-IDF fallback, load
            fb_b = _TFIDFFallback()
            index_b = self._make_index_with_fallback(index_dir, "model", fb_b)

            captured, handler = self._capture_rag_warnings()
            try:
                with _patch.object(SCPIEmbedder, "embed", _embed_method):
                    index_b.load()
            finally:
                self._remove_handler(handler)

            dim_warnings = [m for m in captured if "dimension mismatch" in m.lower()]
            assert not dim_warnings, (
                "load() emitted a spurious dimension-mismatch warning on a legitimate "
                "TF-IDF→TF-IDF cross-session reload (R8-F1 regression). "
                f"Captured warnings: {captured!r}"
            )

    def test_genuine_class_mismatch_still_warns(self) -> None:
        """A class mismatch (stored class != current class) must STILL emit a warning after
        the R8-F1 fix — the fix must not suppress genuine mismatch alerts."""
        import sqlite3

        chunks = self._make_corpus_chunks()
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            # Build with whatever embedder is available.
            index_a = SCPIIndex(index_dir, "model")
            index_a.build(chunks)

            # Overwrite stored embedder_class to a synthetic name → class mismatch.
            db_path = index_dir / "model.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "UPDATE meta SET value='R8SyntheticClassThatNeverExists' WHERE key='embedder_class'"
                )
                conn.commit()

            index_b = SCPIIndex(index_dir, "model")
            captured, handler = self._capture_rag_warnings()
            try:
                index_b.load()
            finally:
                self._remove_handler(handler)

            mismatch_warnings = [m for m in captured if "mismatch" in m.lower()]
            assert mismatch_warnings, (
                "load() did NOT warn on a genuine class mismatch after the R8-F1 fix. "
                "The fix must suppress only the spurious TF-IDF probe warning, not real alerts. "
                f"Captured warnings: {captured!r}"
            )

    def test_genuine_dim_mismatch_no_sidecar_still_warns(self) -> None:
        """A dimension mismatch with no vocab sidecar must STILL emit a warning.

        Without a sidecar the probe is the only check — it must fire when stored_dim
        differs from the probed dim.
        """
        import sqlite3

        chunks = self._make_corpus_chunks()
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "idx"

            index_a = SCPIIndex(index_dir, "model")
            index_a.build(chunks)

            # Remove sidecar (if present) and set an impossible stored dim.
            vocab_path = index_dir / "model.vocab.json"
            if vocab_path.is_file():
                vocab_path.unlink()

            db_path = index_dir / "model.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE meta SET value='9999' WHERE key='vec_dim'")
                conn.commit()

            index_b = SCPIIndex(index_dir, "model")
            captured, handler = self._capture_rag_warnings()
            try:
                index_b.load()
            finally:
                self._remove_handler(handler)

            mismatch_warnings = [m for m in captured if "mismatch" in m.lower()]
            assert mismatch_warnings, (
                "load() did NOT warn on a genuine dimension mismatch (no sidecar, impossible "
                "stored_dim=9999) after the R8-F1 fix. "
                f"Captured warnings: {captured!r}"
            )
