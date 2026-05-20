"""Runtime helpers for quiet headless figure rendering."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import platformdirs


def _first_writable_dir(candidates: list[Path]) -> Path:
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError:
            continue
    fallback = Path(tempfile.gettempdir()) / "maglab-cache"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def ensure_matplotlib_runtime_env() -> None:
    """Set writable cache env vars before matplotlib/fontconfig import."""
    cache_root = _first_writable_dir(
        [
            Path(platformdirs.user_cache_dir("maglab")),
            Path.cwd() / ".maglab" / "cache",
            Path(tempfile.gettempdir()) / "maglab-cache",
        ]
    )
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root / "xdg"))
    Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)
