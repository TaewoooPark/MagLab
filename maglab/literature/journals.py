"""Journal impact metrics — SJR·OpenAlex 2yr_mean_citedness·Eigenfactor (§14.4).

Note: use of the term "JCR Impact Factor" is prohibited (§14.4·§21).
All metrics are returned with their source label.

Bundled CSV: ``data/sjr.csv``, ``data/eigenfactor.csv`` (offline fallback).
"""

from __future__ import annotations

import csv
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric schema
# ---------------------------------------------------------------------------

# Forbidden "JCR Impact Factor" label strings — used in output validation
_FORBIDDEN_LABELS = frozenset(
    {
        "JCR Impact Factor",
        "JCR IF",
        "Impact Factor",
        "Thomson Reuters IF",
        "Clarivate IF",
    }
)


class JournalMetrics(BaseModel):
    """Journal impact metrics — three open metrics with explicit source labeling.

    Attributes
    ----------
    journal_name:
        Journal display name.
    sjr:
        SCImago Journal Rank (SJR) score.
    sjr_quartile:
        SJR quartile (Q1/Q2/Q3/Q4).
    sjr_year:
        SJR data year.
    sjr_source:
        SJR source label ("SJR (SCImago)").
    openalex_2yr_mean_citedness:
        OpenAlex 2-year mean citedness (IF-like, real-time).
    openalex_source:
        OpenAlex source label.
    eigenfactor:
        Eigenfactor score.
    eigenfactor_source:
        Eigenfactor source label.
    h_index:
        h-index (OpenAlex basis, if available).
    openalex_id:
        OpenAlex Source ID (if available).
    notes:
        Warnings and supplementary notes.

    **Important**: This class never uses a "JCR Impact Factor" label.
    """

    journal_name: str
    sjr: float | None = None
    sjr_quartile: str = ""
    sjr_year: int | None = None
    sjr_source: str = "SJR (SCImago)"
    openalex_2yr_mean_citedness: float | None = None
    openalex_source: str = "OpenAlex 2yr_mean_citedness"
    eigenfactor: float | None = None
    eigenfactor_source: str = "Eigenfactor"
    h_index: int | None = None
    openalex_id: str = ""
    notes: list[str] = Field(default_factory=list)

    def as_display(self) -> dict[str, Any]:
        """Display dict for UI — includes source labels, no forbidden labels."""
        result: dict[str, Any] = {
            "Journal": self.journal_name,
            self.sjr_source: self.sjr,
            "SJR Quartile": self.sjr_quartile or None,
            self.openalex_source: self.openalex_2yr_mean_citedness,
            self.eigenfactor_source: self.eigenfactor,
            "h-index (OpenAlex)": self.h_index,
        }
        if self.notes:
            result["Notes"] = self.notes
        # Safety check: raise an error if a forbidden label appears in a key
        for key in result:
            for forbidden in _FORBIDDEN_LABELS:
                if forbidden.lower() in key.lower():
                    raise ValueError(
                        f"Forbidden impact-factor label '{key}' attempted (§14.4·§21): "
                        f"use SJR·OpenAlex·Eigenfactor instead."
                    )
        return result

    def validate_no_jcr_label(self) -> None:
        """Check that no JCR IF forbidden label exists in any field."""
        all_strings = [
            self.sjr_source,
            self.openalex_source,
            self.eigenfactor_source,
        ]
        for s in all_strings:
            for forbidden in _FORBIDDEN_LABELS:
                if forbidden.lower() in s.lower():
                    raise ValueError(
                        f"Forbidden label '{forbidden}' detected (§14.4): use SJR·OpenAlex·Eigenfactor"
                    )


# ---------------------------------------------------------------------------
# Bundled CSV loaders
# ---------------------------------------------------------------------------


def _bundle_data_dir() -> Path:
    """Path to the bundled data/ directory."""
    return Path(__file__).parent.parent / "physics" / "data"


@lru_cache(maxsize=1)
def _load_sjr_csv() -> dict[str, dict[str, Any]]:
    """Load the bundled SJR CSV. Returns an empty dict if not found."""
    candidates = [
        _bundle_data_dir() / "sjr.csv",
        Path(__file__).parent / "data" / "sjr.csv",
    ]
    for csv_path in candidates:
        if csv_path.is_file():
            return _parse_sjr_csv(csv_path)
    log.debug("Bundled SJR CSV not found — offline SJR unavailable")
    return {}


def _parse_sjr_csv(path: Path) -> dict[str, dict[str, Any]]:
    """Parse an SJR CSV file.

    Expected columns: Title, SJR, SJR Best Quartile, Year (or similar format).
    """
    result: dict[str, dict[str, Any]] = {}
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                # Normalize column names (trim)
                row = {k.strip(): v.strip() for k, v in row.items() if k}
                title = row.get("Title") or row.get("title") or ""
                if not title:
                    continue
                key = title.lower()
                sjr_val = row.get("SJR") or row.get("sjr") or ""
                quartile = row.get("SJR Best Quartile") or row.get("sjr_quartile") or ""
                year_str = row.get("Year") or row.get("year") or ""
                try:
                    sjr_float = float(sjr_val.replace(",", "."))
                except ValueError:
                    sjr_float = None
                try:
                    year_int = int(year_str)
                except ValueError:
                    year_int = None
                result[key] = {
                    "title": title,
                    "sjr": sjr_float,
                    "quartile": quartile,
                    "year": year_int,
                }
    except Exception as exc:  # noqa: BLE001
        log.warning("SJR CSV parse failed (%s): %s", path, exc)
    return result


@lru_cache(maxsize=1)
def _load_eigenfactor_csv() -> dict[str, float]:
    """Load the bundled Eigenfactor CSV."""
    candidates = [
        _bundle_data_dir() / "eigenfactor.csv",
        Path(__file__).parent / "data" / "eigenfactor.csv",
    ]
    for csv_path in candidates:
        if csv_path.is_file():
            return _parse_eigenfactor_csv(csv_path)
    log.debug("Bundled Eigenfactor CSV not found — offline Eigenfactor unavailable")
    return {}


def _parse_eigenfactor_csv(path: Path) -> dict[str, float]:
    """Parse an Eigenfactor CSV file.

    Expected columns: Journal, Eigenfactor Score (or similar format).
    """
    result: dict[str, float] = {}
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row = {k.strip(): v.strip() for k, v in row.items() if k}
                journal = row.get("Journal") or row.get("journal") or ""
                ef_str = row.get("Eigenfactor Score") or row.get("eigenfactor") or ""
                if not journal or not ef_str:
                    continue
                import contextlib  # noqa: PLC0415

                with contextlib.suppress(ValueError):
                    result[journal.lower()] = float(ef_str.replace(",", "."))
    except Exception as exc:  # noqa: BLE001
        log.warning("Eigenfactor CSV parse failed (%s): %s", path, exc)
    return result


# ---------------------------------------------------------------------------
# Journal matching
# ---------------------------------------------------------------------------


def _match_journal_name(query: str, lookup: dict[str, Any]) -> str | None:
    """Match a journal name against a lookup dict.

    Tries lowercase exact match first, then partial match.
    """
    q = query.lower().strip()
    if q in lookup:
        return q
    for key in lookup:
        if q in key or key in q:
            return key
    return None


# ---------------------------------------------------------------------------
# OpenAlex journal metric lookup
# ---------------------------------------------------------------------------


def _fetch_openalex_venue_metrics(journal_name: str) -> dict[str, Any]:
    """Query 2yr_mean_citedness for a journal from OpenAlex."""
    try:
        import pyalex  # noqa: PLC0415

        sources = pyalex.Sources().search(journal_name).get(per_page=3)
        for src in sources or []:
            sname = src.get("display_name", "").lower()
            if journal_name.lower() in sname or sname in journal_name.lower():
                stats = src.get("summary_stats") or {}
                return {
                    "id": src.get("id", "").replace("https://openalex.org/", ""),
                    "display_name": src.get("display_name", ""),
                    "2yr_mean_citedness": stats.get("2yr_mean_citedness"),
                    "h_index": stats.get("h_index"),
                }
    except ImportError:
        log.debug("pyalex not installed — OpenAlex journal metrics unavailable")
    except Exception as exc:  # noqa: BLE001
        log.debug("OpenAlex journal lookup failed (%s): %s", journal_name, exc)
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_journal_metrics(
    journal_name: str,
    *,
    use_openalex: bool = True,
) -> JournalMetrics:
    """Retrieve journal impact metrics (§14.4).

    Parameters
    ----------
    journal_name:
        Journal name (e.g. "Physical Review Letters", "npj Spintronics").
    use_openalex:
        If True, attempt a real-time OpenAlex lookup.

    Returns
    -------
    JournalMetrics — three metrics (None if unavailable, label always specified).

    Note
    ----
    The "JCR Impact Factor" label is never used (§14.4·§21).
    """
    # SJR bundle lookup
    sjr_db = _load_sjr_csv()
    sjr_key = _match_journal_name(journal_name, sjr_db)
    sjr_val: float | None = None
    sjr_quartile = ""
    sjr_year: int | None = None
    if sjr_key and sjr_db.get(sjr_key):
        entry = sjr_db[sjr_key]
        sjr_val = entry.get("sjr")
        sjr_quartile = entry.get("quartile", "")
        sjr_year = entry.get("year")

    # Eigenfactor bundle lookup
    ef_db = _load_eigenfactor_csv()
    ef_key = _match_journal_name(journal_name, ef_db)
    eigenfactor: float | None = ef_db.get(ef_key) if ef_key else None

    # OpenAlex real-time lookup
    oa_citedness: float | None = None
    oa_h_index: int | None = None
    oa_id = ""
    notes: list[str] = []
    if use_openalex:
        oa_data = _fetch_openalex_venue_metrics(journal_name)
        if oa_data:
            oa_citedness = oa_data.get("2yr_mean_citedness")
            oa_h_index = oa_data.get("h_index")
            oa_id = oa_data.get("id", "")
        else:
            notes.append("No OpenAlex real-time result — using bundled data only")

    if sjr_val is None and eigenfactor is None and oa_citedness is None:
        notes.append(
            f"No metric data found for '{journal_name}' "
            f"— may not be registered in the bundled CSV or OpenAlex"
        )

    metrics = JournalMetrics(
        journal_name=journal_name,
        sjr=sjr_val,
        sjr_quartile=sjr_quartile,
        sjr_year=sjr_year,
        sjr_source="SJR (SCImago)",
        openalex_2yr_mean_citedness=oa_citedness,
        openalex_source="OpenAlex 2yr_mean_citedness",
        eigenfactor=eigenfactor,
        eigenfactor_source="Eigenfactor",
        h_index=oa_h_index,
        openalex_id=oa_id,
        notes=notes,
    )
    # Safety check
    metrics.validate_no_jcr_label()
    return metrics


def list_top_journals_by_sjr(
    field_query: str = "",
    top_n: int = 20,
) -> list[JournalMetrics]:
    """Return top journals from the SJR bundle data.

    Parameters
    ----------
    field_query:
        Journal name filter keyword (empty string returns all).
    top_n:
        Maximum number of results to return.
    """
    sjr_db = _load_sjr_csv()
    entries = list(sjr_db.values())

    if field_query:
        q = field_query.lower()
        entries = [e for e in entries if q in e.get("title", "").lower()]

    # Sort by SJR descending
    entries.sort(key=lambda e: e.get("sjr") or 0.0, reverse=True)

    results: list[JournalMetrics] = []
    for e in entries[:top_n]:
        m = JournalMetrics(
            journal_name=e.get("title", ""),
            sjr=e.get("sjr"),
            sjr_quartile=e.get("quartile", ""),
            sjr_year=e.get("year"),
            sjr_source="SJR (SCImago)",
            openalex_source="OpenAlex 2yr_mean_citedness",
            eigenfactor_source="Eigenfactor",
        )
        m.validate_no_jcr_label()
        results.append(m)
    return results
