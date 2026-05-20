"""tests/unit/test_gateway_adapters.py — Adapter unit tests (all network mocked)."""

from __future__ import annotations

import time

import pytest

from maglab.gateway.adapters.base import BaseAdapter, UnifiedMessage, hash_user_id
from maglab.gateway.adapters.discord import DiscordAdapter
from maglab.gateway.adapters.slack import SlackAdapter
from maglab.gateway.adapters.telegram import TelegramAdapter

# ---------------------------------------------------------------------------
# BaseAdapter contract
# ---------------------------------------------------------------------------


class TestBaseAdapterContract:
    """Verify that BaseAdapter.verify_request raises NotImplementedError."""

    def test_abstract_verify_request(self) -> None:
        """verify_request must be implemented by subclass."""
        with pytest.raises(TypeError):
            BaseAdapter()  # type: ignore[abstract]

    def test_hash_user_id_is_hex(self) -> None:
        h = hash_user_id("user123")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_user_id_deterministic(self) -> None:
        assert hash_user_id("same") == hash_user_id("same")

    def test_hash_user_id_different_inputs(self) -> None:
        assert hash_user_id("user1") != hash_user_id("user2")


# ---------------------------------------------------------------------------
# SlackAdapter
# ---------------------------------------------------------------------------


class TestSlackAdapter:
    def _make_adapter(
        self,
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
    ) -> SlackAdapter:
        return SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="",
            app_token="xapp-test",
            allowed_users=allowed_users,
            allowed_channels=allowed_channels,
        )

    # verify_request --------------------------------------------------------

    def test_verify_allowed_user(self) -> None:
        uid = "U12345"
        uid_hash = hash_user_id(uid)
        adapter = self._make_adapter(allowed_users={uid_hash})
        raw = {"user_id": uid, "channel": "C99", "body": "", "timestamp": "", "signature": ""}
        assert adapter.verify_request(raw) is True

    def test_verify_blocked_user(self) -> None:
        adapter = self._make_adapter(allowed_users={hash_user_id("U_ALLOWED")})
        raw = {
            "user_id": "U_OTHER",
            "channel": "C99",
            "body": "",
            "timestamp": "",
            "signature": "",
        }
        assert adapter.verify_request(raw) is False

    def test_verify_empty_allowlist_blocks_all(self) -> None:
        adapter = self._make_adapter(allowed_users=set())
        raw = {"user_id": "U12345", "channel": "C99", "body": "", "timestamp": "", "signature": ""}
        assert adapter.verify_request(raw) is False

    def test_verify_channel_blocked(self) -> None:
        uid = "U12345"
        uid_hash = hash_user_id(uid)
        adapter = self._make_adapter(
            allowed_users={uid_hash},
            allowed_channels={"C_ALLOWED"},
        )
        raw = {
            "user_id": uid,
            "channel": "C_OTHER",
            "body": "",
            "timestamp": "",
            "signature": "",
        }
        assert adapter.verify_request(raw) is False

    def test_verify_no_allowlists(self) -> None:
        """None allowed_users means no restriction."""
        adapter = self._make_adapter(allowed_users=None, allowed_channels=None)
        raw = {
            "user_id": "U_ANYONE",
            "channel": "C_ANY",
            "body": "",
            "timestamp": "",
            "signature": "",
        }
        assert adapter.verify_request(raw) is True

    def test_verify_stale_timestamp_rejected(self) -> None:
        uid = "U12345"
        uid_hash = hash_user_id(uid)
        adapter = self._make_adapter(allowed_users={uid_hash})
        old_ts = str(time.time() - 400)  # 400 seconds ago
        raw = {
            "user_id": uid,
            "channel": "C99",
            "body": "test",
            "timestamp": old_ts,
            "signature": "v0=badhash",
        }
        assert adapter.verify_request(raw) is False

    # parse_message ---------------------------------------------------------

    def test_parse_message_fields(self) -> None:
        adapter = self._make_adapter()
        raw = {
            "user_id": "U12345",
            "channel": "C99",
            "text": "  hello maglab  ",
            "ts": "1700000000.0",
        }
        msg = adapter.parse_message(raw)
        assert isinstance(msg, UnifiedMessage)
        assert msg.platform == "slack"
        assert msg.text == "hello maglab"
        assert msg.channel == "C99"
        assert msg.user_id_hash == hash_user_id("U12345")

    # send_reply ------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_send_reply_mock_no_error(self) -> None:
        adapter = self._make_adapter()
        # No client set — should log and not raise
        await adapter.send_reply("C99", "test reply")

    # --- Regression test for F3 (silent HMAC bypass) ---

    def test_empty_signing_secret_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """F3 regression: when signing_secret is empty, a WARNING must be logged.

        Before the fix the silent return-True was completely invisible in operator
        logs.  Every request that bypasses HMAC verification must now produce at
        least one log record at WARNING level mentioning the skipped verification.
        """
        import logging

        adapter = SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="",  # empty → bypass path
            app_token="xapp-test",
        )
        raw = {
            "user_id": "U_ANYONE",
            "channel": "C_ANY",
            "body": "",
            "timestamp": "",
            "signature": "",
        }
        with caplog.at_level(logging.WARNING):
            result = adapter.verify_request(raw)

        assert result is True, "Empty signing_secret must still return True (backward-compat)"
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, (
            "F3: No WARNING was emitted when HMAC verification was skipped. "
            "Misconfigured deployments would be completely silent."
        )
        combined = " ".join(r.message for r in warning_records).lower()
        # The warning must mention that signature verification was skipped/disabled
        assert any(
            kw in combined
            for kw in ("skip", "signing_secret", "hmac", "verification", "not configured")
        ), f"F3: WARNING message does not describe the skipped verification. Got: {combined!r}"

    def test_configured_secret_rejects_missing_signature(self) -> None:
        """R2 regression: with signing_secret configured, a request carrying no
        signature header must be REJECTED, not silently accepted.

        The Round-1 fix used ``elif signature and not _verify(...)`` — it only
        rejected when a signature was present, so a forged request with no
        signature header slipped past HMAC verification entirely.
        """
        adapter = SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="a-real-secret",  # HMAC verification is active
            app_token="xapp-test",
        )
        raw = {
            "user_id": "U_ANYONE",
            "channel": "C_ANY",
            "body": "{}",
            "timestamp": "",
            "signature": "",  # no signature header
        }
        assert adapter.verify_request(raw) is False, (
            "A request with no signature must be rejected when signing_secret is configured."
        )


# ---------------------------------------------------------------------------
# TelegramAdapter
# ---------------------------------------------------------------------------


class TestTelegramAdapter:
    def _make_adapter(
        self,
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
    ) -> TelegramAdapter:
        return TelegramAdapter(
            bot_token="1234:ABCD",
            allowed_users=allowed_users,
            allowed_channels=allowed_channels,
        )

    def test_verify_allowed_user(self) -> None:
        uid = "123456789"
        uid_hash = hash_user_id(uid)
        adapter = self._make_adapter(allowed_users={uid_hash})
        raw = {"user_id": uid, "chat_id": "999"}
        assert adapter.verify_request(raw) is True

    def test_verify_blocked_user(self) -> None:
        adapter = self._make_adapter(allowed_users={hash_user_id("999")})
        raw = {"user_id": "111", "chat_id": "999"}
        assert adapter.verify_request(raw) is False

    def test_verify_missing_user_id(self) -> None:
        adapter = self._make_adapter(allowed_users=None)
        raw = {"chat_id": "999"}  # no user_id
        assert adapter.verify_request(raw) is False

    def test_parse_message(self) -> None:
        adapter = self._make_adapter()
        raw = {"user_id": "123", "chat_id": "456", "text": "run sim", "date": 1700000000}
        msg = adapter.parse_message(raw)
        assert msg.platform == "telegram"
        assert msg.channel == "456"
        assert msg.text == "run sim"

    @pytest.mark.asyncio
    async def test_send_reply_no_client(self) -> None:
        adapter = self._make_adapter()
        await adapter.send_reply("999", "hello")  # should not raise


# ---------------------------------------------------------------------------
# DiscordAdapter
# ---------------------------------------------------------------------------


class TestDiscordAdapter:
    def _make_adapter(
        self,
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
    ) -> DiscordAdapter:
        return DiscordAdapter(
            bot_token="disc-bot-token",
            allowed_users=allowed_users,
            allowed_channels=allowed_channels,
        )

    def test_verify_allowed_user(self) -> None:
        uid = "811111111111111111"
        uid_hash = hash_user_id(uid)
        adapter = self._make_adapter(allowed_users={uid_hash})
        raw = {"user_id": uid, "channel_id": "999111111111111111"}
        assert adapter.verify_request(raw) is True

    def test_verify_blocked_channel(self) -> None:
        uid = "811111111111111111"
        uid_hash = hash_user_id(uid)
        adapter = self._make_adapter(
            allowed_users={uid_hash},
            allowed_channels={"C_GOOD"},
        )
        raw = {"user_id": uid, "channel_id": "C_BAD"}
        assert adapter.verify_request(raw) is False

    def test_verify_missing_user(self) -> None:
        adapter = self._make_adapter(allowed_users=None)
        raw = {"channel_id": "999"}
        assert adapter.verify_request(raw) is False

    def test_parse_message(self) -> None:
        adapter = self._make_adapter()
        raw = {
            "user_id": "811111111111111111",
            "channel_id": "999111111111111111",
            "content": "/maglab status",
        }
        msg = adapter.parse_message(raw)
        assert msg.platform == "discord"
        assert msg.text == "/maglab status"

    @pytest.mark.asyncio
    async def test_send_reply_no_client(self) -> None:
        adapter = self._make_adapter()
        await adapter.send_reply("999111111111111111", "pong")


# ---------------------------------------------------------------------------
# Regression: Finding 2 — empty channel bypasses allowed_channels allowlist
# ---------------------------------------------------------------------------


class TestEmptyChannelAllowlistBypass:
    """Regression tests for Finding 2 (MEDIUM): all three adapters allowed an
    empty/absent channel field to bypass the allowed_channels check.

    When allowed_channels is configured (non-None), a request with no channel
    must be REJECTED, not silently accepted.
    """

    # Slack -----------------------------------------------------------------

    def test_slack_empty_channel_rejected_when_allowlist_set(self) -> None:
        """Slack: empty channel string must be rejected when allowed_channels is set."""
        uid = "U_GOOD"
        uid_hash = hash_user_id(uid)
        adapter = SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="",
            app_token="xapp-test",
            allowed_users={uid_hash},
            allowed_channels={"C_ALLOWED"},
        )
        raw = {
            "user_id": uid,
            "channel": "",  # empty — was previously skipping the check
            "body": "",
            "timestamp": "",
            "signature": "",
        }
        assert adapter.verify_request(raw) is False, (
            "Finding 2 regression: Slack empty channel bypassed allowed_channels allowlist."
        )

    def test_slack_absent_channel_rejected_when_allowlist_set(self) -> None:
        """Slack: missing channel key must be rejected when allowed_channels is set."""
        uid = "U_GOOD"
        uid_hash = hash_user_id(uid)
        adapter = SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="",
            app_token="xapp-test",
            allowed_users={uid_hash},
            allowed_channels={"C_ALLOWED"},
        )
        raw = {
            "user_id": uid,
            # "channel" key entirely absent
            "body": "",
            "timestamp": "",
            "signature": "",
        }
        assert adapter.verify_request(raw) is False, (
            "Finding 2 regression: Slack absent channel bypassed allowed_channels allowlist."
        )

    def test_slack_empty_channel_allowed_when_no_allowlist(self) -> None:
        """Slack: empty channel is fine when allowed_channels is None (no restriction)."""
        uid = "U_GOOD"
        uid_hash = hash_user_id(uid)
        adapter = SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="",
            app_token="xapp-test",
            allowed_users={uid_hash},
            allowed_channels=None,  # no channel restriction
        )
        raw = {
            "user_id": uid,
            "channel": "",
            "body": "",
            "timestamp": "",
            "signature": "",
        }
        assert adapter.verify_request(raw) is True

    # Telegram --------------------------------------------------------------

    def test_telegram_empty_chat_rejected_when_allowlist_set(self) -> None:
        """Telegram: empty chat_id must be rejected when allowed_channels is set."""
        uid = "123456789"
        uid_hash = hash_user_id(uid)
        adapter = TelegramAdapter(
            bot_token="1234:ABCD",
            allowed_users={uid_hash},
            allowed_channels={"CHAT_ALLOWED"},
        )
        raw = {
            "user_id": uid,
            "chat_id": "",  # empty
        }
        assert adapter.verify_request(raw) is False, (
            "Finding 2 regression: Telegram empty chat_id bypassed allowed_channels allowlist."
        )

    def test_telegram_absent_chat_rejected_when_allowlist_set(self) -> None:
        """Telegram: absent chat_id must be rejected when allowed_channels is set."""
        uid = "123456789"
        uid_hash = hash_user_id(uid)
        adapter = TelegramAdapter(
            bot_token="1234:ABCD",
            allowed_users={uid_hash},
            allowed_channels={"CHAT_ALLOWED"},
        )
        raw = {
            "user_id": uid,
            # "chat_id" key absent
        }
        assert adapter.verify_request(raw) is False, (
            "Finding 2 regression: Telegram absent chat_id bypassed allowed_channels allowlist."
        )

    def test_telegram_empty_chat_allowed_when_no_allowlist(self) -> None:
        """Telegram: empty chat_id is fine when allowed_channels is None."""
        uid = "123456789"
        uid_hash = hash_user_id(uid)
        adapter = TelegramAdapter(
            bot_token="1234:ABCD",
            allowed_users={uid_hash},
            allowed_channels=None,
        )
        raw = {"user_id": uid, "chat_id": ""}
        assert adapter.verify_request(raw) is True

    # Discord ---------------------------------------------------------------

    def test_discord_empty_channel_rejected_when_allowlist_set(self) -> None:
        """Discord: empty channel_id must be rejected when allowed_channels is set."""
        uid = "811111111111111111"
        uid_hash = hash_user_id(uid)
        adapter = DiscordAdapter(
            bot_token="disc-bot-token",
            allowed_users={uid_hash},
            allowed_channels={"CHAN_GOOD"},
        )
        raw = {
            "user_id": uid,
            "channel_id": "",  # empty
        }
        assert adapter.verify_request(raw) is False, (
            "Finding 2 regression: Discord empty channel_id bypassed allowed_channels allowlist."
        )

    def test_discord_absent_channel_rejected_when_allowlist_set(self) -> None:
        """Discord: absent channel_id must be rejected when allowed_channels is set."""
        uid = "811111111111111111"
        uid_hash = hash_user_id(uid)
        adapter = DiscordAdapter(
            bot_token="disc-bot-token",
            allowed_users={uid_hash},
            allowed_channels={"CHAN_GOOD"},
        )
        raw = {
            "user_id": uid,
            # "channel_id" key absent
        }
        assert adapter.verify_request(raw) is False, (
            "Finding 2 regression: Discord absent channel_id bypassed allowed_channels allowlist."
        )

    def test_discord_empty_channel_allowed_when_no_allowlist(self) -> None:
        """Discord: empty channel_id is fine when allowed_channels is None."""
        uid = "811111111111111111"
        uid_hash = hash_user_id(uid)
        adapter = DiscordAdapter(
            bot_token="disc-bot-token",
            allowed_users={uid_hash},
            allowed_channels=None,
        )
        raw = {"user_id": uid, "channel_id": ""}
        assert adapter.verify_request(raw) is True


# ---------------------------------------------------------------------------
# Regression: Finding 4 — Slack replay check silently skipped on bad timestamp
# ---------------------------------------------------------------------------


class TestSlackReplayTimestampBypass:
    """Regression tests for Finding 4 (LOW/defence-in-depth): when signing_secret
    is configured, an unparseable timestamp must cause request rejection rather than
    silently skipping the 5-minute replay window.
    """

    def test_unparseable_timestamp_rejected_with_secret(self) -> None:
        """When signing_secret is set, a non-numeric timestamp must be rejected."""
        uid = "U_GOOD"
        uid_hash = hash_user_id(uid)
        adapter = SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="real-signing-secret",
            app_token="xapp-test",
            allowed_users={uid_hash},
        )
        raw = {
            "user_id": uid,
            "channel": "C_ANY",
            "body": "payload",
            "timestamp": "not-a-number",  # unparseable
            "signature": "",
        }
        assert adapter.verify_request(raw) is False, (
            "Finding 4 regression: non-numeric timestamp was not rejected when "
            "signing_secret is configured — replay-attack protection was bypassed."
        )

    def test_empty_timestamp_skipped_without_secret(self) -> None:
        """When signing_secret is empty, an unparseable timestamp is tolerated
        (no secret means replay protection was already absent).
        The request may still succeed if the user is allowed.
        """
        uid = "U_GOOD"
        uid_hash = hash_user_id(uid)
        adapter = SlackAdapter(
            bot_token="xoxb-test",
            signing_secret="",  # no secret — replay protection absent
            app_token="xapp-test",
            allowed_users={uid_hash},
        )
        raw = {
            "user_id": uid,
            "channel": "C_ANY",
            "body": "",
            "timestamp": "",  # unparseable but secret is not configured
            "signature": "",
        }
        # Must not crash; return value depends on HMAC-skip path (True in this config)
        result = adapter.verify_request(raw)
        assert isinstance(result, bool)
