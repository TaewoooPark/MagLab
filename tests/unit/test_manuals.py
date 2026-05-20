"""Tests for installed bilingual manual discovery."""

from __future__ import annotations

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
