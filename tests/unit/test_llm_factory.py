"""Unit tests for the configured LLM backend factory.

Factory construction is local-only: no API calls, Ollama requests, or CLI subprocesses.
"""

from __future__ import annotations

from maglab.config import Config
from maglab.llm.base import LLMResponse


def test_factory_creates_api_backend_from_config() -> None:
    from maglab.llm.backends.api import APIBackend
    from maglab.llm.factory import create_llm_backend

    cfg = Config.model_validate(
        {
            "backend": {
                "mode": "api",
                "api": {
                    "provider": "openai",
                    "model": "gpt-4o",
                },
            }
        }
    )

    backend = create_llm_backend(cfg)

    assert isinstance(backend, APIBackend)
    assert backend.provider == "openai"
    assert backend.default_model == "gpt-4o"


def test_factory_creates_local_backend_from_config() -> None:
    from maglab.llm.backends.local import LocalBackend
    from maglab.llm.factory import create_llm_backend

    cfg = Config.model_validate(
        {
            "backend": {
                "mode": "local",
                "local": {
                    "host": "http://127.0.0.1:11434",
                    "model": "llama3.1:8b",
                },
            }
        }
    )

    backend = create_llm_backend(cfg)

    assert isinstance(backend, LocalBackend)
    assert backend.host == "http://127.0.0.1:11434"
    assert backend.default_model == "llama3.1:8b"


def test_factory_creates_delegated_codex_backend_from_config() -> None:
    from maglab.llm.backends.delegated_cli import DelegatedCLIBackend
    from maglab.llm.factory import create_llm_backend

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

    backend = create_llm_backend(cfg)

    assert isinstance(backend, DelegatedCLIBackend)
    assert backend.cli == "codex"
    assert backend.default_model == ""


def test_live_backend_smoke_requires_exact_parsed_sentinel(monkeypatch) -> None:
    from maglab.llm.factory import test_llm_backend

    class RawJsonlBackend:
        def complete(self, *args, **kwargs):
            return LLMResponse(
                content='{"type":"item.completed","item":{"type":"agent_message","text":"MAGLAB_OK"}}'
            )

    cfg = Config.model_validate({"backend": {"mode": "delegated_cli"}})
    monkeypatch.setattr("maglab.llm.factory.create_llm_backend", lambda config: RawJsonlBackend())

    status = test_llm_backend(cfg)

    assert status.ok is False
    assert "sentinel exactly" in status.detail


def test_live_backend_smoke_accepts_plain_sentinel(monkeypatch) -> None:
    from maglab.llm.factory import test_llm_backend

    class ParsedBackend:
        def complete(self, *args, **kwargs):
            return LLMResponse(content="MAGLAB_OK\n")

    cfg = Config.model_validate({"backend": {"mode": "delegated_cli"}})
    monkeypatch.setattr("maglab.llm.factory.create_llm_backend", lambda config: ParsedBackend())

    status = test_llm_backend(cfg)

    assert status.ok is True
