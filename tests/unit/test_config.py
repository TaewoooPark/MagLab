"""maglab.config tests — defaults, file overrides, and env overrides."""

from __future__ import annotations

import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from maglab.config import (
    Config,
    ConfigError,
    config_backup_path,
    config_path,
    load_config,
    save_config,
)


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

    assert roundtripped.get("ui", {}).get("theme") == "mono", "theme was not updated"
    assert roundtripped.get("backend", {}).get("mode") == "local", (
        "F1 regression: [backend] section was silently discarded by theme set"
    )


# ---------------------------------------------------------------------------
# Broken config files must not lock the user out of every command
# ---------------------------------------------------------------------------


def test_malformed_toml_raises_actionable_config_error(tmp_path: Path) -> None:
    """A truncated config (what an interrupted write leaves) must not leak tomllib."""
    p = tmp_path / "config.toml"
    p.write_text('[backend]\nmode = "api"\n[routi', encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(p)

    message = str(excinfo.value)
    assert str(p) in message, "the offending file must be named"
    assert "maglab config reset" in message, "must point at the repair command"


def test_malformed_toml_prefers_restore_when_backup_exists(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("[[[", encoding="utf-8")
    config_backup_path(p).write_text('[ui]\ntheme = "domain"\n', encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(p)

    assert "maglab config restore" in str(excinfo.value)


def test_invalid_schema_value_raises_config_error_naming_the_field(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('[backend]\nmode = "bogus"\n', encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(p)

    message = str(excinfo.value)
    assert "backend.mode" in message, "the invalid field must be named"
    assert "bogus" not in message.split("\n")[0], "first line stays a summary"


def test_empty_config_file_still_loads_defaults(tmp_path: Path) -> None:
    """An empty file is valid TOML — it must fall back to defaults, not error."""
    p = tmp_path / "config.toml"
    p.write_text("", encoding="utf-8")
    assert load_config(p).backend.mode == "api"


def test_config_error_surfaces_as_clean_cli_message(tmp_path: Path) -> None:
    """`maglab.__main__.main` must convert ConfigError into a message + exit 1."""
    import maglab.__main__ as main_mod

    def _boom() -> None:
        raise ConfigError("config is broken")

    with patch.object(main_mod, "app", _boom), pytest.raises(SystemExit) as excinfo:
        main_mod.main()

    assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# Atomic save — an interrupted write must not destroy the existing config
# ---------------------------------------------------------------------------


def test_save_config_is_atomic_on_failure(tmp_path: Path) -> None:
    """If the write fails midway, the previous config must survive intact."""
    p = tmp_path / "config.toml"
    original = '[ui]\ntheme = "moke"\n'
    p.write_text(original, encoding="utf-8")

    with (
        patch("maglab.config.atomic_write_text", side_effect=OSError("disk full")),
        pytest.raises(OSError),
    ):
        save_config(Config(), path=p)

    assert p.read_text(encoding="utf-8") == original, "config was clobbered by a failed save"
    assert load_config(p).ui.theme == "moke", "config must remain loadable"


def test_save_config_leaves_no_temp_files(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    save_config(Config(), path=p)
    save_config(Config(), path=p)

    leftovers = [q.name for q in tmp_path.iterdir() if q.name.endswith(".tmp")]
    assert leftovers == [], f"atomic write left scratch files behind: {leftovers}"
