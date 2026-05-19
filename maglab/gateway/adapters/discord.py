"""Discord adapter — discord.py Gateway + slash commands (§8, T-P6-31).

Security (§8)
-------------
- ``allowed_users`` / ``allowed_channels`` allowlist enforced in ``verify_request``.
- ``discord.ui.Button`` components implement the human gate (Tier 2/3 approvals).

Notes
-----
- This module does *not* start the Discord client itself; ``runner.py``
  manages the event-loop integration.
- ``verify_request`` operates on a plain dict (not a ``discord.Message``
  object) so that it remains testable without a live Discord connection.
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


class DiscordAdapter(BaseAdapter):
    """Discord Gateway adapter.

    Parameters
    ----------
    bot_token:
        Discord bot token.
    allowed_users:
        Set of SHA-256 hashed Discord user IDs (numeric snowflakes as strings).
    allowed_channels:
        Set of permitted Discord channel IDs (snowflakes as strings).
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
        self._client: Any = None

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    def verify_request(self, raw: dict[str, Any]) -> bool:
        """Verify Discord event allowlist membership.

        The ``raw`` dict must contain:
        - ``"user_id"``   : Discord user ID (snowflake as string, before hashing).
        - ``"channel_id"``: Discord channel ID (snowflake as string).

        Returns ``False`` on any failure — never raises.
        """
        try:
            user_id = str(raw.get("user_id", ""))
            channel_id = str(raw.get("channel_id", ""))

            if not user_id:
                log.info("[discord] Missing user_id in raw event")
                return False

            uid_hash = hash_user_id(user_id)

            if not self._user_allowed(uid_hash):
                log.info("[discord] User %s not in allowlist", uid_hash[:8])
                return False

            if self._allowed_channels is not None and (
                not channel_id or not self._channel_allowed(channel_id)
            ):
                log.info("[discord] Channel %r not in allowlist (or missing)", channel_id)
                return False

        except Exception:  # noqa: BLE001
            log.exception("[discord] verify_request raised unexpectedly")
            return False

        return True

    def parse_message(self, raw: dict[str, Any]) -> UnifiedMessage:
        """Convert a Discord event dict to ``UnifiedMessage``.

        Parameters
        ----------
        raw:
            Must contain ``"user_id"``, ``"channel_id"``, ``"content"``.

        Returns
        -------
        UnifiedMessage
        """
        user_id = str(raw.get("user_id", ""))
        channel_id = str(raw.get("channel_id", ""))
        text = raw.get("content", "").strip()
        ts = float(raw.get("ts", time.time()))
        attachments: list[Any] = [a.get("url", a) for a in raw.get("attachments", [])]

        uid_hash = hash_user_id(user_id)
        return UnifiedMessage(
            platform="discord",
            user_id_hash=uid_hash,
            channel=channel_id,
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
        thread_ts: str | None = None,  # Not used in Discord; accepted for interface compat.
    ) -> None:
        """Send a message to *channel* (a Discord channel ID / snowflake string).

        Falls back to a no-op log if the client is not initialised.

        Parameters
        ----------
        channel:
            Discord channel ID (snowflake as string).
        text:
            Message content.
        attachments:
            Optional list of file paths to upload.
        thread_ts:
            Unused; present for interface compatibility.
        """
        if self._client is None:
            log.info("[discord] send_reply (mock) channel=%s text=%.60s", channel, text)
            return

        try:
            disc_channel = await self._client.fetch_channel(int(channel))
        except Exception:  # noqa: BLE001
            log.exception("[discord] Failed to fetch channel %s", channel)
            return

        import discord

        files: list[discord.File] = []
        if attachments:
            for att in attachments:
                path = Path(att) if isinstance(att, str) else att
                if path.exists():
                    files.append(discord.File(str(path)))

        if files:
            await disc_channel.send(content=text, files=files)
        else:
            await disc_channel.send(content=text)

    async def send_approval_request(
        self,
        channel: str,
        prompt: str,
        *,
        timeout: float = 300.0,
    ) -> bool:
        """Send a human-gate button view and wait for response.

        Posts ``discord.ui.Button`` components and suspends the caller via
        ``asyncio.Event`` until a button is pressed or the timeout expires.

        Parameters
        ----------
        channel:
            Discord channel ID.
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

        log.info("[discord] Human gate posted to %s: %s", channel, prompt[:60])

        if self._client is not None:
            try:
                import discord

                class GateView(discord.ui.View):
                    def __init__(self) -> None:
                        super().__init__(timeout=timeout)

                    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
                    async def approve_btn(
                        self, interaction: discord.Interaction, button: discord.ui.Button
                    ) -> None:
                        approved[0] = True
                        gate_event.set()
                        await interaction.response.send_message("Approved.", ephemeral=True)

                    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
                    async def reject_btn(
                        self, interaction: discord.Interaction, button: discord.ui.Button
                    ) -> None:
                        approved[0] = False
                        gate_event.set()
                        await interaction.response.send_message("Rejected.", ephemeral=True)

                disc_channel = await self._client.fetch_channel(int(channel))
                await disc_channel.send(content=f"[Human Gate] {prompt}", view=GateView())
            except Exception:  # noqa: BLE001
                log.exception("[discord] Failed to send approval request")

        try:
            await asyncio.wait_for(gate_event.wait(), timeout=timeout)
        except TimeoutError:
            log.warning("[discord] Human gate timed out for channel=%s", channel)
            return False

        return approved[0]
