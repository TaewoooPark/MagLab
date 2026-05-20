"""tests/integrity/test_scpi_safety.py — SCPI safety envelope integrity tests.

§19 P4 validation gate V6: Appendix D "instrument (SCPI safety envelope / command order)"
validation rules. Commands exceeding limits or violating order must be statically rejected;
normal sequences must pass.

These tests are quantitative validations and do not use LLM-as-judge (§20).
"""

from __future__ import annotations

from maglab.instrument.safety import (
    SafetyChecker,
    SafetyProfile,
    ViolationType,
    check_scpi,
    check_script,
)
from maglab.instrument.scpi import (
    SCPIGenerator,
    SCPIValidator,
    validate_sequence,
)

# ===========================================================================
# Appendix D validation rules — over-limit command rejection
# ===========================================================================


class TestVoltageLimit:
    """Over-limit voltage command rejection (Appendix D)."""

    def test_keithley2400_max_voltage_rejected(self):
        """Exceeding the Keithley 2400 maximum voltage (210V) should be rejected."""
        cmds = ["*RST", "*CLS", ":SOUR:VOLT 300.0", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        assert not result.ok, "Over-limit voltage was accepted."
        types = [v.violation_type for v in result.violations]
        assert ViolationType.VOLTAGE_OVER in types

    def test_keithley2400_max_voltage_boundary_accepted(self):
        """The Keithley 2400 maximum voltage boundary (210V) should be accepted."""
        cmds = ["*RST", "*CLS", ":SOUR:VOLT 210.0", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        voltage_errs = [
            v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER
        ]
        assert not voltage_errs, "Boundary value was rejected."

    def test_keithley2400_min_voltage_rejected(self):
        """Below the Keithley 2400 minimum voltage (-210V) should be rejected."""
        cmds = ["*RST", "*CLS", ":SOUR:VOLT -300.0", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.VOLTAGE_UNDER in types

    def test_voltage_within_limit_accepted(self):
        """Commands within the voltage limit should be accepted."""
        cmds = ["*RST", "*CLS", ":SOUR:VOLT 5.0", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        voltage_errs = [
            v
            for v in result.violations
            if v.violation_type in (ViolationType.VOLTAGE_OVER, ViolationType.VOLTAGE_UNDER)
        ]
        assert not voltage_errs


class TestCurrentLimit:
    """Over-limit current command rejection (Appendix D)."""

    def test_keithley2400_max_current_rejected(self):
        """Exceeding the Keithley 2400 maximum current (1.05A) should be rejected."""
        cmds = ["*RST", "*CLS", ":SOUR:CURR 2.0", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.CURRENT_OVER in types

    def test_keithley2400_current_within_limit_accepted(self):
        """Commands within the current limit should be accepted."""
        cmds = ["*RST", "*CLS", ":SOUR:CURR 0.001", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        current_errs = [
            v
            for v in result.violations
            if v.violation_type in (ViolationType.CURRENT_OVER, ViolationType.CURRENT_UNDER)
        ]
        assert not current_errs


class TestFieldLimit:
    """Over-limit magnetic field command rejection (Appendix D)."""

    def test_custom_field_limit_exceeded_rejected(self):
        """Exceeding a custom magnetic field limit should be rejected."""
        profile = SafetyProfile(model="custom-magnet", max_field_t=1.0, requires_init=True)
        checker = SafetyChecker(profile)
        cmds = ["*RST", ":FIELD 1.5"]
        result = checker.check_scpi_sequence(cmds)
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.FIELD_OVER in types

    def test_custom_field_within_limit_accepted(self):
        """Commands within the magnetic field limit should be accepted."""
        profile = SafetyProfile(model="custom-magnet", max_field_t=1.0, requires_init=True)
        checker = SafetyChecker(profile)
        cmds = ["*RST", ":FIELD 0.5"]
        result = checker.check_scpi_sequence(cmds)
        field_errs = [v for v in result.violations if v.violation_type == ViolationType.FIELD_OVER]
        assert not field_errs


# ===========================================================================
# Appendix D validation rules — command order violation rejection
# ===========================================================================


class TestCommandOrderViolation:
    """Command order violation rejection (Appendix D)."""

    def test_output_without_init_rejected(self):
        """Output activation without initialization (*RST/*CLS) should be rejected."""
        cmds = [":SOUR:VOLT 1.0", "OUTP ON", "READ?"]
        result = check_scpi(cmds, model="keithley-2400")
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.ORDER_VIOLATION in types

    def test_output_with_only_cls_rejected(self):
        """*CLS alone should count as initialization (*CLS is the INIT phase)."""
        cmds = ["*CLS", ":SOUR:VOLT 1.0", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        # *CLS is also INIT phase → initialization complete
        order_errs = [
            v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION
        ]
        assert not order_errs, "Output after *CLS should be allowed."

    def test_output_after_rst_accepted(self):
        """Output activation after *RST should be allowed."""
        cmds = ["*RST", "OUTP ON"]
        result = check_scpi(cmds, model="keithley-2400")
        order_errs = [
            v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION
        ]
        assert not order_errs

    def test_scpi_validator_order_enforcement(self):
        """SCPIValidator should enforce command order."""
        SCPIValidator(require_init_before_output=True)
        result = validate_sequence(["OUTP ON", "READ?"])
        assert not result.ok
        assert any("initialization" in e for e in result.errors)


# ===========================================================================
# Normal sequence pass-through
# ===========================================================================


class TestNormalSequences:
    """Normal SCPI sequences should pass."""

    def test_complete_measurement_sequence_passes(self):
        """A complete measurement sequence (init→config→output→measure→cleanup) should pass."""
        cmds = [
            "*RST",
            "*CLS",
            ":SOUR:VOLT 1.0",
            "OUTP ON",
            "READ?",
            "OUTP OFF",
            "*RST",
        ]
        result = check_scpi(cmds, model="keithley-2400")
        assert result.ok, result.summary()

    def test_sr830_sequence_passes(self):
        """A basic SR-830 sequence should pass."""
        cmds = [
            "*RST",
            "*CLS",
            "FREQ 1000.0",
            "SENS 24",
            "OUTP? 1",
        ]
        result = check_scpi(cmds, model="sr830")
        # SR-830 has no current limit; OUTP? is a query → should pass
        order_errs = [
            v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION
        ]
        voltage_errs = [
            v
            for v in result.violations
            if v.violation_type in (ViolationType.VOLTAGE_OVER, ViolationType.VOLTAGE_UNDER)
        ]
        assert not order_errs
        assert not voltage_errs

    def test_generator_output_passes_safety(self):
        """A sequence generated by SCPIGenerator should pass safety validation."""
        gen = SCPIGenerator(model="test")
        seq = gen.build_sequence(
            description="safety test",
            config_commands=[":SOUR:VOLT 1.0"],
            measure_commands=["READ?"],
            output_on_cmd="OUTP ON",
            output_off_cmd="OUTP OFF",
        )
        result = check_scpi(seq.to_lines(), model="generic")
        assert result.ok, result.summary()


# ===========================================================================
# Script text validation
# ===========================================================================


class TestTemperatureLimit:
    """Temperature limit enforcement (Appendix D, I-07 gap fix)."""

    def test_temperature_over_limit_rejected(self):
        """A temperature command exceeding the limit must be rejected."""
        profile = SafetyProfile(
            model="cryo-controller", max_temperature_k=400.0, requires_init=False
        )
        checker = SafetyChecker(profile)
        cmds = ["*RST", "TEMP 9999"]
        result = checker.check_scpi_sequence(cmds)
        assert not result.ok, "Over-limit temperature was accepted — safety gate missing."
        types = [v.violation_type for v in result.violations]
        assert ViolationType.TEMPERATURE_OVER in types

    def test_temperature_boundary_accepted(self):
        """A temperature command at the exact limit boundary must be accepted."""
        profile = SafetyProfile(
            model="cryo-controller", max_temperature_k=400.0, requires_init=False
        )
        checker = SafetyChecker(profile)
        cmds = ["*RST", "TEMP 400.0"]
        result = checker.check_scpi_sequence(cmds)
        temp_errs = [
            v for v in result.violations if v.violation_type == ViolationType.TEMPERATURE_OVER
        ]
        assert not temp_errs, f"Boundary temperature was rejected: {temp_errs}"

    def test_temperature_within_limit_accepted(self):
        """A temperature command well within the limit must be accepted."""
        profile = SafetyProfile(
            model="cryo-controller", max_temperature_k=400.0, requires_init=False
        )
        checker = SafetyChecker(profile)
        cmds = ["*RST", "TEMP 300.0"]
        result = checker.check_scpi_sequence(cmds)
        temp_errs = [
            v for v in result.violations if v.violation_type == ViolationType.TEMPERATURE_OVER
        ]
        assert not temp_errs

    def test_temperature_no_limit_profile_passes(self):
        """When max_temperature_k is None (no limit), any temperature should pass."""
        profile = SafetyProfile(model="generic", max_temperature_k=None, requires_init=False)
        checker = SafetyChecker(profile)
        cmds = ["*RST", "TEMP 9999"]
        result = checker.check_scpi_sequence(cmds)
        temp_errs = [
            v for v in result.violations if v.violation_type == ViolationType.TEMPERATURE_OVER
        ]
        assert not temp_errs, "Unlimited temperature profile incorrectly rejected a command."

    def test_sour_temp_prefix_rejected(self):
        """SOUR:TEMP prefix must also be checked for temperature limit."""
        profile = SafetyProfile(
            model="cryo-controller", max_temperature_k=350.0, requires_init=False
        )
        checker = SafetyChecker(profile)
        cmds = ["*RST", "SOUR:TEMP 500"]
        result = checker.check_scpi_sequence(cmds)
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.TEMPERATURE_OVER in types

    def test_temp_in_script_rejected(self):
        """A Python script containing a temperature command over the limit is rejected."""
        profile = SafetyProfile(
            model="cryo-controller", max_temperature_k=400.0, requires_init=False
        )
        checker = SafetyChecker(profile)
        script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write("TEMP 9999")
"""
        result = checker.check_script_text(script)
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.TEMPERATURE_OVER in types


class TestScriptTextValidation:
    """Safety validation of Python script text (Appendix D)."""

    def test_safe_script_passes(self):
        """A safe script should pass."""
        script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write("*CLS")
instr.write(":SOUR:VOLT 1.0")
instr.write("OUTP ON")
data = instr.query("READ?")
instr.write("OUTP OFF")
instr.write("*RST")
"""
        result = check_script(script, model="generic")
        assert result.ok

    def test_dangerous_voltage_in_script_rejected(self):
        """A script containing a dangerous voltage should be rejected (Keithley-2400)."""
        script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write(":SOUR:VOLT 500.0")
instr.write("OUTP ON")
data = instr.query("READ?")
"""
        result = check_script(script, model="keithley-2400")
        assert not result.ok
        voltage_errs = [
            v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER
        ]
        assert voltage_errs

    def test_output_without_init_in_script_rejected(self):
        """A script writing OUTP ON without initialization should be rejected."""
        script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write(":SOUR:VOLT 1.0")
instr.write("OUTP ON")
data = instr.query("READ?")
"""
        result = check_script(script, model="keithley-2400")
        assert not result.ok
        order_errs = [
            v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION
        ]
        assert order_errs
