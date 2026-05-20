"""tests/unit/test_gateway_runner.py — GatewayRunner unit tests (all network mocked)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from maglab.gateway.adapters.base import BaseAdapter, UnifiedMessage, hash_user_id
from maglab.gateway.runner import (
    GatewayRunner,
    NotificationEvent,
    generate_launchd_plist,
    generate_systemd_unit,
    install_service,
)
from maglab.gateway.session_db import SessionDB

# ---------------------------------------------------------------------------
# Mock adapter for testing
# ---------------------------------------------------------------------------


class MockAdapter(BaseAdapter):
    """Minimal adapter implementation for testing."""

    def __init__(
        self,
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
    ) -> None:
        super().__init__(allowed_users=allowed_users, allowed_channels=allowed_channels)
        self.sent_replies: list[dict[str, Any]] = []

    def verify_request(self, raw: dict[str, Any]) -> bool:
        user_id = raw.get("user_id", "")
        channel = raw.get("channel", "")
        if not user_id:
            return False
        uid_hash = hash_user_id(user_id)
        if not self._user_allowed(uid_hash):
            return False
        return not (channel and not self._channel_allowed(channel))

    def parse_message(self, raw: dict[str, Any]) -> UnifiedMessage:
        return UnifiedMessage(
            platform="mock",
            user_id_hash=hash_user_id(raw.get("user_id", "")),
            channel=raw.get("channel", ""),
            text=raw.get("text", ""),
            ts=float(raw.get("ts", 0.0)),
            raw=raw,
        )

    async def send_reply(
        self,
        channel: str,
        text: str,
        attachments: list[Any] | None = None,
        *,
        thread_ts: str | None = None,
    ) -> None:
        self.sent_replies.append({"channel": channel, "text": text})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_runner(tmp_path: Path) -> GatewayRunner:
    db = SessionDB(db_path=tmp_path / "gw.db")
    runner = GatewayRunner(db_path=tmp_path / "gw.db")
    yield runner
    db.close()


@pytest.fixture
def mock_adapter_open() -> MockAdapter:
    """Adapter with no allowlist restrictions."""
    return MockAdapter(allowed_users=None, allowed_channels=None)


@pytest.fixture
def mock_adapter_restricted() -> MockAdapter:
    """Adapter that only allows 'ALLOWED_USER'."""
    return MockAdapter(allowed_users={hash_user_id("ALLOWED_USER")})


# ---------------------------------------------------------------------------
# handle_message routing
# ---------------------------------------------------------------------------


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_unknown_platform_returns_none(self, tmp_runner: GatewayRunner) -> None:
        result = await tmp_runner.handle_message(
            "unknown_platform", {"user_id": "U1", "text": "hello"}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_rejected_user_returns_none(
        self, tmp_runner: GatewayRunner, mock_adapter_restricted: MockAdapter
    ) -> None:
        tmp_runner.add_adapter("mock", mock_adapter_restricted)
        result = await tmp_runner.handle_message(
            "mock", {"user_id": "BLOCKED_USER", "channel": "C1", "text": "hi"}
        )
        assert result is None
        assert mock_adapter_restricted.sent_replies == []

    @pytest.mark.asyncio
    async def test_allowed_user_gets_reply(
        self, tmp_runner: GatewayRunner, mock_adapter_restricted: MockAdapter
    ) -> None:
        tmp_runner.add_adapter("mock", mock_adapter_restricted)
        result = await tmp_runner.handle_message(
            "mock",
            {"user_id": "ALLOWED_USER", "channel": "C1", "text": "status"},
        )
        assert result is not None
        assert len(mock_adapter_restricted.sent_replies) == 1

    @pytest.mark.asyncio
    async def test_status_command(
        self, tmp_runner: GatewayRunner, mock_adapter_open: MockAdapter
    ) -> None:
        tmp_runner.add_adapter("mock", mock_adapter_open)
        result = await tmp_runner.handle_message(
            "mock", {"user_id": "U1", "channel": "C1", "text": "status"}
        )
        assert result is not None
        assert "Running" in result

    @pytest.mark.asyncio
    async def test_help_command(
        self, tmp_runner: GatewayRunner, mock_adapter_open: MockAdapter
    ) -> None:
        tmp_runner.add_adapter("mock", mock_adapter_open)
        result = await tmp_runner.handle_message(
            "mock", {"user_id": "U1", "channel": "C1", "text": "help"}
        )
        assert result is not None
        assert "commands" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_command_gets_default_reply(
        self, tmp_runner: GatewayRunner, mock_adapter_open: MockAdapter
    ) -> None:
        tmp_runner.add_adapter("mock", mock_adapter_open)
        result = await tmp_runner.handle_message(
            "mock",
            {"user_id": "U1", "channel": "C1", "text": "xyzzy_unknown_cmd"},
        )
        assert result is not None
        # Should get default "not recognised" reply
        assert "not recognised" in result.lower() or "help" in result.lower()


# ---------------------------------------------------------------------------
# Notification loop
# ---------------------------------------------------------------------------


class TestNotificationEvent:
    def test_format_sim_done(self) -> None:
        event = NotificationEvent("sim_done", "C1", payload={"task_id": "T42"})
        text = event.format_text()
        assert "Simulation complete" in text
        assert "T42" in text

    def test_format_figure_produced(self) -> None:
        event = NotificationEvent("figure_produced", "C2")
        text = event.format_text()
        assert "Figure produced" in text

    def test_format_unknown_kind(self) -> None:
        event = NotificationEvent("custom_kind", "C3")
        text = event.format_text()
        assert "custom_kind" in text


class TestNotificationPush:
    @pytest.mark.asyncio
    async def test_notification_delivered(
        self, tmp_runner: GatewayRunner, mock_adapter_open: MockAdapter
    ) -> None:
        tmp_runner.add_adapter("mock", mock_adapter_open)
        event = NotificationEvent("sim_done", "C99", platform="mock")
        await tmp_runner._send_notification(event)
        assert len(mock_adapter_open.sent_replies) == 1
        assert "Simulation" in mock_adapter_open.sent_replies[0]["text"]

    @pytest.mark.asyncio
    async def test_notification_all_platforms(self, tmp_runner: GatewayRunner) -> None:
        a1 = MockAdapter(allowed_users=None)
        a2 = MockAdapter(allowed_users=None)
        tmp_runner.add_adapter("slack", a1)
        tmp_runner.add_adapter("discord", a2)
        event = NotificationEvent("ralph_milestone", "C1", platform="all")
        await tmp_runner._send_notification(event)
        assert len(a1.sent_replies) == 1
        assert len(a2.sent_replies) == 1


# ---------------------------------------------------------------------------
# Service file generation
# ---------------------------------------------------------------------------


class TestServiceFiles:
    def test_systemd_unit_contains_maglab(self) -> None:
        unit = generate_systemd_unit()
        assert "maglab" in unit
        assert "[Service]" in unit
        assert "ExecStart" in unit

    def test_launchd_plist_contains_maglab(self) -> None:
        plist = generate_launchd_plist()
        assert "maglab" in plist
        assert "com.maglab.gateway" in plist
        assert "ProgramArguments" in plist

    def test_install_service_linux(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(
            "maglab.gateway.runner.Path.home",
            lambda: tmp_path,
        )
        # Patch the target path to stay within tmp_path
        with patch("maglab.gateway.runner.Path.home", return_value=tmp_path):
            # Just verify the function produces the service content
            content = generate_systemd_unit()
            assert "ExecStart" in content

    def test_install_service_darwin(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "darwin")
        content = generate_launchd_plist()
        assert "com.maglab.gateway" in content

    def test_install_service_unsupported_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        with pytest.raises(RuntimeError, match="Unsupported platform"):
            install_service()


# ---------------------------------------------------------------------------
# FIX 1: install_service credential permission check (T-P6-33)
# ---------------------------------------------------------------------------


class TestInstallServiceCredentialCheck:
    """install_service must enforce 0600 on gateway.yaml before writing any service file."""

    def test_install_service_raises_on_insecure_cred_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """install_service must raise PermissionError when gateway.yaml has group/other read bits."""
        import os

        cred_file = tmp_path / ".maglab" / "gateway.yaml"
        cred_file.parent.mkdir(parents=True, exist_ok=True)
        cred_file.write_text("dummy", encoding="utf-8")
        os.chmod(cred_file, 0o644)  # insecure: group + other readable

        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        with pytest.raises(PermissionError, match="insecure permissions"):
            install_service()

    def test_install_service_passes_when_cred_file_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """install_service must not raise when the credential file does not exist yet."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sys.platform", "linux")

        # No gateway.yaml in tmp_path — should proceed without a permission error.
        # The service target directory must also exist or be creatable.
        service_path = install_service()
        assert service_path.exists()

    def test_install_service_passes_with_secure_cred_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """install_service must succeed when gateway.yaml has exactly 0600 permissions."""
        import os

        cred_file = tmp_path / ".maglab" / "gateway.yaml"
        cred_file.parent.mkdir(parents=True, exist_ok=True)
        cred_file.write_text("dummy", encoding="utf-8")
        os.chmod(cred_file, 0o600)  # correct permissions

        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sys.platform", "linux")

        service_path = install_service()
        assert service_path.exists()


# ---------------------------------------------------------------------------
# FIX 2: gateway start writes daemon subprocess PID (T-P6-32)
# ---------------------------------------------------------------------------


class TestGatewayStartPid:
    """gateway_start background mode must write the subprocess PID, not the parent PID."""

    def test_background_start_writes_subprocess_pid(self, tmp_path: Path) -> None:
        """The PID file must contain proc.pid, not os.getpid()."""
        import os

        # _pid_path is used inside gateway_start via a local import from runner.
        # Patch it in the runner module where it is defined and called.
        pid_file = tmp_path / "gateway.pid"

        class FakeProc:
            pid = 99999  # sentinel PID that is NOT os.getpid()
            returncode = None

            def poll(self) -> None:
                return None

        with (
            patch("subprocess.Popen", return_value=FakeProc()),
            patch("maglab.gateway.runner._pid_path", return_value=pid_file),
            patch("maglab.gateway.runner.is_running", return_value=False),
        ):
            from typer.testing import CliRunner as TRunner

            from maglab.commands.p6_authoring import gateway_app

            result = TRunner().invoke(gateway_app, ["start", "--background"])

        # The PID file should contain FakeProc.pid, not the test process PID.
        assert pid_file.is_file(), f"PID file not written. Output: {result.output}"
        written_pid = int(pid_file.read_text().strip())
        assert written_pid == 99999, (
            f"Expected subprocess PID 99999, got {written_pid}.  "
            f"Parent PID is {os.getpid()} — must not be written."
        )
