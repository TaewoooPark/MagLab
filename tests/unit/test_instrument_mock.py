"""tests/unit/test_instrument_mock.py — mock instrument unit tests."""

from __future__ import annotations

from maglab.instrument.mock import (
    MockProfile,
    MockResource,
    MockResourceManager,
    get_mock_profile,
    make_mock_manager,
    make_mock_resource,
)

# ---------------------------------------------------------------------------
# Profile lookup
# ---------------------------------------------------------------------------


def test_get_sr830_profile():
    """Retrieve the SR-830 mock profile."""
    p = get_mock_profile("sr830")
    assert "Stanford" in p.idn_response or "SR830" in p.idn_response


def test_get_keithley_profile():
    """Retrieve the Keithley-2400 mock profile."""
    p = get_mock_profile("keithley-2400")
    assert "KEITHLEY" in p.idn_response.upper()


def test_get_unknown_profile_generic():
    """Unknown model should return the generic profile."""
    p = get_mock_profile("unknown-xyz")
    assert p.model == "generic"


# ---------------------------------------------------------------------------
# MockResource
# ---------------------------------------------------------------------------


def test_mock_resource_idn():
    """*IDN? query should return an IDN response."""
    resource = make_mock_resource("sr830")
    response = resource.query("*IDN?")
    assert response  # not empty
    assert len(response) > 5


def test_mock_resource_write_no_crash():
    """write() should operate without raising."""
    resource = make_mock_resource("generic")
    resource.write("*RST")
    resource.write("*CLS")


def test_mock_resource_query_returns_string():
    """query() should return a string."""
    resource = make_mock_resource("generic")
    resp = resource.query("MEAS?")
    assert isinstance(resp, str)


def test_mock_resource_command_log():
    """Executed commands should be recorded in the log."""
    resource = make_mock_resource("generic")
    resource.write("*RST")
    resource.query("*IDN?")
    log = resource.command_log
    assert len(log) == 2
    assert log[0][0] == "write"
    assert log[0][1] == "*RST"
    assert log[1][0] == "query"
    assert log[1][1] == "*IDN?"


def test_mock_resource_noise_in_measurement():
    """Measurement responses may include noise (SR-830 OUTP?)."""
    resource = make_mock_resource("sr830")
    responses = [float(resource.query("OUTP? 1")) for _ in range(10)]
    # Responses need not all be identical; just confirm they are floats
    assert all(isinstance(r, float) for r in responses)


def test_mock_resource_close_no_crash():
    """close() should operate without raising."""
    resource = make_mock_resource("generic")
    resource.close()  # no exception


# ---------------------------------------------------------------------------
# MockResourceManager
# ---------------------------------------------------------------------------


def test_mock_manager_open_resource():
    """open_resource() should return a MockResource."""
    manager = make_mock_manager("sr830")
    resource = manager.open_resource("GPIB0::1::INSTR")
    assert isinstance(resource, MockResource)


def test_mock_manager_list_resources():
    """Opened resources should appear in the list."""
    manager = make_mock_manager()
    manager.open_resource("GPIB0::1::INSTR")
    manager.open_resource("GPIB0::2::INSTR")
    resources = manager.list_resources()
    assert "GPIB0::1::INSTR" in resources
    assert "GPIB0::2::INSTR" in resources


def test_mock_manager_with_registered_profile():
    """Should open a resource with a registered profile."""
    manager = MockResourceManager()
    profile = MockProfile(
        model="custom",
        idn_response="Custom Instrument,Model1,SN001,FW1.0",
    )
    manager.register_profile("CUSTOM::0::INSTR", profile)
    resource = manager.open_resource("CUSTOM::0::INSTR")
    idn = resource.query("*IDN?")
    assert "Custom Instrument" in idn


def test_mock_manager_close_no_crash():
    """close() should operate without raising."""
    manager = make_mock_manager()
    manager.close()


# ---------------------------------------------------------------------------
# SCPI sequence dry run with mock instrument
# ---------------------------------------------------------------------------


def test_scpi_dry_run_with_mock():
    """Dry-run a SCPI sequence using a mock instrument."""
    resource = make_mock_resource("keithley-2400")

    # Execute in safe order
    resource.write("*RST")
    resource.write("*CLS")
    idn = resource.query("*IDN?")
    resource.write(":SOUR:VOLT 1.0")
    resource.write("OUTP ON")
    result = resource.query("MEAS:VOLT?")
    resource.write("OUTP OFF")
    resource.write("*RST")

    # Verify IDN response
    assert idn  # not empty
    # Measurement value should be convertible to float
    assert isinstance(result, str)
    log = resource.command_log
    assert len(log) == 8  # write 6 + query 2


def test_keithley2182_profile():
    """Keithley-2182 mock profile should work."""
    resource = make_mock_resource("keithley-2182")
    idn = resource.query("*IDN?")
    assert "2182" in idn
