"""PyVISA backend skeleton generation — `instrument/scaffold.py`.

§13.1, T-P4-12: Generates a PyVISA connection skeleton Python file from an
instrument model name and interface type. This module does not open a VISA
session itself (code generation only).

Generated files include:
- Safety comment ("human executes")
- Initialization sequence (*RST → *CLS → *IDN?)
- Explicit safety.py pass-condition note
- Rendered output of Jinja2 templates/scaffold.py.j2
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

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
# Interface settings
# ---------------------------------------------------------------------------

# Interface → default VISA resource string pattern
_IFACE_RESOURCE: dict[str, str] = {
    "GPIB": "GPIB0::{gpib_addr}::INSTR",
    "USB": "USB0::0x{vendor_id:04X}::0x{product_id:04X}::INSTR",
    "TCPIP": "TCPIP0::{host}::INSTR",
    "SERIAL": "ASRL{port}::INSTR",
    "PXI": "PXI0::CHASSIS1::SLOT{slot}::INSTR",
}

_IFACE_DEFAULTS: dict[str, dict[str, Any]] = {
    "GPIB": {"gpib_addr": 1},
    "USB": {"vendor_id": 0x0957, "product_id": 0x0001},
    "TCPIP": {"host": "192.168.1.100"},
    "SERIAL": {"port": 1},
    "PXI": {"slot": 1},
}

_IFACE_BAUD: dict[str, int] = {
    "GPIB": 0,
    "USB": 0,
    "TCPIP": 0,
    "SERIAL": 9600,
    "PXI": 0,
}


def _model_to_class_name(model: str) -> str:
    """Convert a model name to a Python class name.

    E.g. "Keithley 2400" → "Keithley2400" | "SR-830" → "SR830"
    """
    cleaned = re.sub(r"[^A-Za-z0-9 ]", "", model)
    parts = cleaned.split()
    return "".join(p.capitalize() if not p[0].isdigit() else p for p in parts if p)


def _build_resource_string(iface: str, options: dict[str, Any]) -> str:
    """Build a VISA resource string from interface type and options."""
    iface_up = iface.upper()
    template = _IFACE_RESOURCE.get(iface_up, "GPIB0::1::INSTR")
    defaults = _IFACE_DEFAULTS.get(iface_up, {})
    merged = {**defaults, **options}
    try:
        return template.format(**merged)
    except (KeyError, ValueError):
        return template


# ---------------------------------------------------------------------------
# Skeleton generation function
# ---------------------------------------------------------------------------


def generate_scaffold(
    model: str,
    iface: str = "GPIB",
    output_path: Path | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """Generate a PyVISA backend skeleton Python file.

    §13.1: Does not open a VISA session — code generation only.
    The generated code must pass `maglab instr check` safety validation before execution.

    Args:
        model: Instrument model name (★ confirm with the user — never guess, §13.2).
        iface: Interface type (GPIB, USB, TCPIP, SERIAL, PXI).
        output_path: Path to save the generated file. Not saved when None.
        options: Resource string options (gpib_addr, host, etc.).

    Returns:
        Generated Python script text.

    Raises:
        jinja2.TemplateNotFound: When the template file is missing.
    """
    opts = options or {}
    resource_string = _build_resource_string(iface, opts)
    class_name = _model_to_class_name(model) or "GenericInstrument"
    gpib_addr = opts.get("gpib_addr", _IFACE_DEFAULTS.get(iface.upper(), {}).get("gpib_addr", 1))

    ctx: dict[str, Any] = {
        "model": model,
        "iface": iface.upper(),
        "resource_string": resource_string,
        "class_name": class_name,
        "timeout_ms": 10000,
        "baud_rate": _IFACE_BAUD.get(iface.upper(), 9600),
        "gpib_addr": gpib_addr,
        "timestamp": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }

    env = _get_jinja_env()
    template = env.get_template("scaffold.py.j2")
    code = template.render(**ctx)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code, encoding="utf-8")

    return code
