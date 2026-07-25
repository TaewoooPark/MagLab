"""Atomic file writes for durable MagLab state.

MagLab persists research state — configuration, provenance records, research
pool entries, long-term memories — as plain files.  A naive
``Path.write_text()`` truncates the target first, so an interrupted write
(Ctrl-C, crash, full disk, killed batch job) leaves a *partially written* file
behind.  For state that is read back on the next startup, that turns a transient
failure into a permanently broken workspace.

The helpers here write to a temporary file in the same directory and then
``os.replace()`` it over the target, which is atomic on POSIX and on Windows.
A reader therefore observes either the complete old file or the complete new
one — never a truncated mixture.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["atomic_write_bytes", "atomic_write_text"]


def atomic_write_bytes(path: Path, data: bytes, *, fsync: bool = True) -> Path:
    """Atomically write *data* to *path*.

    The parent directory is created when missing.  The payload is written to a
    temporary sibling file, flushed (and ``fsync``-ed unless disabled), then
    renamed over *path*.

    Args:
        path: Destination file.
        data: Payload to persist.
        fsync: Flush the file to disk before renaming.  Keep enabled for state
            that must survive a power loss; disable only for bulk throwaway
            output where durability does not matter.

    Returns:
        The destination path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            if fsync:
                os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Never leave the scratch file behind on failure — including on
        # KeyboardInterrupt, which is exactly the interruption this guards.
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
) -> Path:
    """Atomically write *text* to *path*.  See :func:`atomic_write_bytes`."""
    return atomic_write_bytes(Path(path), text.encode(encoding), fsync=fsync)
