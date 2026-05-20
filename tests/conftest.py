"""Shared pytest fixtures.

Verification principle (PLAN §20): LLM-as-judge is forbidden for quantitative,
citation, and fitting verification — deterministic checks only.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_user_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reading or mutating the developer's real app dirs."""
    root = tmp_path / "user-dirs"

    def _app_dir(kind: str) -> Callable[..., str]:
        def _inner(appname: str | None = None, *args: object, **kwargs: object) -> str:
            name = appname or "maglab"
            return str(root / kind / name)

        return _inner

    monkeypatch.setattr("platformdirs.user_data_dir", _app_dir("data"))
    monkeypatch.setattr("platformdirs.user_config_dir", _app_dir("config"))
    monkeypatch.setattr("platformdirs.user_cache_dir", _app_dir("cache"))


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    """Golden-value data directory (µMAG, VAMPIRE, literature values)."""
    return Path(__file__).parent / "golden" / "data"
