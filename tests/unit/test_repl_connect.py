"""Tests for REPL backend slash connection commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from maglab.config import Config
from maglab.repl import _get_response, _handle_slash, _run_cli_slash, _workspace_startup_note


def test_connect_codex_slash_saves_delegated_backend(tmp_path: Path) -> None:
    cfg = Config()

    with (
        patch("maglab.config.save_config") as mock_save,
        patch("shutil.which", return_value="/usr/local/bin/codex"),
    ):
        keep_running = _handle_slash("/connect codex", cfg)

    assert keep_running is True
    mock_save.assert_called_once()
    saved_config = mock_save.call_args[0][0]
    assert saved_config.backend.mode == "delegated_cli"
    assert saved_config.backend.delegated_cli.tool == "codex"
    assert saved_config.backend.delegated_cli.model is None


def test_connect_api_slash_uses_hidden_key_input(tmp_path: Path) -> None:
    cfg = Config()

    with (
        patch("maglab.config.save_config", return_value=tmp_path / "config.toml"),
        patch("getpass.getpass", return_value="sk-test"),
        patch("maglab.llm.auth.store_api_key", return_value="keyring") as mock_store,
    ):
        keep_running = _handle_slash("/connect api openai gpt-4o", cfg)

    assert keep_running is True
    assert cfg.backend.mode == "api"
    assert cfg.backend.api.provider == "openai"
    assert cfg.backend.api.model == "gpt-4o"
    mock_store.assert_called_once_with("openai", "sk-test")


def test_connect_direct_provider_slash_updates_routing(tmp_path: Path) -> None:
    cfg = Config()

    with (
        patch("maglab.config.save_config", return_value=tmp_path / "config.toml"),
        patch("getpass.getpass", return_value="dash-key"),
        patch("maglab.llm.auth.store_api_key", return_value="keyring") as mock_store,
    ):
        keep_running = _handle_slash("/connect qwen qwen3.5-plus", cfg)

    assert keep_running is True
    assert cfg.backend.mode == "api"
    assert cfg.backend.api.provider == "qwen"
    assert cfg.backend.api.model == "qwen3.5-plus"
    assert cfg.routing.plan == "dashscope/qwen3.5-plus"
    assert cfg.routing.build == "dashscope/qwen3.5-plus"
    assert cfg.routing.summarize == "dashscope/qwen3.5-plus"
    mock_store.assert_called_once_with("qwen", "dash-key")


def test_setup_slash_routes_to_feature_setup() -> None:
    cfg = Config()

    with patch("maglab.setup.render_setup") as mock_render:
        keep_running = _handle_slash("/setup literature", cfg)

    assert keep_running is True
    args, kwargs = mock_render.call_args
    assert args == ("literature",)
    assert "console" in kwargs


def test_direct_setup_feature_slash_routes_to_feature_setup() -> None:
    cfg = Config()

    with patch("maglab.setup.render_setup") as mock_render:
        keep_running = _handle_slash("/setup-simulation", cfg)

    assert keep_running is True
    args, kwargs = mock_render.call_args
    assert args == ("simulation",)
    assert "console" in kwargs


def test_help_slash_renders_quick_help_by_default() -> None:
    cfg = Config()

    with patch("maglab.commands.tree.render_quick_help") as mock_render:
        keep_running = _handle_slash("/help", cfg)

    assert keep_running is True
    mock_render.assert_called_once()


def test_help_all_slash_renders_command_tree() -> None:
    cfg = Config()

    with patch("maglab.commands.tree.render_slash_help") as mock_render:
        keep_running = _handle_slash("/help all", cfg)

    assert keep_running is True
    mock_render.assert_called_once()


def test_workspace_slash_dispatches_to_cli_command() -> None:
    cfg = Config()

    with patch("maglab.repl._run_cli_slash") as mock_run:
        keep_running = _handle_slash("/workspace status", cfg)

    assert keep_running is True
    args, _ = mock_run.call_args
    assert args[0] == ["/workspace", "status"]


def test_run_cli_slash_executes_without_standalone_click(capsys) -> None:
    """Regression: REPL CLI-slash dispatch must not need a standalone ``click``.

    typer >= 0.26 vendors click as ``typer._click`` and drops the standalone
    distribution, so a bare ``import click`` in ``_run_cli_slash`` crashed every
    CLI slash command (/physics, /mat, /doctor, …) in the REPL.
    """
    from rich.console import Console

    # Real dispatch (not mocked) of a deterministic command — must not raise.
    _run_cli_slash(["/physics", "units", "1000", "oe", "tesla"], Console())
    assert "tesla" in capsys.readouterr().out.lower()


def test_skill_create_slash_dispatches_to_cli_command() -> None:
    cfg = Config()

    with patch("maglab.repl._run_cli_slash") as mock_run:
        keep_running = _handle_slash('/skill create demo --description "Demo skill"', cfg)

    assert keep_running is True
    args, _ = mock_run.call_args
    assert args[0] == ["/skill", "create", "demo", "--description", "Demo skill"]


def test_skill_list_slash_uses_fast_catalog_view(capsys) -> None:
    cfg = Config()

    with patch("maglab.repl._run_cli_slash") as mock_run:
        keep_running = _handle_slash("/skill list", cfg)

    assert keep_running is True
    mock_run.assert_not_called()
    output = capsys.readouterr().out
    assert output.strip()


def test_workspace_startup_note_reports_folder_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    note = _workspace_startup_note(max_entries=5)

    assert str(tmp_path) in note
    assert "MAGLAB.md loaded" in note
    assert "README.md" in note


def test_no_backend_response_includes_workspace_note(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("# Project\n", encoding="utf-8")

    response = _get_response("what is this repo?", orchestrator=None)

    assert "Workspace context:" in response
    assert str(tmp_path) in response
    assert "No LLM backend is connected" in response


def test_manual_slash_accepts_language_first(capsys) -> None:
    console = Console(force_terminal=False, width=120)

    _run_cli_slash(["/manual", "ko", "figures"], console)

    output = capsys.readouterr().out
    assert "lang: ko" in output
    assert "figures" in output


def test_reset_defaults_slash_mutates_active_config(tmp_path: Path) -> None:
    cfg = Config()
    cfg.ui.theme = "moke"
    cfg.backend.local.model = "custom-local"
    fresh = Config()

    with (
        patch("maglab.config.reset_config", return_value=tmp_path / "config.toml") as mock_reset,
        patch("maglab.config.load_config", return_value=fresh) as mock_load,
    ):
        keep_running = _handle_slash("/reset defaults", cfg)

    assert keep_running is True
    mock_reset.assert_called_once_with()
    mock_load.assert_called_once_with(tmp_path / "config.toml")
    assert cfg.ui.theme == fresh.ui.theme
    assert cfg.backend.local.model == fresh.backend.local.model


def test_connect_reset_slash_restores_previous_config(tmp_path: Path) -> None:
    cfg = Config()
    cfg.ui.theme = "light"
    restored = Config()
    restored.ui.theme = "mono"

    with (
        patch(
            "maglab.config.restore_config", return_value=tmp_path / "config.toml"
        ) as mock_restore,
        patch("maglab.config.load_config", return_value=restored) as mock_load,
    ):
        keep_running = _handle_slash("/connect reset", cfg)

    assert keep_running is True
    mock_restore.assert_called_once_with()
    mock_load.assert_called_once_with(tmp_path / "config.toml")
    assert cfg.ui.theme == "mono"
