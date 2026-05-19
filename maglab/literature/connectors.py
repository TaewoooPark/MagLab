"""Academic data backbone — OpenAlex·Semantic Scholar·arXiv·CrossRef unified connector (§14.1).

Wraps four sources under a common ``LiteratureRecord`` schema.
Shares an exponential backoff and SQLite cache layer.

The MCP connector (§14.7) falls back to this module when unavailable.
Network dependencies: pyalex·semanticscholar·arxiv·habanero (``[literature]`` extra).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

import platformdirs
from pydantic import BaseModel, Field

# HTTP status codes that should be retried (rate-limit and server errors).
_RETRIABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

log = logging.getLogger(__name__)

_APP = "maglab"


# ---------------------------------------------------------------------------
# Common record schema
# ---------------------------------------------------------------------------


class LiteratureRecord(BaseModel):
    """Common return schema for all four sources.

    All fields return empty string/None when unknown — no speculation (§3.3).
    """

    doi: str = ""
    """DOI (normalized: lowercase, leading 'https://doi.org/' or 'http://doi.org/' removed)."""
    title: str = ""
    """Paper title."""
    authors: list[str] = Field(default_factory=list)
    """Author name list (last, first format)."""
    year: int | None = None
    """Publication year."""
    venue: str = ""
    """Journal or conference name."""
    abstract: str = ""
    """Abstract."""
    pdf_url: str = ""
    """Direct PDF URL (if available)."""
    openalex_id: str = ""
    """OpenAlex Work ID (e.g. W2741809807)."""
    s2_id: str = ""
    """Semantic Scholar Paper ID."""
    oa_status: str = ""
    """Open Access status (gold/green/bronze/closed/unknown)."""
    retraction_status: str = "unknown"
    """Retraction status (retracted/corrected/unknown/ok)."""
    source: str = ""
    """Record source (openalex/semantic_scholar/arxiv/crossref)."""
    citation_count: int | None = None
    """Citation count."""
    fields_of_study: list[str] = Field(default_factory=list)
    """Research field tags."""

    def normalized_doi(self) -> str:
        """Return the DOI in lowercase with prefix stripped."""
        d = self.doi.lower().strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if d.startswith(prefix):
                d = d[len(prefix) :]
        return d

    def dedup_key(self) -> str:
        """Deduplication key — DOI preferred, falls back to normalized title."""
        doi = self.normalized_doi()
        if doi:
            return f"doi:{doi}"
        # Normalize title: lowercase, collapse whitespace
        t = " ".join(self.title.lower().split())
        return f"title:{t}"


# ---------------------------------------------------------------------------
# Cache layer (SQLite)
# ---------------------------------------------------------------------------


def _cache_db_path() -> Path:
    """Cache DB path."""
    d = Path(platformdirs.user_cache_dir(_APP)) / "literature"
    d.mkdir(parents=True, exist_ok=True)
    return d / "cache.db"


def _get_cache_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_cache_db_path(), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS literature_cache (
            key       TEXT PRIMARY KEY,
            payload   TEXT NOT NULL,
            cached_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _cache_get(key: str, ttl_s: float = 86400.0) -> Any:
    """Retrieve a record from cache. Returns None if missing or TTL is exceeded.

    Expired rows are deleted on access so the cache table does not grow
    without bound (fix for F-08: stale row accumulation).
    """
    try:
        conn = _get_cache_conn()
        try:
            row = conn.execute(
                "SELECT payload, cached_at FROM literature_cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            payload, cached_at = row
            if time.time() - cached_at > ttl_s:
                # Delete the expired entry so stale rows do not accumulate.
                conn.execute("DELETE FROM literature_cache WHERE key = ?", (key,))
                conn.commit()
                return None
            return json.loads(payload)  # type: ignore[no-any-return]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        log.debug("Cache read error (key=%s): %s", key, exc)
        return None


def _cache_put(key: str, data: Any) -> None:
    """Write a record to cache."""
    try:
        conn = _get_cache_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO literature_cache (key, payload, cached_at) VALUES (?,?,?)",
                (key, json.dumps(data), time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        log.debug("Cache write error (key=%s): %s", key, exc)


def _make_cache_key(*parts: str) -> str:
    """Generate a cache key."""
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Retriable-error classifier
# ---------------------------------------------------------------------------


def _is_retriable(exc: BaseException) -> bool:
    """Return True when *exc* represents a transient error worth retrying.

    Inspects:
    * ``requests.exceptions.HTTPError`` / ``httpx.HTTPStatusError`` — checks
      the response status code against ``_RETRIABLE_STATUS_CODES``.
    * ``requests.exceptions.ConnectionError``, ``TimeoutError``,
      ``ConnectionResetError``, ``BrokenPipeError`` — always retriable.
    * Any exception whose string representation starts with "429" or "5xx"
      pattern (covers library-specific wrappers without a standard status attr).
    """
    # --- standard requests/httpx HTTP errors with a status code attribute ---
    status: int | None = None
    # requests.exceptions.HTTPError
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
    # httpx.HTTPStatusError
    if status is None:
        status = getattr(exc, "status_code", None)

    if status is not None:
        return int(status) in _RETRIABLE_STATUS_CODES

    # --- network-level transient errors ---
    _retriable_types = (
        TimeoutError,
        ConnectionError,       # broad: includes ConnectionResetError etc.
        BrokenPipeError,
        OSError,               # catches socket-level timeouts
    )
    if isinstance(exc, _retriable_types):
        return True

    # --- heuristic: exception message starts with 429/5xx status string ---
    msg = str(exc)
    for code in ("429", "500", "502", "503", "504"):
        if msg.startswith(code) or f" {code} " in msg or f":{code}" in msg:
            return True

    return False


# ---------------------------------------------------------------------------
# Exponential backoff decorator
# ---------------------------------------------------------------------------


def _with_backoff(max_retries: int = 3, base_delay: float = 1.0) -> Callable:
    """Exponential backoff retry decorator."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exc: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < max_retries - 1:
                        log.debug(
                            "%s failed (attempt %d/%d), waiting %.1fs: %s",
                            fn.__name__,
                            attempt + 1,
                            max_retries,
                            delay,
                            exc,
                        )
                        time.sleep(delay)
                        delay *= 2
            raise RuntimeError(
                f"{fn.__name__} failed after {max_retries} retries: {last_exc}"
            ) from last_exc

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# OpenAlex abstract reconstruction helper
# ---------------------------------------------------------------------------


def _reconstruct_abstract(inv: dict[str, Any]) -> str:
    """Reconstruct an abstract string from an OpenAlex inverted-index dict.

    OpenAlex stores abstracts as ``{word: [pos1, pos2, ...]}``.  This helper
    reverses the mapping: collect ``(position, word)`` pairs, sort by position,
    then join with spaces.

    Parameters
    ----------
    inv:
        Inverted-index dict from ``abstract_inverted_index`` field.  Pass ``{}``
        when the field is absent; the function returns ``""`` safely.

    Returns
    -------
    str
        Reconstructed plain-text abstract.  Empty string when ``inv`` is empty.
    """
    if not inv:
        return ""
    pos_word = sorted(
        (pos, word)
        for word, positions in inv.items()
        for pos in positions
    )
    return " ".join(word for _, word in pos_word)


# ---------------------------------------------------------------------------
# OpenAlex connector
# ---------------------------------------------------------------------------


class OpenAlexConnector:
    """OpenAlex REST API wrapper (`pyalex`).

    No API key required since 2026-02 — email header recommended for polite pool.
    """

    def __init__(self, email: str = "") -> None:
        self._email = email
        try:
            import pyalex

            if email:
                pyalex.config.email = email
            self._pyalex = pyalex
        except ImportError as exc:
            raise ImportError("pyalex not installed — pip install 'maglab[literature]'") from exc

    @_with_backoff()
    def fetch_by_doi(self, doi: str) -> LiteratureRecord | None:
        """Fetch a single record by DOI."""
        key = _make_cache_key("oa_doi", doi)
        cached = _cache_get(key)
        if cached:
            return LiteratureRecord(**cached)
        try:
            work = self._pyalex.Works()[f"https://doi.org/{doi}"]
            if work is None:
                return None
            rec = self._work_to_record(work)
            _cache_put(key, rec.model_dump())
            return rec
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("OpenAlex DOI lookup failed (doi=%s): %s", doi, exc)
            return None

    @_with_backoff()
    def search(self, query: str, max_results: int = 20) -> list[LiteratureRecord]:
        """Keyword search — sorted by citation count descending."""
        key = _make_cache_key("oa_search", query, str(max_results))
        cached = _cache_get(key)
        if cached and isinstance(cached, list):
            return [LiteratureRecord(**r) for r in cached]
        try:
            works = (
                self._pyalex.Works()
                .search(query)
                .sort("cited_by_count", descending=True)
                .get(per_page=max_results)
            )
            records = [self._work_to_record(w) for w in (works or [])]
            _cache_put(key, [r.model_dump() for r in records])
            return records
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("OpenAlex search failed (query=%s): %s", query, exc)
            return []

    @_with_backoff()
    def fetch_top_authors_by_topic(
        self, topic_id: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """Retrieve top author list by topic ID."""
        key = _make_cache_key("oa_authors_topic", topic_id, str(max_results))
        cached = _cache_get(key)
        if cached and isinstance(cached, list):
            return cached
        try:
            authors = (
                self._pyalex.Authors()
                .filter(topics={"id": topic_id})
                .sort("cited_by_count", descending=True)
                .get(per_page=max_results)
            )
            result = list(authors or [])
            _cache_put(key, result)
            return result
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("OpenAlex author lookup failed (topic=%s): %s", topic_id, exc)
            return []

    @_with_backoff()
    def get_venue_metrics(self, venue_id: str) -> dict[str, Any]:
        """Retrieve journal metrics (2yr_mean_citedness)."""
        key = _make_cache_key("oa_venue", venue_id)
        cached = _cache_get(key)
        if cached:
            return cached
        try:
            source = self._pyalex.Sources()[venue_id]
            result = {
                "id": venue_id,
                "display_name": source.get("display_name", ""),
                "2yr_mean_citedness": source.get("summary_stats", {}).get("2yr_mean_citedness"),
                "h_index": source.get("summary_stats", {}).get("h_index"),
                "i10_index": source.get("summary_stats", {}).get("i10_index"),
                "works_count": source.get("works_count"),
            }
            _cache_put(key, result)
            return result
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("OpenAlex journal lookup failed (id=%s): %s", venue_id, exc)
            return {}

    @staticmethod
    def _work_to_record(work: dict[str, Any]) -> LiteratureRecord:
        """Convert an OpenAlex Work dict to a LiteratureRecord."""
        doi_raw = work.get("doi") or ""
        doi = doi_raw.replace("https://doi.org/", "").replace("http://doi.org/", "").lower()

        authors = []
        for auth in work.get("authorships", []):
            author = auth.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)

        venue = ""
        loc = work.get("primary_location") or {}
        src = loc.get("source") or {}
        if src:
            venue = src.get("display_name", "")

        pdf_url = ""
        if loc.get("is_oa") and loc.get("pdf_url"):
            pdf_url = loc.get("pdf_url", "")

        oa_val = work.get("open_access", {}).get("oa_status", "unknown")

        retraction = "ok"
        if work.get("is_retracted"):
            retraction = "retracted"

        return LiteratureRecord(
            doi=doi,
            title=work.get("title") or "",
            authors=authors,
            year=work.get("publication_year"),
            venue=venue,
            abstract=_reconstruct_abstract(work.get("abstract_inverted_index") or {}),
            pdf_url=pdf_url,
            openalex_id=work.get("id", "").replace("https://openalex.org/", ""),
            oa_status=oa_val,
            retraction_status=retraction,
            source="openalex",
            citation_count=work.get("cited_by_count"),
            fields_of_study=[c.get("display_name", "") for c in work.get("concepts", [])[:5]],
        )


# ---------------------------------------------------------------------------
# Semantic Scholar connector
# ---------------------------------------------------------------------------


class SemanticScholarConnector:
    """Semantic Scholar API wrapper (`semanticscholar`)."""

    _FIELDS = [
        "paperId",
        "externalIds",
        "title",
        "abstract",
        "year",
        "authors",
        "venue",
        "openAccessPdf",
        "citationCount",
        "fieldsOfStudy",
    ]

    def __init__(self) -> None:
        try:
            from semanticscholar import SemanticScholar

            self._api = SemanticScholar()
        except ImportError as exc:
            raise ImportError(
                "semanticscholar not installed — pip install 'maglab[literature]'"
            ) from exc

    @_with_backoff()
    def fetch_by_doi(self, doi: str) -> LiteratureRecord | None:
        """Fetch a single record by DOI."""
        key = _make_cache_key("s2_doi", doi)
        cached = _cache_get(key)
        if cached:
            return LiteratureRecord(**cached)
        try:
            paper = self._api.get_paper(f"DOI:{doi}", fields=self._FIELDS)
            if paper is None:
                return None
            rec = self._paper_to_record(paper)
            _cache_put(key, rec.model_dump())
            return rec
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("S2 DOI lookup failed (doi=%s): %s", doi, exc)
            return None

    @_with_backoff()
    def search(self, query: str, max_results: int = 20) -> list[LiteratureRecord]:
        """Keyword search."""
        key = _make_cache_key("s2_search", query, str(max_results))
        cached = _cache_get(key)
        if cached and isinstance(cached, list):
            return [LiteratureRecord(**r) for r in cached]
        try:
            results = self._api.search_paper(query, limit=max_results, fields=self._FIELDS)
            records = [self._paper_to_record(p) for p in (results or [])]
            _cache_put(key, [r.model_dump() for r in records])
            return records
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("S2 search failed (query=%s): %s", query, exc)
            return []

    @_with_backoff()
    def fetch_author_papers(self, author_id: str, max_results: int = 20) -> list[LiteratureRecord]:
        """Retrieve a paper list by author ID."""
        key = _make_cache_key("s2_author_papers", author_id, str(max_results))
        cached = _cache_get(key)
        if cached and isinstance(cached, list):
            return [LiteratureRecord(**r) for r in cached]
        try:
            author = self._api.get_author(author_id)
            papers = getattr(author, "papers", []) or []
            records = []
            for p in papers[:max_results]:
                try:
                    detail = self._api.get_paper(p["paperId"], fields=self._FIELDS)
                    if detail:
                        records.append(self._paper_to_record(detail))
                except Exception as inner_exc:  # noqa: BLE001
                    if _is_retriable(inner_exc):
                        raise
            _cache_put(key, [r.model_dump() for r in records])
            return records
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("S2 author paper lookup failed (author=%s): %s", author_id, exc)
            return []

    @staticmethod
    def _paper_to_record(paper: Any) -> LiteratureRecord:
        """Convert an S2 Paper object to a LiteratureRecord."""
        doi = ""
        ext_ids = getattr(paper, "externalIds", {}) or {}
        if ext_ids.get("DOI"):
            doi = str(ext_ids["DOI"]).lower()

        authors = []
        for a in getattr(paper, "authors", []) or []:
            name = getattr(a, "name", "") or ""
            if name:
                authors.append(name)

        pdf_url = ""
        oa_pdf = getattr(paper, "openAccessPdf", None)
        if oa_pdf and isinstance(oa_pdf, dict):
            pdf_url = oa_pdf.get("url", "")

        return LiteratureRecord(
            doi=doi,
            title=getattr(paper, "title", "") or "",
            authors=authors,
            year=getattr(paper, "year", None),
            venue=getattr(paper, "venue", "") or "",
            abstract=getattr(paper, "abstract", "") or "",
            pdf_url=pdf_url,
            s2_id=getattr(paper, "paperId", "") or "",
            oa_status="open" if pdf_url else "unknown",
            source="semantic_scholar",
            citation_count=getattr(paper, "citationCount", None),
            fields_of_study=getattr(paper, "fieldsOfStudy", []) or [],
        )


# ---------------------------------------------------------------------------
# arXiv connector
# ---------------------------------------------------------------------------


class ArXivConnector:
    """arXiv API wrapper (`arxiv`)."""

    def __init__(self) -> None:
        try:
            import arxiv

            self._arxiv = arxiv
        except ImportError as exc:
            raise ImportError(
                "arxiv not installed — pip install 'maglab[literature]'"
            ) from exc

    @_with_backoff()
    def search(
        self,
        query: str,
        max_results: int = 20,
        categories: list[str] | None = None,
    ) -> list[LiteratureRecord]:
        """arXiv search.

        Parameters
        ----------
        query:
            Search query string.
        max_results:
            Maximum number of results.
        categories:
            arXiv category filter (e.g. ['cond-mat.mes-hall']).
        """
        cat_str = " OR ".join(f"cat:{c}" for c in (categories or []))
        full_query = f"({query}) AND ({cat_str})" if cat_str else query

        key = _make_cache_key("arxiv_search", full_query, str(max_results))
        cached = _cache_get(key)
        if cached and isinstance(cached, list):
            return [LiteratureRecord(**r) for r in cached]

        try:
            client = self._arxiv.Client()
            search = self._arxiv.Search(
                query=full_query,
                max_results=max_results,
                sort_by=self._arxiv.SortCriterion.Relevance,
            )
            records = []
            for result in client.results(search):
                records.append(self._result_to_record(result))
            _cache_put(key, [r.model_dump() for r in records])
            return records
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("arXiv search failed (query=%s): %s", query, exc)
            return []

    @_with_backoff()
    def fetch_by_arxiv_id(self, arxiv_id: str) -> LiteratureRecord | None:
        """Fetch a single record by arXiv ID."""
        key = _make_cache_key("arxiv_id", arxiv_id)
        cached = _cache_get(key)
        if cached:
            return LiteratureRecord(**cached)
        try:
            client = self._arxiv.Client()
            search = self._arxiv.Search(id_list=[arxiv_id])
            results = list(client.results(search))
            if not results:
                return None
            rec = self._result_to_record(results[0])
            _cache_put(key, rec.model_dump())
            return rec
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("arXiv ID lookup failed (id=%s): %s", arxiv_id, exc)
            return None

    @staticmethod
    def _result_to_record(result: Any) -> LiteratureRecord:
        """Convert an arXiv Result object to a LiteratureRecord."""
        doi = ""
        if result.doi:
            doi = (
                str(result.doi)
                .lower()
                .replace("https://doi.org/", "")
                .replace("http://doi.org/", "")
            )

        authors = [str(a) for a in (result.authors or [])]

        pdf_url = ""
        for link in result.links or []:
            if hasattr(link, "content_type") and "pdf" in str(link.content_type).lower():
                pdf_url = str(link.href)
                break
        if not pdf_url:
            pdf_url = str(result.pdf_url) if result.pdf_url else ""

        year = result.published.year if result.published else None

        return LiteratureRecord(
            doi=doi,
            title=result.title or "",
            authors=authors,
            year=year,
            venue=result.journal_ref or "arXiv",
            abstract=result.summary or "",
            pdf_url=pdf_url,
            oa_status="green",
            retraction_status="unknown",
            source="arxiv",
            fields_of_study=[str(c) for c in (result.categories or [])],
        )


# ---------------------------------------------------------------------------
# CrossRef connector
# ---------------------------------------------------------------------------


class CrossRefConnector:
    """CrossRef API wrapper (`habanero`) — for DOI metadata validation."""

    def __init__(self) -> None:
        try:
            from habanero import Crossref

            self._cr = Crossref()
        except ImportError as exc:
            raise ImportError(
                "habanero not installed — pip install 'maglab[literature]'"
            ) from exc

    @_with_backoff()
    def fetch_by_doi(self, doi: str) -> LiteratureRecord | None:
        """Fetch CrossRef metadata by DOI."""
        key = _make_cache_key("cr_doi", doi)
        cached = _cache_get(key)
        if cached:
            return LiteratureRecord(**cached)
        try:
            result = self._cr.works(ids=doi)
            if not result or result.get("status") != "ok":
                return None
            item = result.get("message", {})
            rec = self._item_to_record(item)
            _cache_put(key, rec.model_dump())
            return rec
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            log.warning("CrossRef DOI lookup failed (doi=%s): %s", doi, exc)
            return None

    @_with_backoff()
    def validate_doi(self, doi: str) -> bool:
        """Check whether a DOI is registered in CrossRef."""
        return self.fetch_by_doi(doi) is not None

    @staticmethod
    def _item_to_record(item: dict[str, Any]) -> LiteratureRecord:
        """Convert a CrossRef message item to a LiteratureRecord."""
        doi = (item.get("DOI") or "").lower()

        authors = []
        for a in item.get("author", []):
            family = a.get("family", "")
            given = a.get("given", "")
            name = f"{family}, {given}".strip(", ")
            if name:
                authors.append(name)

        title_list = item.get("title", [])
        title = title_list[0] if title_list else ""

        venue_list = item.get("container-title", [])
        venue = venue_list[0] if venue_list else ""

        year = None
        dp = item.get("published-print") or item.get("published-online") or {}
        dp_parts = dp.get("date-parts", [[]])
        if dp_parts and dp_parts[0]:
            year = dp_parts[0][0]

        return LiteratureRecord(
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            source="crossref",
        )


# ---------------------------------------------------------------------------
# Unified multi-source lookup
# ---------------------------------------------------------------------------


def fetch_by_doi_multi(
    doi: str,
    *,
    use_openalex: bool = True,
    use_s2: bool = True,
    use_crossref: bool = True,
    email: str = "",
) -> LiteratureRecord | None:
    """Query multiple sources in order by DOI and return the first successful result.

    Priority: OpenAlex → Semantic Scholar → CrossRef.
    """
    import contextlib  # noqa: PLC0415

    connectors: list[tuple[str, Any]] = []
    if use_openalex:
        with contextlib.suppress(ImportError):
            connectors.append(("openalex", OpenAlexConnector(email=email)))
    if use_s2:
        with contextlib.suppress(ImportError):
            connectors.append(("s2", SemanticScholarConnector()))
    if use_crossref:
        with contextlib.suppress(ImportError):
            connectors.append(("crossref", CrossRefConnector()))

    for name, connector in connectors:
        try:
            rec = connector.fetch_by_doi(doi)
            if rec is not None:
                log.debug("DOI %s → retrieved from %s source", doi, name)
                return rec
        except Exception as exc:  # noqa: BLE001
            log.debug("%s source failed (doi=%s): %s", name, doi, exc)

    return None
