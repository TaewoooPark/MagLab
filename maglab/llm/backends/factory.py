"""Backend factory and status helpers for MagLab LLM providers.

This module is the single wiring point between ``config.toml`` and concrete
LLM backend implementations. It deliberately does not own credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maglab.config import Config


@dataclass(frozen=True)
class BackendStatus:
    """Human-readable backend status used by CLI and REPL setup commands."""

    ok: bool
    mode: str
    label: str
    detail: str
    action: str = ""


def create_backend(config: Config) -> Any:
    """Create the configured backend instance.

    Raises:
        ValueError: if the configured backend mode is unknown.
    """
    mode = config.backend.mode
    if mode == "api":
        from maglab.llm.backends.api import APIBackend

        api = config.backend.api
        return APIBackend(
            provider=api.provider,
            model=api.model,
            base_url=api.base_url,
        )
    if mode == "delegated_cli":
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        delegated = config.backend.delegated_cli
        return DelegatedCLIBackend(
            cli=delegated.tool,
            model=delegated.model,
            timeout=delegated.timeout,
            extra_flags=list(delegated.extra_flags),
        )
    if mode == "local":
        from maglab.llm.backends.local import LocalBackend

        local = config.backend.local
        return LocalBackend(model=local.model, host=local.host)
    raise ValueError(f"Unknown backend mode: {mode!r}")


def backend_label(config: Config) -> str:
    """Return a concise label for the configured backend."""
    mode = config.backend.mode
    if mode == "api":
        api = config.backend.api
        return f"{api.provider}:{api.model} · API"
    if mode == "delegated_cli":
        delegated = config.backend.delegated_cli
        model = delegated.model or "CLI default"
        return f"{delegated.tool}:{model} · delegated CLI"
    local = config.backend.local
    return f"{local.model} · Ollama"


def backend_status(config: Config) -> BackendStatus:
    """Return a non-secret status summary for the configured backend.

    This is intentionally lightweight. Delegated CLI status checks executable
    availability only; a live smoke prompt would consume model quota and is left
    to explicit test commands.
    """
    mode = config.backend.mode
    label = backend_label(config)
    try:
        backend = create_backend(config)
    except Exception as exc:  # noqa: BLE001
        return BackendStatus(False, mode, label, str(exc))

    try:
        ok = bool(backend.health_check())
    except Exception as exc:  # noqa: BLE001
        return BackendStatus(False, mode, label, str(exc))

    if ok:
        if mode == "delegated_cli":
            version = ""
            get_version = getattr(backend, "get_cli_version", None)
            if callable(get_version):
                version = get_version() or ""
            detail = version or "CLI executable found"
        elif mode == "api":
            detail = "API key found"
        else:
            detail = "Ollama server is reachable"
        return BackendStatus(True, mode, label, detail)

    if mode == "delegated_cli":
        tool = config.backend.delegated_cli.tool
        return BackendStatus(
            False,
            mode,
            label,
            f"{tool!r} executable was not found on PATH",
            f"Install and authenticate the official {tool} CLI, then run `maglab auth {tool}`.",
        )
    if mode == "api":
        from maglab.llm.providers import get_provider_profile

        provider = config.backend.api.provider
        profile = get_provider_profile(provider)
        return BackendStatus(
            False,
            mode,
            label,
            f"No API key found for provider {provider!r}",
            f"Run `maglab auth {profile.key}` or set {profile.maglab_env_var}.",
        )
    return BackendStatus(
        False,
        mode,
        label,
        "Ollama is not reachable",
        "Start Ollama with `ollama serve`, then run `maglab auth status`.",
    )
