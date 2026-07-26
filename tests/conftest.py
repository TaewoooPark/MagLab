"""Shared pytest fixtures.

Verification principle (PLAN §20): LLM-as-judge is forbidden for quantitative,
citation, and fitting verification — deterministic checks only.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

# Rich latches FORCE_COLOR/CLICOLOR_FORCE in ``Console.__init__``, and the CLI
# modules build their consoles at import time — which happens after conftest is
# loaded but before any fixture runs. Scrubbing the variables here is therefore
# the only point early enough to take effect. Without it, a developer whose
# shell exports FORCE_COLOR sees assertions like ``assert "0.0.4" in
# result.output`` fail against ``maglab \x1b[1;36m0.0\x1b[0m.\x1b[1;36m4`` while
# CI passes — false failures that also hide real ones.
for _forced_colour_var in ("FORCE_COLOR", "CLICOLOR_FORCE", "COLORTERM"):
    os.environ.pop(_forced_colour_var, None)


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


@pytest.fixture(autouse=True)
def deterministic_console_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin colour handling so CLI text assertions don't depend on the terminal.

    Rich colourises when told to, and ``FORCE_COLOR``/``CLICOLOR_FORCE`` override
    its non-TTY detection. A developer whose shell exports either then sees
    assertions like ``assert "0.0.4" in result.output`` fail against
    ``maglab \\x1b[1;36m0.0\\x1b[0m.\\x1b[1;36m4``, while CI passes — false
    failures that also mask real ones. Tests that care about colour set their own
    environment with monkeypatch, which still wins over this fixture.
    """
    for var in ("FORCE_COLOR", "CLICOLOR_FORCE", "COLORTERM"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    """Golden-value data directory (µMAG, VAMPIRE, literature values)."""
    return Path(__file__).parent / "golden" / "data"
