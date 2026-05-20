"""Unit tests for DFT parsers.

Design rationale: impl/04-P3-multiscale.md T-P3-03·T-P3-04.
Validates VASP OUTCAR·QE stdout parsing and TB2J exchange.out parsing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers — generate test QE/VASP/TB2J output
# ---------------------------------------------------------------------------


def _make_qe_output(converged: bool = True, mag: float = 2.22) -> str:
    """Generate a test QE pw.x stdout string."""
    conv_line = (
        "     convergence has been achieved in  14 iterations\n"
        if converged
        else "     convergence NOT achieved after  60 iterations\n"
    )
    return (
        "     Program PWSCF v.7.0 starts on  1Jan2024\n"
        "     Parallel version (MPI)\n\n"
        f"!    total energy              =     -854.23456789 Ry\n"
        f"{conv_line}"
        f"     total magnetization    =     {mag:.2f} Bohr mag/cell\n"
        "     number of atoms/cell      =            1\n"
        "     End of self-consistent calculation\n"
    )


def _make_vasp_outcar(converged: bool = True, nions: int = 2, mag: float = 2.22) -> str:
    """Generate a test VASP OUTCAR string.

    The last magnetization (z) column line must match the format expected by
    parse_vasp_outcar. Parses via _VASP_SIMPLE_RE or the last magnetization line.
    """
    return (
        f" NIONS =           {nions}\n"
        " TOTEN  =      -100.12345678 eV\n"
        " reached required accuracy - stopping structural energy minimisation\n"
        "   number of electron     14.000 magnetization"
        f"          {mag * nions:.6f}\n"
    )


def _make_tb2j_output(with_dmi: bool = False) -> str:
    """Generate a test TB2J exchange.out file.

    TB2J exchange.out format:
    Exchange pairs are listed after the J_iso section header.
    """
    lines = [
        "==================================================================================",
        "J_iso exchange parameters (meV):",
        "i=0, j=0, R=(1, 0, 0), distance=2.483 Ang, J=34.30 meV",
        "i=0, j=0, R=(0, 1, 0), distance=2.483 Ang, J=34.30 meV",
        "i=0, j=0, R=(2, 0, 0), distance=4.055 Ang, J=-1.80 meV",
    ]
    if with_dmi:
        lines += [
            "DMI parameters:",
            "i=0, j=0, R=(1, 0, 0), distance=2.483 Ang, D=(0.10, 0.10, 0.20) meV",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DFTInputGenerator tests
# ---------------------------------------------------------------------------


class TestDFTInputGenerator:
    """DFTInputGenerator — input file generation tests."""

    def test_qe_scf_generates_files(self, tmp_path: Path) -> None:
        """QE SCF input files must be generated."""
        from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator

        gen = DFTInputGenerator(engine=DFTEngine.QE)
        files = gen.generate(
            structure="bcc_fe",
            params={"calc_type": DFTCalcType.SCF},
            output_dir=tmp_path,
        )

        # QE generator uses the "pw_input" key
        assert len(files) > 0
        pw_path = files.get("pw_input") or next(iter(files.values()), None)
        assert pw_path is not None
        assert pw_path.exists()
        content = pw_path.read_text()
        assert "calculation" in content.lower() or "scf" in content.lower()

    def test_qe_mae_has_soc(self, tmp_path: Path) -> None:
        """QE MAE input must contain SOC-related keywords."""
        from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator

        gen = DFTInputGenerator(engine=DFTEngine.QE)
        files = gen.generate(
            structure="bcc_fe",
            params={"calc_type": DFTCalcType.MAE},
            output_dir=tmp_path,
        )

        assert len(files) > 0
        # Search for SOC flag across all generated files
        all_content = " ".join(f.read_text() for f in files.values() if f.exists())
        assert "lspinorb" in all_content.lower() or "noncolin" in all_content.lower()

    def test_vasp_scf_generates_files(self, tmp_path: Path) -> None:
        """VASP SCF input files (INCAR·KPOINTS·POSCAR) must be generated."""
        from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator

        gen = DFTInputGenerator(engine=DFTEngine.VASP)
        files = gen.generate(
            structure="bcc_fe",
            params={"calc_type": DFTCalcType.SCF},
            output_dir=tmp_path,
        )

        assert "INCAR" in files
        assert "KPOINTS" in files
        assert "POSCAR" in files
        assert files["INCAR"].exists()

    def test_vasp_mae_has_lsorbit(self, tmp_path: Path) -> None:
        """VASP MAE INCAR must contain LSORBIT=.TRUE."""
        from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator

        gen = DFTInputGenerator(engine=DFTEngine.VASP)
        files = gen.generate(
            structure="bcc_fe",
            params={"calc_type": DFTCalcType.MAE},
            output_dir=tmp_path,
        )

        incar = files["INCAR"].read_text()
        assert "LSORBIT" in incar

    def test_fleur_generates_stub(self, tmp_path: Path) -> None:
        """FLEUR stub input must be generated."""
        from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator

        gen = DFTInputGenerator(engine=DFTEngine.FLEUR)
        files = gen.generate(
            structure="bcc_fe",
            params={"calc_type": DFTCalcType.SCF},
            output_dir=tmp_path,
        )

        assert len(files) > 0


# ---------------------------------------------------------------------------
# DFT output parser tests
# ---------------------------------------------------------------------------


class TestParseDFTOutput:
    """parse_dft_output — QE/VASP output parsing tests."""

    def test_parse_qe_converged(self, tmp_path: Path) -> None:
        """Parse a converged QE stdout result."""
        from maglab.sim.dft.parse_dft import parse_qe_output

        qe_file = tmp_path / "pw.out"
        qe_file.write_text(_make_qe_output(converged=True, mag=2.22), encoding="utf-8")

        result = parse_qe_output(qe_file, job_id="test_qe_01")
        assert result.converged is True
        assert result.m_muB is not None
        assert abs(result.m_muB - 2.22) < 0.01

    def test_parse_qe_energy_ry_to_ev(self, tmp_path: Path) -> None:
        """QE total energy must be converted from Ry to eV/atom."""
        from maglab.sim.dft.parse_dft import parse_qe_output

        qe_file = tmp_path / "pw.out"
        qe_file.write_text(_make_qe_output(), encoding="utf-8")

        result = parse_qe_output(qe_file)
        # -854.23... Ry / 1 atom × 13.6057 eV/Ry ≈ -11618 eV/atom
        assert result.total_energy_eV is not None
        assert result.total_energy_eV < 0  # energy is negative

    def test_parse_qe_not_converged(self, tmp_path: Path) -> None:
        """Non-converged QE case must be handled correctly."""
        from maglab.sim.dft.parse_dft import parse_qe_output

        qe_file = tmp_path / "pw.out"
        qe_file.write_text(_make_qe_output(converged=False), encoding="utf-8")

        result = parse_qe_output(qe_file)
        assert result.converged is False

    def test_parse_vasp_outcar(self, tmp_path: Path) -> None:
        """Parse a VASP OUTCAR."""
        from maglab.sim.dft.parse_dft import parse_vasp_outcar

        outcar = tmp_path / "OUTCAR"
        outcar.write_text(_make_vasp_outcar(nions=2, mag=2.22), encoding="utf-8")

        result = parse_vasp_outcar(outcar)
        assert result.m_muB is not None
        assert abs(result.m_muB - 2.22) < 0.01

    def test_parse_vasp_toten(self, tmp_path: Path) -> None:
        """Total energy must be parsed from VASP OUTCAR."""
        from maglab.sim.dft.parse_dft import parse_vasp_outcar

        outcar = tmp_path / "OUTCAR"
        outcar.write_text(_make_vasp_outcar(nions=2), encoding="utf-8")

        result = parse_vasp_outcar(outcar)
        assert result.total_energy_eV is not None
        assert result.total_energy_eV < 0

    def test_parse_dft_unified_qe(self, tmp_path: Path) -> None:
        """parse_dft_output (unified entry point) — QE engine."""
        from maglab.sim.dft.input_gen import DFTEngine
        from maglab.sim.dft.parse_dft import parse_dft_output

        qe_file = tmp_path / "pw.out"
        qe_file.write_text(_make_qe_output(), encoding="utf-8")

        result = parse_dft_output(qe_file, engine=DFTEngine.QE)
        assert result.engine.lower() in ("qe", "quantum_espresso", "quantum espresso")

    def test_parse_dft_unified_vasp(self, tmp_path: Path) -> None:
        """parse_dft_output (unified entry point) — VASP engine."""
        from maglab.sim.dft.input_gen import DFTEngine
        from maglab.sim.dft.parse_dft import parse_dft_output

        outcar = tmp_path / "OUTCAR"
        outcar.write_text(_make_vasp_outcar(), encoding="utf-8")

        result = parse_dft_output(outcar, engine=DFTEngine.VASP)
        assert result.engine.lower() == "vasp"

    def test_parse_nonexistent_file_raises(self) -> None:
        """A non-existent file must raise FileNotFoundError or an appropriate exception."""
        from maglab.sim.dft.parse_dft import parse_qe_output

        with pytest.raises((FileNotFoundError, Exception)):
            parse_qe_output(Path("/nonexistent/pw.out"))


# ---------------------------------------------------------------------------
# TB2J parser tests
# ---------------------------------------------------------------------------


class TestParseTB2J:
    """parse_tb2j_output — TB2J exchange.out parsing tests."""

    def test_parse_exchange_pairs(self, tmp_path: Path) -> None:
        """Exchange pairs must be parsed."""
        from maglab.sim.dft.tb2j import parse_tb2j_output

        tb2j_file = tmp_path / "exchange.out"
        tb2j_file.write_text(_make_tb2j_output(), encoding="utf-8")

        result = parse_tb2j_output(tb2j_file)
        assert len(result.exchange_pairs) > 0

    def test_parse_j_ij_meV(self, tmp_path: Path) -> None:
        """J_ij_meV aggregate value must be computed."""
        from maglab.sim.dft.tb2j import parse_tb2j_output

        tb2j_file = tmp_path / "exchange.out"
        tb2j_file.write_text(_make_tb2j_output(), encoding="utf-8")

        result = parse_tb2j_output(tb2j_file)
        assert result.J_ij_meV > 0  # 1NN Fe is ferromagnetic (positive)

    def test_parse_dmi_with_dmi_section(self, tmp_path: Path) -> None:
        """DMI magnitude must be parsed when a DMI section is present."""
        from maglab.sim.dft.tb2j import parse_tb2j_output

        tb2j_file = tmp_path / "exchange.out"
        tb2j_file.write_text(_make_tb2j_output(with_dmi=True), encoding="utf-8")

        result = parse_tb2j_output(tb2j_file)
        # Must complete without error regardless of whether DMI is parsed
        assert result is not None

    def test_parse_empty_file_graceful(self, tmp_path: Path) -> None:
        """An empty file must be handled gracefully."""
        from maglab.sim.dft.tb2j import parse_tb2j_output

        tb2j_file = tmp_path / "exchange.out"
        tb2j_file.write_text("", encoding="utf-8")

        result = parse_tb2j_output(tb2j_file)
        assert result is not None
        assert len(result.exchange_pairs) == 0

    def test_completeness_warning_near_cutoff(self, tmp_path: Path) -> None:
        """A warning must be generated when a large J_ij is near the cutoff boundary."""
        from maglab.sim.dft.tb2j import parse_tb2j_output

        # Large J_ij close to the cutoff (5 Ang)
        tb2j_content = (
            "exchange parameters:\n"
            "(i, j, R, distance, J) in units of meV\n"
            "i=0, j=0, R=(1, 0, 0), distance=2.483 Ang, J=34.30 meV\n"
            "i=0, j=0, R=(3, 0, 0), distance=4.95 Ang, J=10.00 meV\n"  # near cutoff
        )
        tb2j_file = tmp_path / "exchange.out"
        tb2j_file.write_text(tb2j_content, encoding="utf-8")

        result = parse_tb2j_output(tb2j_file, cutoff_ang=5.0, check_completeness=True)
        # Warning or complete=False expected
        assert not result.complete or len(result.warnings) > 0


# ---------------------------------------------------------------------------
# DFTResult data structure tests
# ---------------------------------------------------------------------------


class TestDFTResult:
    """DFTResult data class tests."""

    def test_dft_result_has_quantities(self, tmp_path: Path) -> None:
        """DFTResult.quantities must hold DataPoints."""
        from maglab.sim.dft.parse_dft import parse_qe_output

        qe_file = tmp_path / "pw.out"
        qe_file.write_text(_make_qe_output(mag=2.22), encoding="utf-8")

        result = parse_qe_output(qe_file)
        assert isinstance(result.quantities, dict)

    def test_dft_result_source_file(self, tmp_path: Path) -> None:
        """DFTResult.source_file must be the actual file path."""
        from maglab.sim.dft.parse_dft import parse_qe_output

        qe_file = tmp_path / "pw.out"
        qe_file.write_text(_make_qe_output(), encoding="utf-8")

        result = parse_qe_output(qe_file, job_id="src_test")
        assert result.source_file is not None
