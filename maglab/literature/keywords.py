"""Weighted keyword extraction — TF-IDF 40% + KeyBERT 40% + YAKE 20% (§14.3).

Input: text string or list of PDF paths.
Output: ``WeightedKeyword`` list (with score and source labels).

Deterministic pipeline — LLM re-ranking is performed externally (client's choice).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Optional dependencies — placed at module level so mock.patch works
try:
    from keybert import KeyBERT  # noqa: PLC0415
except ImportError:
    KeyBERT: Any = None  # type: ignore[no-redef]  # noqa: N816

try:
    import yake  # noqa: PLC0415
except ImportError:
    yake: Any = None  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


class WeightedKeyword(BaseModel):
    """Weighted keyword result entry.

    Attributes
    ----------
    keyword:
        Extracted keyword/phrase (normalized: lowercase, whitespace collapsed).
    score:
        Combined weighted score [0, 1]. TF-IDF 40% + KeyBERT 40% + YAKE 20%.
    tfidf_score:
        TF-IDF sub-score (normalized).
    keybert_score:
        KeyBERT sub-score (normalized).
    yake_score:
        YAKE sub-score (normalized, lower is better → inverted).
    source_methods:
        List of contributing methods (may repeat).
    """

    keyword: str
    score: float
    tfidf_score: float = 0.0
    keybert_score: float = 0.0
    yake_score: float = 0.0
    source_methods: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract full text from a PDF using pdfplumber.

    Parameters
    ----------
    pdf_path:
        PDF file path.

    Returns
    -------
    Extracted text (empty string on failure).
    """
    try:
        import pdfplumber  # noqa: PLC0415

        with pdfplumber.open(str(pdf_path)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n".join(pages)
    except ImportError:
        log.warning("pdfplumber not installed — PDF extraction unavailable")
        return ""
    except Exception as exc:  # noqa: BLE001
        log.warning("PDF extraction failed (%s): %s", pdf_path, exc)
        return ""


def extract_texts_from_folder(
    folder: Path | str, extensions: tuple[str, ...] = (".pdf", ".txt")
) -> list[tuple[Path, str]]:
    """Extract text from supported files in a folder.

    Returns
    -------
    [(file_path, text), ...] — entries with empty text are excluded.

    Notes
    -----
    Returns ``[]`` when *folder* does not exist or is not a directory,
    consistent with the empty-folder case.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return []
    results: list[tuple[Path, str]] = []
    for f in sorted(folder.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in extensions:
            continue
        if f.suffix.lower() == ".pdf":
            text = extract_text_from_pdf(f)
        else:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                text = ""
        if text.strip():
            results.append((f, text))
    return results


# ---------------------------------------------------------------------------
# TF-IDF keyword extraction
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Normalize text (lowercase, remove non-alphanumeric characters)."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_tfidf_keywords(
    texts: list[str],
    top_n: int = 30,
    ngram_range: tuple[int, int] = (1, 3),
) -> list[tuple[str, float]]:
    """Extract n-gram keywords using TF-IDF.

    Parameters
    ----------
    texts:
        Input text list.
    top_n:
        Maximum number of keywords to return.
    ngram_range:
        n-gram range (min, max).

    Returns
    -------
    [(keyword, score), ...] in descending order.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: PLC0415
    except ImportError:
        log.warning("scikit-learn not installed — TF-IDF extraction unavailable")
        return []

    if not texts:
        return []

    norm_texts = [_normalize_text(t) for t in texts]
    try:
        vec = TfidfVectorizer(
            ngram_range=ngram_range,
            max_features=500,
            stop_words="english",
            min_df=1,
        )
        mat = vec.fit_transform(norm_texts)
        feature_names = vec.get_feature_names_out()
        # Average TF-IDF score across all documents
        scores = mat.mean(axis=0).A1
        ranked = sorted(
            zip(feature_names, scores, strict=False),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(kw, sc) for kw, sc in ranked[:top_n]]
    except Exception as exc:  # noqa: BLE001
        log.warning("TF-IDF extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# KeyBERT keyword extraction
# ---------------------------------------------------------------------------


def extract_keybert_keywords(
    text: str,
    top_n: int = 20,
    ngram_range: tuple[int, int] = (1, 3),
) -> list[tuple[str, float]]:
    """Extract semantic keywords using KeyBERT.

    Parameters
    ----------
    text:
        Input text.
    top_n:
        Maximum number of results.
    ngram_range:
        n-gram range.

    Returns
    -------
    [(keyword, score), ...] in descending order.
    """
    if KeyBERT is None:
        log.warning("keybert not installed — KeyBERT extraction unavailable")
        return []

    # Use SPECTER2 (academic document embedding model) when available; fall back
    # to the KeyBERT default (all-MiniLM-L6-v2) in offline / test environments.
    # P6-TODO: inject domain LLM reranker as a post-processing step here.
    #
    # Pin the embedding model to CPU. KeyBERT's default device auto-selection
    # puts the transformer on MPS on Apple Silicon, where SPECTER2 OOMs mid-
    # inference and dumps raw Metal command-buffer errors to stderr while
    # silently contributing nothing to the scores. CPU is reliable cross-platform
    # and fast enough for keyword-scale text.
    def _cpu_keybert(model_name: str) -> Any:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            return KeyBERT(SentenceTransformer(model_name, device="cpu"))
        except Exception:  # noqa: BLE001 - fall back to KeyBERT's own loader
            return KeyBERT(model_name)

    _specter2_model = "allenai/specter2_base"
    try:
        kw_model = _cpu_keybert(_specter2_model)
        log.debug("KeyBERT initialised with SPECTER2 model (%s) on CPU", _specter2_model)
    except Exception as specter_exc:  # noqa: BLE001
        log.warning(
            "SPECTER2 model unavailable (%s) — falling back to KeyBERT default embedding",
            specter_exc,
        )
        try:
            kw_model = _cpu_keybert("all-MiniLM-L6-v2")
        except Exception as exc:  # noqa: BLE001
            log.warning("KeyBERT initialisation failed: %s", exc)
            return []

    try:
        results = kw_model.extract_keywords(
            text,
            keyphrase_ngram_range=ngram_range,
            stop_words="english",
            top_n=top_n,
            use_mmr=True,
            diversity=0.5,
        )
        return [(kw.lower(), float(sc)) for kw, sc in (results or [])]
    except Exception as exc:  # noqa: BLE001
        log.warning("KeyBERT extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# YAKE keyword extraction
# ---------------------------------------------------------------------------


def extract_yake_keywords(
    text: str,
    top_n: int = 20,
    max_ngram_size: int = 3,
    language: str = "en",
) -> list[tuple[str, float]]:
    """Extract statistically-based keywords using YAKE.

    YAKE scores are lower-is-better — inverted before returning.

    Returns
    -------
    [(keyword, inverted_score), ...] in descending order (higher = more important).
    """
    if yake is None:
        log.warning("yake not installed — YAKE extraction unavailable")
        return []

    try:
        extractor = yake.KeywordExtractor(
            lan=language,
            n=max_ngram_size,
            top=top_n,
        )
        keywords = extractor.extract_keywords(text)
        # Invert YAKE scores: lower original → higher inverted
        max_score = max((sc for _, sc in keywords), default=1.0) + 1e-9
        return [(kw.lower(), 1.0 - sc / max_score) for kw, sc in (keywords or [])]
    except Exception as exc:  # noqa: BLE001
        log.warning("YAKE extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Normalization, deduplication, and weighted fusion
# ---------------------------------------------------------------------------


def _normalize_scores(pairs: list[tuple[str, float]]) -> dict[str, float]:
    """Normalize scores to [0, 1]."""
    if not pairs:
        return {}
    max_sc = max(sc for _, sc in pairs)
    if max_sc <= 0:
        return {kw: 0.0 for kw, _ in pairs}
    return {kw: sc / max_sc for kw, sc in pairs}


def _normalize_keyword(kw: str) -> str:
    """Normalize a keyword (lowercase, collapse whitespace)."""
    return " ".join(kw.lower().split())


WEIGHT_TFIDF = 0.4
WEIGHT_KEYBERT = 0.4
WEIGHT_YAKE = 0.2


def merge_keyword_scores(
    tfidf: list[tuple[str, float]],
    keybert: list[tuple[str, float]],
    yake: list[tuple[str, float]],
    top_n: int = 30,
) -> list[WeightedKeyword]:
    """Fuse scores from three methods with weights and remove duplicates.

    Weights: TF-IDF 40% + KeyBERT 40% + YAKE 20%.
    Duplicate keywords: shorter n-grams contained in a longer one are suppressed (substring suppression).

    Returns
    -------
    WeightedKeyword list (sorted by score descending).
    """
    tfidf_norm = _normalize_scores(tfidf)
    keybert_norm = _normalize_scores(keybert)
    yake_norm = _normalize_scores(yake)

    # Build a unified map keyed by *normalised* keyword so that source strings
    # that differ only in case ("Spin Hall Effect" vs "spin hall effect") are
    # merged into a single entry instead of producing two identical
    # WeightedKeyword objects.
    # For each normalised keyword, accumulate the *maximum* score seen across
    # all source variants (conservative — avoids double-counting).
    norm_to_scores: dict[str, dict[str, float]] = {}

    def _accumulate(src_dict: dict[str, float], label: str) -> None:
        for kw, sc in src_dict.items():
            norm = _normalize_keyword(kw)
            entry = norm_to_scores.setdefault(norm, {"t": 0.0, "k": 0.0, "y": 0.0})
            entry[label] = max(entry[label], sc)

    _accumulate(tfidf_norm, "t")
    _accumulate(keybert_norm, "k")
    _accumulate(yake_norm, "y")

    results: list[WeightedKeyword] = []
    for norm, sc_map in norm_to_scores.items():
        t_sc = sc_map["t"]
        k_sc = sc_map["k"]
        y_sc = sc_map["y"]
        total = WEIGHT_TFIDF * t_sc + WEIGHT_KEYBERT * k_sc + WEIGHT_YAKE * y_sc
        methods: list[str] = []
        if t_sc > 0:
            methods.append("tfidf")
        if k_sc > 0:
            methods.append("keybert")
        if y_sc > 0:
            methods.append("yake")
        results.append(
            WeightedKeyword(
                keyword=norm,
                score=total,
                tfidf_score=t_sc,
                keybert_score=k_sc,
                yake_score=y_sc,
                source_methods=methods,
            )
        )

    # Sort by score
    results.sort(key=lambda w: w.score, reverse=True)

    # Substring suppression: remove shorter keywords that are substrings of longer ones
    final: list[WeightedKeyword] = []
    for candidate in results:
        dominated = any(
            candidate.keyword != kept.keyword and candidate.keyword in kept.keyword
            for kept in final
        )
        if not dominated:
            final.append(candidate)
        if len(final) >= top_n:
            break

    return final


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_keywords_from_texts(
    texts: list[str],
    *,
    top_n: int = 30,
    ngram_range: tuple[int, int] = (1, 3),
    rerank_fn: Callable[[list[WeightedKeyword]], list[WeightedKeyword]] | None = None,
) -> list[WeightedKeyword]:
    """Extract weighted keywords from a list of texts.

    Parameters
    ----------
    texts:
        Input text list.
    top_n:
        Maximum number of keywords to return.
    ngram_range:
        n-gram range.
    rerank_fn:
        Optional domain LLM re-ranking function.  When provided it receives the
        fused keyword list and returns a re-ordered list.
        P6-TODO: inject domain LLM reranker here.

    Returns
    -------
    WeightedKeyword list (sorted by score descending).
    """
    combined_text = " ".join(texts)

    tfidf = extract_tfidf_keywords(texts, top_n=top_n * 2, ngram_range=ngram_range)
    keybert = extract_keybert_keywords(combined_text, top_n=top_n * 2, ngram_range=ngram_range)
    yake_kw = extract_yake_keywords(combined_text, top_n=top_n * 2, max_ngram_size=ngram_range[1])

    merged = merge_keyword_scores(tfidf, keybert, yake_kw, top_n=top_n)

    # Apply optional domain LLM re-ranking after score fusion.
    # P6-TODO: inject domain LLM reranker here.
    if rerank_fn is not None:
        try:
            merged = rerank_fn(merged)
        except Exception as exc:  # noqa: BLE001
            log.warning("rerank_fn failed — using pre-rerank order: %s", exc)

    return merged


def extract_keywords_from_folder(
    folder: Path,
    *,
    top_n: int = 30,
    rerank_fn: Callable[[list[WeightedKeyword]], list[WeightedKeyword]] | None = None,
) -> list[WeightedKeyword]:
    """Extract keywords from PDF and text files in a folder.

    Parameters
    ----------
    folder:
        Paper folder path.
    top_n:
        Maximum number of keywords to return.
    rerank_fn:
        Optional domain LLM re-ranking function passed through to
        ``extract_keywords_from_texts``.
        P6-TODO: inject domain LLM reranker here.

    Returns
    -------
    WeightedKeyword list.
    """
    file_texts = extract_texts_from_folder(folder)
    if not file_texts:
        log.warning("No extractable text found in folder (%s)", folder)
        return []
    texts = [t for _, t in file_texts]
    log.info("Extracting keywords from %d files...", len(texts))
    return extract_keywords_from_texts(texts, top_n=top_n, rerank_fn=rerank_fn)


def top_keyword_strings(keywords: list[WeightedKeyword], n: int = 10) -> list[str]:
    """Return the top n keyword strings from a WeightedKeyword list."""
    return [kw.keyword for kw in keywords[:n]]
