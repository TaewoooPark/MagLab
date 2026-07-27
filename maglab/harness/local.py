"""Local workflow execution — run a plan through MagLab's own subagent runner.

No second agent framework is involved. ``SubagentRunner`` already loads the
``agents/*.md`` definitions, isolates each worker's context, parses structured
output and runs the four-layer verifier, so routing a harness plan through it
means local execution inherits every one of those guarantees instead of
re-implementing them behind a different engine.

Each step receives the topic plus a compact digest of what earlier steps
returned, which is what makes a workflow more than N independent calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from maglab.harness.plan import WorkflowPlan

log = logging.getLogger(__name__)

# How much of an upstream result to carry forward. Full results would blow the
# context out by the third step of a six-step workflow.
_DIGEST_CHARS = 2000


class LocalExecutionError(RuntimeError):
    """Local execution could not start."""


def _skill_context(step: Any) -> str:
    """Return the SKILL.md bodies this worker declares, for JIT injection."""
    from maglab.core.skills import SkillLoader

    if not step.skills_found:
        return ""
    loader = SkillLoader()
    blocks: list[str] = []
    for name in step.skills_found:
        skill = loader.load(name)
        body = getattr(skill, "body", "") if skill is not None else ""
        if body:
            blocks.append(f"### Skill: {name}\n\n{body}")
    return "\n\n".join(blocks)


def _digest(results: list[dict[str, Any]]) -> str:
    """Compact summary of upstream step results for the next worker."""
    if not results:
        return ""
    lines: list[str] = []
    for entry in results:
        payload = json.dumps(entry.get("result", {}), ensure_ascii=False)
        if len(payload) > _DIGEST_CHARS:
            payload = payload[:_DIGEST_CHARS] + " …(truncated)"
        lines.append(f"#### {entry['agent']} → {entry.get('verify_status', 'unknown')}\n{payload}")
    return "## Upstream results\n\n" + "\n\n".join(lines)


def _build_runner() -> Any:
    """Construct a SubagentRunner on the configured backend."""
    from maglab.config import ConfigError, load_config
    from maglab.core.subagents import SubagentRunner, load_subagent_defs
    from maglab.llm.factory import create_llm_backend

    try:
        config = load_config()
    except ConfigError as exc:
        raise LocalExecutionError(str(exc)) from exc

    try:
        backend = create_llm_backend(config)
    except Exception as exc:  # noqa: BLE001 - surfaced as an actionable message
        raise LocalExecutionError(
            f"No usable LLM backend: {exc}. Run `maglab harness doctor` for details."
        ) from exc

    return SubagentRunner(defs=load_subagent_defs(), backend=backend)


def execute_locally(
    plan: WorkflowPlan,
    *,
    max_steps: int | None = None,
    runner: Any | None = None,
) -> dict[str, Any]:
    """Run *plan* step by step and return the collected results.

    Args:
        plan: A ready workflow plan.
        max_steps: Stop after this many steps. The runner issues one completion
            per step, so this bounds steps rather than turns inside a step.
        runner: Injected ``SubagentRunner`` (tests supply a fake).

    Returns:
        ``{"ok", "steps", "completed", "planned"}``. A step that fails
        verification stops the run — later steps consume upstream output, so
        continuing past a failure would build on an unverified result.
    """
    active = runner if runner is not None else _build_runner()
    planned = list(plan.steps)
    if max_steps is not None:
        planned = planned[:max_steps]

    results: list[dict[str, Any]] = []
    for step in planned:
        task_parts = [f"Topic: {plan.topic}" if plan.topic else "Topic: (not supplied)"]
        digest = _digest(results)
        if digest:
            task_parts.append(digest)
        task = "\n\n".join(task_parts)

        try:
            structured = active.run(step.agent, task, extra_context=_skill_context(step))
        except Exception as exc:  # noqa: BLE001 - recorded per step, not fatal to the report
            log.warning("Harness step %s failed: %s", step.agent, exc)
            results.append(
                {"agent": step.agent, "ok": False, "error": str(exc), "verify_status": "failed"}
            )
            break

        verify_status = str(structured.get("_verify_status", "unknown"))
        status = str(structured.get("status", "success"))
        ok = verify_status != "failed" and status != "failed"
        results.append(
            {
                "agent": step.agent,
                "ok": ok,
                "status": status,
                "verify_status": verify_status,
                "warnings": list(structured.get("_warnings") or []),
                "result": {k: v for k, v in structured.items() if not k.startswith("_")},
            }
        )
        if not ok:
            # Downstream steps read upstream results; continuing would layer new
            # work on top of output that did not verify.
            break

    return {
        "ok": bool(results) and all(entry["ok"] for entry in results),
        "planned": len(plan.steps),
        "completed": len(results),
        "steps": results,
    }


def write_run_artifact(
    plan: WorkflowPlan,
    execution: dict[str, Any],
    *,
    root: Path | None = None,
) -> Path:
    """Persist a local run under ``.maglab/artifacts/`` and return the path."""
    from maglab.core.atomic import atomic_write_text

    base = root if root is not None else Path.cwd()
    target = base / ".maglab" / "artifacts" / f"harness-{plan.name}.json"
    atomic_write_text(
        target,
        json.dumps(
            {"workflow": plan.name, "topic": plan.topic, "execution": execution},
            ensure_ascii=False,
            indent=2,
        ),
    )
    return target
