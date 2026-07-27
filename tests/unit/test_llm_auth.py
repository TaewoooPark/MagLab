"""Unit tests for maglab.llm.auth.

All external calls (keyring, auth.json file I/O, litellm) are mocked.
No real API/network calls are made.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maglab.llm.auth import (
    _auth_json_get,
    _auth_json_set,
    _keyring_available,
    _keyring_get,
    _keyring_set,
    check_auth_json_permissions,
    delete_api_key,
    get_api_key,
    list_providers,
    store_api_key,
    verify_connection,
)

# ---------------------------------------------------------------------------
# get_api_key — priority tests
# ---------------------------------------------------------------------------


class TestGetApiKeyPriority:
    """get_api_key() priority: env var > keyring > auth.json."""

    def test_env_var_priority_over_keyring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variable takes priority over keyring."""
        monkeypatch.setenv("MAGLAB_ANTHROPIC_API_KEY", "env-key-123")

        with patch("maglab.llm.auth._keyring_get", return_value="keyring-key") as mock_kr:
            result = get_api_key("anthropic")

        assert result == "env-key-123"
        mock_kr.assert_not_called()

    def test_env_var_direct_pattern(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Direct ANTHROPIC_API_KEY environment variable is also supported."""
        monkeypatch.delenv("MAGLAB_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "direct-env-key")

        with (
            patch("maglab.llm.auth._keyring_get", return_value=None),
            patch("maglab.llm.auth._auth_json_get", return_value=None),
        ):
            result = get_api_key("anthropic")

        assert result == "direct-env-key"

    def test_keyring_priority_over_auth_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """keyring takes priority over auth.json."""
        monkeypatch.delenv("MAGLAB_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with (
            patch("maglab.llm.auth._keyring_get", return_value="keyring-key"),
            patch("maglab.llm.auth._auth_json_get", return_value="json-key") as mock_json,
        ):
            result = get_api_key("anthropic")

        assert result == "keyring-key"
        mock_json.assert_not_called()

    def test_auth_json_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to auth.json when env var and keyring are absent."""
        monkeypatch.delenv("MAGLAB_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with (
            patch("maglab.llm.auth._keyring_get", return_value=None),
            patch("maglab.llm.auth._auth_json_get", return_value="json-fallback"),
        ):
            result = get_api_key("anthropic")

        assert result == "json-fallback"

    def test_returns_none_when_all_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when no key is found from any source."""
        monkeypatch.delenv("MAGLAB_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with (
            patch("maglab.llm.auth._keyring_get", return_value=None),
            patch("maglab.llm.auth._auth_json_get", return_value=None),
        ):
            result = get_api_key("anthropic")

        assert result is None

    def test_all_providers_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reads the environment variable for each provider correctly."""
        from maglab.llm.providers import api_provider_keys, get_provider_profile

        env_map = {
            provider: get_provider_profile(provider).maglab_env_var
            for provider in api_provider_keys()
        }
        for provider, env_var in env_map.items():
            monkeypatch.setenv(env_var, f"key-for-{provider}")

        for provider in env_map:
            result = get_api_key(provider)
            assert result == f"key-for-{provider}", f"provider={provider}"


# ---------------------------------------------------------------------------
# keyring tests
# ---------------------------------------------------------------------------


class TestKeyring:
    def test_keyring_get_returns_value(self) -> None:
        """Reads a value from keyring successfully."""
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "kr-secret"

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = _keyring_get("anthropic")

        assert result == "kr-secret"
        mock_keyring.get_password.assert_called_once_with("maglab", "anthropic")

    def test_keyring_get_returns_none_on_error(self) -> None:
        """Returns None on keyring error."""
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = RuntimeError("keyring error")

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = _keyring_get("anthropic")

        assert result is None

    def test_keyring_set_success(self) -> None:
        """Stores a value in keyring successfully."""
        mock_keyring = MagicMock()

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = _keyring_set("openai", "sk-test-key")

        assert result is True
        mock_keyring.set_password.assert_called_once_with("maglab", "openai", "sk-test-key")

    def test_keyring_available_true(self) -> None:
        """Returns True when the keyring package is available."""
        mock_keyring = MagicMock()
        with (
            patch.dict("sys.modules", {"keyring": mock_keyring}),
            patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **k: (
                    mock_keyring if name == "keyring" else __import__(name, *a, **k)
                ),
            ),
        ):
            # _keyring_available attempts its own import
            pass
        # Return type is always bool regardless of installation
        assert isinstance(_keyring_available(), bool)

    def test_keyring_available_false_on_import_error(self) -> None:
        """Returns False when keyring is not installed."""
        import sys

        original = sys.modules.get("keyring", None)
        try:
            sys.modules["keyring"] = None  # type: ignore[assignment]
            result = _keyring_available()
            assert result is False
        finally:
            if original is None:
                sys.modules.pop("keyring", None)
            else:
                sys.modules["keyring"] = original


# ---------------------------------------------------------------------------
# auth.json tests
# ---------------------------------------------------------------------------


class TestAuthJson:
    def test_auth_json_set_and_get(self, tmp_path: Path) -> None:
        """Stores and retrieves a value in auth.json."""
        json_path = tmp_path / "auth.json"

        with (
            patch("maglab.llm.auth._AUTH_JSON_PATH", json_path),
            patch("maglab.llm.auth._ensure_auth_json_secure", return_value=json_path),
        ):
            # Initialise with empty JSON
            json_path.write_text("{}\n", encoding="utf-8")

            _auth_json_set("anthropic", "json-secret")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert data["anthropic"] == "json-secret"

    def test_auth_json_get_missing_key(self, tmp_path: Path) -> None:
        """Returns None for a key that does not exist."""
        json_path = tmp_path / "auth.json"
        json_path.write_text('{"openai": "other-key"}\n', encoding="utf-8")

        with patch("maglab.llm.auth._ensure_auth_json_secure", return_value=json_path):
            result = _auth_json_get("anthropic")

        assert result is None

    def test_auth_json_get_returns_value(self, tmp_path: Path) -> None:
        """Reads a value from auth.json successfully."""
        json_path = tmp_path / "auth.json"
        json_path.write_text('{"anthropic": "my-key"}\n', encoding="utf-8")

        with patch("maglab.llm.auth._ensure_auth_json_secure", return_value=json_path):
            result = _auth_json_get("anthropic")

        assert result == "my-key"

    def test_auth_json_get_on_parse_error(self, tmp_path: Path) -> None:
        """Returns None on JSON parse error."""
        json_path = tmp_path / "auth.json"
        json_path.write_text("not valid json{{{\n", encoding="utf-8")

        with patch("maglab.llm.auth._ensure_auth_json_secure", return_value=json_path):
            result = _auth_json_get("anthropic")

        assert result is None


# ---------------------------------------------------------------------------
# store_api_key / delete_api_key tests
# ---------------------------------------------------------------------------


class TestStoreDeleteApiKey:
    def test_store_prefers_keyring(self) -> None:
        """Stores in keyring when keyring is available."""
        with (
            patch("maglab.llm.auth._keyring_available", return_value=True),
            patch("maglab.llm.auth._keyring_set", return_value=True) as mock_ks,
        ):
            location = store_api_key("anthropic", "test-key")

        assert location == "keyring"
        mock_ks.assert_called_once_with("anthropic", "test-key")

    def test_store_falls_back_to_auth_json(self) -> None:
        """Falls back to auth.json when keyring storage fails."""
        with (
            patch("maglab.llm.auth._keyring_available", return_value=True),
            patch("maglab.llm.auth._keyring_set", return_value=False),
            patch("maglab.llm.auth._auth_json_set", return_value=True) as mock_js,
        ):
            location = store_api_key("anthropic", "test-key")

        assert location == "auth.json"
        mock_js.assert_called_once_with("anthropic", "test-key")

    def test_store_raises_on_all_failure(self) -> None:
        """Raises RuntimeError when all storage methods fail."""
        with (
            patch("maglab.llm.auth._keyring_available", return_value=False),
            patch("maglab.llm.auth._auth_json_set", return_value=False),
            pytest.raises(RuntimeError, match="API key storage failed"),
        ):
            store_api_key("anthropic", "test-key")

    def test_delete_clears_both_storages(self) -> None:
        """Deletes from both keyring and auth.json."""
        with (
            patch("maglab.llm.auth._keyring_delete", return_value=True) as mock_kd,
            patch("maglab.llm.auth._auth_json_delete", return_value=True) as mock_jd,
        ):
            result = delete_api_key("anthropic")

        assert result is True
        mock_kd.assert_called_once_with("anthropic")
        mock_jd.assert_called_once_with("anthropic")


# ---------------------------------------------------------------------------
# list_providers tests
# ---------------------------------------------------------------------------


class TestListProviders:
    def test_returns_providers_with_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the list of providers for which an API key exists."""
        monkeypatch.setenv("MAGLAB_ANTHROPIC_API_KEY", "ak")
        monkeypatch.setenv("MAGLAB_OPENAI_API_KEY", "ok")
        monkeypatch.delenv("MAGLAB_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("MAGLAB_OPENAI_COMPATIBLE_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)

        with (
            patch("maglab.llm.auth._keyring_get", return_value=None),
            patch("maglab.llm.auth._auth_json_get", return_value=None),
        ):
            result = list_providers()

        assert "anthropic" in result
        assert "openai" in result
        assert "gemini" not in result


# ---------------------------------------------------------------------------
# verify_connection tests
# ---------------------------------------------------------------------------


class TestVerifyConnection:
    def test_returns_error_when_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns ok=False when no API key is found."""
        monkeypatch.delenv("MAGLAB_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with (
            patch("maglab.llm.auth._keyring_get", return_value=None),
            patch("maglab.llm.auth._auth_json_get", return_value=None),
        ):
            result = verify_connection("anthropic")

        assert result["ok"] is False
        assert "API key" in str(result["error"])

    def test_returns_ok_on_successful_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns ok=True on a successful litellm call."""
        monkeypatch.setenv("MAGLAB_ANTHROPIC_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]

        with (
            patch("maglab.llm.auth.get_api_key", return_value="test-key"),
            patch("litellm.completion", return_value=mock_resp),
        ):
            result = verify_connection("anthropic")

        assert result["ok"] is True
        assert result["provider"] == "anthropic"
        assert result["error"] is None

    def test_returns_error_on_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns ok=False and an error message on litellm call failure."""
        with (
            patch("maglab.llm.auth.get_api_key", return_value="test-key"),
            patch("litellm.completion", side_effect=RuntimeError("connection failed")),
        ):
            result = verify_connection("anthropic")

        assert result["ok"] is False
        assert "connection failed" in str(result["error"])


# ---------------------------------------------------------------------------
# check_auth_json_permissions tests
# ---------------------------------------------------------------------------


class TestCheckAuthJsonPermissions:
    def test_returns_not_exists_when_file_missing(self, tmp_path: Path) -> None:
        """Returns exists=False when the file is missing."""
        missing_path = tmp_path / "auth.json"
        with patch("maglab.llm.auth._AUTH_JSON_PATH", missing_path):
            result = check_auth_json_permissions()

        assert result["exists"] is False
        assert result["mode_ok"] is True

    def test_detects_correct_permissions(self, tmp_path: Path) -> None:
        """Detects 0600 permissions correctly."""
        json_path = tmp_path / "auth.json"
        json_path.write_text("{}\n")
        json_path.chmod(0o600)

        with patch("maglab.llm.auth._AUTH_JSON_PATH", json_path):
            result = check_auth_json_permissions()

        assert result["exists"] is True
        assert result["mode_ok"] is True

    def test_detects_incorrect_permissions(self, tmp_path: Path) -> None:
        """Detects 0644 permissions as a violation."""
        json_path = tmp_path / "auth.json"
        json_path.write_text("{}\n")
        json_path.chmod(0o644)

        with patch("maglab.llm.auth._AUTH_JSON_PATH", json_path):
            result = check_auth_json_permissions()

        assert result["exists"] is True
        assert result["mode_ok"] is False


class TestAuthJsonDurability:
    """Credentials must survive an interrupted write and a corrupt file.

    ``_auth_json_set`` truncated auth.json before writing, so an interruption
    left it unparseable — and ``_auth_json_get`` then answered None for *every*
    provider, not just the one being stored. The corrupt file also wedged the
    store permanently: each later save re-read it, raised, and returned False.
    """

    @pytest.fixture()
    def auth_path(self, tmp_path: Path):
        path = tmp_path / "auth.json"
        with patch("maglab.llm.auth._AUTH_JSON_PATH", path):
            yield path

    def test_keys_round_trip(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_get, _auth_json_set

        assert _auth_json_set("anthropic", "sk-ant-1")
        assert _auth_json_set("openai", "sk-oai-1")

        assert _auth_json_get("anthropic") == "sk-ant-1"
        assert _auth_json_get("openai") == "sk-oai-1"

    def test_file_is_created_at_0600(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_set

        _auth_json_set("anthropic", "sk-ant-1")
        assert auth_path.stat().st_mode & 0o777 == 0o600

    def test_failed_write_keeps_every_existing_key(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_get, _auth_json_set

        _auth_json_set("anthropic", "sk-ant-1")
        _auth_json_set("openai", "sk-oai-1")
        before = auth_path.read_text(encoding="utf-8")

        with patch("maglab.llm.auth.atomic_write_text", side_effect=OSError("disk full")):
            assert _auth_json_set("gemini", "sk-gem-1") is False

        assert auth_path.read_text(encoding="utf-8") == before
        assert _auth_json_get("anthropic") == "sk-ant-1"
        assert _auth_json_get("openai") == "sk-oai-1"

    def test_no_scratch_files_left_behind(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_set

        for i in range(3):
            _auth_json_set("anthropic", f"sk-{i}")

        assert sorted(p.name for p in auth_path.parent.iterdir()) == ["auth.json"]

    def test_corrupt_file_does_not_wedge_the_store(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_get, _auth_json_set

        _auth_json_set("anthropic", "sk-old")
        auth_path.write_text("{corrupt", encoding="utf-8")

        assert _auth_json_set("anthropic", "sk-new") is True
        assert _auth_json_get("anthropic") == "sk-new"

    def test_corrupt_file_is_preserved_for_inspection(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_set

        auth_path.write_text("{corrupt", encoding="utf-8")
        _auth_json_set("anthropic", "sk-new")

        quarantined = auth_path.with_name("auth.json.corrupt")
        assert quarantined.is_file(), "the unreadable file was discarded instead of kept"
        assert quarantined.read_text(encoding="utf-8") == "{corrupt"

    def test_non_object_json_is_ignored_not_crashed_on(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_get, _auth_json_set

        auth_path.write_text('["not", "a", "map"]', encoding="utf-8")

        assert _auth_json_get("anthropic") is None
        assert _auth_json_set("anthropic", "sk-new") is True
        assert _auth_json_get("anthropic") == "sk-new"

    def test_delete_removes_only_the_named_provider(self, auth_path: Path) -> None:
        from maglab.llm.auth import _auth_json_delete, _auth_json_get, _auth_json_set

        _auth_json_set("anthropic", "sk-ant-1")
        _auth_json_set("openai", "sk-oai-1")

        assert _auth_json_delete("anthropic") is True

        assert _auth_json_get("anthropic") is None
        assert _auth_json_get("openai") == "sk-oai-1"


class TestDelegatedTimeoutPreservesWork:
    """A killed agent has usually done real work; discarding it all is costly.

    The default was 120 s, which is a completion-endpoint figure. These CLIs are
    agents: codex ships ~19k tokens of context before answering and takes ~8 s
    for a one-word reply, so anything resembling research overran and every tool
    call it had already completed was thrown away.
    """

    def test_default_timeout_suits_an_agentic_cli(self) -> None:
        from maglab.config import DelegatedCLIBackendConfig

        assert DelegatedCLIBackendConfig().timeout >= 600

    def test_timeout_carries_the_partial_output(self) -> None:
        import sys

        from maglab.llm.backends.delegated_cli import (
            DelegatedCLIBackend,
            DelegatedCLITimeoutError,
        )

        backend = DelegatedCLIBackend(cli="codex", timeout=1.5)
        backend._emit_codex_trace_line = lambda line: None  # type: ignore[method-assign]
        command = [
            sys.executable,
            "-c",
            "import sys, time\n"
            "for i in range(5):\n"
            "    sys.stdout.write(f'work-{i}\\n'); sys.stdout.flush()\n"
            "time.sleep(30)\n",
        ]

        with pytest.raises(DelegatedCLITimeoutError) as excinfo:
            backend._complete_codex_with_live_trace(command, "model")

        assert "work-0" in excinfo.value.partial_output
        assert excinfo.value.partial_output.count("\n") == 5

    def test_timeout_message_says_how_to_extend_it(self) -> None:
        import sys

        from maglab.llm.backends.delegated_cli import (
            DelegatedCLIBackend,
            DelegatedCLITimeoutError,
        )

        backend = DelegatedCLIBackend(cli="codex", timeout=0.5)
        backend._emit_codex_trace_line = lambda line: None  # type: ignore[method-assign]

        with pytest.raises(DelegatedCLITimeoutError, match="timeout"):
            backend._complete_codex_with_live_trace(
                [sys.executable, "-c", "import time; time.sleep(20)"], "model"
            )
