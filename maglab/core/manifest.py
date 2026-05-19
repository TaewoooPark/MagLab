"""Harness manifest loader — declarative routing table (§5.16).

Reads ``harness.manifest.json`` at startup.  Contains:
- Registered subagents  (name, description, model, tools, …)
- Skills                (name, path)
- MCP servers           (name, url / command)
- Named workflows       (name → ordered list of subagent names)
- ModelRouter stage→model mapping

The manifest is purely additive meta-data — nothing crashes when the file
is absent.  Callers always get a ``Manifest`` instance back; it is just
empty when no file is found.

Usage::

    from maglab.core.manifest import load_manifest
    m = load_manifest()               # uses the repo-root default
    router = m.build_model_router()   # -> ModelRouter
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Default location: repo root / harness.manifest.json
_DEFAULT_MANIFEST_PATH = Path(__file__).parent.parent.parent / "harness.manifest.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AgentEntry:
    """A single subagent registration entry."""

    name: str
    description: str = ""
    model: str = "inherit"
    tools: list[str] = field(default_factory=list)
    max_turns: int = 10
    context: str = "isolated"
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillEntry:
    """A single skill registration entry."""

    name: str
    path: str = ""
    description: str = ""


@dataclass
class McpServerEntry:
    """A single MCP server registration entry."""

    name: str
    url: str = ""
    command: str = ""


@dataclass
class WorkflowEntry:
    """A named workflow — ordered list of subagent names."""

    name: str
    steps: list[str] = field(default_factory=list)


@dataclass
class Manifest:
    """Parsed harness manifest.

    All fields default to empty — the Manifest is a no-op if the file is
    absent or empty.
    """

    agents: list[AgentEntry] = field(default_factory=list)
    skills: list[SkillEntry] = field(default_factory=list)
    mcp_servers: list[McpServerEntry] = field(default_factory=list)
    workflows: list[WorkflowEntry] = field(default_factory=list)
    model_routing: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def build_model_router(self) -> Any:
        """Build a :class:`ModelRouter` from ``self.model_routing``.

        Returns a default router when ``model_routing`` is empty.
        """
        from maglab.llm.base import ModelRouter  # deferred to avoid circular import

        return ModelRouter(routing_config=self.model_routing or None)

    def agent_names(self) -> list[str]:
        """Return a list of registered agent names."""
        return [a.name for a in self.agents]

    def skill_names(self) -> list[str]:
        """Return a list of registered skill names."""
        return [s.name for s in self.skills]

    def mcp_server_names(self) -> list[str]:
        """Return a list of registered MCP server names."""
        return [m.name for m in self.mcp_servers]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_manifest(path: str | Path | None = None) -> Manifest:
    """Load and parse the harness manifest JSON file.

    Parameters
    ----------
    path:
        Path to ``harness.manifest.json``.  When ``None`` the default location
        (repo root) is tried.  A missing or unreadable file is treated as an
        empty manifest — the function never raises.

    Returns
    -------
    Manifest
        Parsed manifest.  All fields are empty if no file was found.
    """
    resolved = Path(path) if path is not None else _DEFAULT_MANIFEST_PATH

    if not resolved.exists():
        log.debug("Manifest not found at %s — using empty manifest", resolved)
        return Manifest()

    try:
        raw: dict[str, Any] = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to read manifest at %s: %s — using empty manifest", resolved, exc)
        return Manifest()

    return _parse(raw, resolved)


def _parse(raw: dict[str, Any], source: Path) -> Manifest:
    """Parse a raw manifest dict into a ``Manifest`` dataclass."""
    agents: list[AgentEntry] = []
    for entry in raw.get("agents", []):
        if not isinstance(entry, dict):
            continue
        agents.append(
            AgentEntry(
                name=str(entry.get("name", "")),
                description=str(entry.get("description", "")),
                model=str(entry.get("model", "inherit")),
                tools=list(entry.get("tools", [])),
                max_turns=int(entry.get("max_turns", 10)),
                context=str(entry.get("context", "isolated")),
                skills=list(entry.get("skills", [])),
                mcp_servers=list(entry.get("mcp_servers", [])),
                metadata=dict(entry.get("metadata", {})),
            )
        )

    skills: list[SkillEntry] = []
    for entry in raw.get("skills", []):
        if not isinstance(entry, dict):
            continue
        skills.append(
            SkillEntry(
                name=str(entry.get("name", "")),
                path=str(entry.get("path", "")),
                description=str(entry.get("description", "")),
            )
        )

    mcp_servers: list[McpServerEntry] = []
    for entry in raw.get("mcp_servers", []):
        if not isinstance(entry, dict):
            continue
        mcp_servers.append(
            McpServerEntry(
                name=str(entry.get("name", "")),
                url=str(entry.get("url", "")),
                command=str(entry.get("command", "")),
            )
        )

    workflows: list[WorkflowEntry] = []
    for entry in raw.get("workflows", []):
        if not isinstance(entry, dict):
            continue
        workflows.append(
            WorkflowEntry(
                name=str(entry.get("name", "")),
                steps=list(entry.get("steps", [])),
            )
        )

    model_routing: dict[str, str] = {}
    routing_raw = raw.get("model_routing", {})
    if isinstance(routing_raw, dict):
        model_routing = {str(k): str(v) for k, v in routing_raw.items()}

    metadata: dict[str, Any] = dict(raw.get("metadata", {}))

    log.debug(
        "Manifest loaded from %s: %d agents, %d skills, %d mcp_servers, %d workflows",
        source,
        len(agents),
        len(skills),
        len(mcp_servers),
        len(workflows),
    )

    return Manifest(
        agents=agents,
        skills=skills,
        mcp_servers=mcp_servers,
        workflows=workflows,
        model_routing=model_routing,
        metadata=metadata,
    )
