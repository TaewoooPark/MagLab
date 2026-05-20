"""maglab.core.budget unit tests — deterministic, no network/LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.core.budget import (
    BudgetEvent,
    BudgetSummary,
    BudgetTracker,
    StepKind,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tracker(tmp_path: Path) -> BudgetTracker:
    """Tracker using a temporary DB path."""
    t = BudgetTracker(session_id="test-session", db_path=tmp_path / "budget.db")
    yield t
    t.close()


# ---------------------------------------------------------------------------
# Basic recording tests
# ---------------------------------------------------------------------------


def test_record_llm_appears_in_summary(tracker: BudgetTracker) -> None:
    tracker.record_llm(
        label="claude-sonnet",
        input_tokens=100,
        output_tokens=50,
        usd_cost=0.001,
        wall_time=1.2,
    )
    s = tracker.session_summary()
    assert s.llm_calls == 1
    assert s.input_tokens == 100
    assert s.output_tokens == 50
    assert abs(s.usd_cost - 0.001) < 1e-9
    assert abs(s.wall_time - 1.2) < 1e-9
    assert s.total_steps == 1


def test_record_tool(tracker: BudgetTracker) -> None:
    tracker.record_tool(label="physics.compute", wall_time=0.05)
    s = tracker.session_summary()
    assert s.tool_calls == 1
    assert s.llm_calls == 0
    assert abs(s.wall_time - 0.05) < 1e-9


def test_record_sim(tracker: BudgetTracker) -> None:
    tracker.record_sim(label="mumax3", wall_time=300.0, core_hours=2.5)
    s = tracker.session_summary()
    assert s.sim_jobs == 1
    assert abs(s.core_hours - 2.5) < 1e-9


def test_multiple_steps_accumulate(tracker: BudgetTracker) -> None:
    tracker.record_llm(
        label="model-a", input_tokens=50, output_tokens=25, usd_cost=0.01, wall_time=1.0
    )
    tracker.record_llm(
        label="model-b", input_tokens=200, output_tokens=100, usd_cost=0.02, wall_time=2.0
    )
    tracker.record_tool(label="tool-x", wall_time=0.1)
    s = tracker.session_summary()
    assert s.llm_calls == 2
    assert s.tool_calls == 1
    assert s.input_tokens == 250
    assert s.output_tokens == 125
    assert abs(s.usd_cost - 0.03) < 1e-9
    assert s.total_steps == 3


# ---------------------------------------------------------------------------
# run_summary tests
# ---------------------------------------------------------------------------


def test_run_summary(tracker: BudgetTracker, tmp_path: Path) -> None:
    run_a = "run-111"
    run_b = "run-222"
    tracker.record_llm(
        label="m",
        input_tokens=10,
        output_tokens=5,
        usd_cost=0.001,
        wall_time=1.0,
        run_id=run_a,
    )
    tracker.record_llm(
        label="m",
        input_tokens=20,
        output_tokens=10,
        usd_cost=0.002,
        wall_time=2.0,
        run_id=run_b,
    )
    sa = tracker.run_summary(run_a)
    assert sa.llm_calls == 1
    assert sa.input_tokens == 10
    sb = tracker.run_summary(run_b)
    assert sb.llm_calls == 1
    assert sb.input_tokens == 20


# ---------------------------------------------------------------------------
# Budget gate tests
# ---------------------------------------------------------------------------


def test_budget_warn_fires_at_80_percent(tmp_path: Path) -> None:
    events: list[BudgetEvent] = []

    def listener(sig):  # type: ignore[no-untyped-def]
        events.append(sig.event)

    # max_usd_per_session = 10.0 (default)
    # 8.0 USD → 80 % → WARN

    tracker = BudgetTracker(
        session_id="warn-test",
        db_path=tmp_path / "warn.db",
        budget_listeners=[listener],
    )
    # directly manipulate the internal limit to 1.0 USD
    tracker._max_usd = 1.0

    # record 0.80 USD → WARN
    tracker.record_llm(label="m", input_tokens=0, output_tokens=0, usd_cost=0.80, wall_time=0.0)
    assert BudgetEvent.WARN in events
    tracker.close()


def test_budget_block_fires_at_100_percent(tmp_path: Path) -> None:
    events: list[BudgetEvent] = []

    def listener(sig):  # type: ignore[no-untyped-def]
        events.append(sig.event)

    tracker = BudgetTracker(
        session_id="block-test",
        db_path=tmp_path / "block.db",
        budget_listeners=[listener],
    )
    tracker._max_usd = 1.0

    tracker.record_llm(label="m", input_tokens=0, output_tokens=0, usd_cost=1.01, wall_time=0.0)
    assert BudgetEvent.BLOCK in events
    assert tracker.is_over_budget()
    tracker.close()


def test_is_over_budget_false_when_under_limit(tracker: BudgetTracker) -> None:
    tracker._max_usd = 10.0
    tracker.record_llm(label="m", input_tokens=0, output_tokens=0, usd_cost=0.001, wall_time=0.0)
    assert not tracker.is_over_budget()


# ---------------------------------------------------------------------------
# Persistence test — total_summary across new connections
# ---------------------------------------------------------------------------


def test_total_summary_persists_across_connections(tmp_path: Path) -> None:
    db = tmp_path / "persist.db"
    t1 = BudgetTracker(session_id="s1", db_path=db)
    t1.record_llm(label="x", input_tokens=5, output_tokens=3, usd_cost=0.005, wall_time=0.5)
    t1.close()

    t2 = BudgetTracker(session_id="s2", db_path=db)
    total = t2.total_summary()
    assert total.llm_calls == 1
    assert total.input_tokens == 5
    t2.close()


# ---------------------------------------------------------------------------
# Empty session summary (maglab cost empty output)
# ---------------------------------------------------------------------------


def test_empty_session_summary(tracker: BudgetTracker) -> None:
    s = tracker.session_summary()
    assert isinstance(s, BudgetSummary)
    assert s.total_steps == 0
    assert s.usd_cost == 0.0


def test_step_kinds(tracker: BudgetTracker) -> None:
    """StepKind enum values are correct."""
    assert StepKind.LLM.value == "llm"
    assert StepKind.TOOL.value == "tool"
    assert StepKind.SIM.value == "sim"
