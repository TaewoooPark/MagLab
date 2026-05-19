"""LLM credential management — storage, retrieval, and testing.

§7.2 authentication priority: env var ``MAGLAB_<PROVIDER>_API_KEY`` > keyring > auth.json.

Uses ``~/.config/maglab/auth.json`` (chmod 0600) as a headless fallback.
OAuth tokens are never stored by this module (§7.2 honesty comment).
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVICE_NAME = "maglab"
_AUTH_JSON_PATH = Path.home() / ".config" / "maglab" / "auth.json"

# Provider name → env var name mapping
_PROVIDER_ENV: dict[str, str] = {
    "anthropic": "MAGLAB_ANTHROPIC_API_KEY",
    "openai": "MAGLAB_OPENAI_API_KEY",
    "google": "MAGLAB_GOOGLE_API_KEY",
    "openai-compatible": "MAGLAB_OPENAI_COMPATIBLE_API_KEY",
}


# ---------------------------------------------------------------------------
# keyring wrapper (silently disabled on import failure)
# ---------------------------------------------------------------------------


def _keyring_available() -> bool:
    """Check whether keyring is available."""
    try:
        import keyring  # noqa: F401

        return True
    except ImportError:
        return False


def _keyring_get(provider: str) -> str | None:
    """Retrieve a credential from keyring."""
    try:
        import keyring

        return keyring.get_password(_SERVICE_NAME, provider)
    except Exception as exc:
        log.debug("keyring lookup failed (provider=%s): %s", provider, exc)
        return None


def _keyring_set(provider: str, api_key: str) -> bool:
    """Store a credential in keyring.

    Returns:
        True on success.
    """
    try:
        import keyring

        keyring.set_password(_SERVICE_NAME, provider, api_key)
        return True
    except Exception as exc:
        log.debug("keyring store failed (provider=%s): %s", provider, exc)
        return False


def _keyring_delete(provider: str) -> bool:
    """Delete a credential from keyring."""
    try:
        import keyring

        keyring.delete_password(_SERVICE_NAME, provider)
        return True
    except Exception as exc:
        log.debug("keyring delete failed (provider=%s): %s", provider, exc)
        return False


# ---------------------------------------------------------------------------
# auth.json headless fallback
# ---------------------------------------------------------------------------


def _ensure_auth_json_secure() -> Path:
    """Enforce 0600 permissions on auth.json.

    Creates the file as an empty JSON object if it does not exist.
    Forces permissions to 0600 and logs a warning if they are incorrect.

    Returns:
        Path to auth.json.
    """
    _AUTH_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _AUTH_JSON_PATH.exists():
        _AUTH_JSON_PATH.write_text("{}\n", encoding="utf-8")
    mode = _AUTH_JSON_PATH.stat().st_mode & 0o777
    if mode != 0o600:
        log.warning(
            "auth.json permissions are %o — forcing to 0600: %s",
            mode,
            _AUTH_JSON_PATH,
        )
        _AUTH_JSON_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return _AUTH_JSON_PATH


def _auth_json_get(provider: str) -> str | None:
    """Retrieve an API key from auth.json."""
    try:
        path = _ensure_auth_json_secure()
        data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        return data.get(provider)
    except Exception as exc:
        log.debug("auth.json lookup failed (provider=%s): %s", provider, exc)
        return None


def _auth_json_set(provider: str, api_key: str) -> bool:
    """Store an API key in auth.json."""
    try:
        path = _ensure_auth_json_secure()
        data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        data[provider] = api_key
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return True
    except Exception as exc:
        log.warning("auth.json store failed (provider=%s): %s", provider, exc)
        return False


def _auth_json_delete(provider: str) -> bool:
    """Delete an API key from auth.json."""
    try:
        path = _ensure_auth_json_secure()
        data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        data.pop(provider, None)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return True
    except Exception as exc:
        log.warning("auth.json delete failed (provider=%s): %s", provider, exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_api_key(provider: str) -> str | None:
    """Retrieve an API key following the priority order.

    Priority: env var > keyring > auth.json.

    OAuth tokens are not returned — only API keys are handled (§7.2).

    Args:
        provider: Provider name (``"anthropic"`` · ``"openai"`` · ``"google"`` ·
                  ``"openai-compatible"``).

    Returns:
        API key string, or None if not found.
    """
    # Priority 1: environment variable
    env_var = _PROVIDER_ENV.get(provider)
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val
    # Also support direct env var pattern (e.g. ANTHROPIC_API_KEY)
    direct_env = f"{provider.upper().replace('-', '_')}_API_KEY"
    val = os.environ.get(direct_env)
    if val:
        return val

    # Priority 2: keyring
    val = _keyring_get(provider)
    if val:
        return val

    # Priority 3: auth.json headless fallback
    return _auth_json_get(provider)


def store_api_key(provider: str, api_key: str) -> str:
    """Store an API key in keyring or auth.json.

    Prefers keyring when available; falls back to auth.json otherwise.

    Args:
        provider: Provider name.
        api_key: API key to store.

    Returns:
        Storage location identifier (``"keyring"`` or ``"auth.json"``).

    Raises:
        RuntimeError: When all storage methods fail.
    """
    if _keyring_available() and _keyring_set(provider, api_key):
        log.info("API key stored in keyring (provider=%s).", provider)
        return "keyring"
    if _auth_json_set(provider, api_key):
        log.info("API key stored in auth.json (provider=%s).", provider)
        return "auth.json"
    raise RuntimeError(
        f"API key storage failed (provider={provider}): both keyring and auth.json failed."
    )


def delete_api_key(provider: str) -> bool:
    """Delete the API key from both keyring and auth.json.

    Args:
        provider: Provider name.

    Returns:
        True if at least one deletion succeeded.
    """
    deleted_keyring = _keyring_delete(provider)
    deleted_json = _auth_json_delete(provider)
    return deleted_keyring or deleted_json


def list_providers() -> list[str]:
    """Return the list of providers for which credentials exist.

    Returns:
        List of provider names for which an API key was found.
    """
    found: list[str] = []
    for provider in _PROVIDER_ENV:
        if get_api_key(provider) is not None:
            found.append(provider)
    return found


def verify_connection(provider: str, model: str | None = None) -> dict[str, object]:
    """Validate an API key with a live call.

    Args:
        provider: Provider name.
        model: Model to use for testing.  Uses the provider default if None.

    Returns:
        ``{"ok": bool, "provider": str, "model": str, "error": str|None}``
    """
    api_key = get_api_key(provider)
    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "model": model or "",
            "error": f"API key not found (provider={provider}).",
        }

    # Default model per provider
    _default_models: dict[str, str] = {
        "anthropic": "claude-haiku-4-5",
        "openai": "gpt-4o-mini",
        "google": "gemini-1.5-flash",
        "openai-compatible": "gpt-4o-mini",
    }
    test_model = model or _default_models.get(provider, "gpt-4o-mini")

    try:
        import litellm  # type: ignore[import-untyped]

        # Temporarily inject the API key as an env var (litellm reads env vars)
        env_var = _PROVIDER_ENV.get(provider, f"{provider.upper()}_API_KEY")
        original = os.environ.get(env_var)
        os.environ[env_var] = api_key
        try:
            resp = litellm.completion(
                model=test_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            ok = bool(resp and resp.choices)
        finally:
            if original is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = original

        return {"ok": ok, "provider": provider, "model": test_model, "error": None}

    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "model": test_model,
            "error": str(exc),
        }


def check_auth_json_permissions() -> dict[str, object]:
    """Return the permission status of the auth.json file.

    Returns:
        ``{"path": str, "exists": bool, "mode_ok": bool, "mode": str}``
    """
    exists = _AUTH_JSON_PATH.exists()
    if not exists:
        return {
            "path": str(_AUTH_JSON_PATH),
            "exists": False,
            "mode_ok": True,
            "mode": "---",
        }
    mode = _AUTH_JSON_PATH.stat().st_mode & 0o777
    mode_str = oct(mode)
    return {
        "path": str(_AUTH_JSON_PATH),
        "exists": True,
        "mode_ok": mode == 0o600,
        "mode": mode_str,
    }
