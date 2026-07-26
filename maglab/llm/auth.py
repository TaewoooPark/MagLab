"""LLM credential management — storage, retrieval, and testing.

§7.2 authentication priority: env var ``MAGLAB_<PROVIDER>_API_KEY`` > keyring > auth.json.

Uses ``~/.config/maglab/auth.json`` (chmod 0600) as a headless fallback.
OAuth tokens are never stored by this module (§7.2 honesty comment).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import stat
from pathlib import Path

from maglab.core.atomic import atomic_write_text
from maglab.llm.providers import (
    api_provider_keys,
    build_litellm_model,
    get_provider_profile,
    normalize_provider,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVICE_NAME = "maglab"
_AUTH_JSON_PATH = Path.home() / ".config" / "maglab" / "auth.json"

# Provider name → MagLab env var name mapping. Kept as a module constant for
# compatibility with older code/tests, but sourced from the central profile
# registry.
_PROVIDER_ENV: dict[str, str] = {
    key: get_provider_profile(key).maglab_env_var for key in api_provider_keys()
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
        # Created through the atomic helper, which uses mkstemp — the file is
        # 0600 from the moment it exists. Creating it with write_text left a
        # window at the umask default (typically 0644) before the chmod landed.
        _write_auth_json({})
    mode = _AUTH_JSON_PATH.stat().st_mode & 0o777
    if mode != 0o600:
        log.warning(
            "auth.json permissions are %o — forcing to 0600: %s",
            mode,
            _AUTH_JSON_PATH,
        )
        _AUTH_JSON_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return _AUTH_JSON_PATH


def _write_auth_json(data: dict[str, str]) -> None:
    """Persist the credential map atomically at 0600.

    Atomic because a truncate-then-write loses *every* provider's key if it is
    interrupted: the file becomes unparseable and ``_auth_json_get`` then
    answers None for all of them.
    """
    atomic_write_text(_AUTH_JSON_PATH, json.dumps(data, indent=2) + "\n")
    _AUTH_JSON_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _load_auth_json(path: Path) -> dict[str, str]:
    """Read the credential map, quarantining an unreadable file.

    A corrupt auth.json used to wedge the CLI permanently: every ``_auth_json_set``
    re-read it, raised, and returned False, so no key could ever be stored again
    and the only trace was a log line. The bad file is preserved next to the
    original for inspection rather than discarded.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        quarantine = path.with_name(path.name + ".corrupt")
        with contextlib.suppress(OSError):
            path.replace(quarantine)
        log.warning(
            "auth.json was unreadable (%s); moved to %s and starting a fresh store. "
            "Re-run `maglab auth <provider>` to store keys again.",
            exc,
            quarantine,
        )
        return {}
    if not isinstance(loaded, dict):
        log.warning("auth.json did not contain a JSON object — ignoring its contents.")
        return {}
    return {str(k): str(v) for k, v in loaded.items()}


def _auth_json_get(provider: str) -> str | None:
    """Retrieve an API key from auth.json."""
    try:
        path = _ensure_auth_json_secure()
        return _load_auth_json(path).get(provider)
    except Exception as exc:
        log.debug("auth.json lookup failed (provider=%s): %s", provider, exc)
        return None


def _auth_json_set(provider: str, api_key: str) -> bool:
    """Store an API key in auth.json."""
    try:
        data = _load_auth_json(_ensure_auth_json_secure())
        data[provider] = api_key
        _write_auth_json(data)
        return True
    except Exception as exc:
        log.warning("auth.json store failed (provider=%s): %s", provider, exc)
        return False


def _auth_json_delete(provider: str) -> bool:
    """Delete an API key from auth.json."""
    try:
        data = _load_auth_json(_ensure_auth_json_secure())
        data.pop(provider, None)
        _write_auth_json(data)
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
        provider: Provider name or alias.

    Returns:
        API key string, or None if not found.
    """
    provider = normalize_provider(provider)
    profile = get_provider_profile(provider)

    # Priority 1: MagLab-scoped env var
    val = os.environ.get(profile.maglab_env_var)
    if val:
        return val

    # Also support provider-native env vars used by LiteLLM/vendor CLIs.
    direct_envs = (
        *profile.direct_env_vars,
        profile.litellm_env_var,
        f"{provider.upper().replace('-', '_')}_API_KEY",
    )
    for direct_env in dict.fromkeys(direct_envs):
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
    provider = normalize_provider(provider)
    get_provider_profile(provider)
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
    provider = normalize_provider(provider)
    get_provider_profile(provider)
    deleted_keyring = _keyring_delete(provider)
    deleted_json = _auth_json_delete(provider)
    return deleted_keyring or deleted_json


def list_providers() -> list[str]:
    """Return the list of providers for which credentials exist.

    Returns:
        List of provider names for which an API key was found.
    """
    found: list[str] = []
    for provider in api_provider_keys():
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
    provider = normalize_provider(provider)
    api_key = get_api_key(provider)
    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "model": model or "",
            "error": f"API key not found (provider={provider}).",
        }

    profile = get_provider_profile(provider)
    test_model = model or profile.default_model

    try:
        import litellm  # type: ignore[import-untyped]

        # Temporarily inject the API key as an env var (litellm reads env vars)
        env_var = profile.litellm_env_var
        original = os.environ.get(env_var)
        os.environ[env_var] = api_key
        try:
            resp = litellm.completion(
                model=build_litellm_model(provider, test_model),
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
