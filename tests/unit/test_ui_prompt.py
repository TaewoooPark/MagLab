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
    assert "gemini/gemini-3.5-flash" in connect["api"]["gemini"]


def test_slash_completion_tree_registers_research_surface() -> None:
    assert "/help" in SLASH_COMMANDS
    assert "/install" in SLASH_COMMANDS
    assert "/doctor" in SLASH_COMMANDS
    assert "/workspace" in SLASH_COMMANDS
    assert "/reset" in SLASH_COMMANDS

    assert {"status", "init", "tree"} <= set(SLASH_COMMANDS["/workspace"])
    assert {"config", "defaults"} <= set(SLASH_COMMANDS["/reset"])
    assert {"micro", "validate", "plot", "job", "dft", "atomistic", "pipeline"} <= set(
        SLASH_COMMANDS["/sim"]
    )
    assert {"spec", "render", "compose", "export", "primitives"} <= set(SLASH_COMMANDS["/figure"])
    assert {"search", "authors", "keywords", "journal", "graph"} <= set(SLASH_COMMANDS["/lit"])
    assert {"revision", "cover-letter", "email", "abstract", "grant", "rebuttal"} <= set(
        SLASH_COMMANDS["/comms"]
    )
    assert {"setup", "start", "stop", "status", "install"} <= set(SLASH_COMMANDS["/gateway"])


def test_model_choice_prompt_is_noop_outside_tty() -> None:
    assert prompt_model_choice("openai") is None
    assert prompt_delegated_model_choice("codex") is None
