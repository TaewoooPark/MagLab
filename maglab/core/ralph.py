"""Ralph loop engine — P0 skeleton + P4 Loop B/D/E implementation (§6).

Two execution modes:
  1. In-session: The harness Stop-hook intercepts termination and re-injects
     the original prompt. State is preserved in ``.maglab/ralph.local.md``.
  2. Detached fresh-context: An external loop spawns the ``maglab`` agent
     as a fresh process each iteration. State is managed via files + git.

Circuit-breaker conditions:
  - 3 consecutive no-progress iterations (score_delta < threshold)
  - Same error 5 times
  - Output similarity > 0.95 (repeated identical output)
  - Cost rate exceeded (budget.is_over_budget())

Completion signal: ``<promise>DONE</promise>``

P4 implementation:
  - Loop B: Implement experiment code → mock instrument pytest → parse failures → fix
  - Loop D: Improve effect fitting → check residuals and physics bounds → refit
  - Loop E: Render figure → vision critic → apply fixes
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import logging
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from maglab.core.atomic import atomic_write_text

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State file path
# ---------------------------------------------------------------------------

_APP = "maglab"
_LOCAL_STATE_PATH = Path(".maglab") / "ralph.local.md"

# ---------------------------------------------------------------------------
# Completion signal parsing
# ---------------------------------------------------------------------------

_DONE_PATTERN = re.compile(r"<promise>\s*DONE\s*</promise>", re.IGNORECASE)


def parse_done_signal(text: str) -> bool:
    """Detect the completion signal ``<promise>DONE</promise>`` in text.

    Parameters
    ----------
    text:
        Agent output text.

    Returns
    -------
    True if the completion signal is present.
    """
    return bool(_DONE_PATTERN.search(text))


# ---------------------------------------------------------------------------
# Circuit-breaker data structures
# ---------------------------------------------------------------------------


class StopReason(StrEnum):
    """Circuit-breaker stop reason."""

    NO_PROGRESS = "no_progress"
    """3 consecutive no-progress iterations (score delta < threshold)."""
    REPEATED_ERROR = "repeated_error"
    """Same error 5 times."""
    OUTPUT_SIMILARITY = "output_similarity"
    """Output similarity > 0.95 (repeated identical output)."""
    BUDGET_EXCEEDED = "budget_exceeded"
    """Cost rate exceeded."""
    DONE_SIGNAL = "done_signal"
    """Completion signal received."""
    MAX_ITERATIONS = "max_iterations"
    """Maximum iteration count reached."""
    EXTERNAL = "external"
    """External stop request."""


@dataclass
class CircuitBreakerState:
    """Circuit-breaker state tracking.

    Attributes
    ----------
    no_progress_count:
        Consecutive no-progress iteration count (threshold: 3).
    error_counts:
        Dict mapping error message to occurrence count (threshold: 5).
    last_output_hash:
        SHA-256 hash of the previous output (for similarity check).
    last_score:
        Score from the previous iteration.
    no_progress_threshold:
        Score delta below which an iteration is considered no-progress.
    no_progress_limit:
        Consecutive no-progress count that triggers a stop.
    error_limit:
        Same-error count that triggers a stop.
    similarity_threshold:
        Output similarity threshold for stop trigger (0–1).
    """

    no_progress_count: int = 0
    error_counts: dict[str, int] = field(default_factory=dict)
    last_output_hash: str = ""
    # Sentinel value: None means no score has been recorded yet.
    # Using float = 0.0 caused an off-by-one: the first call with score=0.0
    # would compute delta=0.0 < threshold and immediately increment no_progress_count,
    # even though no prior iteration had occurred to compare against.
    last_score: float | None = None
    no_progress_threshold: float = 0.01
    no_progress_limit: int = 3
    error_limit: int = 5
    similarity_threshold: float = 0.95

    def record_output(self, output: str, score: float) -> StopReason | None:
        """Record output and check circuit-breaker conditions.

        Parameters
        ----------
        output:
            Agent output text for this iteration.
        score:
            Progress score for this iteration (0–1).

        Returns
        -------
        Stop reason (None means continue).
        """
        # Output similarity check
        output_hash = hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest()
        if self.last_output_hash and output_hash == self.last_output_hash:
            return StopReason.OUTPUT_SIMILARITY
        self.last_output_hash = output_hash

        # No-progress check.
        # Skip on the very first recorded iteration (last_score is None) so
        # that a first-iteration score of 0.0 is not spuriously counted as
        # "no progress compared to the initialisation default".
        if self.last_score is not None:
            delta = abs(score - self.last_score)
            if delta < self.no_progress_threshold:
                self.no_progress_count += 1
                if self.no_progress_count >= self.no_progress_limit:
                    return StopReason.NO_PROGRESS
            else:
                self.no_progress_count = 0
        self.last_score = score

        return None

    def record_error(self, error_key: str) -> StopReason | None:
        """Record an error and check the repeated-error condition.

        Parameters
        ----------
        error_key:
            Error identification string (exception message or type, etc.).

        Returns
        -------
        Stop reason (None means continue).
        """
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        if self.error_counts[error_key] >= self.error_limit:
            return StopReason.REPEATED_ERROR
        return None

    def reset_no_progress(self) -> None:
        """Reset the no-progress counter."""
        self.no_progress_count = 0


# ---------------------------------------------------------------------------
# Ralph loop state
# ---------------------------------------------------------------------------


class RalphMode(StrEnum):
    """Ralph loop execution mode."""

    IN_SESSION = "in-session"
    """In-session: based on the harness internal Stop-hook."""
    DETACHED = "detached"
    """Detached: an external loop spawns a fresh process each iteration."""


@dataclass
class RalphState:
    """Ralph loop execution state — saved to ``.maglab/ralph.local.md``.

    Attributes
    ----------
    run_id:
        Unique Ralph run identifier (UUID4).
    mode:
        Execution mode (in-session / detached).
    active:
        Whether the loop is currently active.
    iteration:
        Current iteration number (0-based).
    max_iterations:
        Maximum iteration count.
    completion_promise:
        Whether the agent has sent a completion promise.
    goal:
        Loop goal string.
    loop_type:
        Loop type (A/B/C/D/E or user-defined).
    created_at:
        Creation timestamp (Unix epoch).
    updated_at:
        Last-updated timestamp.
    stop_reason:
        Stop reason (None if still running).
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mode: RalphMode = RalphMode.IN_SESSION
    active: bool = True
    iteration: int = 0
    max_iterations: int = 20
    completion_promise: bool = False
    goal: str = ""
    loop_type: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    stop_reason: str | None = None

    def to_markdown(self) -> str:
        """Serialize state to Markdown format."""
        lines = [
            "# ralph.local.md — Ralph Loop State",
            "",
            f"- **run_id**: {self.run_id}",
            f"- **mode**: {self.mode.value}",
            f"- **active**: {self.active}",
            f"- **iteration**: {self.iteration}",
            f"- **max_iterations**: {self.max_iterations}",
            f"- **completion_promise**: {self.completion_promise}",
            f"- **goal**: {self.goal}",
            f"- **loop_type**: {self.loop_type}",
            f"- **created_at**: {self.created_at}",
            f"- **updated_at**: {self.updated_at}",
            f"- **stop_reason**: {self.stop_reason or ''}",
        ]
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str) -> RalphState:
        """Restore state from Markdown.

        Fields that fail to parse retain their default values.
        """
        state = cls()

        def _extract(key: str) -> str | None:
            m = re.search(rf"\*\*{re.escape(key)}\*\*[:\s]+(.+)", text)
            return m.group(1).strip() if m else None

        if v := _extract("run_id"):
            state.run_id = v
        if v := _extract("mode"):
            with contextlib.suppress(ValueError):
                state.mode = RalphMode(v)
        if v := _extract("active"):
            state.active = v.lower() == "true"
        if v := _extract("iteration"):
            with contextlib.suppress(ValueError):
                state.iteration = int(v)
        if v := _extract("max_iterations"):
            with contextlib.suppress(ValueError):
                state.max_iterations = int(v)
        if v := _extract("completion_promise"):
            state.completion_promise = v.lower() == "true"
        if v := _extract("goal"):
            state.goal = v
        if v := _extract("loop_type"):
            state.loop_type = v
        if v := _extract("created_at"):
            with contextlib.suppress(ValueError):
                state.created_at = float(v)
        if v := _extract("updated_at"):
            with contextlib.suppress(ValueError):
                state.updated_at = float(v)
        if v := _extract("stop_reason"):
            state.stop_reason = v if v else None

        return state


# ---------------------------------------------------------------------------
# State file I/O
# ---------------------------------------------------------------------------


def load_state(state_path: Path | None = None) -> RalphState | None:
    """Read the state file and return a ``RalphState``.

    Returns None if the file does not exist.
    """
    path = state_path or _LOCAL_STATE_PATH
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return RalphState.from_markdown(text)


def save_state(state: RalphState, state_path: Path | None = None) -> None:
    """Save a ``RalphState`` to the state file.

    Written atomically. ``from_markdown`` deliberately falls back to defaults for
    fields it cannot parse, so a truncated state file does not fail loudly — it
    silently resurrects the loop at ``iteration=0``, ``active=True`` and
    ``stop_reason=None``, handing an exhausted or deliberately stopped run a
    fresh iteration budget. Interrupting a long autonomous loop is exactly when
    that half-written file would appear.
    """
    path = state_path or _LOCAL_STATE_PATH
    state.updated_at = time.time()
    atomic_write_text(path, state.to_markdown())


def clear_state(state_path: Path | None = None) -> None:
    """Delete the state file."""
    path = state_path or _LOCAL_STATE_PATH
    if path.is_file():
        path.unlink()


# ---------------------------------------------------------------------------
# Ralph loop engine skeleton
# ---------------------------------------------------------------------------


class RalphEngine:
    """Ralph loop engine (P0 skeleton).

    Provides scaffold interfaces for each execution mode.
    Loops A–E are implemented in P4–P6.

    Parameters
    ----------
    mode:
        Execution mode (in-session / detached).
    max_iterations:
        Maximum iteration count (default 20, overnight cap 50).
    goal:
        Loop goal string.
    loop_type:
        Loop type (A, B, C, D, E, or user-defined).
    budget_tracker:
        BudgetTracker instance (for budget gate integration).
    state_path:
        State file path (None → .maglab/ralph.local.md).
    """

    MAX_ITERATIONS_OVERNIGHT = 50

    def __init__(
        self,
        mode: RalphMode = RalphMode.IN_SESSION,
        max_iterations: int = 20,
        goal: str = "",
        loop_type: str = "",
        budget_tracker: Any = None,
        state_path: Path | None = None,
    ) -> None:
        self._mode = mode
        self._max_iterations = min(max_iterations, self.MAX_ITERATIONS_OVERNIGHT)
        self._goal = goal
        self._loop_type = loop_type
        self._budget = budget_tracker
        self._state_path = state_path or _LOCAL_STATE_PATH
        self._circuit = CircuitBreakerState()
        self._state: RalphState | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> RalphState:
        """Start a new Ralph run and initialize state.

        Returns
        -------
        New RalphState.
        """
        self._state = RalphState(
            mode=self._mode,
            active=True,
            iteration=0,
            max_iterations=self._max_iterations,
            goal=self._goal,
            loop_type=self._loop_type,
        )
        self._circuit = CircuitBreakerState()
        save_state(self._state, self._state_path)
        log.info(
            "Ralph loop started: run_id=%s, mode=%s, max_iter=%d",
            self._state.run_id,
            self._state.mode.value,
            self._state.max_iterations,
        )
        return self._state

    def resume(self) -> RalphState | None:
        """Resume a run from an existing state file.

        Returns None if no state file exists.
        """
        state = load_state(self._state_path)
        if state is None:
            log.warning("No Ralph state file to resume: %s", self._state_path)
            return None
        if not state.active:
            log.warning("Ralph run is already inactive: run_id=%s", state.run_id)
            return state
        self._state = state
        self._circuit = CircuitBreakerState()
        log.info(
            "Ralph loop resumed: run_id=%s, iteration=%d/%d",
            state.run_id,
            state.iteration,
            state.max_iterations,
        )
        return state

    def step(
        self,
        output: str,
        score: float = 0.0,
        error_key: str | None = None,
    ) -> StopReason | None:
        """Record one iteration and check circuit-breaker conditions.

        Parameters
        ----------
        output:
            Agent output for this iteration.
        score:
            Progress score (0–1).
        error_key:
            Error identification string, if an error occurred.

        Returns
        -------
        Stop reason (None means continue).
        """
        if self._state is None:
            raise RuntimeError("Ralph run has not been started. Call start() or resume() first.")

        self._state.iteration += 1

        # Check completion signal
        if parse_done_signal(output):
            self._state.completion_promise = True
            self._stop(StopReason.DONE_SIGNAL)
            return StopReason.DONE_SIGNAL

        # Check max iterations
        if self._state.iteration >= self._state.max_iterations:
            self._stop(StopReason.MAX_ITERATIONS)
            return StopReason.MAX_ITERATIONS

        # Budget gate
        if self._budget is not None and self._budget.is_over_budget():
            self._stop(StopReason.BUDGET_EXCEEDED)
            return StopReason.BUDGET_EXCEEDED

        # Record error — error iterations are not passed to record_output (no-progress check)
        if error_key:
            reason = self._circuit.record_error(error_key)
            if reason:
                self._stop(reason)
                return reason
            save_state(self._state, self._state_path)
            return None

        # Record output and score (normal iteration, no error)
        reason = self._circuit.record_output(output, score)
        if reason:
            self._stop(reason)
            return reason

        # Save state
        save_state(self._state, self._state_path)
        return None

    def stop(self, reason: StopReason = StopReason.EXTERNAL) -> RalphState:
        """Explicitly stop the loop.

        Returns
        -------
        Final RalphState.
        """
        return self._stop(reason)

    @property
    def state(self) -> RalphState | None:
        return self._state

    @property
    def circuit_breaker(self) -> CircuitBreakerState:
        return self._circuit

    def is_active(self) -> bool:
        """Return True if the loop is currently active."""
        return self._state is not None and self._state.active

    # ------------------------------------------------------------------
    # In-session scaffold (implemented from P4)
    # ------------------------------------------------------------------

    def in_session_hook(self, output: str) -> bool:
        """Stop-hook handler scaffold for in-session mode.

        Receives the agent output and returns True to continue or False to stop.
        The actual re-injection logic is implemented in P4.

        Parameters
        ----------
        output:
            Agent output text.

        Returns
        -------
        True to proceed to the next iteration, False to stop.
        """
        # P0 skeleton: only check completion signal and max iterations
        if parse_done_signal(output):
            log.info("[in-session] Completion signal received — stopping loop")
            return False
        if self._state and self._state.iteration >= self._state.max_iterations:
            log.info("[in-session] Max iterations reached — stopping loop")
            return False
        return True

    # ------------------------------------------------------------------
    # Detached scaffold (implemented from P4)
    # ------------------------------------------------------------------

    def detached_loop(
        self,
        agent_fn: Any,
        *args: Any,
        git_commit: bool = False,
        score_fn: Callable[[str], float] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """External loop scaffold for detached mode.

        Calls ``agent_fn`` on each iteration and collects outputs.

        Parameters
        ----------
        agent_fn:
            Agent function to call each iteration.
            Signature: (state: RalphState, *args, **kwargs) -> str
        git_commit:
            When True, commit the working tree after every successful
            iteration (§6.2 — detached fresh-context handoff via files + git).
            A no-op with a logged warning when the working directory is not a
            git repository or there is nothing to commit.
        score_fn:
            Optional scoring function: ``(output: str) -> float`` (0–1).
            When provided, its return value is passed to ``step()`` as the
            progress score and the NO_PROGRESS circuit breaker is active.
            When absent (default), the NO_PROGRESS circuit breaker is
            suppressed — a detached loop's genuine "stuck" condition is
            repeated identical output, which the OUTPUT_SIMILARITY breaker
            already detects.  The DONE_SIGNAL, REPEATED_ERROR, BUDGET, and
            MAX_ITERATIONS breakers remain fully active in both cases.

        Returns
        -------
        List of outputs from each iteration.
        """
        if self._state is None:
            self.start()
        assert self._state is not None  # noqa: S101 — always initialized here

        outputs: list[str] = []
        while self._state.active and self._state.iteration < self._state.max_iterations:
            try:
                output = agent_fn(self._state, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                error_key = type(exc).__name__
                log.warning("[detached] Agent error (iteration %d): %s", self._state.iteration, exc)
                reason = self.step("", score=0.0, error_key=error_key)
                if reason:
                    log.info("[detached] Circuit breaker: %s", reason)
                    break
                continue

            outputs.append(output)
            if score_fn is not None:
                # Caller-supplied scorer: NO_PROGRESS breaker is active.
                score = score_fn(output)
                reason = self.step(output, score=score)
            else:
                # No scorer supplied: suppress the NO_PROGRESS breaker so that
                # the loop can run to max_iterations.  Reset no_progress_count
                # before recording so that consecutive same-score calls never
                # accumulate, while OUTPUT_SIMILARITY, REPEATED_ERROR, BUDGET,
                # and MAX_ITERATIONS breakers remain active.
                self._circuit.reset_no_progress()
                reason = self.step(output, score=0.5)
            if git_commit:
                self._git_commit_iteration()
            if reason:
                log.info("[detached] Circuit breaker: %s", reason)
                break

        return outputs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _stop(self, reason: StopReason) -> RalphState:
        """Stop the loop and save state."""
        if self._state is not None:
            self._state.active = False
            self._state.stop_reason = reason.value
            save_state(self._state, self._state_path)
            log.info(
                "Ralph loop stopped: run_id=%s, reason=%s, iteration=%d",
                self._state.run_id,
                reason.value,
                self._state.iteration,
            )
        return self._state  # type: ignore[return-value]

    def _git_commit_iteration(self) -> None:
        """Commit the working tree after a detached-mode iteration (§6.2).

        Detached fresh-context mode hands state between iterations via files +
        git.  This is a no-op with a logged warning when the working directory
        is not a git repository or there is nothing to commit.
        """
        if self._state is None:
            return
        label = self._state.loop_type or "loop"
        msg = f"ralph: {label} iteration {self._state.iteration}"
        try:
            subprocess.run(
                ["git", "add", "-A"],
                check=True,
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["git", "commit", "-m", msg],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ) as exc:
            log.warning(
                "[detached] git commit skipped (iteration %d): %s",
                self._state.iteration,
                exc,
            )


# ---------------------------------------------------------------------------
# Loop B — Experiment code implementation / pytest / fix loop (§6.3-B, §13.4)
# ---------------------------------------------------------------------------


@dataclass
class LoopBResult:
    """Loop B execution result.

    Attributes
    ----------
    success:
        True if pytest passed all tests.
    iterations:
        Total number of iterations executed.
    final_code:
        Final generated code string.
    stop_reason:
        Stop reason.
    test_output:
        Last pytest output string.
    """

    success: bool
    iterations: int
    final_code: str
    stop_reason: str
    test_output: str


def _run_pytest(
    code: str,
    test_code: str,
    tmp_dir: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Write code and tests to a temp directory and run pytest -x.

    Parameters
    ----------
    code:
        Implementation code string (instrument_script.py).
    test_code:
        Test code string (test_script.py).
    tmp_dir:
        Temporary working directory.
    extra_env:
        Additional environment variables (e.g. mock instrument settings).

    Returns
    -------
    (passed, output)
        passed=True if all tests pass.
    """
    import os

    code_path = tmp_dir / "instrument_script.py"
    test_path = tmp_dir / "test_script.py"
    code_path.write_text(code, encoding="utf-8")
    test_path.write_text(test_code, encoding="utf-8")

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    # ``-B`` disables bytecode caching: Loop B rewrites instrument_script.py
    # every iteration, and a same-length edit (e.g. ``a - b`` -> ``a + b``)
    # written within the same integer-second would otherwise reuse a stale
    # ``.pyc`` so the fixed code would never take effect.
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", str(test_path), "-x", "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=str(tmp_dir),
        env=env,
        timeout=60,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def _parse_pytest_failures(output: str) -> list[str]:
    """Parse failure entries from pytest output.

    Parameters
    ----------
    output:
        pytest --tb=short output.

    Returns
    -------
    List of failure descriptions.
    """
    failures: list[str] = []
    lines = output.splitlines()
    in_failure = False
    current: list[str] = []
    for line in lines:
        if line.startswith("FAILED") or "AssertionError" in line or "Error" in line:
            in_failure = True
        if in_failure:
            current.append(line)
            if line.startswith("=") and current:
                failures.append("\n".join(current))
                current = []
                in_failure = False
    if current:
        failures.append("\n".join(current))
    # If no failures found, treat the whole output as a single entry
    if not failures and output.strip():
        failures = [output[:2000]]
    return failures


def run_loop_b(
    *,
    goal: str,
    initial_code: str,
    test_code: str,
    code_improver_fn: Callable[[str, list[str]], str],
    max_iterations: int = 10,
    budget_tracker: Any = None,
    state_path: Path | None = None,
) -> LoopBResult:
    """Loop B — implement experiment code → mock instrument pytest → parse failures → fix loop.

    Parameters
    ----------
    goal:
        Loop goal description.
    initial_code:
        Initial implementation code.
    test_code:
        pytest test code (including mock instrument).
    code_improver_fn:
        Code fix function: (current_code: str, failures: list[str]) -> new_code: str.
        Replaced by a mock in tests when LLM-based.
    max_iterations:
        Maximum iteration count.
    budget_tracker:
        BudgetTracker instance (budget gate).
    state_path:
        Ralph state file path.

    Returns
    -------
    LoopBResult
    """
    engine = RalphEngine(
        mode=RalphMode.IN_SESSION,
        max_iterations=max_iterations,
        goal=goal,
        loop_type="B",
        budget_tracker=budget_tracker,
        state_path=state_path or Path(".maglab") / "ralph_loop_b.md",
    )
    engine.start()

    current_code = initial_code
    test_output = ""

    with tempfile.TemporaryDirectory() as _tmp:
        tmp_dir = Path(_tmp)

        while engine.is_active():
            # Run pytest -x
            try:
                passed, test_output = _run_pytest(current_code, test_code, tmp_dir)
            except subprocess.TimeoutExpired:
                test_output = "pytest timeout"
                passed = False
            except Exception as exc:  # noqa: BLE001
                test_output = f"pytest run error: {exc}"
                passed = False

            if passed:
                # Send completion signal
                reason = engine.step("<promise>DONE</promise>", score=1.0)
                return LoopBResult(
                    success=True,
                    iterations=engine.state.iteration if engine.state else 0,
                    final_code=current_code,
                    stop_reason=StopReason.DONE_SIGNAL.value,
                    test_output=test_output,
                )

            # Parse failures
            failures = _parse_pytest_failures(test_output)
            failure_summary = "\n".join(failures[:3])

            # Circuit breaker — record error
            reason = engine.step(
                failure_summary,
                score=0.0,
                error_key=failure_summary[:100],
            )
            if reason is not None:
                return LoopBResult(
                    success=False,
                    iterations=engine.state.iteration if engine.state else 0,
                    final_code=current_code,
                    stop_reason=reason.value,
                    test_output=test_output,
                )

            # Fix code
            try:
                current_code = code_improver_fn(current_code, failures)
            except Exception as exc:  # noqa: BLE001
                log.warning("[Loop B] code_improver_fn error: %s", exc)
                err_key = type(exc).__name__
                reason = engine.step("", score=0.0, error_key=err_key)
                if reason:
                    break

    return LoopBResult(
        success=False,
        iterations=engine.state.iteration if engine.state else 0,
        final_code=current_code,
        stop_reason=engine.state.stop_reason or StopReason.MAX_ITERATIONS.value
        if engine.state
        else StopReason.EXTERNAL.value,
        test_output=test_output,
    )


# ---------------------------------------------------------------------------
# Loop D — Effect fitting improvement Ralph loop (§6.3-D, §11.4)
# ---------------------------------------------------------------------------


@dataclass
class FitCheckResult:
    """Fit quality check result.

    Attributes
    ----------
    passed:
        True if all checks pass.
    chi2:
        χ² value (lower is better).
    r2:
        R² value (closer to 1 is better).
    residuals_random:
        Whether the residuals pass the randomness check.
    physics_ok:
        Whether the physics bounds check passes.
    messages:
        List of check result messages.
    """

    passed: bool
    chi2: float = 0.0
    r2: float = 0.0
    residuals_random: bool = True
    physics_ok: bool = True
    messages: list[str] = dataclasses.field(default_factory=list)


def _check_fit_quality(
    fit_result: dict[str, Any],
    *,
    chi2_threshold: float = 10.0,
    r2_threshold: float = 0.95,
) -> FitCheckResult:
    """Check residuals and physics bounds of a fit result.

    Parameters
    ----------
    fit_result:
        Dictionary returned by EffectModel.fit().
        Expected keys: chi2, r2, residuals, params.
    chi2_threshold:
        χ² acceptance threshold (fail if exceeded).
    r2_threshold:
        R² acceptance threshold (fail if not met).

    Returns
    -------
    FitCheckResult
    """
    import numpy as np

    messages: list[str] = []
    chi2 = float(fit_result.get("chi2", 0.0))
    r2 = float(fit_result.get("r2", 1.0))
    residuals = fit_result.get("residuals")

    # χ² check
    chi2_ok = chi2 < chi2_threshold
    if not chi2_ok:
        messages.append(f"χ²={chi2:.4f} > threshold {chi2_threshold}")

    # R² check
    r2_ok = r2 >= r2_threshold
    if not r2_ok:
        messages.append(f"R²={r2:.4f} < threshold {r2_threshold}")

    # Residuals randomness check (simplified runs test)
    residuals_random = True
    if residuals is not None:
        try:
            res_arr = np.asarray(residuals, dtype=float)
            if len(res_arr) >= 4:
                # Simple judgment by sign-change count: too few suggests systematic pattern
                sign_changes = int(np.sum(np.diff(np.sign(res_arr)) != 0))
                if sign_changes < len(res_arr) // 4:
                    residuals_random = False
                    messages.append(
                        f"Residuals may be non-random (sign changes={sign_changes}/{len(res_arr)})"
                    )
        except Exception:  # noqa: BLE001
            pass

    # Physics bounds check (oracle integration)
    physics_ok = True
    params = fit_result.get("params", {})
    if params:
        try:
            from maglab.physics import oracle as physics_oracle

            oracle_result = physics_oracle.check(
                {k: float(v) for k, v in params.items() if isinstance(v, (int, float))}
            )
            if not oracle_result.ok:
                physics_ok = False
                messages.append(f"Physics bounds violation: {oracle_result.reason}")
        except Exception:  # noqa: BLE001
            pass  # skip if oracle import fails

    passed = chi2_ok and r2_ok and residuals_random and physics_ok
    return FitCheckResult(
        passed=passed,
        chi2=chi2,
        r2=r2,
        residuals_random=residuals_random,
        physics_ok=physics_ok,
        messages=messages,
    )


@dataclass
class LoopDResult:
    """Loop D execution result.

    Attributes
    ----------
    success:
        True if the fit converged.
    iterations:
        Total number of iterations executed.
    final_params:
        Final fit parameters.
    fit_check:
        Last fit quality check result.
    stop_reason:
        Stop reason.
    """

    success: bool
    iterations: int
    final_params: dict[str, Any]
    fit_check: FitCheckResult
    stop_reason: str


def run_loop_d(
    *,
    goal: str,
    fit_fn: Callable[..., dict[str, Any]],
    adjust_fn: Callable[[dict[str, Any], FitCheckResult], dict[str, Any]],
    initial_kwargs: dict[str, Any] | None = None,
    max_iterations: int = 10,
    chi2_threshold: float = 10.0,
    r2_threshold: float = 0.95,
    budget_tracker: Any = None,
    state_path: Path | None = None,
) -> LoopDResult:
    """Loop D — improve effect fitting → check residuals and physics bounds → refit loop.

    Parameters
    ----------
    goal:
        Loop goal description.
    fit_fn:
        Fit function: (**kwargs) -> dict[str, Any].
        Result dict must contain keys: chi2, r2, params, residuals.
    adjust_fn:
        Parameter adjustment function: (fit_result: dict, check: FitCheckResult) -> new_kwargs: dict.
        Replaced by a mock in tests when LLM-based.
    initial_kwargs:
        Initial fit parameter dict.
    max_iterations:
        Maximum iteration count.
    chi2_threshold:
        χ² acceptance threshold.
    r2_threshold:
        R² acceptance threshold.
    budget_tracker:
        BudgetTracker instance.
    state_path:
        Ralph state file path.

    Returns
    -------
    LoopDResult
    """
    engine = RalphEngine(
        mode=RalphMode.IN_SESSION,
        max_iterations=max_iterations,
        goal=goal,
        loop_type="D",
        budget_tracker=budget_tracker,
        state_path=state_path or Path(".maglab") / "ralph_loop_d.md",
    )
    engine.start()

    current_kwargs = initial_kwargs or {}
    last_fit_result: dict[str, Any] = {}
    last_check = FitCheckResult(passed=False)

    while engine.is_active():
        # Run fit
        try:
            last_fit_result = fit_fn(**current_kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("[Loop D] fit_fn error: %s", exc)
            err_key = type(exc).__name__
            reason = engine.step("", score=0.0, error_key=err_key)
            if reason:
                return LoopDResult(
                    success=False,
                    iterations=engine.state.iteration if engine.state else 0,
                    final_params=current_kwargs,
                    fit_check=last_check,
                    stop_reason=reason.value,
                )
            continue

        # Quality check
        last_check = _check_fit_quality(
            last_fit_result,
            chi2_threshold=chi2_threshold,
            r2_threshold=r2_threshold,
        )

        if last_check.passed:
            reason = engine.step("<promise>DONE</promise>", score=1.0)
            return LoopDResult(
                success=True,
                iterations=engine.state.iteration if engine.state else 0,
                final_params=last_fit_result.get("params", current_kwargs),
                fit_check=last_check,
                stop_reason=StopReason.DONE_SIGNAL.value,
            )

        # Score calculation (R²-based)
        score = max(0.0, min(1.0, float(last_fit_result.get("r2", 0.0))))
        iteration_n = engine.state.iteration if engine.state else 0
        check_summary = f"[iter={iteration_n}] " + (
            "; ".join(last_check.messages) or "fit check failed"
        )

        reason = engine.step(check_summary, score=score)
        if reason is not None:
            return LoopDResult(
                success=False,
                iterations=engine.state.iteration if engine.state else 0,
                final_params=last_fit_result.get("params", current_kwargs),
                fit_check=last_check,
                stop_reason=reason.value,
            )

        # Adjust parameters
        try:
            current_kwargs = adjust_fn(last_fit_result, last_check)
        except Exception as exc:  # noqa: BLE001
            log.warning("[Loop D] adjust_fn error: %s", exc)
            err_key = type(exc).__name__
            reason = engine.step("", score=0.0, error_key=err_key)
            if reason:
                break

    return LoopDResult(
        success=False,
        iterations=engine.state.iteration if engine.state else 0,
        final_params=last_fit_result.get("params", current_kwargs),
        fit_check=last_check,
        stop_reason=engine.state.stop_reason or StopReason.MAX_ITERATIONS.value
        if engine.state
        else StopReason.EXTERNAL.value,
    )


# ---------------------------------------------------------------------------
# Loop E — Figure refinement Ralph loop (§6.3-E, §12.5)
# ---------------------------------------------------------------------------


@dataclass
class FigureCriticResult:
    """Vision model figure critic result.

    Attributes
    ----------
    passed:
        True if all checks pass.
    issues:
        List of identified issues.
    suggestions:
        List of fix suggestions.
    raw_response:
        Raw response from the vision model.
    """

    passed: bool
    issues: list[str] = dataclasses.field(default_factory=list)
    suggestions: list[str] = dataclasses.field(default_factory=list)
    raw_response: str = ""


_CRITIC_CHECKLIST = [
    "Axis and unit labels present",
    "Readability at publication size (font >= 8pt)",
    "Colorblind-safe palette",
    "Panel labels (a/b/c)",
    "Journal spec dimensions match",
    "Data-source consistency (DataPoint binding)",
]


def _build_critic_prompt(checklist: list[str] | None = None) -> str:
    """Generate the vision model critic prompt."""
    items = checklist or _CRITIC_CHECKLIST
    checklist_text = "\n".join(f"- {item}" for item in items)
    return (
        "You are a publication figure quality reviewer. Evaluate the provided "
        "figure image against the following checklist:\n\n"
        f"{checklist_text}\n\n"
        "Judge each item as pass or fail, and for any failures provide specific "
        "corrective actions. If all items pass, write 'PASSED' on the last line."
    )


def _parse_critic_response(response: str) -> FigureCriticResult:
    """Parse the vision model response into a FigureCriticResult."""
    # Detect PASSED only as a standalone word on the final non-empty line so
    # that mid-response occurrences ("not passed", "items not passed: …",
    # "Axis labels passed, colorblind failed") do NOT trigger a false pass.
    # The final line must contain the word PASSED (word boundary) but must
    # NOT contain "NOT PASSED" or "FAILED".
    import re as _re

    _lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
    if _lines:
        _last = _lines[-1].upper()
        passed = bool(
            _re.search(r"\bPASSED\b", _last)
            and not _re.search(r"\bNOT\s+PASSED\b", _last)
            and "FAILED" not in _last
        )
    else:
        passed = False
    issues: list[str] = []
    suggestions: list[str] = []

    for line in response.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if "fail" in low or "missing" in low or "absent" in low:
            issues.append(stripped)
        elif "fix" in low or "suggest" in low or "improve" in low or "add" in low:
            suggestions.append(stripped)

    if not issues and not passed:
        # Response exists but is unstructured
        issues = [response[:500]]

    return FigureCriticResult(
        passed=passed,
        issues=issues,
        suggestions=suggestions,
        raw_response=response,
    )


def _rasterize_figure(svg_or_pdf_path: Path, output_png: Path) -> bool:
    """Rasterize SVG/PDF to PNG (for vision critic preview).

    Uses cairosvg when installed; returns False on failure.
    """
    try:
        if svg_or_pdf_path.suffix.lower() == ".svg":
            import cairosvg

            cairosvg.svg2png(
                url=str(svg_or_pdf_path),
                write_to=str(output_png),
                dpi=150,
            )
            return True
        # PDF → PNG: not supported by cairosvg; fall back to matplotlib
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("[Loop E] Rasterization failed: %s", exc)
        return False


@dataclass
class LoopEResult:
    """Loop E execution result.

    Attributes
    ----------
    success:
        True if the critic returned PASSED.
    iterations:
        Total number of iterations executed.
    stop_reason:
        Stop reason.
    final_critic:
        Last critic result.
    """

    success: bool
    iterations: int
    stop_reason: str
    final_critic: FigureCriticResult


def run_loop_e(
    *,
    goal: str,
    render_fn: Callable[[], Path],
    apply_fixes_fn: Callable[[FigureCriticResult], None],
    vision_critic_fn: Callable[[Path, str], str] | None = None,
    max_iterations: int = 5,
    budget_tracker: Any = None,
    state_path: Path | None = None,
    critic_checklist: list[str] | None = None,
) -> LoopEResult:
    """Loop E — render figure → vision model critic → apply fixes loop.

    Parameters
    ----------
    goal:
        Loop goal description.
    render_fn:
        Figure render function: () -> Path (SVG or PDF path).
    apply_fixes_fn:
        Fix application function: (critic_result: FigureCriticResult) -> None.
        Modifies FigureSpec or schematic parameters.
    vision_critic_fn:
        Vision model critic function: (image_path: Path, prompt: str) -> str.
        When None, the critic step is skipped with a warning.
    max_iterations:
        Maximum iteration count.
    budget_tracker:
        BudgetTracker instance.
    state_path:
        Ralph state file path.
    critic_checklist:
        Evaluation checklist. Uses the default checklist when None.

    Returns
    -------
    LoopEResult
    """
    engine = RalphEngine(
        mode=RalphMode.IN_SESSION,
        max_iterations=max_iterations,
        goal=goal,
        loop_type="E",
        budget_tracker=budget_tracker,
        state_path=state_path or Path(".maglab") / "ralph_loop_e.md",
    )
    engine.start()

    critic_prompt = _build_critic_prompt(critic_checklist)
    last_critic = FigureCriticResult(passed=False, raw_response="not executed")

    with tempfile.TemporaryDirectory() as _tmp:
        tmp_dir = Path(_tmp)

        while engine.is_active():
            # Render
            try:
                figure_path = render_fn()
            except Exception as exc:  # noqa: BLE001
                log.warning("[Loop E] render_fn error: %s", exc)
                reason = engine.step("", score=0.0, error_key=type(exc).__name__)
                if reason:
                    return LoopEResult(
                        success=False,
                        iterations=engine.state.iteration if engine.state else 0,
                        stop_reason=reason.value,
                        final_critic=last_critic,
                    )
                continue

            # No vision critic — warn and treat as PASSED
            if vision_critic_fn is None:
                log.warning("[Loop E] No vision model configured — skipping critic step")
                last_critic = FigureCriticResult(
                    passed=True,
                    issues=[],
                    suggestions=[],
                    raw_response="No vision model configured — automatic PASSED",
                )
                reason = engine.step("<promise>DONE</promise>", score=1.0)
                return LoopEResult(
                    success=True,
                    iterations=engine.state.iteration if engine.state else 0,
                    stop_reason=StopReason.DONE_SIGNAL.value,
                    final_critic=last_critic,
                )

            # Rasterize (PNG preview)
            preview_png = tmp_dir / f"preview_{engine.state.iteration if engine.state else 0}.png"
            rasterized = _rasterize_figure(figure_path, preview_png)
            critic_input = preview_png if rasterized else figure_path

            # Call vision model critic
            try:
                raw_response = vision_critic_fn(critic_input, critic_prompt)
                last_critic = _parse_critic_response(raw_response)
            except Exception as exc:  # noqa: BLE001
                log.warning("[Loop E] vision_critic_fn error: %s", exc)
                reason = engine.step("", score=0.0, error_key=type(exc).__name__)
                if reason:
                    break
                continue

            if last_critic.passed:
                reason = engine.step("<promise>DONE</promise>", score=1.0)
                return LoopEResult(
                    success=True,
                    iterations=engine.state.iteration if engine.state else 0,
                    stop_reason=StopReason.DONE_SIGNAL.value,
                    final_critic=last_critic,
                )

            # Circuit-breaker check
            issues_summary = "; ".join(last_critic.issues[:3]) or "critic failed"
            score = 1.0 - min(1.0, len(last_critic.issues) / 6.0)
            reason = engine.step(issues_summary, score=score)
            if reason is not None:
                return LoopEResult(
                    success=False,
                    iterations=engine.state.iteration if engine.state else 0,
                    stop_reason=reason.value,
                    final_critic=last_critic,
                )

            # Apply fixes
            try:
                apply_fixes_fn(last_critic)
            except Exception as exc:  # noqa: BLE001
                log.warning("[Loop E] apply_fixes_fn error: %s", exc)
                reason = engine.step("", score=0.0, error_key=type(exc).__name__)
                if reason:
                    break

    return LoopEResult(
        success=False,
        iterations=engine.state.iteration if engine.state else 0,
        stop_reason=engine.state.stop_reason or StopReason.MAX_ITERATIONS.value
        if engine.state
        else StopReason.EXTERNAL.value,
        final_critic=last_critic,
    )
