"""Orchestrator — research loop backtracking tree search & REPL single turn (§5.3, §5.12, §5.16).

Architecture:
  - ``Orchestrator.respond()``  — REPL single turn: backend call + tool loop + verify gate
  - ``Orchestrator.run()``      — Autonomous research loop: tree search (best-first)

Tree nodes: {hypothesis, design, execution state, result, analysis judgment, score}
Expansion:  best-first (highest score node first)
Pruning:    record failure types → prevent duplicate attempts
Termination: goal achieved / budget exhausted / all branches blocked

Topology: orchestrator-workers (delegates sub-tasks to subagents).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from maglab.config import Config, load_config
from maglab.core.budget import BudgetTracker
from maglab.core.checkpoint import CheckpointStore, StepStatus
from maglab.core.context import ContextEngine
from maglab.core.hooks import HookRegistry, ToolCall, default_registry
from maglab.core.manifest import Manifest, load_manifest
from maglab.core.memory import ResearchPool, SessionMemory
from maglab.core.verify import Verifier, VerifyStatus

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public contract data structures
# ---------------------------------------------------------------------------


class OrchestratorResult(BaseModel):
    """Return data structure for ``Orchestrator.run()``.

    Attributes
    ----------
    status:
        "completed" / "budget_exhausted" / "all_pruned" / "partial"
    summary:
        Summary string of research loop results.
    datapoints:
        List of collected DataPoint IDs.
    warnings:
        List of warning messages.
    """

    status: str
    summary: str
    datapoints: list[str] = []
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Tree node
# ---------------------------------------------------------------------------


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    PRUNED = "pruned"


@dataclass
class ResearchNode:
    """Research loop tree node.

    Attributes
    ----------
    node_id:   UUID4 identifier.
    parent_id: Parent node ID (None for root).
    hypothesis:    Hypothesis text.
    design:        Experiment/simulation design text.
    execution_state: Execution state memo.
    result:    Result text (filled after completion).
    analysis:  Analysis judgment text.
    score:     Expansion priority score (higher = more urgent).
    status:    Node status.
    failure_type:  Pruning reason (oracle failure / physically invalid / budget exceeded, etc.).
    depth:     Root = 0.
    """

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None
    hypothesis: str = ""
    design: str = ""
    execution_state: str = ""
    result: str = ""
    analysis: str = ""
    score: float = 0.0
    status: NodeStatus = NodeStatus.PENDING
    failure_type: str = ""
    depth: int = 0
    children: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "hypothesis": self.hypothesis,
            "design": self.design,
            "execution_state": self.execution_state,
            "result": self.result,
            "analysis": self.analysis,
            "score": self.score,
            "status": self.status.value,
            "failure_type": self.failure_type,
            "depth": self.depth,
            "children": self.children,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Research loop tree
# ---------------------------------------------------------------------------


class ResearchTree:
    """Research loop backtracking tree.

    Serialized to ``CheckpointStore`` to support pause and resume.
    """

    def __init__(
        self,
        task_id: str,
        goal: str,
        checkpoint_store: CheckpointStore,
    ) -> None:
        self._task_id = task_id
        self._goal = goal
        self._store = checkpoint_store
        self._nodes: dict[str, ResearchNode] = {}
        self._root_id: str | None = None
        self._known_failures: list[str] = []  # records failure types already attempted

    # ------------------------------------------------------------------
    # Root initialization
    # ------------------------------------------------------------------

    def init_root(self, hypothesis: str = "") -> ResearchNode:
        """Initialize and return the root node."""
        root = ResearchNode(
            hypothesis=hypothesis or self._goal,
            score=1.0,
            depth=0,
        )
        self._nodes[root.node_id] = root
        self._root_id = root.node_id
        self._checkpoint(root)
        return root

    # ------------------------------------------------------------------
    # Node manipulation
    # ------------------------------------------------------------------

    def add_child(
        self,
        parent_id: str,
        hypothesis: str,
        design: str = "",
        score: float = 0.5,
    ) -> ResearchNode:
        """Add a child node to the parent node."""
        parent = self._nodes[parent_id]
        child = ResearchNode(
            parent_id=parent_id,
            hypothesis=hypothesis,
            design=design,
            score=score,
            depth=parent.depth + 1,
        )
        self._nodes[child.node_id] = child
        parent.children.append(child.node_id)
        self._checkpoint(child)
        return child

    def update_node(
        self,
        node_id: str,
        *,
        result: str = "",
        analysis: str = "",
        score: float | None = None,
        status: NodeStatus | None = None,
        failure_type: str = "",
    ) -> ResearchNode:
        """Update a node."""
        node = self._nodes[node_id]
        if result:
            node.result = result
        if analysis:
            node.analysis = analysis
        if score is not None:
            node.score = score
        if status is not None:
            node.status = status
        if failure_type:
            node.failure_type = failure_type
            if failure_type not in self._known_failures:
                self._known_failures.append(failure_type)
        self._checkpoint(node)
        return node

    def prune(self, node_id: str, failure_type: str) -> None:
        """Prune a node. Records the failure type."""
        self.update_node(
            node_id,
            status=NodeStatus.PRUNED,
            failure_type=failure_type,
        )

    # ------------------------------------------------------------------
    # Search support
    # ------------------------------------------------------------------

    def best_pending(self) -> ResearchNode | None:
        """Return the highest-scoring PENDING leaf node (no children) available for expansion."""
        candidates = [
            n for n in self._nodes.values() if n.status == NodeStatus.PENDING and not n.children
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda n: n.score)

    def all_done_or_pruned(self) -> bool:
        """Return True if all nodes are in DONE or PRUNED status."""
        return all(n.status in (NodeStatus.DONE, NodeStatus.PRUNED) for n in self._nodes.values())

    def completed_nodes(self) -> list[ResearchNode]:
        """Return the list of nodes in DONE status."""
        return [n for n in self._nodes.values() if n.status == NodeStatus.DONE]

    @property
    def known_failures(self) -> list[str]:
        return list(self._known_failures)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _checkpoint(self, node: ResearchNode) -> None:
        self._store.save(
            task_id=self._task_id,
            idempotency_key=f"node:{node.node_id}",
            status=StepStatus(
                {
                    NodeStatus.PENDING: "pending",
                    NodeStatus.RUNNING: "running",
                    NodeStatus.DONE: "done",
                    NodeStatus.PRUNED: "failed",
                }.get(node.status, "pending")
            ),
            payload=node.to_dict(),
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """MagLab Orchestrator.

    Provides two modes: REPL single turn (``respond``) and autonomous research loop (``run``).

    Parameters
    ----------
    config:
        maglab Config (None → ``load_config()``).
    backend:
        LLMBackend instance.
    session_id:
        Session ID (None → auto-generated).
    hook_registry:
        PreToolUse hook registry (None → default registry).
    budget_tracker:
        BudgetTracker (None → auto-created).
    checkpoint_store:
        CheckpointStore (None → auto-created).
    verifier:
        Verifier (None → default Verifier).
    model_router:
        Optional :class:`~maglab.llm.base.ModelRouter` for stage-wise model
        routing (plan / build / summarize / …).  When ``None`` the single
        ``backend`` is used for every stage — existing behaviour is unchanged.
    gateway_runner:
        Optional :class:`~maglab.gateway.runner.GatewayRunner` to receive
        proactive "research complete" notifications at the end of ``run()``.
        When ``None`` no notifications are sent.
    manifest_path:
        Optional path to ``harness.manifest.json``.  When ``None`` the default
        repo-root location is tried; a missing file is a graceful no-op.
    """

    def __init__(
        self,
        config: Config | None = None,
        backend: Any = None,
        session_id: str | None = None,
        hook_registry: HookRegistry | None = None,
        budget_tracker: BudgetTracker | None = None,
        checkpoint_store: CheckpointStore | None = None,
        verifier: Verifier | None = None,
        model_router: Any | None = None,
        gateway_runner: Any | None = None,
        manifest_path: Any | None = None,
    ) -> None:
        self._config = config or load_config()
        self._backend = backend
        self._session_id = session_id or str(uuid.uuid4())
        self._hooks = hook_registry or default_registry()
        self._budget = budget_tracker or BudgetTracker(session_id=self._session_id)
        self._checkpoint = checkpoint_store or CheckpointStore()
        self._verifier = verifier or Verifier(allow_llm_judge=False)
        self._context = ContextEngine()
        self._session_memory = SessionMemory(session_id=self._session_id)
        self._research_pool = ResearchPool()
        self._tool_log: list[dict[str, Any]] = []
        self._max_tool_iterations = 10
        # FIX 2: stage-wise model router (optional, backward-compatible)
        self._model_router = model_router
        # FIX 4: gateway runner for proactive notifications (optional, backward-compatible)
        self._gateway_runner = gateway_runner
        # FIX 3: load harness manifest (graceful no-op if absent)
        self._manifest: Manifest = load_manifest(manifest_path)

    # ------------------------------------------------------------------
    # REPL single turn
    # ------------------------------------------------------------------

    def respond(self, user_message: str) -> str:
        """REPL single turn — backend call + tool loop + verify gate.

        Parameters
        ----------
        user_message:
            User input string.

        Returns
        -------
        Assistant response string.  When the HonestyGate detects violations the
        response is still returned (not suppressed) but a warning header is
        prepended and violations are logged at WARNING level.
        """
        if self._backend is None:
            return "[Orchestrator] Backend is not configured."

        if self._budget.is_over_budget():
            return "[Orchestrator] Budget exceeded — blocking additional LLM calls."

        # Add user message to context engine
        self._context.add_turn("user", user_message)

        # Tool loop
        response_text = self._tool_loop()

        # Add response to context
        self._context.add_turn("assistant", response_text)

        # Check if compaction is needed
        if self._context.needs_compaction():
            self._compact_context()

        # FIX 1 (CRITICAL-1): apply HonestyGate at the REPL turn boundary.
        # Violations are flagged — the response is NOT suppressed, but the
        # warning is surfaced to the caller so the UI can display it.
        response_text = self._apply_honesty_gate(response_text)

        return response_text

    # ------------------------------------------------------------------
    # Autonomous research loop (tree search)
    # ------------------------------------------------------------------

    def run(self, goal: str) -> OrchestratorResult:
        """Autonomous research loop — backtracking tree search.

        Parameters
        ----------
        goal:
            Research goal string.

        Returns
        -------
        OrchestratorResult
        """
        task_id = str(uuid.uuid4())
        tree = ResearchTree(task_id, goal, self._checkpoint)
        tree.init_root(hypothesis=goal)

        # JIT inject prior failure regions from research_pool
        prior_failures = self._query_prior_failures(goal)
        if prior_failures:
            log.info("Injecting %d prior failure regions into context", len(prior_failures))

        warnings: list[str] = []
        datapoints: list[str] = []
        max_nodes = 20  # safety upper bound

        for _iteration in range(max_nodes):
            # Budget gate
            if self._budget.is_over_budget():
                log.warning("Budget exceeded — terminating research loop early")
                return OrchestratorResult(
                    status="budget_exhausted",
                    summary=f"Early termination due to budget exhaustion. Completed nodes: {len(tree.completed_nodes())}",
                    datapoints=datapoints,
                    warnings=warnings + ["Early termination due to budget exhaustion"],
                )

            # Check if all branches are blocked
            if tree.all_done_or_pruned():
                break

            # Best-first expansion
            node = tree.best_pending()
            if node is None:
                break

            tree.update_node(node.node_id, status=NodeStatus.RUNNING)

            # Process node (deterministic verification + optional LLM)
            node_result, node_warnings, dp_ids = self._process_node(node, goal, prior_failures)
            warnings.extend(node_warnings)
            datapoints.extend(dp_ids)

            if node_result.get("pruned"):
                tree.prune(node.node_id, node_result.get("failure_type", "unknown"))
                continue

            # Update result
            tree.update_node(
                node.node_id,
                result=node_result.get("result", ""),
                analysis=node_result.get("analysis", ""),
                score=node_result.get("score", 0.5),
                status=NodeStatus.DONE,
            )

            # Create child nodes (candidate alternatives)
            children_specs = node_result.get("children", [])
            for child_spec in children_specs[:3]:  # maximum 3 children
                if isinstance(child_spec, dict):
                    tree.add_child(
                        node.node_id,
                        hypothesis=child_spec.get("hypothesis", ""),
                        design=child_spec.get("design", ""),
                        score=child_spec.get("score", 0.5),
                    )

            # Check goal achievement
            if node_result.get("goal_achieved"):
                completed = tree.completed_nodes()
                result = OrchestratorResult(
                    status="completed",
                    summary=(
                        f"Goal achieved. Completed nodes: {len(completed)}. Result: {node.result[:200]}"
                    ),
                    datapoints=datapoints,
                    warnings=warnings,
                )
                # FIX 4: proactive gateway notification on successful completion
                self._notify_gateway(task_id, goal, result)
                return result

        # Loop terminated
        completed = tree.completed_nodes()
        if not completed:
            result = OrchestratorResult(
                status="all_pruned",
                summary="All branches were pruned. A different approach is needed.",
                datapoints=datapoints,
                warnings=warnings + tree.known_failures,
            )
            # FIX 4: notify gateway on terminal completion (all_pruned)
            self._notify_gateway(task_id, goal, result)
            return result

        result = OrchestratorResult(
            status="partial",
            summary=(
                f"Research loop completed (partial). Completed nodes: {len(completed)}. "
                f"Known failures: {tree.known_failures}"
            ),
            datapoints=datapoints,
            warnings=warnings,
        )
        # FIX 4: notify gateway on terminal completion (partial)
        self._notify_gateway(task_id, goal, result)
        return result

    # ------------------------------------------------------------------
    # Internal: tool loop
    # ------------------------------------------------------------------

    def _tool_loop(self, stage: str = "default") -> str:
        """Execute backend call + tool loop and return the final response.

        Parameters
        ----------
        stage:
            Pipeline stage name used for model routing when a
            :class:`~maglab.llm.base.ModelRouter` is available.
            Ignored when ``model_router`` is ``None``.
        """
        from maglab.llm.base import Message, Role  # deferred import

        messages = self._context.get_messages_for_llm()
        # Convert dicts to Message objects
        msg_objects = [
            Message(role=Role(m["role"]), content=m["content"])
            for m in messages
            if m.get("content")
        ]

        # FIX 2: resolve model via ModelRouter when available
        stage_model: str | None = None
        if self._model_router is not None:
            stage_model = self._model_router.model_for(stage)

        for _ in range(self._max_tool_iterations):
            t0 = time.monotonic()
            try:
                # Pass stage_model as the `model` kwarg so the backend can
                # override its default; backends that ignore the kwarg are unaffected.
                response = self._backend.complete(msg_objects, max_tokens=4096, model=stage_model)
            except Exception as exc:  # noqa: BLE001
                log.warning("Backend call error: %s", exc)
                return f"[Error] Backend call failed: {exc}"

            elapsed = time.monotonic() - t0
            # Record budget
            if response.usage:
                self._budget.record_llm(
                    label=response.model or "unknown",
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    usd_cost=response.usage.estimated_cost_usd or 0.0,
                    wall_time=elapsed,
                )

            # Return text if no tool calls
            if not response.tool_calls:
                return response.content or ""

            # Process tool calls
            tool_results = []
            for tc in response.tool_calls:
                tool_call = ToolCall(name=tc.name, args=tc.arguments)
                allowed, reason = self._hooks.is_allowed(tool_call)
                if not allowed:
                    log.warning("Hook blocked: %s — %s", tc.name, reason)
                    tool_results.append(
                        {
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": f"[Blocked] {reason}",
                            "is_error": True,
                        }
                    )
                    self._tool_log.append({"tool": tc.name, "status": "blocked"})
                    continue

                result_content = self._execute_tool(tc.name, tc.arguments)
                tool_results.append(
                    {
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result_content,
                        "is_error": False,
                    }
                )
                self._tool_log.append({"tool": tc.name, "status": "success"})

            # Add tool results to messages.
            # Each TOOL-role message must carry the originating tool_call_id so
            # that OpenAI/Anthropic APIs can match results to the correct call in
            # multi-tool-call responses.  Dropping tool_call_id causes API errors
            # and corrupts the conversation context.
            if response.content:
                msg_objects.append(Message(role=Role.ASSISTANT, content=response.content))
            for tr in tool_results:
                msg_objects.append(
                    Message(
                        role=Role.TOOL,
                        content=tr["content"],
                        tool_call_id=tr.get("tool_call_id"),
                    )
                )

        return "[Warning] Tool loop reached maximum iterations."

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return the result string."""
        from maglab.llm import tools as tool_registry  # deferred import

        t0 = time.monotonic()
        try:
            result = tool_registry.call_tool(name, arguments)
            self._budget.record_tool(
                label=name,
                wall_time=time.monotonic() - t0,
            )
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except KeyError:
            return f"[Error] Tool '{name}' not found."
        except Exception as exc:  # noqa: BLE001
            log.warning("Tool execution error (%s): %s", name, exc)
            return f"[Error] Tool execution failed: {exc}"

    # ------------------------------------------------------------------
    # Internal: node processing
    # ------------------------------------------------------------------

    def _process_node(
        self,
        node: ResearchNode,
        goal: str,
        prior_failures: list[str],
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        """Process a single node.

        Returns
        -------
        (result dict, warnings list, datapoint ID list)
        """
        warnings: list[str] = []
        datapoints: list[str] = []

        # Immediately prune if hypothesis is a known failure type
        if node.hypothesis in prior_failures:
            return (
                {"pruned": True, "failure_type": "known_failure"},
                [f"Pruned due to prior failure: {node.hypothesis[:80]}"],
                [],
            )

        # Deterministic verification (oracle)
        oracle_result = self._run_oracle_check(node)
        if not oracle_result["ok"]:
            return (
                {
                    "pruned": True,
                    "failure_type": f"oracle_fail:{oracle_result.get('reason', '')}",
                },
                [f"Oracle verification failed: {oracle_result.get('reason', '')}"],
                [],
            )

        # Return deterministic stub result if no backend
        if self._backend is None:
            return (
                {
                    "result": f"[stub] Node processed: {node.hypothesis[:80]}",
                    "analysis": "No backend — stub result",
                    "score": 0.5,
                    "goal_achieved": False,
                    "children": [],
                },
                warnings,
                datapoints,
            )

        # Delegate node processing to LLM — build stage uses the "build" model
        prompt = self._build_node_prompt(node, goal, prior_failures)
        self._context.add_turn("user", prompt)
        response_text = self._tool_loop(stage="build")
        self._context.add_turn("assistant", response_text)

        # Attempt structured parsing
        structured = _try_parse_json(response_text)
        if not structured:
            structured = {
                "result": response_text,
                "analysis": "",
                "score": 0.3,
                "goal_achieved": False,
                "children": [],
            }

        # verify requires subagent schema (status field) — normalize the node result
        structured.setdefault("status", "success")
        # verify
        vr = self._verifier.verify(structured, is_quantitative=True)
        if vr.status == VerifyStatus.FAILED:
            return (
                {
                    "pruned": True,
                    "failure_type": f"verify_fail:{','.join(vr.violations[:2])}",
                },
                vr.violations + vr.warnings,
                [],
            )
        warnings.extend(vr.warnings)

        return structured, warnings, datapoints

    def _run_oracle_check(self, node: ResearchNode) -> dict[str, Any]:
        """Extract physics parameters from node metadata and run an oracle check."""
        params = {k: v for k, v in node.metadata.items() if isinstance(v, (int, float))}
        if not params:
            return {"ok": True}
        from maglab.physics import oracle  # deferred import

        result = oracle.check(params)
        return {"ok": result.ok, "reason": result.reason if not result.ok else ""}

    def _build_node_prompt(
        self,
        node: ResearchNode,
        goal: str,
        prior_failures: list[str],
    ) -> str:
        """Assemble the LLM prompt for node processing."""
        failure_hint = ""
        if prior_failures:
            failure_hint = (
                f"\n\n## Already failed areas (do not repeat)\n{chr(10).join(prior_failures[:5])}"
            )
        return (
            f"## Research goal\n{goal}\n\n"
            f"## Current node\nHypothesis: {node.hypothesis}\nDesign: {node.design}"
            f"{failure_hint}\n\n"
            "Return result, analysis, score, child nodes (alternatives), and goal achievement status as JSON.\n"
            'Schema: {"result": str, "analysis": str, "score": float(0-1), '
            '"goal_achieved": bool, "children": [{"hypothesis": str, "design": str, "score": float}]}'
        )

    # ------------------------------------------------------------------
    # Internal: research_pool query
    # ------------------------------------------------------------------

    def _query_prior_failures(self, goal: str) -> list[str]:
        """Query relevant prior failures from the research_pool."""
        from maglab.core.memory import PoolRecordKind  # deferred import

        keywords = goal.split()[:5]
        records = self._research_pool.query(
            keywords=keywords,
            kind=PoolRecordKind.FAILED_REGION,
            max_results=10,
        )
        return [r.summary for r in records]

    # ------------------------------------------------------------------
    # Internal: compaction
    # ------------------------------------------------------------------

    def _compact_context(self) -> None:
        """Compact the context (preserving key values)."""
        summary = (
            "[compaction] Previous context has been compressed. "
            "Physics constants, provenance IDs, and parameter names are preserved."
        )
        self._context.compact(summary)
        log.debug("Context compaction complete")

    # ------------------------------------------------------------------
    # Internal: HonestyGate (FIX 1)
    # ------------------------------------------------------------------

    def _apply_honesty_gate(self, response_text: str) -> str:
        """Run the HonestyGate on ``response_text`` at the REPL turn boundary.

        Violations do NOT suppress the response — the text is returned as-is
        with a warning header prepended so the UI can surface the problem.
        Violations are also logged at WARNING level.

        Parameters
        ----------
        response_text:
            The raw LLM response text to audit.

        Returns
        -------
        str
            Original response text, optionally prefixed with a
            ``[HonestyGate WARNING]`` block listing violations.
        """
        from maglab.report.honesty_gate import run_gate  # deferred import

        try:
            gate_result = run_gate(
                response_text,
                tool_log=self._tool_log,
                raise_on_violation=False,
            )
        except Exception as exc:  # noqa: BLE001
            # Gate itself must never crash the REPL — log and move on
            log.warning("HonestyGate raised an unexpected error: %s", exc)
            return response_text

        if gate_result.passed:
            return response_text

        # Log each violation
        for v in gate_result.violations:
            log.warning("HonestyGate violation: %s", v)

        # Build a human-readable warning header to surface in the UI
        violation_lines = "\n".join(f"  • {v}" for v in gate_result.violations)
        warning_header = (
            f"[HonestyGate WARNING — {len(gate_result.violations)} violation(s) detected]\n"
            f"{violation_lines}\n"
            "---\n"
        )
        return warning_header + response_text

    # ------------------------------------------------------------------
    # Internal: gateway notification (FIX 4)
    # ------------------------------------------------------------------

    def _notify_gateway(
        self,
        task_id: str,
        goal: str,
        result: OrchestratorResult,
    ) -> None:
        """Push a proactive notification to the gateway runner on research completion.

        This is a fire-and-forget operation — any error is logged and silently
        swallowed so the gateway is never on the critical path.

        Parameters
        ----------
        task_id:
            The research loop task identifier.
        goal:
            The research goal string.
        result:
            The final ``OrchestratorResult``.
        """
        if self._gateway_runner is None:
            return

        try:
            from maglab.gateway.runner import NotificationEvent  # deferred import

            event = NotificationEvent(
                kind="research_complete",
                channel="all",
                platform="all",
                payload={
                    "task_id": task_id,
                    "goal": goal[:200],
                    "status": result.status,
                    "summary": result.summary[:500],
                },
            )
            # GatewayRunner exposes notification_queue; put_nowait is sync
            self._gateway_runner.notification_queue.put_nowait(event)
            log.info("Gateway notification queued: task_id=%s status=%s", task_id, result.status)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to send gateway notification: %s", exc)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Resource management (Fix 6)
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close all owned SQLite connections.

        Call this when the orchestrator is no longer needed to release
        database file handles.  On Windows and network file-systems, unclosed
        SQLite connections can prevent file access by other processes or cause
        locking errors across sessions.
        """
        self._budget.close()
        self._checkpoint.close()
        self._session_memory.close()

    def __enter__(self) -> Orchestrator:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def budget(self) -> BudgetTracker:
        return self._budget


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Extract JSON from text. Returns None on failure."""
    import re

    code_block = re.search(r"```json\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass
    return None
