"""Compatibility helpers for Typer's test runner."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import chdir, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


@contextmanager
def isolated_filesystem(runner: Any) -> Iterator[Path]:
    """Run a CLI test in an isolated cwd across Typer versions."""
    isolated = getattr(runner, "isolated_filesystem", None)
    if callable(isolated):
        with isolated():
            yield Path.cwd()
        return

    with TemporaryDirectory() as tmp:
        path = Path(tmp)
        with chdir(path):
            yield path
