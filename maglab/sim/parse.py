"""Structured JobResult generation — the LLM does not read raw output files.

Design rationale: PLAN §10.2 · impl/02-P1-figure-sim.md T-P1-04.

Converts MuMax3 table (.out), OOMMF table (.odt), and magnum.np dictionary
output into a ``JobResult`` struct.

Only the ``JobResult`` summary text is exposed to the LLM; raw output files
are parsed by this module into ``DataPoint`` arrays.
OVF/OMF magnetization file paths are stored by reference only (actual reading
is done by P3 simviz).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# JobResult data structure
# ---------------------------------------------------------------------------


class JobResult(BaseModel):
    """Simulation job execution result struct.

    Attributes:
        job_id: Unique job identifier.
        engine: Name of the solver engine used.
        converged: Convergence status. None means convergence cannot be determined.
        elapsed_s: Execution time [s].
        quantities: Physical quantity name → DataPoint array.
        ovf_paths: List of OVF/OMF magnetization file paths (reference only).
        raw_stdout: Solver standard output (for debugging).
        raw_stderr: Solver standard error (for debugging).
        error_message: Error message (on failure).
        extra: Engine-specific additional metadata.
    """

    job_id: str = Field(default="", description="Job ID")
    engine: str = Field(default="", description="Solver engine")
    converged: bool | None = Field(default=None, description="Convergence status")
    elapsed_s: float = Field(default=0.0, description="Execution time [s]")
    quantities: dict[str, list[DataPoint]] = Field(default_factory=dict)
    ovf_paths: list[str] = Field(default_factory=list)
    raw_stdout: str = Field(default="")
    raw_stderr: str = Field(default="")
    error_message: str = Field(default="")
    extra: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Summary text (exposable to LLM)
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a summary text suitable for LLM exposure.

        Only this structured summary is provided to the LLM;
        raw output files are not passed directly.
        """
        status = (
            "converged" if self.converged else ("not converged" if self.converged is False else "unknown")
        )
        q_summary = ", ".join(f"{k}: {len(v)}" for k, v in self.quantities.items())
        return (
            f"engine: {self.engine} | status: {status} | "
            f"elapsed: {self.elapsed_s:.1f}s | "
            f"quantities: [{q_summary}] | "
            f"OVF files: {len(self.ovf_paths)}"
        )

    def get_scalar(self, quantity: str, index: int = -1) -> float | None:
        """Return the scalar value of the specified physical quantity.

        Parameters:
            quantity: Physical quantity name.
            index: DataPoint array index. -1 returns the last value.

        Returns:
            float value, or None if not found.
        """
        dps = self.quantities.get(quantity)
        if not dps:
            return None
        dp = dps[index]
        try:
            return dp.scalar()
        except TypeError:
            return None


# ---------------------------------------------------------------------------
# MuMax3 table parser (.out / table.txt)
# ---------------------------------------------------------------------------

# MuMax3 table header: # t (s)    mx ()    my ()    mz ()    ...
_MUMAX3_HEADER_RE = re.compile(r"^#\s+(.*)")
_MUMAX3_UNIT_RE = re.compile(r"^(.+?)\s*\(([^)]*)\)$")


def parse_mumax3_table(
    path: Path | str,
    job_id: str = "",
) -> JobResult:
    """Parse a MuMax3 table output file (.out) and return a JobResult.

    MuMax3 table.txt format:
        # t (s)    mx ()    my ()    mz ()    ...
        0.000e+00   1.000  0.000  0.000  ...

    Parameters:
        path: Path to the MuMax3 table file.
        job_id: Job ID (uses filename if empty).

    Returns:
        JobResult.
    """
    path = Path(path)
    if not job_id:
        job_id = path.stem

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Parse header
    header_line: str | None = None
    data_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = _MUMAX3_HEADER_RE.match(stripped)
        if m:
            header_line = m.group(1)
        elif not stripped.startswith("#"):
            data_lines.append(stripped)

    if header_line is None:
        return JobResult(
            job_id=job_id,
            engine="mumax3",
            error_message="MuMax3 table header not found.",
            raw_stdout=text,
        )

    # Parse column names and units
    col_names: list[str] = []
    col_units: list[str] = []
    for token in header_line.split("\t"):
        token = token.strip()
        if not token:
            continue
        m2 = _MUMAX3_UNIT_RE.match(token)
        if m2:
            col_names.append(m2.group(1).strip())
            col_units.append(m2.group(2).strip() or "1")
        else:
            col_names.append(token)
            col_units.append("1")

    # Parse data rows
    quantities: dict[str, list[DataPoint]] = {name: [] for name in col_names}
    source_ref = str(path)

    for line_no, line in enumerate(data_lines, start=1):
        vals = line.split()
        if len(vals) < len(col_names):
            continue
        for i, (name, unit) in enumerate(zip(col_names, col_units, strict=False)):
            try:
                val = float(vals[i])
            except ValueError:
                continue
            quantities[name].append(
                DataPoint(
                    value=val,
                    units=unit if unit else "1",
                    provenance_type=ProvenanceType.SIMULATED,
                    source_ref=f"{source_ref}:line{line_no}",
                )
            )

    return JobResult(
        job_id=job_id,
        engine="mumax3",
        converged=True,  # presence of the table file is treated as completion
        quantities=quantities,
        raw_stdout=text,
    )


# ---------------------------------------------------------------------------
# OOMMF table parser (.odt)
# ---------------------------------------------------------------------------

# OOMMF ODT format:
# # ODT 1.0
# # Table Start
# # Columns: {t} {E} {mx} {my} {mz} ...
# # Units: {s} {J} ...
# 0.0  -1.23e-17  0.999  ...
# # Table End


def parse_oommf_odt(
    path: Path | str,
    job_id: str = "",
) -> JobResult:
    """Parse an OOMMF ODT table file and return a JobResult.

    Parameters:
        path: Path to the OOMMF .odt file.
        job_id: Job ID.

    Returns:
        JobResult.
    """
    path = Path(path)
    if not job_id:
        job_id = path.stem

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    col_names: list[str] = []
    col_units: list[str] = []
    data_lines: list[str] = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# Columns:"):
            raw = stripped[len("# Columns:") :].strip()
            # OOMMF columns: {Oxford::RungeKuttaEvolve:evolver:Total field energy density} ...
            # Simple parse: use the last word inside {} as the column name
            tokens = re.findall(r"\{([^}]+)\}", raw)
            if not tokens:
                tokens = raw.split()
            col_names = [t.split(":")[-1].strip() for t in tokens]
        elif stripped.startswith("# Units:"):
            raw = stripped[len("# Units:") :].strip()
            tokens = re.findall(r"\{([^}]+)\}", raw)
            if not tokens:
                tokens = raw.split()
            col_units = [t.strip() or "1" for t in tokens]
        elif stripped == "# Table Start":
            in_table = True
        elif stripped == "# Table End":
            in_table = False
        elif in_table and not stripped.startswith("#"):
            data_lines.append(stripped)

    if not col_names:
        return JobResult(
            job_id=job_id,
            engine="oommf",
            error_message="OOMMF ODT column header not found.",
            raw_stdout=text,
        )

    # Pad unit list with "1" if shorter than column list
    while len(col_units) < len(col_names):
        col_units.append("1")

    source_ref = str(path)
    quantities: dict[str, list[DataPoint]] = {name: [] for name in col_names}

    for line_no, line in enumerate(data_lines, start=1):
        vals = line.split()
        if len(vals) < len(col_names):
            continue
        for i, (name, unit) in enumerate(zip(col_names, col_units, strict=False)):
            try:
                val = float(vals[i])
            except ValueError:
                continue
            quantities[name].append(
                DataPoint(
                    value=val,
                    units=unit if unit else "1",
                    provenance_type=ProvenanceType.SIMULATED,
                    source_ref=f"{source_ref}:line{line_no}",
                )
            )

    return JobResult(
        job_id=job_id,
        engine="oommf",
        converged=True,
        quantities=quantities,
        raw_stdout=text,
    )


# ---------------------------------------------------------------------------
# magnum.np dictionary parser (Python-native)
# ---------------------------------------------------------------------------


def parse_magnumnp_result(
    data: dict[str, Any],
    job_id: str = "magnumnp",
    elapsed_s: float = 0.0,
    converged: bool | None = None,
    source_ref: str = "",
) -> JobResult:
    """Convert a magnum.np execution result dictionary into a JobResult.

    magnum.np runs natively in Python without external files, so results
    are received as a dictionary directly.

    ``data`` format:
        {"mx": float_or_list, "my": ..., "mz": ..., "t": ..., ...}
        or {"mx": [v1, v2, ...], ...} (time series)

    Parameters:
        data: magnum.np result dictionary.
        job_id: Job ID.
        elapsed_s: Execution time [s].
        converged: Convergence status.
        source_ref: Source reference.

    Returns:
        JobResult.
    """
    quantities: dict[str, list[DataPoint]] = {}

    for key, val in data.items():
        # Unit inference (name-based heuristic)
        unit = _infer_unit(key)

        if isinstance(val, (int, float)):
            quantities[key] = [
                DataPoint(
                    value=float(val),
                    units=unit,
                    provenance_type=ProvenanceType.SIMULATED,
                    source_ref=source_ref or job_id,
                )
            ]
        elif isinstance(val, (list, tuple)):
            quantities[key] = [
                DataPoint(
                    value=float(v),
                    units=unit,
                    provenance_type=ProvenanceType.SIMULATED,
                    source_ref=f"{source_ref or job_id}:idx{i}",
                )
                for i, v in enumerate(val)
                if isinstance(v, (int, float))
            ]

    return JobResult(
        job_id=job_id,
        engine="magnumnp",
        converged=converged,
        elapsed_s=elapsed_s,
        quantities=quantities,
    )


def _infer_unit(name: str) -> str:
    """Infer units from a physical quantity name (heuristic).

    Parameters:
        name: Physical quantity name (e.g. "mx", "t", "E").

    Returns:
        Unit string.
    """
    name_lower = name.lower()
    if name_lower in ("mx", "my", "mz", "m"):
        return "1"  # normalized magnetization — dimensionless
    if name_lower == "t":
        return "s"
    if name_lower in ("e", "energy", "e_total"):
        return "J"
    if name_lower in ("bx", "by", "bz", "b"):
        return "T"
    if name_lower in ("hx", "hy", "hz", "h"):
        return "A/m"
    return "1"
