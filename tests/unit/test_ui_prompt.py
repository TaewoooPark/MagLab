"""Tests for MagLab prompt completion metadata."""

from __future__ import annotations

from maglab.ui.prompt import (
    SLASH_COMMANDS,
    prompt_delegated_model_choice,
    prompt_model_choice,
)


def test_connect_completion_tree_includes_model_choices() -> None:
    connect = SLASH_COMMANDS["/connect"]

    assert "gpt-5.5" in connect["codex"]
    assert "gpt-5.3-codex" in connect["codex"]
    assert "claude-opus-4-7" in connect["anthropic"]
    assert "dashscope/qwen3.6-plus" in connect["qwen"]
    assert "gemini/gemini-3.1-pro-preview" in connect["api"]["gemini"]
    assert "gemini/gemini-3.5-flash" in connect["api"]["gemini"]


def test_slash_completion_tree_registers_research_surface() -> None:
    assert "/help" in SLASH_COMMANDS
    assert "/install" in SLASH_COMMANDS
    assert "/doctor" in SLASH_COMMANDS
    assert "/workspace" in SLASH_COMMANDS
    assert "/reset" in SLASH_COMMANDS

    assert {"status", "init", "tree", "brief"} <= set(SLASH_COMMANDS["/workspace"])
    assert "doctor" in SLASH_COMMANDS["/install"]
    assert {"config", "defaults"} <= set(SLASH_COMMANDS["/reset"])
    assert {"list", "create", "install"} <= set(SLASH_COMMANDS["/skill"])
    assert {"inventory"} <= set(SLASH_COMMANDS["/report"])
    assert {"summary", "status"} <= set(SLASH_COMMANDS["/prov"])
    assert {"list", "status", "scaffold"} <= set(SLASH_COMMANDS["/task"])
    assert {"micro", "validate", "plot", "job", "dft", "atomistic", "pipeline"} <= set(
        SLASH_COMMANDS["/sim"]
    )
    assert {"spec", "render", "compose", "export", "primitives"} <= set(SLASH_COMMANDS["/figure"])
    assert {"list", "show", "ingest"} <= set(SLASH_COMMANDS["/figure"]["primitives"])
    assert {"search", "authors", "keywords", "journal", "graph"} <= set(SLASH_COMMANDS["/lit"])
    assert {"revision", "cover-letter", "email", "abstract", "grant", "rebuttal"} <= set(
        SLASH_COMMANDS["/comms"]
    )
    assert {"setup", "start", "stop", "status", "install"} <= set(SLASH_COMMANDS["/gateway"])
    assert {"--effect", "--discover", "--init-grid"} <= set(SLASH_COMMANDS["/fit"])


def test_model_choice_prompt_is_noop_outside_tty() -> None:
    assert prompt_model_choice("openai") is None
    assert prompt_delegated_model_choice("codex") is None


def test_quick_help_renders_first_run_commands() -> None:
    from rich.console import Console

    from maglab.commands.tree import render_quick_help

    console = Console(record=True, width=120)
    render_quick_help(console)
    text = console.export_text()

    assert "/doctor" in text
    assert "/install doctor" in text
    assert "/workspace brief" in text
    assert "/help all" in text


def test_area_help_covers_public_research_surfaces() -> None:
    from rich.console import Console

    from maglab.commands.tree import render_area_help

    expected = {
        "review": "/review",
        "instrument": "/instr scaffold",
        "setup": "/install doctor",
        "physics": "/physics compute",
        "present": "/present templates",
        "authoring": "/write",
        "gateway": "/gateway setup",
    }
    for area, marker in expected.items():
        console = Console(record=True, width=140)
        assert render_area_help(area, console) is True
        assert marker in console.export_text()


def test_help_completion_includes_public_area_names() -> None:
    help_tree = SLASH_COMMANDS["/help"]

    for area in {
        "install",
        "setup",
        "auth",
        "physics",
        "materials",
        "analysis",
        "writing",
        "authoring",
        "review",
        "lab",
        "instrument",
        "automation",
        "present",
        "poster",
        "deck",
    }:
        assert area in help_tree
