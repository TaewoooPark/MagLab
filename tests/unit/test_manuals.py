"""Tests for installed bilingual manual discovery."""

from __future__ import annotations

from pathlib import Path

from maglab.manuals import available_languages, list_manuals, resolve_manual


def test_manuals_include_english_and_korean() -> None:
    langs = set(available_languages())
    assert {"en", "ko"} <= langs
    assert len(list_manuals("en")) >= 8
    assert len(list_manuals("ko")) >= 8


def test_resolve_manual_accepts_aliases() -> None:
    entry = resolve_manual("fig", lang="en")
    assert entry.topic == "figures"
    assert entry.path.name == "figures.md"

    quickstart = resolve_manual("quickstart", lang="ko")
    assert quickstart.topic == "quickstart-operations"
    assert quickstart.path.name == "quickstart-operations.md"


def test_installed_manuals_are_not_shadowed_by_workspace_docs(tmp_path: Path, monkeypatch) -> None:
    workspace_manuals = tmp_path / "docs" / "manuals" / "en"
    workspace_manuals.mkdir(parents=True)
    (workspace_manuals / "index.md").write_text("# Workspace Manual\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    entry = resolve_manual("figures", lang="en")

    assert entry.path.name == "figures.md"
    assert "Workspace Manual" not in entry.path.read_text(encoding="utf-8")
