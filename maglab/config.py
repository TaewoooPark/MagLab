"""maglab configuration — load TOML from XDG path, defaults, and env overrides (§7.1).

Credentials are not stored in this file (§7.2) — use env vars, keyring, or auth.json instead.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path
from typing import Any, Literal

import platformdirs
from pydantic import BaseModel, Field

APP_NAME = "maglab"


class APIBackendConfig(BaseModel):
    """Direct API backend configuration (bring-your-own key)."""

    provider: str = "anthropic"
    model: str = "claude-opus-4-7"
    base_url: str | None = None


class DelegatedCLIBackendConfig(BaseModel):
    """Delegated CLI backend configuration — official codex/claude/gemini subprocess."""

    tool: str = "claude"
    model: str | None = None
    timeout: float = 120.0
    extra_flags: list[str] = Field(default_factory=list)


class LocalBackendConfig(BaseModel):
    """Local (Ollama) backend configuration."""

    host: str = "http://localhost:11434"
    model: str = "llama3.1"


class BackendConfig(BaseModel):
    """LLM backend configuration (§7.2)."""

    mode: Literal["api", "delegated_cli", "local"] = "api"
    api: APIBackendConfig = Field(default_factory=APIBackendConfig)
    delegated_cli: DelegatedCLIBackendConfig = Field(default_factory=DelegatedCLIBackendConfig)
    local: LocalBackendConfig = Field(default_factory=LocalBackendConfig)


class RoutingConfig(BaseModel):
    """Per-stage model routing (§7.3) — different model for each pipeline stage."""

    plan: str = "claude-opus-4-7"
    build: str = "claude-sonnet-4-6"
    summarize: str = "claude-haiku-4-5-20251001"
    vision_critic: str = "claude-opus-4-7"


class AutonomyConfig(BaseModel):
    """Autonomy mode (§5.8)."""

    mode: Literal["copilot", "semi-auto", "autonomous"] = "copilot"


class UIConfig(BaseModel):
    """Terminal UI configuration (§7.8)."""

    theme: str = "domain"


class BudgetConfig(BaseModel):
    """Budget gate (§5.14)."""

    max_usd_per_session: float = 10.0
    max_iterations_default: int = 20


class Config(BaseModel):
    """maglab global configuration."""

    backend: BackendConfig = Field(default_factory=BackendConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    autonomy: AutonomyConfig = Field(default_factory=AutonomyConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)


def config_path() -> Path:
    """User configuration file path (XDG — typically ``~/.config/maglab/config.toml``)."""
    return Path(platformdirs.user_config_dir(APP_NAME)) / "config.toml"


def config_backup_path(path: Path | None = None) -> Path:
    """Return the one-step backup path for the config file."""
    path = path or config_path()
    return path.with_name(f"{path.name}.bak")


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides (env > file > defaults)."""
    theme = os.environ.get("MAGLAB_THEME")
    if theme:
        data.setdefault("ui", {})["theme"] = theme
    return data


def load_config(path: Path | None = None) -> Config:
    """Load configuration.

    If the file does not exist, uses defaults; env vars override file values.
    """
    path = path or config_path()
    data: dict[str, Any] = {}
    if path.is_file():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    data = _apply_env_overrides(data)
    return Config.model_validate(data)


def _format_toml_scalar(value: Any) -> str:
    """Format a primitive scalar for the minimal fallback TOML writer."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_format_toml_scalar(v) for v in value)
        return f"[{items}]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_toml_fallback(data: dict[str, Any]) -> str:
    """Serialize simple nested config dictionaries when tomlkit is unavailable."""
    lines: list[str] = []

    def emit_table(prefix: str, table: dict[str, Any]) -> None:
        scalar_items: list[tuple[str, Any]] = []
        nested_items: list[tuple[str, dict[str, Any]]] = []
        for key, value in table.items():
            if value is None:
                continue
            if isinstance(value, dict):
                nested_items.append((key, value))
            else:
                scalar_items.append((key, value))

        if prefix:
            lines.append(f"[{prefix}]")
        for key, value in scalar_items:
            lines.append(f"{key} = {_format_toml_scalar(value)}")
        if scalar_items:
            lines.append("")
        for key, value in nested_items:
            nested_prefix = f"{prefix}.{key}" if prefix else key
            emit_table(nested_prefix, value)

    emit_table("", data)
    return "\n".join(lines).rstrip() + "\n"


def save_config(config: Config, path: Path | None = None) -> Path:
    """Save non-secret MagLab configuration as TOML.

    Credentials intentionally do not live in ``config.toml``. API keys remain in
    env/keyring/auth.json, and delegated CLI OAuth state remains owned by the
    official CLI tool.
    """
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        backup = config_backup_path(path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    data = config.model_dump(mode="json", exclude_none=True)
    try:
        import tomlkit

        path.write_text(tomlkit.dumps(data), encoding="utf-8")
    except Exception:
        path.write_text(_write_toml_fallback(data), encoding="utf-8")
    return path


def restore_config(path: Path | None = None) -> Path:
    """Restore the previous config backup."""
    path = path or config_path()
    backup = config_backup_path(path)
    if not backup.is_file():
        raise FileNotFoundError(f"No MagLab config backup found at {backup}")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, path)
    return path


def reset_config(path: Path | None = None) -> Path:
    """Write a clean default config, preserving the previous file as backup."""
    return save_config(Config(), path=path)
