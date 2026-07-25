"""maglab.core.atomic tests — durable writes for research state files."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from maglab.core.atomic import atomic_write_bytes, atomic_write_text


def test_write_text_creates_file_and_parents(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "state.json"
    returned = atomic_write_text(target, '{"ok": true}')

    assert returned == target
    assert target.read_text(encoding="utf-8") == '{"ok": true}'


def test_write_bytes_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    payload = bytes(range(256))
    atomic_write_bytes(target, payload)
    assert target.read_bytes() == payload


def test_overwrite_replaces_content_entirely(tmp_path: Path) -> None:
    target = tmp_path / "state.txt"
    atomic_write_text(target, "a much longer previous value")
    atomic_write_text(target, "short")
    assert target.read_text(encoding="utf-8") == "short", "stale tail bytes survived"


def test_failed_write_preserves_previous_content(tmp_path: Path) -> None:
    """The whole point: an interrupted write must not truncate the old file."""
    target = tmp_path / "state.txt"
    atomic_write_text(target, "original")

    with patch("os.replace", side_effect=OSError("boom")), pytest.raises(OSError):
        atomic_write_text(target, "replacement")

    assert target.read_text(encoding="utf-8") == "original"


def test_failed_write_removes_scratch_file(tmp_path: Path) -> None:
    target = tmp_path / "state.txt"
    atomic_write_text(target, "original")

    with patch("os.replace", side_effect=OSError("boom")), pytest.raises(OSError):
        atomic_write_text(target, "replacement")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.txt"], "scratch file leaked"


def test_keyboard_interrupt_also_cleans_up(tmp_path: Path) -> None:
    """Ctrl-C is the interruption this guards against — it must not leak a temp file."""
    target = tmp_path / "state.txt"
    atomic_write_text(target, "original")

    with patch("os.replace", side_effect=KeyboardInterrupt), pytest.raises(KeyboardInterrupt):
        atomic_write_text(target, "replacement")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.txt"]
    assert target.read_text(encoding="utf-8") == "original"


def test_successful_write_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "state.txt"
    for i in range(5):
        atomic_write_text(target, f"value {i}")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.txt"]


def test_temp_file_lands_in_target_directory(tmp_path: Path) -> None:
    """The scratch file must be a sibling — os.replace is not atomic across filesystems."""
    target = tmp_path / "state.txt"
    seen: list[str] = []

    real_replace = os.replace

    def _record(src: str, dst: str) -> None:
        seen.append(str(Path(src).parent))
        real_replace(src, dst)

    with patch("os.replace", side_effect=_record):
        atomic_write_text(target, "x")

    assert seen == [str(tmp_path)]


def test_non_utf8_encoding_supported(tmp_path: Path) -> None:
    target = tmp_path / "state.txt"
    atomic_write_text(target, "café", encoding="latin-1")
    assert target.read_text(encoding="latin-1") == "café"


def test_fsync_can_be_disabled(tmp_path: Path) -> None:
    target = tmp_path / "state.txt"
    with patch("os.fsync") as fake_fsync:
        atomic_write_text(target, "x", fsync=False)
    fake_fsync.assert_not_called()
    assert target.read_text(encoding="utf-8") == "x"
