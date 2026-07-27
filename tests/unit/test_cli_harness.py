"""`maglab harness` CLI tests — contracts, exit codes and JSON parseability.

Exit codes matter here: `harness compile --check` is meant to be wired into CI,
so drift has to fail the command, not just print a table.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from maglab.cli import app

runner = CliRunner()


def _json(result) -> dict:
    return json.loads(result.stdout)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clean cwd, with home redirected so the MCP registry is deterministic."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return tmp_path


class TestDoctor:
    def test_json_output_parses(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "doctor", "--json"])
        payload = _json(result)
        assert {"ok", "checks", "failing"} <= set(payload)

    def test_reports_structural_health_of_the_shipped_manifest(self, workspace: Path) -> None:
        payload = _json(runner.invoke(app, ["harness", "doctor", "--json"]))
        structural = {"manifest", "workflow-steps", "agent-definitions", "agent-skills"}
        failing = set(payload["failing"]) & structural
        assert failing == set(), f"shipped manifest is inconsistent: {failing}"

    def test_text_output_renders(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "doctor"])
        assert "harness readiness" in result.output


class TestCompile:
    def test_prints_a_compiled_document(self, workspace: Path) -> None:
        payload = _json(runner.invoke(app, ["harness", "compile", "survey", "--json"]))
        assert payload["workflow"] == "survey"
        assert payload["steps"]

    def test_alias_compiles_to_the_canonical_name(self, workspace: Path) -> None:
        payload = _json(runner.invoke(app, ["harness", "compile", "literature-review", "--json"]))
        assert payload["workflow"] == "survey"

    def test_write_then_check_succeeds(self, workspace: Path) -> None:
        assert runner.invoke(app, ["harness", "compile", "--write"]).exit_code == 0
        assert runner.invoke(app, ["harness", "compile", "--check"]).exit_code == 0

    def test_check_without_artifacts_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "compile", "--check"])
        assert result.exit_code == 1

    def test_check_fails_on_drift(self, workspace: Path) -> None:
        """This command is meant for CI — drift must be a non-zero exit."""
        runner.invoke(app, ["harness", "compile", "--write"])
        artifact = workspace / ".pi" / "workflows" / "survey.json"
        artifact.write_text(
            artifact.read_text(encoding="utf-8").replace('"haiku"', '"opus"'), encoding="utf-8"
        )

        result = runner.invoke(app, ["harness", "compile", "--check"])

        assert result.exit_code == 1
        assert "survey" in result.output

    def test_unknown_workflow_exits_nonzero(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "compile", "no-such-workflow"])
        assert result.exit_code == 1
        assert "Unknown workflow" in result.output


class TestRunDryRun:
    def test_emits_the_documented_contract(self, workspace: Path) -> None:
        payload = _json(
            runner.invoke(
                app, ["harness", "run", "literature-review", "--topic", "SOT", "--dry-run"]
            )
        )
        for key in (
            "workflow",
            "steps",
            "local_run_plan",
            "pi_agents_workflow_payload",
            "cross_links",
            "mode",
        ):
            assert key in payload, f"missing contract key {key!r}"
        assert payload["mode"] == "dry-run"

    def test_alias_is_recorded_alongside_the_canonical_name(self, workspace: Path) -> None:
        payload = _json(runner.invoke(app, ["harness", "run", "deepresearch", "--dry-run"]))
        assert payload["workflow"] == "deep-research"
        assert payload["requested"] == "deepresearch"

    def test_ready_and_blockers_agree(self, workspace: Path) -> None:
        """A plan reported ready with blockers would be saying two things."""
        payload = _json(runner.invoke(app, ["harness", "run", "survey", "--dry-run"]))
        assert payload["ready"] == (payload["blockers"] == [])

    def test_topic_reaches_the_pi_payload(self, workspace: Path) -> None:
        payload = _json(
            runner.invoke(
                app, ["harness", "run", "survey", "--topic", "SOT switching", "--dry-run"]
            )
        )
        assert payload["pi_agents_workflow_payload"]["input"] == "SOT switching"

    def test_text_output_renders_a_plan(self, workspace: Path) -> None:
        result = runner.invoke(
            app, ["harness", "run", "survey", "--topic", "x", "--dry-run", "--output", "text"]
        )
        assert "step(s)" in result.output
        assert "Dry run" in result.output

    def test_pi_handoff_is_included_on_request(self, workspace: Path) -> None:
        payload = _json(
            runner.invoke(app, ["harness", "run", "survey", "--dry-run", "--pi-handoff"])
        )
        handoff = payload["pi_handoff"]
        assert handoff["command"][1:6] == [
            "--mode",
            "json",
            "--no-builtin-tools",
            "--tools",
            "workflow",
        ]

    def test_unknown_workflow_exits_nonzero(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "run", "nope", "--dry-run"])
        assert result.exit_code == 1

    def test_two_execution_paths_are_rejected(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "run", "survey", "--execute-local", "--execute-pi"])
        assert result.exit_code == 2

    def test_record_provenance_writes_a_store(self, workspace: Path) -> None:
        db = workspace / "prov.sqlite"
        payload = _json(
            runner.invoke(
                app,
                [
                    "harness",
                    "run",
                    "survey",
                    "--dry-run",
                    "--record-provenance",
                    "--provenance-db",
                    str(db),
                    "--pi-flow-id",
                    "flow-9",
                ],
            )
        )
        assert db.is_file()
        assert payload["cross_links"]["provenance_activity"]["recorded"] is True
        assert payload["cross_links"]["pi_flow_id"] == "flow-9"


class TestRunExecutePi:
    def test_missing_pi_fails_with_a_pointer_not_a_fake_result(self, workspace: Path) -> None:
        """Live PI execution is gated, never simulated."""
        with patch("maglab.harness.pi.find_pi_binary", return_value=""):
            result = runner.invoke(app, ["harness", "run", "survey", "--execute-pi"])

        assert result.exit_code == 1
        assert "PI handoff unavailable" in result.output
        assert "--execute-local" in result.output


class TestWorker:
    def test_json_plan_for_one_agent(self, workspace: Path) -> None:
        payload = _json(runner.invoke(app, ["harness", "worker", "search-scout", "--json"]))
        assert payload["agent"] == "search-scout"
        assert payload["resolved_model"]
        assert payload["tools"]

    def test_task_is_carried(self, workspace: Path) -> None:
        payload = _json(
            runner.invoke(app, ["harness", "worker", "citation-auditor", "--task", "{}", "--json"])
        )
        assert "--task" in payload["command"]

    def test_unknown_agent_exits_nonzero(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "worker", "ghost"])
        assert result.exit_code == 1
        assert "Unknown agent" in result.output

    def test_text_output_renders(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "worker", "synthesis-editor"])
        assert "worker plan" in result.output


class TestPiTool:
    def test_resolves_a_payload(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            ["harness", "pi-tool", "--payload-json", '{"workflow":"survey","input":"SOT"}'],
        )
        payload = _json(result)
        assert payload["workflow"] == "survey"
        assert payload["input"] == "SOT"

    def test_malformed_payload_exits_nonzero(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "pi-tool", "--payload-json", "{broken"])
        assert result.exit_code == 1
        assert "not valid JSON" in result.output

    def test_text_output_lists_the_steps(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            [
                "harness",
                "pi-tool",
                "--payload-json",
                '{"workflow":"citation-map","input":"x"}',
                "--output",
                "text",
            ],
        )
        assert "citation-auditor" in result.output


class TestExistingCommandIntegration:
    """The harness is reachable from the commands users already run."""

    def test_run_with_harness_workflow_shows_a_plan(self, workspace: Path) -> None:
        result = runner.invoke(
            app, ["run", "SOT switching in CoFeB", "--harness-workflow", "literature-review"]
        )

        assert result.exit_code == 0, result.output
        assert "survey" in result.output
        assert "step(s)" in result.output

    def test_run_without_the_flag_is_untouched(self, workspace: Path) -> None:
        """The default path must not start planning a workflow."""
        with patch("maglab.cli._build_orchestrator") as build:
            build.return_value.run.return_value = SimpleNamespace(
                status="done", summary="s", datapoints=[], warnings=[]
            )
            result = runner.invoke(app, ["run", "a goal"])

        assert result.exit_code == 0
        build.assert_called_once()

    def test_run_with_unknown_workflow_exits_nonzero(self, workspace: Path) -> None:
        result = runner.invoke(app, ["run", "goal", "--harness-workflow", "no-such-workflow"])
        assert result.exit_code == 1


class TestLitSearchHarnessPlan:
    @pytest.fixture()
    def corpus(self, workspace: Path) -> Path:
        (workspace / "a.txt").write_text(
            "spin orbit torque magnetization switching CoFeB heavy metal " * 40, encoding="utf-8"
        )
        return workspace

    def test_harness_json_stdout_is_pure_json(self, corpus: Path) -> None:
        """A keyword table printed ahead of the payload would break parsing."""
        result = runner.invoke(
            app, ["lit", "search", str(corpus), "--harness-plan", "--harness-json"]
        )

        payload = json.loads(result.stdout)
        assert payload["workflow"] == "survey"
        assert payload["steps"]

    def test_explicit_topic_wins_over_keywords(self, corpus: Path) -> None:
        result = runner.invoke(
            app,
            [
                "lit",
                "search",
                str(corpus),
                "--harness-plan",
                "--harness-json",
                "--topic",
                "explicit topic",
            ],
        )
        assert json.loads(result.stdout)["topic"] == "explicit topic"

    def test_no_evidence_matrix_is_written_in_plan_mode(self, corpus: Path) -> None:
        """Plan mode prepares the workflow; it does not do the search itself."""
        runner.invoke(app, ["lit", "search", str(corpus), "--harness-plan"])
        assert not (corpus / "evidence_matrix.json").exists()

    def test_text_mode_explains_what_was_skipped(self, corpus: Path) -> None:
        result = runner.invoke(app, ["lit", "search", str(corpus), "--harness-plan"])
        assert "No direct search was run" in result.output
