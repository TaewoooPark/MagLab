"""Autonomy mode & cost-tier gate (§5.8).

Three autonomy levels:
- ``copilot``     — Default. Human confirms all decisions.
- ``semi-auto``   — Tier 0–1 automatic, Tier 2+ requires approval.
- ``autonomous``  — Tier 0–2 automatic, Tier 3 requires human approval.

Action cost-tiers (0 → 3, ordered by cost and risk):
- **Tier 0** — Read-only/computation (always automatic): oracle, physics_compute, read.
- **Tier 1** — Harmless writes (maglab internal state): memory save, session record.
- **Tier 2** — Reversible external writes: file creation, experiment code generation.
- **Tier 3** — Irreversible/high-risk: file deletion, external API submission, real device control.

Only depends on maglab.config.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

from maglab.config import AutonomyConfig, load_config

# ---------------------------------------------------------------------------
# Autonomy mode
# ---------------------------------------------------------------------------


class AutonomyMode:
    """Autonomy mode constants."""

    COPILOT = "copilot"
    SEMI_AUTO = "semi-auto"
    AUTONOMOUS = "autonomous"

    _ALL = {COPILOT, SEMI_AUTO, AUTONOMOUS}

    @classmethod
    def validate(cls, mode: str) -> str:
        if mode not in cls._ALL:
            raise ValueError(f"Unknown autonomy mode: {mode!r}. Allowed values: {cls._ALL}")
        return mode


# ---------------------------------------------------------------------------
# Cost-tier
# ---------------------------------------------------------------------------


class CostTier(IntEnum):
    """Action cost-tier — lower values are more automation-friendly."""

    T0 = 0
    """Read-only/computation — always automatic."""
    T1 = 1
    """Harmless internal maglab writes — automatic in semi-auto and above."""
    T2 = 2
    """Reversible external writes — automatic in autonomous mode."""
    T3 = 3
    """Irreversible/high-risk — always requires human approval."""


# Default action → tier mapping
_DEFAULT_TIER_MAP: dict[str, CostTier] = {
    # Tier 0
    "oracle.check": CostTier.T0,
    "physics.compute": CostTier.T0,
    "physics.check": CostTier.T0,
    "units.convert": CostTier.T0,
    "material.lookup": CostTier.T0,
    "workspace_tree": CostTier.T0,
    "workspace_read_file": CostTier.T0,
    "workspace_search": CostTier.T0,
    "physics_compute": CostTier.T0,
    "physics_check": CostTier.T0,
    "convert_units": CostTier.T0,
    "material_lookup": CostTier.T0,
    "material_search": CostTier.T0,
    "sim_validate": CostTier.T0,
    "memory.read": CostTier.T0,
    "pool.query": CostTier.T0,
    "read": CostTier.T0,
    # Tier 1
    "memory.write": CostTier.T1,
    "session.set": CostTier.T1,
    "pool.add": CostTier.T1,
    "checkpoint.save": CostTier.T1,
    # Tier 2
    "file.create": CostTier.T2,
    "file.write": CostTier.T2,
    "instrument.codegen": CostTier.T2,
    "figure.render": CostTier.T2,
    "figure_render": CostTier.T2,
    # Tier 3
    "file.delete": CostTier.T3,
    "api.submit": CostTier.T3,
    "instrument.execute": CostTier.T3,
    "review.patch_apply": CostTier.T3,
    "authoring.submit": CostTier.T3,
}


def classify_action(action_name: str) -> CostTier:
    """Return the default cost-tier for the given action name.

    Unknown actions are conservatively classified as Tier 2.
    """
    return _DEFAULT_TIER_MAP.get(action_name, CostTier.T2)


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """Autonomy gate decision result."""

    allowed: bool
    """True means immediately executable. False means human approval required or blocked."""
    requires_approval: bool
    """Whether a human approval UI is needed."""
    reason: str
    """Decision rationale message."""
    tier: CostTier
    """Determined tier."""
    mode: str
    """Current autonomy mode."""


# ---------------------------------------------------------------------------
# AutonomyGate
# ---------------------------------------------------------------------------


class AutonomyGate:
    """Autonomy gate — called before action execution to decide automatic/approval/block.

    Parameters
    ----------
    config:
        ``AutonomyConfig`` (None → loaded from ``load_config()``).
    approval_callback:
        Callback invoked when Tier 2/3 approval is required (user UI). Returns True = approved.
    """

    def __init__(
        self,
        config: AutonomyConfig | None = None,
        approval_callback: Callable[[str, CostTier], bool] | None = None,
    ) -> None:
        cfg = config or load_config().autonomy
        self._mode = AutonomyMode.validate(cfg.mode)
        self._approval_callback = approval_callback
        self._custom_tiers: dict[str, CostTier] = {}

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Change the autonomy mode."""
        self._mode = AutonomyMode.validate(mode)

    def register_tier(self, action_name: str, tier: CostTier) -> None:
        """Register a custom action tier."""
        self._custom_tiers[action_name] = tier

    def tier_of(self, action_name: str) -> CostTier:
        """Return the cost-tier of the given action."""
        return self._custom_tiers.get(action_name, classify_action(action_name))

    def check(self, action_name: str, tier: CostTier | None = None) -> GateResult:
        """Gate decision.

        Parameters
        ----------
        action_name:
            Name of the action to execute.
        tier:
            Explicit tier (if None, uses ``tier_of(action_name)``).

        Returns
        -------
        GateResult — allowed=True means execute immediately, False means wait/block.
        """
        effective_tier = tier if tier is not None else self.tier_of(action_name)

        if self._mode == AutonomyMode.COPILOT:
            # copilot: only Tier 0 is automatic, others require approval
            if effective_tier == CostTier.T0:
                return GateResult(
                    allowed=True,
                    requires_approval=False,
                    reason="Tier 0 action — automatically allowed in copilot mode.",
                    tier=effective_tier,
                    mode=self._mode,
                )
            return self._request_approval(action_name, effective_tier)

        elif self._mode == AutonomyMode.SEMI_AUTO:
            # semi-auto: Tier 0–1 automatic, Tier 2+ requires approval
            if effective_tier <= CostTier.T1:
                return GateResult(
                    allowed=True,
                    requires_approval=False,
                    reason=f"Tier {effective_tier} action — automatically allowed in semi-auto mode.",
                    tier=effective_tier,
                    mode=self._mode,
                )
            return self._request_approval(action_name, effective_tier)

        else:  # autonomous
            # autonomous: Tier 0–2 automatic, Tier 3 requires approval
            if effective_tier <= CostTier.T2:
                return GateResult(
                    allowed=True,
                    requires_approval=False,
                    reason=f"Tier {effective_tier} action — automatically allowed in autonomous mode.",
                    tier=effective_tier,
                    mode=self._mode,
                )
            return self._request_approval(action_name, effective_tier)

    def _request_approval(self, action_name: str, tier: CostTier) -> GateResult:
        """Invoke approval callback or return a pending-approval result."""
        msg = (
            f"Action '{action_name}' (Tier {tier}) requires human approval "
            f"in current mode '{self._mode}'."
        )
        if self._approval_callback is not None:
            approved = self._approval_callback(action_name, tier)
            return GateResult(
                allowed=approved,
                requires_approval=True,
                reason=msg + (" [approved]" if approved else " [denied]"),
                tier=tier,
                mode=self._mode,
            )
        # No callback — return pending-approval state
        return GateResult(
            allowed=False,
            requires_approval=True,
            reason=msg,
            tier=tier,
            mode=self._mode,
        )
