"""CLI tests for the P4 ralph command — typer.testing.CliRunner-based.

All tests are deterministic (no LLM calls, no I/O except tmp_path).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from maglab.commands.p4_ralph import register
from maglab.core.ralph import RalphMode, RalphState, save_state

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

runner = CliRunner()


@pytest.fixture()
def ralph_cli() -> typer.Typer:
    """Fresh Typer app with the ralph sub-app registered."""
    app = typer.Typer()
    register(app)
    return app


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    """Return a temp path to use as a Ralph state file."""
    return tmp_path / "ralph_test.md"


# ---------------------------------------------------------------------------
# Help smoke-tests (must always exit 0)
# ---------------------------------------------------------------------------


class TestHelp:
    def test_ralph_help(self, ralph_cli: typer.Typer) -> None:
        result = runner.invoke(ralph_cli, ["ralph", "--help"])
        assert result.exit_code == 0, result.output
        assert "start" in result.output
        assert "status" in result.output
        assert "cancel" in result.output

    def test_start_help(self, ralph_cli: typer.Typer) -> None:
        result = runner.invoke(ralph_cli, ["ralph", "start", "--help"])
        assert result.exit_code == 0, result.output
        assert "goal" in result.output.lower()

    def test_status_help(self, ralph_cli: typer.Typer) -> None:
        result = runner.invoke(ralph_cli, ["ralph", "status", "--help"])
        assert result.exit_code == 0, result.output

    def test_cancel_help(self, ralph_cli: typer.Typer) -> None:
        result = runner.invoke(ralph_cli, ["ralph", "cancel", "--help"])
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# ralph start
# ---------------------------------------------------------------------------


class TestStart:
    def test_start_creates_state_file(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        result = runner.invoke(
            ralph_cli,
            ["ralph", "start", "Test goal", "--state-file", str(state_file)],
        )
        assert result.exit_code == 0, result.output
        assert state_file.is_file()

    def test_start_output_contains_goal(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        result = runner.invoke(
            ralph_cli,
            ["ralph", "start", "My research goal", "--state-file", str(state_file)],
        )
        assert result.exit_code == 0, result.output
        assert "My research goal" in result.output

    def test_start_default_mode_in_session(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        runner.invoke(
            ralph_cli,
            ["ralph", "start", "Goal", "--state-file", str(state_file)],
        )
        from maglab.core.ralph import load_state

        state = load_state(state_file)
        assert state is not None
        assert state.mode == RalphMode.IN_SESSION

    def test_start_detached_mode(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        result = runner.invoke(
            ralph_cli,
            [
                "ralph",
                "start",
                "Goal",
                "--mode",
                "detached",
                "--state-file",
                str(state_file),
            ],
        )
        assert result.exit_code == 0, result.output
        from maglab.core.ralph import load_state

        state = load_state(state_file)
        assert state is not None
        assert state.mode == RalphMode.DETACHED

    def test_start_custom_max_iterations(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        runner.invoke(
            ralph_cli,
            [
                "ralph",
                "start",
                "Goal",
                "--max-iter",
                "5",
                "--state-file",
                str(state_file),
            ],
        )
        from maglab.core.ralph import load_state

        state = load_state(state_file)
        assert state is not None
        assert state.max_iterations == 5

    def test_start_invalid_mode_exits_1(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        result = runner.invoke(
            ralph_cli,
            [
                "ralph",
                "start",
                "Goal",
                "--mode",
                "invalid-mode",
                "--state-file",
                str(state_file),
            ],
        )
        assert result.exit_code == 1

    def test_start_loop_type_saved(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        runner.invoke(
            ralph_cli,
            [
                "ralph",
                "start",
                "Goal",
                "--loop-type",
                "B",
                "--state-file",
                str(state_file),
            ],
        )
        from maglab.core.ralph import load_state

        state = load_state(state_file)
        assert state is not None
        assert state.loop_type == "B"


# ---------------------------------------------------------------------------
# ralph status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_missing_state_file_exits_1(
        self, ralph_cli: typer.Typer, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.md"
        result = runner.invoke(ralph_cli, ["ralph", "status", "--state-file", str(missing)])
        assert result.exit_code == 1
        assert "No Ralph state file" in result.output

    def test_status_active_loop(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        # Pre-create an active state
        state = RalphState(goal="Active goal", active=True, iteration=3, max_iterations=20)
        save_state(state, state_file)

        result = runner.invoke(ralph_cli, ["ralph", "status", "--state-file", str(state_file)])
        assert result.exit_code == 0, result.output
        assert "Active goal" in result.output
        assert "3" in result.output  # iteration count appears in output

    def test_status_stopped_loop_shows_reason(
        self, ralph_cli: typer.Typer, state_file: Path
    ) -> None:
        from maglab.core.ralph import StopReason

        state = RalphState(
            goal="Stopped goal",
            active=False,
            stop_reason=StopReason.MAX_ITERATIONS.value,
        )
        save_state(state, state_file)

        result = runner.invoke(ralph_cli, ["ralph", "status", "--state-file", str(state_file)])
        assert result.exit_code == 0, result.output
        assert StopReason.MAX_ITERATIONS.value in result.output

    def test_status_shows_mode(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        state = RalphState(mode=RalphMode.DETACHED, goal="Detached run")
        save_state(state, state_file)

        result = runner.invoke(ralph_cli, ["ralph", "status", "--state-file", str(state_file)])
        assert result.exit_code == 0, result.output
        assert "detached" in result.output


# ---------------------------------------------------------------------------
# ralph cancel
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_missing_state_file_exits_1(
        self, ralph_cli: typer.Typer, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.md"
        result = runner.invoke(ralph_cli, ["ralph", "cancel", "--state-file", str(missing)])
        assert result.exit_code == 1
        assert "No Ralph state file" in result.output

    def test_cancel_active_loop_stops_it(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        state = RalphState(goal="Running goal", active=True, iteration=2)
        save_state(state, state_file)

        result = runner.invoke(ralph_cli, ["ralph", "cancel", "--state-file", str(state_file)])
        assert result.exit_code == 0, result.output
        assert "cancelled" in result.output.lower()

        from maglab.core.ralph import load_state

        updated = load_state(state_file)
        assert updated is not None
        assert not updated.active
        assert updated.stop_reason == "external"

    def test_cancel_already_stopped_loop_reports_gracefully(
        self, ralph_cli: typer.Typer, state_file: Path
    ) -> None:
        state = RalphState(
            goal="Done goal",
            active=False,
            stop_reason="done_signal",
        )
        save_state(state, state_file)

        result = runner.invoke(ralph_cli, ["ralph", "cancel", "--state-file", str(state_file)])
        # Should NOT exit 1 — already stopped is not an error
        assert result.exit_code == 0, result.output
        assert "already stopped" in result.output.lower()


# ---------------------------------------------------------------------------
# Start → status → cancel lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_status_cancel_full_cycle(self, ralph_cli: typer.Typer, state_file: Path) -> None:
        # 1. Start
        result = runner.invoke(
            ralph_cli,
            ["ralph", "start", "Lifecycle goal", "--state-file", str(state_file)],
        )
        assert result.exit_code == 0, result.output
        assert state_file.is_file()

        # 2. Status — loop should be active
        result = runner.invoke(ralph_cli, ["ralph", "status", "--state-file", str(state_file)])
        assert result.exit_code == 0, result.output
        assert "Lifecycle goal" in result.output

        # 3. Cancel
        result = runner.invoke(ralph_cli, ["ralph", "cancel", "--state-file", str(state_file)])
        assert result.exit_code == 0, result.output

        # 4. Status after cancel — should show stopped
        result = runner.invoke(ralph_cli, ["ralph", "status", "--state-file", str(state_file)])
        assert result.exit_code == 0, result.output
        assert "external" in result.output
