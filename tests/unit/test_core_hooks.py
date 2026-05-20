"""maglab.core.hooks unit tests — deterministic, no network/LLM."""

from __future__ import annotations

from maglab.config import AutonomyConfig
from maglab.core.autonomy import AutonomyGate
from maglab.core.hooks import (
    DenyRule,
    HookRegistry,
    HookResult,
    ToolCall,
    default_registry,
    deny_rule_hook,
    irreversibility_hook,
    plan_mode_hook,
)

# ---------------------------------------------------------------------------
# DenyRule
# ---------------------------------------------------------------------------


def test_deny_rule_glob_match() -> None:
    rule = DenyRule(pattern="file.*", reason="file operations forbidden")
    assert rule.matches("file.delete") is True
    assert rule.matches("file.write") is True
    assert rule.matches("physics.compute") is False


def test_deny_rule_exact_match() -> None:
    rule = DenyRule(pattern="api.submit", reason="submission forbidden")
    assert rule.matches("api.submit") is True
    assert rule.matches("api.submit.extra") is False


def test_deny_rule_regex_match() -> None:
    rule = DenyRule(pattern=r"file\.(delete|write)", reason="file modification forbidden", is_regex=True)
    assert rule.matches("file.delete") is True
    assert rule.matches("file.write") is True
    assert rule.matches("file.read") is False


# ---------------------------------------------------------------------------
# deny_rule_hook
# ---------------------------------------------------------------------------


def test_deny_rule_hook_blocks_matching_tool() -> None:
    hook = deny_rule_hook([DenyRule(pattern="bad.tool", reason="forbidden tool")])
    call = ToolCall(name="bad.tool", args={})
    result = hook(call)
    assert result.allow is False
    assert "forbidden tool" in result.reason


def test_deny_rule_hook_allows_non_matching() -> None:
    hook = deny_rule_hook([DenyRule(pattern="bad.tool", reason="forbidden")])
    call = ToolCall(name="good.tool", args={})
    result = hook(call)
    assert result.allow is True


def test_deny_rule_hook_empty_rules_always_allows() -> None:
    hook = deny_rule_hook([])
    call = ToolCall(name="anything", args={})
    assert hook(call).allow is True


# ---------------------------------------------------------------------------
# plan_mode_hook
# ---------------------------------------------------------------------------


def test_plan_mode_blocks_execution_tools_when_active() -> None:
    hook = plan_mode_hook(plan_mode=True)
    # file.create = T2 → blocked in plan mode
    call = ToolCall(name="file.create", args={})
    result = hook(call)
    assert result.allow is False
    assert "plan_mode" in result.reason


def test_plan_mode_allows_read_tools_when_active() -> None:
    hook = plan_mode_hook(plan_mode=True)
    # read = T0 → allowed even in plan mode
    call = ToolCall(name="read", args={})
    result = hook(call)
    assert result.allow is True


def test_plan_mode_allows_everything_when_inactive() -> None:
    hook = plan_mode_hook(plan_mode=False)
    call = ToolCall(name="file.delete", args={})
    assert hook(call).allow is True


# ---------------------------------------------------------------------------
# irreversibility_hook
# ---------------------------------------------------------------------------


def _make_gate(mode: str = "copilot") -> AutonomyGate:
    return AutonomyGate(config=AutonomyConfig(mode=mode))  # type: ignore[call-arg]


def test_irreversibility_blocks_tier2_in_copilot() -> None:
    gate = _make_gate("copilot")
    hook = irreversibility_hook(gate)
    call = ToolCall(name="file.create", args={})
    result = hook(call)
    assert result.allow is False


def test_irreversibility_allows_tier0_always() -> None:
    gate = _make_gate("copilot")
    hook = irreversibility_hook(gate)
    call = ToolCall(name="oracle.check", args={})
    assert hook(call).allow is True


def test_irreversibility_allows_tier2_in_autonomous() -> None:
    gate = _make_gate("autonomous")
    hook = irreversibility_hook(gate)
    call = ToolCall(name="file.create", args={})
    result = hook(call)
    assert result.allow is True


# ---------------------------------------------------------------------------
# HookRegistry
# ---------------------------------------------------------------------------


def test_registry_allows_tier0_no_deny_rules() -> None:
    registry = HookRegistry(plan_mode=False)
    call = ToolCall(name="read", args={})
    allowed, reason = registry.is_allowed(call)
    assert allowed is True


def test_registry_blocks_via_deny_rule() -> None:
    rules = [DenyRule(pattern="forbidden.*", reason="test forbidden")]
    registry = HookRegistry(deny_rules=rules)
    call = ToolCall(name="forbidden.action", args={})
    allowed, reason = registry.is_allowed(call)
    assert allowed is False
    assert "forbidden" in reason


def test_registry_blocks_in_plan_mode() -> None:
    registry = HookRegistry(plan_mode=True)
    # file.write = T2 → blocked in plan mode
    call = ToolCall(name="file.write", args={})
    allowed, _ = registry.is_allowed(call)
    assert allowed is False


def test_registry_custom_hook_registration() -> None:
    registry = HookRegistry()

    def always_deny(call: ToolCall) -> HookResult:
        return HookResult(allow=False, reason="custom block", hook_name="custom")

    registry.register("custom-hook", always_deny)
    call = ToolCall(name="any.tool", args={})
    allowed, reason = registry.is_allowed(call)
    assert allowed is False
    assert "custom block" in reason


def test_registry_prepend_hook_runs_first() -> None:
    registry = HookRegistry()
    order: list[str] = []

    def hook_a(call: ToolCall) -> HookResult:
        order.append("A")
        return HookResult(allow=True, reason="A", hook_name="A")

    def hook_b(call: ToolCall) -> HookResult:
        order.append("B")
        return HookResult(allow=True, reason="B", hook_name="B")

    registry.register("hook-b", hook_b)
    registry.register("hook-a", hook_a, prepend=True)
    registry.run(ToolCall(name="anything", args={}))
    assert order[0] == "A"


def test_registry_stops_on_first_deny() -> None:
    registry = HookRegistry()
    called: list[str] = []

    def deny_hook(call: ToolCall) -> HookResult:
        called.append("deny")
        return HookResult(allow=False, reason="blocked", hook_name="deny")

    def after_hook(call: ToolCall) -> HookResult:
        called.append("after")
        return HookResult(allow=True, reason="passed", hook_name="after")

    registry.register("deny", deny_hook)
    registry.register("after", after_hook)
    registry.run(ToolCall(name="x", args={}))
    assert "deny" in called
    assert "after" not in called


def test_registry_unregister() -> None:
    registry = HookRegistry()
    registry.register("temp-hook", lambda c: HookResult(allow=True, reason="", hook_name="temp"))
    assert "temp-hook" in registry.registered_hook_names
    removed = registry.unregister("temp-hook")
    assert removed is True
    assert "temp-hook" not in registry.registered_hook_names


def test_registry_unregister_nonexistent_returns_false() -> None:
    registry = HookRegistry()
    assert registry.unregister("nonexistent") is False


def test_registry_set_plan_mode() -> None:
    registry = HookRegistry(plan_mode=False)
    # plan mode inactive → file.write allowed
    call = ToolCall(name="file.write", args={})
    allowed_before, _ = registry.is_allowed(call)
    # activate plan mode
    registry.set_plan_mode(True)
    allowed_after, _ = registry.is_allowed(call)
    # plan_mode_hook should have blocked it
    assert not allowed_after


def test_registry_registered_hook_names() -> None:
    registry = HookRegistry()
    names = registry.registered_hook_names
    assert isinstance(names, list)
    assert "plan_mode_hook" in names


# ---------------------------------------------------------------------------
# default_registry
# ---------------------------------------------------------------------------


def test_default_registry_returns_hook_registry() -> None:
    reg = default_registry()
    assert isinstance(reg, HookRegistry)


def test_default_registry_with_deny_rules() -> None:
    rules = [DenyRule(pattern="bad.call", reason="default forbidden")]
    reg = default_registry(deny_rules=rules)
    allowed, _ = reg.is_allowed(ToolCall(name="bad.call", args={}))
    assert allowed is False


def test_default_registry_includes_oracle_hook() -> None:
    reg = default_registry()
    assert "oracle_hook" in reg.registered_hook_names
    # oracle_hook must run first (prepended) so physics is gated before tier/plan checks
    assert reg.registered_hook_names[0] == "oracle_hook"
