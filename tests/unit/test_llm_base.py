"""Unit tests for maglab.llm.base.

No external calls. Tests only pure Python/Pydantic logic.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from maglab.llm.base import (
    ContentBlock,
    LLMBackend,
    LLMResponse,
    Message,
    ModelRouter,
    PipelineStage,
    Role,
    ToolCall,
    UsageStats,
)

# ---------------------------------------------------------------------------
# Concrete backend stub (for tests)
# ---------------------------------------------------------------------------


class _StubBackend(LLMBackend):
    """Minimal concrete implementation for testing."""

    default_model = "stub-model"

    def complete(self, messages: list[Message], **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="stub", model=self.default_model)

    def stream(self, messages: list[Message], **kwargs: Any) -> Iterator[str]:
        yield "stub"

    def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Role / Message tests
# ---------------------------------------------------------------------------


class TestMessage:
    def test_to_dict_str_content(self) -> None:
        """Converts a message with string content to a dictionary."""
        msg = Message(role=Role.USER, content="hello")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "hello"}

    def test_to_dict_content_blocks(self) -> None:
        """Converts a ContentBlock list to a dictionary."""
        blocks = [ContentBlock(type="text", text="hi")]
        msg = Message(role=Role.ASSISTANT, content=blocks)
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert isinstance(d["content"], list)
        assert d["content"][0]["text"] == "hi"

    def test_to_dict_includes_name(self) -> None:
        """The name field is included in the dictionary when present."""
        msg = Message(role=Role.TOOL, content="result", name="my_tool")
        d = msg.to_dict()
        assert d["name"] == "my_tool"

    def test_to_dict_excludes_none_name(self) -> None:
        """The name field is omitted from the dictionary when None."""
        msg = Message(role=Role.USER, content="q")
        d = msg.to_dict()
        assert "name" not in d

    def test_system_role_value(self) -> None:
        """The system role has the correct string value."""
        msg = Message(role=Role.SYSTEM, content="sys prompt")
        assert msg.to_dict()["role"] == "system"

    def test_content_block_exclude_none(self) -> None:
        """None fields are excluded from ContentBlock serialization."""
        block = ContentBlock(type="text", text="hello")
        dumped = block.model_dump(exclude_none=True)
        assert "tool_use_id" not in dumped
        assert "content" not in dumped


# ---------------------------------------------------------------------------
# UsageStats tests
# ---------------------------------------------------------------------------


class TestUsageStats:
    def test_defaults(self) -> None:
        """Default values are initialised to 0."""
        u = UsageStats()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0
        assert u.estimated_cost_usd is None
        assert u.latency_sec is None

    def test_assignment(self) -> None:
        """Value assignment works correctly."""
        u = UsageStats(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert u.total_tokens == 150

    def test_latency_settable(self) -> None:
        """latency_sec can be set after creation."""
        u = UsageStats()
        u.latency_sec = 1.23
        assert u.latency_sec == pytest.approx(1.23)


# ---------------------------------------------------------------------------
# LLMResponse tests
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_defaults(self) -> None:
        """Default values are correct."""
        r = LLMResponse()
        assert r.content is None
        assert r.tool_calls == []
        assert r.stop_reason == "end_turn"
        assert r.raw is None
        assert r.model is None

    def test_with_tool_calls(self) -> None:
        """The tool_calls field is stored correctly."""
        tc = ToolCall(id="tc-1", name="my_tool", arguments={"x": 1})
        r = LLMResponse(tool_calls=[tc], stop_reason="tool_use")
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "my_tool"
        assert r.stop_reason == "tool_use"


# ---------------------------------------------------------------------------
# PipelineStage / ModelRouter tests
# ---------------------------------------------------------------------------


class TestModelRouter:
    def test_default_routing(self) -> None:
        """Uses the default routing table correctly."""
        router = ModelRouter.default()
        plan_model = router.model_for(PipelineStage.PLAN)
        build_model = router.model_for(PipelineStage.BUILD)
        assert "opus" in plan_model or "claude" in plan_model
        assert build_model != ""

    def test_custom_routing_overrides_default(self) -> None:
        """Custom config overrides the default values."""
        router = ModelRouter(routing_config={"plan": "gpt-4o", "build": "gpt-4o-mini"})
        assert router.model_for(PipelineStage.PLAN) == "gpt-4o"
        assert router.model_for(PipelineStage.BUILD) == "gpt-4o-mini"

    def test_unknown_stage_falls_back_to_default(self) -> None:
        """Unknown stage falls back to the DEFAULT model."""
        router = ModelRouter.default()
        result = router.model_for("nonexistent_stage")
        default = router.model_for(PipelineStage.DEFAULT)
        assert result == default

    def test_string_stage_resolved(self) -> None:
        """String stage names are resolved correctly."""
        router = ModelRouter.default()
        assert router.model_for("plan") == router.model_for(PipelineStage.PLAN)
        assert router.model_for("build") == router.model_for(PipelineStage.BUILD)
        assert router.model_for("summarize") == router.model_for(PipelineStage.SUMMARIZE)

    def test_unknown_config_keys_ignored(self) -> None:
        """Unknown config keys are silently ignored (no exception)."""
        router = ModelRouter(routing_config={"future_stage": "some-model"})
        # Must not raise
        assert router.model_for(PipelineStage.DEFAULT) != ""

    def test_all_stages_have_model(self) -> None:
        """All PipelineStage members have a model assigned."""
        router = ModelRouter.default()
        for stage in PipelineStage:
            model = router.model_for(stage)
            assert model, f"stage={stage} has no model assigned"

    def test_partial_config_inherits_defaults(self) -> None:
        """Setting only some stages leaves the rest at their default values."""
        router = ModelRouter(routing_config={"plan": "custom-plan-model"})
        assert router.model_for(PipelineStage.PLAN) == "custom-plan-model"
        # BUILD keeps the default
        default_router = ModelRouter.default()
        assert router.model_for(PipelineStage.BUILD) == default_router.model_for(
            PipelineStage.BUILD
        )


# ---------------------------------------------------------------------------
# LLMBackend abstract class tests
# ---------------------------------------------------------------------------


class TestLLMBackend:
    def test_stub_backend_complete(self) -> None:
        """Concrete implementation returns correctly from complete()."""
        backend = _StubBackend()
        msgs = [Message(role=Role.USER, content="ping")]
        result = backend.complete(msgs)
        assert result.content == "stub"

    def test_stub_backend_stream(self) -> None:
        """Concrete implementation yields text from stream()."""
        backend = _StubBackend()
        msgs = [Message(role=Role.USER, content="ping")]
        chunks = list(backend.stream(msgs))
        assert chunks == ["stub"]

    def test_stub_backend_health_check(self) -> None:
        """Concrete implementation returns True from health_check()."""
        backend = _StubBackend()
        assert backend.health_check() is True

    def test_resolve_model_returns_default(self) -> None:
        """Returns default_model when model=None."""
        backend = _StubBackend()
        assert backend._resolve_model(None) == "stub-model"

    def test_resolve_model_returns_provided(self) -> None:
        """Returns the provided model string unchanged."""
        backend = _StubBackend()
        assert backend._resolve_model("custom-model") == "custom-model"

    def test_abstract_class_cannot_instantiate(self) -> None:
        """LLMBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            LLMBackend()  # type: ignore[abstract]

    def test_partial_implementation_raises_type_error(self) -> None:
        """Implementing only some abstract methods raises TypeError."""

        class _PartialBackend(LLMBackend):
            def complete(self, messages: list[Message], **kwargs: Any) -> LLMResponse:
                return LLMResponse()

        with pytest.raises(TypeError):
            _PartialBackend()  # type: ignore[abstract]
