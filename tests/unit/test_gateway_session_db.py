"""tests/unit/test_gateway_session_db.py — SessionDB unit tests."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest

from maglab.gateway.adapters.base import hash_user_id
from maglab.gateway.session_db import SessionDB, _hash_user_id

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Generator[SessionDB, None, None]:
    """Return a fresh in-memory SessionDB backed by a temp file."""
    db = SessionDB(db_path=tmp_path / "test_gateway.db")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# session creation and retrieval
# ---------------------------------------------------------------------------


class TestGetOrCreateSession:
    def test_creates_new_session(self, tmp_db: SessionDB) -> None:
        session = tmp_db.get_or_create_session("slack", hash_user_id("U12345"), "C9999")
        assert session.id != ""
        assert session.platform == "slack"
        assert session.channel_id == "C9999"

    def test_idempotent_same_id(self, tmp_db: SessionDB) -> None:
        """Two calls with the same user return the same session id."""
        uid_hash = hash_user_id("U12345")
        s1 = tmp_db.get_or_create_session("slack", uid_hash)
        s2 = tmp_db.get_or_create_session("slack", uid_hash)
        assert s1.id == s2.id

    def test_pii_hashed(self, tmp_db: SessionDB) -> None:
        """The stored hash equals SHA-256(user_id) — exactly once, not double-hashed."""
        raw_uid = "123456789"
        expected_hash = hash_user_id(raw_uid)
        session = tmp_db.get_or_create_session("telegram", expected_hash)
        assert session.user_id_hash == expected_hash
        assert raw_uid not in session.user_id_hash
        # Confirm stored value is SHA-256 of the raw ID, not SHA-256 of the hash
        assert session.user_id_hash == _hash_user_id(raw_uid)

    def test_different_platforms_different_sessions(self, tmp_db: SessionDB) -> None:
        uid_hash = hash_user_id("U12345")
        s1 = tmp_db.get_or_create_session("slack", uid_hash)
        s2 = tmp_db.get_or_create_session("telegram", uid_hash)
        assert s1.id != s2.id

    def test_last_active_updated(self, tmp_db: SessionDB) -> None:
        uid_hash = hash_user_id("DUSER1")
        s1 = tmp_db.get_or_create_session("discord", uid_hash)
        # Small sleep to get a different timestamp
        time.sleep(0.01)
        s2 = tmp_db.get_or_create_session("discord", uid_hash)
        assert s2.last_active >= s1.last_active

    def test_get_session_by_id(self, tmp_db: SessionDB) -> None:
        created = tmp_db.get_or_create_session("slack", hash_user_id("U999"))
        fetched = tmp_db.get_session(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_session_missing_returns_none(self, tmp_db: SessionDB) -> None:
        assert tmp_db.get_session("nonexistent-uuid") is None


# ---------------------------------------------------------------------------
# Message logging
# ---------------------------------------------------------------------------


class TestLogMessage:
    def test_log_user_message(self, tmp_db: SessionDB) -> None:
        session = tmp_db.get_or_create_session("slack", hash_user_id("U1"))
        mid = tmp_db.log_message(session.id, "user", "Hello MagLab")
        assert mid != ""

    def test_log_assistant_message(self, tmp_db: SessionDB) -> None:
        session = tmp_db.get_or_create_session("slack", hash_user_id("U2"))
        mid = tmp_db.log_message(session.id, "assistant", "Running simulation…")
        assert mid != ""

    def test_raw_content_not_stored(self, tmp_db: SessionDB) -> None:
        """The raw message content must not be stored in the DB."""
        raw_text = "my secret hypothesis"
        session = tmp_db.get_or_create_session("slack", hash_user_id("U3"))
        tmp_db.log_message(session.id, "user", raw_text)
        # Directly query the DB to check
        conn = tmp_db._get_conn()
        rows = conn.execute("SELECT content_hash FROM messages").fetchall()
        for row in rows:
            assert raw_text not in row["content_hash"]


# ---------------------------------------------------------------------------
# Regression test for F2: no double-hashing of user_id
# ---------------------------------------------------------------------------


class TestNoDoubleHashing:
    """F2 regression: get_or_create_session must store SHA-256(user_id) exactly once.

    Before the fix, the runner passed msg.user_id_hash (already SHA-256'd) to
    get_or_create_session, which then hashed it again, storing
    SHA-256(SHA-256(user_id)).  The stored value must be SHA-256(user_id).
    """

    def test_stored_hash_equals_sha256_of_raw_id(self, tmp_db: SessionDB) -> None:
        """The user_id_hash stored in the DB is SHA-256(raw_uid), not a double-hash."""
        raw_uid = "slack-user-U98765"
        pre_hashed = hash_user_id(raw_uid)  # simulates what the adapter does
        session = tmp_db.get_or_create_session("slack", pre_hashed)

        expected = _hash_user_id(raw_uid)  # SHA-256 of the raw ID
        double_hashed = _hash_user_id(pre_hashed)  # SHA-256 of the hash (the bug)

        assert session.user_id_hash == expected, "Stored hash is a double-hash (bug F2 not fixed)."
        assert session.user_id_hash != double_hashed, (
            "Stored hash must NOT be SHA-256(SHA-256(uid)) — that is the double-hash bug."
        )

    def test_runner_path_stores_correct_hash(self, tmp_path: Path) -> None:
        """End-to-end check: runner passes msg.user_id_hash → DB stores SHA-256(raw_uid)."""
        db = SessionDB(db_path=tmp_path / "f2_check.db")
        raw_uid = "telegram-user-12345"
        # Simulate what adapter.parse_message produces
        adapter_hash = hash_user_id(raw_uid)
        session = db.get_or_create_session("telegram", adapter_hash)
        db.close()

        assert session.user_id_hash == _hash_user_id(raw_uid), (
            "End-to-end: stored hash must equal SHA-256(raw_uid)."
        )


class TestOneSessionPerUser:
    """Concurrent messages from one user must not split their history.

    ``get_or_create_session`` did SELECT then INSERT, and nothing in the schema
    prevented two concurrent messages — which the async adapters routinely
    produce — from both observing "no session" and both inserting. The user then
    had two session rows and their messages were divided between them.
    """

    def test_concurrent_lookups_yield_one_session(self, tmp_path: Path) -> None:
        db = tmp_path / "sessions.db"
        SessionDB(db).close()

        ids: list[str] = []
        errors: list[BaseException] = []
        barrier = threading.Barrier(6)

        def _lookup() -> None:
            try:
                store = SessionDB(db)
                try:
                    barrier.wait(timeout=10)
                    ids.append(store.get_or_create_session("slack", "user-hash", "C1").id)
                finally:
                    store.close()
            except BaseException as exc:  # noqa: BLE001 - re-asserted below
                errors.append(exc)

        threads = [threading.Thread(target=_lookup) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"concurrent session lookup raised: {errors!r}"
        assert len(set(ids)) == 1, f"the same user was given {len(set(ids))} sessions"

    def test_schema_rejects_a_duplicate_pair(self, tmp_path: Path) -> None:
        db = tmp_path / "sessions.db"
        store = SessionDB(db)
        store.get_or_create_session("slack", "user-hash", "C1")
        conn = store._get_conn()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
                ("other-id", "slack", "user-hash", "C1", time.time(), time.time()),
            )
        store.close()

    def test_repeat_lookup_preserves_identity_and_creation_time(self, tmp_path: Path) -> None:
        store = SessionDB(tmp_path / "sessions.db")
        first = store.get_or_create_session("slack", "user-hash", "C1")
        time.sleep(0.01)
        second = store.get_or_create_session("slack", "user-hash", "C-other")

        assert second.id == first.id, "the upsert minted a new session"
        assert second.created_at == first.created_at
        assert second.channel_id == "C1", "the original channel must not be overwritten"
        assert second.last_active >= first.last_active
        store.close()

    def test_different_users_and_platforms_stay_separate(self, tmp_path: Path) -> None:
        store = SessionDB(tmp_path / "sessions.db")
        a = store.get_or_create_session("slack", "user-a", "C1")
        b = store.get_or_create_session("slack", "user-b", "C1")
        c = store.get_or_create_session("telegram", "user-a", "C1")

        assert len({a.id, b.id, c.id}) == 3
        store.close()

    def test_existing_duplicates_are_merged_without_losing_messages(self, tmp_path: Path) -> None:
        """Databases created before the unique index may already hold duplicates."""
        db = tmp_path / "sessions.db"
        store = SessionDB(db)
        store.get_or_create_session("slack", "seed", "C0")
        conn = store._get_conn()
        conn.execute("DROP INDEX IF EXISTS idx_sessions_platform_user_unique")
        older, newer = time.time() - 100, time.time() - 50
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
            ("keep-me", "slack", "dup", "C1", older, older),
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
            ("drop-me", "slack", "dup", "C1", newer, newer),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?)", ("m1", "drop-me", "user", "hash", newer)
        )
        conn.commit()
        store.close()

        reopened = SessionDB(db)
        conn = reopened._get_conn()
        remaining = [r[0] for r in conn.execute("SELECT id FROM sessions WHERE user_id_hash='dup'")]
        message_owner = conn.execute("SELECT session_id FROM messages WHERE id='m1'").fetchone()[0]

        assert remaining == ["keep-me"], "the earliest session should survive"
        assert message_owner == "keep-me", "the orphaned message was not re-pointed"
        reopened.close()
