"""Direct API backend — Anthropic/OpenAI/Google/OpenAI-compatible integration via LiteLLM.

§7.2: BYO-key mode implementation. Credentials are retrieved via ``llm.auth.get_api_key()``,
following the priority order: env var first → keyring → auth.json.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from typing import Any

from maglab.llm.auth import get_api_key
from maglab.llm.base import (
    LLMBackend,
    LLMResponse,
    Message,
    ToolCall,
    UsageStats,
)

log = logging.getLogger(__name__)

# provider → litellm model prefix mapping
_PROVIDER_PREFIX: dict[str, str] = {
    "openai": "",  # no prefix
    "anthropic": "anthropic/",
    "google": "gemini/",
    "openai-compatible": "",
}

# Environment variable names read by litellm
_PROVIDER_ENV_KEY: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "openai-compatible": "OPENAI_API_KEY",
}


class APIBackend(LLMBackend):
    """LiteLLM-based direct API backend.

    Args:
        provider: LLM provider (``"anthropic"``·``"openai"``·``"google"``·
                  ``"openai-compatible"``).
        model: Default model identifier.
        base_url: OpenAI-compatible endpoint URL (used with ``openai-compatible``).
        max_retries: Number of retries on API call failure.
        retry_delay: Initial retry delay in seconds (exponential backoff applied).
    """

    def __init__(
        self,
        provider: str = "anthropic",
        model: str = "claude-opus-4-7",
        base_url: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.provider = provider
        self.default_model = model
        self.base_url = base_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._api_key: str | None = None

    def _get_api_key(self) -> str | None:
        """Cached credential lookup (avoids re-fetching on every call)."""
        if self._api_key is None:
            self._api_key = get_api_key(self.provider)
        return self._api_key

    def _inject_api_key(self) -> dict[str, str]:
        """Return a snapshot of env var key → current value for the API key used by litellm.

        The caller uses this to temporarily inject credentials as a context manager.
        """
        key = self._get_api_key()
        env_var = _PROVIDER_ENV_KEY.get(self.provider)
        if key and env_var and not os.environ.get(env_var):
            return {env_var: key}
        return {}

    def _build_model_str(self, model: str | None) -> str:
        """Construct the model string to pass to litellm."""
        resolved = self._resolve_model(model)
        prefix = _PROVIDER_PREFIX.get(self.provider, "")
        # Do not duplicate the prefix if it is already present
        if prefix and not resolved.startswith(prefix):
            return prefix + resolved
        return resolved

    def _call_litellm(
        self,
        messages: list[Message],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Call litellm.completion and return the result (with retries)."""
        import litellm  # type: ignore[import-untyped]

        model_str = self._build_model_str(model)
        msg_dicts = [m.to_dict() for m in messages]

        call_kwargs: dict[str, Any] = {
            "model": model_str,
            "messages": msg_dicts,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if stop:
            call_kwargs["stop"] = stop
        if tools:
            call_kwargs["tools"] = tools
        if self.base_url:
            call_kwargs["api_base"] = self.base_url
        call_kwargs.update(kwargs)

        # Temporarily inject API key as an environment variable
        injected = self._inject_api_key()
        old_env: dict[str, str | None] = {}
        for var, val in injected.items():
            old_env[var] = os.environ.get(var)
            os.environ[var] = val

        last_exc: Exception | None = None
        try:
            for attempt in range(max(1, self.max_retries)):
                try:
                    return litellm.completion(**call_kwargs)
                except (litellm.RateLimitError, litellm.ServiceUnavailableError) as exc:
                    last_exc = exc
                    delay = self.retry_delay * (2**attempt)
                    log.warning(
                        "API call failed (attempt %d/%d) — retrying in %.1f s: %s",
                        attempt + 1,
                        self.max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                except Exception:
                    raise
        finally:
            for var, original in old_env.items():
                if original is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = original

        raise last_exc or RuntimeError("litellm call failed")

    @staticmethod
    def _parse_response(resp: Any, model_str: str) -> LLMResponse:
        """Convert a litellm response to ``LLMResponse``."""
        choice = resp.choices[0] if resp.choices else None
        content: str | None = None
        tool_calls: list[ToolCall] = []
        stop_reason = "end_turn"

        if choice:
            msg = choice.message
            content = getattr(msg, "content", None) or None
            stop_reason = getattr(choice, "finish_reason", "end_turn") or "end_turn"
            # OpenAI-format tool_calls
            raw_tc = getattr(msg, "tool_calls", None)
            if raw_tc:
                stop_reason = "tool_use"
                for tc in raw_tc:
                    import json

                    args: dict[str, Any] = {}
                    if hasattr(tc, "function"):
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except Exception:
                            args = {}
                    tool_calls.append(
                        ToolCall(
                            id=tc.id or "",
                            name=getattr(tc.function, "name", "")
                            if hasattr(tc, "function")
                            else "",
                            arguments=args,
                        )
                    )

        usage_obj = getattr(resp, "usage", None)
        usage = UsageStats(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
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
        t0 = time.monotonic()
        model_str = self._build_model_str(model)
        resp = self._call_litellm(
            messages=messages,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=False,
            **kwargs,
        )
        result = self._parse_response(resp, model_str)
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
        resp = self._call_litellm(
            messages=messages,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=True,
            **kwargs,
        )
        for chunk in resp:
            if chunk.choices:
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    yield text

    def health_check(self) -> bool:
        """Quick connectivity check based on API key presence."""
        return self._get_api_key() is not None
