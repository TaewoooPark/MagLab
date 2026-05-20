"""Unit tests for the configured LLM backend factory.

Factory construction is local-only: no API calls, Ollama requests, or CLI subprocesses.
"""

from __future__ import annotations

from maglab.config import Config


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
