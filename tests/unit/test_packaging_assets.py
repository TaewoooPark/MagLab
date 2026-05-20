"""Packaging checks for runtime assets required after global installation."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_wheel_force_includes_runtime_assets() -> None:
    """Wheel builds must carry root-level runtime assets used by installed CLI sessions."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    force_include = data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    for asset in (
        "MAGLAB.md",
        "harness.manifest.json",
        "agents",
        "skills",
        "themes",
        "docs/manuals",
    ):
        assert force_include[asset] == asset


def test_sdist_includes_tests_and_plan_docs() -> None:
    """Source distributions should keep the implementation plan and test suite."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    sdist_include = set(data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])

    assert "/plan" in sdist_include
    assert "/tests" in sdist_include
