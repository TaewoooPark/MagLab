"""Machine-readable `--json` output must stay parseable.

Rich colourises whenever it decides colour is wanted — and ``FORCE_COLOR``, set
by default on many CI runners, makes that happen even when stdout is a pipe. Any
``--json`` payload that went through ``Console.print_json``/``Console.print``
therefore arrived at ``json.load`` wrapped in ANSI escapes.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from maglab.ui.json_output import emit_json, emit_json_text

runner = CliRunner()


class TestEmitHelpers:
    def test_emit_json_writes_parseable_payload(self, capsys: pytest.CaptureFixture[str]) -> None:
        emit_json({"a": 1, "b": ["x", "y"]})
        assert json.loads(capsys.readouterr().out) == {"a": 1, "b": ["x", "y"]}

    def test_emit_json_preserves_non_ascii(self, capsys: pytest.CaptureFixture[str]) -> None:
        emit_json({"topic": "자성"})
        assert json.loads(capsys.readouterr().out) == {"topic": "자성"}

    def test_emit_json_text_passes_through_verbatim(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        emit_json_text('{"already": "serialised"}')
        out = capsys.readouterr().out
        assert out == '{"already": "serialised"}\n'

    def test_emit_json_text_does_not_double_newline(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        emit_json_text('{"a": 1}\n')
        assert capsys.readouterr().out == '{"a": 1}\n'

    def test_long_values_are_not_wrapped(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Rich word-wraps at terminal width, which can split a string literal."""
        payload = {"note": "x" * 500}
        emit_json(payload)
        assert json.loads(capsys.readouterr().out) == payload


class TestJsonCommandsUnderForcedColour:
    """End-to-end: run the real CLI with FORCE_COLOR set and parse its stdout."""

    def _run(self, *args: str) -> str:
        proc = subprocess.run(
            [sys.executable, "-m", "maglab", *args],
            capture_output=True,
            text=True,
            env={"FORCE_COLOR": "3", "TERM": "xterm-256color", "PATH": "/usr/bin:/bin"},
            timeout=120,
            check=False,
        )
        assert proc.returncode == 0, f"command failed: {proc.stderr[:400]}"
        return proc.stdout

    def test_config_show_emits_parseable_json(self) -> None:
        payload = json.loads(self._run("config", "show"))
        assert "backend" in payload

    def test_config_callback_emits_parseable_json(self) -> None:
        payload = json.loads(self._run("config"))
        assert "backend" in payload

    def test_prov_summary_json_is_parseable(self) -> None:
        payload = json.loads(self._run("prov", "summary", "--json"))
        assert isinstance(payload, dict)

    def test_json_output_carries_no_ansi_escapes(self) -> None:
        assert "\x1b[" not in self._run("config", "show")


class TestProgressStaysOffStdout:
    """A live spinner emits cursor control sequences — they must not hit stdout.

    ``Console.status`` hides the cursor, paints a frame, then moves back and
    erases the line. On stdout those land in the pipe ahead of the payload, so
    ``maglab explain --json | jq`` failed at column 1 whenever Rich rendered
    live output — a terminal, or ``FORCE_COLOR``, which many CI runners set.
    """

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "maglab", *args],
            capture_output=True,
            text=True,
            env={"FORCE_COLOR": "3", "TERM": "xterm-256color", "PATH": "/usr/bin:/bin"},
            timeout=300,
            check=False,
        )

    def test_explain_json_stdout_is_pure_json(self) -> None:
        proc = self._run("explain", "AHE sign reversal above 200 K", "--json")
        assert proc.returncode == 0, proc.stderr[:400]
        payload = json.loads(proc.stdout)
        assert "candidates" in payload

    def test_explain_json_stdout_has_no_control_sequences(self) -> None:
        proc = self._run("explain", "AHE sign reversal above 200 K", "--json")
        assert "\x1b[" not in proc.stdout, "progress output leaked into the data stream"

    def test_status_console_targets_stderr(self) -> None:
        from maglab.ui.status import status_console

        assert status_console.stderr is True

    def test_command_modules_do_not_spin_on_stdout(self) -> None:
        from pathlib import Path

        import maglab

        root = Path(maglab.__file__).parent
        offenders = [
            str(path.relative_to(root.parent))
            for path in root.rglob("*.py")
            if "console.status("
            in path.read_text(encoding="utf-8").replace("status_console.status(", "")
        ]
        assert offenders == [], f"progress written to stdout in: {offenders}"


class TestNoColourisedJsonPrintersRemain:
    def test_source_tree_has_no_console_print_json(self) -> None:
        """`Console.print_json` always highlights — it must not gate a --json flag."""
        from pathlib import Path

        import maglab

        offenders = [
            f"{path.relative_to(Path(maglab.__file__).parent.parent)}"
            for path in Path(maglab.__file__).parent.rglob("*.py")
            if ".print_json(" in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"colourised JSON printers reintroduced in: {offenders}"
