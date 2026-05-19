"""Abstract base adapter and shared message schema (§8, T-P6-28).

Every platform adapter must:
  1. Implement ``verify_request`` — signature check + allowlist guard.
  2. Implement ``parse_message`` — convert a raw platform event to ``UnifiedMessage``.
  3. Implement ``send_reply`` — deliver a reply (and optional attachments) back.

Security contract (§8)
-----------------------
- ``allowed_users``  : set of SHA-256 hashed user IDs that may interact.
- ``allowed_channels``: set of channel / chat identifiers that are permitted.
- Credentials must be stored in files with chmod 0600; the adapter checks this.
- Raw PII (user_id) is *never* stored — adapters receive and return hashed IDs.
"""

from __future__ import annotations

import abc
import hashlib
import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared message schema
# ---------------------------------------------------------------------------


@dataclass
class UnifiedMessage:
    """Platform-neutral message representation.

    Attributes
    ----------
    platform:
        Source platform — ``"slack"``, ``"telegram"``, or ``"discord"``.
    user_id_hash:
        SHA-256 hex digest of the platform-specific user identifier.
    channel:
        Channel or chat identifier.
    text:
        Message body text (stripped of platform-specific markup where possible).
    attachments:
        List of attachment descriptors (filenames, URLs, etc.).
    ts:
        Platform-provided or local Unix timestamp.
    raw:
        Original platform event dict (for debugging; not forwarded to the harness).
    """

    platform: str
    user_id_hash: str
    channel: str
    text: str
    attachments: list[Any] = field(default_factory=list)
    ts: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def hash_user_id(user_id: str) -> str:
    """Return the SHA-256 hex digest of *user_id* (§8 PII hashing)."""
    return hashlib.sha256(user_id.encode()).hexdigest()


def check_credential_permissions(path: Path) -> None:
    """Raise ``PermissionError`` if *path* is readable by group or others.

    Enforces the §8 requirement that credential files must have chmod 0600.
    No-op on Windows (``stat`` mode bits are not enforced there).

    Parameters
    ----------
    path:
        Path to the credential file.
    """
    if os.name == "nt":
        return  # Windows: skip
    if not path.exists():
        return
    mode = path.stat().st_mode
    if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
        raise PermissionError(
            f"Credential file {path} has insecure permissions "
            f"({oct(stat.S_IMODE(mode))}). "
            "Set to 0600: chmod 0600 " + str(path)
        )


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------


class BaseAdapter(abc.ABC):
    """Abstract base class for platform-specific adapters (§8, T-P6-28).

    Parameters
    ----------
    allowed_users:
        Set of *SHA-256 hashed* user IDs permitted to interact.  Pass an
        empty set to allow all users (insecure — for testing only).
    allowed_channels:
        Set of channel / chat IDs permitted to receive messages.  Pass an
        empty set to allow all channels.
    """

    def __init__(
        self,
        allowed_users: set[str] | None = None,
        allowed_channels: set[str] | None = None,
    ) -> None:
        # None means "not enforced" (useful in tests); empty set blocks everyone.
        self._allowed_users: set[str] | None = allowed_users
        self._allowed_channels: set[str] | None = allowed_channels

    # ------------------------------------------------------------------
    # Internal allowlist helpers
    # ------------------------------------------------------------------

    def _user_allowed(self, user_id_hash: str) -> bool:
        """Return True iff the hashed user ID passes the allowlist check."""
        if self._allowed_users is None:
            return True  # no restriction
        return user_id_hash in self._allowed_users

    def _channel_allowed(self, channel: str) -> bool:
        """Return True iff the channel passes the allowlist check."""
        if self._allowed_channels is None:
            return True  # no restriction
        return channel in self._allowed_channels

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement these
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def verify_request(self, raw: dict[str, Any]) -> bool:
        """Verify the authenticity and authorisation of a raw platform event.

        Must check both the platform-level signature/token AND the allowlists.
        Returns ``False`` for any unknown or unauthorized event — never raises.

        Parameters
        ----------
        raw:
            Raw platform event dictionary.

        Returns
        -------
        bool
            ``True`` if the request is authentic and authorised.
        """

    @abc.abstractmethod
    def parse_message(self, raw: dict[str, Any]) -> UnifiedMessage:
        """Convert a raw platform event into a ``UnifiedMessage``.

        Parameters
        ----------
        raw:
            Raw platform event dictionary (already verified by ``verify_request``).

        Returns
        -------
        UnifiedMessage
        """

    @abc.abstractmethod
    async def send_reply(
        self,
        channel: str,
        text: str,
        attachments: list[Any] | None = None,
        *,
        thread_ts: str | None = None,
    ) -> None:
        """Deliver a reply to the given channel.

        Parameters
        ----------
        channel:
            Target channel / chat identifier.
        text:
            Reply text.
        attachments:
            Optional list of files or URLs to attach.
        thread_ts:
            Optional thread timestamp (Slack-specific; ignored by other adapters).
        """
