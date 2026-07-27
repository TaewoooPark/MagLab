"""PI handoff — the command and payload that hand a plan to an external PI run.

MagLab does not embed PI. It prepares an exact, inspectable invocation and hands
it over, so the boundary is visible: everything up to the handoff is
deterministic MagLab planning, everything after it belongs to PI.

The handoff is generated whether or not PI is installed — reading the command
you *would* run is useful on a machine that cannot run it. Actually executing it
is gated on the environment and is never simulated.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maglab.harness.plan import HarnessPlanError, WorkflowPlan, build_workflow_plan

# The documented invocation: JSON output, MagLab's payload only, and the single
# `workflow` tool that pi-agents exposes.
_PI_BASE_ARGS = ["--mode", "json", "--no-builtin-tools", "--tools", "workflow", "-p"]


class PiUnavailableError(RuntimeError):
    """PI cannot run the handoff in this environment."""


@dataclass
class Handoff:
    """A concrete PI invocation for a prepared plan."""

    binary: str
    command: list[str]
    prompt: str
    available: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "binary": self.binary,
            "command": list(self.command),
            "prompt": self.prompt,
            "available": self.available,
            "reason": self.reason,
        }

    def shell_command(self) -> str:
        """The invocation as a copy-pasteable shell line."""
        import shlex

        return " ".join(shlex.quote(part) for part in self.command)


def find_pi_binary() -> str:
    """Return the PI binary, preferring a project-local install."""
    local = Path(".pi") / "npm" / "node_modules" / ".bin" / "pi"
    if local.is_file():
        return str(local)
    return shutil.which("pi") or ""


def build_prompt(plan: WorkflowPlan) -> str:
    """Build the prompt that carries the plan to PI's ``workflow`` tool.

    The payload is embedded verbatim so the receiving side does not have to
    re-derive the routing table — and so the prompt is reproducible from the
    manifest alone.
    """
    payload = json.dumps(plan.pi_agents_workflow_payload(), ensure_ascii=False, indent=2)
    topic = plan.topic or "(no topic supplied)"
    return (
        f"Run the MagLab `{plan.name}` workflow for: {topic}\n\n"
        "Call the `workflow` tool with exactly this payload — the agent order, "
        "model tiers and tool allowlists come from MagLab's harness manifest and "
        "must not be substituted:\n\n"
        f"```json\n{payload}\n```\n"
    )


def build_handoff(plan: WorkflowPlan, *, binary: str | None = None) -> Handoff:
    """Build the PI invocation for *plan*, whether or not PI can run it here."""
    resolved = binary if binary is not None else find_pi_binary()
    prompt = build_prompt(plan)
    command = [resolved or "pi", *_PI_BASE_ARGS, prompt]
    if not resolved:
        return Handoff(
            binary="",
            command=command,
            prompt=prompt,
            available=False,
            reason="PI binary not found on PATH or in .pi/npm/node_modules/.bin",
        )
    return Handoff(binary=resolved, command=command, prompt=prompt, available=True)


def execute_handoff(handoff: Handoff, *, timeout: float = 900.0) -> dict[str, Any]:
    """Run a prepared handoff.

    Raises:
        PiUnavailableError: PI is not installed. The caller must surface this
            rather than pretending the workflow ran.
    """
    if not handoff.available:
        raise PiUnavailableError(handoff.reason or "PI is not available")
    try:
        proc = subprocess.run(
            handoff.command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PiUnavailableError(f"PI did not complete within {timeout:.0f}s") from exc
    except OSError as exc:
        raise PiUnavailableError(f"Could not start PI: {exc}") from exc

    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def pi_tool_payload(payload: str | dict[str, Any]) -> dict[str, Any]:
    """Resolve a PI-callable ``{"workflow", "input"}`` payload into a plan.

    This is the wrapper PI itself calls: it takes the minimal request PI knows
    how to build and returns the full MagLab plan for it.

    Raises:
        HarnessPlanError: The payload is malformed or names an unknown workflow.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HarnessPlanError(f"payload is not valid JSON: {exc}") from exc
    else:
        data = payload

    if not isinstance(data, dict):
        raise HarnessPlanError("payload must be a JSON object")

    workflow = data.get("workflow")
    if not isinstance(workflow, str) or not workflow.strip():
        raise HarnessPlanError('payload must contain a non-empty "workflow" string')

    topic = data.get("input", "")
    if not isinstance(topic, str):
        raise HarnessPlanError('payload "input" must be a string')

    plan = build_workflow_plan(workflow, topic=topic)
    return {
        "ok": plan.ready,
        "workflow": plan.name,
        "requested": plan.requested_name,
        "input": plan.topic,
        "ready": plan.ready,
        "blockers": plan.blockers,
        "warnings": plan.warnings,
        "payload": plan.pi_agents_workflow_payload(),
        "local_run_plan": plan.local_run_plan(),
    }
