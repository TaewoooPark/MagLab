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
import shlex
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


# ---------------------------------------------------------------------------
# Flags, not just command names
# ---------------------------------------------------------------------------

MANUAL_FILES = sorted(
    str(path.relative_to(REPO_ROOT)) for path in (REPO_ROOT / "docs" / "manuals").rglob("*.md")
)


def _command_node(parts: list[str]):
    """Resolve a command path to its click node, or None."""
    node = get_command(app)
    for part in parts:
        subs = getattr(node, "commands", {}) or {}
        if part not in subs:
            return None
        node = subs[part]
    return node


def _valid_options(node) -> set[str]:
    options: set[str] = set()
    for param in node.params:
        options |= set(param.opts) | set(param.secondary_opts)
    return options


def _documented_invocations(text: str) -> list[tuple[list[str], list[str]]]:
    """Return (command path, flags) for every runnable maglab line."""
    found: list[tuple[list[str], list[str]]] = []
    for invocation in _shell_invocations(text):
        # shlex, not split(): a quoted argument may legitimately contain
        # something that looks like a flag, e.g.
        # `maglab mcp add arxiv "npx -y @scope/server"`.
        try:
            tokens = shlex.split(invocation)
        except ValueError:
            continue  # unbalanced quotes in a prose snippet
        path: list[str] = []
        flags: list[str] = []
        for token in tokens:
            if token.startswith("-"):
                flags.append(token.split("=")[0])
            elif not flags and len(path) < 3 and re.fullmatch(r"[a-z][a-z0-9-]*", token):
                path.append(token)
        if path:
            found.append((path, flags))
    return found


@pytest.mark.parametrize("doc_name", README_FILES + MANUAL_FILES)
def test_documented_flags_exist(doc_name: str) -> None:
    """A documented flag that does not exist is worse than an undocumented one.

    `instr scpi --model` was real but ignored; the manuals separately referenced
    `--local-max-turns`, `--task-json`, `--execute` and `fit --json`, none of
    which exist. Checking command names alone missed every one of them.
    """
    doc = REPO_ROOT / doc_name
    if not doc.is_file():
        pytest.skip(f"{doc_name} not present")

    unknown: list[str] = []
    for path, flags in _documented_invocations(doc.read_text(encoding="utf-8")):
        node = _command_node(path)
        # Fall back to the parent when the last token was an argument, not a
        # subcommand (e.g. `maglab manual orchestration`).
        while node is None and len(path) > 1:
            path = path[:-1]
            node = _command_node(path)
        if node is None:
            continue  # command existence is covered by test_documented_commands_exist
        valid = _valid_options(node)
        for flag in flags:
            if flag == "--" or re.fullmatch(r"-\d+", flag):
                continue
            if flag not in valid:
                unknown.append(f"maglab {' '.join(path)} {flag}")

    assert unknown == [], f"{doc_name} documents flags that do not exist: {sorted(set(unknown))}"


def test_the_flag_check_actually_inspects_something() -> None:
    """Guard the guard: a parser that finds nothing would pass vacuously."""
    total = 0
    for doc_name in README_FILES + MANUAL_FILES:
        doc = REPO_ROOT / doc_name
        if doc.is_file():
            total += sum(
                len(f) for _p, f in _documented_invocations(doc.read_text(encoding="utf-8"))
            )
    assert total > 50, f"only {total} documented flags found — the extractor is broken"
