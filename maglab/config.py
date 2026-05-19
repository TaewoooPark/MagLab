"""maglab configuration — load TOML from XDG path, defaults, and env overrides (§7.1).

Credentials are not stored in this file (§7.2) — use env vars, keyring, or auth.json instead.
"""

from __future__ import annotations

import os
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


class DelegatedCLIBackendConfig(BaseModel):
    """Delegated CLI backend configuration — official codex/claude/gemini subprocess."""

    tool: str = "claude"


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
    build: str = "claude-haiku-4-5-20251001"
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
