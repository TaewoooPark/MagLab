"""SQLite session store for the messaging gateway (§8, T-P6-27).

Database lives at ``~/.maglab/gateway.db``.

Tables
------
sessions:
    id TEXT PK, platform TEXT, user_id_hash TEXT, channel_id TEXT,
    created_at REAL, last_active REAL

messages:
    id TEXT PK, session_id TEXT FK, role TEXT, content_hash TEXT, ts REAL

Security
--------
- user_id is stored only as SHA-256 hex digest — raw PII is never persisted.
- File permissions are checked / enforced at ``open()`` time on Unix systems.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import NamedTuple

import platformdirs

log = logging.getLogger(__name__)

_APP = "maglab"
_DB_FILENAME = "gateway.db"

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Session(NamedTuple):
    """Gateway session record.

    Attributes
    ----------
    id:
        Unique session UUID (text).
    platform:
        Originating platform — ``"slack"``, ``"telegram"``, or ``"discord"``.
    user_id_hash:
        SHA-256 hex digest of the platform-specific user identifier.
    channel_id:
        Channel or chat identifier (stored as-is; not treated as PII).
    created_at:
        Unix timestamp of first interaction.
    last_active:
        Unix timestamp of the most recent interaction.
    """

    id: str
    platform: str
    user_id_hash: str
    channel_id: str
    created_at: float
    last_active: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_user_id(user_id: str) -> str:
    """Return the SHA-256 hex digest of *user_id*.

    The raw identifier is never stored — only the digest (§8 PII hashing).
    """
    return hashlib.sha256(user_id.encode()).hexdigest()


def _db_path() -> Path:
    """Return the path to ``gateway.db`` (creates parent directory if needed)."""
    data_dir = Path(platformdirs.user_data_dir(_APP))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _DB_FILENAME


# ---------------------------------------------------------------------------
# SessionDB
# ---------------------------------------------------------------------------


class SessionDB:
    """Thin wrapper around the gateway SQLite database.

    Parameters
    ----------
    db_path:
        Explicit path to the SQLite file.  Defaults to ``~/.maglab/gateway.db``
        (resolved via ``platformdirs``).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _db_path()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return (and lazily open) the SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Create tables if they do not yet exist."""
        conn = self._conn
        assert conn is not None  # internal — always called after open
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                platform    TEXT NOT NULL,
                user_id_hash TEXT NOT NULL,
                channel_id  TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL,
                last_active REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL REFERENCES sessions(id),
                role        TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                ts          REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_platform_user
                ON sessions (platform, user_id_hash);
            """
        )
        conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def get_or_create_session(
        self,
        platform: str,
        user_id_hash: str,
        channel_id: str = "",
    ) -> Session:
        """Return an existing session or create a new one.

        The caller is responsible for hashing the raw user identifier before
        calling this method — the adapter's ``parse_message`` already produces
        a ``SHA-256(user_id)`` hex digest in ``UnifiedMessage.user_id_hash``.
        Passing the pre-hashed value here ensures the stored hash is exactly
        ``SHA-256(original_user_id)``, not a double-hash.

        Parameters
        ----------
        platform:
            Originating platform (``"slack"``, ``"telegram"``, ``"discord"``).
        user_id_hash:
            SHA-256 hex digest of the platform-specific user identifier (as
            produced by ``hash_user_id`` / ``UnifiedMessage.user_id_hash``).
            The raw user ID must never be passed here.
        channel_id:
            Channel or chat identifier (stored as-is).

        Returns
        -------
        Session
            Either the existing session or a freshly created one.
        """
        conn = self._get_conn()
        uid_hash = user_id_hash
        now = time.time()

        row = conn.execute(
            "SELECT * FROM sessions WHERE platform=? AND user_id_hash=?",
            (platform, uid_hash),
        ).fetchone()

        if row is not None:
            # Update last_active timestamp
            conn.execute(
                "UPDATE sessions SET last_active=? WHERE id=?",
                (now, row["id"]),
            )
            conn.commit()
            return Session(
                id=row["id"],
                platform=row["platform"],
                user_id_hash=row["user_id_hash"],
                channel_id=row["channel_id"],
                created_at=row["created_at"],
                last_active=now,
            )

        # Create new session
        sid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
            (sid, platform, uid_hash, channel_id, now, now),
        )
        conn.commit()
        log.debug("[gateway] New session created: %s platform=%s", sid, platform)
        return Session(
            id=sid,
            platform=platform,
            user_id_hash=uid_hash,
            channel_id=channel_id,
            created_at=now,
            last_active=now,
        )

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by its UUID, or ``None`` if not found."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            platform=row["platform"],
            user_id_hash=row["user_id_hash"],
            channel_id=row["channel_id"],
            created_at=row["created_at"],
            last_active=row["last_active"],
        )

    # ------------------------------------------------------------------
    # Message logging
    # ------------------------------------------------------------------

    def log_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> str:
        """Append a message record to the *messages* table.

        The full message content is stored only as a SHA-256 hash — the raw
        text is NOT persisted (PII / privacy compliance).

        Parameters
        ----------
        session_id:
            Parent session UUID.
        role:
            ``"user"`` or ``"assistant"``.
        content:
            Raw message text (hashed before storage).

        Returns
        -------
        str
            New message UUID.
        """
        conn = self._get_conn()
        mid = str(uuid.uuid4())
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        ts = time.time()
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?)",
            (mid, session_id, role, content_hash, ts),
        )
        conn.commit()
        return mid
