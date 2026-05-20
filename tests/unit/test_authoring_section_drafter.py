"""Unit tests for maglab/authoring/section_drafter.py (§16.5)."""

from __future__ import annotations

import pytest

from maglab.authoring.bib_manager import BibManager
from maglab.authoring.data_vault import AuthoringBlockedError, DataVault
from maglab.authoring.section_drafter import (
    DRAFTING_ORDER,
    HUMAN_REVIEW_MARKER,
    DraftResult,
    SectionDrafter,
    SectionType,
    _extract_cite_keys_from_tex,
    compile_draft,
    readback_pdf,
)
from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dp(value: float = 2.5, units: str = "T") -> DataPoint:
    return DataPoint(
        value=value,
        units=units,
        provenance_type=ProvenanceType.MEASURED,
        source_ref="test",
    )


def _make_vault(*keys: str) -> DataVault:
    """Return a vault with the given keys mapped to minimal DataPoints."""
    return DataVault({k: _make_dp() for k in keys})


def _make_bib(*dois: str) -> BibManager:
    """Return a BibManager with verified entries for the given DOIs."""
    mgr = BibManager()
    for doi in dois:
        mgr.add_verified(doi, {"title": "Test Paper", "author": "A, B", "year": "2024"})
    return mgr


def _make_llm(response: str):
    """Return a mock LLM that always returns *response*."""

    def _llm(system: str, user: str) -> str:  # noqa: ARG001
        return response

    return _llm


class TestSectionDrafter:
    """Tests for SectionDrafter.draft_section."""

    def test_drafts_methods_section(self) -> None:
        """draft_section returns a DraftResult for SectionType.METHODS."""
        vault = _make_vault("B_applied")
        bib = _make_bib()
        llm = _make_llm("The sample was grown by MBE. Field {{dp:B_applied}}.")
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm)
        result = drafter.draft_section(SectionType.METHODS, "Grow GdFeCo by MBE.")
        assert isinstance(result, DraftResult)
        assert result.section == SectionType.METHODS

    def test_draft_has_human_review_marker(self) -> None:
        """Draft LaTeX starts with the human review marker."""
        vault = DataVault()
        bib = _make_bib()
        llm = _make_llm("Simple methods text with no numbers or cites. [FILL]")
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm)
        result = drafter.draft_section(SectionType.METHODS, "No data.")
        assert HUMAN_REVIEW_MARKER in result.tex

    def test_vault_placeholder_substituted(self) -> None:
        """DataVault placeholders are replaced in the output tex."""
        vault = _make_vault("rho_AHE")
        bib = _make_bib()
        llm = _make_llm(r"AHE resistivity is {{dp:rho_AHE}}.")
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm)
        result = drafter.draft_section(SectionType.RESULTS, "AHE was measured.")
        assert "{{dp:rho_AHE}}" not in result.tex

    def test_missing_vault_key_raises(self) -> None:
        """Missing DataVault key raises AuthoringBlockedError."""
        vault = DataVault()  # empty
        bib = _make_bib()
        llm = _make_llm(r"Resistivity {{dp:rho_AHE}} was measured.")
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm)
        with pytest.raises(AuthoringBlockedError):
            drafter.draft_section(SectionType.RESULTS, "AHE result.")

    @pytest.mark.parametrize("section_type", list(SectionType))
    def test_all_section_types_accepted(self, section_type: SectionType) -> None:
        """All SectionType values are accepted without TypeError."""
        vault = DataVault()
        bib = _make_bib()
        llm = _make_llm("No cites or numbers. [FILL: placeholder]")
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm)
        result = drafter.draft_section(section_type, "Context.")
        assert result.section == section_type

    def test_drafting_order_is_correct(self) -> None:
        """DRAFTING_ORDER starts with Methods and ends with Title."""
        assert DRAFTING_ORDER[0] == SectionType.METHODS
        assert DRAFTING_ORDER[-1] == SectionType.TITLE

    def test_string_section_type_accepted(self) -> None:
        """String section type is coerced to SectionType."""
        vault = DataVault()
        bib = _make_bib()
        llm = _make_llm("Methods text. [FILL]")
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm)
        result = drafter.draft_section("methods", "Context.")
        assert result.section == SectionType.METHODS

    def test_abstract_word_limit_warning(self, caplog) -> None:
        """Abstract word count exceeding the limit triggers a warning."""
        import logging

        vault = DataVault()
        bib = _make_bib()
        many_words = " ".join(["word"] * 300)
        llm = _make_llm(many_words)
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm, abstract_word_limit=50)
        with caplog.at_level(logging.WARNING, logger="maglab.authoring.section_drafter"):
            drafter.draft_section(SectionType.ABSTRACT, "Context.")
        assert any("word count" in r.message for r in caplog.records)

    def test_abstract_word_limit_not_inflated_by_boilerplate(self, caplog) -> None:
        """F5 regression: boilerplate (HUMAN_REVIEW_MARKER + _AI_DISCLOSURE) must NOT
        count toward the word limit.

        A 40-word abstract with a 50-word limit must not trigger a warning even
        though the boilerplate appended to final_tex adds ~40 extra words.
        """
        import logging

        from maglab.authoring.section_drafter import _AI_DISCLOSURE

        vault = DataVault()
        bib = _make_bib()
        # 40 content words — well within the 50-word limit.
        abstract_body = " ".join(["content"] * 40)
        llm = _make_llm(abstract_body)
        drafter = SectionDrafter(vault=vault, bib_manager=bib, llm_fn=llm, abstract_word_limit=50)
        with caplog.at_level(logging.WARNING, logger="maglab.authoring.section_drafter"):
            result = drafter.draft_section(SectionType.ABSTRACT, "Context.")

        # The final tex must still contain the disclosure (sanity check).
        assert _AI_DISCLOSURE in result.tex

        # No word-count warning should have fired — the 40-word body is within limit.
        assert not any("word count" in r.message for r in caplog.records), (
            "F5 regression: boilerplate inflated word count caused a spurious warning"
        )


class TestExtractCiteKeys:
    """Tests for _extract_cite_keys_from_tex."""

    def test_extracts_single_key(self) -> None:
        r"""Extracts single \cite{KEY}."""
        keys = _extract_cite_keys_from_tex(r"As shown in \cite{Smith2024}.")
        assert keys == ["Smith2024"]

    def test_extracts_multi_key(self) -> None:
        r"""Extracts multiple keys from \cite{A,B,C}."""
        keys = _extract_cite_keys_from_tex(r"\cite{Smith2024,Doe2023,Jones2022}")
        assert set(keys) == {"Smith2024", "Doe2023", "Jones2022"}

    def test_deduplicates_keys(self) -> None:
        r"""Duplicate \cite{} references are deduplicated."""
        keys = _extract_cite_keys_from_tex(r"\cite{A} and \cite{A} and \cite{B}")
        assert keys.count("A") == 1
        assert "B" in keys


class TestCompileDraft:
    """Tests for compile_draft (tectonic integration)."""

    def test_missing_entry_point_returns_failure(self, tmp_path) -> None:
        """compile_draft returns failure when main.tex is absent."""
        result = compile_draft(tmp_path)
        assert not result.success
        assert result.pdf_path is None
        assert "not found" in result.log.lower()

    def test_tectonic_not_installed_returns_failure(self, tmp_path) -> None:
        """compile_draft returns failure when tectonic binary is absent."""
        (tmp_path / "main.tex").write_text(
            r"\documentclass{article}\begin{document}Hi\end{document}"
        )
        result = compile_draft(tmp_path, tectonic_bin="nonexistent_tectonic_xyz")
        assert not result.success
        assert "not found" in result.log.lower() or "tectonic" in result.log.lower()


class TestReadbackPdf:
    """Tests for readback_pdf."""

    def test_missing_pdf_returns_failure(self, tmp_path) -> None:
        """readback_pdf returns failure when PDF is absent."""
        feedback = readback_pdf(tmp_path / "nonexistent.pdf")
        assert not feedback.layout_ok
        assert len(feedback.issues) > 0

    def test_existing_pdf_no_vision_fn_passes(self, tmp_path) -> None:
        """A non-empty existing PDF without a vision function passes."""
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 " + b"0" * 200)
        feedback = readback_pdf(pdf)
        assert feedback.layout_ok

    def test_vision_fn_overflow_detected(self, tmp_path) -> None:
        """A vision function returning 'overflow' flags a layout issue."""
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 " + b"0" * 200)
        vision_fn = lambda p: "There is an overflow in the page layout."  # noqa: E731
        feedback = readback_pdf(pdf, vision_fn=vision_fn)
        assert not feedback.layout_ok
        assert len(feedback.issues) > 0
