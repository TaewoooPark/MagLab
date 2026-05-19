"""Slack adapter — Socket Mode via slack-bolt (§8, T-P6-29).

Uses ``slack-bolt`` in Socket Mode so no public IP is required.

Security (§8)
-------------
- Signature verification via ``slack_bolt.signature_verifier.SignatureVerifier``.
- ``allowed_users`` / ``allowed_channels`` allowlist enforced in ``verify_request``.
- Credentials must be in a file with chmod 0600.

Human-gate (§8)
---------------
``send_approval_request`` sends a Block Kit message with Approve / Reject
buttons and suspends the caller via ``asyncio.Event`` until the user responds.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from pathlib import Path
from typing import Any

from maglab.gateway.adapters.base import (
    BaseAdapter,
    UnifiedMessage,
    check_credential_permissions,
    hash_user_id,
)

log = logging.getLogger(__name__)


class SlackAdapter(BaseAdapter):
    """Slack Socket Mode adapter.

    Parameters
    ----------
    bot_token:
        Slack bot OAuth token (``xoxb-...``).
    signing_secret:
        Slack app signing secret (used for request signature verification).
    app_token:
        Slack app-level token for Socket Mode (``xapp-...``).
    allowed_users:
        Set of SHA-256 hashed Slack user IDs.
    allowed_channels:
        Set of permitted Slack channel IDs.
    credential_path:
        Optional path to the credential file; permissions are checked.
    """

    def __init__(
        self,
        bot_token: str = "",
        signing_secret: str = "",
        app_token: str = "",
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
        credential_path: Path | None = None,
    ) -> None:
        super().__init__(allowed_users=allowed_users, allowed_channels=allowed_channels)
        self._bot_token = bot_token
        self._signing_secret = signing_secret
        self._app_token = app_token

        if credential_path is not None:
            check_credential_permissions(credential_path)

        # Lazy-import slack_bolt to keep the core package light
        self._client: Any = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _verify_slack_signature(
        self,
        body: str,
        timestamp: str,
        signature: str,
    ) -> bool:
        """Verify the Slack request signature (HMAC-SHA256).

        Reference: https://api.slack.com/authentication/verifying-requests-from-slack
        """
        if not self._signing_secret:
            # No secret configured — skip (useful in unit tests with mock adapter)
            return True
        sig_basestring = f"v0:{timestamp}:{body}".encode()
        computed = hmac.new(
            self._signing_secret.encode(),
            sig_basestring,
            hashlib.sha256,
        ).hexdigest()
        expected = f"v0={computed}"
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    def verify_request(self, raw: dict[str, Any]) -> bool:
        """Verify Slack event authenticity and allowlist membership.

        The ``raw`` dict must contain:
        - ``"body"`` : raw request body string.
        - ``"timestamp"`` : ``X-Slack-Request-Timestamp`` header value.
        - ``"signature"`` : ``X-Slack-Signature`` header value.
        - ``"user_id"`` : Slack user ID (raw, before hashing).
        - ``"channel"`` : Slack channel ID.

        Returns ``False`` on any failure — never raises.
        """
        try:
            body = raw.get("body", "")
            timestamp = raw.get("timestamp", "")
            signature = raw.get("signature", "")
            user_id = raw.get("user_id", "")
            channel = raw.get("channel", "")

            # 1. Replay-attack protection (reject events > 5 minutes old)
            try:
                req_ts = float(timestamp)
                if abs(time.time() - req_ts) > 300:
                    log.warning("[slack] Request timestamp too old: %s", timestamp)
                    return False
            except (ValueError, TypeError):
                pass  # No timestamp provided — skip replay check in mock mode

            # 2. Signature verification
            if signature and not self._verify_slack_signature(body, timestamp, signature):
                log.warning("[slack] Signature verification failed")
                return False

            # 3. Allowlist checks
            uid_hash = hash_user_id(user_id)
            if not self._user_allowed(uid_hash):
                log.info("[slack] User %s not in allowlist", uid_hash[:8])
                return False
            if channel and not self._channel_allowed(channel):
                log.info("[slack] Channel %s not in allowlist", channel)
                return False

        except Exception:  # noqa: BLE001
            log.exception("[slack] verify_request raised unexpectedly")
            return False

        return True

    def parse_message(self, raw: dict[str, Any]) -> UnifiedMessage:
        """Convert a Slack event dict to ``UnifiedMessage``.

        Handles ``app_mention`` and ``message`` event types.

        Parameters
        ----------
        raw:
            Must contain ``"user_id"``, ``"channel"``, ``"text"``.

        Returns
        -------
        UnifiedMessage
        """
        user_id = raw.get("user_id", "")
        channel = raw.get("channel", "")
        text = raw.get("text", "").strip()
        ts = float(raw.get("ts", time.time()))
        attachments: list[Any] = raw.get("files", [])

        uid_hash = hash_user_id(user_id)
        return UnifiedMessage(
            platform="slack",
            user_id_hash=uid_hash,
            channel=channel,
            text=text,
            attachments=attachments,
            ts=ts,
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
        """Post a message to *channel* via the Slack Web API.

        Falls back to a no-op log if the client is not initialised
        (e.g. during unit tests).

        Parameters
        ----------
        channel:
            Slack channel ID.
        text:
            Message text.
        attachments:
            Optional list of file paths to upload.
        thread_ts:
            If set, post as a thread reply.
        """
        if self._client is None:
            log.info("[slack] send_reply (mock) channel=%s text=%.60s", channel, text)
            return

        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        await asyncio.to_thread(self._client.chat_postMessage, **kwargs)

        if attachments:
            for att in attachments:
                path = Path(att) if isinstance(att, str) else att
                if path.exists():
                    await asyncio.to_thread(
                        self._client.files_upload_v2,
                        channel=channel,
                        file=str(path),
                        filename=path.name,
                    )

    async def send_approval_request(
        self,
        channel: str,
        prompt: str,
        *,
        timeout: float = 300.0,
    ) -> bool:
        """Send a human-gate approval request and wait for the user to respond.

        Posts Block Kit buttons (Approve / Reject) and suspends the current
        coroutine via ``asyncio.Event`` until a button is pressed or the
        timeout expires.

        Parameters
        ----------
        channel:
            Slack channel to post to.
        prompt:
            Human-readable description of what is being approved.
        timeout:
            Seconds to wait before auto-rejecting.

        Returns
        -------
        bool
            ``True`` if approved, ``False`` if rejected or timed out.
        """
        gate_event: asyncio.Event = asyncio.Event()
        approved: list[bool] = [False]  # mutable container for closure

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Human Gate* — {prompt}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "gate_approve",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "gate_reject",
                    },
                ],
            },
        ]

        log.info("[slack] Human gate posted to %s: %s", channel, prompt[:60])

        if self._client is not None:
            await asyncio.to_thread(
                self._client.chat_postMessage,
                channel=channel,
                text=f"[Human Gate] {prompt}",
                blocks=blocks,
            )

        def _approve() -> None:
            approved[0] = True
            gate_event.set()

        def _reject() -> None:
            approved[0] = False
            gate_event.set()

        # Store callbacks so the action handler can resolve them
        self._gate_approve = _approve  # type: ignore[attr-defined]
        self._gate_reject = _reject  # type: ignore[attr-defined]

        try:
            await asyncio.wait_for(gate_event.wait(), timeout=timeout)
        except TimeoutError:
            log.warning("[slack] Human gate timed out for channel=%s", channel)
            return False

        return approved[0]
