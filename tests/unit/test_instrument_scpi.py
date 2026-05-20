"""tests/unit/test_instrument_scpi.py — SCPI sequence generation and static validation unit tests."""

from __future__ import annotations

import pytest

from maglab.instrument.scpi import (
    SCPICommand,
    SCPIGenerator,
    SCPIPhase,
    SCPISequence,
    SCPIValidator,
    validate_sequence,
)

# ---------------------------------------------------------------------------
# SCPICommand classification
# ---------------------------------------------------------------------------


def test_scpi_command_rst_is_init():
    """*RST should be classified as the INIT phase."""
    cmd = SCPICommand.from_string("*RST")
    assert cmd.phase == SCPIPhase.INIT


def test_scpi_command_cls_is_init():
    """*CLS should be classified as the INIT phase."""
    cmd = SCPICommand.from_string("*CLS")
    assert cmd.phase == SCPIPhase.INIT


def test_scpi_command_sour_volt_is_config():
    """:SOUR:VOLT should be classified as the CONFIG phase."""
    cmd = SCPICommand.from_string(":SOUR:VOLT 1.0")
    assert cmd.phase == SCPIPhase.CONFIG


def test_scpi_command_outp_on_is_output():
    """OUTP ON should be classified as the OUTPUT phase."""
    cmd = SCPICommand.from_string("OUTP ON")
    assert cmd.phase == SCPIPhase.OUTPUT


def test_scpi_command_read_query_is_measure():
    """READ? should be classified as the MEASURE phase."""
    cmd = SCPICommand.from_string("READ?")
    assert cmd.phase == SCPIPhase.MEASURE


def test_scpi_command_idn_query_is_query():
    """*IDN? should be classified as the QUERY phase."""
    cmd = SCPICommand.from_string("*IDN?")
    assert cmd.phase == SCPIPhase.QUERY


def test_scpi_command_param_extraction():
    """Should extract the numeric parameter value."""
    cmd = SCPICommand.from_string(":SOUR:VOLT 3.14")
    assert cmd.param_value == pytest.approx(3.14)


def test_scpi_command_no_param():
    """Commands without parameters should have param_value of None."""
    cmd = SCPICommand.from_string("*RST")
    assert cmd.param_value is None


# ---------------------------------------------------------------------------
# SCPISequence
# ---------------------------------------------------------------------------


def test_scpi_sequence_append_and_lines():
    """to_lines() should return the correct list after appending commands."""
    seq = SCPISequence(model="test")
    seq.append("*RST", "initialization")
    seq.append(":SOUR:VOLT 1.0")
    seq.append("OUTP ON", "enable output")
    lines = seq.to_lines()
    assert lines == ["*RST", ":SOUR:VOLT 1.0", "OUTP ON"]


def test_scpi_sequence_to_script():
    """to_script() should return a text string."""
    seq = SCPISequence(description="test", model="generic")
    seq.append("*RST")
    seq.append("*CLS")
    script = seq.to_script()
    assert "*RST" in script
    assert "*CLS" in script


# ---------------------------------------------------------------------------
# SCPIValidator
# ---------------------------------------------------------------------------


def test_validator_correct_order_passes():
    """A sequence in the correct order should pass validation."""
    cmds = ["*RST", "*CLS", ":SOUR:VOLT 1.0", "OUTP ON", "READ?"]
    result = validate_sequence(cmds)
    assert result.ok, result.summary()


def test_validator_output_without_init_fails():
    """OUTPUT without initialization should fail."""
    cmds = [":SOUR:VOLT 1.0", "OUTP ON", "READ?"]
    result = validate_sequence(cmds)
    assert not result.ok
    assert any("initialization" in e for e in result.errors), result.errors


def test_validator_empty_sequence_passes():
    """An empty sequence should pass."""
    result = validate_sequence([])
    assert result.ok


def test_validator_query_only_passes():
    """A sequence containing only query commands should pass."""
    cmds = ["*IDN?", "*STB?"]
    result = validate_sequence(cmds)
    assert result.ok


# ---------------------------------------------------------------------------
# SCPIGenerator
# ---------------------------------------------------------------------------


def test_generator_build_sequence_correct_order():
    """The generated sequence should follow the correct order."""
    gen = SCPIGenerator(model="test")
    seq = gen.build_sequence(
        description="test measurement",
        config_commands=[":SOUR:VOLT 1.0"],
        measure_commands=["READ?"],
        output_on_cmd="OUTP ON",
        output_off_cmd="OUTP OFF",
    )
    lines = seq.to_lines()
    # Start: *RST, *CLS
    assert lines[0] == "*RST"
    assert lines[1] == "*CLS"
    # CONFIG before OUTPUT
    volt_idx = lines.index(":SOUR:VOLT 1.0")
    outp_on_idx = lines.index("OUTP ON")
    read_idx = lines.index("READ?")
    outp_off_idx = lines.index("OUTP OFF")
    assert volt_idx < outp_on_idx
    assert outp_on_idx < read_idx
    assert read_idx < outp_off_idx
    # Last: *RST
    assert lines[-1] == "*RST"


def test_generator_validation_failure_raises():
    """Should raise SCPIValidationError on validation failure."""
    # Configure validator to require initialization
    validator = SCPIValidator(require_init_before_output=True)

    # build_sequence auto-inserts *RST/*CLS, so test validator directly
    seq = SCPISequence()
    seq.append("OUTP ON")  # without init
    result = validator.validate(seq)
    assert not result.ok


def test_generator_minimal_id_sequence():
    """Should generate a minimal ID query sequence."""
    gen = SCPIGenerator()
    seq = gen.minimal_id_sequence()
    lines = seq.to_lines()
    assert "*IDN?" in lines
    assert "*RST" in lines
