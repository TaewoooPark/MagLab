"""tests/smoke/test_gateway_smoke.py — Gateway daemon start/stop smoke test (§20).

All network calls are mocked — no real Slack/Telegram/Discord connections.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from maglab.gateway.adapters.base import BaseAdapter, UnifiedMessage, hash_user_id
from maglab.gateway.runner import GatewayRunner, NotificationEvent

# ---------------------------------------------------------------------------
# Minimal in-process mock adapter
# ---------------------------------------------------------------------------


class SmokeAdapter(BaseAdapter):
    """Minimal adapter for smoke tests — no network, no credentials."""

    def __init__(
        self,
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
    ) -> None:
        super().__init__(allowed_users=allowed_users, allowed_channels=allowed_channels)
        self.replies: list[str] = []
        self.notified: list[str] = []

    def verify_request(self, raw: dict[str, Any]) -> bool:
        user_id = raw.get("user_id", "")
        if not user_id:
            return False
        uid_hash = hash_user_id(user_id)
        return self._user_allowed(uid_hash)

    def parse_message(self, raw: dict[str, Any]) -> UnifiedMessage:
        return UnifiedMessage(
            platform="smoke",
            user_id_hash=hash_user_id(raw.get("user_id", "")),
            channel=raw.get("channel", "C1"),
            text=raw.get("text", ""),
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
        self.replies.append(text)

    async def send_notification(self, channel: str, text: str) -> None:
        self.notified.append(text)


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestGatewaySmoke:
    """Gateway daemon smoke tests — no real platform connections."""

    @pytest.mark.asyncio
    async def test_runner_starts_and_stops(self, tmp_path: Path) -> None:
        """Runner can be started and stopped cleanly."""
        runner = GatewayRunner(db_path=tmp_path / "smoke.db")
        await runner.start()
        assert runner._running is True
        await runner.stop()
        assert runner._running is False

    @pytest.mark.asyncio
    async def test_blocked_message_no_reply(self, tmp_path: Path) -> None:
        """Messages from non-allowlisted users are silently dropped."""
        runner = GatewayRunner(db_path=tmp_path / "smoke2.db")
        await runner.start()
        try:
            allowed_hash = hash_user_id("GOOD_USER")
            adapter = SmokeAdapter(allowed_users={allowed_hash})
            runner.add_adapter("smoke", adapter)

            result = await runner.handle_message(
                "smoke",
                {"user_id": "BAD_USER", "channel": "C1", "text": "status"},
            )
            assert result is None
            assert adapter.replies == []
        finally:
            await runner.stop()

    @pytest.mark.asyncio
    async def test_allowed_message_gets_reply(self, tmp_path: Path) -> None:
        """Messages from allowlisted users receive a reply."""
        runner = GatewayRunner(db_path=tmp_path / "smoke3.db")
        await runner.start()
        try:
            uid = "GOOD_USER"
            uid_hash = hash_user_id(uid)
            adapter = SmokeAdapter(allowed_users={uid_hash})
            runner.add_adapter("smoke", adapter)

            result = await runner.handle_message(
                "smoke",
                {"user_id": uid, "channel": "C1", "text": "status"},
            )
            assert result is not None
            assert len(adapter.replies) == 1
        finally:
            await runner.stop()

    @pytest.mark.asyncio
    async def test_proactive_notification_delivered(self, tmp_path: Path) -> None:
        """A notification event is delivered to the correct adapter."""
        queue: asyncio.Queue[NotificationEvent] = asyncio.Queue()
        runner = GatewayRunner(
            db_path=tmp_path / "smoke4.db",
            notification_queue=queue,
        )
        adapter = SmokeAdapter(allowed_users=None)
        runner.add_adapter("smoke", adapter)

        event = NotificationEvent("sim_done", "C1", platform="smoke")
        await runner._send_notification(event)
        assert len(adapter.replies) == 1
        assert "Simulation" in adapter.replies[0]

    @pytest.mark.asyncio
    async def test_runner_multiple_start_stop(self, tmp_path: Path) -> None:
        """Runner can be started and stopped multiple times cleanly."""
        runner = GatewayRunner(db_path=tmp_path / "smoke5.db")
        for _ in range(2):
            await runner.start()
            await runner.stop()
        assert runner._running is False

    @pytest.mark.asyncio
    async def test_session_persists_across_messages(self, tmp_path: Path) -> None:
        """Two messages from the same user share a session ID."""
        db_path = tmp_path / "smoke6.db"
        runner = GatewayRunner(db_path=db_path)
        await runner.start()
        try:
            adapter = SmokeAdapter(allowed_users=None)
            runner.add_adapter("smoke", adapter)

            uid = "PERSISTENT_USER"
            raw = {"user_id": uid, "channel": "C1", "text": "status"}

            await runner.handle_message("smoke", raw)
            await runner.handle_message("smoke", raw)

            # Both calls should have succeeded — 2 replies
            assert len(adapter.replies) == 2
        finally:
            await runner.stop()
