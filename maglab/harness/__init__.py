"""PI harness surface — manifest-driven workflow planning and execution (§5.16, §14.7).

``harness.manifest.json`` is the declarative routing table: which subagents
exist, which model tier each runs on, which tools and skills they may use, and
which ordered workflows compose them. This package turns that table into
something executable and inspectable:

- :mod:`maglab.harness.plan` builds a plan from the manifest. It is entirely
  deterministic — no LLM, no network — so ``doctor``, ``compile``, ``run
  --dry-run``, ``worker`` and ``pi-tool`` are all exactly reproducible.
- :mod:`maglab.harness.compile` renders and diffs the ``.pi/workflows/*.json``
  drift artifacts.
- :mod:`maglab.harness.doctor` reports what is and is not ready to run.
- :mod:`maglab.harness.local` executes a plan step by step through MagLab's own
  ``SubagentRunner``, so verification, hooks and budget apply unchanged.
- :mod:`maglab.harness.pi` builds the PI handoff and the PI-callable payload.
- :mod:`maglab.harness.record` records a prepared run as a W3C PROV activity.
"""

from __future__ import annotations

from maglab.harness.plan import (
    WORKFLOW_ALIASES,
    WorkerPlan,
    WorkflowPlan,
    build_worker_plan,
    build_workflow_plan,
    resolve_workflow_name,
)

__all__ = [
    "WORKFLOW_ALIASES",
    "WorkerPlan",
    "WorkflowPlan",
    "build_worker_plan",
    "build_workflow_plan",
    "resolve_workflow_name",
]
