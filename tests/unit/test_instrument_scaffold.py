"""tests/unit/test_instrument_scaffold.py — PyVISA skeleton generation unit tests."""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path

from maglab.instrument.scaffold import (
    _build_resource_string,
    _model_to_class_name,
    generate_scaffold,
)

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def test_model_to_class_name_basic():
    """Convert a model name to a Python class name."""
    assert _model_to_class_name("Keithley 2400") == "Keithley2400"


def test_model_to_class_name_with_dash():
    """Remove hyphens and special characters during conversion."""
    name = _model_to_class_name("SR-830")
    assert "830" in name


def test_build_resource_string_gpib():
    """Generate a GPIB interface resource string."""
    rs = _build_resource_string("GPIB", {"gpib_addr": 5})
    assert "GPIB" in rs
    assert "5" in rs


def test_build_resource_string_tcpip():
    """Generate a TCPIP interface resource string."""
    rs = _build_resource_string("TCPIP", {"host": "192.168.1.1"})
    assert "TCPIP" in rs
    assert "192.168.1.1" in rs


def test_build_resource_string_unknown_iface():
    """Unknown interface should return a default value."""
    rs = _build_resource_string("UNKNOWN", {})
    assert rs  # not empty


# ---------------------------------------------------------------------------
# generate_scaffold
# ---------------------------------------------------------------------------


def test_generate_scaffold_returns_string():
    """generate_scaffold should return a string."""
    code = generate_scaffold("Keithley 2400", iface="GPIB")
    assert isinstance(code, str)
    assert len(code) > 100


def test_generate_scaffold_contains_model_name():
    """Generated code should contain the model name."""
    code = generate_scaffold("SR830", iface="GPIB")
    assert "SR830" in code


def test_generate_scaffold_contains_safety_comment():
    """Generated code should contain the safety comment."""
    code = generate_scaffold("Keithley 2400", iface="GPIB")
    assert "Tier 3" in code


def test_generate_scaffold_contains_rst_cls():
    """Generated code should contain the initialization sequence (*RST, *CLS)."""
    code = generate_scaffold("Keithley 2400", iface="GPIB")
    assert "*RST" in code
    assert "*CLS" in code


def test_generate_scaffold_valid_python_syntax():
    """Generated code should be valid Python syntax."""
    code = generate_scaffold("Keithley 2400", iface="GPIB")
    # Verify no syntax errors with ast.parse
    tree = ast.parse(code)
    assert tree is not None


def test_generate_scaffold_saves_to_file():
    """When output_path is specified, the file should be saved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_driver.py"
        code = generate_scaffold("Keithley 2400", iface="GPIB", output_path=out)
        assert out.is_file()
        content = out.read_text(encoding="utf-8")
        assert content == code


def test_generate_scaffold_usb_interface():
    """Generate a skeleton for USB interface."""
    code = generate_scaffold("Keithley 2400", iface="USB")
    assert isinstance(code, str)
    assert "USB" in code


def test_generate_scaffold_gpib_addr_in_resource():
    """GPIB address should be included in the resource string."""
    code = generate_scaffold("Keithley 2400", iface="GPIB", options={"gpib_addr": 22})
    assert "22" in code


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 3)
# ---------------------------------------------------------------------------


class TestR3Finding5NumericModelName:
    """R3-F5 (MEDIUM): Digit-starting model names must produce valid Python class names.

    The old implementation returned '2400' verbatim, causing the Jinja2
    template to emit ``class 2400:`` which is a SyntaxError.
    """

    def test_pure_numeric_model_name_is_valid_identifier(self):
        """'2400' must not produce a digit-starting class name."""
        name = _model_to_class_name("2400")
        assert name.isidentifier(), f"Class name {name!r} is not a valid Python identifier."
        assert not name[0].isdigit(), f"Class name {name!r} still starts with a digit."

    def test_pure_numeric_class_name_has_prefix(self):
        """'2400' must produce 'Instr2400' (Instr prefix applied)."""
        name = _model_to_class_name("2400")
        assert name == "Instr2400", f"Expected 'Instr2400', got {name!r}"

    def test_digit_model_name_2182a_is_valid_identifier(self):
        """'2182A' must produce a valid Python identifier (Instr2182A)."""
        name = _model_to_class_name("2182A")
        assert name.isidentifier(), f"Class name {name!r} is not a valid Python identifier."
        assert name == "Instr2182A", f"Expected 'Instr2182A', got {name!r}"

    def test_alpha_prefix_model_no_instr_prefix_added(self):
        """'SR830' (letter-starting) must NOT get the 'Instr' prefix."""
        name = _model_to_class_name("SR830")
        assert not name.startswith("Instr"), (
            f"Letter-starting model 'SR830' incorrectly got Instr prefix: {name!r}"
        )
        assert name.isidentifier(), f"Class name {name!r} is not a valid identifier."

    def test_keithley_2400_mixed_no_instr_prefix(self):
        """'Keithley 2400' must NOT get the 'Instr' prefix (starts with letter)."""
        name = _model_to_class_name("Keithley 2400")
        assert not name.startswith("Instr"), (
            f"'Keithley 2400' incorrectly got Instr prefix: {name!r}"
        )
        assert "2400" in name, f"Model number '2400' not present in class name: {name!r}"

    def test_numeric_scaffold_generates_valid_python(self):
        """generate_scaffold('2400') must produce syntactically valid Python."""
        code = generate_scaffold("2400", iface="GPIB")
        tree = ast.parse(code)
        assert tree is not None, "Generated code for model '2400' is not valid Python."

    def test_numeric_scaffold_does_not_contain_invalid_class(self):
        """generate_scaffold('2400') must not emit 'class 2400:'."""
        code = generate_scaffold("2400", iface="GPIB")
        assert "class 2400:" not in code, (
            "Generated code contains 'class 2400:' — invalid Python class name."
        )
