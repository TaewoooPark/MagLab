"""tests/unit/test_instrument_script.py — measurement script generation unit tests."""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path

import pytest

from maglab.instrument.script import (
    ScriptConfig,
    ScriptGenerator,
    SweepConfig,
    generate_measurement_script,
)

# ---------------------------------------------------------------------------
# ScriptConfig
# ---------------------------------------------------------------------------


def test_script_config_defaults():
    """ScriptConfig defaults should be valid."""
    config = ScriptConfig(model="SR830", description="lock-in measurement")
    assert config.model == "SR830"
    assert config.iface == "GPIB"
    assert config.sweep.start == 0.0
    assert config.sweep.stop == 1.0


# ---------------------------------------------------------------------------
# ScriptGenerator
# ---------------------------------------------------------------------------


def test_script_generator_returns_code_and_result():
    """generate() should return a (code, SafetyCheckResult) tuple."""
    gen = ScriptGenerator()
    config = ScriptConfig(
        model="SR830",
        description="SR830 first harmonic measurement",
        iface="GPIB",
    )
    code, safety = gen.generate(config)
    assert isinstance(code, str)
    assert len(code) > 100
    # generic profile → should pass
    assert safety.ok


def test_script_contains_model_name():
    """Generated script should contain the model name."""
    code, _ = generate_measurement_script(
        model="SR830",
        description="measurement test",
    )
    assert "SR830" in code


def test_script_contains_safety_comment():
    """Generated script should contain the safety comment."""
    code, _ = generate_measurement_script(
        model="SR830",
        description="measurement test",
    )
    assert "Tier 3" in code


def test_script_valid_python_syntax():
    """Generated script should be valid Python syntax."""
    code, _ = generate_measurement_script(
        model="SR830",
        description="measurement test",
    )
    tree = ast.parse(code)
    assert tree is not None


def test_script_sweep_parameters_in_code():
    """Sweep parameters should be reflected in the script."""
    code, _ = generate_measurement_script(
        model="SR830",
        description="sweep measurement",
        sweep_start=0.0,
        sweep_stop=10.0,
        sweep_step=1.0,
    )
    # Values should be present in code
    assert "0.0" in code
    assert "10.0" in code or "10" in code


def test_script_save_to_file_when_safe():
    """File should be saved when safety validation passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_script.py"
        gen = ScriptGenerator()
        config = ScriptConfig(model="SR830", description="save test")
        code, safety = gen.generate(config, output_path=out)
        # generic profile → passes → file saved
        if safety.ok:
            assert out.is_file()
            content = out.read_text(encoding="utf-8")
            assert content == code


def test_script_skip_safety_check():
    """With skip_safety_check=True, code should be returned without safety validation."""
    gen = ScriptGenerator()
    config = ScriptConfig(model="SR830", description="skip validation")
    code, safety = gen.generate(config, skip_safety_check=True)
    assert isinstance(code, str)
    assert safety.ok  # always passes


def test_generate_measurement_script_convenience():
    """generate_measurement_script() convenience function should work."""
    code, safety = generate_measurement_script(
        model="Keithley 2400",
        description="IV characteristic measurement",
        iface="GPIB",
        sweep_start=0.0,
        sweep_stop=1.0,
        sweep_step=0.1,
    )
    assert isinstance(code, str)
    assert "Keithley 2400" in code


def test_generate_with_output_csv():
    """Output CSV filename should be reflected in the script."""
    code, _ = generate_measurement_script(
        model="SR830",
        description="CSV path test",
        output_csv="my_data.csv",
    )
    assert "my_data.csv" in code


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 2, domain 03)
# ---------------------------------------------------------------------------


class TestR2Low1SweepConfigZeroStep:
    """LOW-1 (R2): SweepConfig.step=0.0 must be rejected by the Pydantic validator."""

    def test_step_zero_raises_value_error(self):
        """SweepConfig(step=0.0) must raise a ValueError (or ValidationError wrapping it)."""
        from pydantic import ValidationError

        with pytest.raises((ValueError, ValidationError)):
            SweepConfig(step=0.0)

    def test_step_nonzero_positive_accepted(self):
        """SweepConfig(step=0.1) must be accepted."""
        cfg = SweepConfig(step=0.1)
        assert cfg.step == pytest.approx(0.1)

    def test_step_nonzero_negative_accepted(self):
        """SweepConfig(step=-0.1) must be accepted (negative step is valid for reverse sweeps)."""
        cfg = SweepConfig(step=-0.1)
        assert cfg.step == pytest.approx(-0.1)

    def test_sweep_config_default_step_is_nonzero(self):
        """The default step (0.1) must not be zero and must be accepted by the validator."""
        cfg = SweepConfig()
        assert cfg.step != 0.0

    def test_script_config_with_zero_step_raises(self):
        """ScriptConfig with a zero sweep step must also be rejected."""
        from pydantic import ValidationError

        with pytest.raises((ValueError, ValidationError)):
            ScriptConfig(
                model="SR830",
                description="zero step test",
                sweep=SweepConfig(step=0.0),
            )
