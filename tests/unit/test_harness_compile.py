"""maglab.harness.compile tests — drift artifacts must be stable and honest.

The artifact only earns its keep if it is byte-identical for the same manifest
on any machine; otherwise ``--check`` fails for reasons that have nothing to do
with the routing table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maglab.core.manifest import AgentEntry, Manifest, WorkflowEntry
from maglab.harness.compile import (
    artifact_path,
    check_artifacts,
    compile_workflow,
    render,
    workflow_targets,
    write_artifacts,
)
from maglab.harness.plan import HarnessPlanError


@pytest.fixture()
def manifest() -> Manifest:
    return Manifest(
        agents=[
            AgentEntry(name="scout", model="haiku", tools=["b", "a"], skills=["s2", "s1"]),
            AgentEntry(name="editor", model="sonnet", tools=["read_file"]),
        ],
        workflows=[
            WorkflowEntry(name="mini", steps=["scout", "editor"], description="two steps"),
            WorkflowEntry(name="solo", steps=["scout"]),
        ],
        metadata={"version": "1.0.0"},
    )


class TestCompile:
    def test_compiles_steps_in_order(self, manifest: Manifest) -> None:
        doc = compile_workflow("mini", manifest)
        assert [s["agent"] for s in doc["steps"]] == ["scout", "editor"]

    def test_resolves_the_model_tier(self, manifest: Manifest) -> None:
        doc = compile_workflow("mini", manifest)
        assert doc["steps"][0]["resolved_model"] == "claude-haiku-4-5"

    def test_lists_are_sorted_for_stability(self, manifest: Manifest) -> None:
        step = compile_workflow("mini", manifest)["steps"][0]
        assert step["tools"] == ["a", "b"]
        assert step["skills"] == ["s1", "s2"]

    def test_undeclared_agent_is_recorded_not_dropped(self) -> None:
        m = Manifest(workflows=[WorkflowEntry(name="broken", steps=["ghost"])])
        doc = compile_workflow("broken", m)
        assert doc["steps"] == [{"agent": "ghost", "declared": False}]

    def test_unknown_workflow_raises(self, manifest: Manifest) -> None:
        with pytest.raises(HarnessPlanError, match="Unknown workflow"):
            compile_workflow("nope", manifest)

    def test_render_is_deterministic(self, manifest: Manifest) -> None:
        assert render(compile_workflow("mini", manifest)) == render(
            compile_workflow("mini", manifest)
        )

    def test_artifact_carries_no_machine_state(self, manifest: Manifest) -> None:
        """No absolute paths, no local install state, no timestamps."""
        text = render(compile_workflow("mini", manifest))
        assert "/Users/" not in text and "/home/" not in text
        for leaked in ("skills_found", "mcp_registered", "definition_path", "created_at"):
            assert leaked not in text

    def test_alias_compiles_to_the_canonical_name(self, manifest: Manifest) -> None:
        m = Manifest(
            agents=manifest.agents,
            workflows=[WorkflowEntry(name="survey", steps=["scout"])],
        )
        assert compile_workflow("literature-review", m)["workflow"] == "survey"


class TestArtifacts:
    def test_write_then_check_is_clean(self, manifest: Manifest, tmp_path: Path) -> None:
        write_artifacts(manifest=manifest, root=tmp_path)
        assert all(entry.ok for entry in check_artifacts(manifest=manifest, root=tmp_path))

    def test_write_covers_every_workflow(self, manifest: Manifest, tmp_path: Path) -> None:
        written = write_artifacts(manifest=manifest, root=tmp_path)
        assert sorted(p.stem for p in written) == ["mini", "solo"]

    def test_missing_artifact_is_reported(self, manifest: Manifest, tmp_path: Path) -> None:
        entries = check_artifacts(manifest=manifest, root=tmp_path)
        assert {e.status for e in entries} == {"missing"}

    def test_edited_artifact_is_stale(self, manifest: Manifest, tmp_path: Path) -> None:
        write_artifacts(manifest=manifest, root=tmp_path)
        path = artifact_path("mini", tmp_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["steps"][0]["max_turns"] = 999
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        stale = [e for e in check_artifacts(manifest=manifest, root=tmp_path) if not e.ok]

        assert [e.workflow for e in stale] == ["mini"]
        assert stale[0].status == "stale"

    def test_manifest_change_makes_the_artifact_stale(
        self, manifest: Manifest, tmp_path: Path
    ) -> None:
        """The whole point: editing the routing table must fail --check."""
        write_artifacts(manifest=manifest, root=tmp_path)
        manifest.agents[0].model = "opus"

        stale = [e for e in check_artifacts(manifest=manifest, root=tmp_path) if not e.ok]

        assert {e.workflow for e in stale} == {"mini", "solo"}

    def test_write_is_idempotent(self, manifest: Manifest, tmp_path: Path) -> None:
        write_artifacts(manifest=manifest, root=tmp_path)
        first = artifact_path("mini", tmp_path).read_text(encoding="utf-8")
        write_artifacts(manifest=manifest, root=tmp_path)
        assert artifact_path("mini", tmp_path).read_text(encoding="utf-8") == first

    def test_single_workflow_target(self, manifest: Manifest, tmp_path: Path) -> None:
        written = write_artifacts("mini", manifest=manifest, root=tmp_path)
        assert [p.stem for p in written] == ["mini"]

    def test_write_leaves_no_scratch_files(self, manifest: Manifest, tmp_path: Path) -> None:
        write_artifacts(manifest=manifest, root=tmp_path)
        directory = artifact_path("mini", tmp_path).parent
        assert all(p.suffix == ".json" for p in directory.iterdir())

    def test_targets_default_to_every_workflow(self, manifest: Manifest) -> None:
        assert workflow_targets(None, manifest) == ["mini", "solo"]


class TestShippedManifestCompiles:
    def test_every_shipped_workflow_compiles(self) -> None:
        from maglab.core.manifest import load_manifest

        manifest = load_manifest()
        for name in manifest.workflow_names():
            doc = compile_workflow(name, manifest)
            assert doc["steps"], f"{name} compiled to zero steps"
            assert all(s.get("declared") for s in doc["steps"]), f"{name} names an undeclared agent"
