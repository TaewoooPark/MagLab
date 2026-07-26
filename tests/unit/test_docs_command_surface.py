"""Runnable README examples must name commands that actually exist.

The READMEs are the project's front page and the place users copy from. When
they document a command that was never built, the first thing a new user runs
fails with ``No such command`` — the failure mode that hid a missing
``prov lineage`` and an entire unimplemented ``maglab harness`` surface.

Only fenced shell blocks are checked: those are the copy-paste examples. Prose
may legitimately discuss a command by name (including, deliberately, to say it
does not exist yet).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from typer.main import get_command

from maglab.cli import app

REPO_ROOT = Path(__file__).resolve().parents[2]
README_FILES = ["README.md", "README.ko.md", "MAGLAB.md"]

_SH_BLOCK_RE = re.compile(r"```(?:sh|bash|shell|console)\n(.*?)```", re.DOTALL)
_INVOCATION_RE = re.compile(r"^\s*(?:\$\s*)?(?:[\w./-]*\bmaglab)\s+(.*)$", re.MULTILINE)


def _command_tree() -> dict[str, set[str]]:
    root = get_command(app)
    return {
        name: set(getattr(sub, "commands", {}) or {})
        for name, sub in getattr(root, "commands", {}).items()
    }


def _shell_invocations(text: str) -> list[str]:
    lines: list[str] = []
    for block in _SH_BLOCK_RE.findall(text):
        lines.extend(m.group(1).strip() for m in _INVOCATION_RE.finditer(block))
    return lines


def _documented_commands(text: str) -> set[tuple[str, str | None]]:
    """Return (group, subcommand) pairs from runnable shell examples."""
    found: set[tuple[str, str | None]] = set()
    for invocation in _shell_invocations(text):
        tokens = [t for t in invocation.split() if not t.startswith("-")]
        if not tokens:
            continue
        group = tokens[0]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", group):
            continue
        sub = tokens[1] if len(tokens) > 1 and re.fullmatch(r"[a-z][a-z0-9-]*", tokens[1]) else None
        found.add((group, sub))
    return found


@pytest.mark.parametrize("doc_name", README_FILES)
def test_documented_commands_exist(doc_name: str) -> None:
    doc = REPO_ROOT / doc_name
    if not doc.is_file():
        pytest.skip(f"{doc_name} not present")

    tree = _command_tree()
    missing: list[str] = []
    documented = sorted(
        _documented_commands(doc.read_text(encoding="utf-8")), key=lambda p: (p[0], p[1] or "")
    )
    for group, sub in documented:
        if group not in tree:
            missing.append(f"maglab {group}")
        elif sub is not None and tree[group] and sub not in tree[group]:
            missing.append(f"maglab {group} {sub}")

    assert missing == [], f"{doc_name} documents commands that do not exist: {sorted(set(missing))}"


@pytest.mark.parametrize("doc_name", README_FILES)
def test_documented_install_extras_exist(doc_name: str) -> None:
    doc = REPO_ROOT / doc_name
    if not doc.is_file():
        pytest.skip(f"{doc_name} not present")

    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        declared = set(tomllib.load(fh)["project"]["optional-dependencies"])

    documented = set(re.findall(r'"\.\[([a-z0-9,\s-]+)\]"', doc.read_text(encoding="utf-8")))
    referenced = {part.strip() for group in documented for part in group.split(",") if part.strip()}

    missing = sorted(referenced - declared)
    assert missing == [], f"{doc_name} tells users to install extras that do not exist: {missing}"


def test_repo_root_readmes_are_checked() -> None:
    """Guard the guard: the parametrisation must actually be finding the files."""
    present = [name for name in README_FILES if (REPO_ROOT / name).is_file()]
    assert "README.md" in present, "README.md not found — the check above would silently skip"
