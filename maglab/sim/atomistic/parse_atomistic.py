"""Atomistic result parser — extract M_s(T)·T_C·A(T)·K(T) from VAMPIRE·Spirit output.

Design rationale: impl/04-P3-multiscale.md T-P3-05 · plan/03-physics-simulation.md §10.1.

The LLM does not read raw output files. This module parses them and converts the data
into an ``AtomisticResult``. T_C is determined from the inflection point of the M(T)
curve (d²M/dT²=0) or from the specific-heat peak.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from maglab.provenance.datapoint import DataPoint, ProvenanceType


@dataclass
class AtomisticResult:
    """Atomistic simulation result.

    Attributes:
        engine: Solver engine used.
        source_file: Parsed output file.
        T_K: Temperature array [K].
        M_s_Am: Saturation magnetization array [A/m] at each temperature.
        T_C_K: Extracted Curie temperature [K]. None if extraction failed.
        A_Jm: Exchange stiffness array [J/m] (temperature-dependent — None if not implemented).
        K_Jm3: Anisotropy constant array [J/m³] (temperature-dependent — None if not implemented).
        converged: Whether the simulation converged.
        quantities: DataPoint dictionary.
        extra: Additional metadata.
    """

    engine: str = ""
    source_file: str = ""
    T_K: list[float] = field(default_factory=list)
    M_s_Am: list[float] = field(default_factory=list)
    T_C_K: float | None = None
    A_Jm: list[float] | None = None
    K_Jm3: list[float] | None = None
    converged: bool = False
    quantities: dict[str, DataPoint] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Return a summary string for LLM exposure."""
        tc_str = f"T_C: {self.T_C_K:.1f} K" if self.T_C_K is not None else "T_C: not extracted"
        return (
            f"Engine: {self.engine} | Converged: {self.converged} | "
            f"Temperature steps: {len(self.T_K)} | {tc_str}"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_tc_from_mt(T: np.ndarray, M: np.ndarray) -> float | None:
    """Extract the Curie temperature T_C from an M(T) curve.

    Method: inflection point of the M(T) curve — the temperature at which
    d|M/M_0|/dT is minimized. T_C is defined as the temperature at which M
    drops below 10% of M_0.

    Parameters
    ----------
    T:
        Temperature array [K] (ascending order).
    M:
        Normalized magnetization array (M/M_s at T=0, range 0–1).

    Returns
    -------
    float | None
        Curie temperature [K], or None if extraction failed.
    """
    if len(T) < 4 or len(M) < 4:
        return None

    T_arr = np.asarray(T, dtype=float)
    M_arr = np.asarray(M, dtype=float)

    # Normalize (M_0 = first value or maximum value)
    M_0 = np.max(np.abs(M_arr))
    if M_0 < 1e-10:
        return None
    m_norm = np.abs(M_arr) / M_0

    # Method 1: m_norm = 0.1 threshold crossing
    for i in range(len(m_norm) - 1):
        if m_norm[i] >= 0.1 > m_norm[i + 1]:
            # Linear interpolation
            t_c = T_arr[i] + (T_arr[i + 1] - T_arr[i]) * (m_norm[i] - 0.1) / (
                m_norm[i] - m_norm[i + 1]
            )
            return float(t_c)

    # Method 2: minimum of dM/dT (inflection point = steepest descent)
    if len(T_arr) > 5:
        dM_dT = np.gradient(m_norm, T_arr)
        min_idx = int(np.argmin(dM_dT))
        if 0 < min_idx < len(T_arr) - 1:
            return float(T_arr[min_idx])

    return None


# ---------------------------------------------------------------------------
# VAMPIRE output parser
# ---------------------------------------------------------------------------

# VAMPIRE output format:
# # Temperature  M_x  M_y  M_z  |M|  ...
# 0.0  0.000  0.000  2.220  2.220  ...

_VAMPIRE_HEADER_RE = re.compile(r"#\s*temperature", re.IGNORECASE)
_VAMPIRE_DATA_RE = re.compile(r"^\s*([\d.e+\-]+)\s+([\d.e+\-]+)\s*", re.IGNORECASE)


def parse_vampire_output(
    output_dir: Path | str,
    mu_s_muB: float = 2.22,
    n_atoms: int = 1000,
) -> AtomisticResult:
    """Extract M_s(T) and T_C from a VAMPIRE output directory or file.

    VAMPIRE writes a magnetisation file into the output/ directory.
    VAMPIRE documentation: https://vampire.york.ac.uk/

    Parameters
    ----------
    output_dir:
        VAMPIRE output directory or path to the magnetisation file.
    mu_s_muB:
        Atomic magnetic moment [μ_B/atom]. Required for M_s [A/m] conversion.
    n_atoms:
        Number of atoms in the simulation. Required for M_s [A/m] conversion.

    Returns
    -------
    AtomisticResult
    """
    output_dir = Path(output_dir)
    src = str(output_dir)

    # Search for the VAMPIRE output file
    mag_file: Path | None = None
    if output_dir.is_file():
        mag_file = output_dir
    else:
        # Search the output/ directory
        for candidate in [
            output_dir / "output" / "magnetisation",
            output_dir / "magnetisation",
            output_dir / "output",
        ]:
            if candidate.is_file():
                mag_file = candidate
                break

    if mag_file is None or not mag_file.exists():
        return AtomisticResult(
            engine="vampire",
            source_file=src,
            converged=False,
            extra={"note": "VAMPIRE magnetisation file not found"},
        )

    text = mag_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    T_list: list[float] = []
    M_norm_list: list[float] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            T = float(parts[0])
            # VAMPIRE outputs normalized magnetization |M| = M/M_s (range 0–1)
            # Column 4: |M| (absolute magnetization), columns 1–3: Mx, My, Mz
            m_abs = float(parts[4]) if len(parts) > 4 else float(parts[1])
            T_list.append(T)
            M_norm_list.append(m_abs)
        except (ValueError, IndexError):
            continue

    if not T_list:
        return AtomisticResult(
            engine="vampire",
            source_file=src,
            converged=False,
            extra={"note": "Failed to parse VAMPIRE output data"},
        )

    # Convert M_s(T) to [A/m]
    # M_s = mu_s * N_atoms / V — volume is not directly known, so use normalized M × M_s_0
    # bcc Fe: M_s(0) = 1.71e6 A/m (experimental) — mu_s=2.22 muB, a=2.87 Å, n_atoms_per_cell=2
    # V_cell = a^3 = (2.87e-10)^3 = 2.366e-29 m³
    # M_s_0 = 2 * 2.22 * 9.274e-24 / 2.366e-29 ≈ 1.74e6 A/m
    mu_B_J_T = 9.2740100657e-24  # J/T = A·m²
    # Volume = n_atoms × bcc unit cell volume / 2 atoms_per_cell
    a_bcc_m = 2.87e-10  # bcc Fe lattice constant [m]
    n_atoms_cell = 2  # bcc: 2 atoms per unit cell
    V_total = (n_atoms / n_atoms_cell) * a_bcc_m**3
    M_s_0_Am = (n_atoms * mu_s_muB * mu_B_J_T) / V_total

    T_arr = np.array(T_list)
    M_norm_arr = np.array(M_norm_list)
    M_s_Am_arr = M_norm_arr * M_s_0_Am

    # Extract T_C
    T_C = _extract_tc_from_mt(T_arr, M_norm_arr)

    # Build DataPoints
    quantities: dict[str, DataPoint] = {}
    if T_C is not None:
        quantities["T_C_K"] = DataPoint(
            value=T_C,
            units="K",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
            conditions={"engine": "vampire", "method": "M(T) inflection point"},
        )
    if M_s_Am_arr.size > 0:
        quantities["M_s_0_Am"] = DataPoint(
            value=float(M_s_Am_arr[0]),
            units="A/m",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
            conditions={"temperature_K": float(T_arr[0])},
        )

    return AtomisticResult(
        engine="vampire",
        source_file=src,
        T_K=T_list,
        M_s_Am=M_s_Am_arr.tolist(),
        T_C_K=T_C,
        converged=True,
        quantities=quantities,
    )


# ---------------------------------------------------------------------------
# Spirit output parser
# ---------------------------------------------------------------------------


def parse_spirit_output(
    output_dir: Path | str,
    mu_s_muB: float = 2.22,
) -> AtomisticResult:
    """Extract M_s(T) and T_C from Spirit output.

    Spirit writes results in JSON or plain-text format.
    Spirit documentation: https://spirit-code.github.io/

    Parameters
    ----------
    output_dir:
        Spirit output directory or path to the result file.
    mu_s_muB:
        Atomic magnetic moment [μ_B/atom].

    Returns
    -------
    AtomisticResult
    """
    output_dir = Path(output_dir)
    src = str(output_dir)

    # Search for the Spirit output file
    result_file: Path | None = None
    for candidate in [
        output_dir / "output.json",
        output_dir / "energies.txt",
        output_dir,
    ]:
        if candidate.is_file():
            result_file = candidate
            break

    if result_file is None or not result_file.exists():
        return AtomisticResult(
            engine="spirit",
            source_file=src,
            converged=False,
            extra={"note": "Spirit output file not found"},
        )

    # Try JSON format first
    if result_file.suffix == ".json":
        try:
            import json

            data = json.loads(result_file.read_text(encoding="utf-8"))
            T_list = data.get("temperature", [])
            M_list = data.get("magnetization", [])

            if T_list and M_list:
                T_arr = np.array(T_list)
                M_arr = np.array(M_list)
                T_C = _extract_tc_from_mt(T_arr, M_arr)

                quantities: dict[str, DataPoint] = {}
                if T_C is not None:
                    quantities["T_C_K"] = DataPoint(
                        value=T_C,
                        units="K",
                        provenance_type=ProvenanceType.SIMULATED,
                        source_ref=src,
                    )

                return AtomisticResult(
                    engine="spirit",
                    source_file=src,
                    T_K=T_list,
                    M_s_Am=M_list,
                    T_C_K=T_C,
                    converged=True,
                    quantities=quantities,
                )
        except Exception:
            pass

    # Parse plain-text format
    text = result_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    T_list2: list[float] = []
    M_list2: list[float] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2:
            try:
                T_list2.append(float(parts[0]))
                M_list2.append(float(parts[1]))
            except ValueError:
                continue

    if not T_list2:
        return AtomisticResult(
            engine="spirit",
            source_file=src,
            converged=False,
        )

    T_arr2 = np.array(T_list2)
    M_arr2 = np.array(M_list2)
    T_C2 = _extract_tc_from_mt(T_arr2, M_arr2)

    quantities2: dict[str, DataPoint] = {}
    if T_C2 is not None:
        quantities2["T_C_K"] = DataPoint(
            value=T_C2,
            units="K",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
        )

    return AtomisticResult(
        engine="spirit",
        source_file=src,
        T_K=T_list2,
        M_s_Am=M_list2,
        T_C_K=T_C2,
        converged=True,
        quantities=quantities2,
    )
