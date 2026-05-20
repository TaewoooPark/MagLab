"""Public LLM backend factory.

Kept at ``maglab.llm.factory`` so CLI, REPL, authoring, and tests all share
one import path for backend construction and status.
"""

from __future__ import annotations

from typing import Any

from maglab.config import Config
from maglab.llm.backends.factory import BackendStatus, backend_label, create_backend
from maglab.llm.base import LLMBackend, Message, Role


def create_llm_backend(config: Config, *, event_sink: Any | None = None) -> LLMBackend:
    """Create the configured LLM backend."""
    return create_backend(config, event_sink=event_sink)


def backend_status(config: Config) -> BackendStatus:
    """Return non-secret backend readiness status."""
    mode = config.backend.mode
    label = backend_label(config)
    try:
        backend = create_llm_backend(config)
    except Exception as exc:  # noqa: BLE001
        return BackendStatus(False, mode, label, str(exc))

    try:
        ok = bool(backend.health_check())  # type: ignore[attr-defined]
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


def test_llm_backend(config: Config) -> BackendStatus:
    """Run a small live smoke call against the configured backend."""
    mode = config.backend.mode
    label = backend_label(config)
    try:
        backend = create_llm_backend(config)
        response = backend.complete(  # type: ignore[attr-defined]
            [Message(role=Role.USER, content="Reply with exactly: MAGLAB_OK")],
            max_tokens=20,
        )
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        action = "Check CLI login/API key/Ollama server, then run `maglab auth test` again."
        if "usage limit" in detail.lower() or "quota" in detail.lower():
            action = (
                "Wait for the provider quota reset, buy more credits, or switch backend with "
                "`/connect openai`, `/connect anthropic`, or `/connect ollama`."
            )
        return BackendStatus(
            False,
            mode,
            label,
            detail,
            action,
        )
    content = (getattr(response, "content", None) or "").strip()
    normalized = content.strip("\"'").strip()
    if normalized == "MAGLAB_OK":
        return BackendStatus(True, mode, label, content)
    detail = content or "Backend returned an empty response"
    return BackendStatus(
        False,
        mode,
        label,
        f"Backend smoke did not return the parsed sentinel exactly: {detail}",
        "Check CLI login/API key/Ollama server and delegated CLI output parsing, then rerun `maglab auth test`.",
    )
