"""Unit tests for sim/parse.py — JobResult parser validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.provenance.datapoint import ProvenanceType
from maglab.sim.parse import (
    JobResult,
    parse_magnumnp_result,
    parse_mumax3_table,
    parse_oommf_odt,
)

# ---------------------------------------------------------------------------
# MuMax3 table parser tests
# ---------------------------------------------------------------------------

MUMAX3_SAMPLE = """\
# t (s)\tmx ()\tmy ()\tmz ()\tE_total (J)
0.000000e+00\t1.000000e+00\t0.000000e+00\t0.000000e+00\t-1.234567e-17
1.000000e-12\t9.990000e-01\t4.472000e-02\t0.000000e+00\t-1.230000e-17
2.000000e-12\t9.980000e-01\t6.324000e-02\t0.000000e+00\t-1.225000e-17
"""


class TestParseMumax3Table:
    def test_basic_parse(self, tmp_path: Path) -> None:
        """Verify basic MuMax3 table parsing."""
        table_file = tmp_path / "table.txt"
        table_file.write_text(MUMAX3_SAMPLE, encoding="utf-8")

        result = parse_mumax3_table(table_file)

        assert result.engine == "mumax3"
        assert result.converged is True
        assert "t" in result.quantities
        assert "mx" in result.quantities
        assert "my" in result.quantities
        assert "mz" in result.quantities
        assert "E_total" in result.quantities

    def test_value_accuracy(self, tmp_path: Path) -> None:
        """Parsed values must match the original file values exactly."""
        table_file = tmp_path / "table.txt"
        table_file.write_text(MUMAX3_SAMPLE, encoding="utf-8")

        result = parse_mumax3_table(table_file)

        # t[0] = 0, mx[0] = 1.0
        t_vals = [dp.scalar() for dp in result.quantities["t"]]
        mx_vals = [dp.scalar() for dp in result.quantities["mx"]]

        assert t_vals[0] == pytest.approx(0.0)
        assert t_vals[1] == pytest.approx(1e-12)
        assert t_vals[2] == pytest.approx(2e-12)
        assert mx_vals[0] == pytest.approx(1.0)
        assert mx_vals[1] == pytest.approx(0.999)
        assert mx_vals[2] == pytest.approx(0.998)

    def test_provenance_type_simulated(self, tmp_path: Path) -> None:
        """Parsed DataPoint provenance_type must be SIMULATED."""
        table_file = tmp_path / "table.txt"
        table_file.write_text(MUMAX3_SAMPLE, encoding="utf-8")

        result = parse_mumax3_table(table_file)

        for dp in result.quantities["mx"]:
            assert dp.provenance_type == ProvenanceType.SIMULATED

    def test_source_ref_contains_filepath(self, tmp_path: Path) -> None:
        """DataPoint.source_ref must contain the file path."""
        table_file = tmp_path / "table.txt"
        table_file.write_text(MUMAX3_SAMPLE, encoding="utf-8")

        result = parse_mumax3_table(table_file)
        dp = result.quantities["mx"][0]
        assert str(table_file) in dp.source_ref

    def test_get_scalar(self, tmp_path: Path) -> None:
        """JobResult.get_scalar must be able to retrieve the last value."""
        table_file = tmp_path / "table.txt"
        table_file.write_text(MUMAX3_SAMPLE, encoding="utf-8")

        result = parse_mumax3_table(table_file)
        last_mx = result.get_scalar("mx")
        assert last_mx is not None
        assert last_mx == pytest.approx(0.998)

    def test_missing_file_returns_error(self) -> None:
        """Parsing a non-existent file must raise an exception."""
        with pytest.raises(FileNotFoundError):
            parse_mumax3_table(Path("/nonexistent/table.txt"))


# ---------------------------------------------------------------------------
# OOMMF ODT parser tests
# ---------------------------------------------------------------------------

OOMMF_ODT_SAMPLE = """\
# ODT 1.0
# Table Start
# Title: mmArchive Simulation Data
# Columns: {t} {E_total} {mx} {my} {mz}
# Units: {s} {J} {} {} {}
0.000000e+00  -1.23456e-17   1.000000  0.000000  0.000000
1.000000e-12  -1.22000e-17   0.999000  0.044720  0.000000
2.000000e-12  -1.21000e-17   0.998000  0.063240  0.000000
# Table End
"""


class TestParseOOMMFOdt:
    def test_basic_parse(self, tmp_path: Path) -> None:
        odt_file = tmp_path / "sim.odt"
        odt_file.write_text(OOMMF_ODT_SAMPLE, encoding="utf-8")

        result = parse_oommf_odt(odt_file)

        assert result.engine == "oommf"
        assert result.converged is True
        assert "t" in result.quantities
        assert "mx" in result.quantities

    def test_value_accuracy_oommf(self, tmp_path: Path) -> None:
        odt_file = tmp_path / "sim.odt"
        odt_file.write_text(OOMMF_ODT_SAMPLE, encoding="utf-8")

        result = parse_oommf_odt(odt_file)

        t_vals = [dp.scalar() for dp in result.quantities["t"]]
        mx_vals = [dp.scalar() for dp in result.quantities["mx"]]

        assert t_vals[0] == pytest.approx(0.0)
        assert t_vals[1] == pytest.approx(1e-12)
        assert mx_vals[0] == pytest.approx(1.0)
        assert mx_vals[1] == pytest.approx(0.999)

    def test_provenance_type_simulated_oommf(self, tmp_path: Path) -> None:
        odt_file = tmp_path / "sim.odt"
        odt_file.write_text(OOMMF_ODT_SAMPLE, encoding="utf-8")

        result = parse_oommf_odt(odt_file)

        for dp in result.quantities["mx"]:
            assert dp.provenance_type == ProvenanceType.SIMULATED


# ---------------------------------------------------------------------------
# magnum.np dictionary parser tests
# ---------------------------------------------------------------------------


class TestParseMagnumnpResult:
    def test_scalar_result(self) -> None:
        data = {"mx": 0.999, "my": 0.0447, "mz": 0.0}
        result = parse_magnumnp_result(data, job_id="test_relax", elapsed_s=1.5)

        assert result.engine == "magnumnp"
        assert result.elapsed_s == pytest.approx(1.5)
        assert "mx" in result.quantities
        mx_val = result.get_scalar("mx")
        assert mx_val == pytest.approx(0.999)

    def test_list_result(self) -> None:
        data = {
            "t": [0.0, 1e-12, 2e-12],
            "mx": [1.0, 0.999, 0.998],
        }
        result = parse_magnumnp_result(data, job_id="test_dynamics")

        mx_vals = [dp.scalar() for dp in result.quantities["mx"]]
        assert len(mx_vals) == 3
        assert mx_vals[0] == pytest.approx(1.0)
        assert mx_vals[2] == pytest.approx(0.998)

    def test_provenance_type_simulated_magnumnp(self) -> None:
        data = {"mx": 0.5}
        result = parse_magnumnp_result(data)

        for dp in result.quantities["mx"]:
            assert dp.provenance_type == ProvenanceType.SIMULATED

    def test_unit_inference(self) -> None:
        """Units must be correctly inferred from the physical quantity name."""
        data = {"mx": 1.0, "t": 1e-9, "E": -1e-17}
        result = parse_magnumnp_result(data)

        mx_unit = result.quantities["mx"][0].units
        t_unit = result.quantities["t"][0].units
        e_unit = result.quantities["E"][0].units

        assert mx_unit == "1"  # dimensionless
        assert t_unit == "s"
        assert e_unit == "J"

    def test_converged_flag(self) -> None:
        data = {"mx": 0.9}
        result = parse_magnumnp_result(data, converged=True)
        assert result.converged is True

        result2 = parse_magnumnp_result(data, converged=False)
        assert result2.converged is False

    def test_summary_text(self) -> None:
        data = {"mx": 0.9}
        result = parse_magnumnp_result(data, job_id="test", elapsed_s=2.0, converged=True)
        summary = result.summary()
        assert "magnumnp" in summary
        assert "converged" in summary


# ---------------------------------------------------------------------------
# JobResult basic tests
# ---------------------------------------------------------------------------


class TestJobResult:
    def test_empty_result(self) -> None:
        result = JobResult(engine="test")
        assert result.get_scalar("unknown") is None
        assert result.summary() is not None

    def test_roundtrip_serialization(self) -> None:
        """JobResult serialization/deserialization identity."""
        data = {"mx": [1.0, 0.99], "my": [0.0, 0.14]}
        original = parse_magnumnp_result(data, job_id="rt_test", elapsed_s=3.0)

        d = original.model_dump()
        restored = JobResult.model_validate(d)

        assert restored.job_id == original.job_id
        assert restored.elapsed_s == pytest.approx(original.elapsed_s)
        mx_orig = [dp.scalar() for dp in original.quantities["mx"]]
        mx_rest = [dp.scalar() for dp in restored.quantities["mx"]]
        assert mx_orig == pytest.approx(mx_rest)
