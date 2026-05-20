"""ralph.py unit tests — LLM mock, deterministic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from maglab.core.ralph import (
    CircuitBreakerState,
    RalphEngine,
    RalphMode,
    RalphState,
    StopReason,
    clear_state,
    load_state,
    parse_done_signal,
    save_state,
)

# ---------------------------------------------------------------------------
# Done signal parsing
# ---------------------------------------------------------------------------


class TestParseDoneSignal:
    def test_exact_match(self) -> None:
        assert parse_done_signal("<promise>DONE</promise>")

    def test_case_insensitive(self) -> None:
        assert parse_done_signal("<promise>done</promise>")
        assert parse_done_signal("<PROMISE>DONE</PROMISE>")

    def test_with_surrounding_text(self) -> None:
        text = "Task completed. <promise>DONE</promise> Thank you."
        assert parse_done_signal(text)

    def test_whitespace_in_tag(self) -> None:
        assert parse_done_signal("<promise> DONE </promise>")

    def test_no_signal(self) -> None:
        assert not parse_done_signal("Still in progress.")
        assert not parse_done_signal("")
        assert not parse_done_signal("<promise>IN_PROGRESS</promise>")

    def test_partial_tag(self) -> None:
        assert not parse_done_signal("<promise>DONE")
        assert not parse_done_signal("DONE</promise>")


# ---------------------------------------------------------------------------
# CircuitBreakerState
# ---------------------------------------------------------------------------


class TestCircuitBreakerState:
    def test_initial_state(self) -> None:
        cb = CircuitBreakerState()
        assert cb.no_progress_count == 0
        assert cb.error_counts == {}
        assert cb.last_output_hash == ""

    def test_no_stop_on_first_call(self) -> None:
        cb = CircuitBreakerState()
        reason = cb.record_output("First output", score=0.5)
        assert reason is None

    def test_output_similarity_stop(self) -> None:
        """Repeated identical output → OUTPUT_SIMILARITY."""
        cb = CircuitBreakerState()
        cb.record_output("Same output", score=0.5)
        reason = cb.record_output("Same output", score=0.5)
        assert reason == StopReason.OUTPUT_SIMILARITY

    def test_different_outputs_no_stop(self) -> None:
        cb = CircuitBreakerState()
        cb.record_output("Output A", score=0.5)
        reason = cb.record_output("Output B", score=0.5)
        assert reason is None

    def test_no_progress_stop(self) -> None:
        """No change in score for 3 rounds → NO_PROGRESS."""
        cb = CircuitBreakerState(no_progress_limit=3, no_progress_threshold=0.01)
        # 3 consecutive no-progress
        cb.record_output("a1", score=0.5)
        cb.record_output("a2", score=0.505)  # delta=0.005 < 0.01
        cb.record_output("a3", score=0.508)  # delta=0.003 < 0.01
        reason = cb.record_output("a4", score=0.510)  # delta=0.002 < 0.01, count=3
        assert reason == StopReason.NO_PROGRESS

    def test_progress_resets_counter(self) -> None:
        """No-progress counter is reset when there is progress."""
        cb = CircuitBreakerState(no_progress_limit=3, no_progress_threshold=0.01)
        cb.record_output("a1", score=0.5)
        cb.record_output("a2", score=0.505)  # no progress 1
        cb.record_output("a3", score=0.9)  # progress → reset
        reason = cb.record_output("a4", score=0.905)  # no progress 1 (restarted)
        assert reason is None
        assert cb.no_progress_count == 1

    def test_repeated_error_stop(self) -> None:
        """Same error 5 times → REPEATED_ERROR."""
        cb = CircuitBreakerState(error_limit=5)
        for _ in range(4):
            reason = cb.record_error("TimeoutError")
            assert reason is None
        reason = cb.record_error("TimeoutError")
        assert reason == StopReason.REPEATED_ERROR

    def test_different_errors_no_stop(self) -> None:
        cb = CircuitBreakerState(error_limit=5)
        for err in ["Err1", "Err2", "Err3", "Err4", "Err5"]:
            reason = cb.record_error(err)
            assert reason is None

    def test_reset_no_progress(self) -> None:
        cb = CircuitBreakerState()
        cb.no_progress_count = 2
        cb.reset_no_progress()
        assert cb.no_progress_count == 0

    # ------------------------------------------------------------------
    # REGRESSION — Finding 5: off-by-one on first iteration with score=0.0
    # ------------------------------------------------------------------

    def test_first_iteration_zero_score_does_not_increment_no_progress(self) -> None:
        """First call with score=0.0 must NOT increment no_progress_count.

        Before the fix, last_score defaulted to 0.0.  A first iteration with
        score=0.0 produced delta=0.0 < threshold, immediately incrementing
        no_progress_count to 1.  This could cause premature circuit-breaker
        trips (e.g. Loop D starts with score 0.0 for the first fit attempt).
        """
        cb = CircuitBreakerState(no_progress_limit=3, no_progress_threshold=0.01)
        reason = cb.record_output("first output", score=0.0)
        assert reason is None, "First iteration must not stop the loop"
        assert cb.no_progress_count == 0, (
            f"no_progress_count must be 0 after the first iteration with score=0.0, "
            f"got {cb.no_progress_count}"
        )

    def test_last_score_is_none_before_first_call(self) -> None:
        """last_score must be None before any call to record_output."""
        cb = CircuitBreakerState()
        assert cb.last_score is None

    def test_first_zero_score_then_progress(self) -> None:
        """Loop starting at 0.0, then making genuine progress, must not be killed prematurely."""
        cb = CircuitBreakerState(no_progress_limit=3, no_progress_threshold=0.01)
        cb.record_output("iter1", score=0.0)  # first call — no comparison, count stays 0
        cb.record_output("iter2", score=0.0)  # delta=0.0 < threshold → count=1
        cb.record_output("iter3", score=0.5)  # delta=0.5 >= threshold → progress, count resets to 0
        # iter4: score=0.5 (same as last), delta=0.0 < threshold → count=1
        reason = cb.record_output("iter4", score=0.5)
        assert reason is None, "Loop must still be running after a progress reset"
        assert cb.no_progress_count == 1

    def test_three_genuine_no_progress_rounds_after_first(self) -> None:
        """After the initial call, 3 consecutive no-progress rounds must still stop."""
        cb = CircuitBreakerState(no_progress_limit=3, no_progress_threshold=0.01)
        cb.record_output("iter1", score=0.5)  # first — no comparison, count stays 0
        cb.record_output("iter2", score=0.505)  # delta=0.005 < 0.01 → count=1
        cb.record_output("iter3", score=0.508)  # delta=0.003 → count=2
        reason = cb.record_output("iter4", score=0.510)  # delta=0.002 → count=3 → STOP
        assert reason == StopReason.NO_PROGRESS


# ---------------------------------------------------------------------------
# RalphState serialization / deserialization
# ---------------------------------------------------------------------------


class TestRalphStateSerializer:
    def test_to_markdown_contains_fields(self) -> None:
        state = RalphState(goal="Test goal", loop_type="B")
        md = state.to_markdown()
        assert "run_id" in md
        assert "active" in md
        assert "iteration" in md
        assert "max_iterations" in md
        assert "Test goal" in md
        assert "loop_type" in md

    def test_from_markdown_roundtrip(self) -> None:
        original = RalphState(
            mode=RalphMode.DETACHED,
            active=True,
            iteration=5,
            max_iterations=20,
            goal="Research goal",
            loop_type="A",
        )
        md = original.to_markdown()
        restored = RalphState.from_markdown(md)
        assert restored.mode == RalphMode.DETACHED
        assert restored.active is True
        assert restored.iteration == 5
        assert restored.max_iterations == 20
        assert restored.goal == "Research goal"
        assert restored.loop_type == "A"

    def test_from_markdown_partial_content(self) -> None:
        """Restore without error even when only some fields are present."""
        md = "# ralph.local.md\n\n- **active**: False\n- **iteration**: 3"
        state = RalphState.from_markdown(md)
        assert state.active is False
        assert state.iteration == 3

    def test_from_markdown_stop_reason(self) -> None:
        state = RalphState(stop_reason="no_progress")
        md = state.to_markdown()
        restored = RalphState.from_markdown(md)
        assert restored.stop_reason == "no_progress"


# ---------------------------------------------------------------------------
# State file I/O
# ---------------------------------------------------------------------------


class TestStateFileIO:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "ralph.local.md"
        state = RalphState(goal="Save test", iteration=7)
        save_state(state, path)
        loaded = load_state(path)
        assert loaded is not None
        assert loaded.goal == "Save test"
        assert loaded.iteration == 7

    def test_load_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.md"
        assert load_state(path) is None

    def test_clear_state(self, tmp_path: Path) -> None:
        path = tmp_path / "ralph.local.md"
        save_state(RalphState(), path)
        assert path.is_file()
        clear_state(path)
        assert not path.is_file()

    def test_clear_state_nonexistent(self, tmp_path: Path) -> None:
        """Deleting a non-existent file must pass without error."""
        path = tmp_path / "ghost.md"
        clear_state(path)  # must not raise

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "ralph.local.md"
        save_state(RalphState(), path)
        assert path.is_file()


# ---------------------------------------------------------------------------
# RalphEngine
# ---------------------------------------------------------------------------


class TestRalphEngine:
    def test_start_creates_state(self, tmp_path: Path) -> None:
        path = tmp_path / "ralph.local.md"
        engine = RalphEngine(
            goal="Test goal",
            max_iterations=10,
            state_path=path,
        )
        state = engine.start()
        assert state.active is True
        assert state.iteration == 0
        assert state.max_iterations == 10
        assert state.goal == "Test goal"
        assert path.is_file()

    def test_max_iterations_capped(self, tmp_path: Path) -> None:
        """max_iterations is capped at the overnight upper bound (50)."""
        engine = RalphEngine(max_iterations=100, state_path=tmp_path / "s.md")
        state = engine.start()
        assert state.max_iterations == 50

    def test_resume_existing_state(self, tmp_path: Path) -> None:
        path = tmp_path / "ralph.local.md"
        # save an existing state
        existing = RalphState(iteration=5, goal="Resume test", active=True)
        save_state(existing, path)

        engine = RalphEngine(state_path=path)
        resumed = engine.resume()
        assert resumed is not None
        assert resumed.iteration == 5
        assert resumed.goal == "Resume test"

    def test_resume_no_file(self, tmp_path: Path, caplog) -> None:
        path = tmp_path / "missing.md"
        engine = RalphEngine(state_path=path)
        import logging

        with caplog.at_level(logging.WARNING):
            result = engine.resume()
        assert result is None

    def test_step_increments_iteration(self, tmp_path: Path) -> None:
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=10, state_path=path)
        engine.start()
        engine.step("output1", score=0.5)
        assert engine.state.iteration == 1
        engine.step("output2", score=0.6)
        assert engine.state.iteration == 2

    def test_step_done_signal_stops(self, tmp_path: Path) -> None:
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=10, state_path=path)
        engine.start()
        reason = engine.step("<promise>DONE</promise>", score=1.0)
        assert reason == StopReason.DONE_SIGNAL
        assert engine.state.active is False
        assert engine.state.completion_promise is True

    def test_step_max_iterations_stops(self, tmp_path: Path) -> None:
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=3, state_path=path)
        engine.start()
        engine.step("output1", score=0.5)
        engine.step("output2", score=0.6)
        reason = engine.step("output3", score=0.7)
        assert reason == StopReason.MAX_ITERATIONS

    def test_step_no_progress_stops(self, tmp_path: Path) -> None:
        """3 no-progress rounds → circuit breaker."""
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=20, state_path=path)
        engine.start()
        # outputs with almost no score change
        engine.step("outputA", score=0.5)
        engine.step("outputB", score=0.504)  # delta < 0.01
        engine.step("outputC", score=0.507)  # delta < 0.01
        reason = engine.step("outputD", score=0.509)  # delta < 0.01, count=3
        assert reason == StopReason.NO_PROGRESS

    def test_step_repeated_error_stops(self, tmp_path: Path) -> None:
        """Same error 5 times → circuit breaker."""
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=20, state_path=path)
        engine.start()
        for i in range(4):
            reason = engine.step(f"output{i}", score=0.5, error_key="ConnectionError")
            assert reason is None
        reason = engine.step("output5", score=0.5, error_key="ConnectionError")
        assert reason == StopReason.REPEATED_ERROR

    def test_step_budget_exceeded_stops(self, tmp_path: Path) -> None:
        """Budget exceeded → BUDGET_EXCEEDED."""
        budget = MagicMock()
        budget.is_over_budget.return_value = True
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=10, budget_tracker=budget, state_path=path)
        engine.start()
        reason = engine.step("output1", score=0.5)
        assert reason == StopReason.BUDGET_EXCEEDED

    def test_step_without_start_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "s.md"
        engine = RalphEngine(state_path=path)
        with pytest.raises(RuntimeError, match="start()"):
            engine.step("output", score=0.5)

    def test_stop_explicit(self, tmp_path: Path) -> None:
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=10, state_path=path)
        engine.start()
        state = engine.stop(StopReason.EXTERNAL)
        assert state.active is False
        assert state.stop_reason == StopReason.EXTERNAL.value

    def test_is_active(self, tmp_path: Path) -> None:
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=10, state_path=path)
        assert not engine.is_active()
        engine.start()
        assert engine.is_active()
        engine.stop()
        assert not engine.is_active()

    # ------------------------------------------------------------------
    # In-session scaffold
    # ------------------------------------------------------------------

    def test_in_session_hook_done(self, tmp_path: Path) -> None:
        engine = RalphEngine(max_iterations=10, state_path=tmp_path / "s.md")
        engine.start()
        # done signal → False (stop)
        result = engine.in_session_hook("<promise>DONE</promise>")
        assert result is False

    def test_in_session_hook_continue(self, tmp_path: Path) -> None:
        engine = RalphEngine(max_iterations=10, state_path=tmp_path / "s.md")
        engine.start()
        result = engine.in_session_hook("In-progress output")
        assert result is True

    def test_in_session_hook_max_iter(self, tmp_path: Path) -> None:
        engine = RalphEngine(max_iterations=1, state_path=tmp_path / "s.md")
        state = engine.start()
        state.iteration = 1  # reached max
        result = engine.in_session_hook("output")
        assert result is False

    # ------------------------------------------------------------------
    # Detached scaffold
    # ------------------------------------------------------------------

    def test_detached_loop_basic(self, tmp_path: Path) -> None:
        """Detached loop basic operation."""
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=3, state_path=path)
        engine.start()

        call_count = [0]

        def fake_agent(state: RalphState) -> str:
            call_count[0] += 1
            return f"Output {call_count[0]}"

        outputs = engine.detached_loop(fake_agent)
        assert len(outputs) > 0

    def test_detached_loop_done_signal(self, tmp_path: Path) -> None:
        """Detached loop stops when done signal is received."""
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=10, state_path=path)
        engine.start()

        def fake_agent(state: RalphState) -> str:
            return "<promise>DONE</promise>"

        outputs = engine.detached_loop(fake_agent)
        assert len(outputs) == 1
        assert engine.state.completion_promise is True

    def test_detached_loop_error_handling(self, tmp_path: Path) -> None:
        """Error counter increases on agent exception; stops at 5."""
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=20, state_path=path)
        engine.start()

        call_count = [0]

        def failing_agent(state: RalphState) -> str:
            call_count[0] += 1
            raise RuntimeError("ConnectionError")

        engine.detached_loop(failing_agent)
        # when only errors occur, outputs is empty and circuit breaker triggers
        assert call_count[0] >= 5

    def test_detached_loop_auto_starts(self, tmp_path: Path) -> None:
        """Calling detached_loop without start() auto-starts."""
        path = tmp_path / "s.md"
        engine = RalphEngine(max_iterations=2, state_path=path)

        def simple_agent(state: RalphState) -> str:
            return "output"

        engine.detached_loop(simple_agent)
        assert engine.state is not None
