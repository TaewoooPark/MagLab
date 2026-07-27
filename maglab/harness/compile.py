"""Compile manifest workflows into ``.pi/workflows/*.json`` drift artifacts.

These files are *not* the live execution payload — that is
``pi_agents_workflow_payload`` from ``harness run --dry-run``, which is bound to
a topic. What is written here is the compiled shape of a workflow: which agents,
in what order, on which model tier, with which tools and skills.

The point is drift detection. A committed artifact plus ``harness compile
--check`` turns "someone edited the manifest and nobody noticed" into a failing
command, so the routing table cannot silently diverge from what was reviewed.

Everything about the artifact is therefore machine-independent: no absolute
paths, no "is this skill installed here" state, no timestamps. The same manifest
compiles to byte-identical JSON on any machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maglab.core.atomic import atomic_write_text
from maglab.core.manifest import Manifest, load_manifest
from maglab.harness.plan import HarnessPlanError, resolve_model, resolve_workflow_name

ARTIFACT_DIR = Path(".pi") / "workflows"


def artifact_path(name: str, root: Path | None = None) -> Path:
    """Return the drift-artifact path for a compiled workflow."""
    base = root if root is not None else Path.cwd()
    return base / ARTIFACT_DIR / f"{name}.json"


def compile_workflow(name: str, manifest: Manifest | None = None) -> dict[str, Any]:
    """Compile one workflow into its canonical, machine-independent form.

    Raises:
        HarnessPlanError: The workflow is not declared in the manifest.
    """
    manifest = manifest if manifest is not None else load_manifest()
    canonical = resolve_workflow_name(name, manifest)
    entry = manifest.workflow(canonical)
    if entry is None:
        raise HarnessPlanError(
            f"Unknown workflow {name!r}. Available: {', '.join(sorted(manifest.workflow_names()))}"
        )

    steps: list[dict[str, Any]] = []
    for agent_name in entry.steps:
        agent = manifest.agent(agent_name)
        if agent is None:
            # Recorded rather than dropped: a workflow naming an undeclared
            # agent is exactly the drift this artifact exists to catch.
            steps.append({"agent": agent_name, "declared": False})
            continue
        steps.append(
            {
                "agent": agent.name,
                "declared": True,
                "model": agent.model,
                "resolved_model": resolve_model(agent.model),
                "tools": sorted(agent.tools),
                "skills": sorted(agent.skills),
                "mcp_servers": sorted(agent.mcp_servers),
                "max_turns": agent.max_turns,
                "context": agent.context,
            }
        )

    return {
        "workflow": canonical,
        "description": entry.description,
        "manifest_version": str(manifest.metadata.get("version", "")),
        "steps": steps,
    }


def render(document: dict[str, Any]) -> str:
    """Serialise a compiled workflow deterministically."""
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@dataclass
class DriftEntry:
    """One workflow's agreement (or not) with its committed artifact."""

    workflow: str
    status: str
    """``ok``, ``missing``, ``stale`` or ``unreadable``."""
    path: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {"workflow": self.workflow, "status": self.status, "path": self.path}


def workflow_targets(name: str | None, manifest: Manifest | None = None) -> list[str]:
    """Return the workflows to operate on — one, or all when *name* is None."""
    manifest = manifest if manifest is not None else load_manifest()
    if name:
        return [resolve_workflow_name(name, manifest)]
    return sorted(manifest.workflow_names())


def write_artifacts(
    name: str | None = None,
    *,
    manifest: Manifest | None = None,
    root: Path | None = None,
) -> list[Path]:
    """Write (or refresh) the drift artifacts and return the paths."""
    manifest = manifest if manifest is not None else load_manifest()
    written: list[Path] = []
    for workflow in workflow_targets(name, manifest):
        path = artifact_path(workflow, root)
        atomic_write_text(path, render(compile_workflow(workflow, manifest)))
        written.append(path)
    return written


def check_artifacts(
    name: str | None = None,
    *,
    manifest: Manifest | None = None,
    root: Path | None = None,
) -> list[DriftEntry]:
    """Compare committed artifacts against a fresh compile."""
    manifest = manifest if manifest is not None else load_manifest()
    results: list[DriftEntry] = []
    for workflow in workflow_targets(name, manifest):
        path = artifact_path(workflow, root)
        expected = render(compile_workflow(workflow, manifest))
        if not path.is_file():
            results.append(DriftEntry(workflow, "missing", str(path)))
            continue
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError:
            results.append(DriftEntry(workflow, "unreadable", str(path)))
            continue
        results.append(DriftEntry(workflow, "ok" if actual == expected else "stale", str(path)))
    return results
