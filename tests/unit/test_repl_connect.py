"""Tests for REPL backend slash connection commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from maglab.config import Config
from maglab.repl import _handle_slash, _run_cli_slash


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
    assert cfg.routing.plan == "dashscope/qwen3.6-plus"
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


def test_help_slash_renders_command_tree() -> None:
    cfg = Config()

    with patch("maglab.commands.tree.render_slash_help") as mock_render:
        keep_running = _handle_slash("/help", cfg)

    assert keep_running is True
    mock_render.assert_called_once()


def test_workspace_slash_dispatches_to_cli_command() -> None:
    cfg = Config()

    with patch("maglab.repl._run_cli_slash") as mock_run:
        keep_running = _handle_slash("/workspace status", cfg)

    assert keep_running is True
    args, _ = mock_run.call_args
    assert args[0] == ["/workspace", "status"]


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
