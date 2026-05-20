"""TB2J interface — extract J_ij·DMI from Wannier90 results.

Design rationale: impl/04-P3-multiscale.md T-P3-03 · plan/03-physics-simulation.md §10.1 · Appendix D.

Uses the TB2J Python API or a subprocess wrapper. Provides explicit guidance when TB2J is not installed.
Includes J_ij completeness validation (Appendix D DFT static check — truncated-pair warning).

Reference: TB2J — He, Zhao, Franchini, Phys. Rev. Materials 5, 103602 (2021).
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.provenance.datapoint import DataPoint, ProvenanceType


@dataclass
class ExchangePair:
    """Information for a single exchange pair.

    Attributes:
        i, j : Atom indices (0-based).
        distance_ang: Interatomic distance [Å].
        J_meV: Exchange coupling [meV].
        D_meV: DMI vector [meV] (Dx, Dy, Dz).
        R: Lattice translation vector (R1, R2, R3).
    """

    i: int
    j: int
    distance_ang: float
    J_meV: float
    D_meV: tuple[float, float, float] = field(default_factory=lambda: (0.0, 0.0, 0.0))
    R: tuple[int, int, int] = field(default_factory=lambda: (0, 0, 0))


@dataclass
class TB2JResult:
    """TB2J extraction result.

    Attributes:
        exchange_pairs: List of exchange pairs.
        J_ij_meV: Aggregated 1NN positive J_ij value [meV] (nearest-neighbor ferromagnetic exchange — scalar).
                  0.0 if no pairs are present. See exchange_pairs for individual pair values.
        DMI_magnitude_meV: List of DMI magnitudes [meV].
        source_file: Parsed TB2J output file.
        complete: Whether J_ij is complete (Appendix D DFT validation).
        warnings: List of completeness warning messages.
        quantities: DataPoint dictionary.
    """

    exchange_pairs: list[ExchangePair] = field(default_factory=list)
    J_ij_meV: float = field(default=0.0)
    DMI_magnitude_meV: list[float] = field(default_factory=list)
    source_file: str = ""
    complete: bool = True
    warnings: list[str] = field(default_factory=list)
    quantities: dict[str, DataPoint] = field(default_factory=dict)

    def summary(self) -> str:
        """Return a summary string."""
        n = len(self.exchange_pairs)
        dmi_str = f"  DMI pairs: {len(self.DMI_magnitude_meV)}" if self.DMI_magnitude_meV else ""
        warn_str = f"  Warnings: {len(self.warnings)}" if self.warnings else ""
        return f"J_ij pairs: {n} | 1NN J_ij={self.J_ij_meV:.3f} meV{dmi_str}{warn_str}"


# ---------------------------------------------------------------------------
# TB2J text output parser (exchange.out format)
# ---------------------------------------------------------------------------

# TB2J exchange.out column-based header: J_iso (meV)
#  i   j   R1  R2  R3   dist(ang)   J_iso     ...
_PAIR_LINE_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([-\d]+)\s+([-\d]+)\s+([-\d]+)\s+([\d.]+)\s+([-\d.eE+]+)"
)
_EXCHANGE_SECTION_RE = re.compile(r"J_iso|exchange\s+param", re.IGNORECASE)
_DMI_LINE_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([-\d]+)\s+([-\d]+)\s+([-\d]+)\s+[\d.]+\s+[-\d.eE+]+\s+"
    r"([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)"
)

# TB2J inline format: "i=0, j=0, R=(1, 0, 0), distance=2.483 Ang, J=34.30 meV"
_INLINE_PAIR_RE = re.compile(
    r"i=(\d+),\s*j=(\d+),\s*R=\(([^)]+)\),\s*distance=([\d.]+)\s*Ang,\s*J=([-\d.eE+]+)\s*meV",
    re.IGNORECASE,
)
# TB2J inline DMI: "i=0, j=0, R=(1, 0, 0), distance=2.483 Ang, D=(0.10, 0.10, 0.20) meV"
_INLINE_DMI_RE = re.compile(
    r"i=(\d+),\s*j=(\d+),\s*R=\(([^)]+)\),\s*distance=([\d.]+)\s*Ang,\s*D=\(([^)]+)\)\s*meV",
    re.IGNORECASE,
)


def parse_tb2j_output(
    path: Path | str,
    cutoff_ang: float = 6.0,
    check_completeness: bool = True,
) -> TB2JResult:
    """Parse a TB2J exchange.out file and return a TB2JResult.

    J_ij completeness validation (Appendix D): warns when the J magnitude changes
    abruptly near the truncation radius (cutoff_ang).

    Parameters
    ----------
    path:
        TB2J output file path (exchange.out).
    cutoff_ang:
        J_ij truncation radius [Å]. Only pairs within this radius are considered complete.
    check_completeness:
        If True, perform the J_ij completeness check.

    Returns
    -------
    TB2JResult
    """
    path = Path(path)
    src = str(path)

    if not path.exists():
        return TB2JResult(
            source_file=src,
            complete=False,
            warnings=[f"TB2J output file does not exist: {path}"],
        )

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    exchange_pairs: list[ExchangePair] = []
    in_exchange = False

    for line in lines:
        # Detect section header
        if _EXCHANGE_SECTION_RE.search(line):
            in_exchange = True
            continue

        # Try inline format first: "i=0, j=0, R=(1, 0, 0), distance=2.483 Ang, J=34.30 meV"
        m_inline = _INLINE_PAIR_RE.search(line)
        if m_inline:
            i = int(m_inline.group(1))
            j = int(m_inline.group(2))
            r_parts = [int(x.strip()) for x in m_inline.group(3).split(",")]
            r1, r2, r3 = (r_parts + [0, 0, 0])[:3]
            dist = float(m_inline.group(4))
            j_iso = float(m_inline.group(5))
            pair = ExchangePair(i=i, j=j, distance_ang=dist, J_meV=j_iso, R=(r1, r2, r3))
            exchange_pairs.append(pair)
            continue

        # Handle inline DMI format (DMI-only lines without J)
        # — J lines have already been parsed above, so DMI-only lines can be ignored

        if in_exchange:
            # Column-based format: "i  j  R1  R2  R3  dist  J_iso  ..."
            m = _PAIR_LINE_RE.match(line)
            if m:
                i, j = int(m.group(1)), int(m.group(2))
                r1, r2, r3 = int(m.group(3)), int(m.group(4)), int(m.group(5))
                dist = float(m.group(6))
                j_iso = float(m.group(7))

                # Try to parse DMI (additional Dx Dy Dz columns on the same line)
                dm = _DMI_LINE_RE.match(line)
                dmi_vec = (0.0, 0.0, 0.0)
                if dm:
                    dmi_vec = (float(dm.group(6)), float(dm.group(7)), float(dm.group(8)))

                pair = ExchangePair(
                    i=i, j=j, distance_ang=dist, J_meV=j_iso, D_meV=dmi_vec, R=(r1, r2, r3)
                )
                exchange_pairs.append(pair)

    # DMI list (|D| magnitudes)
    dmi_list = [
        (p.D_meV[0] ** 2 + p.D_meV[1] ** 2 + p.D_meV[2] ** 2) ** 0.5
        for p in exchange_pairs
        if any(d != 0.0 for d in p.D_meV)
    ]

    # J_ij_meV aggregate: maximum positive J of the shortest-distance neighbors (1NN ferromagnetic exchange)
    # 0.0 if no pairs; otherwise the J_meV of the nearest-neighbor (minimum distance) pairs (positive preferred)
    j_aggregate = 0.0
    if exchange_pairs:
        min_dist = min(p.distance_ang for p in exchange_pairs)
        nn_pairs = [p for p in exchange_pairs if abs(p.distance_ang - min_dist) < 0.05]
        pos_j = [p.J_meV for p in nn_pairs if p.J_meV > 0]
        j_aggregate = max(pos_j) if pos_j else nn_pairs[0].J_meV

    # Completeness check (Appendix D)
    result_warnings: list[str] = []
    complete = True

    if check_completeness and exchange_pairs:
        # Warn if J_iso magnitude near the cutoff boundary exceeds 10% of the overall maximum
        near_cutoff = [p for p in exchange_pairs if abs(p.distance_ang - cutoff_ang) < 0.3]
        if near_cutoff:
            max_j_near = max(abs(p.J_meV) for p in near_cutoff)
            max_j_all = max(abs(p.J_meV) for p in exchange_pairs) if exchange_pairs else 1.0
            if max_j_all > 0 and max_j_near / max_j_all > 0.10:
                w = (
                    f"J_ij completeness warning (Appendix D): |J|_max={max_j_near:.3f} meV near "
                    f"cutoff={cutoff_ang:.1f} Å boundary is {max_j_near / max_j_all * 100:.0f}% "
                    f"of total |J|_max={max_j_all:.3f} meV. "
                    "Consider increasing the cutoff radius."
                )
                result_warnings.append(w)
                warnings.warn(w, UserWarning, stacklevel=2)
                complete = False

    # Build DataPoints
    quantities: dict[str, DataPoint] = {}
    if exchange_pairs:
        quantities["J_nn_meV"] = DataPoint(
            value=j_aggregate,
            units="meV",
            provenance_type=ProvenanceType.SIMULATED,
            source_ref=src,
            conditions={"description": "Nearest-neighbor exchange coupling J_ij (TB2J)"},
        )

    return TB2JResult(
        exchange_pairs=exchange_pairs,
        J_ij_meV=j_aggregate,
        DMI_magnitude_meV=dmi_list,
        source_file=src,
        complete=complete,
        warnings=result_warnings,
        quantities=quantities,
    )


# ---------------------------------------------------------------------------
# TB2J API wrapper (used when installed; provides guidance when not)
# ---------------------------------------------------------------------------


def run_tb2j(
    wannier_dir: Path | str,
    prefix: str = "wannier90",
    cutoff_ang: float = 6.0,
    extra_args: dict[str, Any] | None = None,
) -> TB2JResult:
    """Extract J_ij·DMI from Wannier90 output using the TB2J Python API.

    Returns explicit installation guidance when TB2J is not installed.

    Parameters
    ----------
    wannier_dir:
        Directory containing the Wannier90 output.
    prefix:
        Wannier90 prefix string.
    cutoff_ang:
        Exchange truncation radius [Å].
    extra_args:
        Additional TB2J parameters.

    Returns
    -------
    TB2JResult
    """
    wannier_dir = Path(wannier_dir)

    try:
        # TB2J often does not expose a Python API, so run as a subprocess
        import shutil
        import subprocess

        tb2j_bin = shutil.which("wann2J.py") or shutil.which("tb2j-wann.py")
        if tb2j_bin is None:
            return TB2JResult(
                source_file=str(wannier_dir),
                complete=False,
                warnings=[
                    "TB2J is not installed. "
                    "Install with: pip install tb2j  or  conda install -c conda-forge tb2j"
                ],
            )

        cmd = [
            tb2j_bin,
            str(wannier_dir / prefix),
            "--prefix",
            prefix,
            "--cutoff",
            str(cutoff_ang),
        ]
        if extra_args:
            for k, v in extra_args.items():
                cmd += [f"--{k}", str(v)]

        result = subprocess.run(
            cmd,
            cwd=str(wannier_dir),
            capture_output=True,
            text=True,
            timeout=3600,
        )

        if result.returncode != 0:
            return TB2JResult(
                source_file=str(wannier_dir),
                complete=False,
                warnings=[f"TB2J execution failed: {result.stderr[:500]}"],
            )

        # Search for the exchange.out path in the TB2J output
        exchange_out = wannier_dir / "TB2J_results" / "exchange.out"
        if not exchange_out.exists():
            # Also search in the current directory
            exchange_out = wannier_dir / "exchange.out"

        if exchange_out.exists():
            return parse_tb2j_output(exchange_out, cutoff_ang=cutoff_ang)
        else:
            return TB2JResult(
                source_file=str(wannier_dir),
                complete=False,
                warnings=["TB2J completed successfully but exchange.out could not be found."],
            )

    except Exception as exc:
        return TB2JResult(
            source_file=str(wannier_dir),
            complete=False,
            warnings=[f"Error during TB2J execution: {exc}"],
        )
