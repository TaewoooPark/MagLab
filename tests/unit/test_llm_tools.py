"""Tests for the MagLab LLM tool registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.llm.tools import call_tool, get_registered_tools, get_tool_definition


def test_bundled_llm_tools_are_registered() -> None:
    names = {tool.name for tool in get_registered_tools()}

    assert "workspace_tree" in names
    assert "workspace_read_file" in names
    assert "workspace_search" in names
    assert "physics_compute" in names
    assert "sim_validate" in names
    assert "figure_render" in names


def test_tool_schema_preserves_dict_parameters() -> None:
    definition = get_tool_definition("physics_compute")

    assert definition is not None
    params = definition.parameters["properties"]
    assert params["params"]["type"] == "object"


def test_workspace_read_file_is_scoped_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("sample text\n", encoding="utf-8")

    result = call_tool("workspace_read_file", {"path": "notes.md"})
    assert result["ok"] is True
    assert result["path"] == "notes.md"
    assert "sample text" in result["content"]

    escaped = call_tool("workspace_read_file", {"path": str(tmp_path.parent / "outside.md")})
    assert escaped["ok"] is False
    assert "escapes active workspace" in escaped["error"]


def test_workspace_search_returns_line_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("alpha\nspin Hall signal\n", encoding="utf-8")

    result = call_tool("workspace_search", {"pattern": "spin Hall", "glob": "*.md"})
    assert result["ok"] is True
    assert result["matches"] == [{"path": "MAGLAB.md", "line": 2, "text": "spin Hall signal"}]


def test_physics_compute_tool_returns_deterministic_result() -> None:
    result = call_tool(
        "physics_compute",
        {"formula": "exchange_length", "params": {"A": 1.3e-11, "Ms": 8.0e5}},
    )

    assert result["ok"] is True
    assert result["formula"] == "exchange_length"
    assert result["result"] > 0
