"""Local backend — based on the Ollama Python client.

§7.2: Local mode implementation. Displays an explicit guidance message when Ollama
is not running. Default endpoint: ``http://localhost:11434``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

from maglab.llm.base import (
    LLMBackend,
    LLMResponse,
    Message,
    ToolCall,
    UsageStats,
)

log = logging.getLogger(__name__)

_OLLAMA_NOT_RUNNING = (
    "Ollama is not running. "
    "Start the Ollama server first with 'ollama serve'. "
    "(default address: http://localhost:11434)"
)


class LocalBackend(LLMBackend):
    """Ollama-based local LLM backend.

    Args:
        model: Ollama model name (e.g. ``"llama3.2"``, ``"mistral"``).
        host: Ollama server address (default: ``"http://localhost:11434"``).
        timeout: API call timeout in seconds.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.default_model = model
        self.host = host
        self.timeout = timeout

    def _get_client(self) -> Any:
        """Return the Ollama client. Raises an exception if Ollama is not installed."""
        try:
            import ollama  # type: ignore[import-untyped]

            client = ollama.Client(host=self.host)
            return client
        except ImportError as exc:
            raise RuntimeError(
                "The ollama package is not installed. Install it with 'pip install ollama'."
            ) from exc

    def _check_ollama_running(self, client: Any) -> None:
        """Verify that the Ollama server is responding."""
        try:
            client.list()
        except Exception as exc:
            raise ConnectionError(_OLLAMA_NOT_RUNNING) from exc

    def _messages_to_ollama(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert a ``Message`` list to Ollama chat format."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.role.value
            if isinstance(msg.content, str):
                content = msg.content
            else:
                # ContentBlock list → extract text only
                parts = [b.text or b.content or "" for b in msg.content]
                content = "\n".join(p for p in parts if p)
            result.append({"role": role, "content": content})
        return result

    def _parse_chat_response(self, resp: Any, model_str: str) -> LLMResponse:
        """Convert an Ollama chat response to ``LLMResponse``."""
        content: str | None = None
        tool_calls: list[ToolCall] = []
        stop_reason = "end_turn"

        if hasattr(resp, "message"):
            msg = resp.message
            content = getattr(msg, "content", None) or None

        # Ollama does not support tool_calls — always an empty list
        usage_resp = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage_resp, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage_resp, "completion_tokens", 0) or 0

        # Ollama responses may include eval_count (completion tokens) field
        if hasattr(resp, "eval_count"):
            completion_tokens = resp.eval_count or 0
        if hasattr(resp, "prompt_eval_count"):
            prompt_tokens = resp.prompt_eval_count or 0

        usage = UsageStats(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw=resp,
            model=model_str,
        )

    def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Non-streaming completion request."""
        client = self._get_client()
        self._check_ollama_running(client)

        model_str = self._resolve_model(model)
        ollama_messages = self._messages_to_ollama(messages)

        options: dict[str, Any] = {"num_predict": max_tokens}
        if temperature is not None:
            options["temperature"] = temperature
        if stop:
            options["stop"] = stop

        t0 = time.monotonic()
        try:
            resp = client.chat(
                model=model_str,
                messages=ollama_messages,
                options=options,
                stream=False,
            )
        except ConnectionError:
            raise
        except Exception as exc:
            err_msg = str(exc).lower()
            if "connection" in err_msg or "refused" in err_msg:
                raise ConnectionError(_OLLAMA_NOT_RUNNING) from exc
            raise

        result = self._parse_chat_response(resp, model_str)
        result.usage.latency_sec = time.monotonic() - t0
        return result

    def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Streaming completion request — yields text chunks in order."""
        client = self._get_client()
        self._check_ollama_running(client)

        model_str = self._resolve_model(model)
        ollama_messages = self._messages_to_ollama(messages)

        options: dict[str, Any] = {"num_predict": max_tokens}
        if temperature is not None:
            options["temperature"] = temperature
        if stop:
            options["stop"] = stop

        try:
            resp_iter = client.chat(
                model=model_str,
                messages=ollama_messages,
                options=options,
                stream=True,
            )
            for chunk in resp_iter:
                if hasattr(chunk, "message"):
                    text = getattr(chunk.message, "content", None)
                    if text:
                        yield text
        except ConnectionError:
            raise
        except Exception as exc:
            err_msg = str(exc).lower()
            if "connection" in err_msg or "refused" in err_msg:
                raise ConnectionError(_OLLAMA_NOT_RUNNING) from exc
            raise

    def list_models(self) -> list[str]:
        """Return the list of models installed on the Ollama server.

        Returns:
            List of model names. Returns an empty list if Ollama is not running.
        """
        try:
            client = self._get_client()
            self._check_ollama_running(client)
            result = client.list()
            models = getattr(result, "models", [])
            return [getattr(m, "model", str(m)) for m in models]
        except Exception as exc:
            log.warning("Failed to retrieve Ollama model list: %s", exc)
            return []

    def health_check(self) -> bool:
        """Check Ollama server connectivity."""
        try:
            client = self._get_client()
            self._check_ollama_running(client)
            return True
        except Exception:
            return False
