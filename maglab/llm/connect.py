"""Interactive-safe backend connection helpers.

These helpers update non-secret backend configuration. API secrets remain in
``maglab.llm.auth`` storage, and delegated CLI credentials remain owned by the
official CLI tools.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from maglab import config as config_mod
from maglab.config import Config
from maglab.llm.providers import get_provider_profile, normalize_provider

_DELEGATED_TOOLS = {"codex", "claude", "gemini"}


def configure_delegated_cli(
    config: Config,
    *,
    tool: str,
    model: str | None = None,
    path: Path | None = None,
) -> tuple[Path, str]:
    """Persist a delegated CLI backend selection."""
    tool = tool.strip().lower()
    if tool not in _DELEGATED_TOOLS:
        raise ValueError(f"Unsupported delegated CLI tool: {tool!r}")
    config.backend.mode = "delegated_cli"
    config.backend.delegated_cli.tool = tool
    config.backend.delegated_cli.model = model.strip() if model and model.strip() else None
    saved = config_mod.save_config(config, path)
    exe_status = "found" if shutil.which(tool) else "missing"
    return saved, exe_status


def configure_api_backend(
    config: Config,
    *,
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
    path: Path | None = None,
) -> Path:
    """Persist a direct API backend selection."""
    provider = normalize_provider(provider)
    profile = get_provider_profile(provider)
    config.backend.mode = "api"
    config.backend.api.provider = provider
    config.backend.api.model = model.strip() if model and model.strip() else profile.default_model
    config.backend.api.base_url = base_url.strip() if base_url and base_url.strip() else None
    for stage, stage_model in profile.routing.items():
        if hasattr(config.routing, stage):
            setattr(config.routing, stage, stage_model)
    return config_mod.save_config(config, path)


def configure_local_backend(
    config: Config,
    *,
    model: str,
    host: str | None = None,
    path: Path | None = None,
) -> Path:
    """Persist an Ollama backend selection."""
    config.backend.mode = "local"
    config.backend.local.model = model
    if host:
        config.backend.local.host = host
    return config_mod.save_config(config, path)
