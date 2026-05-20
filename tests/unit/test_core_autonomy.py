"""maglab.core.autonomy unit tests — deterministic, no network/LLM."""

from __future__ import annotations

import pytest

from maglab.config import AutonomyConfig
from maglab.core.autonomy import (
    AutonomyGate,
    AutonomyMode,
    CostTier,
    GateResult,
    classify_action,
)

# ---------------------------------------------------------------------------
# AutonomyMode validation
# ---------------------------------------------------------------------------


def test_mode_validate_valid() -> None:
    assert AutonomyMode.validate("copilot") == "copilot"
    assert AutonomyMode.validate("semi-auto") == "semi-auto"
    assert AutonomyMode.validate("autonomous") == "autonomous"


def test_mode_validate_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown autonomy mode"):
        AutonomyMode.validate("turbo")


# ---------------------------------------------------------------------------
# CostTier classification
# ---------------------------------------------------------------------------


def test_classify_known_tier0() -> None:
    assert classify_action("oracle.check") == CostTier.T0
    assert classify_action("physics.compute") == CostTier.T0
    assert classify_action("read") == CostTier.T0


def test_classify_known_tier1() -> None:
    assert classify_action("memory.write") == CostTier.T1
    assert classify_action("session.set") == CostTier.T1


def test_classify_known_tier2() -> None:
    assert classify_action("file.create") == CostTier.T2
    assert classify_action("file.write") == CostTier.T2


def test_classify_known_tier3() -> None:
    assert classify_action("file.delete") == CostTier.T3
    assert classify_action("api.submit") == CostTier.T3
    assert classify_action("instrument.execute") == CostTier.T3


def test_classify_unknown_defaults_to_tier2() -> None:
    assert classify_action("some.unknown.action") == CostTier.T2


# ---------------------------------------------------------------------------
# copilot mode
# ---------------------------------------------------------------------------


def _make_gate(mode: str, callback=None) -> AutonomyGate:
    cfg = AutonomyConfig(mode=mode)  # type: ignore[call-arg]
    return AutonomyGate(config=cfg, approval_callback=callback)


def test_copilot_allows_tier0_automatically() -> None:
    gate = _make_gate("copilot")
    result = gate.check("oracle.check")
    assert result.allowed is True
    assert result.requires_approval is False


def test_copilot_requires_approval_for_tier1() -> None:
    gate = _make_gate("copilot")
    result = gate.check("memory.write")
    assert result.requires_approval is True
    assert result.allowed is False  # no callback → pending = False


def test_copilot_requires_approval_for_tier3() -> None:
    gate = _make_gate("copilot")
    result = gate.check("file.delete")
    assert result.requires_approval is True
    assert result.allowed is False


def test_copilot_approval_callback_approve() -> None:
    gate = _make_gate("copilot", callback=lambda name, tier: True)
    result = gate.check("memory.write")
    assert result.allowed is True
    assert result.requires_approval is True


def test_copilot_approval_callback_deny() -> None:
    gate = _make_gate("copilot", callback=lambda name, tier: False)
    result = gate.check("memory.write")
    assert result.allowed is False
    assert result.requires_approval is True


# ---------------------------------------------------------------------------
# semi-auto mode
# ---------------------------------------------------------------------------


def test_semi_auto_allows_tier0() -> None:
    gate = _make_gate("semi-auto")
    assert gate.check("read").allowed is True


def test_semi_auto_allows_tier1() -> None:
    gate = _make_gate("semi-auto")
    result = gate.check("memory.write")
    assert result.allowed is True
    assert result.requires_approval is False


def test_semi_auto_requires_approval_for_tier2() -> None:
    gate = _make_gate("semi-auto")
    result = gate.check("file.create")
    assert result.requires_approval is True
    assert result.allowed is False


def test_semi_auto_requires_approval_for_tier3() -> None:
    gate = _make_gate("semi-auto")
    result = gate.check("file.delete")
    assert result.requires_approval is True


# ---------------------------------------------------------------------------
# autonomous mode
# ---------------------------------------------------------------------------


def test_autonomous_allows_tier0() -> None:
    gate = _make_gate("autonomous")
    assert gate.check("physics.compute").allowed is True


def test_autonomous_allows_tier1() -> None:
    gate = _make_gate("autonomous")
    assert gate.check("session.set").allowed is True


def test_autonomous_allows_tier2() -> None:
    gate = _make_gate("autonomous")
    result = gate.check("file.create")
    assert result.allowed is True
    assert result.requires_approval is False


def test_autonomous_requires_approval_for_tier3() -> None:
    gate = _make_gate("autonomous")
    result = gate.check("file.delete")
    assert result.requires_approval is True
    assert result.allowed is False


# ---------------------------------------------------------------------------
# tier_of and register_tier
# ---------------------------------------------------------------------------


def test_tier_of_default() -> None:
    gate = _make_gate("copilot")
    assert gate.tier_of("oracle.check") == CostTier.T0


def test_register_custom_tier() -> None:
    gate = _make_gate("semi-auto")
    gate.register_tier("custom.action", CostTier.T0)
    assert gate.tier_of("custom.action") == CostTier.T0
    # semi-auto with T0 → automatically allowed
    result = gate.check("custom.action")
    assert result.allowed is True


# ---------------------------------------------------------------------------
# set_mode
# ---------------------------------------------------------------------------


def test_set_mode_changes_behavior() -> None:
    gate = _make_gate("copilot")
    # copilot with T1 → approval required
    assert gate.check("memory.write").requires_approval is True
    # switch to semi-auto
    gate.set_mode("semi-auto")
    assert gate.check("memory.write").allowed is True


def test_set_mode_invalid() -> None:
    gate = _make_gate("copilot")
    with pytest.raises(ValueError):
        gate.set_mode("god-mode")


# ---------------------------------------------------------------------------
# GateResult type validation
# ---------------------------------------------------------------------------


def test_gate_result_is_dataclass() -> None:
    gate = _make_gate("autonomous")
    result = gate.check("physics.compute")
    assert isinstance(result, GateResult)
    assert isinstance(result.allowed, bool)
    assert isinstance(result.tier, CostTier)
    assert isinstance(result.mode, str)
