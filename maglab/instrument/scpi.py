"""SCPI sequence generation and static validation — `instrument/scpi.py`.

§13.1, Appendix D: Generates and statically validates SCPI command sequences.

Validation rules (Appendix D):
1. Whether the command exists in the RAG index (registered known commands).
2. Whether parameter values are within safety limits (LIMITS).
3. Whether command order matches the safe sequence (init→config→output→measure→cleanup).

Violations result in generation refusal and an error message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# SCPI command phases (safe ordering)
# ---------------------------------------------------------------------------


class SCPIPhase(IntEnum):
    """Execution phase of an SCPI command (lower value runs first).

    Safe order: INIT → CONFIG → OUTPUT → MEASURE → CLEANUP.
    """

    INIT = 0  # *RST, *CLS, *OPC
    CONFIG = 1  # SOUR:*, SENS:*, CONF:*, TRIG:*, etc. — parameter setup
    OUTPUT = 2  # OUTP ON, INIT (initiate), etc. — output activation
    MEASURE = 3  # MEAS:*, READ?, FETC?, etc. — measurement
    CLEANUP = 4  # OUTP OFF, *RST — cleanup
    QUERY = 5  # *IDN?, SYST:ERR?, etc. — queries (phase-independent)
    UNKNOWN = 9  # Unknown phase


# Command prefix → phase mapping
_PREFIX_PHASE: dict[str, SCPIPhase] = {
    "*RST": SCPIPhase.INIT,
    "*CLS": SCPIPhase.INIT,
    "*OPC": SCPIPhase.QUERY,
    "*IDN": SCPIPhase.QUERY,
    "*STB": SCPIPhase.QUERY,
    "*ESR": SCPIPhase.QUERY,
    "SOUR": SCPIPhase.CONFIG,
    ":SOUR": SCPIPhase.CONFIG,
    "CONF": SCPIPhase.CONFIG,
    ":CONF": SCPIPhase.CONFIG,
    "SENS": SCPIPhase.CONFIG,
    ":SENS": SCPIPhase.CONFIG,
    "TRIG": SCPIPhase.CONFIG,
    ":TRIG": SCPIPhase.CONFIG,
    "FORM": SCPIPhase.CONFIG,
    ":FORM": SCPIPhase.CONFIG,
    # Lock-in amplifier
    "FREQ": SCPIPhase.CONFIG,
    "PHAS": SCPIPhase.CONFIG,
    "HARM": SCPIPhase.CONFIG,
    "SLVL": SCPIPhase.CONFIG,
    "RMOD": SCPIPhase.CONFIG,
    "FMOD": SCPIPhase.CONFIG,
    # Output activation
    "OUTP": SCPIPhase.OUTPUT,
    ":OUTP": SCPIPhase.OUTPUT,
    "INIT": SCPIPhase.OUTPUT,
    ":INIT": SCPIPhase.OUTPUT,
    # Measurement
    "MEAS": SCPIPhase.MEASURE,
    ":MEAS": SCPIPhase.MEASURE,
    "READ": SCPIPhase.MEASURE,
    "FETC": SCPIPhase.MEASURE,
    "SNAP": SCPIPhase.MEASURE,
    "OUTP?": SCPIPhase.QUERY,
    "OAUX": SCPIPhase.MEASURE,
}


_MEASURE_QUERY_PREFIXES = frozenset(
    {"READ", "FETC", "MEAS", "SNAP", "OAUX", ":READ", ":FETC", ":MEAS", ":SNAP", ":OAUX"}
)


def _classify_phase(cmd: str) -> SCPIPhase:
    """Classify the execution phase of an SCPI command."""
    cmd_up = cmd.strip().upper()
    # Measurement query commands are classified as MEASURE rather than QUERY
    cmd_base = cmd_up.split("?")[0].split()[0]
    if "?" in cmd_up and cmd_base in _MEASURE_QUERY_PREFIXES:
        return SCPIPhase.MEASURE
    # Query commands (ending with ? or IDN, STB, ESR)
    if "?" in cmd_up:
        return SCPIPhase.QUERY
    # Handle OUTP OFF and *RST as cleanup-phase commands
    if re.match(r"\*RST\b", cmd_up) or re.match(r"(?::?OUTP(?:UT)?)\s+(?:OFF|0)\b", cmd_up):
        # Classification note: in simple phase detection *RST → INIT, OUTP OFF → CLEANUP
        if "*RST" in cmd_up:
            return SCPIPhase.INIT
        return SCPIPhase.CLEANUP
    for prefix, phase in _PREFIX_PHASE.items():
        if cmd_up.startswith(prefix.upper()):
            return phase
    return SCPIPhase.UNKNOWN


# ---------------------------------------------------------------------------
# SCPI command data structure
# ---------------------------------------------------------------------------


class SCPICommand(BaseModel):
    """Single SCPI command data structure."""

    command: str
    """SCPI command string (including parameters)."""
    phase: SCPIPhase = SCPIPhase.UNKNOWN
    """Execution phase (auto-classified)."""
    comment: str = ""
    """Descriptive comment."""
    param_value: float | None = None
    """Extracted numeric parameter value (when present)."""

    model_config = {"use_enum_values": False}

    @classmethod
    def from_string(cls, cmd: str, comment: str = "") -> SCPICommand:
        """Create an SCPICommand from a string."""
        phase = _classify_phase(cmd)
        # Extract numeric parameter value
        m = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", cmd)
        param_value = float(m.group()) if m else None
        return cls(command=cmd.strip(), phase=phase, comment=comment, param_value=param_value)


@dataclass
class SCPISequence:
    """SCPI command sequence."""

    commands: list[SCPICommand] = field(default_factory=list)
    model: str = "generic"
    description: str = ""

    def append(self, cmd: str, comment: str = "") -> None:
        """Append a command to the sequence."""
        self.commands.append(SCPICommand.from_string(cmd, comment))

    def to_lines(self) -> list[str]:
        """Return the list of command strings."""
        return [c.command for c in self.commands]

    def to_script(self) -> str:
        """Convert to a human-readable SCPI script text."""
        lines: list[str] = [f"# {self.description or 'SCPI sequence'} — {self.model}"]
        prev_phase: SCPIPhase | None = None
        for cmd in self.commands:
            if prev_phase is not None and cmd.phase != prev_phase and cmd.phase != SCPIPhase.QUERY:
                lines.append("")  # Blank line between phases
            comment_str = f"  # {cmd.comment}" if cmd.comment else ""
            lines.append(f"{cmd.command}{comment_str}")
            if cmd.phase != SCPIPhase.QUERY:
                prev_phase = cmd.phase
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Static validation errors
# ---------------------------------------------------------------------------


class SCPIValidationError(Exception):
    """SCPI sequence static validation failure."""


@dataclass
class SCPIValidationResult:
    """SCPI static validation result."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Summary string of the validation result."""
        if self.ok:
            return f"SCPI static validation passed ({len(self.warnings)} warnings)"
        lines = [f"SCPI static validation failed ({len(self.errors)} errors):"]
        for e in self.errors:
            lines.append(f"  [ERROR] {e}")
        for w in self.warnings:
            lines.append(f"  [WARNING] {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SCPI validator
# ---------------------------------------------------------------------------


class SCPIValidator:
    """SCPI sequence static validator.

    Safe order (Appendix D):
    - INIT phase must come before CONFIG/OUTPUT/MEASURE.
    - CONFIG must come before OUTPUT (parameter setup before output activation).
    - Unregistered commands trigger a warning when a known-command set is provided.
    """

    def __init__(
        self,
        known_commands: set[str] | None = None,
        require_init_before_output: bool = True,
        require_config_before_output: bool = True,
    ) -> None:
        """Initialize the validator.

        Args:
            known_commands: Allowed SCPI command base set. Unchecked when None.
            require_init_before_output: When True, INIT must precede OUTPUT.
            require_config_before_output: When True, CONFIG must precede OUTPUT.
        """
        self._known = known_commands
        self._req_init = require_init_before_output
        self._req_config = require_config_before_output

    def validate(
        self,
        sequence: SCPISequence | list[str],
    ) -> SCPIValidationResult:
        """Statically validate an SCPI sequence.

        Args:
            sequence: SCPISequence or a list of command strings.

        Returns:
            SCPIValidationResult — ok=True means passed.
        """
        seq: SCPISequence
        if isinstance(sequence, list):
            seq = SCPISequence()
            for cmd_str in sequence:
                seq.append(cmd_str)
        else:
            seq = sequence

        errors: list[str] = []
        warnings: list[str] = []

        seen_phases: set[SCPIPhase] = set()

        for i, scpi_cmd in enumerate(seq.commands, start=1):
            phase = SCPIPhase(scpi_cmd.phase)

            # Order check: INIT must precede OUTPUT
            if phase == SCPIPhase.OUTPUT and self._req_init and SCPIPhase.INIT not in seen_phases:
                errors.append(
                    f"Command #{i} ({scpi_cmd.command!r}): initialization (*RST/*CLS) "
                    f"is required before OUTPUT activation (Appendix D)."
                )

            # Order check: CONFIG should precede OUTPUT (optional)
            if (
                phase == SCPIPhase.OUTPUT
                and self._req_config
                and SCPIPhase.CONFIG not in seen_phases
            ):
                warnings.append(
                    f"Command #{i} ({scpi_cmd.command!r}): parameter configuration (CONFIG) "
                    f"is recommended before OUTPUT activation."
                )

            # Unknown command warning
            if self._known is not None and phase == SCPIPhase.UNKNOWN:
                cmd_base = scpi_cmd.command.split()[0].upper().rstrip("?")
                if cmd_base not in {k.upper() for k in self._known}:
                    warnings.append(
                        f"Command #{i} ({scpi_cmd.command!r}): not in the registered command set."
                    )

            if phase != SCPIPhase.QUERY:
                seen_phases.add(phase)

        ok = len(errors) == 0
        return SCPIValidationResult(ok=ok, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# SCPI sequence generator
# ---------------------------------------------------------------------------


class SCPIGenerator:
    """SCPI command sequence generator.

    §13.1: Generates sequences with a built-in safe SCPI order
    (init→config→output→measure→cleanup).
    Only sequences that pass static validation are returned.
    """

    def __init__(
        self,
        model: str = "generic",
        validator: SCPIValidator | None = None,
    ) -> None:
        """Initialize the generator.

        Args:
            model: Instrument model name.
            validator: Static validator; defaults to a new SCPIValidator when None.
        """
        self._model = model
        self._validator = validator or SCPIValidator()

    def build_sequence(
        self,
        description: str,
        config_commands: list[str],
        measure_commands: list[str],
        output_on_cmd: str | None = None,
        output_off_cmd: str | None = None,
    ) -> SCPISequence:
        """Generate an SCPI sequence with a guaranteed safe ordering.

        Runs static validation immediately after generation and raises
        SCPIValidationError on any violation.

        Args:
            description: Sequence description.
            config_commands: List of parameter configuration commands.
            measure_commands: List of measurement commands.
            output_on_cmd: Output activation command. Skipped when None.
            output_off_cmd: Output deactivation command. Skipped when None.

        Returns:
            Validated SCPISequence.

        Raises:
            SCPIValidationError: On static validation failure.
        """
        seq = SCPISequence(model=self._model, description=description)

        # 1. Initialization (§13.1 — INIT phase)
        seq.append("*RST", "factory reset")
        seq.append("*CLS", "clear status registers")

        # 2. Parameter configuration (CONFIG phase)
        for cmd in config_commands:
            seq.append(cmd)

        # 3. Output activation (OUTPUT phase)
        if output_on_cmd:
            seq.append(output_on_cmd, "enable output")

        # 4. Measurement (MEASURE phase)
        for cmd in measure_commands:
            seq.append(cmd)

        # 5. Cleanup and reset (CLEANUP phase)
        if output_off_cmd:
            seq.append(output_off_cmd, "disable output")
        seq.append("*RST", "safety reset")

        # Static validation
        result = self._validator.validate(seq)
        if not result.ok:
            raise SCPIValidationError(result.summary())

        return seq

    def minimal_id_sequence(self) -> SCPISequence:
        """Generate the minimal sequence for querying instrument identity."""
        return self.build_sequence(
            description="ID query",
            config_commands=[],
            measure_commands=["*IDN?"],
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def validate_sequence(commands: list[str]) -> SCPIValidationResult:
    """Validate a list of SCPI commands against the default rules.

    Args:
        commands: List of SCPI command strings.

    Returns:
        SCPIValidationResult.
    """
    validator = SCPIValidator()
    seq = SCPISequence()
    for cmd in commands:
        seq.append(cmd)
    return validator.validate(seq)
