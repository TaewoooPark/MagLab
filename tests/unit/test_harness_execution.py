"""maglab.harness local execution, PI handoff and provenance recording.

No test here contacts a provider: local execution takes an injected runner, and
the PI path is exercised through a stubbed binary. Anything that would need real
credentials is the thing being gated, not the thing being tested.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from maglab.core.manifest import AgentEntry, Manifest, WorkflowEntry
from maglab.harness.local import execute_locally
from maglab.harness.pi import (
    PiUnavailableError,
    build_handoff,
    build_prompt,
    execute_handoff,
    pi_tool_payload,
)
from maglab.harness.plan import HarnessPlanError, build_workflow_plan
from maglab.harness.record import record_run


@pytest.fixture()
def manifest() -> Manifest:
    return Manifest(
        agents=[
            AgentEntry(name="scout", model="haiku", tools=["read_file"]),
            AgentEntry(name="editor", model="sonnet", tools=["read_file"]),
        ],
        workflows=[WorkflowEntry(name="mini", steps=["scout", "editor"], description="two steps")],
        metadata={"version": "1.0.0"},
    )


@pytest.fixture()
def plan(manifest: Manifest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return build_workflow_plan("mini", topic="SOT in CoFeB", manifest=manifest, root=tmp_path)


class StubRunner:
    """Stands in for SubagentRunner — records calls, returns canned results."""

    def __init__(self, fail_at: str | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.fail_at = fail_at

    def run(self, name: str, task: str, *, depth: int = 0, extra_context: str = ""):
        self.calls.append((name, task, extra_context))
        if name == self.fail_at:
            return {
                "status": "failed",
                "_verify_status": "failed",
                "_warnings": ["stub failure"],
            }
        return {"status": "success", "finding": f"{name} finding", "_verify_status": "passed"}


class TestLocalExecution:
    def test_runs_every_step_in_order(self, plan) -> None:
        runner = StubRunner()
        result = execute_locally(plan, runner=runner)

        assert result["ok"] is True
        assert [c[0] for c in runner.calls] == ["scout", "editor"]
        assert result["completed"] == result["planned"] == 2

    def test_topic_reaches_the_first_step(self, plan) -> None:
        runner = StubRunner()
        execute_locally(plan, runner=runner)
        assert "SOT in CoFeB" in runner.calls[0][1]

    def test_later_steps_receive_upstream_results(self, plan) -> None:
        """A workflow is more than N independent calls."""
        runner = StubRunner()
        execute_locally(plan, runner=runner)

        second_task = runner.calls[1][1]
        assert "Upstream results" in second_task
        assert "scout finding" in second_task

    def test_failure_stops_the_run(self, plan) -> None:
        """Downstream steps consume upstream output — continuing would build on it."""
        result = execute_locally(plan, runner=StubRunner(fail_at="scout"))

        assert result["ok"] is False
        assert result["completed"] == 1
        assert result["steps"][-1]["verify_status"] == "failed"

    def test_max_steps_caps_the_run(self, plan) -> None:
        result = execute_locally(plan, runner=StubRunner(), max_steps=1)
        assert result["completed"] == 1
        assert result["planned"] == 2

    def test_runner_exception_is_recorded_not_raised(self, plan) -> None:
        class Exploding:
            def run(self, *args, **kwargs):
                raise RuntimeError("backend exploded")

        result = execute_locally(plan, runner=Exploding())

        assert result["ok"] is False
        assert "backend exploded" in result["steps"][0]["error"]

    def test_result_is_json_serialisable(self, plan) -> None:
        assert json.loads(json.dumps(execute_locally(plan, runner=StubRunner())))

    def test_internal_keys_are_stripped_from_step_results(self, plan) -> None:
        result = execute_locally(plan, runner=StubRunner())
        assert all(not k.startswith("_") for k in result["steps"][0]["result"])


class TestPiHandoff:
    def test_command_matches_the_documented_form(self, plan) -> None:
        handoff = build_handoff(plan, binary="/usr/local/bin/pi")
        assert handoff.command[:6] == [
            "/usr/local/bin/pi",
            "--mode",
            "json",
            "--no-builtin-tools",
            "--tools",
            "workflow",
        ]
        assert handoff.command[6] == "-p"

    def test_prompt_embeds_the_payload_verbatim(self, plan) -> None:
        prompt = build_prompt(plan)
        assert plan.name in prompt
        assert "SOT in CoFeB" in prompt
        payload = json.loads(prompt.split("```json")[1].split("```")[0])
        assert payload == plan.pi_agents_workflow_payload()

    def test_handoff_is_generated_even_without_pi(self, plan) -> None:
        """Reading the command you would run is useful on a machine that cannot."""
        handoff = build_handoff(plan, binary="")
        assert handoff.available is False
        assert handoff.command[0] == "pi"
        assert "not found" in handoff.reason

    def test_shell_command_is_quoted(self, plan) -> None:
        line = build_handoff(plan, binary="/usr/local/bin/pi").shell_command()
        assert line.startswith("/usr/local/bin/pi --mode json")

    def test_execute_refuses_when_pi_is_absent(self, plan) -> None:
        with pytest.raises(PiUnavailableError, match="not found"):
            execute_handoff(build_handoff(plan, binary=""))

    def test_execute_returns_the_process_result(self, plan) -> None:
        completed = SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")
        with patch("maglab.harness.pi.subprocess.run", return_value=completed):
            result = execute_handoff(build_handoff(plan, binary="/usr/local/bin/pi"))

        assert result["returncode"] == 0
        assert json.loads(result["stdout"]) == {"ok": True}

    def test_execute_surfaces_a_timeout(self, plan) -> None:
        import subprocess

        with (
            patch(
                "maglab.harness.pi.subprocess.run",
                side_effect=subprocess.TimeoutExpired("pi", 900),
            ),
            pytest.raises(PiUnavailableError, match="did not complete"),
        ):
            execute_handoff(build_handoff(plan, binary="/usr/local/bin/pi"))

    def test_execute_surfaces_a_launch_failure(self, plan) -> None:
        with (
            patch("maglab.harness.pi.subprocess.run", side_effect=OSError("no exec")),
            pytest.raises(PiUnavailableError, match="Could not start PI"),
        ):
            execute_handoff(build_handoff(plan, binary="/usr/local/bin/pi"))

    def test_handoff_serialises(self, plan) -> None:
        assert json.loads(json.dumps(build_handoff(plan, binary="/x/pi").to_dict()))


class TestPiToolPayload:
    def test_resolves_a_workflow(self) -> None:
        result = pi_tool_payload('{"workflow": "literature-review", "input": "SOT"}')
        assert result["workflow"] == "survey"
        assert result["requested"] == "literature-review"
        assert result["input"] == "SOT"

    def test_accepts_a_dict(self) -> None:
        assert pi_tool_payload({"workflow": "citation-map"})["workflow"] == "citation-map"

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ("{not json", "not valid JSON"),
            ("[1, 2]", "must be a JSON object"),
            ('{"input": "x"}', "non-empty"),
            ('{"workflow": ""}', "non-empty"),
            ('{"workflow": "survey", "input": 5}', "must be a string"),
            ('{"workflow": "no-such-workflow"}', "Unknown workflow"),
        ],
    )
    def test_malformed_payloads_are_rejected(self, payload: str, message: str) -> None:
        with pytest.raises(HarnessPlanError, match=message):
            pi_tool_payload(payload)


class TestProvenanceRecording:
    def test_records_an_activity_and_one_entity_per_step(self, plan, tmp_path: Path) -> None:
        db = tmp_path / "prov.sqlite"
        record = record_run(plan, db_path=db, pi_flow_id="flow-1")

        assert record["recorded"] is True
        assert len(record["entities"]) == len(plan.steps)
        assert record["pi_flow_id"] == "flow-1"

    def test_entities_are_linked_to_the_activity(self, plan, tmp_path: Path) -> None:
        from maglab.provenance.store import ProvenanceStore

        db = tmp_path / "prov.sqlite"
        record = record_run(plan, db_path=db)

        with ProvenanceStore(db) as store:
            lineage = store.get_entity_lineage(record["entities"][0])

        ids = {row["id"] for row in lineage}
        assert any("wgb-" in i for i in ids), "step is not linked to the activity"
        assert any("wat-" in i for i in ids), "step has no attribution"

    def test_recording_failure_is_reported_not_raised(self, plan, tmp_path: Path) -> None:
        """Losing the audit record must not abandon the research task."""
        with patch("maglab.provenance.store.ProvenanceStore", side_effect=OSError("read-only")):
            record = record_run(plan, db_path=tmp_path / "prov.sqlite")

        assert record["recorded"] is False
        assert "read-only" in record["error"]

    def test_a_not_ready_plan_is_still_recorded(self, tmp_path: Path) -> None:
        """What was attempted matters even when it could not run."""
        manifest = Manifest(workflows=[WorkflowEntry(name="broken", steps=["ghost"])])
        broken = build_workflow_plan("broken", manifest=manifest, root=tmp_path)

        record = record_run(broken, db_path=tmp_path / "prov.sqlite")

        assert record["recorded"] is True
