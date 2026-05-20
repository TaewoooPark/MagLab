"""Shared pytest fixtures.

Verification principle (PLAN §20): LLM-as-judge is forbidden for quantitative,
citation, and fitting verification — deterministic checks only.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    """Golden-value data directory (µMAG, VAMPIRE, literature values)."""
    return Path(__file__).parent / "golden" / "data"
