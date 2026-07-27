"""Hook framework and registry (§5.8, §5.15).

PreToolUse hook system — a chainable list of hook functions executed *before* each tool call.

This file implements only the hook **framework / registry**.
The concrete `honesty_gate` (being written in report/) is not imported here.
Only the hook registration interface is defined.

Built-in hooks:
- ``deny_rule_hook``        — Block tools matching configuration-based deny patterns.
- ``irreversibility_hook``  — Route irreversible tools (Tier 2+) through the autonomy gate.
- ``plan_mode_hook``        — Block execution tools while in plan mode.
- ``oracle_hook``           — Block physics tools called with unphysical parameters.

Depends on maglab.config and maglab.core.autonomy; ``oracle_hook`` lazily
imports maglab.physics.oracle only when a tool carries physical parameters.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maglab.config import load_config
from maglab.core.autonomy import AutonomyGate, CostTier

# ---------------------------------------------------------------------------
# Hook data structures
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """Tool call information received by a PreToolUse hook."""

    name: str
    """Tool name."""
    args: dict[str, Any]
    """Tool arguments."""
    meta: dict[str, Any] = field(default_factory=dict)
    """Additional metadata (caller context, etc.)."""


@dataclass
class HookResult:
    """Hook execution result."""

    allow: bool
    """True means continue with the tool call. False means block."""
    reason: str
    """Decision rationale message."""
    hook_name: str
    """Hook name."""


# Hook function type
HookFn = Callable[[ToolCall], HookResult]


# ---------------------------------------------------------------------------
# Deny rule data structures
# ---------------------------------------------------------------------------


@dataclass
class DenyRule:
    """A tool-call blocking rule."""

    pattern: str
    """Glob/regex pattern to match against the tool name."""
    reason: str
    """Block reason message."""
    is_regex: bool = False
    """When True, treat pattern as a regular expression."""

    def matches(self, tool_name: str) -> bool:
        """Return True if this rule matches the given tool name."""
        if self.is_regex:
            return bool(re.fullmatch(self.pattern, tool_name))
        # glob-like: support * wildcard
        regex = re.escape(self.pattern).replace(r"\*", ".*")
        return bool(re.fullmatch(regex, tool_name))


# ---------------------------------------------------------------------------
# Built-in hook factories
# ---------------------------------------------------------------------------


def deny_rule_hook(rules: list[DenyRule]) -> HookFn:
    """Return a hook that applies the given deny rules."""

    def _hook(call: ToolCall) -> HookResult:
        for rule in rules:
            if rule.matches(call.name):
                return HookResult(
                    allow=False,
                    reason=f"[deny_rule] Tool '{call.name}' blocked: {rule.reason}",
                    hook_name="deny_rule_hook",
                )
        return HookResult(allow=True, reason="deny_rule: passed", hook_name="deny_rule_hook")

    return _hook


def irreversibility_hook(gate: AutonomyGate) -> HookFn:
    """Return a hook that routes irreversible tools (Tier 2+) through the autonomy gate."""

    def _hook(call: ToolCall) -> HookResult:
        tier = gate.tier_of(call.name)
        if tier >= CostTier.T2:
            result = gate.check(call.name, tier)
            if not result.allowed:
                return HookResult(
                    allow=False,
                    reason=f"[irreversibility] Tier {tier} tool '{call.name}' — {result.reason}",
                    hook_name="irreversibility_hook",
                )
        return HookResult(
            allow=True,
            reason="irreversibility: passed",
            hook_name="irreversibility_hook",
        )

    return _hook


def plan_mode_hook(plan_mode: bool = False) -> HookFn:
    """Return a hook that blocks execution (write/irreversible) tools in plan mode."""

    execution_tier_threshold = CostTier.T2  # T2 and above are blocked in plan mode

    def _hook(call: ToolCall) -> HookResult:
        if not plan_mode:
            return HookResult(allow=True, reason="plan_mode: inactive", hook_name="plan_mode_hook")
        # Block execution tools in plan mode
        tier = classify_tier_simple(call.name)
        if tier >= execution_tier_threshold:
            return HookResult(
                allow=False,
                reason=f"[plan_mode] Blocking Tier {tier} tool '{call.name}' during planning phase.",
                hook_name="plan_mode_hook",
            )
        return HookResult(allow=True, reason="plan_mode: passed", hook_name="plan_mode_hook")

    return _hook


def oracle_hook(
    oracle_check_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> HookFn:
    """Return a hook that blocks physics tools called with unphysical parameters.

    Extracts the oracle-recognised physical parameters from the tool call and
    runs them through the deterministic physics sanity oracle.  If the oracle
    reports an unphysical value (e.g. ``alpha=50``, ``T=-10``), the call is
    blocked *before* the tool executes.  Tool calls with no recognised physical
    parameters pass through unchanged.

    Parameters
    ----------
    oracle_check_fn:
        Override for the oracle entry point ``(params: dict) -> OracleResult``.
        ``None`` uses ``maglab.physics.oracle.check`` (imported lazily).
    """

    # Parameter names the sanity oracle understands (see physics/oracle.py).
    recognised = {"alpha", "M", "Ms", "T", "velocity", "A", "K", "T_C", "l_ex"}

    def _hook(call: ToolCall) -> HookResult:
        params = {
            k: v
            for k, v in call.args.items()
            if k in recognised and isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        if not params:
            return HookResult(
                allow=True,
                reason="oracle: no physical parameters",
                hook_name="oracle_hook",
            )
        if oracle_check_fn is not None:
            check_fn = oracle_check_fn
        else:
            from maglab.physics.oracle import check as _oracle_check  # noqa: PLC0415

            check_fn = _oracle_check

        result = check_fn(params)
        if not result.ok:
            return HookResult(
                allow=False,
                reason=f"[oracle] Tool '{call.name}' blocked — {result.reason}",
                hook_name="oracle_hook",
            )
        return HookResult(allow=True, reason="oracle: passed", hook_name="oracle_hook")

    return _hook


def classify_tier_simple(tool_name: str) -> CostTier:
    """Classify a tool by name into a tier (partial copy of autonomy classifier — avoids circular import)."""
    from maglab.core.autonomy import classify_action  # noqa: PLC0415

    return classify_action(tool_name)


# ---------------------------------------------------------------------------
# HookRegistry
# ---------------------------------------------------------------------------


class HookRegistry:
    """PreToolUse hook registry.

    Hooks are chained and executed in registration order.
    Execution stops immediately on the first block (allow=False).

    Parameters
    ----------
    plan_mode:
        When True, plan_mode_hook is automatically activated.
    autonomy_gate:
        Gate used by the irreversibility hook (None → irreversibility_hook not registered).
    deny_rules:
        Initial deny rules list.
    """

    def __init__(
        self,
        *,
        plan_mode: bool = False,
        autonomy_gate: AutonomyGate | None = None,
        deny_rules: list[DenyRule] | None = None,
    ) -> None:
        self._hooks: list[tuple[str, HookFn]] = []
        self._plan_mode = plan_mode

        # Register default hooks
        rules = deny_rules or []
        if rules:
            self.register("deny_rule_hook", deny_rule_hook(rules))
        self.register("plan_mode_hook", plan_mode_hook(plan_mode))
        if autonomy_gate is not None:
            self.register("irreversibility_hook", irreversibility_hook(autonomy_gate))

    def register(self, name: str, hook: HookFn, *, prepend: bool = False) -> None:
        """Register a hook.

        Parameters
        ----------
        name:
            Hook identifier name.
        hook:
            ``HookFn`` — ``(ToolCall) -> HookResult``.
        prepend:
            When True, insert at the front of the list.
        """
        entry = (name, hook)
        if prepend:
            self._hooks.insert(0, entry)
        else:
            self._hooks.append(entry)

    def unregister(self, name: str) -> bool:
        """Remove a hook by name. Returns True if successfully removed."""
        before = len(self._hooks)
        self._hooks = [(n, h) for n, h in self._hooks if n != name]
        return len(self._hooks) < before

    def run(self, call: ToolCall) -> list[HookResult]:
        """Execute all hooks in order.

        Stops immediately on the first block (allow=False).

        Returns
        -------
        List of executed hook results. The last entry is the overall decision.
        """
        results: list[HookResult] = []
        for _name, hook in self._hooks:
            result = hook(call)
            results.append(result)
            if not result.allow:
                break
        return results

    def is_allowed(self, call: ToolCall) -> tuple[bool, str]:
        """Return whether the tool call is allowed and the decision reason.

        Returns
        -------
        (allowed: bool, reason: str)
        """
        results = self.run(call)
        if not results:
            return True, "No hooks registered — allowed."
        last = results[-1]
        return last.allow, last.reason

    def set_plan_mode(self, active: bool) -> None:
        """Dynamically switch plan mode (re-registers plan_mode_hook)."""
        self._plan_mode = active
        self.unregister("plan_mode_hook")
        self.register("plan_mode_hook", plan_mode_hook(active))

    @property
    def registered_hook_names(self) -> list[str]:
        """List of currently registered hook names."""
        return [name for name, _ in self._hooks]


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def interactive_approval(action_name: str, tier: CostTier) -> bool:
    """Ask the operator to approve one irreversible action.

    Without a callback the gate denies every Tier 2+ action and there is no way
    to say yes, so the only workable response was to switch the whole session to
    ``autonomous`` — turning the gate off for everything. A safety control with
    no escape hatch gets disabled wholesale, which is worse than one that asks.
    """
    import sys

    from rich.console import Console

    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        return False

    console = Console(stderr=True)
    console.print(
        f"\n[yellow]Approval needed[/] — Tier {tier} action [bold]{action_name}[/] is irreversible."
    )
    try:
        answer = console.input("  Run it? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("  [dim]declined[/]")
        return False
    return answer in {"y", "yes"}


def default_registry(
    *,
    deny_rules: list[DenyRule] | None = None,
    plan_mode: bool = False,
    approval_callback: Callable[[str, CostTier], bool] | None = None,
) -> HookRegistry:
    """Create a HookRegistry with default settings.

    Automatically creates an AutonomyGate from the configured autonomy mode.
    On an interactive terminal, Tier 2+ actions prompt for approval instead of
    being denied outright.
    """
    cfg = load_config()
    gate = AutonomyGate(
        config=cfg.autonomy,
        approval_callback=approval_callback or interactive_approval,
    )
    registry = HookRegistry(
        plan_mode=plan_mode,
        autonomy_gate=gate,
        deny_rules=deny_rules or [],
    )
    # Oracle range check — blocks physics tools with unphysical parameters
    # before execution (§5.15, T-P0-29).  Prepended so physics validation
    # runs ahead of the tier / plan-mode gates and is never skipped.
    registry.register("oracle_hook", oracle_hook(), prepend=True)
    return registry
