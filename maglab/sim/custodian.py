"""Engine error classification and auto-correction — Custodian.

Design rationale: PLAN §10.2 · impl/02-P1-figure-sim.md T-P1-05.

Classifies error patterns from solver exit codes and stderr.
``InputError`` (parameter range, etc.) is linked with ``validate.py``
to generate automatic correction hints.

The LLM receives only the classification result (``ErrorClass`` and hint text)
and does not read raw stderr directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Error class enumeration
# ---------------------------------------------------------------------------


class ErrorClass(StrEnum):
    """Engine error classification.

    - OK              : Completed successfully.
    - CONVERGENCE     : Convergence failure (iteration limit / magnetization divergence).
    - INPUT           : Input parameter error (range / format).
    - RESOURCE        : Resource shortage (memory / timeout / disk).
    - ENGINE_NOT_FOUND: Solver binary not installed.
    - UNKNOWN         : Unclassified error.
    """

    OK = "OK"
    CONVERGENCE = "CONVERGENCE"
    INPUT = "INPUT"
    RESOURCE = "RESOURCE"
    ENGINE_NOT_FOUND = "ENGINE_NOT_FOUND"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------


@dataclass
class CustodianResult:
    """Custodian error classification result.

    Attributes:
        error_class: Error classification.
        message: Human-readable error description.
        hint: Auto-correction hint (specific recommendation for InputError).
        backend_suggestion: Backend rerouting recommendation (for ResourceError).
        details: Additional debugging information.
    """

    error_class: ErrorClass
    message: str = ""
    hint: str = ""
    backend_suggestion: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Whether the run completed successfully."""
        return self.error_class == ErrorClass.OK


# ---------------------------------------------------------------------------
# Pattern mapping (per engine)
# ---------------------------------------------------------------------------

# MuMax3 error patterns
_MUMAX3_PATTERNS: list[tuple[re.Pattern[str], ErrorClass, str]] = [
    (
        re.compile(r"out of memory|CUDA out of memory|memory allocation", re.I),
        ErrorClass.RESOURCE,
        "GPU/CPU memory insufficient",
    ),
    (
        re.compile(r"NaN|Inf|not a number", re.I),
        ErrorClass.CONVERGENCE,
        "magnetization diverged (NaN/Inf)",
    ),
    (
        re.compile(r"invalid.*parameter|invalid.*value|out of range", re.I),
        ErrorClass.INPUT,
        "parameter out of range",
    ),
    (
        re.compile(r"no such file|cannot open|permission denied", re.I),
        ErrorClass.INPUT,
        "file access error",
    ),
    (
        re.compile(r"syntax error|unexpected token|parse error", re.I),
        ErrorClass.INPUT,
        "MX3 script syntax error",
    ),
    (
        re.compile(r"timeout|time limit|timed out", re.I),
        ErrorClass.RESOURCE,
        "execution time exceeded",
    ),
    (
        re.compile(r"mumax3: command not found|executable not found|no such file.*mumax", re.I),
        ErrorClass.ENGINE_NOT_FOUND,
        "MuMax3 binary not installed",
    ),
]

# OOMMF error patterns
_OOMMF_PATTERNS: list[tuple[re.Pattern[str], ErrorClass, str]] = [
    (
        re.compile(r"OutOfMemory|out of memory|MemAlloc", re.I),
        ErrorClass.RESOURCE,
        "insufficient memory",
    ),
    (
        re.compile(r"NaN|Inf|Diverge|diverge", re.I),
        ErrorClass.CONVERGENCE,
        "magnetization diverged",
    ),
    (
        re.compile(r"bad parameter|invalid input|value out of range|ReadError", re.I),
        ErrorClass.INPUT,
        "input parameter error",
    ),
    (
        re.compile(r"can't find|file not found|no file named", re.I),
        ErrorClass.INPUT,
        "file access error",
    ),
    (
        re.compile(r"tclsh.*not found|oommf.*not found|can't execute", re.I),
        ErrorClass.ENGINE_NOT_FOUND,
        "OOMMF/Tcl binary not installed",
    ),
    (re.compile(r"Timeout|timeout", re.I), ErrorClass.RESOURCE, "execution time exceeded"),
]

# magnum.np error patterns (Python exceptions)
_MAGNUMNP_PATTERNS: list[tuple[re.Pattern[str], ErrorClass, str]] = [
    (
        re.compile(r"CUDA out of memory|out of memory|OutOfMemoryError", re.I),
        ErrorClass.RESOURCE,
        "insufficient memory",
    ),
    (re.compile(r"nan|inf|overflow", re.I), ErrorClass.CONVERGENCE, "numerical divergence"),
    (
        re.compile(r"ValueError|KeyError|TypeError", re.I),
        ErrorClass.INPUT,
        "Python parameter error",
    ),
    (
        re.compile(r"ModuleNotFoundError.*magnumnp|ImportError.*magnumnp", re.I),
        ErrorClass.ENGINE_NOT_FOUND,
        "magnum.np not installed",
    ),
]

# Generic patterns (engine-agnostic)
_GENERIC_PATTERNS: list[tuple[re.Pattern[str], ErrorClass, str]] = [
    (
        re.compile(r"FileNotFoundError|No such file", re.I),
        ErrorClass.ENGINE_NOT_FOUND,
        "executable not found",
    ),
    (re.compile(r"Permission denied", re.I), ErrorClass.RESOURCE, "file permission error"),
    (
        re.compile(r"killed|signal 9|OOM", re.I),
        ErrorClass.RESOURCE,
        "process killed (out of memory)",
    ),
]


# ---------------------------------------------------------------------------
# Correction hint generation
# ---------------------------------------------------------------------------


def _input_error_hint(stderr: str, stdout: str) -> str:
    """Generate an auto-correction hint for input errors."""
    hints: list[str] = []

    # NaN/divergence → check cell size or damping
    if re.search(r"NaN|Inf|diverge", stderr + stdout, re.I):
        hints.append("Check whether cell size exceeds exchange length (run 'sim validate').")
        hints.append("Check that damping constant α is large enough (α > 0.01 recommended).")

    # Memory → reduce mesh
    if re.search(r"memory|oom|killed", stderr + stdout, re.I):
        hints.append("Reduce mesh size (try reducing nx/ny/nz by 50%).")
        hints.append(
            "When using the CPU fallback backend, meshes of 64³ or smaller are recommended."
        )

    # File not found → check path
    if re.search(r"not found|no such file", stderr + stdout, re.I):
        hints.append("Check the solver binary path (which mumax3 / which tclsh).")

    return " ".join(hints) if hints else "Re-validate the spec using validate.py."


def _resource_backend_suggestion(stderr: str) -> str:
    """Return a backend rerouting recommendation when resources are insufficient."""
    if re.search(r"memory|oom", stderr, re.I):
        return "Switch to the cpu backend or reduce mesh size."
    if re.search(r"timeout|time limit", stderr, re.I):
        return "Reduce t_sim_ns or simplify the mesh."
    return "Try the cpu backend fallback with a smaller mesh."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(
    returncode: int,
    stdout: str,
    stderr: str,
    engine: str = "generic",
) -> CustodianResult:
    """Classify a solver execution result.

    Parameters:
        returncode: Process exit code.
        stdout: Standard output text.
        stderr: Standard error text.
        engine: Solver engine name ("mumax3"|"oommf"|"magnumnp"|"generic").

    Returns:
        CustodianResult.
    """
    combined = (stdout + "\n" + stderr).strip()

    # Normal exit
    if returncode == 0 and not re.search(r"NaN|Inf", combined, re.I):
        return CustodianResult(
            error_class=ErrorClass.OK,
            message="completed successfully",
        )

    # Select engine-specific patterns
    if engine == "mumax3":
        patterns = _MUMAX3_PATTERNS + _GENERIC_PATTERNS
    elif engine == "oommf":
        patterns = _OOMMF_PATTERNS + _GENERIC_PATTERNS
    elif engine in ("magnumnp", "magnum.np"):
        patterns = _MAGNUMNP_PATTERNS + _GENERIC_PATTERNS
    else:
        patterns = _GENERIC_PATTERNS

    # Pattern matching
    for pat, err_class, desc in patterns:
        if pat.search(combined):
            hint = ""
            backend_suggestion = ""

            if err_class == ErrorClass.CONVERGENCE or err_class == ErrorClass.INPUT:
                hint = _input_error_hint(stderr, stdout)
            elif err_class == ErrorClass.RESOURCE:
                backend_suggestion = _resource_backend_suggestion(stderr)
            elif err_class == ErrorClass.ENGINE_NOT_FOUND:
                hint = f"{engine} binary not installed. Installation: https://mumax.github.io/ or conda install oommf"

            return CustodianResult(
                error_class=err_class,
                message=desc,
                hint=hint,
                backend_suggestion=backend_suggestion,
                details={"returncode": returncode, "engine": engine},
            )

    # Unclassified
    return CustodianResult(
        error_class=ErrorClass.UNKNOWN,
        message=f"unclassified error (returncode={returncode})",
        hint="Check stderr directly or report to the maglab issue tracker.",
        details={"returncode": returncode, "engine": engine},
    )


def classify_exception(
    exc: Exception,
    engine: str = "magnumnp",
) -> CustodianResult:
    """Classify a Python exception as an error.

    Used when an exception occurs in a Python-native solver such as magnum.np.

    Parameters:
        exc: The raised exception.
        engine: Solver engine name.

    Returns:
        CustodianResult.
    """
    stderr = f"{type(exc).__name__}: {exc}"
    return classify(
        returncode=1,
        stdout="",
        stderr=stderr,
        engine=engine,
    )
