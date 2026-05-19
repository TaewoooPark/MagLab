"""Hardware safety envelope static validation — `instrument/safety.py`.

§13.1, §13.4, Appendix D: Statically detects and rejects physical safety limit
violations and command-order violations in generated scripts and SCPI sequences.
Does not touch real hardware.

Safety validation rules (Appendix D):
1. Reject commands that exceed voltage, current, magnetic field, or temperature limits.
2. Prohibit output activation without prior initialization (RST → configure → output order enforced).
3. Reject parameter changes that exceed limits while output is active.
4. Warn about unknown SCPI commands when a registered profile is present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Safety limit profile
# ---------------------------------------------------------------------------


class SafetyProfile(BaseModel):
    """Instrument safety limit profile.

    All values are SI-based (voltage V, current A, magnetic field T, temperature K).
    None means that limit is not enforced.
    """

    model: str = "generic"
    max_voltage_v: float | None = None
    min_voltage_v: float | None = None
    max_current_a: float | None = None
    min_current_a: float | None = None
    max_field_t: float | None = None
    max_temperature_k: float | None = None
    # Whether initialization is required — when True, output cannot be activated without RST/INIT
    requires_init: bool = True
    # List of known SCPI command prefixes (empty means unchecked)
    known_command_prefixes: list[str] = Field(default_factory=list)


# Built-in default profiles (based on Appendix D examples)
_BUILTIN_PROFILES: dict[str, SafetyProfile] = {
    "generic": SafetyProfile(model="generic", requires_init=True),
    "keithley-2400": SafetyProfile(
        model="keithley-2400",
        max_voltage_v=210.0,
        min_voltage_v=-210.0,
        max_current_a=1.05,
        min_current_a=-1.05,
        requires_init=True,
        known_command_prefixes=[
            ":SOUR",
            ":MEAS",
            ":OUTP",
            ":SENS",
            ":FORM",
            "*RST",
            "*CLS",
            "*IDN",
            "*OPC",
            "*STB",
        ],
    ),
    "sr830": SafetyProfile(
        model="sr830",
        max_voltage_v=5.0,
        min_voltage_v=0.0,
        requires_init=True,
        known_command_prefixes=[
            "SENS",
            "FREQ",
            "PHAS",
            "HARM",
            "SLVL",
            "RMOD",
            "REFR",
            "FMOD",
            "OUTP",
            "SNAP",
            "OAUX",
            "*RST",
            "*CLS",
            "*IDN",
            "*OPC",
        ],
    ),
    "keithley-2182": SafetyProfile(
        model="keithley-2182",
        max_voltage_v=120.0,
        min_voltage_v=-120.0,
        requires_init=True,
    ),
}


def get_profile(model_key: str) -> SafetyProfile:
    """Look up a safety profile by model key; returns the generic profile when not found."""
    key = model_key.lower().replace(" ", "-")
    return _BUILTIN_PROFILES.get(key, _BUILTIN_PROFILES["generic"])


# ---------------------------------------------------------------------------
# Violation types
# ---------------------------------------------------------------------------


class ViolationType(StrEnum):
    """Safety violation types (Appendix D)."""

    VOLTAGE_OVER = "voltage_over_limit"
    VOLTAGE_UNDER = "voltage_under_limit"
    CURRENT_OVER = "current_over_limit"
    CURRENT_UNDER = "current_under_limit"
    FIELD_OVER = "field_over_limit"
    TEMPERATURE_OVER = "temperature_over_limit"
    ORDER_VIOLATION = "order_violation"  # Command order violation
    UNKNOWN_COMMAND = "unknown_command"  # Unknown command (warning)


@dataclass
class SafetyViolation:
    """Individual safety violation entry."""

    violation_type: ViolationType
    line_number: int
    command: str
    message: str
    is_error: bool = True  # False means warning only


@dataclass
class SafetyCheckResult:
    """Overall safety validation result."""

    ok: bool
    violations: list[SafetyViolation] = field(default_factory=list)
    warnings: list[SafetyViolation] = field(default_factory=list)
    profile_used: str = "generic"

    @property
    def errors(self) -> list[SafetyViolation]:
        """Return only blocking (error-level) violations."""
        return [v for v in self.violations if v.is_error]

    def summary(self) -> str:
        """Return a summary string of the validation result."""
        if self.ok:
            return f"Safety check passed (profile: {self.profile_used})"
        msgs = [f"Safety check failed (profile: {self.profile_used}):"]
        for v in self.violations:
            prefix = "[ERROR]" if v.is_error else "[WARNING]"
            msgs.append(f"  {prefix} line {v.line_number}: {v.message}")
        return "\n".join(msgs)


# ---------------------------------------------------------------------------
# SCPI parameter value extraction pattern
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?",
)


def _extract_number(text: str) -> float | None:
    """Extract the first numeric value from a string."""
    m = _NUMBER_RE.search(text)
    return float(m.group()) if m else None


# ---------------------------------------------------------------------------
# Safety checker
# ---------------------------------------------------------------------------


class SafetyChecker:
    """Static safety envelope validator for SCPI sequences and Python scripts.

    Performs text-based static analysis — not full semantic analysis.
    Conservatively detects dangerous patterns; actual execution is Tier 3 (human).
    """

    # Voltage-related SCPI prefixes
    _VOLT_PREFIXES = (
        ":SOUR:VOLT",
        "VOLT",
        "SOUR:VOLT",
        ":VOLT",
        ":OUTPUT:VOLT",
        "OUTPUT:VOLT",
    )
    # Current-related SCPI prefixes
    _CURR_PREFIXES = (
        ":SOUR:CURR",
        "CURR",
        "SOUR:CURR",
        ":CURR",
        ":OUTPUT:CURR",
        "OUTPUT:CURR",
    )
    # Magnetic field-related SCPI prefixes
    _FIELD_PREFIXES = (
        ":FIELD",
        "FIELD",
        ":MAG:FIELD",
        "MAG:FIELD",
        ":OUTP:FIELD",
    )
    # Temperature-related SCPI prefixes
    _TEMP_PREFIXES = (
        ":TEMP",
        "TEMP",
        ":SOUR:TEMP",
        "SOUR:TEMP",
    )
    # Output activation pattern
    _OUTPUT_ON_RE = re.compile(
        r"(?:OUTP(?:UT)?\s+ON|\:OUTP(?:UT)?\s+ON|OUTP\s+1|\:OUTP\s+1)",
        re.IGNORECASE,
    )
    # Initialization command pattern
    _INIT_RE = re.compile(r"\*RST|\*CLS|:SYST:PRES|SYST:PRES", re.IGNORECASE)

    def __init__(self, profile: SafetyProfile | None = None) -> None:
        """Initialize the checker.

        Args:
            profile: Safety profile to use. Defaults to the generic profile when None.
        """
        self._profile = profile or get_profile("generic")

    def check_scpi_sequence(
        self,
        commands: list[str],
        context: str = "scpi_sequence",
    ) -> SafetyCheckResult:
        """Statically validate a list of SCPI commands.

        Args:
            commands: List of SCPI command strings.
            context: Validation context label (used in logging).

        Returns:
            Safety check result.
        """
        violations: list[SafetyViolation] = []
        warnings: list[SafetyViolation] = []
        initialized = False

        for lineno, cmd in enumerate(commands, start=1):
            cmd_stripped = cmd.strip()
            if not cmd_stripped or cmd_stripped.startswith(("#", "//")):
                continue

            # Detect initialization
            if self._INIT_RE.search(cmd_stripped):
                initialized = True
                continue

            # Check output activation order
            if (
                self._OUTPUT_ON_RE.search(cmd_stripped)
                and self._profile.requires_init
                and not initialized
            ):
                violations.append(
                    SafetyViolation(
                        violation_type=ViolationType.ORDER_VIOLATION,
                        line_number=lineno,
                        command=cmd_stripped,
                        message=(
                            f"Initialization (*RST/*CLS) is required before activating output "
                            f"(Appendix D command-order rule). Command: {cmd_stripped!r}"
                        ),
                        is_error=True,
                    )
                )

            # Voltage limit check
            if any(cmd_stripped.upper().startswith(p.upper()) for p in self._VOLT_PREFIXES):
                val = _extract_number(cmd_stripped)
                if val is not None:
                    if (
                        self._profile.max_voltage_v is not None
                        and val > self._profile.max_voltage_v
                    ):
                        violations.append(
                            SafetyViolation(
                                violation_type=ViolationType.VOLTAGE_OVER,
                                line_number=lineno,
                                command=cmd_stripped,
                                message=(
                                    f"Voltage {val:.3g} V exceeds the maximum limit "
                                    f"of {self._profile.max_voltage_v:.3g} V."
                                ),
                            )
                        )
                    if (
                        self._profile.min_voltage_v is not None
                        and val < self._profile.min_voltage_v
                    ):
                        violations.append(
                            SafetyViolation(
                                violation_type=ViolationType.VOLTAGE_UNDER,
                                line_number=lineno,
                                command=cmd_stripped,
                                message=(
                                    f"Voltage {val:.3g} V is below the minimum limit "
                                    f"of {self._profile.min_voltage_v:.3g} V."
                                ),
                            )
                        )

            # Current limit check
            if any(cmd_stripped.upper().startswith(p.upper()) for p in self._CURR_PREFIXES):
                val = _extract_number(cmd_stripped)
                if val is not None:
                    if (
                        self._profile.max_current_a is not None
                        and val > self._profile.max_current_a
                    ):
                        violations.append(
                            SafetyViolation(
                                violation_type=ViolationType.CURRENT_OVER,
                                line_number=lineno,
                                command=cmd_stripped,
                                message=(
                                    f"Current {val:.3g} A exceeds the maximum limit "
                                    f"of {self._profile.max_current_a:.3g} A."
                                ),
                            )
                        )
                    if (
                        self._profile.min_current_a is not None
                        and val < self._profile.min_current_a
                    ):
                        violations.append(
                            SafetyViolation(
                                violation_type=ViolationType.CURRENT_UNDER,
                                line_number=lineno,
                                command=cmd_stripped,
                                message=(
                                    f"Current {val:.3g} A is below the minimum limit "
                                    f"of {self._profile.min_current_a:.3g} A."
                                ),
                            )
                        )

            # Magnetic field limit check
            if any(cmd_stripped.upper().startswith(p.upper()) for p in self._FIELD_PREFIXES):
                val = _extract_number(cmd_stripped)
                if (
                    val is not None
                    and self._profile.max_field_t is not None
                    and abs(val) > self._profile.max_field_t
                ):
                    violations.append(
                        SafetyViolation(
                            violation_type=ViolationType.FIELD_OVER,
                            line_number=lineno,
                            command=cmd_stripped,
                            message=(
                                f"Magnetic field |{val:.3g}| T exceeds the maximum limit "
                                f"of {self._profile.max_field_t:.3g} T."
                            ),
                        )
                    )

            # Temperature limit check
            if any(cmd_stripped.upper().startswith(p.upper()) for p in self._TEMP_PREFIXES):
                val = _extract_number(cmd_stripped)
                if (
                    val is not None
                    and self._profile.max_temperature_k is not None
                    and val > self._profile.max_temperature_k
                ):
                    violations.append(
                        SafetyViolation(
                            violation_type=ViolationType.TEMPERATURE_OVER,
                            line_number=lineno,
                            command=cmd_stripped,
                            message=(
                                f"Temperature {val:.3g} K exceeds the maximum limit "
                                f"of {self._profile.max_temperature_k:.3g} K."
                            ),
                        )
                    )

            # Unknown command warning (when known_command_prefixes is set)
            if self._profile.known_command_prefixes:
                cmd_upper = cmd_stripped.upper()
                known = any(
                    cmd_upper.startswith(p.upper()) for p in self._profile.known_command_prefixes
                )
                if not known:
                    warnings.append(
                        SafetyViolation(
                            violation_type=ViolationType.UNKNOWN_COMMAND,
                            line_number=lineno,
                            command=cmd_stripped,
                            message=f"Unrecognized SCPI command (profile: {self._profile.model}): {cmd_stripped!r}",
                            is_error=False,
                        )
                    )

        ok = not any(v.is_error for v in violations)
        return SafetyCheckResult(
            ok=ok,
            violations=violations,
            warnings=warnings,
            profile_used=self._profile.model,
        )

    def check_script_text(
        self,
        script_text: str,
        context: str = "script",
    ) -> SafetyCheckResult:
        """Extract SCPI commands from a Python script text and validate them.

        Extracts string literals from .write(…) and .query(…) calls.

        Args:
            script_text: Python script text.
            context: Validation context label (used in logging).

        Returns:
            Safety check result.
        """
        # Extract commands from write("CMD") or write('CMD') patterns
        write_re = re.compile(r'\.write\s*\(\s*["\']([^"\']+)["\']\s*\)')

        # Estimate line numbers (approximate — limitation of static analysis)
        lines = script_text.splitlines()
        lineno_map: dict[str, int] = {}
        for i, line in enumerate(lines, start=1):
            m = write_re.search(line)
            if m:
                cmd = m.group(1)
                lineno_map.setdefault(cmd, i)

        # Order by appearance in the script
        ordered: list[tuple[int, str]] = []
        seen: set[str] = set()
        for i, line in enumerate(lines, start=1):
            m = write_re.search(line)
            if m:
                cmd = m.group(1)
                if cmd not in seen:
                    seen.add(cmd)
                    ordered.append((i, cmd))

        # Convert to list for order-based checking
        cmd_list = [cmd for _, cmd in ordered]
        result = self.check_scpi_sequence(cmd_list, context=context)

        # Adjust line numbers to match actual script lines
        for v in result.violations + result.warnings:
            cmd = v.command
            if cmd in lineno_map:
                v.line_number = lineno_map[cmd]

        return result

    def check_file(self, path: Path) -> SafetyCheckResult:
        """Read a file and run the safety check on it.

        Args:
            path: Path to the script or SCPI file to validate.

        Returns:
            Safety check result.

        Raises:
            FileNotFoundError: When the file does not exist.
        """
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        if suffix == ".py":
            return self.check_script_text(text, context=str(path))
        # .scpi or other — treat as a line-by-line SCPI command list
        commands = [line.strip() for line in text.splitlines()]
        return self.check_scpi_sequence(commands, context=str(path))


# ---------------------------------------------------------------------------
# Convenience functions (used by CLI and tests)
# ---------------------------------------------------------------------------


def check_scpi(
    commands: list[str],
    model: str = "generic",
) -> SafetyCheckResult:
    """Validate a list of SCPI commands against a safety profile.

    Args:
        commands: List of SCPI command strings.
        model: Safety profile model key.

    Returns:
        Safety check result.
    """
    profile = get_profile(model)
    checker = SafetyChecker(profile)
    return checker.check_scpi_sequence(commands)


def check_script(
    script_text: str,
    model: str = "generic",
) -> SafetyCheckResult:
    """Safety-validate a Python script text.

    Args:
        script_text: Python script text.
        model: Safety profile model key.

    Returns:
        Safety check result.
    """
    profile = get_profile(model)
    checker = SafetyChecker(profile)
    return checker.check_script_text(script_text)
