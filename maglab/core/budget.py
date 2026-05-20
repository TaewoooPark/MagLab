"""Per-step cost and resource tracking — `maglab cost` backend (§5.14).

Measures LLM calls, tool calls, and simulation jobs as **steps**:
- LLM call: input tokens, output tokens, USD cost, wall-time (seconds)
- Tool call: wall-time (seconds)
- Simulation job: wall-time + core-hours (populated from P1 onward)

Aggregates by session, run (Ralph loop unit), and total (cumulative).
Emits a warning signal at 80% of the budget limit and a block signal when exceeded.

No other module dependencies (imports only maglab.config).
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import platformdirs

from maglab.config import load_config
from maglab.core.storage import connect_writable_sqlite

_APP = "maglab"


# ---------------------------------------------------------------------------
# Step kinds
# ---------------------------------------------------------------------------


class StepKind(StrEnum):
    """Step kind — LLM call / tool call / simulation job."""

    LLM = "llm"
    TOOL = "tool"
    SIM = "sim"


# ---------------------------------------------------------------------------
# Step record
# ---------------------------------------------------------------------------


@dataclass
class Step:
    """A single step measurement record."""

    step_id: str
    """Unique step identifier (UUID4)."""
    session_id: str
    """Session ID this step belongs to."""
    run_id: str | None
    """Ralph run ID this step belongs to (None if outside a run)."""
    kind: StepKind
    """Step kind."""
    label: str
    """Human-readable label (e.g. model name, tool name)."""
    input_tokens: int = 0
    """LLM input tokens (LLM steps only)."""
    output_tokens: int = 0
    """LLM output tokens (LLM steps only)."""
    usd_cost: float = 0.0
    """USD cost (LLM steps only)."""
    wall_time: float = 0.0
    """Wall-clock time in seconds."""
    core_hours: float = 0.0
    """Core-hours (simulation jobs only; populated from P1 onward)."""
    ts: float = field(default_factory=time.time)
    """Record timestamp (Unix epoch)."""
    extra: dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""


# ---------------------------------------------------------------------------
# Budget events
# ---------------------------------------------------------------------------


class BudgetEvent(StrEnum):
    """Budget gate event type."""

    WARN = "warn"
    """Reached 80% of the limit — warning."""
    BLOCK = "block"
    """Exceeded the limit — block signal."""


@dataclass
class BudgetSignal:
    """Budget gate signal."""

    event: BudgetEvent
    """Event type."""
    current_usd: float
    """Current cumulative USD."""
    limit_usd: float
    """Configured limit USD."""
    message: str
    """Human-readable message."""


# ---------------------------------------------------------------------------
# Cumulative summary
# ---------------------------------------------------------------------------


@dataclass
class BudgetSummary:
    """Budget aggregation summary."""

    total_steps: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    sim_jobs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd_cost: float = 0.0
    wall_time: float = 0.0
    core_hours: float = 0.0


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _default_db_path() -> Path:
    """Default SQLite path (XDG data dir)."""
    data_dir = Path(platformdirs.user_data_dir(_APP))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "budget.db"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steps (
            step_id      TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            run_id       TEXT,
            kind         TEXT NOT NULL,
            label        TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            usd_cost     REAL NOT NULL DEFAULT 0.0,
            wall_time    REAL NOT NULL DEFAULT 0.0,
            core_hours   REAL NOT NULL DEFAULT 0.0,
            ts           REAL NOT NULL,
            extra        TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# BudgetTracker
# ---------------------------------------------------------------------------


class BudgetTracker:
    """Per-session and per-run cost and resource tracker.

    Parameters
    ----------
    session_id:
        Session identifier (auto-generated UUID4 if None).
    db_path:
        SQLite file path (None → default XDG path).
    budget_listeners:
        Callbacks to invoke when a budget event fires.
    """

    def __init__(
        self,
        session_id: str | None = None,
        db_path: Path | None = None,
        budget_listeners: list[Callable[[BudgetSignal], None]] | None = None,
    ) -> None:
        cfg = load_config()
        self._max_usd = cfg.budget.max_usd_per_session
        self._session_id = session_id or str(uuid.uuid4())
        self._listeners = budget_listeners or []
        primary_path = db_path or _default_db_path()
        self._conn, self._db_path = connect_writable_sqlite(
            primary_path,
            fallback_filename="budget.db",
            ensure_schema=_ensure_schema,
            allow_fallback=db_path is None,
        )
        # In-memory accumulator for fast reads without DB I/O
        self._session_steps: list[Step] = []

    # ------------------------------------------------------------------
    # Step recording API
    # ------------------------------------------------------------------

    def record_llm(
        self,
        *,
        label: str,
        input_tokens: int,
        output_tokens: int,
        usd_cost: float,
        wall_time: float,
        run_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Step:
        """Record an LLM call step."""
        step = Step(
            step_id=str(uuid.uuid4()),
            session_id=self._session_id,
            run_id=run_id,
            kind=StepKind.LLM,
            label=label,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd_cost=usd_cost,
            wall_time=wall_time,
            extra=extra or {},
        )
        self._persist(step)
        self._session_steps.append(step)
        self._check_budget()
        return step

    def record_tool(
        self,
        *,
        label: str,
        wall_time: float,
        run_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Step:
        """Record a tool call step."""
        step = Step(
            step_id=str(uuid.uuid4()),
            session_id=self._session_id,
            run_id=run_id,
            kind=StepKind.TOOL,
            label=label,
            wall_time=wall_time,
            extra=extra or {},
        )
        self._persist(step)
        self._session_steps.append(step)
        return step

    def record_sim(
        self,
        *,
        label: str,
        wall_time: float,
        core_hours: float = 0.0,
        run_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Step:
        """Record a simulation job step."""
        step = Step(
            step_id=str(uuid.uuid4()),
            session_id=self._session_id,
            run_id=run_id,
            kind=StepKind.SIM,
            label=label,
            wall_time=wall_time,
            core_hours=core_hours,
            extra=extra or {},
        )
        self._persist(step)
        self._session_steps.append(step)
        return step

    # ------------------------------------------------------------------
    # Aggregation queries
    # ------------------------------------------------------------------

    def session_summary(self) -> BudgetSummary:
        """Return the aggregation summary for the current session."""
        return self._summarize(self._session_steps)

    def run_summary(self, run_id: str) -> BudgetSummary:
        """Return the aggregation summary for a specific run (DB query)."""
        cur = self._conn.execute(
            """
            SELECT kind, input_tokens, output_tokens, usd_cost, wall_time, core_hours
            FROM steps WHERE run_id = ?
            """,
            (run_id,),
        )
        steps = [
            Step(
                step_id="",
                session_id="",
                run_id=run_id,
                kind=StepKind(row[0]),
                label="",
                input_tokens=row[1],
                output_tokens=row[2],
                usd_cost=row[3],
                wall_time=row[4],
                core_hours=row[5],
            )
            for row in cur.fetchall()
        ]
        return self._summarize(steps)

    def total_summary(self) -> BudgetSummary:
        """Return the total cumulative aggregation summary (full DB scan)."""
        cur = self._conn.execute(
            """
            SELECT kind, input_tokens, output_tokens, usd_cost, wall_time, core_hours
            FROM steps
            """
        )
        steps = [
            Step(
                step_id="",
                session_id="",
                run_id=None,
                kind=StepKind(row[0]),
                label="",
                input_tokens=row[1],
                output_tokens=row[2],
                usd_cost=row[3],
                wall_time=row[4],
                core_hours=row[5],
            )
            for row in cur.fetchall()
        ]
        return self._summarize(steps)

    # ------------------------------------------------------------------
    # Budget gate
    # ------------------------------------------------------------------

    def _check_budget(self) -> None:
        """Check budget limit — emit WARN at 80%, BLOCK when exceeded."""
        total_usd = sum(s.usd_cost for s in self._session_steps)
        ratio = total_usd / self._max_usd if self._max_usd > 0 else 0.0
        if ratio >= 1.0:
            sig = BudgetSignal(
                event=BudgetEvent.BLOCK,
                current_usd=total_usd,
                limit_usd=self._max_usd,
                message=(
                    f"Budget exceeded: ${total_usd:.4f} / ${self._max_usd:.2f} "
                    f"({ratio * 100:.1f}%) — blocking additional LLM calls."
                ),
            )
            for cb in self._listeners:
                cb(sig)
        elif ratio >= 0.8:
            sig = BudgetSignal(
                event=BudgetEvent.WARN,
                current_usd=total_usd,
                limit_usd=self._max_usd,
                message=(
                    f"Budget warning: ${total_usd:.4f} / ${self._max_usd:.2f} "
                    f"({ratio * 100:.1f}%) — reached 80% of the limit."
                ),
            )
            for cb in self._listeners:
                cb(sig)

    def is_over_budget(self) -> bool:
        """Return True if the session USD total has exceeded the limit."""
        total_usd = sum(s.usd_cost for s in self._session_steps)
        return self._max_usd > 0 and total_usd >= self._max_usd

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _persist(self, step: Step) -> None:
        import json

        self._conn.execute(
            """
            INSERT INTO steps
            (step_id, session_id, run_id, kind, label,
             input_tokens, output_tokens, usd_cost, wall_time, core_hours, ts, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step.step_id,
                step.session_id,
                step.run_id,
                step.kind.value,
                step.label,
                step.input_tokens,
                step.output_tokens,
                step.usd_cost,
                step.wall_time,
                step.core_hours,
                step.ts,
                json.dumps(step.extra),
            ),
        )
        self._conn.commit()

    @staticmethod
    def _summarize(steps: list[Step]) -> BudgetSummary:
        s = BudgetSummary()
        for step in steps:
            s.total_steps += 1
            s.wall_time += step.wall_time
            s.usd_cost += step.usd_cost
            s.core_hours += step.core_hours
            if step.kind == StepKind.LLM:
                s.llm_calls += 1
                s.input_tokens += step.input_tokens
                s.output_tokens += step.output_tokens
            elif step.kind == StepKind.TOOL:
                s.tool_calls += 1
            elif step.kind == StepKind.SIM:
                s.sim_jobs += 1
        return s

    def close(self) -> None:
        """Close the DB connection."""
        self._conn.close()

    @property
    def session_id(self) -> str:
        return self._session_id
