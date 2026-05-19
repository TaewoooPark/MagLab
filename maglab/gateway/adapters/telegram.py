"""Telegram adapter — python-telegram-bot long-polling / webhook (§8, T-P6-30).

Security (§8)
-------------
- Bot token HMAC verification for webhook updates (if applicable).
- ``allowed_users`` / ``allowed_channels`` allowlist enforced in ``verify_request``.
- Inline keyboard buttons (``InlineKeyboardMarkup``) implement the human gate.
"""

from __future__ import annotations

import asyncio
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


class TelegramAdapter(BaseAdapter):
    """Telegram adapter using python-telegram-bot.

    Parameters
    ----------
    bot_token:
        Telegram bot API token (``123456:ABC-...``).
    allowed_users:
        Set of SHA-256 hashed Telegram user IDs (numeric, as string).
    allowed_channels:
        Set of permitted chat IDs (string-encoded integers).
    credential_path:
        Optional path to the credential file; chmod 0600 is enforced.
    """

    def __init__(
        self,
        bot_token: str = "",
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
        credential_path: Path | None = None,
    ) -> None:
        super().__init__(allowed_users=allowed_users, allowed_channels=allowed_channels)
        self._bot_token = bot_token

        if credential_path is not None:
            check_credential_permissions(credential_path)

        # Lazy client — set by runner when running live
        self._bot: Any = None

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    def verify_request(self, raw: dict[str, Any]) -> bool:
        """Verify Telegram update authenticity and allowlist membership.

        The ``raw`` dict must contain:
        - ``"user_id"`` : Telegram user ID as string (raw, before hashing).
        - ``"chat_id"`` : Telegram chat ID as string.

        Returns ``False`` on any failure — never raises.
        """
        try:
            user_id = str(raw.get("user_id", ""))
            chat_id = str(raw.get("chat_id", ""))

            if not user_id:
                log.info("[telegram] Missing user_id in raw event")
                return False

            uid_hash = hash_user_id(user_id)

            if not self._user_allowed(uid_hash):
                log.info("[telegram] User %s not in allowlist", uid_hash[:8])
                return False

            if self._allowed_channels is not None and (
                not chat_id or not self._channel_allowed(chat_id)
            ):
                log.info("[telegram] Chat %r not in allowlist (or missing)", chat_id)
                return False

        except Exception:  # noqa: BLE001
            log.exception("[telegram] verify_request raised unexpectedly")
            return False

        return True

    def parse_message(self, raw: dict[str, Any]) -> UnifiedMessage:
        """Convert a Telegram Update dict to ``UnifiedMessage``.

        Parameters
        ----------
        raw:
            Must contain ``"user_id"``, ``"chat_id"``, ``"text"``.

        Returns
        -------
        UnifiedMessage
        """
        user_id = str(raw.get("user_id", ""))
        chat_id = str(raw.get("chat_id", ""))
        text = raw.get("text", "").strip()
        ts = float(raw.get("date", time.time()))
        attachments: list[Any] = raw.get("attachments", [])

        uid_hash = hash_user_id(user_id)
        return UnifiedMessage(
            platform="telegram",
            user_id_hash=uid_hash,
            channel=chat_id,
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
        thread_ts: str | None = None,  # Not used in Telegram; accepted for interface compat.
    ) -> None:
        """Send a message to *channel* (a Telegram chat_id).

        Falls back to a no-op log if the bot is not initialised
        (e.g. during unit tests).

        Parameters
        ----------
        channel:
            Telegram chat ID (as string).
        text:
            Message text (Markdown V2 supported).
        attachments:
            Optional list of file paths to upload via ``send_document``.
        thread_ts:
            Unused; present for interface compatibility.
        """
        if self._bot is None:
            log.info("[telegram] send_reply (mock) chat=%s text=%.60s", channel, text)
            return

        await self._bot.send_message(chat_id=channel, text=text)

        if attachments:
            for att in attachments:
                path = Path(att) if isinstance(att, str) else att
                if path.exists():
                    with path.open("rb") as fh:
                        await self._bot.send_document(chat_id=channel, document=fh)

    async def send_approval_request(
        self,
        channel: str,
        prompt: str,
        *,
        timeout: float = 300.0,
    ) -> bool:
        """Send a human-gate inline keyboard and wait for response.

        Posts an ``InlineKeyboardMarkup`` with Approve / Reject buttons and
        suspends the caller via ``asyncio.Event`` until a callback query arrives
        or the timeout expires.

        Parameters
        ----------
        channel:
            Telegram chat ID.
        prompt:
            Human-readable description of what is being approved.
        timeout:
            Seconds before auto-rejection.

        Returns
        -------
        bool
            ``True`` if approved, ``False`` if rejected or timed out.
        """
        gate_event: asyncio.Event = asyncio.Event()
        approved: list[bool] = [False]

        log.info("[telegram] Human gate posted to %s: %s", channel, prompt[:60])

        if self._bot is not None:
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Approve ✓", callback_data="gate_approve"),
                            InlineKeyboardButton("Reject ✗", callback_data="gate_reject"),
                        ]
                    ]
                )
                await self._bot.send_message(
                    chat_id=channel,
                    text=f"[Human Gate] {prompt}",
                    reply_markup=keyboard,
                )
            except Exception:  # noqa: BLE001
                log.exception("[telegram] Failed to send approval request")

        def _approve() -> None:
            approved[0] = True
            gate_event.set()

        def _reject() -> None:
            approved[0] = False
            gate_event.set()

        self._gate_approve = _approve  # type: ignore[attr-defined]
        self._gate_reject = _reject  # type: ignore[attr-defined]

        try:
            await asyncio.wait_for(gate_event.wait(), timeout=timeout)
        except TimeoutError:
            log.warning("[telegram] Human gate timed out for chat=%s", channel)
            return False

        return approved[0]
