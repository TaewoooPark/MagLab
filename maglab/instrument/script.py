"""Measurement script generation — `instrument/script.py`.

§13.1, §13.4, T-P4-16: Generates a measurement script from a natural-language
experiment description and instrument information.

Script structure: initialization → parameter configuration → measurement loop →
cleanup and reset (§13.1 Appendix D).
Output is a standalone Python file delivered to the user only after passing safety.py.
Actual execution is Tier 3 (human).
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, Field, field_validator

from maglab.instrument.safety import SafetyCheckResult, check_script

# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    """Return the Jinja2 environment."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# Script configuration data structures
# ---------------------------------------------------------------------------


class SweepConfig(BaseModel):
    """Sweep configuration."""

    start: float = 0.0
    stop: float = 1.0
    step: float = 0.1
    settle_time_s: float = 0.1

    @field_validator("step")
    @classmethod
    def step_must_be_nonzero(cls, v: float) -> float:
        """Reject step=0 to prevent ZeroDivisionError in the generated np.arange loop."""
        if v == 0.0:
            raise ValueError("sweep step must be non-zero (step=0.0 would cause ZeroDivisionError in the generated script)")
        return v


class ScriptConfig(BaseModel):
    """Measurement script generation configuration."""

    model: str
    """Instrument model name (★ never guess — confirm with the user, §13.2)."""
    description: str
    """Experiment description (natural language)."""
    iface: str = "GPIB"
    """Interface type."""
    resource_string: str = "GPIB0::1::INSTR"
    """VISA resource string."""
    sweep: SweepConfig = Field(default_factory=SweepConfig)
    """Sweep configuration."""
    output_csv: str = "measurement.csv"
    """Output CSV file path."""
    measurement_type: str = "voltage"
    """Measurement type (voltage, current, resistance, etc.)."""
    safety_model: str = "generic"
    """Safety profile model key for validation."""


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------


class ScriptGenerator:
    """Measurement script generator.

    Generates measurement scripts with the §13.1 safe SCPI order built in.
    Returns the result only after it passes safety.py validation.
    """

    def __init__(self) -> None:
        self._env = _get_jinja_env()

    def generate(
        self,
        config: ScriptConfig,
        output_path: Path | None = None,
        skip_safety_check: bool = False,
    ) -> tuple[str, SafetyCheckResult]:
        """Generate a measurement script.

        Args:
            config: Script generation configuration.
            output_path: Path to save the file. Not saved when None.
            skip_safety_check: When True, skips safety validation (for testing only).

        Returns:
            (script text, SafetyCheckResult) tuple.
            When SafetyCheckResult.ok is False, the script must not be executed.
        """
        ctx: dict[str, Any] = {
            "model": config.model,
            "iface": config.iface.upper(),
            "description": config.description,
            "resource_string": config.resource_string,
            "start_value": config.sweep.start,
            "stop_value": config.sweep.stop,
            "step_value": config.sweep.step,
            "settle_time_s": config.sweep.settle_time_s,
            "output_csv": config.output_csv,
            "measurement_type": config.measurement_type,
            "timestamp": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC"),
        }

        template = self._env.get_template("measurement_script.py.j2")
        code = template.render(**ctx)

        # Safety validation (§13.4 — must pass safety.py)
        if skip_safety_check:
            safety_result = SafetyCheckResult(ok=True, profile_used=config.safety_model)
        else:
            safety_result = check_script(code, model=config.safety_model)

        if output_path is not None and safety_result.ok:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(code, encoding="utf-8")

        return code, safety_result


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def generate_measurement_script(
    model: str,
    description: str,
    iface: str = "GPIB",
    output_path: Path | None = None,
    sweep_start: float = 0.0,
    sweep_stop: float = 1.0,
    sweep_step: float = 0.1,
    settle_time_s: float = 0.1,
    output_csv: str = "measurement.csv",
    safety_model: str = "generic",
) -> tuple[str, SafetyCheckResult]:
    """Convenience function to generate a measurement script.

    Args:
        model: Instrument model name (★ never guess — confirm with the user, §13.2).
        description: Experiment description.
        iface: Interface type (GPIB, USB, TCPIP, SERIAL).
        output_path: Path to save the file.
        sweep_start: Sweep start value.
        sweep_stop: Sweep stop value.
        sweep_step: Sweep step size.
        settle_time_s: Settle time per step in seconds.
        output_csv: Output CSV file path.
        safety_model: Safety validation profile model key.

    Returns:
        (script text, SafetyCheckResult) tuple.
    """
    config = ScriptConfig(
        model=model,
        description=description,
        iface=iface,
        sweep=SweepConfig(
            start=sweep_start,
            stop=sweep_stop,
            step=sweep_step,
            settle_time_s=settle_time_s,
        ),
        output_csv=output_csv,
        safety_model=safety_model,
    )
    generator = ScriptGenerator()
    return generator.generate(config, output_path=output_path)
