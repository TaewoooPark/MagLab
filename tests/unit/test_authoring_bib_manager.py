"""Unit tests for maglab/authoring/bib_manager.py (§16.4)."""

from __future__ import annotations

import pytest

from maglab.authoring.bib_manager import BibManager, UnverifiedCitationError


def _sample_metadata(title: str = "Test Paper") -> dict:
    return {
        "title": title,
        "author": "Smith, John and Doe, Jane",
        "year": "2024",
        "journal": "Physical Review Letters",
        "ENTRYTYPE": "article",
    }


class TestAddVerified:
    """Tests for verified DOI entry addition."""

    def test_add_verified_returns_key(self) -> None:
        """add_verified returns a non-empty cite-key."""
        mgr = BibManager()
        key = mgr.add_verified("10.1103/PhysRevLett.132.106701", _sample_metadata())
        assert isinstance(key, str)
        assert len(key) > 0

    def test_add_verified_idempotent(self) -> None:
        """Adding the same DOI twice returns the same cite-key."""
        mgr = BibManager()
        doi = "10.1103/PhysRevLett.132.106701"
        k1 = mgr.add_verified(doi, _sample_metadata())
        k2 = mgr.add_verified(doi, _sample_metadata())
        assert k1 == k2
        assert mgr.entry_count() == 1

    def test_add_verified_key_in_verified_pool(self) -> None:
        """After adding, the key appears in get_verified_keys()."""
        mgr = BibManager()
        doi = "10.1038/s41563-022-01222-4"
        key = mgr.add_verified(doi, _sample_metadata())
        assert key in mgr.get_verified_keys()

    def test_add_verified_empty_doi_raises(self) -> None:
        """Adding an empty DOI raises UnverifiedCitationError."""
        mgr = BibManager()
        with pytest.raises(UnverifiedCitationError):
            mgr.add_verified("", _sample_metadata())

    def test_add_verified_doi_normalised(self) -> None:
        """https://doi.org/ prefix is stripped and the entry is recognised."""
        mgr = BibManager()
        doi_raw = "https://doi.org/10.1103/PhysRevLett.132.106701"
        doi_clean = "10.1103/PhysRevLett.132.106701"
        k1 = mgr.add_verified(doi_raw, _sample_metadata("Paper A"))
        k2 = mgr.add_verified(doi_clean, _sample_metadata("Paper A dup"))
        assert k1 == k2, "Normalised DOI should deduplicate."

    def test_add_unverified_is_blocked(self) -> None:
        """add_unverified always raises UnverifiedCitationError."""
        mgr = BibManager()
        with pytest.raises(UnverifiedCitationError):
            mgr.add_unverified("10.xxxx/something", _sample_metadata())


class TestExportBib:
    """Tests for .bib export."""

    def test_export_creates_file(self, tmp_path) -> None:
        """export_bib writes a non-empty .bib file."""
        mgr = BibManager()
        mgr.add_verified("10.1103/PhysRevLett.132.106701", _sample_metadata())
        bib_path = tmp_path / "refs.bib"
        mgr.export_bib(bib_path)
        assert bib_path.is_file()
        content = bib_path.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_export_contains_doi(self, tmp_path) -> None:
        """Exported .bib contains the DOI field."""
        mgr = BibManager()
        doi = "10.1103/PhysRevLett.132.106701"
        mgr.add_verified(doi, _sample_metadata())
        bib_path = tmp_path / "refs.bib"
        mgr.export_bib(bib_path)
        content = bib_path.read_text(encoding="utf-8")
        assert "10.1103" in content

    def test_to_bib_string_non_empty(self) -> None:
        """to_bib_string returns a non-empty string."""
        mgr = BibManager()
        mgr.add_verified("10.1038/s41563-022-01222-4", _sample_metadata())
        bib_str = mgr.to_bib_string()
        assert isinstance(bib_str, str)
        assert len(bib_str) > 0


class TestHasKey:
    """Tests for existence checks."""

    def test_has_key_after_add(self) -> None:
        """has_key returns True for an added entry."""
        mgr = BibManager()
        key = mgr.add_verified("10.1103/PhysRevLett.132.106701", _sample_metadata())
        assert mgr.has_key(key)

    def test_has_key_false_for_unknown(self) -> None:
        """has_key returns False for an unknown key."""
        mgr = BibManager()
        assert not mgr.has_key("nonexistent_key_xyz")

    def test_has_doi_after_add(self) -> None:
        """has_doi returns True after the DOI is added."""
        mgr = BibManager()
        doi = "10.1103/PhysRevLett.132.106701"
        mgr.add_verified(doi, _sample_metadata())
        assert mgr.has_doi(doi)
        assert mgr.has_doi("https://doi.org/" + doi)  # normalised form
