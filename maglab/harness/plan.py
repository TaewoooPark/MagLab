"""Deterministic harness planning — manifest in, execution plan out.

Nothing here calls an LLM, opens a socket, or depends on an optional extra.
That is deliberate: ``doctor``, ``compile``, ``run --dry-run``, ``worker`` and
``pi-tool`` all render from these plans, so their output is reproducible and can
be asserted on in tests without a backend.

A plan resolves four things the manifest only names:

- the model *tier* (``haiku``) to the concrete model id the runner would use,
- each declared skill to the SKILL.md that exists on disk (or records it as
  missing, rather than silently dropping the context),
- each declared MCP server to whether it is registered in ``.maglab/mcp.json``,
- the subagent name to the ``agents/*.md`` definition that actually backs it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.core.manifest import AgentEntry, Manifest, load_manifest

# Ergonomic names accepted on the CLI, mapped to the manifest's own workflow
# names. The manifest stays the single source of truth (§5.16); these only save
# the user from having to know that "survey" is the five-step literature run.
WORKFLOW_ALIASES: dict[str, str] = {
    "literature-review": "survey",
    "lit-review": "survey",
    "deepresearch": "deep-research",
    "research": "deep-research",
}

# Model tiers understood by SubagentRunner._resolve_model. Kept in step with it
# so a dry-run reports the model the live run would actually use.
_TIER_MODELS: dict[str, str] = {
    "opus": "claude-opus-4-7",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}


class HarnessPlanError(ValueError):
    """A workflow or agent could not be planned from the manifest."""


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def resolve_workflow_name(name: str, manifest: Manifest | None = None) -> str:
    """Map an ergonomic workflow name onto the manifest's own name.

    Manifest names win over aliases, so adding a real ``literature-review``
    workflow later would take precedence without a code change.
    """
    manifest = manifest if manifest is not None else load_manifest()
    key = name.strip().lower()
    if manifest.workflow(key) is not None:
        return key
    return WORKFLOW_ALIASES.get(key, key)


def resolve_model(tier: str) -> str:
    """Resolve a manifest model tier to the concrete model id."""
    key = (tier or "inherit").strip().lower()
    if key == "inherit":
        return ""
    return _TIER_MODELS.get(key, tier)


def _registered_mcp_servers(root: Path | None = None) -> set[str]:
    """Return MCP server names registered in the workspace or user registry."""
    base = root if root is not None else Path.cwd()
    candidates = [
        base / ".maglab" / "mcp.json",
        Path.home() / ".config" / "maglab" / "mcp.json",
    ]
    found: set[str] = set()
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A malformed registry is reported by `harness doctor`; planning
            # must not crash over it.
            continue
        servers = data.get("servers")
        if isinstance(servers, dict):
            found.update(str(k) for k in servers)
    return found


def _skill_index() -> dict[str, Path]:
    """Return skill name → SKILL.md path for every discoverable skill."""
    from maglab.core.skills import SkillLoader

    loader = SkillLoader()
    index: dict[str, Path] = {}
    for meta in loader.discover():
        skill_md = meta.skill_dir / "SKILL.md"
        if skill_md.is_file():
            index[meta.name] = skill_md
    return index


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


@dataclass
class WorkerPlan:
    """Everything needed to run — or explain — one subagent step."""

    agent: str
    description: str = ""
    model: str = "inherit"
    resolved_model: str = ""
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    skills_found: list[str] = field(default_factory=list)
    skills_missing: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    mcp_registered: list[str] = field(default_factory=list)
    mcp_unregistered: list[str] = field(default_factory=list)
    max_turns: int = 10
    context: str = "isolated"
    definition_path: str = ""
    task: str = ""

    @property
    def ready(self) -> bool:
        """True when the agent has a backing definition and all declared skills."""
        return bool(self.definition_path) and not self.skills_missing

    def command(self) -> list[str]:
        """The equivalent ``maglab harness worker`` invocation for this step."""
        cmd = ["maglab", "harness", "worker", self.agent]
        if self.task:
            cmd += ["--task", self.task]
        return cmd

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "description": self.description,
            "model": self.model,
            "resolved_model": self.resolved_model,
            "tools": list(self.tools),
            "skills": list(self.skills),
            "skills_found": list(self.skills_found),
            "skills_missing": list(self.skills_missing),
            "mcp_servers": list(self.mcp_servers),
            "mcp_registered": list(self.mcp_registered),
            "mcp_unregistered": list(self.mcp_unregistered),
            "max_turns": self.max_turns,
            "context": self.context,
            "definition_path": self.definition_path,
            "ready": self.ready,
            "command": self.command(),
        }


@dataclass
class WorkflowPlan:
    """An ordered set of :class:`WorkerPlan` steps for one named workflow."""

    name: str
    requested_name: str = ""
    description: str = ""
    topic: str = ""
    steps: list[WorkerPlan] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return bool(self.steps) and all(step.ready for step in self.steps)

    @property
    def blockers(self) -> list[str]:
        """Reasons this plan cannot run at all.

        Kept strictly in step with :attr:`ready`: a plan reported ready with a
        non-empty blocker list would be telling the caller two different things.
        Anything that degrades a run without preventing it belongs in
        :attr:`warnings`.
        """
        reasons: list[str] = []
        for step in self.steps:
            if not step.definition_path:
                reasons.append(f"{step.agent}: no agents/{step.agent}.md definition")
            for skill in step.skills_missing:
                reasons.append(f"{step.agent}: skill {skill!r} not found")
        return reasons

    @property
    def warnings(self) -> list[str]:
        """Conditions that degrade a run without preventing it.

        An unregistered MCP server does not stop local execution — the subagent
        runner issues a plain completion — but the agent will not have the tools
        it declares, and the PI handoff genuinely needs them.
        """
        notes: list[str] = []
        for step in self.steps:
            for server in step.mcp_unregistered:
                notes.append(
                    f"{step.agent}: MCP server {server!r} not registered (maglab mcp add {server})"
                )
        return notes

    def local_run_plan(self) -> list[dict[str, Any]]:
        """The local worker subprocess contract, one entry per step."""
        return [step.to_dict() for step in self.steps]

    def pi_agents_workflow_payload(self) -> dict[str, Any]:
        """Topic-bound payload for PI's ``workflow`` tool."""
        return {
            "workflow": self.name,
            "input": self.topic,
            "steps": [
                {
                    "agent": step.agent,
                    "model": step.resolved_model or step.model,
                    "tools": list(step.tools),
                    "skills": list(step.skills),
                    "max_turns": step.max_turns,
                }
                for step in self.steps
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.name,
            "requested": self.requested_name or self.name,
            "description": self.description,
            "topic": self.topic,
            "ready": self.ready,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "steps": [step.agent for step in self.steps],
            "local_run_plan": self.local_run_plan(),
            "pi_agents_workflow_payload": self.pi_agents_workflow_payload(),
        }


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_worker(
    entry: AgentEntry,
    *,
    skills: dict[str, Path],
    registered_mcp: set[str],
    definition_paths: dict[str, str],
    task: str = "",
) -> WorkerPlan:
    declared_skills = list(entry.skills)
    found = [s for s in declared_skills if s in skills]
    missing = [s for s in declared_skills if s not in skills]
    declared_mcp = list(entry.mcp_servers)
    return WorkerPlan(
        agent=entry.name,
        description=entry.description,
        model=entry.model,
        resolved_model=resolve_model(entry.model),
        tools=list(entry.tools),
        skills=declared_skills,
        skills_found=found,
        skills_missing=missing,
        mcp_servers=declared_mcp,
        mcp_registered=[m for m in declared_mcp if m in registered_mcp],
        mcp_unregistered=[m for m in declared_mcp if m not in registered_mcp],
        max_turns=entry.max_turns,
        context=entry.context,
        definition_path=definition_paths.get(entry.name, ""),
        task=task,
    )


def _definition_paths() -> dict[str, str]:
    """Return subagent name → the agents/*.md file that backs it."""
    from maglab.core.subagents import load_subagent_defs

    return {name: defn.source_file for name, defn in load_subagent_defs().items()}


def build_workflow_plan(
    name: str,
    *,
    topic: str = "",
    manifest: Manifest | None = None,
    root: Path | None = None,
) -> WorkflowPlan:
    """Build the execution plan for a named workflow.

    Raises:
        HarnessPlanError: The workflow is not declared in the manifest.
    """
    manifest = manifest if manifest is not None else load_manifest()
    canonical = resolve_workflow_name(name, manifest)
    entry = manifest.workflow(canonical)
    if entry is None:
        available = sorted(set(manifest.workflow_names()) | set(WORKFLOW_ALIASES))
        raise HarnessPlanError(f"Unknown workflow {name!r}. Available: {', '.join(available)}")

    skills = _skill_index()
    registered = _registered_mcp_servers(root)
    definitions = _definition_paths()

    steps: list[WorkerPlan] = []
    for agent_name in entry.steps:
        agent_entry = manifest.agent(agent_name) or AgentEntry(name=agent_name)
        steps.append(
            _build_worker(
                agent_entry,
                skills=skills,
                registered_mcp=registered,
                definition_paths=definitions,
                task=topic,
            )
        )

    return WorkflowPlan(
        name=canonical,
        requested_name=name,
        description=entry.description,
        topic=topic,
        steps=steps,
    )


def build_worker_plan(
    agent: str,
    *,
    task: str = "",
    manifest: Manifest | None = None,
    root: Path | None = None,
) -> WorkerPlan:
    """Build the execution plan for a single subagent.

    Raises:
        HarnessPlanError: The agent is not declared in the manifest.
    """
    manifest = manifest if manifest is not None else load_manifest()
    entry = manifest.agent(agent.strip())
    if entry is None:
        raise HarnessPlanError(
            f"Unknown agent {agent!r}. Available: {', '.join(sorted(manifest.agent_names()))}"
        )
    return _build_worker(
        entry,
        skills=_skill_index(),
        registered_mcp=_registered_mcp_servers(root),
        definition_paths=_definition_paths(),
        task=task,
    )
