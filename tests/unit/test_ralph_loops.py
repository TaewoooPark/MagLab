"""tests/unit/test_ralph_loops.py — Loop B/D/E behaviour, circuit-breaker and resume tests.

Verification items (§19 P4 validation gate):
- Loop B: experiment-code pytest passes → DONE, failure → fix loop, circuit breaker
- Loop D: fitting converges → DONE, physics-boundary violation handling, circuit breaker
- Loop E: critic PASSED → DONE, no vision model configured → skipped, circuit breaker
- Detached loop git_commit=True path (GAP-R3-B)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from maglab.core.ralph import (
    FigureCriticResult,
    FitCheckResult,
    RalphEngine,
    RalphMode,
    StopReason,
    _check_fit_quality,
    _parse_critic_response,
    _parse_pytest_failures,
    run_loop_b,
    run_loop_d,
    run_loop_e,
)

# ---------------------------------------------------------------------------
# Loop B — Experiment-code Ralph
# ---------------------------------------------------------------------------


class TestLoopBBasic:
    """Loop B basic behaviour tests."""

    def test_loop_b_passes_on_first_try(self, tmp_path: Path) -> None:
        """When tests pass on the first attempt, terminates immediately with success=True."""
        state_path = tmp_path / "ralph_b.md"

        # code that passes pytest
        good_code = "def add(a, b):\n    return a + b\n"
        test_code = (
            "from instrument_script import add\ndef test_add():\n    assert add(1, 2) == 3\n"
        )

        result = run_loop_b(
            goal="Implement add function",
            initial_code=good_code,
            test_code=test_code,
            code_improver_fn=lambda code, failures: code,  # no fix needed
            max_iterations=5,
            state_path=state_path,
        )

        assert result.success is True
        assert result.stop_reason == StopReason.DONE_SIGNAL.value

    def test_loop_b_fixes_failing_code(self, tmp_path: Path) -> None:
        """Failing code passes after the improver function is called."""
        state_path = tmp_path / "ralph_b.md"
        call_count = [0]

        def improver(code: str, failures: list[str]) -> str:
            call_count[0] += 1
            # return correct code on second call
            return "def add(a, b):\n    return a + b\n"

        result = run_loop_b(
            goal="Implement add function",
            initial_code="def add(a, b):\n    return a - b\n",  # buggy code
            test_code=(
                "from instrument_script import add\ndef test_add():\n    assert add(1, 2) == 3\n"
            ),
            code_improver_fn=improver,
            max_iterations=5,
            state_path=state_path,
        )

        assert result.success is True
        assert call_count[0] >= 1

    def test_loop_b_circuit_breaker_repeated_error(self, tmp_path: Path) -> None:
        """Circuit breaker fires on repeated identical errors."""
        state_path = tmp_path / "ralph_b.md"
        call_count = [0]

        def always_fail_improver(code: str, failures: list[str]) -> str:
            call_count[0] += 1
            return code  # no fix → same failure repeated

        result = run_loop_b(
            goal="Always failing",
            initial_code="def add(a, b):\n    return a - b\n",
            test_code=(
                "from instrument_script import add\ndef test_add():\n    assert add(1, 2) == 3\n"
            ),
            code_improver_fn=always_fail_improver,
            max_iterations=20,
            state_path=state_path,
        )

        assert result.success is False
        # REPEATED_ERROR or MAX_ITERATIONS
        assert result.stop_reason in [
            StopReason.REPEATED_ERROR.value,
            StopReason.MAX_ITERATIONS.value,
            StopReason.OUTPUT_SIMILARITY.value,
            StopReason.NO_PROGRESS.value,
        ]

    def test_loop_b_max_iterations_stop(self, tmp_path: Path) -> None:
        """Stops when maximum iteration count is reached."""
        state_path = tmp_path / "ralph_b.md"

        # always return different code to avoid OUTPUT_SIMILARITY
        counter = [0]

        def slow_improver(code: str, failures: list[str]) -> str:
            counter[0] += 1
            return f"def add(a, b):\n    # ver {counter[0]}\n    return a - b\n"

        result = run_loop_b(
            goal="Keep failing",
            initial_code="def add(a, b):\n    return a - b\n",
            test_code=(
                "from instrument_script import add\ndef test_add():\n    assert add(1, 2) == 3\n"
            ),
            code_improver_fn=slow_improver,
            max_iterations=3,
            state_path=state_path,
        )

        assert result.success is False
        assert result.iterations <= 3

    def test_loop_b_budget_exceeded(self, tmp_path: Path) -> None:
        """Circuit breaker fires on budget exceeded."""
        budget = MagicMock()
        budget.is_over_budget.return_value = True
        state_path = tmp_path / "ralph_b.md"

        result = run_loop_b(
            goal="Budget exceeded test",
            initial_code="def add(a, b):\n    return a - b\n",
            test_code=(
                "from instrument_script import add\ndef test_add():\n    assert add(1, 2) == 3\n"
            ),
            code_improver_fn=lambda c, f: c,
            max_iterations=5,
            budget_tracker=budget,
            state_path=state_path,
        )

        assert result.success is False
        assert result.stop_reason == StopReason.BUDGET_EXCEEDED.value


class TestParsePytestFailures:
    """Unit tests for _parse_pytest_failures."""

    def test_parse_empty_output(self) -> None:
        result = _parse_pytest_failures("")
        assert isinstance(result, list)

    def test_parse_failure_output(self) -> None:
        output = (
            "FAILED test_script.py::test_add - AssertionError: assert -1 == 3\n"
            "AssertionError: assert -1 == 3\n"
        )
        result = _parse_pytest_failures(output)
        assert len(result) >= 1

    def test_parse_returns_list(self) -> None:
        result = _parse_pytest_failures("some output")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Loop D — Effect fitting Ralph
# ---------------------------------------------------------------------------


class TestLoopDBasic:
    """Loop D basic behaviour tests."""

    def test_loop_d_converges(self, tmp_path: Path) -> None:
        """Fitting converges on the first attempt."""
        state_path = tmp_path / "ralph_d.md"

        def good_fit(**kwargs: Any) -> dict[str, Any]:
            return {"chi2": 0.5, "r2": 0.99, "residuals": [0.1, -0.1, 0.05], "params": {"A": 1.0}}

        def no_adjust(fit_result: dict, check: FitCheckResult) -> dict:
            return {}

        result = run_loop_d(
            goal="AHE fitting",
            fit_fn=good_fit,
            adjust_fn=no_adjust,
            max_iterations=5,
            state_path=state_path,
        )

        assert result.success is True
        assert result.stop_reason == StopReason.DONE_SIGNAL.value
        assert result.fit_check.passed is True

    def test_loop_d_adjusts_and_converges(self, tmp_path: Path) -> None:
        """Converges after adjustment following an initial fitting failure."""
        state_path = tmp_path / "ralph_d.md"
        call_count = [0]

        def fit_fn(**kwargs: Any) -> dict[str, Any]:
            call_count[0] += 1
            if call_count[0] < 3:
                return {
                    "chi2": 50.0,
                    "r2": 0.5,
                    "residuals": [1.0, 1.1, 1.2, 1.3],
                    "params": {"A": 0.1},
                }
            return {"chi2": 0.5, "r2": 0.99, "residuals": [0.1, -0.1], "params": {"A": 1.0}}

        def adjust_fn(fit_result: dict, check: FitCheckResult) -> dict:
            return {}

        result = run_loop_d(
            goal="Fitting convergence",
            fit_fn=fit_fn,
            adjust_fn=adjust_fn,
            max_iterations=10,
            state_path=state_path,
        )

        assert result.success is True
        assert call_count[0] >= 3

    def test_loop_d_circuit_breaker_no_progress(self, tmp_path: Path) -> None:
        """Circuit breaker fires on no progress."""
        state_path = tmp_path / "ralph_d.md"
        call_count = [0]

        def bad_fit(**kwargs: Any) -> dict[str, Any]:
            call_count[0] += 1
            # same bad result repeated → same output hash
            return {
                "chi2": 100.0,
                "r2": 0.3,
                "residuals": [5.0, 5.1, 5.2, 5.3, 5.4],
                "params": {"A": 0.01},
            }

        def adjust_fn(fit_result: dict, check: FitCheckResult) -> dict:
            return {}

        result = run_loop_d(
            goal="No-progress test",
            fit_fn=bad_fit,
            adjust_fn=adjust_fn,
            max_iterations=20,
            chi2_threshold=10.0,
            r2_threshold=0.95,
            state_path=state_path,
        )

        assert result.success is False

    def test_loop_d_budget_exceeded(self, tmp_path: Path) -> None:
        """Circuit breaker fires on budget exceeded."""
        budget = MagicMock()
        budget.is_over_budget.return_value = True
        state_path = tmp_path / "ralph_d.md"

        def fit_fn(**kwargs: Any) -> dict[str, Any]:
            return {"chi2": 50.0, "r2": 0.5, "residuals": [], "params": {}}

        result = run_loop_d(
            goal="Budget exceeded",
            fit_fn=fit_fn,
            adjust_fn=lambda r, c: {},
            max_iterations=5,
            budget_tracker=budget,
            state_path=state_path,
        )

        assert result.stop_reason == StopReason.BUDGET_EXCEEDED.value


class TestFitCheckResult:
    """Unit tests for _check_fit_quality."""

    def test_good_fit_passes(self) -> None:
        """A good fitting result passes."""
        result = _check_fit_quality(
            {"chi2": 1.0, "r2": 0.99, "residuals": [0.1, -0.1, 0.05, -0.08], "params": {}}
        )
        assert result.passed is True
        assert result.chi2 == 1.0
        assert result.r2 == 0.99

    def test_high_chi2_fails(self) -> None:
        """Fails when chi2 exceeds threshold."""
        result = _check_fit_quality(
            {"chi2": 100.0, "r2": 0.99, "residuals": [], "params": {}},
            chi2_threshold=10.0,
        )
        assert result.passed is False
        assert result.chi2 == 100.0

    def test_low_r2_fails(self) -> None:
        """Fails when R2 is below threshold."""
        result = _check_fit_quality(
            {"chi2": 1.0, "r2": 0.5, "residuals": [], "params": {}},
            r2_threshold=0.95,
        )
        assert result.passed is False

    def test_missing_fields_handled(self) -> None:
        """Missing fields are handled with default values."""
        result = _check_fit_quality({})
        assert isinstance(result, FitCheckResult)

    def test_systematic_residuals_detected(self) -> None:
        """Systematic residual pattern is detected."""
        result = _check_fit_quality(
            {
                "chi2": 1.0,
                "r2": 0.99,
                "residuals": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
                "params": {},
            }
        )
        # all positive → no sign changes → suspected non-random
        assert result.residuals_random is False


# ---------------------------------------------------------------------------
# Loop E — Figure refinement Ralph
# ---------------------------------------------------------------------------


class TestLoopEBasic:
    """Loop E basic behaviour tests."""

    def test_loop_e_no_vision_model_skips(self, tmp_path: Path) -> None:
        """When no vision model is configured, critic is skipped → success=True."""
        state_path = tmp_path / "ralph_e.md"
        svg_path = tmp_path / "test.svg"
        svg_path.write_text("<svg/>", encoding="utf-8")

        result = run_loop_e(
            goal="Figure refinement",
            render_fn=lambda: svg_path,
            apply_fixes_fn=lambda critic: None,
            vision_critic_fn=None,  # no vision model
            max_iterations=3,
            state_path=state_path,
        )

        assert result.success is True
        assert "No vision model configured" in result.final_critic.raw_response

    def test_loop_e_critic_passes_immediately(self, tmp_path: Path) -> None:
        """When critic returns PASSED on the first call → success=True."""
        state_path = tmp_path / "ralph_e.md"
        svg_path = tmp_path / "test.svg"
        svg_path.write_text("<svg/>", encoding="utf-8")

        def mock_critic(image_path: Path, prompt: str) -> str:
            return "All items pass. PASSED"

        result = run_loop_e(
            goal="Figure refinement",
            render_fn=lambda: svg_path,
            apply_fixes_fn=lambda c: None,
            vision_critic_fn=mock_critic,
            max_iterations=5,
            state_path=state_path,
        )

        assert result.success is True
        assert result.stop_reason == StopReason.DONE_SIGNAL.value
        assert result.final_critic.passed is True

    def test_loop_e_applies_fixes_and_passes(self, tmp_path: Path) -> None:
        """Critic fails, fixes applied, passes on next attempt."""
        state_path = tmp_path / "ralph_e.md"
        svg_path = tmp_path / "test.svg"
        svg_path.write_text("<svg/>", encoding="utf-8")

        call_count = [0]
        fix_count = [0]

        def mock_critic(image_path: Path, prompt: str) -> str:
            call_count[0] += 1
            if call_count[0] == 1:
                return "fail: axis label missing. fix required."
            return "All items pass. PASSED"

        def apply_fixes(critic: FigureCriticResult) -> None:
            fix_count[0] += 1

        result = run_loop_e(
            goal="Figure refinement",
            render_fn=lambda: svg_path,
            apply_fixes_fn=apply_fixes,
            vision_critic_fn=mock_critic,
            max_iterations=5,
            state_path=state_path,
        )

        assert result.success is True
        assert fix_count[0] >= 1
        assert call_count[0] >= 2

    def test_loop_e_circuit_breaker_max_iter(self, tmp_path: Path) -> None:
        """Stops when maximum iteration count is reached."""
        state_path = tmp_path / "ralph_e.md"
        svg_path = tmp_path / "test.svg"
        svg_path.write_text("<svg/>", encoding="utf-8")

        call_count = [0]

        def always_fail_critic(image_path: Path, prompt: str) -> str:
            call_count[0] += 1
            return f"fail: multiple issues found (iteration {call_count[0]})"

        result = run_loop_e(
            goal="Always failing",
            render_fn=lambda: svg_path,
            apply_fixes_fn=lambda c: None,
            vision_critic_fn=always_fail_critic,
            max_iterations=3,
            state_path=state_path,
        )

        assert result.success is False
        assert result.iterations <= 3

    def test_loop_e_render_error_handled(self, tmp_path: Path) -> None:
        """Circuit breaker fires on render_fn error."""
        state_path = tmp_path / "ralph_e.md"
        call_count = [0]

        def failing_render() -> Path:
            call_count[0] += 1
            raise RuntimeError("Render error")

        result = run_loop_e(
            goal="Render error",
            render_fn=failing_render,
            apply_fixes_fn=lambda c: None,
            vision_critic_fn=lambda p, pr: "PASSED",
            max_iterations=10,
            state_path=state_path,
        )

        assert result.success is False

    def test_loop_e_budget_exceeded(self, tmp_path: Path) -> None:
        """Circuit breaker fires on budget exceeded."""
        budget = MagicMock()
        budget.is_over_budget.return_value = True
        state_path = tmp_path / "ralph_e.md"
        svg_path = tmp_path / "test.svg"
        svg_path.write_text("<svg/>", encoding="utf-8")

        result = run_loop_e(
            goal="Budget exceeded",
            render_fn=lambda: svg_path,
            apply_fixes_fn=lambda c: None,
            vision_critic_fn=lambda p, pr: "fail: issues found",
            max_iterations=5,
            budget_tracker=budget,
            state_path=state_path,
        )

        assert result.stop_reason == StopReason.BUDGET_EXCEEDED.value


class TestParseCriticResponse:
    """Unit tests for _parse_critic_response."""

    def test_passed_response(self) -> None:
        result = _parse_critic_response("All items checked. PASSED")
        assert result.passed is True

    def test_failed_response(self) -> None:
        result = _parse_critic_response("fail: axis label missing. fix required.")
        assert result.passed is False
        assert len(result.issues) >= 1

    def test_mixed_response(self) -> None:
        result = _parse_critic_response(
            "fail: colorblind-safe palette not followed.\nsuggestion: use Okabe-Ito palette.\nPASSED"
        )
        assert result.passed is True

    def test_empty_response(self) -> None:
        result = _parse_critic_response("")
        assert isinstance(result, FigureCriticResult)


# ---------------------------------------------------------------------------
# REGRESSION — Finding 2 (R2): "PASSED" substring must NOT trigger a pass when
# the word appears mid-response (e.g. "not passed", "items not passed: …").
# Before the fix: `"PASSED" in response.upper()` caused Loop E to exit early
# whenever any sub-item description contained the word.
# ---------------------------------------------------------------------------


class TestParseCriticResponseRegression:
    """Regression tests for Finding 2 — PASSED substring false-positive fix."""

    def test_not_passed_substring_does_not_pass(self) -> None:
        """'not passed' in response must NOT set passed=True."""
        result = _parse_critic_response("Panel labels (a/b/c): not passed. Font size: not passed.")
        assert result.passed is False, (
            "Response with 'not passed' items should not be detected as PASSED."
        )

    def test_items_not_passed_does_not_pass(self) -> None:
        """'Items not passed: font size' must NOT set passed=True."""
        result = _parse_critic_response("Items not passed: font size, axis labels.")
        assert result.passed is False

    def test_axis_label_passed_color_failed_does_not_pass(self) -> None:
        """Partial pass ('Axis labels passed, colorblind palette failed') is not a full pass."""
        result = _parse_critic_response("Axis labels passed, colorblind palette failed.")
        assert result.passed is False

    def test_did_not_passed_does_not_pass(self) -> None:
        """'did NOT PASSED the review' must NOT set passed=True."""
        result = _parse_critic_response("This figure did NOT PASSED the review.")
        assert result.passed is False

    def test_passed_on_final_line_is_genuine_pass(self) -> None:
        """Standalone 'PASSED' on the last non-empty line is the correct success signal."""
        result = _parse_critic_response(
            "All checklist items reviewed.\nFont: OK. Labels: OK.\nPASSED"
        )
        assert result.passed is True

    def test_passed_only_response_passes(self) -> None:
        """A response consisting solely of 'PASSED' is a valid pass."""
        result = _parse_critic_response("PASSED")
        assert result.passed is True

    def test_failed_on_final_line_does_not_pass(self) -> None:
        """Final line 'FAILED' must not be detected as passed."""
        result = _parse_critic_response("Some items passed. Final verdict:\nFAILED")
        assert result.passed is False


# ---------------------------------------------------------------------------
# Resume tests
# ---------------------------------------------------------------------------


class TestLoopResume:
    """Loop resume tests via state file."""

    def test_ralph_engine_resume_loop_b_state(self, tmp_path: Path) -> None:
        """Ralph engine resumes Loop B from a state file."""
        from maglab.core.ralph import RalphState, save_state

        state_path = tmp_path / "ralph_b.md"
        # artificially create a state file with iteration=3
        existing_state = RalphState(
            mode=RalphMode.IN_SESSION,
            active=True,
            iteration=3,
            max_iterations=10,
            goal="Resume test",
            loop_type="B",
        )
        save_state(existing_state, state_path)

        engine = RalphEngine(state_path=state_path)
        resumed = engine.resume()

        assert resumed is not None
        assert resumed.iteration == 3
        assert resumed.loop_type == "B"
        assert resumed.active is True

    def test_ralph_engine_detached_mode_state_persistence(self, tmp_path: Path) -> None:
        """State file is updated after every iteration in detached mode."""
        from maglab.core.ralph import RalphState, load_state

        state_path = tmp_path / "ralph_detached.md"
        engine = RalphEngine(
            mode=RalphMode.DETACHED,
            max_iterations=3,
            goal="Detached resume",
            loop_type="B",
            state_path=state_path,
        )
        engine.start()

        call_count = [0]

        def agent_fn(state: RalphState) -> str:
            call_count[0] += 1
            return f"iteration {call_count[0]} output"

        engine.detached_loop(agent_fn)

        # state file exists and reflects the final state
        loaded = load_state(state_path)
        assert loaded is not None
        assert loaded.iteration >= 1


# ---------------------------------------------------------------------------
# GAP-R3-B — detached_loop(git_commit=True) path
# ---------------------------------------------------------------------------


class TestDetachedLoopGitCommit:
    """Verify detached_loop git_commit=True calls git add -A and git commit in an isolated repo."""

    def test_git_commit_calls_subprocess_run(self, tmp_path: Path, monkeypatch: Any) -> None:
        """detached_loop(git_commit=True) invokes git add -A and git commit -m 'ralph: ...'."""
        # SAFETY: run git in an isolated tmp directory — never in the real repo.
        monkeypatch.chdir(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        state_path = tmp_path / "ralph_git.md"
        engine = RalphEngine(
            mode=RalphMode.DETACHED,
            max_iterations=1,
            goal="Git commit test",
            loop_type="B",
            state_path=state_path,
        )
        engine.start()

        # Write a file so git commit has something to stage
        (tmp_path / "dummy.txt").write_text("iteration output", encoding="utf-8")

        captured_calls: list[list[str]] = []
        real_run = subprocess.run

        def mock_run(cmd: list[str], **kwargs: Any) -> Any:
            captured_calls.append(list(cmd))
            return real_run(cmd, **kwargs)

        with patch("maglab.core.ralph.subprocess.run", side_effect=mock_run):
            engine.detached_loop(lambda state: "output", git_commit=True)

        git_add_calls = [c for c in captured_calls if "add" in c]
        git_commit_calls = [c for c in captured_calls if "commit" in c]
        assert len(git_add_calls) >= 1, "git add -A was not called"
        assert len(git_commit_calls) >= 1, "git commit was not called"
        # The commit message must start with "ralph:"
        commit_msg = next(
            (c[c.index("-m") + 1] for c in captured_calls if "commit" in c and "-m" in c),
            "",
        )
        assert commit_msg.startswith("ralph:"), (
            f"Commit message missing 'ralph:' prefix: {commit_msg!r}"
        )

    def test_git_commit_in_non_git_dir_does_not_raise(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """detached_loop(git_commit=True) is a no-op (no raise) in a non-git directory."""
        # Use a temp dir that is NOT a git repo
        non_git_dir = tmp_path / "not_a_repo"
        non_git_dir.mkdir()
        monkeypatch.chdir(non_git_dir)

        state_path = non_git_dir / "ralph_nongit.md"
        engine = RalphEngine(
            mode=RalphMode.DETACHED,
            max_iterations=1,
            goal="Non-git directory test",
            loop_type="B",
            state_path=state_path,
        )
        engine.start()

        # Should complete without raising, even though git will fail
        outputs = engine.detached_loop(lambda state: "output", git_commit=True)
        # Loop ran (1 iteration) and did not raise
        assert isinstance(outputs, list)


# ---------------------------------------------------------------------------
# REGRESSION — Finding 2 (R4): detached_loop must NOT stop early due to the
# NO_PROGRESS circuit breaker when no score_fn is provided.
#
# Before the fix: detached_loop called self.step(output, score=0.5) with a
# hardcoded constant score.  With a constant score, CircuitBreakerState fired
# NO_PROGRESS at iteration 4 (3 consecutive zero-delta increments), regardless
# of max_iterations.
#
# After the fix: when score_fn is absent, reset_no_progress() is called before
# each record_output() call so that the NO_PROGRESS breaker is suppressed.
# The loop then runs to max_iterations (or until OUTPUT_SIMILARITY / DONE /
# BUDGET / REPEATED_ERROR fires).
# ---------------------------------------------------------------------------


class TestDetachedLoopNoProgressRegression:
    """R4/F2 — detached_loop must run to max_iterations when output varies."""

    def test_detached_loop_runs_all_iterations_with_varying_output(self, tmp_path: Path) -> None:
        """detached_loop with max_iterations=10 and a varying-output agent_fn
        must complete all 10 iterations — not stop at 4 due to NO_PROGRESS.

        This is the core regression: before the fix the loop was hard-terminated
        at iteration 4 because the hardcoded score=0.5 triggered the no-progress
        circuit breaker.
        """
        from maglab.core.ralph import RalphEngine, RalphState

        state_path = tmp_path / "ralph_regression.md"
        engine = RalphEngine(max_iterations=10, state_path=state_path)
        engine.start()

        call_count = [0]

        def varying_agent(state: RalphState) -> str:
            call_count[0] += 1
            # Every call produces a unique output (prevents OUTPUT_SIMILARITY breaker)
            return f"unique output for iteration {call_count[0]}: data={call_count[0] * 3.14}"

        outputs = engine.detached_loop(varying_agent)

        assert len(outputs) == 10, (
            f"Expected 10 outputs (max_iterations=10) but got {len(outputs)}. "
            f"The NO_PROGRESS circuit breaker fired prematurely — "
            f"detached_loop still has the hardcoded score=0.5 bug."
        )

    def test_detached_loop_output_similarity_still_fires(self, tmp_path: Path) -> None:
        """Even without score_fn, the OUTPUT_SIMILARITY breaker must still stop the loop
        when the agent produces identical output on consecutive iterations."""
        from maglab.core.ralph import RalphEngine, RalphState

        state_path = tmp_path / "ralph_similarity.md"
        engine = RalphEngine(max_iterations=20, state_path=state_path)
        engine.start()

        def identical_agent(state: RalphState) -> str:
            return "always the same output"

        outputs = engine.detached_loop(identical_agent)

        # First iteration always recorded; second triggers OUTPUT_SIMILARITY → stops
        assert len(outputs) <= 2, (
            "OUTPUT_SIMILARITY breaker must fire when agent returns identical output."
        )

    def test_detached_loop_with_score_fn_no_progress_still_fires(self, tmp_path: Path) -> None:
        """When score_fn is provided and always returns 0.5, the NO_PROGRESS breaker
        must still fire (backward-compatible: score_fn path is unchanged)."""
        from maglab.core.ralph import RalphEngine, RalphState, StopReason

        state_path = tmp_path / "ralph_score_fn.md"
        engine = RalphEngine(max_iterations=20, state_path=state_path)
        engine.start()

        call_count = [0]

        def varying_agent(state: RalphState) -> str:
            call_count[0] += 1
            return f"output {call_count[0]}"

        # score_fn always returns 0.5 → NO_PROGRESS must fire at iteration 4
        outputs = engine.detached_loop(
            varying_agent,
            score_fn=lambda output: 0.5,
        )

        assert len(outputs) <= 5, (
            "With score_fn returning a constant 0.5, NO_PROGRESS must fire "
            "before the 5th iteration."
        )
        assert engine.state is not None
        assert engine.state.stop_reason == StopReason.NO_PROGRESS.value, (
            f"Expected stop_reason=NO_PROGRESS, got {engine.state.stop_reason!r}."
        )

    def test_detached_loop_with_varying_score_fn_runs_longer(self, tmp_path: Path) -> None:
        """When score_fn returns increasing scores, the loop runs beyond 4 iterations."""
        from maglab.core.ralph import RalphEngine, RalphState

        state_path = tmp_path / "ralph_varying_score.md"
        engine = RalphEngine(max_iterations=10, state_path=state_path)
        engine.start()

        call_count = [0]

        def varying_agent(state: RalphState) -> str:
            call_count[0] += 1
            return f"output {call_count[0]}"

        # score_fn returns genuinely increasing scores → NO_PROGRESS never fires
        outputs = engine.detached_loop(
            varying_agent,
            score_fn=lambda output: min(1.0, call_count[0] * 0.1),
        )

        assert len(outputs) == 10, (
            f"With an increasing score_fn, loop must reach max_iterations=10. "
            f"Got {len(outputs)} outputs."
        )
