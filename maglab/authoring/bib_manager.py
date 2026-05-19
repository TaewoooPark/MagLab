"""BibTeX management — cite-then-write verified bibliography (§16.4).

Wraps ``bibtexparser`` v2 to enforce the cite-then-write invariant:
    - Only DOI-verified entries may be added.
    - Un-verified DOI additions raise ``UnverifiedCitationError``.
    - ``export_bib`` writes the verified pool to disk.

Research integrity rule (§3.3, §16.4):
    LLM may cite only keys that appear in the verified pool.  The pool is
    built **before** drafting starts (preflight); the drafter receives the
    verified key list and must not invent new keys.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.model import Entry, Field

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class UnverifiedCitationError(Exception):
    """Raised when an unverified DOI/key is added to the bib manager.

    The caller must run DOI verification (§16.4) before adding entries.
    """


# ---------------------------------------------------------------------------
# DOI normalisation
# ---------------------------------------------------------------------------


def _normalise_doi(doi: str) -> str:
    """Strip ``https://doi.org/`` prefix and lower-case."""
    doi = doi.strip()
    doi = re.sub(r"^https?://doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.lower()


def _doi_to_key(doi: str) -> str:
    """Convert a DOI to a safe BibTeX cite-key.

    Replaces ``/``, ``.``, ``-`` with ``_`` and removes other
    non-alphanumeric characters.
    """
    key = re.sub(r"[/.\-]", "_", doi)
    key = re.sub(r"[^A-Za-z0-9_]", "", key)
    return key


# ---------------------------------------------------------------------------
# BibManager
# ---------------------------------------------------------------------------


class BibManager:
    """Verified BibTeX bibliography manager.

    Parameters
    ----------
    bib_path:
        Path to the working ``.bib`` file.  If the file exists it is loaded;
        otherwise a new empty library is created.
    """

    def __init__(self, bib_path: Path | None = None) -> None:
        self._bib_path = bib_path
        self._library = bibtexparser.Library()
        # Track which cite-keys were verified (DOI-checked).
        self._verified_keys: set[str] = set()
        # Track normalised DOIs in the library.
        self._doi_index: dict[str, str] = {}  # normalised_doi -> cite_key

        if bib_path and bib_path.is_file():
            self._load_existing(bib_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_verified(self, doi: str, metadata: dict[str, Any]) -> str:
        """Add a DOI-verified entry to the library.

        The caller is responsible for verifying the DOI (cross-checking with
        CrossRef or Semantic Scholar) before calling this method.  Passing
        ``verified=True`` is the caller's assertion that verification passed.

        Parameters
        ----------
        doi:
            Raw DOI string (``10.xxxx/...`` or ``https://doi.org/...``).
        metadata:
            Flat dict with BibTeX fields — at minimum ``title``, ``author``,
            ``year``.  ``ENTRYTYPE`` defaults to ``"article"``.

        Returns
        -------
        The cite-key assigned to this entry.

        Raises
        ------
        UnverifiedCitationError
            If ``doi`` is empty (caller forgot to verify).
        """
        if not doi or not doi.strip():
            raise UnverifiedCitationError(
                "Cannot add entry without a DOI.  Run DOI verification first."
            )

        norm_doi = _normalise_doi(doi)
        if norm_doi in self._doi_index:
            existing_key = self._doi_index[norm_doi]
            self._verified_keys.add(existing_key)
            return existing_key

        cite_key = metadata.get("cite_key") or _doi_to_key(norm_doi)

        entry_type = metadata.get("ENTRYTYPE", "article")
        fields: list[Field] = [Field("doi", norm_doi)]

        # Map common metadata fields to BibTeX fields.
        # "author" takes priority over "authors" to avoid duplicate author fields
        # when a metadata dict contains both keys (e.g. from some APIs).
        _field_map = {
            "title": "title",
            "year": "year",
            "journal": "journal",
            "volume": "volume",
            "pages": "pages",
            "number": "number",
            "abstract": "abstract",
        }
        for src_key, bib_key in _field_map.items():
            val = metadata.get(src_key)
            if val is not None:
                fields.append(Field(bib_key, str(val)))

        # Handle author/authors with explicit priority: "author" wins over "authors".
        if metadata.get("author") is not None:
            fields.append(Field("author", str(metadata["author"])))
        elif metadata.get("authors") is not None:
            authors_val = metadata["authors"]
            str_val = (
                " and ".join(authors_val)
                if isinstance(authors_val, list)
                else str(authors_val)
            )
            fields.append(Field("author", str_val))

        entry = Entry(entry_type, cite_key, fields)
        self._library.add(entry)
        self._doi_index[norm_doi] = cite_key
        self._verified_keys.add(cite_key)
        return cite_key

    def add_unverified(self, _doi: str, _metadata: dict[str, Any]) -> str:
        """Explicitly blocked — unverified entries must not enter the pool.

        Always raises :exc:`UnverifiedCitationError`.
        """
        raise UnverifiedCitationError(
            "add_unverified is not allowed.  "
            "Run DOI verification with maglab.literature before adding entries."
        )

    def get_verified_keys(self) -> list[str]:
        """Return all cite-keys that have been DOI-verified."""
        return sorted(self._verified_keys)

    def has_key(self, cite_key: str) -> bool:
        """Return True if the cite-key exists in the library."""
        return cite_key in {e.key for e in self._library.entries}

    def has_doi(self, doi: str) -> bool:
        """Return True if the normalised DOI is in the library."""
        return _normalise_doi(doi) in self._doi_index

    def export_bib(self, path: Path) -> None:
        """Write the verified ``.bib`` library to *path*.

        Parameters
        ----------
        path:
            Destination ``.bib`` file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        bib_str = bibtexparser.write_string(self._library)
        path.write_text(bib_str, encoding="utf-8")

    def to_bib_string(self) -> str:
        """Return the ``.bib`` content as a string."""
        return bibtexparser.write_string(self._library)

    def entry_count(self) -> int:
        """Number of entries in the library."""
        return len(self._library.entries)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_existing(self, bib_path: Path) -> None:
        """Load an existing ``.bib`` file and mark all entries as verified."""
        bib_str = bib_path.read_text(encoding="utf-8")
        parsed = bibtexparser.parse_string(bib_str)
        for entry in parsed.entries:
            self._library.add(entry)
            doi_field = entry.fields_dict.get("doi")
            if doi_field:
                norm = _normalise_doi(str(doi_field.value))
                self._doi_index[norm] = entry.key
            self._verified_keys.add(entry.key)
