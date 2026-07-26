"""Electronic lab notebook ELN entry — date-based Markdown·frontmatter·provenance links (§13.5).

Structure:
  - Create and manage date-based Markdown entries inside a `notebook/` directory
  - frontmatter: date·sample·instrument·tags·datapoints
  - grep + literature-style index search
  - Jinja2 templates per measurement type
  - FAIR format export (JSON-LD)
  - Entry point: `maglab lab note "<text>"`
"""

from __future__ import annotations

import contextlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from maglab.core.atomic import atomic_write_text

# ---------------------------------------------------------------------------
# Measurement types
# ---------------------------------------------------------------------------


class MeasurementType(StrEnum):
    """Measurement type — used for template selection."""

    MAGNETOTRANSPORT = "magnetotransport"
    """Magnetotransport measurement (Hall, MR, etc.)."""
    FMR = "fmr"
    """Ferromagnetic resonance."""
    MOKE = "moke"
    """Magneto-optical Kerr effect."""
    VSM = "vsm"
    """Vibrating sample magnetometer."""
    GENERAL = "general"
    """General."""


# ---------------------------------------------------------------------------
# ELN entry data structure
# ---------------------------------------------------------------------------


@dataclass
class ELNEntry:
    """Single ELN entry.

    Attributes
    ----------
    entry_id:
        Unique entry identifier (UUID4, auto-generated).
    date:
        Experiment date.
    title:
        Entry title.
    sample:
        Sample ID or stack notation (e.g. "Ta(5)/CoFeB(1)/MgO(2)").
    instrument:
        Instrument name used.
    measurement_type:
        Measurement type.
    tags:
        Tag list (for search).
    datapoint_ids:
        List of linked DataPoint IDs (provenance links).
    body:
        Markdown body.
    provenance_entity_ids:
        List of linked provenance entity IDs.
    created_at:
        Creation timestamp.
    is_draft:
        True if this is an automatic draft (before human review/confirmation).
    """

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    date: date = field(default_factory=date.today)
    title: str = ""
    sample: str = ""
    instrument: str = ""
    measurement_type: MeasurementType = MeasurementType.GENERAL
    tags: list[str] = field(default_factory=list)
    datapoint_ids: list[str] = field(default_factory=list)
    body: str = ""
    provenance_entity_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    is_draft: bool = False

    def to_markdown(self) -> str:
        """Serialize the entry to YAML frontmatter + Markdown format.

        All string fields (sample, instrument) are serialized as JSON strings
        using ``json.dumps``.  List fields (tags, datapoints,
        provenance_entities) are serialized as JSON arrays.  JSON correctly
        handles embedded double-quotes, backslashes, commas, brackets, and
        unicode, giving a permanently correct round-trip regardless of value
        content.
        """
        frontmatter = (
            "---\n"
            f"entry_id: {self.entry_id}\n"
            f"date: {self.date.isoformat()}\n"
            f"sample: {json.dumps(self.sample)}\n"
            f"instrument: {json.dumps(self.instrument)}\n"
            f"measurement_type: {self.measurement_type.value}\n"
            f"tags: {json.dumps(self.tags)}\n"
            f"datapoints: {json.dumps(self.datapoint_ids)}\n"
            f"provenance_entities: {json.dumps(self.provenance_entity_ids)}\n"
            f"is_draft: {str(self.is_draft).lower()}\n"
            f"created_at: {self.created_at.isoformat()}\n"
            "---\n\n"
        )
        title_line = f"# {self.title}\n\n" if self.title else ""
        return frontmatter + title_line + self.body

    @classmethod
    def from_markdown(cls, text: str) -> ELNEntry:
        """Parse an ELNEntry from Markdown text.

        Retains default values on frontmatter parse failure.
        """
        entry = cls()
        fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            body_start = fm_match.end()

            def _extract(key: str) -> str | None:
                m = re.search(rf"^{re.escape(key)}:\s*(.+)$", fm_text, re.MULTILINE)
                return m.group(1).strip() if m else None

            if v := _extract("entry_id"):
                entry.entry_id = v
            if v := _extract("date"):
                with contextlib.suppress(ValueError):
                    entry.date = date.fromisoformat(v)
            if v := _extract("sample"):
                try:
                    entry.sample = json.loads(v)
                except (json.JSONDecodeError, ValueError):
                    entry.sample = v.strip('"')
            if v := _extract("instrument"):
                try:
                    entry.instrument = json.loads(v)
                except (json.JSONDecodeError, ValueError):
                    entry.instrument = v.strip('"')
            if v := _extract("measurement_type"):
                with contextlib.suppress(ValueError):
                    entry.measurement_type = MeasurementType(v)
            if v := _extract("is_draft"):
                entry.is_draft = v.lower() == "true"
            if v := _extract("created_at"):
                with contextlib.suppress(ValueError):
                    entry.created_at = datetime.fromisoformat(v)

            # tags, datapoints, provenance_entities
            # to_markdown() writes these fields as JSON arrays (json.dumps).
            # Parse them back with json.loads, which correctly round-trips
            # double-quotes, backslashes, commas, brackets, and unicode.
            # On any parse failure, fall back gracefully to an empty list.
            for attr, key in [
                ("tags", "tags"),
                ("datapoint_ids", "datapoints"),
                ("provenance_entity_ids", "provenance_entities"),
            ]:
                m = re.search(rf"^{key}:\s*(\[.*\])\s*$", fm_text, re.MULTILINE)
                if m:
                    raw = m.group(1)
                    try:
                        items = json.loads(raw)
                        if isinstance(items, list):
                            setattr(entry, attr, [str(x) for x in items])
                    except (json.JSONDecodeError, ValueError):
                        setattr(entry, attr, [])

            # Split title and body (parse # title after frontmatter end \n\n)
            body_text = text[body_start:].lstrip("\n")
            title_m = re.match(r"^#\s+(.+)\n", body_text)
            if title_m:
                entry.title = title_m.group(1).strip()
                entry.body = body_text[title_m.end() :].lstrip("\n")
            else:
                entry.body = body_text

        return entry

    def to_fair_json_ld(self) -> dict[str, Any]:
        """Export to FAIR format JSON-LD (for sharing and archiving)."""
        return {
            "@context": "https://schema.org",
            "@type": "LabNotebook",
            "@id": f"urn:maglab:eln:{self.entry_id}",
            "identifier": self.entry_id,
            "dateCreated": self.date.isoformat(),
            "name": self.title,
            "description": self.body[:500],
            "about": {
                "sample": self.sample,
                "instrument": self.instrument,
                "measurementType": self.measurement_type.value,
            },
            "keywords": self.tags,
            "relatedLink": [f"urn:maglab:datapoint:{dp}" for dp in self.datapoint_ids],
            "provenance": self.provenance_entity_ids,
            "isDraft": self.is_draft,
        }


# ---------------------------------------------------------------------------
# ELN notebook repository
# ---------------------------------------------------------------------------

# Markdown templates per measurement type
_TEMPLATES: dict[MeasurementType, str] = {
    MeasurementType.MAGNETOTRANSPORT: """\
## Measurement Conditions
- Temperature:
- Applied current:
- Field range:
- Geometry:

## Observations

## Result Summary

## Next Steps
""",
    MeasurementType.FMR: """\
## Measurement Conditions
- Frequency range:
- Power:
- Magnetic field:
- Temperature:

## Observations

## Fitting Results
- f_res:
- ΔH:
- Damping α:

## Next Steps
""",
    MeasurementType.MOKE: """\
## Measurement Conditions
- Wavelength:
- Angle of incidence:
- Field range:

## Observations

## Result Summary

## Next Steps
""",
    MeasurementType.VSM: """\
## Measurement Conditions
- Temperature:
- Field range:
- Step size:

## Observations
- Saturation magnetization Ms:
- Coercive field Hc:
- Remanent magnetization Mr:

## Next Steps
""",
    MeasurementType.GENERAL: """\
## Observations

## Result Summary

## Next Steps
""",
}


class ELNNotebook:
    """Electronic lab notebook repository.

    Parameters
    ----------
    notebook_dir:
        Base directory to store entries in.
    """

    def __init__(self, notebook_dir: Path) -> None:
        self._dir = notebook_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Entry creation and saving
    # ------------------------------------------------------------------

    def create_entry(
        self,
        text: str,
        *,
        sample: str = "",
        instrument: str = "",
        measurement_type: MeasurementType = MeasurementType.GENERAL,
        tags: list[str] | None = None,
        datapoint_ids: list[str] | None = None,
        provenance_entity_ids: list[str] | None = None,
        is_draft: bool = False,
    ) -> ELNEntry:
        """Create and save an ELN entry.

        Parameters
        ----------
        text:
            Entry body or free-text note.
        sample:
            Sample ID.
        instrument:
            Instrument used.
        measurement_type:
            Measurement type.
        tags:
            Tag list.
        datapoint_ids:
            List of DataPoint IDs to link.
        provenance_entity_ids:
            List of provenance entity IDs to link.
        is_draft:
            If True, marks as automatic draft.

        Returns
        -------
        ELNEntry
        """
        # Auto-extract title (first line)
        lines = text.strip().splitlines()
        title = lines[0][:80] if lines else "New Entry"
        body = _TEMPLATES.get(measurement_type, "") + "\n" + text

        entry = ELNEntry(
            date=date.today(),
            title=title,
            sample=sample,
            instrument=instrument,
            measurement_type=measurement_type,
            tags=tags or [],
            datapoint_ids=datapoint_ids or [],
            body=body,
            provenance_entity_ids=provenance_entity_ids or [],
            is_draft=is_draft,
        )
        self._save(entry)
        return entry

    def save_entry(self, entry: ELNEntry) -> Path:
        """Save an ELNEntry to disk and return the file path."""
        return self._save(entry)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def list_entries(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        tags: list[str] | None = None,
        sample: str | None = None,
        measurement_type: MeasurementType | None = None,
    ) -> list[ELNEntry]:
        """Return entries matching the given conditions.

        Parameters
        ----------
        date_from:
            Start date (inclusive).
        date_to:
            End date (inclusive).
        tags:
            List of tags to include (OR condition).
        sample:
            Sample ID filter (partial match).
        measurement_type:
            Measurement type filter.

        Returns
        -------
        list[ELNEntry]
        """
        entries = []
        for md_file in sorted(self._dir.rglob("*.md")):
            try:
                entry = ELNEntry.from_markdown(md_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue

            # Date filter
            if date_from and entry.date < date_from:
                continue
            if date_to and entry.date > date_to:
                continue

            # Tag filter (OR)
            if tags and not any(t in entry.tags for t in tags):
                continue

            # Sample filter
            if sample and sample.lower() not in entry.sample.lower():
                continue

            # Measurement type filter
            if measurement_type and entry.measurement_type != measurement_type:
                continue

            entries.append(entry)

        return entries

    def get_entry(self, entry_id: str) -> ELNEntry | None:
        """Return a single entry by entry_id."""
        for md_file in self._dir.rglob("*.md"):
            try:
                entry = ELNEntry.from_markdown(md_file.read_text(encoding="utf-8"))
                if entry.entry_id == entry_id:
                    return entry
            except Exception:  # noqa: BLE001
                continue
        return None

    def grep(self, query: str) -> list[ELNEntry]:
        """Grep search the body, title, and tags for a query string."""
        q_lower = query.lower()
        results = []
        for md_file in sorted(self._dir.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
                if q_lower in text.lower():
                    entry = ELNEntry.from_markdown(text)
                    results.append(entry)
            except Exception:  # noqa: BLE001
                continue
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_path(self, entry: ELNEntry) -> Path:
        """Return the entry file path (date-based folder)."""
        date_dir = self._dir / entry.date.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir / f"{entry.entry_id}.md"

    def _save(self, entry: ELNEntry) -> Path:
        """Save an entry to a Markdown file."""
        path = self._entry_path(entry)
        # Atomic: ELN entries are the primary research record and are parsed
        # back by list/search; a truncated entry is silently skipped.
        atomic_write_text(path, entry.to_markdown())
        return path
