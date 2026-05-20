"""Workspace helpers for global MagLab installs.

MagLab is installed as a global command, but it should operate on whatever
folder the user starts it from, like Codex-style project CLIs. This module
keeps that distinction explicit:

- global config/cache/data live in platformdirs locations;
- project files are read from the current working directory;
- optional project-local state lives under ``.maglab/`` in the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "maglab"
_IGNORED_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
}


@dataclass(frozen=True)
class WorkspaceInfo:
    """Resolved paths for the active MagLab workspace."""

    root: Path
    local_state_dir: Path
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    maglab_md: Path | None


def workspace_root(path: Path | None = None) -> Path:
    """Return the folder MagLab should treat as the current project."""
    return (path or Path.cwd()).resolve()


def workspace_info(path: Path | None = None) -> WorkspaceInfo:
    """Return workspace and global MagLab storage paths."""
    root = workspace_root(path)
    maglab_md = root / "MAGLAB.md"
    return WorkspaceInfo(
        root=root,
        local_state_dir=root / ".maglab",
        config_dir=Path(platformdirs.user_config_dir(APP_NAME)),
        data_dir=Path(platformdirs.user_data_dir(APP_NAME)),
        cache_dir=Path(platformdirs.user_cache_dir(APP_NAME)),
        maglab_md=maglab_md if maglab_md.is_file() else None,
    )


def iter_workspace_entries(root: Path | None = None, *, max_entries: int = 80) -> list[str]:
    """Return a compact, deterministic file tree for prompt/context display."""
    base = workspace_root(root)
    entries: list[str] = []
    for path in sorted(base.rglob("*"), key=lambda p: p.relative_to(base).as_posix()):
        rel = path.relative_to(base)
        if any(part in _IGNORED_NAMES for part in rel.parts):
            continue
        marker = "/" if path.is_dir() else ""
        entries.append(f"{rel.as_posix()}{marker}")
        if len(entries) >= max_entries:
            break
    return entries


def workspace_summary(root: Path | None = None, *, max_entries: int = 60) -> str:
    """Build a short system-prompt summary of the active workspace."""
    info = workspace_info(root)
    entries = iter_workspace_entries(info.root, max_entries=max_entries)
    lines = [
        f"Current workspace root: {info.root}",
        "MagLab should read and write project artifacts relative to this folder unless the user gives an absolute path.",
        f"Global config directory: {info.config_dir}",
        f"Global data directory: {info.data_dir}",
        f"Global cache directory: {info.cache_dir}",
    ]
    if info.maglab_md:
        lines.append(f"Workspace MAGLAB.md: {info.maglab_md}")
    if entries:
        lines.append("Visible workspace entries:")
        lines.extend(f"- {entry}" for entry in entries)
    else:
        lines.append("Visible workspace entries: none")
    return "\n".join(lines)


def init_workspace(root: Path | None = None) -> tuple[Path, bool]:
    """Create a local MAGLAB.md marker if it does not exist.

    Returns the marker path and whether it was newly created.
    """
    info = workspace_info(root)
    info.local_state_dir.mkdir(parents=True, exist_ok=True)
    marker = info.root / "MAGLAB.md"
    if marker.exists():
        return marker, False
    marker.write_text(
        "# MAGLAB.md\n\n"
        "Project-specific context for MagLab.\n\n"
        "- Research domain:\n"
        "- Active samples/materials:\n"
        "- Data folders:\n"
        "- Simulation folders:\n"
        "- Writing targets:\n",
        encoding="utf-8",
    )
    return marker, True
