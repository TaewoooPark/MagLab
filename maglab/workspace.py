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
    ".cache",
    ".coverage",
    ".DS_Store",
    ".venv",
    ".nox",
    ".tox",
    "venv",
    "env",
    "__pycache__",
    ".ipynb_checkpoints",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    "node_modules",
    "site-packages",
    "dist",
    "build",
    "coverage",
    "target",
}

_PROJECT_CONTEXT_NAMES = (
    "MAGLAB.md",
    "README.md",
    "README.ko.md",
    "pyproject.toml",
    "setup.cfg",
    "requirements.txt",
    "environment.yml",
    "package.json",
    "harness.manifest.json",
)

_PROJECT_CONTEXT_DIRS = (
    "plan",
    "docs",
    "manuals",
    "materials",
    "data",
    "figures",
    "scripts",
    "notebooks",
    "src",
    "maglab",
)


@dataclass(frozen=True)
class WorkspaceInfo:
    """Resolved paths for the active MagLab workspace."""

    root: Path
    local_state_dir: Path
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    maglab_md: Path | None


@dataclass(frozen=True)
class WorkspaceContext:
    """Bounded, deterministic project context visible to MagLab agents."""

    root: Path
    maglab_md: Path | None
    entries: list[str]
    key_paths: list[str]
    truncated: bool
    maglab_md_excerpt: str | None = None

    def to_prompt(self) -> str:
        """Return a compact prompt block for workspace-first agent behavior."""
        lines = [
            f"Current workspace root: {self.root}",
            "MagLab is operating in folder-scoped mode: read and write project artifacts relative to this folder unless the user gives an absolute path.",
            "Before answering project-specific questions, inspect MAGLAB.md and the relevant workspace files via deterministic workspace tools.",
        ]
        if self.maglab_md:
            lines.append(f"Workspace MAGLAB.md: {self.maglab_md}")
            if self.maglab_md_excerpt:
                lines.append("MAGLAB.md excerpt:")
                lines.append(self.maglab_md_excerpt)
        else:
            lines.append(
                "Workspace MAGLAB.md: not initialized; suggest `maglab workspace init` when project context is missing."
            )
        if self.key_paths:
            lines.append("Likely project context files/directories:")
            lines.extend(f"- {path}" for path in self.key_paths)
        if self.entries:
            label = "Visible workspace entries"
            if self.truncated:
                label += " (truncated)"
            lines.append(f"{label}:")
            lines.extend(f"- {entry}" for entry in self.entries)
        else:
            lines.append("Visible workspace entries: none")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation for CLI/tool surfaces."""
        return {
            "root": str(self.root),
            "maglab_md": str(self.maglab_md) if self.maglab_md else None,
            "maglab_md_excerpt": self.maglab_md_excerpt,
            "key_paths": list(self.key_paths),
            "entries": list(self.entries),
            "truncated": self.truncated,
        }


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


def _workspace_entries_with_status(
    root: Path | None = None, *, max_entries: int = 80
) -> tuple[list[str], bool]:
    """Return a compact tree and whether it was truncated.

    This deliberately walks with explicit directory pruning instead of
    ``Path.rglob`` so ignored heavy folders are never descended into.
    """
    base = workspace_root(root)
    entries: list[str] = []
    truncated = False
    stack: list[Path] = [base]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            continue
        dirs: list[Path] = []
        for path in children:
            if path.name in _IGNORED_NAMES:
                continue
            try:
                rel = path.relative_to(base)
            except ValueError:
                continue
            marker = "/" if path.is_dir() else ""
            entries.append(f"{rel.as_posix()}{marker}")
            if len(entries) >= max_entries:
                truncated = True
                return entries, truncated
            if path.is_dir():
                dirs.append(path)
        stack.extend(reversed(dirs))
    return entries, truncated


def iter_workspace_entries(root: Path | None = None, *, max_entries: int = 80) -> list[str]:
    """Return a compact, deterministic file tree for prompt/context display."""
    entries, _truncated = _workspace_entries_with_status(root, max_entries=max_entries)
    return entries


def _detect_key_paths(root: Path) -> list[str]:
    """Return likely high-signal project context files/directories."""
    paths: list[str] = []
    for name in _PROJECT_CONTEXT_NAMES:
        if (root / name).is_file():
            paths.append(name)
    for name in _PROJECT_CONTEXT_DIRS:
        if (root / name).is_dir():
            paths.append(f"{name}/")
    return paths


def _read_maglab_excerpt(path: Path | None, *, max_chars: int) -> str | None:
    """Read a bounded MAGLAB.md excerpt for deterministic startup context."""
    if path is None:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text.strip()
    return text[:max_chars].rstrip() + "\n[truncated]"


def workspace_context(
    root: Path | None = None,
    *,
    max_entries: int = 60,
    max_maglab_chars: int = 2_000,
) -> WorkspaceContext:
    """Collect bounded workspace context for first-turn prompts and tools."""
    info = workspace_info(root)
    entries, truncated = _workspace_entries_with_status(info.root, max_entries=max_entries)
    return WorkspaceContext(
        root=info.root,
        maglab_md=info.maglab_md,
        entries=entries,
        key_paths=_detect_key_paths(info.root),
        truncated=truncated,
        maglab_md_excerpt=_read_maglab_excerpt(info.maglab_md, max_chars=max_maglab_chars),
    )


def workspace_summary(root: Path | None = None, *, max_entries: int = 60) -> str:
    """Build a short system-prompt summary of the active workspace."""
    info = workspace_info(root)
    context = workspace_context(info.root, max_entries=max_entries)
    lines = [
        context.to_prompt(),
        f"Global config directory: {info.config_dir}",
        f"Global data directory: {info.data_dir}",
        f"Global cache directory: {info.cache_dir}",
    ]
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
