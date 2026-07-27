"""Authoritative researcher search — OpenAlex·Semantic Scholar cross-enrichment (§14.2).

``find_authoritative_authors(topic) -> list[AuthorProfile]``
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from maglab.literature.connectors import (
    LiteratureRecord,
    OpenAlexConnector,
    SemanticScholarConnector,
    _cache_get,
    _cache_put,
    _is_retriable,
    _make_cache_key,
    _with_backoff,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Author profile schema
# ---------------------------------------------------------------------------


class AuthorProfile(BaseModel):
    """Authoritative researcher profile.

    Each field explicitly states its data source — no speculative generation (§3.3).
    """

    name: str
    """Author display name."""
    affiliation: str = ""
    """Institutional affiliation."""
    h_index: int | None = None
    """h-index (OpenAlex or S2 basis)."""
    h_index_source: str = ""
    """h-index source ('openalex' / 'semantic_scholar')."""
    cited_by_count: int | None = None
    """Cumulative citation count."""
    works_count: int | None = None
    """Total number of works."""
    recent_papers: list[LiteratureRecord] = Field(default_factory=list)
    """Recent papers list (up to 5)."""
    top_topics: list[str] = Field(default_factory=list)
    """Top research topic tags."""
    openalex_id: str = ""
    """OpenAlex Author ID."""
    s2_id: str = ""
    """Semantic Scholar Author ID."""
    orcid: str = ""
    """ORCID (if available)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _oa_author_to_profile(
    author: dict[str, Any],
    recent_papers: list[LiteratureRecord] | None = None,
) -> AuthorProfile:
    """Convert an OpenAlex Author dict to an AuthorProfile."""
    last_inst = author.get("last_known_institutions") or []
    affiliation = ""
    if last_inst:
        affiliation = last_inst[0].get("display_name", "")

    summary = author.get("summary_stats") or {}
    h_index = summary.get("h_index")
    cited = author.get("cited_by_count")
    works = author.get("works_count")

    topics = []
    for t in (author.get("topics") or [])[:5]:
        if isinstance(t, dict) and t.get("display_name"):
            topics.append(t["display_name"])

    oa_id = author.get("id", "").replace("https://openalex.org/", "")

    ids = author.get("ids") or {}
    orcid = ids.get("orcid", "").replace("https://orcid.org/", "")

    return AuthorProfile(
        name=author.get("display_name", ""),
        affiliation=affiliation,
        h_index=h_index,
        h_index_source="openalex" if h_index is not None else "",
        cited_by_count=cited,
        works_count=works,
        recent_papers=recent_papers or [],
        top_topics=topics,
        openalex_id=oa_id,
        orcid=orcid,
    )


def _enrich_with_s2(profile: AuthorProfile) -> AuthorProfile:
    """Enrich a profile with Semantic Scholar data."""
    try:
        s2 = SemanticScholarConnector()
        # Search for this author by name in S2 (brief cross-validation)
        result = s2._api.search_author(profile.name, limit=3)  # type: ignore[attr-defined]
        for candidate in result or []:
            cname = getattr(candidate, "name", "")
            # Match by name similarity (simple prefix check)
            if _name_similar(profile.name, cname):
                s2_id = getattr(candidate, "authorId", "")
                h_s2 = getattr(candidate, "hIndex", None)
                if profile.h_index is None and h_s2 is not None:
                    profile = profile.model_copy(
                        update={"h_index": h_s2, "h_index_source": "semantic_scholar"}
                    )
                if not profile.s2_id and s2_id:
                    profile = profile.model_copy(update={"s2_id": s2_id})
                break
    except Exception as exc:  # noqa: BLE001
        log.debug("S2 author enrichment failed (%s): %s", profile.name, exc)
    return profile


def _name_similar(a: str, b: str) -> bool:
    """Simple comparison to determine whether two author names refer to the same person.

    Returns False immediately when either name is empty so that an empty
    ``profile.name`` cannot match any S2 candidate (fix for F-09).
    """
    a_parts = set(a.lower().split())
    b_parts = set(b.lower().split())
    if not a_parts or not b_parts:
        return False
    return len(a_parts & b_parts) >= min(2, len(a_parts))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@_with_backoff()
def find_authoritative_authors(
    topic: str,
    *,
    max_results: int = 10,
    email: str = "",
    enrich_s2: bool = True,
) -> list[AuthorProfile]:
    """Search for authoritative researchers by topic keyword.

    Parameters
    ----------
    topic:
        Research topic keyword (e.g. "spin Hall effect", "skyrmion dynamics").
    max_results:
        Maximum number of authors to return.
    email:
        Email header for the OpenAlex polite pool.
    enrich_s2:
        If True, cross-enrich results with Semantic Scholar.

    Returns
    -------
    list[AuthorProfile]
        Author profiles sorted by h-index and citation count in descending order.
        Fields without data are None/empty string — no speculative generation.
    """
    cache_key = _make_cache_key("authors_topic", topic, str(max_results), str(enrich_s2))
    cached = _cache_get(cache_key)
    if cached and isinstance(cached, list):
        return [AuthorProfile(**a) for a in cached]

    profiles: list[AuthorProfile] = []

    try:
        _oa = OpenAlexConnector(email=email)  # noqa: F841 (validates import)
        import pyalex  # noqa: PLC0415

        # Topic search: search works and aggregate authors
        # (Using OpenAlex Authors API topic filter directly)
        try:
            authors_raw = (
                pyalex.Authors().search(topic).sort(cited_by_count="desc").get(per_page=max_results)
            )
        except Exception as exc:  # noqa: BLE001
            if _is_retriable(exc):
                raise
            authors_raw = []

        for auth in authors_raw or []:
            try:
                # Fetch 3 most recent papers
                recent: list[LiteratureRecord] = []
                works_url = auth.get("works_api_url", "")
                if works_url:
                    try:
                        recent_works = (
                            pyalex.Works()
                            .filter(author={"id": auth.get("id", "")})
                            .sort(publication_year="desc")
                            .get(per_page=3)
                        )
                        recent = [
                            OpenAlexConnector._work_to_record(w) for w in (recent_works or [])
                        ]
                    except Exception as exc:  # noqa: BLE001
                        if _is_retriable(exc):
                            raise

                profile = _oa_author_to_profile(auth, recent_papers=recent)
                if enrich_s2 and profile.name:
                    profile = _enrich_with_s2(profile)
                profiles.append(profile)
            except Exception as exc:  # noqa: BLE001
                if _is_retriable(exc):
                    raise
                log.debug("Author profile conversion failed: %s", exc)

    except ImportError:
        log.warning("pyalex not installed — authoritative author search unavailable")
    except Exception as exc:  # noqa: BLE001
        if _is_retriable(exc):
            raise
        log.warning("Authoritative author search failed (topic=%s): %s", topic, exc)

    # Sort by h-index and citation count
    profiles.sort(
        key=lambda p: (p.h_index or 0, p.cited_by_count or 0),
        reverse=True,
    )
    profiles = profiles[:max_results]

    _cache_put(cache_key, [p.model_dump() for p in profiles])
    return profiles


def find_authors_by_topic_id(
    topic_id: str,
    *,
    max_results: int = 10,
    email: str = "",
) -> list[AuthorProfile]:
    """Retrieve authoritative authors by OpenAlex topic ID (§14.2 direct filter method).

    Parameters
    ----------
    topic_id:
        OpenAlex topic ID (e.g. 'T10057').
    max_results:
        Maximum number of results to return.
    email:
        Polite pool email.
    """
    cache_key = _make_cache_key("authors_topic_id", topic_id, str(max_results))
    cached = _cache_get(cache_key)
    if cached and isinstance(cached, list):
        return [AuthorProfile(**a) for a in cached]

    profiles: list[AuthorProfile] = []
    try:
        oa = OpenAlexConnector(email=email)
        authors_raw = oa.fetch_top_authors_by_topic(topic_id, max_results=max_results)
        for auth in authors_raw:
            profile = _oa_author_to_profile(auth)
            profiles.append(profile)
    except Exception as exc:  # noqa: BLE001
        log.warning("Topic ID author search failed (id=%s): %s", topic_id, exc)

    profiles.sort(key=lambda p: (p.h_index or 0, p.cited_by_count or 0), reverse=True)
    _cache_put(cache_key, [p.model_dump() for p in profiles])
    return profiles
