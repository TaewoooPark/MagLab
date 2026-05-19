"""DFT result parser — extract J_ij·MAE·DMI·m from VASP·QE·FLEUR output.

Design rationale: impl/04-P3-multiscale.md T-P3-02 · plan/03-physics-simulation.md §10.1.

The LLM does not read raw output files. This module parses them and converts the data
into a ``DFTResult`` struct; only the ``DFTResult.summary()`` text is exposed to the LLM.

Output units preserve the native units from the solver (unit conversion is delegated to ``handoff.py``):
- J_ij : meV
- MAE  : meV/atom
- DMI  : meV
- m    : μ_B / atom
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from maglab.provenance.datapoint import DataPoint, ProvenanceType


class DFTResult(BaseModel):
    """DFT result data structure.

    Attributes:
        engine: Name of the DFT engine used.
        source_file: Path to the parsed output file.
        J_ij_meV: Exchange coupling parameter list [meV]. (Populated when extracted via TB2J.)
        MAE_meV_atom: Magnetocrystalline anisotropy energy [meV/atom]. None if absent.
        DMI_meV: DMI vector magnitude [meV]. None if absent.
        m_muB: Magnetic moment [μ_B/atom]. None if absent.
        total_energy_eV: Total energy [eV/atom]. None if absent.
        converged: Whether the calculation converged.
        quantities: DataPoint dictionary (for provenance tracking).
        extra: Engine-specific additional metadata.
    """

    engine: str = Field(default="", description="DFT engine")
    source_file: str = Field(default="", description="Parsed output file")
    J_ij_meV: list[float] = Field(default_factory=list, description="J_ij list [meV]")
    MAE_meV_atom: float | None = Field(default=None, description="MAE [meV/atom]")
    DMI_meV: float | None = Field(default=None, description="DMI magnitude [meV]")
    m_muB: float | None = Field(default=None, description="Magnetic moment [μ_B/atom]")
    total_energy_eV: float | None = Field(default=None, description="Total energy [eV/atom]")
    converged: bool = Field(default=False)
    quantities: dict[str, DataPoint] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def summary(self) -> str:
        """Return a summary string for LLM exposure."""
        lines = [
            f"Engine: {self.engine} | Converged: {self.converged}",
            f"J_ij pairs: {len(self.J_ij_meV)}",
        ]
        if self.MAE_meV_atom is not None:
            lines.append(f"MAE: {self.MAE_meV_atom:.4f} meV/atom")
        if self.DMI_meV is not None:
            lines.append(f"DMI: {self.DMI_meV:.4f} meV")
        if self.m_muB is not None:
            lines.append(f"m: {self.m_muB:.4f} μ_B/atom")
        return " | ".join(lines)


# ---------------------------------------------------------------------------
# QE pw.x output parser
# ---------------------------------------------------------------------------

_QE_CONV_RE = re.compile(r"convergence has been achieved", re.IGNORECASE)
_QE_MAG_RE = re.compile(r"total magnetization\s*=\s*([\d.\-]+)\s*Bohr mag/cell", re.IGNORECASE)
_QE_ENERGY_RE = re.compile(r"!\s+total energy\s*=\s*([\d.\-]+)\s*Ry", re.IGNORECASE)
_QE_NATS_RE = re.compile(r"number of atoms/cell\s*=\s*(\d+)", re.IGNORECASE)


def parse_qe_output(path: Path | str, job_id: str = "") -> DFTResult:
    """Parse a QE pw.x output file (.out) and return a DFTResult.

    Extracted quantities:
    - Convergence (convergence has been achieved)
    - Total energy [Ry] → [eV/atom]
    - Total magnetic moment [μ_B/cell] → [μ_B/atom]
    - MAE requires a separate calculation (energy difference between two directions) — None if not implemented

    Parameters
    ----------
    path:
        QE output file path (.out).
    job_id:
        Job ID (uses filename if not provided).

    Returns
    -------
    DFTResult
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"QE output file does not exist: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    converged = bool(_QE_CONV_RE.search(text))

    # Number of atoms
    nat_match = _QE_NATS_RE.search(text)
    nat = int(nat_match.group(1)) if nat_match else 1

    # Total energy [Ry] → [eV/atom]
    energy_eV_atom: float | None = None
    energy_matches = _QE_ENERGY_RE.findall(text)
    if energy_matches:
        last_ry = float(energy_matches[-1])
        energy_eV_atom = last_ry * 13.605693122994 / nat  # Ry → eV, per atom

    # Magnetic moment [μ_B/atom]
    m_muB: float | None = None
    mag_matches = _QE_MAG_RE.findall(text)
    if mag_matches:
        m_total = float(mag_matches[-1])
        m_muB = abs(m_total) / nat

    # Build DataPoints
    quantities: dict[str, DataPoint] = {}
    src = str(path)

    if energy_eV_atom is not None:
        quantities["total_energy_eV_atom"] = DataPoint(
            value=energy_eV_atom,
            units="eV/atom",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
        )
    if m_muB is not None:
        quantities["m_muB"] = DataPoint(
            value=m_muB,
            units="muB/atom",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
        )

    return DFTResult(
        engine="qe",
        source_file=src,
        m_muB=m_muB,
        total_energy_eV=energy_eV_atom,
        converged=converged,
        quantities=quantities,
    )


# ---------------------------------------------------------------------------
# VASP OUTCAR parser
# ---------------------------------------------------------------------------

_VASP_CONV_RE = re.compile(r"General timing and accounting", re.IGNORECASE)
_VASP_MAG_RE = re.compile(r"magnetization \(x\).*?tot\s+([\d.\-]+)", re.DOTALL)
_VASP_ENERGY_RE = re.compile(r"TOTEN\s*=\s*([\d.\-]+)\s*eV", re.IGNORECASE)
_VASP_NIONS_RE = re.compile(r"NIONS\s*=\s*(\d+)", re.IGNORECASE)


def parse_vasp_outcar(path: Path | str, job_id: str = "") -> DFTResult:
    """Parse a VASP OUTCAR file and return a DFTResult.

    Parameters
    ----------
    path:
        VASP OUTCAR file path.
    job_id:
        Job ID.

    Returns
    -------
    DFTResult
    """
    path = Path(path)
    if not path.exists():
        return DFTResult(engine="vasp", source_file=str(path), converged=False)

    text = path.read_text(encoding="utf-8", errors="replace")
    converged = bool(_VASP_CONV_RE.search(text))

    nions_match = _VASP_NIONS_RE.search(text)
    nat = int(nions_match.group(1)) if nions_match else 1

    # Total energy [eV/atom] — use the last TOTEN value
    energy_eV_atom: float | None = None
    energy_matches = _VASP_ENERGY_RE.findall(text)
    if energy_matches:
        energy_eV_atom = float(energy_matches[-1]) / nat

    # Magnetic moment [μ_B/atom] — last tot value from OUTCAR
    m_muB: float | None = None
    mag_match = _VASP_MAG_RE.search(text[::-1])  # reversed search to get the last value
    if not mag_match:
        # Retry with a simpler regex
        simple_re = re.compile(r"number of electron\s+[\d.]+\s+magnetization\s+([\d.\-]+)")
        sm = simple_re.search(text)
        if sm:
            m_muB = abs(float(sm.group(1))) / nat
    else:
        m_muB = abs(float(mag_match.group(1))) / nat

    quantities: dict[str, DataPoint] = {}
    src = str(path)
    if energy_eV_atom is not None:
        quantities["total_energy_eV_atom"] = DataPoint(
            value=energy_eV_atom,
            units="eV/atom",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
        )
    if m_muB is not None:
        quantities["m_muB"] = DataPoint(
            value=m_muB,
            units="muB/atom",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
        )

    return DFTResult(
        engine="vasp",
        source_file=src,
        m_muB=m_muB,
        total_energy_eV=energy_eV_atom,
        converged=converged,
        quantities=quantities,
    )


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


def parse_dft_output(
    path: Path | str,
    engine: str = "qe",
    job_id: str = "",
) -> DFTResult:
    """Parse a DFT output file and return a DFTResult.

    Parameters
    ----------
    path:
        DFT output file path.
    engine:
        DFT engine name ("qe" / "vasp" / "fleur").
    job_id:
        Job ID.

    Returns
    -------
    DFTResult
    """
    path = Path(path)
    engine_lower = engine.lower()

    if engine_lower == "qe":
        return parse_qe_output(path, job_id)
    elif engine_lower == "vasp":
        return parse_vasp_outcar(path, job_id)
    else:
        # FLEUR and others: return a stub
        return DFTResult(
            engine=engine_lower,
            source_file=str(path),
            converged=False,
            extra={"note": f"{engine} parser not implemented — returning stub"},
        )
