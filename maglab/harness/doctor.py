"""Harness readiness report.

Answers one question: if you ran a workflow right now, what would stop it?

Every check is deterministic and offline. Nothing here contacts a provider or
starts a subagent — a readiness report that needed credentials to tell you
whether you had credentials would be useless.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.core.manifest import Manifest, load_manifest
from maglab.harness.plan import _registered_mcp_servers, _skill_index

# A PI install only helps if the `workflow` tool is actually exposed, which
# comes from the pi-agents extension rather than the base binary.
_PI_WORKFLOW_TOOL = "workflow"


@dataclass
class Check:
    """One readiness check."""

    name: str
    ok: bool
    detail: str = ""
    blocking: bool = True
    """False for checks that only gate the optional PI handoff path."""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "blocking": self.blocking}


@dataclass
class DoctorReport:
    """Aggregate readiness across the manifest, workspace and environment."""

    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when nothing blocking is failing."""
        return all(c.ok for c in self.checks if c.blocking)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
            "failing": [c.name for c in self.failures],
        }


def _pi_binary() -> str:
    """Return the PI binary path, preferring a project-local install."""
    local = Path(".pi") / "npm" / "node_modules" / ".bin" / "pi"
    if local.is_file():
        return str(local)
    return shutil.which("pi") or ""


def _pi_has_workflow_tool(binary: str) -> tuple[bool, str]:
    """Return whether PI exposes a ``workflow`` tool, and what was observed.

    ``pi list`` reports installed extension packages; the ``workflow`` tool ships
    with pi-agents rather than the base binary, so a bare PI install cannot run
    the handoff even though the binary is present.
    """
    if not binary:
        return False, "PI binary not found"
    try:
        proc = subprocess.run(
            [binary, "list"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run `{binary} list`: {exc}"
    output = f"{proc.stdout}\n{proc.stderr}".lower()
    if "no packages installed" in output:
        return False, "PI has no extensions installed (pi-agents provides the workflow tool)"
    if _PI_WORKFLOW_TOOL in output:
        return True, "pi-agents workflow tool available"
    return False, "no extension exposing a `workflow` tool was listed"


def _backend_check() -> Check:
    """Report whether an LLM backend is configured for local execution."""
    from maglab.config import ConfigError, load_config

    try:
        config = load_config()
    except ConfigError as exc:
        return Check("llm-backend", False, str(exc).splitlines()[0])

    mode = config.backend.mode
    if mode == "delegated_cli":
        tool = config.backend.delegated_cli.tool
        found = shutil.which(tool)
        return Check(
            "llm-backend",
            bool(found),
            f"delegated_cli → {tool}" + ("" if found else " (not on PATH)"),
        )
    if mode == "local":
        return Check("llm-backend", True, f"local → {config.backend.local.model}")

    from maglab.llm.auth import get_api_key

    provider = config.backend.api.provider
    has_key = bool(get_api_key(provider))
    return Check(
        "llm-backend",
        has_key,
        f"api → {provider}" + ("" if has_key else " (no API key found)"),
    )


def run_doctor(manifest: Manifest | None = None, *, root: Path | None = None) -> DoctorReport:
    """Build the harness readiness report."""
    checks: list[Check] = []
    manifest = manifest if manifest is not None else load_manifest()

    # 1. Manifest itself
    checks.append(
        Check(
            "manifest",
            bool(manifest.agents and manifest.workflows),
            f"{len(manifest.agents)} agents, {len(manifest.workflows)} workflows, "
            f"{len(manifest.skills)} skills, {len(manifest.mcp_servers)} mcp servers",
        )
    )

    # 2. Every workflow step names a declared agent
    declared = set(manifest.agent_names())
    dangling = sorted(
        {f"{w.name}→{s}" for w in manifest.workflows for s in w.steps if s not in declared}
    )
    checks.append(
        Check(
            "workflow-steps",
            not dangling,
            "all steps resolve to declared agents"
            if not dangling
            else f"undeclared: {', '.join(dangling)}",
        )
    )

    # 3. Every declared agent is backed by an agents/*.md definition
    from maglab.core.subagents import load_subagent_defs

    defs = load_subagent_defs()
    missing_defs = sorted(declared - set(defs))
    checks.append(
        Check(
            "agent-definitions",
            not missing_defs,
            f"{len(declared & set(defs))}/{len(declared)} agents backed by agents/*.md"
            + ("" if not missing_defs else f" — missing: {', '.join(missing_defs)}"),
        )
    )

    # 4. Every skill an agent declares exists on disk
    skills = _skill_index()
    wanted = sorted({s for a in manifest.agents for s in a.skills})
    missing_skills = [s for s in wanted if s not in skills]
    checks.append(
        Check(
            "agent-skills",
            not missing_skills,
            f"{len(wanted) - len(missing_skills)}/{len(wanted)} declared skills found"
            + ("" if not missing_skills else f" — missing: {', '.join(missing_skills)}"),
        )
    )

    # 5. MCP servers the agents ask for are registered
    registered = _registered_mcp_servers(root)
    wanted_mcp = sorted({m for a in manifest.agents for m in a.mcp_servers})
    missing_mcp = [m for m in wanted_mcp if m not in registered]
    checks.append(
        Check(
            "mcp-servers",
            not missing_mcp,
            f"{len(wanted_mcp) - len(missing_mcp)}/{len(wanted_mcp)} registered"
            + (
                ""
                if not missing_mcp
                else f" — run `maglab mcp add {missing_mcp[0]}` (missing: {', '.join(missing_mcp)})"
            ),
        )
    )

    # 6. A backend that local execution could actually use
    checks.append(_backend_check())

    # 7. PI handoff path — optional, never blocking
    binary = _pi_binary()
    checks.append(
        Check(
            "pi-binary",
            bool(binary),
            binary or "not found (only needed for --execute-pi)",
            blocking=False,
        )
    )
    has_tool, tool_detail = _pi_has_workflow_tool(binary)
    checks.append(Check("pi-workflow-tool", has_tool, tool_detail, blocking=False))

    return DoctorReport(checks=checks)
