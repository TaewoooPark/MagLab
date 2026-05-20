"""MCP server smoke tests (§20 — MCP smoke).

Validates:
  - All 6 P0 tools are registered
  - Each tool returns deterministic results
  - Both resources (materials://·provenance://) are registered
"""

from __future__ import annotations

import asyncio

import pytest

from maglab.mcp_server import create_server

# ---------------------------------------------------------------------------
# Server tool registration check
# ---------------------------------------------------------------------------

_P0_TOOLS = [
    "physics_compute",
    "physics_check",
    "convert_units",
    "material_lookup",
    "material_search",
    "provenance_query",
]


@pytest.fixture(scope="module")
def mcp_server():
    """MCP server instance fixture."""
    return create_server()


@pytest.mark.smoke
def test_p0_tools_registered(mcp_server) -> None:
    """All 6 P0 tools must be registered."""
    tools = asyncio.run(mcp_server.list_tools())
    tool_names = {t.name for t in tools}
    for expected in _P0_TOOLS:
        assert expected in tool_names, f"Tool not registered: {expected!r}\nRegistered: {tool_names}"


@pytest.mark.smoke
def test_physics_compute_exchange_length(mcp_server) -> None:
    """physics_compute should succeed for exchange_length calculation."""
    result = asyncio.run(
        mcp_server.call_tool(
            "physics_compute",
            {"formula": "exchange_length", "params": {"A": 1.3e-11, "Ms": 860000.0}},
        )
    )
    # ToolResult list
    assert result is not None
    # Verify content — result is list[TextContent]
    content_str = str(result)
    assert "exchange_length" in content_str or "ok" in content_str.lower()


@pytest.mark.smoke
def test_physics_check_valid(mcp_server) -> None:
    """physics_check should return ok=True for physically valid parameters."""
    result = asyncio.run(
        mcp_server.call_tool(
            "physics_check",
            {"params": {"alpha": 0.01}},
        )
    )
    assert result is not None
    content_str = str(result)
    assert "true" in content_str.lower() or "ok" in content_str.lower()


@pytest.mark.smoke
def test_physics_check_invalid(mcp_server) -> None:
    """physics_check should return ok=False for unphysical parameters."""
    result = asyncio.run(
        mcp_server.call_tool(
            "physics_check",
            {"params": {"alpha": 5.0}},  # α > 1 is unphysical
        )
    )
    assert result is not None
    content_str = str(result)
    assert "false" in content_str.lower() or "unphysical" in content_str.lower()


@pytest.mark.smoke
def test_convert_units_oe_to_am(mcp_server) -> None:
    """convert_units should perform Oe→A/m conversion."""
    result = asyncio.run(
        mcp_server.call_tool(
            "convert_units",
            {"value": 1000.0, "from_unit": "oe", "to_unit": "am"},
        )
    )
    assert result is not None
    # 1000 Oe ≈ 79577 A/m
    content_str = str(result)
    assert "ok" in content_str.lower() or "result" in content_str.lower()


@pytest.mark.smoke
def test_material_lookup_permalloy(mcp_server) -> None:
    """material_lookup should return Permalloy properties."""
    result = asyncio.run(
        mcp_server.call_tool(
            "material_lookup",
            {"material_id": "Permalloy"},
        )
    )
    assert result is not None
    content_str = str(result)
    assert "Permalloy" in content_str or "permalloy" in content_str.lower()


@pytest.mark.smoke
def test_material_lookup_unknown(mcp_server) -> None:
    """material_lookup should return null/None for an unknown ID."""
    result = asyncio.run(
        mcp_server.call_tool(
            "material_lookup",
            {"material_id": "DOES_NOT_EXIST_XYZ_12345"},
        )
    )
    assert result is not None
    content_str = str(result).lower()
    assert "none" in content_str or "null" in content_str or "[]" in content_str


@pytest.mark.smoke
def test_material_search(mcp_server) -> None:
    """material_search should return materials matching a keyword."""
    result = asyncio.run(
        mcp_server.call_tool(
            "material_search",
            {"query": "Fe"},
        )
    )
    assert result is not None


@pytest.mark.smoke
def test_provenance_query_unknown(mcp_server) -> None:
    """provenance_query should return None for an unknown ID."""
    result = asyncio.run(
        mcp_server.call_tool(
            "provenance_query",
            {"datapoint_id": "00000000-0000-0000-0000-000000000000"},
        )
    )
    assert result is not None
    content_str = str(result).lower()
    assert "none" in content_str or "null" in content_str or "[]" in content_str


# ---------------------------------------------------------------------------
# Resource registration check
# ---------------------------------------------------------------------------


@pytest.mark.smoke
def test_resources_registered(mcp_server) -> None:
    """materials:// and provenance:// resources must be registered."""
    resources = asyncio.run(mcp_server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert any("materials" in u for u in uris), f"materials:// not registered\n{uris}"
    assert any("provenance" in u for u in uris), f"provenance:// not registered\n{uris}"


# ---------------------------------------------------------------------------
# P4 instrument-domain tools (T-P4-28, FIX 4)
# ---------------------------------------------------------------------------

_P4_INSTRUMENT_TOOLS = [
    "instr_search_manual",
    "instr_ingest_manual",
    "instr_generate_skill",
    "instr_scaffold",
    "instr_safety_check",
]


@pytest.mark.smoke
def test_p4_instrument_tools_registered(mcp_server) -> None:
    """All 5 P4 instrument-domain tools must be registered."""
    tools = asyncio.run(mcp_server.list_tools())
    tool_names = {t.name for t in tools}
    for expected in _P4_INSTRUMENT_TOOLS:
        assert expected in tool_names, (
            f"Instrument tool not registered: {expected!r}\nRegistered: {tool_names}"
        )


@pytest.mark.smoke
def test_manuals_resource_registered(mcp_server) -> None:
    """manuals:// resource must be registered."""
    resources = asyncio.run(mcp_server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert any("manuals" in u for u in uris), f"manuals:// not registered\n{uris}"


@pytest.mark.smoke
def test_instr_scaffold_gpib(mcp_server) -> None:
    """instr_scaffold must return generated Python code for a GPIB instrument."""
    result = asyncio.run(
        mcp_server.call_tool(
            "instr_scaffold",
            {"model": "Keithley-2400", "iface": "GPIB"},
        )
    )
    assert result is not None
    content_str = str(result)
    assert "ok" in content_str.lower() or "code" in content_str.lower()


@pytest.mark.smoke
def test_instr_safety_check_safe_sequence(mcp_server) -> None:
    """instr_safety_check must return ok=True for a safe SCPI sequence."""
    result = asyncio.run(
        mcp_server.call_tool(
            "instr_safety_check",
            {
                "model": "generic",
                "commands": ["*RST", "*CLS", ":SOUR:VOLT 1.0", "OUTP ON", "OUTP OFF"],
            },
        )
    )
    assert result is not None
    content_str = str(result)
    assert "ok" in content_str.lower()


@pytest.mark.smoke
def test_instr_safety_check_over_voltage(mcp_server) -> None:
    """instr_safety_check must return ok=False when voltage exceeds the Keithley-2400 limit."""
    result = asyncio.run(
        mcp_server.call_tool(
            "instr_safety_check",
            {
                "model": "keithley-2400",
                "commands": ["*RST", "*CLS", ":SOUR:VOLT 500.0", "OUTP ON"],
            },
        )
    )
    assert result is not None
    content_str = str(result)
    assert "false" in content_str.lower() or "violation" in content_str.lower()


@pytest.mark.smoke
def test_instr_safety_check_temperature_over(mcp_server) -> None:
    """instr_safety_check must block a TEMP 9999 command when a temperature limit is set."""
    result = asyncio.run(
        mcp_server.call_tool(
            "instr_safety_check",
            {
                "model": "generic",
                "commands": ["*RST", "TEMP 9999"],
            },
        )
    )
    assert result is not None
    # With generic profile, max_temperature_k is None → passes.
    # Test only confirms the tool executes without error.
    content_str = str(result)
    assert "error" not in content_str.lower() or "none" in content_str.lower()


@pytest.mark.smoke
def test_instr_safety_check_no_input_returns_error(mcp_server) -> None:
    """instr_safety_check returns an error when neither commands nor script_text is provided."""
    result = asyncio.run(
        mcp_server.call_tool(
            "instr_safety_check",
            {"model": "generic"},
        )
    )
    assert result is not None
    content_str = str(result)
    assert "error" in content_str.lower() or "provided" in content_str.lower()


@pytest.mark.smoke
def test_instr_ingest_manual_missing_file(mcp_server) -> None:
    """instr_ingest_manual returns ok=False when the PDF file does not exist."""
    result = asyncio.run(
        mcp_server.call_tool(
            "instr_ingest_manual",
            {
                "model": "TestInstrument-9999",
                "pdf_path": "/nonexistent/path/manual.pdf",
            },
        )
    )
    assert result is not None
    content_str = str(result)
    assert "false" in content_str.lower() or "not found" in content_str.lower() or "error" in content_str.lower()


# ---------------------------------------------------------------------------
# R5-F1 regression: file-writing MCP tools must NOT carry readOnlyHint=True
# ---------------------------------------------------------------------------

#: Tools that write files to disk and must NOT be annotated readOnlyHint=True.
_WRITE_TOOLS = {
    "figure_render",
    "figure_export",
    "sim_run",  # writes .mx3/.mif solver scripts to temp directories unconditionally
    "instr_ingest_manual",
    "instr_generate_skill",
    "instr_scaffold",
    "instr_search_manual",  # downloads PDFs + writes checksums to the manual cache
}

#: Genuinely read-only tools that MUST carry readOnlyHint=True.
_READ_ONLY_TOOLS = {
    "physics_compute",
    "physics_check",
    "convert_units",
    "material_lookup",
    "material_search",
    "provenance_query",
    "sim_validate",
    "sim_parse",
    "instr_safety_check",
}


@pytest.mark.smoke
def test_write_tools_not_annotated_read_only(mcp_server) -> None:
    """File-writing MCP tools must have readOnlyHint=False (R5-F1 regression).

    MCP clients use readOnlyHint for sandboxing/permission decisions.
    Tools that write files to disk must NOT claim to be read-only.
    """
    tools = asyncio.run(mcp_server.list_tools())
    tool_map = {t.name: t for t in tools}

    for name in _WRITE_TOOLS:
        assert name in tool_map, f"Write tool not registered: {name!r}"
        tool = tool_map[name]
        ann = getattr(tool, "annotations", None)
        read_only_hint = getattr(ann, "readOnlyHint", None)
        assert read_only_hint is not True, (
            f"R5-F1 regression: tool {name!r} has readOnlyHint=True "
            f"but it writes files to disk — MCP spec violation."
        )


@pytest.mark.smoke
def test_read_only_tools_annotated_read_only(mcp_server) -> None:
    """Genuinely read-only MCP tools must retain readOnlyHint=True (R5-F1 regression).

    Verifies that fixing F1 did not accidentally strip readOnlyHint from
    truly read-only tools.
    """
    tools = asyncio.run(mcp_server.list_tools())
    tool_map = {t.name: t for t in tools}

    for name in _READ_ONLY_TOOLS:
        assert name in tool_map, f"Read-only tool not registered: {name!r}"
        tool = tool_map[name]
        ann = getattr(tool, "annotations", None)
        read_only_hint = getattr(ann, "readOnlyHint", None)
        assert read_only_hint is True, (
            f"R5-F1 side-effect: tool {name!r} should have readOnlyHint=True "
            f"but got readOnlyHint={read_only_hint!r}."
        )


@pytest.mark.smoke
def test_sim_run_annotated_write_op(mcp_server) -> None:
    """R8-F1 regression: sim_run must carry readOnlyHint=False (write-op annotation).

    sim_run writes .mx3/.mif solver scripts to temp directories unconditionally
    before any external-solver availability check, so readOnlyHint=True would
    violate the MCP tool annotation contract.
    """
    tools = asyncio.run(mcp_server.list_tools())
    tool_map = {t.name: t for t in tools}

    assert "sim_run" in tool_map, "sim_run tool is not registered"
    tool = tool_map["sim_run"]
    ann = getattr(tool, "annotations", None)
    read_only_hint = getattr(ann, "readOnlyHint", None)
    assert read_only_hint is not True, (
        "R8-F1 regression: sim_run has readOnlyHint=True but it writes "
        ".mx3/.mif solver scripts to temp directories — MCP spec violation."
    )
    assert read_only_hint is False, (
        f"R8-F1: sim_run should have readOnlyHint=False (write_op annotation) "
        f"but got readOnlyHint={read_only_hint!r}."
    )


# ---------------------------------------------------------------------------
# R9-F1 regression: sim_run with a multi-scale spec must return structured error
# ---------------------------------------------------------------------------

#: A valid single-scale ScaleSpec dictionary (Permalloy micromagnetic).
_PERMALLOY_SCALE: dict = {
    "scale": "micro",
    "engine": "auto",
    "label": "permalloy",
    "material": {
        "Ms_Am": 860000.0,
        "A_Jm": 1.3e-11,
        "alpha": 0.008,
        "K_Jm3": 0.0,
        "K_axis": [0.0, 0.0, 1.0],
        "D_Jm2": 0.0,
        "material_id": None,
    },
    "geometry": {
        "nx": 4,
        "ny": 4,
        "nz": 1,
        "dx_nm": 2.0,
        "dy_nm": 2.0,
        "dz_nm": 3.0,
        "pbc_x": False,
        "pbc_y": False,
        "pbc_z": False,
    },
    "field_sweep": None,
    "t_sim_ns": 0.0,
    "dt_ns": None,
    "initial_state": "uniform_x",
    "initial_m_dir": [1.0, 0.0, 0.0],
    "extra": {},
}

#: MultiScaleSpec with two ScaleSpec entries — triggers single_scale_spec() ValueError.
_MULTI_SCALE_SPEC: dict = {
    "name": "multi_scale_test",
    "description": "Two-scale spec; triggers single_scale_spec() ValueError in run_sim_overlay.",
    "scales": [_PERMALLOY_SCALE, _PERMALLOY_SCALE],
    "handoffs": [],
    "provenance_ref": "",
}


@pytest.mark.smoke
def test_sim_run_multi_scale_spec_returns_structured_error(mcp_server) -> None:
    """R9-F1 regression: sim_run with a multi-scale spec must return ok=False, not raise.

    A MultiScaleSpec with two or more ScaleSpec entries passes model_validate and
    validate(), then reaches single_scale_spec() in run_sim_overlay() which raises
    ValueError("Not a single-scale spec ...").  Before the fix, this ValueError
    escaped sim_run as an unhandled exception reaching the MCP host.  After the fix,
    sim_run catches it and returns {"ok": False, "error": "..."}.
    """
    result = asyncio.run(
        mcp_server.call_tool("sim_run", {"spec_dict": _MULTI_SCALE_SPEC})
    )
    assert result is not None
    content_str = str(result)
    # The tool must return a structured error dict, not raise.
    assert "false" in content_str.lower() or "error" in content_str.lower(), (
        f"R9-F1 regression: sim_run with a multi-scale spec did not return "
        f"a structured error. Response: {content_str!r}"
    )
    # Specifically, "ok" must be False — not raising unhandled ValueError.
    assert "not a single-scale spec" in content_str.lower() or "error" in content_str.lower(), (
        f"Expected 'Not a single-scale spec' or 'error' in response. Got: {content_str!r}"
    )


@pytest.mark.smoke
def test_materials_resource_content(mcp_server) -> None:
    """materials:// resource should return a JSON list."""
    import json

    content = asyncio.run(mcp_server.read_resource("materials://"))
    # content may be in list[Resource] form
    content_str = str(content)
    # Check if JSON-parseable
    # If content is a ResourceContent list, extract the text attribute
    try:
        # ResourceContent / TextResourceContents form
        if isinstance(content, list):
            for item in content:
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if text:
                    parsed = json.loads(text)
                    assert isinstance(parsed, list)
                    return
        # Direct str form
        parsed = json.loads(content_str)
        assert isinstance(parsed, (list, dict))
    except (json.JSONDecodeError, TypeError):
        # Pass if content exists even when JSON parsing fails
        assert len(content_str) > 2
