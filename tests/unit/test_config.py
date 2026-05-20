"""maglab.config tests — defaults, file overrides, and env overrides."""

from __future__ import annotations

import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from maglab.config import Config, config_path, load_config


def test_defaults_when_no_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert isinstance(cfg, Config)
    assert cfg.backend.mode == "api"
    assert cfg.ui.theme == "domain"
    assert cfg.budget.max_iterations_default == 20
    assert cfg.routing.plan == "claude-opus-4-7"


def test_file_overrides(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('[ui]\ntheme = "moke"\n\n[backend]\nmode = "local"\n')
    cfg = load_config(p)
    assert cfg.ui.theme == "moke"
    assert cfg.backend.mode == "local"
    # Values not explicitly set should retain defaults
    assert cfg.backend.api.provider == "anthropic"


def test_env_override_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "config.toml"
    p.write_text('[ui]\ntheme = "moke"\n')
    monkeypatch.setenv("MAGLAB_THEME", "mono")
    cfg = load_config(p)
    assert cfg.ui.theme == "mono"


def test_config_path_is_absolute() -> None:
    assert config_path().is_absolute()
    assert config_path().name == "config.toml"


def test_save_load_roundtrip_delegated_codex_without_credentials(tmp_path: Path) -> None:
    """Delegated Codex config is persisted, but credentials are never written."""
    from maglab.config import save_config

    cfg_file = tmp_path / "config.toml"
    cfg = Config.model_validate(
        {
            "backend": {
                "mode": "delegated_cli",
                "delegated_cli": {
                    "tool": "codex",
                    "model": None,
                },
            }
        }
    )

    save_config(cfg, cfg_file)
    raw = cfg_file.read_text(encoding="utf-8")
    loaded = load_config(cfg_file)

    assert loaded.backend.mode == "delegated_cli"
    assert loaded.backend.delegated_cli.tool == "codex"
    assert loaded.backend.delegated_cli.model is None
    assert "api_key" not in raw
    assert "access_token" not in raw
    assert "credential" not in raw.lower()


def test_save_config_creates_restore_backup(tmp_path: Path) -> None:
    from maglab.config import restore_config, save_config

    cfg_file = tmp_path / "config.toml"
    old = Config()
    old.ui.theme = "mono"
    new = Config()
    new.ui.theme = "moke"

    save_config(old, cfg_file)
    save_config(new, cfg_file)

    assert load_config(cfg_file).ui.theme == "moke"
    restore_config(cfg_file)
    assert load_config(cfg_file).ui.theme == "mono"


def test_reset_config_preserves_previous_file_as_backup(tmp_path: Path) -> None:
    from maglab.config import reset_config, restore_config, save_config

    cfg_file = tmp_path / "config.toml"
    old = Config()
    old.ui.theme = "light"
    save_config(old, cfg_file)

    reset_config(cfg_file)
    assert load_config(cfg_file).ui.theme == "domain"

    restore_config(cfg_file)
    assert load_config(cfg_file).ui.theme == "light"


# ---------------------------------------------------------------------------
# F1 regression — theme set must not destroy existing config keys
# ---------------------------------------------------------------------------


def test_theme_set_preserves_other_config_keys(tmp_path: Path) -> None:
    """F1 regression: `theme set` fallback must not discard non-[ui] sections.

    When tomli_w is not installed the hand-serialiser must round-trip every
    section in the existing config, not only [ui].
    """
    from typer.testing import CliRunner

    from maglab.cli import app

    cfg_file = tmp_path / "config.toml"
    # Pre-populate with multiple sections the user would not want erased.
    cfg_file.write_text(
        '[ui]\ntheme = "domain"\n\n[backend]\nmode = "local"\n',
        encoding="utf-8",
    )

    runner = CliRunner()

    # Patch config_path to return our tmp file and Theme.load to avoid disk lookup.
    # config_path is imported via `from maglab.config import config_path` inside the
    # function body, so we must patch it in maglab.config (the source module).
    with (
        patch("maglab.config.config_path", return_value=cfg_file),
        patch("maglab.ui.theme.Theme.load"),
    ):
        result = runner.invoke(app, ["theme", "set", "mono"])

    assert result.exit_code == 0, result.output

    # The file must still be valid TOML and retain the [backend] section.
    with cfg_file.open("rb") as fh:
        roundtripped = tomllib.load(fh)

    assert roundtripped.get("ui", {}).get("theme") == "mono", (
        "theme was not updated"
    )
    assert roundtripped.get("backend", {}).get("mode") == "local", (
        "F1 regression: [backend] section was silently discarded by theme set"
    )
