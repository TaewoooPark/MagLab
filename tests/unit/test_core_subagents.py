"""subagents.py unit tests — LLM mock, deterministic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from maglab.core.subagents import (
    SubagentLoadError,
    SubagentRunner,
    _parse_agent_md,
    _parse_structured_output,
    load_subagent_defs,
)
from maglab.llm.base import LLMResponse, UsageStats

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_agents_dir(tmp_path: Path) -> Path:
    """Temporary agents directory."""
    d = tmp_path / "agents"
    d.mkdir()
    return d


def _write_agent(
    agents_dir: Path,
    name: str,
    tools: list[str] | None = None,
    model: str = "haiku",
    max_turns: int = 6,
    body: str = "You are a test agent.",
) -> Path:
    fm = {
        "name": name,
        "description": f"{name} agent description",
        "tools": tools or [],
        "model": model,
        "max_turns": max_turns,
        "context": "isolated",
    }
    content = "---\n" + yaml.dump(fm, allow_unicode=True) + "---\n\n" + body
    p = agents_dir / f"{name}.md"
    p.write_text(content, encoding="utf-8")
    return p


def _make_mock_backend(
    response_text: str = '{"status": "success", "result": "ok", "warnings": []}',
) -> MagicMock:
    backend = MagicMock()
    response = LLMResponse(
        content=response_text,
        usage=UsageStats(prompt_tokens=10, completion_tokens=20),
    )
    backend.complete.return_value = response
    return backend


# ---------------------------------------------------------------------------
# SubagentDef parsing
# ---------------------------------------------------------------------------


class TestSubagentDefParsing:
    def test_parse_valid(self, tmp_agents_dir: Path) -> None:
        p = _write_agent(tmp_agents_dir, "physics-validator", tools=["physics_check"])
        defn = _parse_agent_md(p)
        assert defn.name == "physics-validator"
        assert "physics_check" in defn.tools
        assert defn.model == "haiku"
        assert defn.max_turns == 6
        assert defn.context == "isolated"
        assert "test agent" in defn.system_prompt

    def test_missing_frontmatter(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.md"
        p.write_text("body only", encoding="utf-8")
        with pytest.raises(SubagentLoadError, match="frontmatter"):
            _parse_agent_md(p)

    def test_missing_name_field(self, tmp_path: Path) -> None:
        p = tmp_path / "noname.md"
        p.write_text("---\ndescription: description\n---\n\nbody", encoding="utf-8")
        with pytest.raises(SubagentLoadError, match="name"):
            _parse_agent_md(p)

    def test_source_file_set(self, tmp_agents_dir: Path) -> None:
        p = _write_agent(tmp_agents_dir, "test-agent")
        defn = _parse_agent_md(p)
        assert str(p) in defn.source_file

    def test_body_is_system_prompt(self, tmp_agents_dir: Path) -> None:
        body = "## System Prompt\n\nYou are a validator."
        p = _write_agent(tmp_agents_dir, "validator", body=body)
        defn = _parse_agent_md(p)
        assert "System Prompt" in defn.system_prompt

    def test_readme_skipped(self, tmp_agents_dir: Path) -> None:
        (tmp_agents_dir / "README.md").write_text("# README", encoding="utf-8")
        defs = load_subagent_defs(tmp_agents_dir)
        assert "README" not in defs
        assert "readme" not in {k.lower() for k in defs}


# ---------------------------------------------------------------------------
# load_subagent_defs
# ---------------------------------------------------------------------------


class TestLoadSubagentDefs:
    def test_load_from_dir(self, tmp_agents_dir: Path) -> None:
        _write_agent(tmp_agents_dir, "agent-a")
        _write_agent(tmp_agents_dir, "agent-b")
        defs = load_subagent_defs(tmp_agents_dir)
        assert "agent-a" in defs
        assert "agent-b" in defs

    def test_first_wins_on_duplicate(self, tmp_path: Path) -> None:
        """When the same name exists in two directories, the first wins."""
        dir1 = tmp_path / "d1"
        dir2 = tmp_path / "d2"
        dir1.mkdir()
        dir2.mkdir()
        _write_agent(dir1, "my-agent", body="dir1 agent")
        _write_agent(dir2, "my-agent", body="dir2 agent")
        defs = load_subagent_defs(dir1, dir2)
        assert "dir1 agent" in defs["my-agent"].system_prompt

    def test_nonexistent_dir_skipped(self, tmp_path: Path) -> None:
        """Non-existent directories are skipped."""
        defs = load_subagent_defs(tmp_path / "ghost")
        assert defs == {}

    def test_bad_agent_skipped_with_warning(
        self, tmp_agents_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Agents with parse errors are skipped after logging a warning."""
        (tmp_agents_dir / "bad.md").write_text("body only", encoding="utf-8")
        _write_agent(tmp_agents_dir, "good-agent")
        import logging

        with caplog.at_level(logging.WARNING):
            defs = load_subagent_defs(tmp_agents_dir)
        assert "good-agent" in defs
        assert "bad" not in defs

    def test_default_dirs_used_when_no_args(self) -> None:
        """When called without arguments, default paths are used (returns without error)."""
        defs = load_subagent_defs()
        assert isinstance(defs, dict)


# ---------------------------------------------------------------------------
# _parse_structured_output
# ---------------------------------------------------------------------------


class TestParseStructuredOutput:
    def test_json_code_block(self) -> None:
        text = '```json\n{"status": "success", "result": "ok"}\n```'
        parsed = _parse_structured_output(text)
        assert parsed["status"] == "success"

    def test_naked_json(self) -> None:
        text = 'Result: {"status": "success", "x": 1}'
        parsed = _parse_structured_output(text)
        assert parsed["x"] == 1

    def test_empty_text(self) -> None:
        parsed = _parse_structured_output("")
        assert parsed == {}

    def test_no_json(self) -> None:
        parsed = _parse_structured_output("Plain text only.")
        assert parsed == {}

    def test_invalid_json_block(self) -> None:
        text = "```json\n{invalid}\n```"
        parsed = _parse_structured_output(text)
        assert parsed == {}


# ---------------------------------------------------------------------------
# SubagentRunner
# ---------------------------------------------------------------------------


class TestSubagentRunner:
    def test_run_success(self, tmp_agents_dir: Path) -> None:
        _write_agent(tmp_agents_dir, "test-agent")
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend('{"status": "success", "result": "validation passed", "warnings": []}')
        runner = SubagentRunner(defs, backend)
        result = runner.run("test-agent", "test task")
        assert result["status"] == "success"
        assert result["result"] == "validation passed"

    def test_run_unknown_agent(self, tmp_agents_dir: Path) -> None:
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend()
        runner = SubagentRunner(defs, backend)
        with pytest.raises(ValueError, match="not found"):
            runner.run("nonexistent-agent", "task")

    def test_run_depth_exceeded(self, tmp_agents_dir: Path) -> None:
        _write_agent(tmp_agents_dir, "test-agent")
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend()
        runner = SubagentRunner(defs, backend)
        with pytest.raises(ValueError, match="depth"):
            runner.run("test-agent", "task", depth=2)

    def test_run_unstructured_output(self, tmp_agents_dir: Path) -> None:
        """Inject partial structure when JSON parsing fails."""
        _write_agent(tmp_agents_dir, "test-agent")
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend("Pure text response with no JSON.")
        runner = SubagentRunner(defs, backend)
        result = runner.run("test-agent", "task")
        assert result["status"] == "partial"

    def test_run_backend_error(self, tmp_agents_dir: Path) -> None:
        """Return failed structure on backend exception."""
        _write_agent(tmp_agents_dir, "test-agent")
        defs = load_subagent_defs(tmp_agents_dir)
        backend = MagicMock()
        backend.complete.side_effect = RuntimeError("API connection failed")
        runner = SubagentRunner(defs, backend)
        result = runner.run("test-agent", "task")
        assert result["status"] == "failed"

    def test_available(self, tmp_agents_dir: Path) -> None:
        _write_agent(tmp_agents_dir, "agent-x")
        _write_agent(tmp_agents_dir, "agent-y")
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend()
        runner = SubagentRunner(defs, backend)
        names = runner.available()
        assert "agent-x" in names
        assert "agent-y" in names

    def test_get_def(self, tmp_agents_dir: Path) -> None:
        _write_agent(tmp_agents_dir, "my-agent", tools=["physics_check"])
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend()
        runner = SubagentRunner(defs, backend)
        defn = runner.get_def("my-agent")
        assert defn is not None
        assert "physics_check" in defn.tools

    def test_get_def_missing(self, tmp_agents_dir: Path) -> None:
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend()
        runner = SubagentRunner(defs, backend)
        assert runner.get_def("ghost") is None

    def test_verify_status_in_result(self, tmp_agents_dir: Path) -> None:
        """_verify_status field is included in the result."""
        _write_agent(tmp_agents_dir, "test-agent")
        defs = load_subagent_defs(tmp_agents_dir)
        backend = _make_mock_backend('{"status": "success", "warnings": []}')
        runner = SubagentRunner(defs, backend)
        result = runner.run("test-agent", "task")
        assert "_verify_status" in result

    def test_oracle_fail_reflected(self, tmp_agents_dir: Path) -> None:
        """oracle failure → _verify_status=failed."""
        _write_agent(tmp_agents_dir, "test-agent")
        defs = load_subagent_defs(tmp_agents_dir)
        # alpha=5.0 triggers oracle failure
        bad_output = '{"status": "success", "alpha": 5.0, "warnings": []}'
        backend = _make_mock_backend(bad_output)
        runner = SubagentRunner(defs, backend)
        result = runner.run("test-agent", "task")
        assert result["_verify_status"] == "failed"


# ---------------------------------------------------------------------------
# Bundle physics-validator.md load integration
# ---------------------------------------------------------------------------


class TestBundlePhysicsValidator:
    def test_load_physics_validator(self) -> None:
        """Bundle agents/physics-validator.md must be loadable."""
        defs = load_subagent_defs()
        # if physics-validator.md exists in the bundle directory it must load;
        # if absent, no error must be raised
        assert isinstance(defs, dict)
        if "physics-validator" in defs:
            pv = defs["physics-validator"]
            assert pv.model == "haiku"
            assert pv.max_turns <= 10
            assert pv.context == "isolated"
