"""Unit tests for maglab.llm.backends.

litellm.completion, subprocess, and the Ollama client are all mocked.
No real API/network/process calls are made.
"""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maglab.llm.base import Message, Role

# ---------------------------------------------------------------------------
# APIBackend tests
# ---------------------------------------------------------------------------


class TestAPIBackend:
    """Tests for the LiteLLM-based direct API backend."""

    def _make_mock_litellm_response(
        self,
        content: str = "test response",
        finish_reason: str = "stop",
        tool_calls: list[Any] | None = None,
        prompt_tokens: int = 10,
        completion_tokens: int = 20,
    ) -> MagicMock:
        """Create a mock resembling a litellm.completion return value."""
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = content
        choice.finish_reason = finish_reason
        choice.message.tool_calls = tool_calls
        resp.choices = [choice]
        resp.usage.prompt_tokens = prompt_tokens
        resp.usage.completion_tokens = completion_tokens
        resp.usage.total_tokens = prompt_tokens + completion_tokens
        return resp

    def test_complete_returns_llmresponse(self) -> None:
        """complete() returns an LLMResponse."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="anthropic", model="claude-opus-4-7")
        messages = [Message(role=Role.USER, content="ping")]
        mock_resp = self._make_mock_litellm_response("pong")

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="test-key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            result = backend.complete(messages)

        assert result.content == "pong"
        assert result.stop_reason == "stop"
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 20
        mock_litellm.assert_called_once()

    def test_complete_adds_anthropic_prefix(self) -> None:
        """The anthropic provider prepends a prefix to the litellm model string."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="anthropic", model="claude-opus-4-7")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            backend.complete(messages)

        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs["model"].startswith("anthropic/")

    def test_complete_no_prefix_for_openai(self) -> None:
        """The openai provider does not prepend a prefix."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="openai", model="gpt-4o")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            backend.complete(messages)

        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    def test_complete_gemini_prefix(self) -> None:
        """The gemini provider prepends the gemini/ prefix."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="gemini", model="gemini-3.5-flash")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            backend.complete(messages)

        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs["model"].startswith("gemini/")

    def test_complete_alias_google_maps_to_gemini(self) -> None:
        """The old google alias still maps to the Gemini API profile."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="google", model="gemini-3.5-flash")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            backend.complete(messages)

        call_kwargs = mock_litellm.call_args[1]
        assert backend.provider == "gemini"
        assert call_kwargs["model"] == "gemini/gemini-3.5-flash"

    def test_complete_grok_prefix_and_env_injection(self) -> None:
        """Grok uses the xai/ LiteLLM prefix and XAI_API_KEY environment variable."""
        import os

        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="grok", model="grok-4.3")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()
        captured_env: dict[str, str | None] = {}

        def capture_completion(**kwargs: Any) -> Any:
            captured_env["XAI_API_KEY"] = os.environ.get("XAI_API_KEY")
            return mock_resp

        old_value = os.environ.get("XAI_API_KEY")
        try:
            os.environ.pop("XAI_API_KEY", None)
            with (
                patch("maglab.llm.backends.api.get_api_key", return_value="xai-key"),
                patch("litellm.completion", side_effect=capture_completion) as mock_litellm,
            ):
                backend.complete(messages)

            call_kwargs = mock_litellm.call_args[1]
            assert call_kwargs["model"] == "xai/grok-4.3"
            assert captured_env["XAI_API_KEY"] == "xai-key"
            assert os.environ.get("XAI_API_KEY") is None
        finally:
            if old_value is not None:
                os.environ["XAI_API_KEY"] = old_value

    def test_complete_qwen_prefix(self) -> None:
        """Qwen uses DashScope's LiteLLM provider prefix."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="qwen", model="qwen3.5-plus")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            backend.complete(messages)

        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs["model"] == "dashscope/qwen3.5-plus"

    def test_incompatible_stage_model_falls_back_to_backend_default(self) -> None:
        """A Claude route does not override an OpenAI API backend."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="openai", model="gpt-4o")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            backend.complete(messages, model="claude-opus-4-7")

        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    def test_complete_parses_tool_calls(self) -> None:
        """tool_calls in the response are parsed correctly."""
        from maglab.llm.backends.api import APIBackend

        tc = MagicMock()
        tc.id = "call-123"
        tc.function.name = "get_data"
        tc.function.arguments = '{"key": "val"}'

        mock_resp = self._make_mock_litellm_response(
            content=None,
            finish_reason="tool_calls",
            tool_calls=[tc],
        )

        backend = APIBackend(provider="openai", model="gpt-4o")
        messages = [Message(role=Role.USER, content="use tool")]

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp),
        ):
            result = backend.complete(messages)

        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_data"
        assert result.tool_calls[0].arguments == {"key": "val"}

    def test_complete_retries_on_rate_limit(self) -> None:
        """Retries on RateLimitError."""
        import litellm as _litellm

        from maglab.llm.backends.api import APIBackend

        mock_resp = self._make_mock_litellm_response("retry success")
        backend = APIBackend(
            provider="anthropic", model="claude-opus-4-7", max_retries=2, retry_delay=0.0
        )
        messages = [Message(role=Role.USER, content="hi")]

        call_count = 0

        def side_effect(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _litellm.RateLimitError(
                    message="rate limited", llm_provider="anthropic", model="claude-opus-4-7"
                )
            return mock_resp

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", side_effect=side_effect),
        ):
            result = backend.complete(messages)

        assert result.content == "retry success"
        assert call_count == 2

    def test_stream_yields_text_chunks(self) -> None:
        """stream() yields text chunks."""
        from maglab.llm.backends.api import APIBackend

        def _make_chunk(text: str | None) -> MagicMock:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = text
            return chunk

        chunks = [_make_chunk("Hello"), _make_chunk(", "), _make_chunk("world"), _make_chunk(None)]

        backend = APIBackend(provider="anthropic", model="claude-opus-4-7")
        messages = [Message(role=Role.USER, content="stream me")]

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=iter(chunks)),
        ):
            result = list(backend.stream(messages))

        assert result == ["Hello", ", ", "world"]

    def test_health_check_true_with_key(self) -> None:
        """health_check() returns True when an API key is present."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="anthropic")
        with patch("maglab.llm.backends.api.get_api_key", return_value="sk-test"):
            assert backend.health_check() is True

    def test_health_check_false_without_key(self) -> None:
        """health_check() returns False when no API key is present."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="anthropic")
        with patch("maglab.llm.backends.api.get_api_key", return_value=None):
            assert backend.health_check() is False

    def test_api_key_injected_into_env_then_restored(self) -> None:
        """API key is temporarily injected into the environment and then restored."""
        import os

        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(provider="anthropic", model="claude-opus-4-7")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        captured_env: dict[str, str | None] = {}

        def capture_completion(**kwargs: Any) -> Any:
            captured_env["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY")
            return mock_resp

        original_val = os.environ.get("ANTHROPIC_API_KEY")
        try:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with (
                patch("maglab.llm.backends.api.get_api_key", return_value="injected-key"),
                patch("litellm.completion", side_effect=capture_completion),
            ):
                backend.complete(messages)

            assert captured_env.get("ANTHROPIC_API_KEY") == "injected-key"
            assert os.environ.get("ANTHROPIC_API_KEY") is None  # restored
        finally:
            if original_val is not None:
                os.environ["ANTHROPIC_API_KEY"] = original_val

    def test_base_url_passed_to_litellm(self) -> None:
        """base_url is forwarded to litellm as api_base when present."""
        from maglab.llm.backends.api import APIBackend

        backend = APIBackend(
            provider="openai-compatible",
            model="local-model",
            base_url="http://localhost:8080",
        )
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_litellm_response()

        with (
            patch("maglab.llm.backends.api.get_api_key", return_value="key"),
            patch("litellm.completion", return_value=mock_resp) as mock_litellm,
        ):
            backend.complete(messages)

        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs.get("api_base") == "http://localhost:8080"


# ---------------------------------------------------------------------------
# LocalBackend (Ollama) tests
# ---------------------------------------------------------------------------


class TestLocalBackend:
    """Tests for the Ollama-based local backend."""

    def _make_mock_ollama_response(self, content: str = "local response") -> MagicMock:
        """Create a mock resembling an ollama chat response."""
        resp = MagicMock()
        resp.message.content = content
        resp.eval_count = 20
        resp.prompt_eval_count = 10
        return resp

    def test_complete_returns_llmresponse(self) -> None:
        """complete() returns an LLMResponse."""
        from maglab.llm.backends.local import LocalBackend

        backend = LocalBackend(model="llama3.2")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_ollama_response("local answer")

        mock_client = MagicMock()
        mock_client.list.return_value = MagicMock(models=[])
        mock_client.chat.return_value = mock_resp

        with patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client):
            result = backend.complete(messages)

        assert result.content == "local answer"
        assert result.model == "llama3.2"

    def test_complete_passes_options(self) -> None:
        """temperature and max_tokens are forwarded as options."""
        from maglab.llm.backends.local import LocalBackend

        backend = LocalBackend(model="mistral")
        messages = [Message(role=Role.USER, content="hi")]
        mock_resp = self._make_mock_ollama_response()

        mock_client = MagicMock()
        mock_client.list.return_value = MagicMock(models=[])
        mock_client.chat.return_value = mock_resp

        with patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client):
            backend.complete(messages, temperature=0.7, max_tokens=512)

        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["options"]["temperature"] == pytest.approx(0.7)
        assert call_kwargs["options"]["num_predict"] == 512

    def test_stream_yields_chunks(self) -> None:
        """stream() yields text chunks."""
        from maglab.llm.backends.local import LocalBackend

        def _make_chunk(text: str) -> MagicMock:
            c = MagicMock()
            c.message.content = text
            return c

        chunks = [_make_chunk("a"), _make_chunk("b"), _make_chunk("c")]

        backend = LocalBackend(model="llama3.2")
        messages = [Message(role=Role.USER, content="stream")]

        mock_client = MagicMock()
        mock_client.list.return_value = MagicMock(models=[])
        mock_client.chat.return_value = iter(chunks)

        with patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client):
            result = list(backend.stream(messages))

        assert result == ["a", "b", "c"]

    def test_health_check_true_when_ollama_running(self) -> None:
        """health_check() returns True when Ollama is running."""
        from maglab.llm.backends.local import LocalBackend

        backend = LocalBackend()
        mock_client = MagicMock()
        mock_client.list.return_value = MagicMock(models=[])

        with patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client):
            assert backend.health_check() is True

    def test_health_check_false_when_ollama_not_running(self) -> None:
        """health_check() returns False when Ollama is not running."""
        from maglab.llm.backends.local import LocalBackend

        backend = LocalBackend()
        mock_client = MagicMock()
        mock_client.list.side_effect = ConnectionError("Ollama not running")

        with patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client):
            assert backend.health_check() is False

    def test_complete_raises_connection_error_when_not_running(self) -> None:
        """Raises ConnectionError when Ollama is not running."""
        from maglab.llm.backends.local import LocalBackend

        backend = LocalBackend()
        messages = [Message(role=Role.USER, content="hi")]
        mock_client = MagicMock()
        mock_client.list.side_effect = ConnectionError("connection refused")

        with (
            patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client),
            pytest.raises(ConnectionError, match="Ollama"),
        ):
            backend.complete(messages)

    def test_list_models_returns_model_names(self) -> None:
        """list_models() returns the names of installed models."""
        from maglab.llm.backends.local import LocalBackend

        backend = LocalBackend()

        m1 = MagicMock()
        m1.model = "llama3.2"
        m2 = MagicMock()
        m2.model = "mistral"

        mock_client = MagicMock()
        mock_client.list.return_value = MagicMock(models=[m1, m2])

        with patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client):
            models = backend.list_models()

        assert "llama3.2" in models
        assert "mistral" in models

    def test_messages_converted_to_ollama_format(self) -> None:
        """Message list is converted to Ollama chat format."""
        from maglab.llm.backends.local import LocalBackend

        backend = LocalBackend(model="llama3.2")
        messages = [
            Message(role=Role.SYSTEM, content="You are helpful."),
            Message(role=Role.USER, content="Hello"),
        ]
        mock_resp = self._make_mock_ollama_response()
        mock_client = MagicMock()
        mock_client.list.return_value = MagicMock(models=[])
        mock_client.chat.return_value = mock_resp

        with patch("maglab.llm.backends.local.LocalBackend._get_client", return_value=mock_client):
            backend.complete(messages)

        call_kwargs = mock_client.chat.call_args[1]
        msg_list = call_kwargs["messages"]
        assert msg_list[0]["role"] == "system"
        assert msg_list[0]["content"] == "You are helpful."
        assert msg_list[1]["role"] == "user"


# ---------------------------------------------------------------------------
# DelegatedCLIBackend tests
# ---------------------------------------------------------------------------


class TestDelegatedCLIBackend:
    """Tests for the CLI subprocess delegated backend."""

    def _make_mock_proc(
        self,
        stdout: str = '{"content": "cli response"}',
        returncode: int = 0,
        stderr: str = "",
    ) -> MagicMock:
        proc = MagicMock()
        proc.stdout = stdout
        proc.stderr = stderr
        proc.returncode = returncode
        return proc

    def test_complete_returns_llmresponse(self) -> None:
        """complete() returns an LLMResponse."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude", model="claude-opus-4-7")
        messages = [Message(role=Role.USER, content="hi")]
        mock_proc = self._make_mock_proc('{"content": "cli answer"}')

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = backend.complete(messages)

        assert result.content == "cli answer"

    def test_complete_parses_json_content_field(self) -> None:
        """The JSON content field is parsed correctly."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude")
        messages = [Message(role=Role.USER, content="q")]
        mock_proc = self._make_mock_proc('{"content": "answer here"}')

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = backend.complete(messages)

        assert result.content == "answer here"

    def test_complete_falls_back_to_raw_text(self) -> None:
        """Non-JSON stdout is treated as raw text."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude")
        messages = [Message(role=Role.USER, content="q")]
        mock_proc = self._make_mock_proc("plain text response")

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = backend.complete(messages)

        assert result.content == "plain text response"

    def test_complete_raises_on_nonzero_exit(self) -> None:
        """Raises RuntimeError when the CLI exits with a non-zero code."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude")
        messages = [Message(role=Role.USER, content="q")]
        mock_proc = self._make_mock_proc("", returncode=1, stderr="CLI error")

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("subprocess.run", return_value=mock_proc),
            pytest.raises(RuntimeError, match="exit code"),
        ):
            backend.complete(messages)

    def test_complete_raises_timeout_error(self) -> None:
        """Raises TimeoutError on timeout."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude", timeout=5.0)
        messages = [Message(role=Role.USER, content="q")]

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 5.0)),
            pytest.raises(TimeoutError, match="5.0 s"),
        ):
            backend.complete(messages)

    def test_health_check_true_when_cli_exists(self) -> None:
        """health_check() returns True when the CLI is on PATH."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude")
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            assert backend.health_check() is True

    def test_health_check_false_when_cli_missing(self) -> None:
        """health_check() returns False when the CLI is missing."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude")
        with patch("shutil.which", return_value=None):
            assert backend.health_check() is False

    def test_find_executable_raises_file_not_found(self) -> None:
        """Raises FileNotFoundError when the CLI is missing."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="nonexistent_cli")
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(FileNotFoundError, match="PATH"),
        ):
            backend._find_executable()

    def test_stream_delegates_to_complete(self) -> None:
        """stream() delegates to complete() and yields the result."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude")
        messages = [Message(role=Role.USER, content="q")]
        mock_proc = self._make_mock_proc("stream output")

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            chunks = list(backend.stream(messages))

        assert chunks == ["stream output"]

    def test_codex_cli_command_structure(self) -> None:
        """The codex CLI uses the correct command structure."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="codex", model="gpt-4o")
        messages = [Message(role=Role.USER, content="run code")]
        mock_proc = self._make_mock_proc('{"content": "done"}')

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            backend.complete(messages)

        cmd = mock_run.call_args[0][0]
        assert "codex" in cmd[0]
        assert "exec" in cmd

    def test_codex_cli_skips_git_repo_check(self) -> None:
        """Codex must run outside a Git repo — MagLab launches from any folder."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="codex", model="gpt-4o")
        messages = [Message(role=Role.USER, content="ping")]
        mock_proc = self._make_mock_proc('{"content": "done"}')

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            backend.complete(messages)

        cmd = mock_run.call_args[0][0]
        assert "--skip-git-repo-check" in cmd

    def test_codex_jsonl_agent_message_parsed(self) -> None:
        """Codex JSONL transport events are reduced to the agent message only."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        stdout = "\n".join(
            [
                '{"type":"thread.started","thread_id":"019e4418-156b-7203-bb5a-04a614196fbf"}',
                '{"type":"turn.started"}',
                '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"MAGLAB_LLM_OK\\n/tmp/project"}}',
                '{"type":"turn.completed","usage":{"input_tokens":50988,"cached_input_tokens":3456,"output_tokens":109,"reasoning_output_tokens":86}}',
            ]
        )
        backend = DelegatedCLIBackend(cli="codex", model="")
        messages = [Message(role=Role.USER, content="ping")]
        mock_proc = self._make_mock_proc(stdout)

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = backend.complete(messages)

        assert result.content == "MAGLAB_LLM_OK\n/tmp/project"
        assert "thread.started" not in result.content
        assert "50988" not in result.content
        assert result.usage.prompt_tokens == 50988
        assert result.usage.completion_tokens == 109
        assert result.metadata["parse_mode"] == "codex_jsonl"
        assert result.metadata["thread_id"] == "019e4418-156b-7203-bb5a-04a614196fbf"

    def test_codex_jsonl_command_event_maps_to_trace(self) -> None:
        """Codex command/tool transport events expose file references for MagLab trace UI."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="codex", model="")
        event = {
            "type": "item.started",
            "item": {
                "type": "command_execution",
                "command": "python maglab/llm/tools.py README.md",
            },
        }

        trace = backend._codex_trace_event(event)

        assert trace is not None
        assert trace["kind"] == "tool_start"
        assert trace["tool"] == "codex:command_execution"
        assert trace["source"] == "maglab/llm/tools.py"
        assert "README.md" in trace["references"]

    def test_codex_jsonl_trace_line_emits_to_sink(self) -> None:
        """Delegated Codex trace events are forwarded to the interactive renderer sink."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        events: list[dict[str, object]] = []
        backend = DelegatedCLIBackend(cli="codex", model="", event_sink=events.append)
        line = (
            '{"type":"item.completed","item":{"type":"command_execution",'
            '"command":"python maglab/llm/tools.py README.md"}}'
        )

        backend._emit_codex_trace_line(line)

        assert events
        assert events[0]["kind"] == "tool_done"
        assert events[0]["tool"] == "codex:command_execution"
        assert "README.md" in events[0]["references"]

    def test_codex_jsonl_error_event_surfaces_cleanly(self) -> None:
        """A Codex error event is raised without returning raw JSONL as an answer."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        stdout = '{"type":"error","message":"not authenticated"}'
        backend = DelegatedCLIBackend(cli="codex", model="")
        messages = [Message(role=Role.USER, content="ping")]
        mock_proc = self._make_mock_proc(stdout)

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc),
            pytest.raises(RuntimeError, match="not authenticated"),
        ):
            backend.complete(messages)

    def test_codex_nonzero_exit_prefers_jsonl_error_message(self) -> None:
        """Codex non-zero exits should surface JSONL errors instead of generic stderr."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        stdout = "\n".join(
            [
                '{"type":"thread.started","thread_id":"thread_1"}',
                '{"type":"turn.started"}',
                '{"type":"error","message":"usage limit reached"}',
                '{"type":"turn.failed","error":{"message":"usage limit reached"}}',
            ]
        )
        backend = DelegatedCLIBackend(cli="codex", model="")
        messages = [Message(role=Role.USER, content="ping")]
        mock_proc = self._make_mock_proc(
            stdout,
            returncode=1,
            stderr="Reading additional input from stdin...",
        )

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc),
            pytest.raises(RuntimeError, match="usage limit reached"),
        ):
            backend.complete(messages)

    def test_codex_turn_failed_nested_error_surfaces_cleanly(self) -> None:
        """Codex turn.failed events can carry nested error dictionaries."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        stdout = '{"type":"turn.failed","error":{"message":"model quota exhausted"}}'
        backend = DelegatedCLIBackend(cli="codex", model="")
        messages = [Message(role=Role.USER, content="ping")]
        mock_proc = self._make_mock_proc(stdout, returncode=1, stderr="transport stderr")

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc),
            pytest.raises(RuntimeError, match="model quota exhausted"),
        ):
            backend.complete(messages)

    def test_codex_cli_omits_model_flag_when_default_model_blank(self) -> None:
        """Codex delegated mode can rely on the user's authenticated CLI default model."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="codex", model="")
        messages = [Message(role=Role.USER, content="run code")]
        mock_proc = self._make_mock_proc('{"content": "done"}')

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            backend.complete(messages, model=None)

        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    def test_codex_cli_omits_model_flag_when_default_model_none(self) -> None:
        """A None default model also omits --model for Codex."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="codex", model=None)  # type: ignore[arg-type]
        messages = [Message(role=Role.USER, content="run code")]
        mock_proc = self._make_mock_proc('{"content": "done"}')

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            backend.complete(messages, model=None)

        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    def test_codex_cli_omits_model_flag_when_explicit_model_blank(self) -> None:
        """A blank per-call model override also omits --model for Codex."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="codex", model="gpt-4o")
        messages = [Message(role=Role.USER, content="run code")]
        mock_proc = self._make_mock_proc('{"content": "done"}')

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            backend.complete(messages, model="")

        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    def test_codex_cli_ignores_incompatible_stage_model(self) -> None:
        """A Claude stage route does not get passed to Codex delegated mode."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="codex", model=None)
        messages = [Message(role=Role.USER, content="run code")]
        mock_proc = self._make_mock_proc('{"content": "done"}')

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            backend.complete(messages, model="claude-opus-4-7")

        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    def test_get_cli_version(self) -> None:
        """get_cli_version() returns the version string."""
        from maglab.llm.backends.delegated_cli import DelegatedCLIBackend

        backend = DelegatedCLIBackend(cli="claude")
        mock_proc = MagicMock()
        mock_proc.stdout = "claude v1.2.3"
        mock_proc.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            version = backend.get_cli_version()

        assert version == "claude v1.2.3"
