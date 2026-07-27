"""Record a prepared harness run as a W3C PROV activity.

Recorded at *preparation* time rather than after execution: a run that is
interrupted, or handed to PI and never returns, should still leave evidence of
what was going to happen and with which routing table. An audit trail that only
covers successful runs is not an audit trail.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from maglab.harness.plan import WorkflowPlan

log = logging.getLogger(__name__)

DEFAULT_PROVENANCE_DB = Path(".maglab") / "harness-provenance.sqlite"


def record_run(
    plan: WorkflowPlan,
    *,
    db_path: Path | None = None,
    pi_flow_id: str = "",
) -> dict[str, Any]:
    """Record *plan* as a PROV activity with one entity per step.

    Returns a summary of what was written. Recording never fails the run: a
    provenance store that cannot be opened is reported, not raised, because
    losing the audit record is not a reason to abandon the research task.
    """
    target = Path(db_path) if db_path is not None else DEFAULT_PROVENANCE_DB
    activity_id = f"harness-{plan.name}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    try:
        from maglab.provenance.store import ProvenanceStore

        target.parent.mkdir(parents=True, exist_ok=True)
        with ProvenanceStore(target) as store:
            store.add_activity(
                activity_id,
                start_time=now,
                attributes={
                    "kind": "harness-run",
                    "workflow": plan.name,
                    "requested": plan.requested_name or plan.name,
                    "topic": plan.topic,
                    "steps": ",".join(step.agent for step in plan.steps),
                    "ready": str(plan.ready),
                    "pi_flow_id": pi_flow_id,
                },
            )
            for index, step in enumerate(plan.steps, start=1):
                entity_id = f"{activity_id}-step{index}-{step.agent}"
                store.add_entity(
                    entity_id,
                    attributes={
                        "provenance_type": "harness-step",
                        "agent": step.agent,
                        "model": step.resolved_model or step.model,
                        "tools": ",".join(step.tools),
                        "skills": ",".join(step.skills),
                        "order": str(index),
                    },
                )
                store.was_generated_by(entity_id, activity_id, time=now)
                store.was_attributed_to(entity_id)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        log.warning("Could not record harness provenance at %s: %s", target, exc)
        return {"recorded": False, "db": str(target), "error": str(exc)}

    return {
        "recorded": True,
        "db": str(target),
        "activity": activity_id,
        "entities": [f"{activity_id}-step{i}-{s.agent}" for i, s in enumerate(plan.steps, start=1)],
        "pi_flow_id": pi_flow_id or None,
    }
