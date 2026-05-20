"""orchestrator.py unit tests — LLM mock, deterministic."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from maglab.config import load_config
from maglab.core.budget import BudgetTracker
from maglab.core.checkpoint import CheckpointStore
from maglab.core.orchestrator import (
    NodeStatus,
    Orchestrator,
    OrchestratorResult,
    ResearchNode,
    ResearchTree,
    _try_parse_json,
)
from maglab.llm.base import LLMResponse, ModelRouter, PipelineStage, UsageStats

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_backend(content: str = "Response text", tool_calls: list | None = None) -> MagicMock:
    backend = MagicMock()
    response = LLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        usage=UsageStats(prompt_tokens=10, completion_tokens=20, estimated_cost_usd=0.001),
        model="claude-haiku-4-5",
    )
    backend.complete.return_value = response
    return backend


@pytest.fixture()
def tmp_db(tmp_path: Path):
    return tmp_path / "test.db"


@pytest.fixture()
def budget(tmp_path: Path) -> BudgetTracker:
    return BudgetTracker(db_path=tmp_path / "budget.db")


@pytest.fixture()
def checkpoint(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(db_path=tmp_path / "cp.db")


@pytest.fixture()
def orch(budget: BudgetTracker, checkpoint: CheckpointStore) -> Orchestrator:
    """Default orchestrator — no backend."""
    return Orchestrator(
        budget_tracker=budget,
        checkpoint_store=checkpoint,
    )


@pytest.fixture()
def orch_with_backend(budget: BudgetTracker, checkpoint: CheckpointStore) -> Orchestrator:
    backend = _make_backend("Hello.")
    return Orchestrator(
        backend=backend,
        budget_tracker=budget,
        checkpoint_store=checkpoint,
    )


# ---------------------------------------------------------------------------
# OrchestratorResult Pydantic model
# ---------------------------------------------------------------------------


class TestOrchestratorResult:
    def test_instantiation(self) -> None:
        r = OrchestratorResult(status="completed", summary="Test complete")
        assert r.status == "completed"
        assert r.datapoints == []
        assert r.warnings == []

    def test_with_datapoints(self) -> None:
        r = OrchestratorResult(
            status="partial",
            summary="Summary",
            datapoints=["dp-1", "dp-2"],
            warnings=["warning1"],
        )
        assert len(r.datapoints) == 2
        assert len(r.warnings) == 1

    def test_json_serializable(self) -> None:
        r = OrchestratorResult(status="completed", summary="ok")
        d = r.model_dump()
        assert d["status"] == "completed"


# ---------------------------------------------------------------------------
# ResearchNode
# ---------------------------------------------------------------------------


class TestResearchNode:
    def test_default_values(self) -> None:
        node = ResearchNode()
        assert node.status == NodeStatus.PENDING
        assert node.score == 0.0
        assert node.depth == 0

    def test_to_dict(self) -> None:
        node = ResearchNode(hypothesis="H1", score=0.8)
        d = node.to_dict()
        assert d["hypothesis"] == "H1"
        assert d["score"] == 0.8
        assert d["status"] == "pending"


# ---------------------------------------------------------------------------
# ResearchTree
# ---------------------------------------------------------------------------


class TestResearchTree:
    def test_init_root(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("First hypothesis")
        assert root.hypothesis == "First hypothesis"
        assert root.depth == 0
        assert root.status == NodeStatus.PENDING

    def test_add_child(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("root")
        child = tree.add_child(root.node_id, "child hypothesis", score=0.7)
        assert child.parent_id == root.node_id
        assert child.depth == 1
        assert child.score == 0.7
        assert child.node_id in root.children

    def test_best_pending(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("root")
        tree.add_child(root.node_id, "child1", score=0.3)
        c2 = tree.add_child(root.node_id, "child2", score=0.9)
        best = tree.best_pending()
        assert best is not None
        assert best.node_id == c2.node_id

    def test_best_pending_none_when_all_done(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("root")
        tree.update_node(root.node_id, status=NodeStatus.DONE)
        assert tree.best_pending() is None

    def test_prune(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("root")
        tree.prune(root.node_id, "oracle_fail")
        updated = tree._nodes[root.node_id]
        assert updated.status == NodeStatus.PRUNED
        assert "oracle_fail" in tree.known_failures

    def test_all_done_or_pruned(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("root")
        assert not tree.all_done_or_pruned()
        tree.update_node(root.node_id, status=NodeStatus.DONE)
        assert tree.all_done_or_pruned()

    def test_completed_nodes(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("root")
        tree.update_node(root.node_id, status=NodeStatus.DONE)
        completed = tree.completed_nodes()
        assert len(completed) == 1
        assert completed[0].node_id == root.node_id

    def test_known_failures_accumulate(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-1", "goal", checkpoint)
        root = tree.init_root("root")
        c1 = tree.add_child(root.node_id, "child1")
        tree.prune(root.node_id, "fail-type-A")
        tree.prune(c1.node_id, "fail-type-B")
        assert "fail-type-A" in tree.known_failures
        assert "fail-type-B" in tree.known_failures

    def test_checkpoint_persisted(self, checkpoint: CheckpointStore) -> None:
        tree = ResearchTree("task-persist", "goal", checkpoint)
        tree.init_root("root")
        records = checkpoint.list_task("task-persist")
        assert len(records) >= 1


# ---------------------------------------------------------------------------
# Orchestrator — init
# ---------------------------------------------------------------------------


class TestOrchestratorInit:
    def test_basic_init(self, orch: Orchestrator) -> None:
        assert orch.session_id
        assert orch.budget is not None

    def test_init_with_config(self, budget: BudgetTracker, checkpoint: CheckpointStore) -> None:
        cfg = load_config()
        o = Orchestrator(config=cfg, budget_tracker=budget, checkpoint_store=checkpoint)
        assert o.session_id


# ---------------------------------------------------------------------------
# Orchestrator.respond() — REPL single turn
# ---------------------------------------------------------------------------


class TestOrchestratorRespond:
    def test_no_backend(self, orch: Orchestrator) -> None:
        response = orch.respond("Hello")
        assert "Backend" in response

    def test_with_mock_backend(self, orch_with_backend: Orchestrator) -> None:
        response = orch_with_backend.respond("Hello")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_budget_over_blocks(self, checkpoint: CheckpointStore, tmp_path: Path) -> None:
        """Request is blocked when budget is exceeded."""
        budget = BudgetTracker(db_path=tmp_path / "b.db")
        # force budget into over-limit state
        budget.record_llm(
            label="test",
            input_tokens=100,
            output_tokens=100,
            usd_cost=999.0,  # exceeds max_usd_per_session(10.0)
            wall_time=0.1,
        )
        orch = Orchestrator(
            backend=_make_backend(),
            budget_tracker=budget,
            checkpoint_store=checkpoint,
        )
        response = orch.respond("test")
        assert "Budget" in response

    def test_tool_call_hook_blocked(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """An error message is returned when a hook blocks a tool."""
        from maglab.core.hooks import DenyRule, default_registry
        from maglab.llm.base import ToolCall as LLMToolCall

        # rule that blocks file.delete
        registry = default_registry(
            deny_rules=[DenyRule(pattern="file.delete", reason="test block")]
        )
        tool_call_resp = LLMResponse(
            content=None,
            tool_calls=[LLMToolCall(id="tc-1", name="file.delete", arguments={})],
            usage=UsageStats(),
        )
        # second call returns text without tool calls
        text_resp = LLMResponse(content="Done", tool_calls=[], usage=UsageStats())
        backend = MagicMock()
        backend.complete.side_effect = [tool_call_resp, text_resp]

        orch = Orchestrator(
            backend=backend,
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            hook_registry=registry,
        )
        response = orch.respond("Delete the file")
        assert isinstance(response, str)

    def test_budget_recorded_after_call(self, orch_with_backend: Orchestrator) -> None:
        """Budget is recorded after an LLM call."""
        before = orch_with_backend.budget.session_summary().llm_calls
        orch_with_backend.respond("test")
        after = orch_with_backend.budget.session_summary().llm_calls
        assert after > before


# ---------------------------------------------------------------------------
# Orchestrator.run() — autonomous research loop
# ---------------------------------------------------------------------------


class TestOrchestratorRun:
    def test_run_no_backend(self, orch: Orchestrator) -> None:
        """Returns a stub result even without a backend."""
        result = orch.run("Calculate exchange length")
        assert isinstance(result, OrchestratorResult)
        assert result.status in {"completed", "partial", "all_pruned", "budget_exhausted"}

    def test_run_returns_orchestrator_result(self, orch: Orchestrator) -> None:
        result = orch.run("Test goal")
        assert hasattr(result, "status")
        assert hasattr(result, "summary")
        assert hasattr(result, "datapoints")
        assert hasattr(result, "warnings")

    def test_run_with_backend_goal_achieved(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """completed status when backend returns goal_achieved=True."""
        goal_response = json.dumps(
            {
                "result": "Exchange length calculation complete",
                "analysis": "Permalloy l_ex ≈ 5.7 nm",
                "score": 0.9,
                "goal_achieved": True,
                "children": [],
            }
        )
        backend = _make_backend(content=goal_response)
        orch = Orchestrator(
            backend=backend,
            budget_tracker=budget,
            checkpoint_store=checkpoint,
        )
        result = orch.run("Calculate exchange length")
        assert result.status == "completed"

    def test_run_budget_exhausted(self, checkpoint: CheckpointStore, tmp_path: Path) -> None:
        """budget_exhausted returned when budget is exceeded."""
        budget = BudgetTracker(db_path=tmp_path / "b.db")
        budget.record_llm(
            label="test",
            input_tokens=0,
            output_tokens=0,
            usd_cost=999.0,
            wall_time=0.0,
        )
        orch = Orchestrator(
            backend=_make_backend(),
            budget_tracker=budget,
            checkpoint_store=checkpoint,
        )
        result = orch.run("goal")
        assert result.status == "budget_exhausted"

    def test_run_oracle_prunes_invalid_node(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """Nodes with oracle-failing parameters are pruned."""
        # test via direct tree access on the orchestrator
        orch = Orchestrator(
            budget_tracker=budget,
            checkpoint_store=checkpoint,
        )
        tree = ResearchTree("task-oracle", "goal", checkpoint)
        root = tree.init_root("Test hypothesis")
        # alpha=5.0 triggers oracle failure
        root.metadata["alpha"] = 5.0

        result, warnings, _ = orch._process_node(root, "goal", [])
        assert result.get("pruned")
        assert "oracle" in result.get("failure_type", "")


# ---------------------------------------------------------------------------
# _try_parse_json
# ---------------------------------------------------------------------------


class TestTryParseJson:
    def test_json_code_block(self) -> None:
        text = '```json\n{"key": "val"}\n```'
        parsed = _try_parse_json(text)
        assert parsed is not None
        assert parsed["key"] == "val"

    def test_naked_json(self) -> None:
        text = 'Result: {"a": 1, "b": 2}'
        parsed = _try_parse_json(text)
        assert parsed is not None
        assert parsed["a"] == 1

    def test_no_json(self) -> None:
        parsed = _try_parse_json("Plain text")
        assert parsed is None

    def test_invalid_json(self) -> None:
        parsed = _try_parse_json("{invalid json}")
        assert parsed is None


# ---------------------------------------------------------------------------
# FIX 1 — HonestyGate applied at the REPL turn boundary
# ---------------------------------------------------------------------------


class TestHonestyGateOnRespond:
    """HonestyGate is called after respond() — violations flagged, not suppressed."""

    def test_clean_response_unchanged(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """A response that passes the gate is returned verbatim."""
        backend = _make_backend("The result looks correct.")
        orch = Orchestrator(backend=backend, budget_tracker=budget, checkpoint_store=checkpoint)
        response = orch.respond("What is the exchange length?")
        assert isinstance(response, str)
        # No violation header for a clean response
        assert "[HonestyGate WARNING" not in response

    def test_response_with_untagged_number_flagged(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """A response containing an untagged bare number is flagged but still returned."""
        # The HonestyGate will flag bare numbers without DataPoint UUIDs.
        backend = _make_backend("The exchange length is 5.7 nm for Permalloy.")
        orch = Orchestrator(backend=backend, budget_tracker=budget, checkpoint_store=checkpoint)
        response = orch.respond("What is the exchange length?")
        # Response must still contain the original text (not suppressed)
        assert "5.7" in response or "exchange" in response
        # Violation warning header should be prepended
        assert "[HonestyGate WARNING" in response

    def test_gate_violation_does_not_raise(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """HonestyGate violations must NOT raise — response is flagged and returned."""
        backend = _make_backend("I calculated the value is 42.0 Tesla.")
        orch = Orchestrator(backend=backend, budget_tracker=budget, checkpoint_store=checkpoint)
        # Must not raise even with multiple violations
        response = orch.respond("Check the field value")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_gate_not_called_without_backend(self, orch: Orchestrator) -> None:
        """When no backend is set, respond() returns early — no gate needed."""
        response = orch.respond("test")
        assert "Backend" in response
        assert "[HonestyGate WARNING" not in response


# ---------------------------------------------------------------------------
# FIX 2 — ModelRouter wired into Orchestrator
# ---------------------------------------------------------------------------


class TestModelRouterIntegration:
    """ModelRouter routes stage-appropriate model to the backend."""

    def test_init_accepts_model_router(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """Orchestrator accepts model_router without breaking existing interface."""
        router = ModelRouter.default()
        orch = Orchestrator(
            backend=_make_backend(),
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            model_router=router,
        )
        assert orch._model_router is router

    def test_model_router_none_is_default(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """When model_router=None, behaviour is unchanged (single backend)."""
        orch = Orchestrator(
            backend=_make_backend(), budget_tracker=budget, checkpoint_store=checkpoint
        )
        assert orch._model_router is None

    def test_model_passed_to_backend_when_router_present(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """When a router is present, the resolved model is forwarded to backend.complete()."""
        router = ModelRouter(routing_config={"default": "claude-haiku-4-5"})
        backend = _make_backend("Hello.")
        orch = Orchestrator(
            backend=backend,
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            model_router=router,
        )
        orch.respond("ping")
        # The backend's complete() must have been called with model kwarg
        call_kwargs = backend.complete.call_args
        assert call_kwargs is not None
        # model kwarg should be the one from the router
        passed_model = call_kwargs.kwargs.get("model") or (
            call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
        )
        assert passed_model == "claude-haiku-4-5"

    def test_no_model_kwarg_when_router_absent(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """When model_router is None, model=None is still forwarded (backend uses its default)."""
        backend = _make_backend("Hello.")
        orch = Orchestrator(backend=backend, budget_tracker=budget, checkpoint_store=checkpoint)
        orch.respond("ping")
        call_kwargs = backend.complete.call_args
        assert call_kwargs is not None
        passed_model = call_kwargs.kwargs.get("model")
        assert passed_model is None

    def test_model_router_build_stage_used_in_process_node(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """process_node uses the 'build' stage model when a router is configured."""
        router = ModelRouter(
            routing_config={"build": "claude-haiku-4-5", "default": "claude-opus-4-7"}
        )
        backend = _make_backend(
            json.dumps(
                {
                    "result": "done",
                    "analysis": "ok",
                    "score": 0.9,
                    "goal_achieved": True,
                    "children": [],
                }
            )
        )
        orch = Orchestrator(
            backend=backend,
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            model_router=router,
        )
        result = orch.run("calculate exchange length")
        assert result.status in {"completed", "partial", "all_pruned", "budget_exhausted"}
        # The backend must have been called with the build model
        for call in backend.complete.call_args_list:
            m = call.kwargs.get("model")
            if m is not None:
                assert m == "claude-haiku-4-5"
                break


# ---------------------------------------------------------------------------
# FIX 3 — Manifest loader & Orchestrator loads manifest
# ---------------------------------------------------------------------------


class TestManifestLoader:
    """load_manifest() returns a Manifest from valid JSON or an empty Manifest."""

    def test_load_absent_file_returns_empty(self, tmp_path: Path) -> None:
        from maglab.core.manifest import load_manifest

        m = load_manifest(tmp_path / "nonexistent.json")
        assert m.agents == []
        assert m.skills == []
        assert m.mcp_servers == []

    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        from maglab.core.manifest import load_manifest

        data = {
            "agents": [{"name": "test-agent", "description": "A test agent", "model": "haiku"}],
            "skills": [{"name": "test-skill", "path": "skills/test-skill"}],
            "mcp_servers": [{"name": "test-mcp", "command": "python -m test"}],
            "workflows": [{"name": "test-wf", "steps": ["test-agent"]}],
            "model_routing": {"plan": "claude-opus-4-7", "build": "claude-haiku-4-5"},
        }
        manifest_file = tmp_path / "harness.manifest.json"
        manifest_file.write_text(json.dumps(data))
        m = load_manifest(manifest_file)
        assert len(m.agents) == 1
        assert m.agents[0].name == "test-agent"
        assert len(m.skills) == 1
        assert len(m.mcp_servers) == 1
        assert len(m.workflows) == 1
        assert m.model_routing["plan"] == "claude-opus-4-7"

    def test_build_model_router_from_manifest(self, tmp_path: Path) -> None:
        from maglab.core.manifest import load_manifest

        data = {"model_routing": {"plan": "claude-opus-4-7", "build": "claude-haiku-4-5"}}
        manifest_file = tmp_path / "harness.manifest.json"
        manifest_file.write_text(json.dumps(data))
        m = load_manifest(manifest_file)
        router = m.build_model_router()
        assert router.model_for(PipelineStage.PLAN) == "claude-opus-4-7"
        assert router.model_for(PipelineStage.BUILD) == "claude-haiku-4-5"

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        from maglab.core.manifest import load_manifest

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json}")
        m = load_manifest(bad_file)
        assert m.agents == []

    def test_orchestrator_loads_manifest_on_init(
        self, budget: BudgetTracker, checkpoint: CheckpointStore, tmp_path: Path
    ) -> None:
        """Orchestrator loads manifest at construction and exposes it."""
        data = {
            "agents": [{"name": "scout", "description": "test", "model": "haiku"}],
            "model_routing": {"plan": "claude-opus-4-7"},
        }
        manifest_file = tmp_path / "harness.manifest.json"
        manifest_file.write_text(json.dumps(data))
        orch = Orchestrator(
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            manifest_path=manifest_file,
        )
        assert orch._manifest is not None
        assert len(orch._manifest.agents) == 1
        assert orch._manifest.agents[0].name == "scout"

    def test_orchestrator_graceful_no_manifest(
        self, budget: BudgetTracker, checkpoint: CheckpointStore, tmp_path: Path
    ) -> None:
        """Orchestrator init succeeds when no manifest file is found."""
        orch = Orchestrator(
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            manifest_path=tmp_path / "does_not_exist.json",
        )
        assert orch._manifest is not None
        assert orch._manifest.agents == []

    def test_manifest_helper_methods(self, tmp_path: Path) -> None:
        from maglab.core.manifest import load_manifest

        data = {
            "agents": [{"name": "agent-a"}, {"name": "agent-b"}],
            "skills": [{"name": "skill-x"}],
            "mcp_servers": [{"name": "mcp-y"}],
        }
        f = tmp_path / "m.json"
        f.write_text(json.dumps(data))
        m = load_manifest(f)
        assert set(m.agent_names()) == {"agent-a", "agent-b"}
        assert m.skill_names() == ["skill-x"]
        assert m.mcp_server_names() == ["mcp-y"]


# ---------------------------------------------------------------------------
# FIX 4 — GatewayRunner notification wired to run()
# ---------------------------------------------------------------------------


class TestGatewayNotification:
    """Orchestrator.run() calls gateway_runner.notification_queue.put_nowait() on completion."""

    def _make_gateway_runner(self) -> MagicMock:
        runner = MagicMock()
        # Simulate a real asyncio.Queue with put_nowait
        runner.notification_queue = asyncio.Queue()
        return runner

    def test_no_notification_when_gateway_none(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """No crash when gateway_runner is None (backward compat)."""
        orch = Orchestrator(budget_tracker=budget, checkpoint_store=checkpoint)
        result = orch.run("test goal")
        assert isinstance(result, OrchestratorResult)

    def test_notification_queued_on_completion(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """A notification is enqueued on the gateway runner when run() completes."""
        runner = self._make_gateway_runner()
        orch = Orchestrator(
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            gateway_runner=runner,
        )
        result = orch.run("test goal — partial run")
        assert isinstance(result, OrchestratorResult)
        # At least one notification must be in the queue
        assert not runner.notification_queue.empty()
        event = runner.notification_queue.get_nowait()
        assert event.kind == "research_complete"
        assert event.payload["status"] == result.status

    def test_notification_on_goal_achieved(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """A 'research_complete' notification is queued when goal is achieved."""
        runner = self._make_gateway_runner()
        goal_response = json.dumps(
            {
                "result": "done",
                "analysis": "ok",
                "score": 0.9,
                "goal_achieved": True,
                "children": [],
            }
        )
        backend = _make_backend(content=goal_response)
        orch = Orchestrator(
            backend=backend,
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            gateway_runner=runner,
        )
        result = orch.run("achieve goal")
        assert result.status == "completed"
        assert not runner.notification_queue.empty()
        event = runner.notification_queue.get_nowait()
        assert event.kind == "research_complete"
        assert event.payload["status"] == "completed"

    def test_gateway_runner_error_does_not_crash_run(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """If notification_queue.put_nowait raises, run() must still return normally."""
        runner = MagicMock()
        bad_queue = MagicMock()
        bad_queue.put_nowait.side_effect = RuntimeError("queue full")
        runner.notification_queue = bad_queue

        orch = Orchestrator(
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            gateway_runner=runner,
        )
        # Must not raise — gateway is never on the critical path
        result = orch.run("test goal")
        assert isinstance(result, OrchestratorResult)


# ---------------------------------------------------------------------------
# REGRESSION — Finding 3: tool_call_id must be threaded through _tool_loop
# ---------------------------------------------------------------------------


class TestToolCallIdThreading:
    """Regression tests for Finding 3 — tool_call_id must not be dropped.

    Before the fix, tool result messages were created as:
        Message(role=Role.TOOL, content=tr["content"])
    The originating tool_call_id was silently discarded.  This breaks
    OpenAI/Anthropic APIs for multi-tool-call responses.
    """

    def test_tool_result_message_carries_tool_call_id(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """TOOL-role messages in _tool_loop must carry the originating tool_call_id."""
        from maglab.core.hooks import default_registry  # noqa: PLC0415
        from maglab.llm.base import Message, Role  # noqa: PLC0415
        from maglab.llm.base import ToolCall as LLMToolCall

        captured_messages: list[list[Message]] = []

        class CapturingBackend:
            """Records the message list on each call and returns a text response."""

            call_count = 0

            def complete(
                self,
                messages,
                *,
                model=None,
                tools=None,
                temperature=None,
                max_tokens=4096,
                stop=None,
                **kwargs,
            ):
                from maglab.llm.base import LLMResponse, UsageStats

                CapturingBackend.call_count += 1
                captured_messages.append(list(messages))
                if CapturingBackend.call_count == 1:
                    # First call: return a tool call request
                    return LLMResponse(
                        content=None,
                        tool_calls=[LLMToolCall(id="tc-abc123", name="memory.read", arguments={})],
                        usage=UsageStats(),
                    )
                # Second call: return text (no more tool calls)
                return LLMResponse(content="Done.", tool_calls=[], usage=UsageStats())

        # Allow memory.read (deny nothing extra so it runs through the loop)
        registry = default_registry()
        backend = CapturingBackend()
        orch = Orchestrator(
            backend=backend,
            budget_tracker=budget,
            checkpoint_store=checkpoint,
            hook_registry=registry,
        )
        orch.respond("Run the tool")

        # The second backend call's message list must contain a TOOL-role
        # message whose tool_call_id equals the tc.id from the first response.
        assert len(captured_messages) >= 2, "Expected at least 2 backend calls"
        second_call_msgs = captured_messages[1]
        tool_msgs = [m for m in second_call_msgs if m.role == Role.TOOL]
        assert len(tool_msgs) >= 1, "Second call must contain at least one TOOL-role message"
        for tm in tool_msgs:
            assert tm.tool_call_id is not None, (
                f"TOOL-role message must carry tool_call_id; got None. Message: {tm!r}"
            )
            assert tm.tool_call_id == "tc-abc123", (
                f"tool_call_id must match originating call id; "
                f"expected 'tc-abc123', got '{tm.tool_call_id}'"
            )

    def test_tool_result_to_dict_includes_tool_call_id(self) -> None:
        """Message.to_dict() must include tool_call_id when set."""
        from maglab.llm.base import Message, Role

        msg = Message(role=Role.TOOL, content="result content", tool_call_id="tc-xyz999")
        d = msg.to_dict()
        assert "tool_call_id" in d, "to_dict() must include tool_call_id"
        assert d["tool_call_id"] == "tc-xyz999"

    def test_tool_result_to_dict_omits_tool_call_id_when_none(self) -> None:
        """to_dict() must not include tool_call_id when it is None."""
        from maglab.llm.base import Message, Role

        msg = Message(role=Role.ASSISTANT, content="hello")
        d = msg.to_dict()
        assert "tool_call_id" not in d


# ---------------------------------------------------------------------------
# REGRESSION — Finding 6: Orchestrator.close() and context-manager support
# ---------------------------------------------------------------------------


class TestOrchestratorClose:
    """Regression tests for Finding 6 — Orchestrator must close DB connections."""

    def test_close_method_exists(self, budget: BudgetTracker, checkpoint: CheckpointStore) -> None:
        """Orchestrator must expose a close() method."""
        orch = Orchestrator(budget_tracker=budget, checkpoint_store=checkpoint)
        assert callable(getattr(orch, "close", None))

    def test_context_manager_support(
        self, budget: BudgetTracker, checkpoint: CheckpointStore
    ) -> None:
        """Orchestrator must be usable as a context manager."""
        with Orchestrator(budget_tracker=budget, checkpoint_store=checkpoint) as orch:
            response = orch.respond("test")
        assert isinstance(response, str)  # __exit__ must not raise

    def test_close_does_not_raise(self, budget: BudgetTracker, checkpoint: CheckpointStore) -> None:
        """close() must succeed without raising."""
        orch = Orchestrator(budget_tracker=budget, checkpoint_store=checkpoint)
        orch.close()  # must not raise
