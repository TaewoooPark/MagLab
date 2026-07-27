"""maglab.harness.plan tests — planning is deterministic and offline.

Every assertion here runs without a backend, a network call, or an optional
extra. That is the property the whole read-only harness surface depends on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maglab.core.manifest import AgentEntry, Manifest, WorkflowEntry
from maglab.harness.plan import (
    WORKFLOW_ALIASES,
    HarnessPlanError,
    build_worker_plan,
    build_workflow_plan,
    resolve_model,
    resolve_workflow_name,
)


@pytest.fixture()
def manifest() -> Manifest:
    """A small self-contained manifest — no dependence on the shipped file."""
    return Manifest(
        agents=[
            AgentEntry(
                name="scout",
                description="finds things",
                model="haiku",
                tools=["read_file"],
                skills=["literature-search"],
                mcp_servers=["maglab-mcp-server"],
                max_turns=8,
            ),
            AgentEntry(name="editor", description="writes up", model="sonnet", tools=["read_file"]),
        ],
        workflows=[
            WorkflowEntry(name="mini", steps=["scout", "editor"], description="two steps"),
            WorkflowEntry(name="survey", steps=["scout"], description="alias target"),
        ],
        metadata={"version": "1.0.0"},
    )


@pytest.fixture()
def isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep MCP-registry lookup off the developer's real home directory."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return tmp_path


class TestNameResolution:
    def test_manifest_names_pass_through(self, manifest: Manifest) -> None:
        assert resolve_workflow_name("mini", manifest) == "mini"

    def test_alias_resolves(self, manifest: Manifest) -> None:
        assert resolve_workflow_name("literature-review", manifest) == "survey"

    def test_alias_is_case_insensitive(self, manifest: Manifest) -> None:
        assert resolve_workflow_name("  Literature-Review ", manifest) == "survey"

    def test_manifest_name_wins_over_alias(self) -> None:
        """A real workflow named like an alias must not be redirected."""
        m = Manifest(workflows=[WorkflowEntry(name="literature-review", steps=[])])
        assert resolve_workflow_name("literature-review", m) == "literature-review"

    def test_unknown_name_is_returned_unchanged(self, manifest: Manifest) -> None:
        assert resolve_workflow_name("nope", manifest) == "nope"

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            ("haiku", "claude-haiku-4-5"),
            ("sonnet", "claude-sonnet-4-6"),
            ("opus", "claude-opus-4-7"),
            ("inherit", ""),
        ],
    )
    def test_model_tiers_resolve(self, tier: str, expected: str) -> None:
        assert resolve_model(tier) == expected

    def test_model_tiers_match_the_runner(self) -> None:
        """A dry-run must report the model the live runner would actually pick."""
        from maglab.core.subagents import SubagentRunner

        runner = SubagentRunner(defs={}, backend=None)
        for tier in ("haiku", "sonnet", "opus"):
            assert runner._resolve_model(tier) == resolve_model(tier)


class TestWorkflowPlan:
    def test_steps_follow_manifest_order(self, manifest: Manifest, isolated_registry: Path) -> None:
        plan = build_workflow_plan("mini", manifest=manifest, root=isolated_registry)
        assert [s.agent for s in plan.steps] == ["scout", "editor"]

    def test_alias_records_both_names(self, manifest: Manifest, isolated_registry: Path) -> None:
        plan = build_workflow_plan("literature-review", manifest=manifest, root=isolated_registry)
        assert plan.name == "survey"
        assert plan.requested_name == "literature-review"

    def test_topic_is_carried_into_the_payload(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        plan = build_workflow_plan(
            "mini", topic="SOT in CoFeB", manifest=manifest, root=isolated_registry
        )
        assert plan.pi_agents_workflow_payload()["input"] == "SOT in CoFeB"

    def test_unknown_workflow_lists_alternatives(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        with pytest.raises(HarnessPlanError, match="Unknown workflow"):
            build_workflow_plan("nope", manifest=manifest, root=isolated_registry)

    def test_unregistered_mcp_server_is_a_blocker(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        plan = build_workflow_plan("mini", manifest=manifest, root=isolated_registry)
        assert any("maglab-mcp-server" in b for b in plan.blockers)
        assert plan.steps[0].mcp_unregistered == ["maglab-mcp-server"]

    def test_registered_mcp_server_clears_the_blocker(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        registry = isolated_registry / ".maglab" / "mcp.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"servers": {"maglab-mcp-server": {}}}), encoding="utf-8")

        plan = build_workflow_plan("mini", manifest=manifest, root=isolated_registry)

        assert plan.steps[0].mcp_registered == ["maglab-mcp-server"]
        assert plan.steps[0].mcp_unregistered == []

    def test_corrupt_registry_does_not_break_planning(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        registry = isolated_registry / ".maglab" / "mcp.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("{broken", encoding="utf-8")

        plan = build_workflow_plan("mini", manifest=manifest, root=isolated_registry)

        assert plan.steps[0].mcp_unregistered == ["maglab-mcp-server"]

    def test_undeclared_step_agent_still_plans(self, isolated_registry: Path) -> None:
        """A workflow naming an unknown agent must surface, not vanish."""
        m = Manifest(workflows=[WorkflowEntry(name="broken", steps=["ghost"])])
        plan = build_workflow_plan("broken", manifest=m, root=isolated_registry)

        assert [s.agent for s in plan.steps] == ["ghost"]
        assert not plan.ready
        assert any("ghost" in b for b in plan.blockers)

    def test_plan_serialises_the_documented_contract(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        payload = build_workflow_plan(
            "mini", topic="t", manifest=manifest, root=isolated_registry
        ).to_dict()

        for key in ("workflow", "steps", "local_run_plan", "pi_agents_workflow_payload", "ready"):
            assert key in payload
        assert json.loads(json.dumps(payload))  # must be JSON-serialisable

    def test_local_run_plan_carries_one_entry_per_step(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        plan = build_workflow_plan("mini", manifest=manifest, root=isolated_registry)
        entries = plan.local_run_plan()

        assert len(entries) == len(plan.steps)
        assert entries[0]["command"][:3] == ["maglab", "harness", "worker"]


class TestWorkerPlan:
    def test_worker_plan_resolves_the_model(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        plan = build_worker_plan("editor", manifest=manifest, root=isolated_registry)
        assert plan.model == "sonnet"
        assert plan.resolved_model == "claude-sonnet-4-6"

    def test_unknown_agent_lists_alternatives(
        self, manifest: Manifest, isolated_registry: Path
    ) -> None:
        with pytest.raises(HarnessPlanError, match="Unknown agent"):
            build_worker_plan("ghost", manifest=manifest, root=isolated_registry)

    def test_task_is_recorded(self, manifest: Manifest, isolated_registry: Path) -> None:
        plan = build_worker_plan(
            "editor", task="do a thing", manifest=manifest, root=isolated_registry
        )
        assert plan.task == "do a thing"
        assert "--task" in plan.command()


class TestShippedManifest:
    """The manifest that actually ships must plan cleanly."""

    def test_every_declared_workflow_plans(self) -> None:
        from maglab.core.manifest import load_manifest

        manifest = load_manifest()
        assert manifest.workflow_names(), "shipped manifest declares no workflows"
        for name in manifest.workflow_names():
            plan = build_workflow_plan(name, manifest=manifest)
            assert plan.steps, f"{name} compiled to zero steps"

    def test_documented_aliases_all_resolve(self) -> None:
        from maglab.core.manifest import load_manifest

        manifest = load_manifest()
        declared = set(manifest.workflow_names())
        for alias, target in WORKFLOW_ALIASES.items():
            assert target in declared, f"alias {alias!r} points at undeclared workflow {target!r}"

    def test_every_step_has_a_backing_definition(self) -> None:
        from maglab.core.manifest import load_manifest

        manifest = load_manifest()
        for name in manifest.workflow_names():
            for step in build_workflow_plan(name, manifest=manifest).steps:
                assert step.definition_path, f"{name}/{step.agent} has no agents/*.md"

    def test_every_declared_skill_exists(self) -> None:
        from maglab.core.manifest import load_manifest

        manifest = load_manifest()
        for name in manifest.workflow_names():
            for step in build_workflow_plan(name, manifest=manifest).steps:
                assert step.skills_missing == [], (
                    f"{name}/{step.agent} declares missing skills {step.skills_missing}"
                )
