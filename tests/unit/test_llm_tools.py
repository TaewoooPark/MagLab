"""Tests for the MagLab LLM tool registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.llm.tools import call_tool, get_registered_tools, get_tool_definition


def test_bundled_llm_tools_are_registered() -> None:
    names = {tool.name for tool in get_registered_tools()}

    assert "workspace_context" in names
    assert "workspace_tree" in names
    assert "workspace_read_file" in names
    assert "workspace_search" in names
    assert "physics_compute" in names
    assert "sim_validate" in names
    assert "sim_doctor" in names
    assert "maglab_doctor" in names
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


def test_workspace_context_includes_marker_and_key_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("# Project\nSpin Hall context\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "data").mkdir()

    result = call_tool("workspace_context", {"max_entries": 10, "max_maglab_chars": 100})

    assert result["ok"] is True
    assert result["root"] == str(tmp_path)
    assert result["maglab_md"] == str(tmp_path / "MAGLAB.md")
    assert "Spin Hall context" in result["maglab_md_excerpt"]
    assert "README.md" in result["key_paths"]
    assert "data/" in result["key_paths"]
    assert "Before answering project-specific questions" in result["prompt"]


def test_workspace_context_prunes_ignored_heavy_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "hidden.js").write_text("should not appear\n", encoding="utf-8")
    (tmp_path / ".maglab" / "runtime").mkdir(parents=True)
    (tmp_path / ".maglab" / "runtime" / "budget.db").write_text("runtime\n", encoding="utf-8")
    (tmp_path / ".playwright-mcp").mkdir()
    (tmp_path / ".playwright-mcp" / "page.yml").write_text("runtime\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("visible\n", encoding="utf-8")

    result = call_tool("workspace_context", {"max_entries": 20})

    assert result["ok"] is True
    assert "notes.md" in result["entries"]
    assert "node_modules/" not in result["entries"]
    assert all("hidden.js" not in entry for entry in result["entries"])
    assert all(".maglab/runtime" not in entry for entry in result["entries"])
    assert all(".playwright-mcp" not in entry for entry in result["entries"])


def test_workspace_tree_tool_supports_type_and_depth_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "analysis.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample.csv").write_text("x,y\n0,0\n", encoding="utf-8")

    docs = call_tool("workspace_tree", {"entry_type": "docs", "max_depth": 1})
    code = call_tool("workspace_tree", {"entry_type": "code"})
    data = call_tool("workspace_tree", {"entry_type": "data"})

    assert docs["ok"] is True
    assert docs["entries"] == ["README.md"]
    assert "src/analysis.py" in code["entries"]
    assert "data/sample.csv" in data["entries"]


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
