"""Delegated CLI backend — based on official CLI subprocesses (claude · codex · gemini).

§7.2: Delegated mode implementation. Invokes official CLI tools installed on the system
as subprocesses. Uses each CLI's non-interactive flags and parses stdout to return
``LLMResponse``.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from collections.abc import Iterator
from typing import Any

from maglab.llm.base import (
    LLMBackend,
    LLMResponse,
    Message,
    UsageStats,
)
from maglab.llm.providers import is_model_compatible

log = logging.getLogger(__name__)

# CLI name → executable name mapping
_CLI_EXECUTABLES: dict[str, str] = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
}

# CLI name → non-interactive execution flags
_CLI_NON_INTERACTIVE_FLAGS: dict[str, list[str]] = {
    "claude": ["--output-format", "json", "--print"],
    "codex": ["exec", "--json"],
    "gemini": ["--format", "json", "--non-interactive"],
}


def _int_value(value: object) -> int:
    """Best-effort integer conversion for CLI usage counters."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _extract_text_from_cli_item(item: dict[str, Any]) -> str:
    """Extract text from a delegated CLI message item."""
    text = item.get("text")
    if isinstance(text, str):
        return text

    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                block_text = block.get("text") or block.get("content")
                if isinstance(block_text, str):
                    parts.append(block_text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)

    return ""


class DelegatedCLIBackend(LLMBackend):
    """Delegated backend based on official CLI subprocesses.

    Invokes the ``claude``·``codex``·``gemini`` CLI installed on the system as
    subprocesses. Raises ``FileNotFoundError`` if the CLI is not installed.

    Args:
        cli: CLI name to use (``"claude"``·``"codex"``·``"gemini"``).
        model: Default model identifier. When omitted/blank, the official CLI
            decides its own default model.
        timeout: Subprocess timeout in seconds.
        extra_flags: Additional flags to append to the CLI invocation.
    """

    def __init__(
        self,
        cli: str = "claude",
        model: str | None = "claude-opus-4-7",
        timeout: float = 120.0,
        extra_flags: list[str] | None = None,
    ) -> None:
        self.cli = cli
        self.default_model = model or ""
        self.timeout = timeout
        self.extra_flags: list[str] = extra_flags or []

    def _find_executable(self) -> str:
        """Locate the CLI executable path.

        Returns:
            Full path to the executable.

        Raises:
            FileNotFoundError: When the CLI is not found on PATH.
        """
        exe_name = _CLI_EXECUTABLES.get(self.cli, self.cli)
        path = shutil.which(exe_name)
        if path is None:
            if exe_name == "codex":
                hint = (
                    "Install and authenticate the official Codex CLI, then run `maglab auth codex`."
                )
            elif exe_name == "claude":
                hint = "Install and authenticate the official Claude CLI, then run `maglab auth claude`."
            elif exe_name == "gemini":
                hint = "Install and authenticate the official Gemini CLI, then run `maglab auth gemini-cli`."
            else:
                hint = "Install the official CLI first."
            raise FileNotFoundError(f"CLI '{exe_name}' not found on PATH. {hint}")
        return path

    def _build_prompt(self, messages: list[Message]) -> str:
        """Combine a message list into a single prompt string for the CLI."""
        parts: list[str] = []
        for msg in messages:
            role_label = msg.role.value.upper()
            if isinstance(msg.content, str):
                content = msg.content
            else:
                content = "\n".join(
                    b.text or b.content or "" for b in msg.content if (b.text or b.content)
                )
            parts.append(f"[{role_label}]\n{content}")
        return "\n\n".join(parts)

    def _resolve_cli_model(self, model: str | None) -> str:
        """Resolve optional model overrides for delegated CLI commands."""
        provider_for_cli = {"codex": "openai", "gemini": "gemini", "claude": "anthropic"}.get(
            self.cli
        )
        if provider_for_cli and not is_model_compatible(provider_for_cli, model):
            model = None
        resolved = model if model is not None else self.default_model
        return (resolved or "").strip()

    def _build_cmd(
        self,
        prompt: str,
        model: str | None,
    ) -> list[str]:
        """Construct the subprocess command list."""
        exe = self._find_executable()
        resolved_model = self._resolve_cli_model(model)
        base_flags = _CLI_NON_INTERACTIVE_FLAGS.get(self.cli, [])

        cmd: list[str] = [exe]

        # claude CLI handling
        if self.cli == "claude":
            cmd += base_flags  # --output-format json --print
            if resolved_model:
                cmd += ["--model", resolved_model]
            cmd += self.extra_flags
            cmd += [prompt]

        # codex CLI handling
        elif self.cli == "codex":
            cmd += base_flags  # exec --json
            if resolved_model:
                cmd += ["--model", resolved_model]
            cmd += self.extra_flags
            cmd += [prompt]

        # gemini CLI handling
        elif self.cli == "gemini":
            cmd += base_flags  # --format json --non-interactive
            if resolved_model:
                cmd += ["--model", resolved_model]
            cmd += self.extra_flags
            cmd += [prompt]

        else:
            # Unknown CLI — default pattern
            cmd += self.extra_flags
            cmd += [prompt]

        return cmd

    def _parse_stdout(self, stdout: str, model_str: str) -> LLMResponse:
        """Parse CLI stdout and return ``LLMResponse``.

        Attempts JSON parsing first; falls back to raw text on failure.
        """
        if self.cli == "codex":
            parsed = self._parse_codex_jsonl_stdout(stdout, model_str)
            if parsed is not None:
                return parsed

        content: str | None = None
        usage = UsageStats()
        metadata: dict[str, Any] = {}

        try:
            data = json.loads(stdout.strip())
            # claude CLI JSON output format
            if isinstance(data, dict):
                # claude --output-format json format
                content = (
                    data.get("content")
                    or data.get("result")
                    or data.get("text")
                    or data.get("response")
                )
                if content is None and "choices" in data:
                    choices = data["choices"]
                    if choices:
                        content = choices[0].get("message", {}).get("content")
            elif isinstance(data, str):
                content = data
            elif isinstance(data, list) and data:
                # Array-format response
                first = data[0]
                if isinstance(first, dict):
                    content = first.get("text") or first.get("content")
                elif isinstance(first, str):
                    content = first
        except (json.JSONDecodeError, ValueError):
            # Not JSON — use raw text as-is
            content = stdout.strip() or None

        if content is not None:
            content = content.strip() or None

        return LLMResponse(
            content=content,
            tool_calls=[],
            stop_reason="end_turn",
            usage=usage,
            raw=stdout,
            metadata=metadata,
            model=model_str,
        )

    def _parse_codex_jsonl_stdout(self, stdout: str, model_str: str) -> LLMResponse | None:
        """Parse Codex ``exec --json`` JSONL transport events.

        Codex emits one JSON object per line. Only completed agent-message
        payloads are user-facing content; thread IDs and token usage remain
        transport metadata so HonestyGate never treats them as scientific
        claims.
        """
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return LLMResponse(content=None, raw=stdout, model=model_str)

        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return None
            if not isinstance(event, dict):
                return None
            events.append(event)

        if not any(isinstance(event.get("type"), str) for event in events):
            return None

        messages: list[str] = []
        usage = UsageStats()
        thread_id = ""
        errors: list[str] = []

        for event in events:
            event_type = event.get("type")
            if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
                thread_id = event["thread_id"]
                continue

            if event_type == "turn.completed":
                raw_usage = event.get("usage")
                if isinstance(raw_usage, dict):
                    prompt_tokens = _int_value(raw_usage.get("input_tokens"))
                    completion_tokens = _int_value(raw_usage.get("output_tokens"))
                    usage.prompt_tokens = prompt_tokens
                    usage.completion_tokens = completion_tokens
                    usage.total_tokens = prompt_tokens + completion_tokens
                continue

            if event_type == "error":
                message = event.get("message") or event.get("error") or "unknown Codex error"
                errors.append(str(message))
                continue

            if event_type != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") != "agent_message":
                continue
            text = _extract_text_from_cli_item(item)
            if text:
                messages.append(text)

        if errors and not messages:
            raise RuntimeError(f"CLI 'codex' reported error: {errors[0]}")

        content = "\n".join(message.strip() for message in messages if message.strip())
        return LLMResponse(
            content=content or None,
            tool_calls=[],
            stop_reason="end_turn",
            usage=usage,
            raw=stdout,
            metadata={
                "parse_mode": "codex_jsonl",
                "thread_id": thread_id,
                "event_count": len(events),
            },
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
        """Non-streaming completion request via CLI subprocess."""
        model_str = self._resolve_cli_model(model) or f"{self.cli}:default"
        prompt = self._build_prompt(messages)
        cmd = self._build_cmd(prompt, model)

        log.debug("DelegatedCLI executing: %s", cmd[:3])

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"CLI '{self.cli}' did not complete within {self.timeout} s."
            ) from exc
        except FileNotFoundError:
            raise

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            raise RuntimeError(f"CLI '{self.cli}' exit code {proc.returncode}: {stderr[:200]}")

        result = self._parse_stdout(proc.stdout, model_str)
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
        """Streaming completion request via CLI subprocess.

        Yields the full response at once when the CLI does not support streaming.
        """
        result = self.complete(
            messages,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            **kwargs,
        )
        if result.content:
            yield result.content

    def health_check(self) -> bool:
        """Connectivity check based on CLI executable presence."""
        try:
            self._find_executable()
            return True
        except FileNotFoundError:
            return False

    def get_cli_version(self) -> str | None:
        """Return the CLI version string.

        Returns:
            Version string, or None if retrieval fails.
        """
        try:
            exe = self._find_executable()
            proc = subprocess.run(
                [exe, "--version"],
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
            )
            return proc.stdout.strip() or proc.stderr.strip() or None
        except Exception:
            return None
