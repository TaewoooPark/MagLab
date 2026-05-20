"""tests/unit/test_instrument_safety.py — safety envelope static validation unit tests."""

from __future__ import annotations

from maglab.instrument.safety import (
    SafetyChecker,
    SafetyProfile,
    ViolationType,
    check_scpi,
    check_script,
    get_profile,
)

# ---------------------------------------------------------------------------
# Profile lookup
# ---------------------------------------------------------------------------


def test_get_builtin_profile_keithley():
    """Retrieve the built-in Keithley-2400 profile."""
    p = get_profile("keithley-2400")
    assert p.model == "keithley-2400"
    assert p.max_voltage_v is not None
    assert p.max_current_a is not None


def test_get_unknown_profile_falls_back_to_generic():
    """Unknown model key should return the generic profile."""
    p = get_profile("unknown-xyz-999")
    assert p.model == "generic"


# ---------------------------------------------------------------------------
# SCPI sequence safety validation
# ---------------------------------------------------------------------------


def test_normal_scpi_sequence_passes():
    """A normal SCPI sequence should pass."""
    cmds = ["*RST", "*CLS", ":SOUR:VOLT 1.0", "OUTP ON", "READ?", "OUTP OFF", "*RST"]
    result = check_scpi(cmds, model="generic")
    assert result.ok, result.summary()


def test_voltage_over_limit_rejected():
    """Commands exceeding the voltage limit should be rejected (Keithley-2400: max=210V)."""
    cmds = ["*RST", "*CLS", ":SOUR:VOLT 250.0", "OUTP ON"]
    result = check_scpi(cmds, model="keithley-2400")
    assert not result.ok
    violations = [v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER]
    assert violations, "A voltage-over violation should be detected."


def test_voltage_under_limit_rejected():
    """Commands exceeding the negative voltage limit should be rejected."""
    cmds = ["*RST", "*CLS", ":SOUR:VOLT -250.0", "OUTP ON"]
    result = check_scpi(cmds, model="keithley-2400")
    assert not result.ok
    violations = [v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_UNDER]
    assert violations


def test_current_over_limit_rejected():
    """Commands exceeding the current limit should be rejected (Keithley-2400: max=1.05A)."""
    cmds = ["*RST", "*CLS", ":SOUR:CURR 2.0", "OUTP ON"]
    result = check_scpi(cmds, model="keithley-2400")
    assert not result.ok
    violations = [v for v in result.violations if v.violation_type == ViolationType.CURRENT_OVER]
    assert violations


def test_output_without_init_rejected():
    """Output activation without initialization should be rejected (Appendix D command-order rule)."""
    cmds = [":SOUR:VOLT 1.0", "OUTP ON", "READ?"]
    result = check_scpi(cmds, model="keithley-2400")
    assert not result.ok
    violations = [v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION]
    assert violations, "An order violation should be detected."


def test_output_after_init_passes():
    """Output activation after initialization should pass."""
    cmds = ["*RST", "*CLS", ":SOUR:VOLT 1.0", "OUTP ON", "READ?"]
    result = check_scpi(cmds, model="keithley-2400")
    # Within voltage limits, so should pass
    voltage_errs = [v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER]
    order_errs = [v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION]
    assert not order_errs, "There should be no order errors."
    assert not voltage_errs, "There should be no voltage errors."


def test_empty_commands_passes():
    """An empty command list should pass."""
    result = check_scpi([], model="generic")
    assert result.ok


def test_comment_lines_ignored():
    """Comment lines (starting with #) should not be treated as SCPI commands."""
    cmds = ["# this is a comment", "*RST", "OUTP ON"]
    result = check_scpi(cmds, model="generic")
    # Comment is ignored, so *RST then OUTP ON — order is OK
    order_errs = [v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION]
    assert not order_errs


# ---------------------------------------------------------------------------
# Python script text validation
# ---------------------------------------------------------------------------


def test_script_text_with_safe_voltage_passes():
    """A Python script with a safe voltage should pass."""
    script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write(":SOUR:VOLT 1.0")
instr.write("OUTP ON")
result = instr.query("READ?")
instr.write("OUTP OFF")
instr.write("*RST")
"""
    result = check_script(script, model="generic")
    # generic profile has no voltage limit → should pass
    assert result.ok


def test_script_text_with_unsafe_voltage_rejected():
    """A Python script with an over-limit voltage should be rejected."""
    script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write(":SOUR:VOLT 999.0")
instr.write("OUTP ON")
result = instr.query("READ?")
"""
    result = check_script(script, model="keithley-2400")
    assert not result.ok
    voltage_errs = [v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER]
    assert voltage_errs


# ---------------------------------------------------------------------------
# Custom profiles
# ---------------------------------------------------------------------------


def test_custom_profile_field_limit():
    """Validate a custom magnetic field limit profile."""
    profile = SafetyProfile(
        model="custom-magnet",
        max_field_t=1.0,
        requires_init=True,
    )
    checker = SafetyChecker(profile)
    # Over limit
    result_over = checker.check_scpi_sequence(["*RST", ":FIELD 2.5"])
    field_errs = [v for v in result_over.violations if v.violation_type == ViolationType.FIELD_OVER]
    assert field_errs

    # Within limit
    result_ok = checker.check_scpi_sequence(["*RST", ":FIELD 0.5"])
    field_errs_ok = [
        v for v in result_ok.violations if v.violation_type == ViolationType.FIELD_OVER
    ]
    assert not field_errs_ok


def test_sr830_profile_exists():
    """SR-830 profile should exist."""
    p = get_profile("sr830")
    assert p.model == "sr830"
    assert p.requires_init is True


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 1, domain 03)
# ---------------------------------------------------------------------------


class TestHigh1SemicolonChainingBypass:
    """HIGH-1: *RST;SOUR:VOLT 1000 must not bypass the voltage limit check."""

    def test_rst_semicolon_volt_over_limit_is_blocked(self):
        """'*RST; SOUR:VOLT 1000' on one physical line must be rejected (Keithley-2400 max=210V)."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(["*RST; SOUR:VOLT 1000"])
        assert not result.ok, (
            "Semicolon-chained '*RST; SOUR:VOLT 1000' was accepted — safety bypass present."
        )
        types = [v.violation_type for v in result.violations]
        assert ViolationType.VOLTAGE_OVER in types, f"Expected VOLTAGE_OVER violation, got: {types}"

    def test_cls_semicolon_volt_over_limit_is_blocked(self):
        """'*CLS; SOUR:VOLT 1000' must also be rejected."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(["*CLS; SOUR:VOLT 1000"])
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.VOLTAGE_OVER in types

    def test_rst_semicolon_output_on_order_violation_detected(self):
        """'*RST; OUTP ON' on one line: OUTP ON follows *RST on same line, order is satisfied."""
        # *RST initializes, so OUTP ON after it on the same semicolon-split list is valid.
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(["*RST; OUTP ON"])
        order_errs = [
            v for v in result.violations if v.violation_type == ViolationType.ORDER_VIOLATION
        ]
        assert not order_errs, (
            "Order should be satisfied: *RST (init) comes before OUTP ON on same line."
        )

    def test_normal_rst_then_volt_still_passes(self):
        """*RST and SOUR:VOLT 1.0 on separate lines still pass."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(["*RST", "SOUR:VOLT 1.0"])
        assert result.ok, result.summary()

    def test_semicolon_separated_two_volt_commands(self):
        """'SOUR:VOLT 1.0; SOUR:VOLT 500' must catch the second (over-limit) sub-command."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        # Need *RST first to avoid order errors
        result = checker.check_scpi_sequence(["*RST", "SOUR:VOLT 1.0; SOUR:VOLT 500"])
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.VOLTAGE_OVER in types


class TestMedium1Sr830SlvlCheck:
    """MEDIUM-1: SR830 SLVL command must be subject to the max_voltage_v limit."""

    def test_slvl_over_limit_rejected(self):
        """SLVL 10 must be rejected on SR830 (max_voltage_v=5.0)."""
        checker = SafetyChecker(get_profile("sr830"))
        result = checker.check_scpi_sequence(["*RST", "SLVL 10"])
        assert not result.ok, "SLVL 10 V exceeds SR830 5V limit but was accepted."
        types = [v.violation_type for v in result.violations]
        assert ViolationType.VOLTAGE_OVER in types

    def test_slvl_within_limit_passes(self):
        """SLVL 1.0 must be accepted on SR830."""
        checker = SafetyChecker(get_profile("sr830"))
        result = checker.check_scpi_sequence(["*RST", "SLVL 1.0"])
        volt_errs = [
            v
            for v in result.violations
            if v.violation_type in (ViolationType.VOLTAGE_OVER, ViolationType.VOLTAGE_UNDER)
        ]
        assert not volt_errs, f"SLVL 1.0 should be within SR830 limits, got: {volt_errs}"

    def test_slvl_at_limit_boundary_passes(self):
        """SLVL 5.0 (exactly at the limit) must be accepted."""
        checker = SafetyChecker(get_profile("sr830"))
        result = checker.check_scpi_sequence(["*RST", "SLVL 5.0"])
        volt_errs = [v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER]
        assert not volt_errs


class TestMedium3VoltRangFalsePositive:
    """MEDIUM-3: VOLT:RANG must not be treated as a voltage-value command."""

    def test_volt_rang_is_not_flagged_as_voltage_over_limit(self):
        """VOLT:RANG 10 (range selector, not output voltage) must not trigger VOLTAGE_OVER."""
        checker = SafetyChecker(get_profile("sr830"))
        result = checker.check_scpi_sequence(["*RST", "VOLT:RANG 10"])
        volt_over_errs = [
            v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER
        ]
        assert not volt_over_errs, (
            f"VOLT:RANG 10 was incorrectly flagged as a voltage violation: {volt_over_errs}"
        )

    def test_volt_rang_auto_is_not_flagged(self):
        """VOLT:RANG:AUTO must not trigger a voltage limit check."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(["*RST", "VOLT:RANG:AUTO 1"])
        volt_over_errs = [
            v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER
        ]
        assert not volt_over_errs


class TestLow3MultipleWritePerLine:
    """LOW-3: check_script_text must extract ALL .write() calls on the same source line."""

    def test_two_writes_on_same_line_both_checked(self):
        """Both SCPI commands on a single Python source line must be extracted and validated."""
        script = "instr.write('*RST'); instr.write('SOUR:VOLT 300')\n"
        result = check_script(script, model="keithley-2400")
        assert not result.ok, (
            "SOUR:VOLT 300 (over 210V limit) on the same line as *RST was not detected."
        )
        types = [v.violation_type for v in result.violations]
        assert ViolationType.VOLTAGE_OVER in types

    def test_two_safe_writes_on_same_line_pass(self):
        """Two safe .write() calls on the same line must both pass without false positives."""
        script = "instr.write('*RST'); instr.write('SOUR:VOLT 1.0')\n"
        result = check_script(script, model="keithley-2400")
        volt_errs = [v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER]
        assert not volt_errs


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 2, domain 03)
# ---------------------------------------------------------------------------


class TestR2Medium2OutputActiveParamGuard:
    """MEDIUM-2 (R2): Docstring rule #3 — parameter change while output is active must be rejected."""

    def test_volt_after_outp_on_is_rejected(self):
        """SOUR:VOLT after OUTP ON must emit OUTPUT_ACTIVE_PARAM_CHANGE (Appendix D rule #3)."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(["*RST", "SOUR:VOLT 100", "OUTP ON", "SOUR:VOLT 5"])
        assert not result.ok, (
            "SOUR:VOLT while output is active was accepted — Appendix D rule #3 not enforced."
        )
        types = [v.violation_type for v in result.violations]
        assert ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE in types, (
            f"Expected OUTPUT_ACTIVE_PARAM_CHANGE, got: {types}"
        )

    def test_curr_after_outp_on_is_rejected(self):
        """SOUR:CURR after OUTP ON must emit OUTPUT_ACTIVE_PARAM_CHANGE."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(
            ["*RST", "SOUR:CURR 0.001", "OUTP ON", "SOUR:CURR 0.0005"]
        )
        assert not result.ok
        types = [v.violation_type for v in result.violations]
        assert ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE in types

    def test_volt_before_outp_on_is_allowed(self):
        """SOUR:VOLT before OUTP ON (normal CONFIG phase) must not be flagged."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(
            ["*RST", "SOUR:VOLT 100", "OUTP ON", "READ?", "OUTP OFF"]
        )
        param_change_errs = [
            v
            for v in result.violations
            if v.violation_type == ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE
        ]
        assert not param_change_errs, (
            f"SOUR:VOLT before OUTP ON incorrectly flagged: {param_change_errs}"
        )

    def test_volt_after_outp_off_is_allowed(self):
        """SOUR:VOLT after OUTP OFF (output deactivated) must be allowed."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(
            ["*RST", "SOUR:VOLT 100", "OUTP ON", "READ?", "OUTP OFF", "SOUR:VOLT 50"]
        )
        param_change_errs = [
            v
            for v in result.violations
            if v.violation_type == ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE
        ]
        assert not param_change_errs, (
            f"SOUR:VOLT after OUTP OFF should be allowed, got: {param_change_errs}"
        )

    def test_volt_enum_value_exists(self):
        """OUTPUT_ACTIVE_PARAM_CHANGE must be a member of ViolationType."""
        assert hasattr(ViolationType, "OUTPUT_ACTIVE_PARAM_CHANGE")
        assert ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE == "output_active_param_change"


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 3, domain 03)
# ---------------------------------------------------------------------------


class TestR3Finding1ScriptDedup:
    """R3-F1 (HIGH): check_script_text must NOT deduplicate repeated SCPI commands.

    A command that appears once before OUTP ON (safe) and again after OUTP ON
    (unsafe) must trigger OUTPUT_ACTIVE_PARAM_CHANGE.  The old ``seen: set``
    deduplication silently dropped the second occurrence, making the gate miss
    the violation.
    """

    def test_repeated_volt_after_outp_on_is_flagged_in_script(self):
        """Same :SOUR:VOLT string appearing before and after OUTP ON must be rejected."""
        script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write(":SOUR:VOLT 1.0")
instr.write("OUTP ON")
instr.write(":SOUR:VOLT 1.0")
"""
        result = check_script(script, model="keithley-2400")
        assert not result.ok, (
            "Repeated ':SOUR:VOLT 1.0' after OUTP ON was not detected — "
            "deduplication may still be active."
        )
        types = [v.violation_type for v in result.violations]
        assert ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE in types, (
            f"Expected OUTPUT_ACTIVE_PARAM_CHANGE, got: {types}"
        )

    def test_repeated_curr_after_outp_on_is_flagged_in_script(self):
        """Same :SOUR:CURR string appearing before and after OUTP ON must be rejected."""
        script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write(":SOUR:CURR 0.001")
instr.write("OUTP ON")
instr.write(":SOUR:CURR 0.001")
"""
        result = check_script(script, model="keithley-2400")
        assert not result.ok, "Repeated ':SOUR:CURR 0.001' after OUTP ON was not detected."
        types = [v.violation_type for v in result.violations]
        assert ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE in types

    def test_volt_before_outp_on_only_passes(self):
        """A script where :SOUR:VOLT appears only before OUTP ON must pass."""
        script = """
import pyvisa
rm = pyvisa.ResourceManager()
instr = rm.open_resource("GPIB0::1::INSTR")
instr.write("*RST")
instr.write(":SOUR:VOLT 1.0")
instr.write("OUTP ON")
data = instr.query("READ?")
instr.write("OUTP OFF")
"""
        result = check_script(script, model="keithley-2400")
        param_errs = [
            v
            for v in result.violations
            if v.violation_type == ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE
        ]
        assert not param_errs, (
            f"Normal CONFIG-then-OUTP-ON pattern incorrectly flagged: {param_errs}"
        )


class TestR3Finding3CurrPrefixFalsePositive:
    """R3-F3 (MEDIUM): Bare CURR sub-commands must not trigger CURRENT_OVER violations."""

    def test_curr_comp_is_not_flagged_as_current_setpoint(self):
        """CURR:COMP (compliance limit) must NOT trigger CURRENT_OVER."""
        profile = SafetyProfile(model="test", max_current_a=1.0)
        checker = SafetyChecker(profile)
        result = checker.check_scpi_sequence(["*RST", "CURR:COMP 2.0"])
        curr_over = [v for v in result.violations if v.violation_type == ViolationType.CURRENT_OVER]
        assert not curr_over, (
            f"CURR:COMP 2.0 was incorrectly flagged as a current-over violation: {curr_over}"
        )

    def test_curr_rang_is_not_flagged_as_current_setpoint(self):
        """CURR:RANG (measurement range) must NOT trigger CURRENT_OVER."""
        profile = SafetyProfile(model="test", max_current_a=1.0)
        checker = SafetyChecker(profile)
        result = checker.check_scpi_sequence(["*RST", "CURR:RANG 5"])
        curr_over = [v for v in result.violations if v.violation_type == ViolationType.CURRENT_OVER]
        assert not curr_over, (
            f"CURR:RANG 5 was incorrectly flagged as a current-over violation: {curr_over}"
        )

    def test_sour_curr_genuine_setpoint_is_still_checked(self):
        """SOUR:CURR (genuine setpoint) must still be checked for limits."""
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_scpi_sequence(["*RST", ":SOUR:CURR 2.0"])
        curr_over = [v for v in result.violations if v.violation_type == ViolationType.CURRENT_OVER]
        assert curr_over, "Genuine SOUR:CURR over-limit was not detected."


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 4, domain 03)
# ---------------------------------------------------------------------------


class TestR4Finding4CompoundScpiLineNumbers:
    """R4-F4 (LOW): check_script_text must report the correct script line number
    for violations that arise from sub-commands within a compound semicolon-separated
    SCPI string (e.g. ``instr.write('OUTP ON; SOUR:VOLT 999')``).

    Previously, the violation line number was the cmd-list index (position in the
    extracted write-call list) rather than the actual 1-based script line number,
    because sub-commands produced by splitting on ';' were absent from lineno_map.
    """

    def test_compound_write_violation_reports_correct_line_number(self):
        """Violation arising from a compound .write() call must report the actual script line."""
        script = (
            "instr.write('*RST')\n"  # line 1
            "instr.write('*CLS')\n"  # line 2
            "instr.write('SENS:VOLT:RANG 1')\n"  # line 3
            "x = instr.query('*IDN?')\n"  # line 4
            "instr.write('OUTP ON; SOUR:VOLT 999')\n"  # line 5
        )
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_script_text(script)

        assert not result.ok, (
            "Compound SCPI with dangerous voltage ('SOUR:VOLT 999') was not detected."
        )

        # All violations must point to line 5 (the compound write), not to
        # the cmd-list index (which would be 4 for the 4th write call).
        for v in result.violations:
            assert v.line_number == 5, (
                f"Violation {v.violation_type!r} reported line {v.line_number}, "
                f"expected 5 (the compound instr.write line). command={v.command!r}"
            )

    def test_compound_write_output_active_param_change_correct_line(self):
        """OUTPUT_ACTIVE_PARAM_CHANGE from a compound .write() must report the actual script line."""
        script = (
            "instr.write('*RST')\n"  # line 1
            "instr.write('SOUR:VOLT 1.0')\n"  # line 2
            "instr.write('OUTP ON; SOUR:VOLT 5')\n"  # line 3
        )
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_script_text(script)

        assert not result.ok, (
            "Parameter change while output active (via compound write) was not detected."
        )
        param_errs = [
            v
            for v in result.violations
            if v.violation_type == ViolationType.OUTPUT_ACTIVE_PARAM_CHANGE
        ]
        assert param_errs, (
            "Expected OUTPUT_ACTIVE_PARAM_CHANGE but found none. "
            f"All violations: {[(v.violation_type, v.line_number) for v in result.violations]}"
        )
        for v in param_errs:
            assert v.line_number == 3, (
                f"OUTPUT_ACTIVE_PARAM_CHANGE reported line {v.line_number}, expected 3."
            )

    def test_simple_write_line_number_still_correct(self):
        """Non-compound .write() violations still report the correct line number."""
        script = (
            "instr.write('*RST')\n"  # line 1
            "instr.write(':SOUR:VOLT 500')\n"  # line 2
            "instr.write('OUTP ON')\n"  # line 3
        )
        checker = SafetyChecker(get_profile("keithley-2400"))
        result = checker.check_script_text(script)

        assert not result.ok, "Over-limit voltage was not detected."
        volt_errs = [v for v in result.violations if v.violation_type == ViolationType.VOLTAGE_OVER]
        assert volt_errs, "Expected VOLTAGE_OVER violation."
        for v in volt_errs:
            assert v.line_number == 2, f"VOLTAGE_OVER reported line {v.line_number}, expected 2."
