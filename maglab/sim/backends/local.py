"""Local process backend — direct execution of OOMMF·MuMax3.

Design rationale: impl/02-P1-figure-sim.md T-P1-02.

Runs external binaries (OOMMF·MuMax3) directly as subprocesses.
Handles timeouts, process termination, and stdout/stderr capture,
returning results as a structured dictionary — interpretation is delegated to parse.py.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

# Default timeout [s] — based on local CPU execution
DEFAULT_TIMEOUT_S: float = 3600.0  # 1 hour


def run_subprocess(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run an external command as a subprocess and return the result.

    Parameters:
        cmd: Command and argument list to execute.
        cwd: Working directory. None uses the current directory.
        timeout_s: Timeout [s]. The process is killed if this limit is exceeded.
        env: Environment variable dictionary. None inherits the parent environment.

    Returns:
        {"returncode": int, "stdout": str, "stderr": str, "elapsed_s": float}
    """
    start = time.monotonic()

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            env=env,
        )
        elapsed = time.monotonic() - start
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "elapsed_s": elapsed,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"timeout: execution time {elapsed:.1f}s exceeded the limit of {timeout_s}s.",
            "elapsed_s": elapsed,
        }
    except FileNotFoundError as exc:
        return {
            "returncode": -2,
            "stdout": "",
            "stderr": f"FileNotFoundError: {exc}. Binary not found on PATH.",
            "elapsed_s": 0.0,
        }


def check_binary(name: str) -> str | None:
    """Check whether a binary is available on PATH and return its path.

    Parameters:
        name: Binary name (e.g. "mumax3", "tclsh").

    Returns:
        Absolute path string, or None if not found.
    """
    return shutil.which(name)


def run_mumax3(
    script_path: Path | str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, object]:
    """Run a MuMax3 script.

    Returns an error result immediately if the MuMax3 binary is not on PATH.

    Parameters:
        script_path: Path to the .mx3 script file.
        timeout_s: Timeout [s].

    Returns:
        run_subprocess result dictionary.
    """
    script_path = Path(script_path)
    binary = check_binary("mumax3")
    if binary is None:
        return {
            "returncode": -2,
            "stdout": "",
            "stderr": "mumax3: command not found. MuMax3 is not installed on PATH. https://mumax.github.io/",
            "elapsed_s": 0.0,
        }

    return run_subprocess(
        [binary, str(script_path)],
        cwd=script_path.parent,
        timeout_s=timeout_s,
    )


def run_oommf(
    mif_path: Path | str,
    *,
    oommf_path: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, object]:
    """Run an OOMMF MIF file.

    OOMMF is invoked via the ``tclsh oommf.tcl boxsi`` pattern.
    The location of oommf.tcl is specified by the OOMMF_ROOT environment variable
    or via oommf_path.

    Parameters:
        mif_path: Path to the .mif file.
        oommf_path: Path to oommf.tcl. If None, uses the oommf binary found on PATH.
        timeout_s: Timeout [s].

    Returns:
        run_subprocess result dictionary.
    """
    mif_path = Path(mif_path)

    # Determine the OOMMF execution command
    if oommf_path:
        oommf_tcl = Path(oommf_path)
        tclsh = check_binary("tclsh")
        if tclsh is None:
            return {
                "returncode": -2,
                "stdout": "",
                "stderr": "tclsh: command not found. Tcl/Tk is required to run OOMMF.",
                "elapsed_s": 0.0,
            }
        cmd = [tclsh, str(oommf_tcl), "boxsi", str(mif_path)]
    else:
        # Search PATH for oommf or oommf.tcl
        oommf_bin = check_binary("oommf") or check_binary("oommf.tcl")
        if oommf_bin is None:
            return {
                "returncode": -2,
                "stdout": "",
                "stderr": (
                    "oommf: command not found. OOMMF is not on PATH. "
                    "conda install -c conda-forge oommf or https://math.nist.gov/oommf/"
                ),
                "elapsed_s": 0.0,
            }
        if oommf_bin.endswith(".tcl"):
            tclsh = check_binary("tclsh")
            if tclsh is None:
                return {
                    "returncode": -2,
                    "stdout": "",
                    "stderr": "tclsh: command not found.",
                    "elapsed_s": 0.0,
                }
            cmd = [tclsh, oommf_bin, "boxsi", str(mif_path)]
        else:
            cmd = [oommf_bin, "boxsi", str(mif_path)]

    return run_subprocess(
        cmd,
        cwd=mif_path.parent,
        timeout_s=timeout_s,
    )
