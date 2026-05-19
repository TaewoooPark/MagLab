"""Virtual instrument — `instrument/mock.py`.

§13.1, §13.4, T-P4-15: A virtual instrument that mimics the PyVISA interface
without real hardware. Used in Loop B pytest dry-runs and unit tests.

Response patterns are configured per model via MockProfile.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Mock profiles
# ---------------------------------------------------------------------------


@dataclass
class MockResponse:
    """Mock response for a single SCPI command."""

    command_pattern: str
    """Regex pattern to match (case-insensitive)."""
    response: str | None = None
    """Fixed response string. When None, returns a noisy float value."""
    noise_amplitude: float = 0.0
    """Gaussian noise amplitude (used when response is None)."""
    base_value: float = 0.0
    """Base value for the noisy response."""
    delay_s: float = 0.0
    """Response delay in seconds."""


@dataclass
class MockProfile:
    """Per-model mock profile for a virtual instrument."""

    model: str
    idn_response: str
    responses: list[MockResponse] = field(default_factory=list)
    # No default response for write commands (None)
    default_write_response: str | None = None
    # Default response for unknown queries
    default_query_response: str = "0.0"


# ---------------------------------------------------------------------------
# Built-in mock profiles
# ---------------------------------------------------------------------------

_SR830_PROFILE = MockProfile(
    model="sr830",
    idn_response="Stanford_Research_Systems,SR830,s/n00000,ver1.07",
    responses=[
        MockResponse(r"OUTP\?\s*1", response=None, noise_amplitude=1e-7, base_value=1e-6),
        MockResponse(r"OUTP\?\s*2", response=None, noise_amplitude=5e-8, base_value=0.0),
        MockResponse(r"SNAP\?", response=None, noise_amplitude=1e-7, base_value=1e-6),
        MockResponse(r"SENS\s+\d+", response=None),
        MockResponse(r"FREQ\s+", response=None),
        MockResponse(r"PHAS\s+", response=None),
        MockResponse(r"OAUX\?\s*\d", response=None, noise_amplitude=0.01, base_value=0.0),
    ],
)

_KEITHLEY2400_PROFILE = MockProfile(
    model="keithley-2400",
    idn_response="KEITHLEY INSTRUMENTS INC.,MODEL 2400,0000000,C32 Dec 07 2005 15:59:00/A02 /J",
    responses=[
        MockResponse(r"MEAS:VOLT\?", response=None, noise_amplitude=1e-5, base_value=1.0),
        MockResponse(r"MEAS:CURR\?", response=None, noise_amplitude=1e-9, base_value=1e-6),
        MockResponse(r"READ\?", response=None, noise_amplitude=1e-5, base_value=1.0),
        MockResponse(r":SOUR:VOLT", response=None),
        MockResponse(r":SOUR:CURR", response=None),
        MockResponse(r"OUTP\s+ON", response=None),
        MockResponse(r"OUTP\s+OFF", response=None),
    ],
)

_KEITHLEY2182_PROFILE = MockProfile(
    model="keithley-2182",
    idn_response="KEITHLEY INSTRUMENTS INC.,MODEL 2182,0000000,B04",
    responses=[
        MockResponse(r"SENS:VOLT:CHAN1:RANG:AUTO", response=None),
        MockResponse(r"READ\?", response=None, noise_amplitude=1e-7, base_value=1e-3),
    ],
)

_BUILTIN_MOCK_PROFILES: dict[str, MockProfile] = {
    "sr830": _SR830_PROFILE,
    "sr-830": _SR830_PROFILE,
    "keithley-2400": _KEITHLEY2400_PROFILE,
    "keithley 2400": _KEITHLEY2400_PROFILE,
    "keithley-2182": _KEITHLEY2182_PROFILE,
    "generic": MockProfile(
        model="generic",
        idn_response="Mock Instrument,Generic,SN000,FW1.0",
    ),
}


def get_mock_profile(model_key: str) -> MockProfile:
    """Look up a mock profile by model key; falls back to the generic profile."""
    key = model_key.lower().replace(" ", "-")
    return _BUILTIN_MOCK_PROFILES.get(key, _BUILTIN_MOCK_PROFILES["generic"])


# ---------------------------------------------------------------------------
# Virtual resource (PyVISA Resource emulation)
# ---------------------------------------------------------------------------


class MockResource:
    """Virtual resource that emulates pyvisa.resources.Resource.

    Handles write/query/read without a real VISA connection.
    """

    def __init__(self, profile: MockProfile, resource_string: str = "MOCK::0::INSTR") -> None:
        """Initialize the virtual resource.

        Args:
            profile: Mock profile to use.
            resource_string: Resource string (for identification only).
        """
        self._profile = profile
        self.resource_name = resource_string
        self.timeout = 10000
        self._last_command: str = ""
        self._log: list[tuple[str, str, str]] = []  # (type, command, response)

    def write(self, cmd: str) -> None:
        """Send an SCPI command (mock — no response)."""
        self._last_command = cmd
        self._log.append(("write", cmd, ""))

    def query(self, cmd: str) -> str:
        """Send an SCPI command and return the response (mock)."""
        self._last_command = cmd
        response = self._generate_response(cmd)
        self._log.append(("query", cmd, response))
        return response

    def read(self) -> str:
        """Read the response for the last command (mock)."""
        return self._generate_response(self._last_command)

    def close(self) -> None:
        """Close the resource."""
        pass

    def _generate_response(self, cmd: str) -> str:
        """Generate a mock response for a command."""
        cmd_up = cmd.strip().upper()

        # IDN query
        if "*IDN?" in cmd_up:
            return self._profile.idn_response

        # Match profile responses
        for resp_def in self._profile.responses:
            if re.search(resp_def.command_pattern, cmd, re.IGNORECASE):
                if resp_def.delay_s > 0:
                    time.sleep(resp_def.delay_s)
                if resp_def.response is not None:
                    return resp_def.response
                # Generate noisy float value
                value = resp_def.base_value + random.gauss(0.0, resp_def.noise_amplitude or 1e-10)
                return f"{value:.6E}"

        # Default response
        if "?" in cmd:
            return self._profile.default_query_response
        return self._profile.default_write_response or ""

    @property
    def command_log(self) -> list[tuple[str, str, str]]:
        """Return the command log as a list of (type, command, response) tuples."""
        return list(self._log)


# ---------------------------------------------------------------------------
# Virtual resource manager (pyvisa.ResourceManager emulation)
# ---------------------------------------------------------------------------


class MockResourceManager:
    """Virtual resource manager that emulates pyvisa.ResourceManager.

    Used in tests as a drop-in replacement for pyvisa.ResourceManager().
    """

    def __init__(self, default_model: str = "generic") -> None:
        """Initialize the virtual resource manager.

        Args:
            default_model: Default mock profile model key.
        """
        self._default_model = default_model
        self._profiles: dict[str, MockProfile] = {}
        self._resources: dict[str, MockResource] = {}

    def register_profile(self, resource_string: str, profile: MockProfile) -> None:
        """Register a mock profile for a specific resource string.

        Args:
            resource_string: VISA resource string pattern.
            profile: Mock profile to use.
        """
        self._profiles[resource_string] = profile

    def open_resource(self, resource_string: str) -> MockResource:
        """Open and return a virtual resource.

        Args:
            resource_string: VISA resource string.

        Returns:
            MockResource instance.
        """
        profile = self._profiles.get(
            resource_string,
            get_mock_profile(self._default_model),
        )
        resource = MockResource(profile, resource_string)
        self._resources[resource_string] = resource
        return resource

    def list_resources(self) -> tuple[str, ...]:
        """Return the list of opened resources."""
        return tuple(self._resources.keys())

    def close(self) -> None:
        """Close the manager."""
        pass


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------


def make_mock_resource(model: str = "generic") -> MockResource:
    """Quickly create a mock resource by model name.

    Args:
        model: Instrument model key.

    Returns:
        MockResource instance.
    """
    profile = get_mock_profile(model)
    return MockResource(profile, f"MOCK::{model.upper()}::INSTR")


def make_mock_manager(model: str = "generic") -> MockResourceManager:
    """Create a mock resource manager by model name.

    Args:
        model: Default model key.

    Returns:
        MockResourceManager instance.
    """
    return MockResourceManager(default_model=model)
