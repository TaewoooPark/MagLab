"""tests/unit/test_lab_notebook.py — ELN notebook unit tests."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from maglab.lab.notebook.auto_draft import draft_from_fit_result
from maglab.lab.notebook.entry import (
    ELNEntry,
    ELNNotebook,
    MeasurementType,
)


class TestELNEntry:
    """ELNEntry serialization and deserialization tests."""

    def test_to_markdown_has_frontmatter(self):
        entry = ELNEntry(title="Test", sample="Ta/CoFeB/MgO", instrument="Lock-in")
        md = entry.to_markdown()
        assert md.startswith("---")
        assert "entry_id:" in md
        assert "date:" in md

    def test_from_markdown_roundtrip(self):
        entry = ELNEntry(
            title="FMR measurement",
            sample="Py/Pt",
            instrument="VNA",
            measurement_type=MeasurementType.FMR,
            tags=["FMR", "Py"],
            datapoint_ids=["dp-001", "dp-002"],
            body="## Observations\n\nResonance frequency 7.5 GHz",
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.title == entry.title
        assert restored.sample == entry.sample
        assert restored.measurement_type == MeasurementType.FMR
        assert "FMR" in restored.tags
        assert "dp-001" in restored.datapoint_ids

    def test_to_fair_json_ld(self):
        entry = ELNEntry(title="MOKE experiment", tags=["moke"])
        jld = entry.to_fair_json_ld()
        assert jld["@type"] == "LabNotebook"
        assert "entry_id" in jld["@id"] or jld["identifier"]

    def test_is_draft_preserved(self):
        entry = ELNEntry(is_draft=True)
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.is_draft is True

    # ------------------------------------------------------------------
    # R8 regression tests
    # ------------------------------------------------------------------

    def test_roundtrip_list_fields_with_bracket_in_value(self):
        """F-01 regression: tags/datapoints/provenance_entities containing ']'
        must survive a to_markdown() -> from_markdown() round-trip intact."""
        entry = ELNEntry(
            title="Bracket test",
            tags=["sample[A]", "normal", "sot[run1]"],
            datapoint_ids=["dp[2024-01-15]", "dp-plain"],
            provenance_entity_ids=["prov[x]", "clean-id"],
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert restored.tags == ["sample[A]", "normal", "sot[run1]"], (
            f"tags round-trip failed: {restored.tags}"
        )
        assert restored.datapoint_ids == ["dp[2024-01-15]", "dp-plain"], (
            f"datapoint_ids round-trip failed: {restored.datapoint_ids}"
        )
        assert restored.provenance_entity_ids == ["prov[x]", "clean-id"], (
            f"provenance_entity_ids round-trip failed: {restored.provenance_entity_ids}"
        )

    def test_roundtrip_empty_list_fields(self):
        """F-01 regression: empty list fields '[]' must parse back to []."""
        entry = ELNEntry(
            title="Empty lists",
            tags=[],
            datapoint_ids=[],
            provenance_entity_ids=[],
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert restored.tags == []
        assert restored.datapoint_ids == []
        assert restored.provenance_entity_ids == []

    def test_roundtrip_created_at_preserved(self):
        """F-02 regression: created_at is preserved exactly across the round-trip."""
        fixed_ts = datetime(2024, 1, 15, 10, 30, 0)
        entry = ELNEntry(title="Timestamp test", created_at=fixed_ts)
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert restored.created_at == fixed_ts, (
            f"created_at round-trip failed: expected {fixed_ts}, got {restored.created_at}"
        )

    def test_from_markdown_missing_created_at_does_not_crash(self):
        """F-02 regression: a frontmatter missing created_at must not crash
        from_markdown() — it should fall back silently to a default datetime."""
        md_no_created_at = (
            "---\n"
            "entry_id: test-id-000\n"
            "date: 2024-01-15\n"
            'sample: "Py/Pt"\n'
            'instrument: "VNA"\n'
            "measurement_type: general\n"
            "tags: []\n"
            "datapoints: []\n"
            "provenance_entities: []\n"
            "is_draft: false\n"
            "---\n\n"
            "# No timestamp\n\n"
            "body text\n"
        )
        restored = ELNEntry.from_markdown(md_no_created_at)
        # Should not raise and created_at must be a datetime instance.
        assert isinstance(restored.created_at, datetime)
        assert restored.entry_id == "test-id-000"

    def test_from_markdown_malformed_created_at_does_not_crash(self):
        """F-02 regression: a malformed created_at value must not crash
        from_markdown() — it should fall back silently to the default datetime."""
        md_bad_ts = (
            "---\n"
            "entry_id: test-id-001\n"
            "date: 2024-01-15\n"
            'sample: "Py/Pt"\n'
            'instrument: "VNA"\n'
            "measurement_type: general\n"
            "tags: []\n"
            "datapoints: []\n"
            "provenance_entities: []\n"
            "is_draft: false\n"
            "created_at: NOT_A_DATETIME\n"
            "---\n\n"
            "# Bad timestamp\n\n"
            "body text\n"
        )
        restored = ELNEntry.from_markdown(md_bad_ts)
        # Should not raise and created_at must still be a datetime instance.
        assert isinstance(restored.created_at, datetime)

    # ------------------------------------------------------------------
    # R9 regression tests
    # ------------------------------------------------------------------

    def test_roundtrip_list_fields_with_commas_in_value(self):
        """R9 F-01 regression: list values containing literal commas must survive
        a to_markdown() -> from_markdown() round-trip exactly.

        JSON serialization handles commas inside values correctly without any
        special parsing logic.
        """
        entry = ELNEntry(
            title="Comma test",
            tags=["spin-orbit, coupling", "AHE"],
            datapoint_ids=["run-01, retry", "dp-plain"],
            provenance_entity_ids=['entity, "quoted"', "clean-id"],
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert restored.tags == ["spin-orbit, coupling", "AHE"], (
            f"tags round-trip failed: {restored.tags}"
        )
        assert restored.datapoint_ids == ["run-01, retry", "dp-plain"], (
            f"datapoint_ids round-trip failed: {restored.datapoint_ids}"
        )
        assert restored.provenance_entity_ids == ['entity, "quoted"', "clean-id"], (
            f"provenance_entity_ids round-trip failed: {restored.provenance_entity_ids}"
        )

    def test_roundtrip_list_with_bracket_and_comma(self):
        """R9 F-01 regression: combination of ']' and ',' in a single value."""
        entry = ELNEntry(
            title="Mixed special chars",
            tags=["sample[A], run2", "normal"],
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert "sample[A], run2" in restored.tags, (
            f"combined bracket+comma tag lost: {restored.tags}"
        )
        assert "normal" in restored.tags

    def test_roundtrip_empty_lists_still_work_after_r9_fix(self):
        """R9 F-01 regression: empty lists still round-trip to [] after fix."""
        entry = ELNEntry(title="Empty check", tags=[], datapoint_ids=[], provenance_entity_ids=[])
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.tags == []
        assert restored.datapoint_ids == []
        assert restored.provenance_entity_ids == []

    # ------------------------------------------------------------------
    # R10 regression tests — JSON-based list serialization
    # ------------------------------------------------------------------

    def test_roundtrip_list_fields_with_double_quotes(self):
        """R10 F-01: values containing embedded double-quotes survive round-trip."""
        entry = ELNEntry(
            title="Double-quote test",
            tags=['say "hi"', "AHE"],
            datapoint_ids=['dp-"run1"'],
            provenance_entity_ids=['prov-"entity"'],
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert restored.tags == ['say "hi"', "AHE"], f"tags round-trip failed: {restored.tags}"
        assert restored.datapoint_ids == ['dp-"run1"'], (
            f"datapoint_ids round-trip failed: {restored.datapoint_ids}"
        )
        assert restored.provenance_entity_ids == ['prov-"entity"'], (
            f"provenance_entity_ids round-trip failed: {restored.provenance_entity_ids}"
        )

    def test_roundtrip_list_fields_with_backslashes(self):
        """R10 F-01: values containing backslashes survive round-trip."""
        entry = ELNEntry(
            title="Backslash test",
            tags=["path\\to\\file", "normal"],
            datapoint_ids=["dp\\001"],
            provenance_entity_ids=["prov\\x"],
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert restored.tags == ["path\\to\\file", "normal"], (
            f"tags round-trip failed: {restored.tags}"
        )
        assert restored.datapoint_ids == ["dp\\001"], (
            f"datapoint_ids round-trip failed: {restored.datapoint_ids}"
        )
        assert restored.provenance_entity_ids == ["prov\\x"], (
            f"provenance_entity_ids round-trip failed: {restored.provenance_entity_ids}"
        )

    def test_roundtrip_list_fields_combined_special_chars(self):
        """R10 F-01: combination of double-quotes, commas, brackets, backslashes."""
        entry = ELNEntry(
            title="Combined special chars",
            tags=['say "hi", world', "sample[A]", "path\\file"],
            datapoint_ids=['dp-"quoted[1]", extra'],
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)

        assert restored.tags == ['say "hi", world', "sample[A]", "path\\file"], (
            f"tags round-trip failed: {restored.tags}"
        )
        assert restored.datapoint_ids == ['dp-"quoted[1]", extra'], (
            f"datapoint_ids round-trip failed: {restored.datapoint_ids}"
        )

    def test_roundtrip_empty_lists_json(self):
        """R10 F-01: empty lists round-trip to [] with JSON serialization."""
        entry = ELNEntry(
            title="Empty JSON lists",
            tags=[],
            datapoint_ids=[],
            provenance_entity_ids=[],
        )
        md = entry.to_markdown()
        # Verify JSON form is present in the serialized output
        assert "tags: []" in md
        assert "datapoints: []" in md
        assert "provenance_entities: []" in md
        restored = ELNEntry.from_markdown(md)
        assert restored.tags == []
        assert restored.datapoint_ids == []
        assert restored.provenance_entity_ids == []

    def test_from_markdown_malformed_json_list_does_not_crash(self):
        """R10 F-01: a malformed JSON list field does not crash from_markdown()."""
        md_bad_json = (
            "---\n"
            "entry_id: test-id-bad-json\n"
            "date: 2024-01-15\n"
            'sample: "Py/Pt"\n'
            'instrument: "VNA"\n'
            "measurement_type: general\n"
            "tags: [not valid json!!]\n"
            "datapoints: []\n"
            "provenance_entities: []\n"
            "is_draft: false\n"
            "created_at: 2024-01-15T10:30:00\n"
            "---\n\n"
            "# Malformed tags\n\n"
            "body text\n"
        )
        restored = ELNEntry.from_markdown(md_bad_json)
        # Must not raise; malformed field falls back to empty list
        assert restored.tags == []
        assert restored.entry_id == "test-id-bad-json"

    def test_to_markdown_uses_json_format(self):
        """R10 F-01: to_markdown() emits JSON arrays, not bare quoted strings."""
        entry = ELNEntry(
            title="JSON format check",
            tags=["a", "b"],
            datapoint_ids=["dp-1"],
        )
        md = entry.to_markdown()
        # JSON format: tags: ["a", "b"] — must have outer brackets and quotes
        assert 'tags: ["a", "b"]' in md
        assert 'datapoints: ["dp-1"]' in md

    # ------------------------------------------------------------------
    # R11 regression tests — JSON-based scalar string serialization
    # ------------------------------------------------------------------

    def test_roundtrip_sample_with_embedded_double_quote(self):
        """R11 F-01: sample value containing an embedded double-quote round-trips."""
        entry = ELNEntry(title="Quote in sample", sample='Label "A"', instrument="Lock-in")
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.sample == 'Label "A"', f"sample round-trip failed: {restored.sample!r}"

    def test_roundtrip_sample_ending_with_double_quote(self):
        """R11 F-01: sample value ending with a double-quote round-trips (failure mode A)."""
        entry = ELNEntry(title="Trailing quote", sample='hello"', instrument="VNA")
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.sample == 'hello"', f"sample round-trip failed: {restored.sample!r}"

    def test_roundtrip_sample_wrapped_in_quotes(self):
        """R11 F-01: sample that is itself a quoted string round-trips (failure mode B)."""
        entry = ELNEntry(title="Wrapped quotes", sample='"quoted"', instrument="VNA")
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.sample == '"quoted"', f"sample round-trip failed: {restored.sample!r}"

    def test_roundtrip_instrument_with_embedded_double_quote(self):
        """R11 F-01: instrument value containing an embedded double-quote round-trips."""
        entry = ELNEntry(title="Quote in instrument", sample="Py/Pt", instrument='VNA "model-X"')
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.instrument == 'VNA "model-X"', (
            f"instrument round-trip failed: {restored.instrument!r}"
        )

    def test_roundtrip_instrument_ending_with_double_quote(self):
        """R11 F-01: instrument value ending with a double-quote round-trips."""
        entry = ELNEntry(title="Trailing quote instrument", sample="Py/Pt", instrument='Lock-in"')
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.instrument == 'Lock-in"', (
            f"instrument round-trip failed: {restored.instrument!r}"
        )

    def test_roundtrip_sample_instrument_with_backslashes(self):
        """R11 F-01: sample and instrument with backslashes survive round-trip."""
        entry = ELNEntry(
            title="Backslash test",
            sample="Ta(5)\\CoFeB(1)\\MgO(2)",
            instrument="Lab\\Instrument",
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.sample == "Ta(5)\\CoFeB(1)\\MgO(2)", (
            f"sample round-trip failed: {restored.sample!r}"
        )
        assert restored.instrument == "Lab\\Instrument", (
            f"instrument round-trip failed: {restored.instrument!r}"
        )

    def test_roundtrip_empty_sample_and_instrument(self):
        """R11 F-01: empty string values for sample and instrument round-trip correctly."""
        entry = ELNEntry(title="Empty scalars", sample="", instrument="")
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.sample == "", f"sample round-trip failed: {restored.sample!r}"
        assert restored.instrument == "", f"instrument round-trip failed: {restored.instrument!r}"

    def test_roundtrip_sample_combined_special_chars(self):
        """R11 F-01: sample and instrument with combined double-quotes and backslashes."""
        entry = ELNEntry(
            title="Combined special chars",
            sample='Batch "1" \\2024',
            instrument='Keithley\\"2400"',
        )
        md = entry.to_markdown()
        restored = ELNEntry.from_markdown(md)
        assert restored.sample == 'Batch "1" \\2024', (
            f"sample round-trip failed: {restored.sample!r}"
        )
        assert restored.instrument == 'Keithley\\"2400"', (
            f"instrument round-trip failed: {restored.instrument!r}"
        )

    def test_to_markdown_emits_json_string_for_sample_instrument(self):
        """R11 F-01: to_markdown() emits JSON-encoded strings for sample and instrument."""
        entry = ELNEntry(title="JSON scalar check", sample='Say "hi"', instrument="VNA")
        md = entry.to_markdown()
        # json.dumps('Say "hi"') == '"Say \\"hi\\""'
        assert 'sample: "Say \\"hi\\""' in md, f"Expected JSON-encoded sample in: {md}"
        assert 'instrument: "VNA"' in md

    def test_from_markdown_malformed_scalar_does_not_crash(self):
        """R11 F-01: a malformed sample or instrument value falls back gracefully."""
        # Construct a document with intentionally malformed (non-JSON) scalar values
        md = (
            "---\n"
            "entry_id: r11-test-malformed\n"
            "date: 2024-01-15\n"
            "sample: not-json-at-all\n"
            "instrument: also-not-json\n"
            "measurement_type: general\n"
            "tags: []\n"
            "datapoints: []\n"
            "provenance_entities: []\n"
            "is_draft: false\n"
            "created_at: 2024-01-15T10:30:00\n"
            "---\n\n"
            "# Malformed scalars\n\n"
            "body\n"
        )
        restored = ELNEntry.from_markdown(md)
        # Must not raise; falls back to strip('"') on the raw value
        assert restored.entry_id == "r11-test-malformed"
        # Fallback: strip('"') on a value with no surrounding quotes → same string
        assert restored.sample == "not-json-at-all"
        assert restored.instrument == "also-not-json"


class TestELNNotebook:
    """ELNNotebook save and search tests."""

    def test_create_entry_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            nb.create_entry("SOT measurement complete", sample="Ta/CoFeB")
            # verify that a file was created
            md_files = list(Path(tmpdir).rglob("*.md"))
            assert len(md_files) >= 1

    def test_list_entries_returns_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            nb.create_entry("FMR results", tags=["FMR"])
            entries = nb.list_entries()
            assert len(entries) >= 1

    def test_list_entries_tag_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            nb.create_entry("entry 1", tags=["moke"])
            nb.create_entry("entry 2", tags=["fmr"])
            fmr_entries = nb.list_entries(tags=["fmr"])
            assert all("fmr" in e.tags for e in fmr_entries)

    def test_list_entries_sample_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            nb.create_entry("e1", sample="Ta/CoFeB/MgO")
            nb.create_entry("e2", sample="Py/Pt")
            ta_entries = nb.list_entries(sample="Ta")
            assert all("ta" in e.sample.lower() for e in ta_entries)

    def test_grep_finds_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            nb.create_entry("Anomalous signal observed in SOT measurement")
            results = nb.grep("Anomalous signal")
            assert len(results) >= 1

    def test_get_entry_by_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            entry = nb.create_entry("unique content")
            fetched = nb.get_entry(entry.entry_id)
            assert fetched is not None
            assert fetched.entry_id == entry.entry_id

    def test_measurement_type_template(self):
        """Measurement-type-specific template is included in the body."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            entry = nb.create_entry(
                "FMR measurement",
                measurement_type=MeasurementType.FMR,
            )
            assert (
                "Frequency" in entry.body
                or "FMR" in entry.body
                or "frequency" in entry.body.lower()
            )


class TestAutoDraft:
    """Auto-draft generation tests."""

    def test_draft_from_fit_result_creates_draft_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            fit_result = {
                "effect_name": "anomalous_hall",
                "params": {"R_0": 1.2e-4, "R_s": 3.5e-3},
                "chi2": 0.05,
                "r2": 0.99,
                "message": "converged successfully",
            }
            entry = draft_from_fit_result(
                nb,
                fit_result,
                sample="Ta/CoFeB/MgO",
                datapoint_ids=["dp-abc-123"],
            )
            assert entry.is_draft is True
            assert "[Auto-Draft]" in entry.title
            assert "dp-abc-123" in entry.datapoint_ids

    def test_draft_body_has_fit_info(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            fit_result = {
                "effect_name": "fmr_kittel",
                "params": {"f_res": 8.5, "alpha": 0.01},
                "chi2": 0.02,
                "r2": 0.98,
            }
            entry = draft_from_fit_result(nb, fit_result)
            assert "fmr_kittel" in entry.body or "FMR" in entry.body.upper()
            assert "chi2" in entry.body.lower() or "χ²" in entry.body

    # ------------------------------------------------------------------
    # R13 regression tests — F-01 double-write / wrong title on disk
    # ------------------------------------------------------------------

    def test_draft_from_fit_result_on_disk_title_is_correct(self):
        """R13 F-01: the on-disk Markdown file must carry the correct
        '[Auto-Draft] ...' title, not the raw '## Auto-Draft ...' body heading.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            fit_result = {
                "effect_name": "anomalous_hall",
                "params": {"R_0": 1.0e-4},
                "chi2": 0.01,
                "r2": 0.99,
            }
            draft_from_fit_result(nb, fit_result, sample="Ta/CoFeB")

            # Locate the written file
            md_files = list(Path(tmpdir).rglob("*.md"))
            assert len(md_files) == 1, f"Expected exactly one .md file, got: {md_files}"

            disk_text = md_files[0].read_text(encoding="utf-8")

            # The on-disk title line must start with "# [Auto-Draft]", not "# ##"
            assert "# [Auto-Draft]" in disk_text, (
                f"On-disk title line not found in:\n{disk_text[:400]}"
            )
            assert "# ## Auto-Draft" not in disk_text, (
                f"Wrong '## '-prefixed title found in:\n{disk_text[:400]}"
            )

    def test_draft_from_fit_result_from_markdown_parses_nonempty_title(self):
        """R13 F-01: from_markdown() re-parsing the on-disk file must yield a
        non-empty title in the correct '[Auto-Draft] ...' format.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            fit_result = {
                "effect_name": "spin_hall",
                "params": {"theta_sh": 0.15},
                "chi2": 0.03,
                "r2": 0.97,
            }
            draft_from_fit_result(nb, fit_result, sample="Pt/Co")

            md_files = list(Path(tmpdir).rglob("*.md"))
            assert md_files, "No .md file written"

            disk_text = md_files[0].read_text(encoding="utf-8")
            reparsed = ELNEntry.from_markdown(disk_text)

            assert reparsed.title, "Re-parsed title must not be empty"
            assert reparsed.title.startswith("[Auto-Draft]"), (
                f"Re-parsed title has wrong format: {reparsed.title!r}"
            )
            assert "spin_hall" in reparsed.title, (
                f"Effect name missing from re-parsed title: {reparsed.title!r}"
            )

    def test_draft_from_fit_result_single_write(self):
        """R13 F-01: the entry file is written exactly once (single save_entry call)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nb = ELNNotebook(Path(tmpdir))
            fit_result = {
                "effect_name": "smr",
                "params": {"smr_ratio": 0.02},
                "chi2": 0.005,
                "r2": 0.995,
            }

            save_calls: list[ELNEntry] = []
            original_save = nb.save_entry

            def counting_save(e: ELNEntry) -> Path:
                save_calls.append(e)
                return original_save(e)

            with patch.object(nb, "save_entry", side_effect=counting_save):
                draft_from_fit_result(nb, fit_result, sample="W/CoFeB")

            assert len(save_calls) == 1, (
                f"Expected exactly 1 save_entry call, got {len(save_calls)}"
            )
            # The single call must already carry the correct title
            assert save_calls[0].title.startswith("[Auto-Draft]"), (
                f"Title at save time is wrong: {save_calls[0].title!r}"
            )
