"""Tests for MagLab feature setup registry."""

from __future__ import annotations

import io
import re
import tomllib
from pathlib import Path

from rich.console import Console

from maglab.setup import FEATURES, RECOMMENDED_INSTALL, normalize_feature, render_setup


def test_research_extra_contains_all_feature_dependency_groups() -> None:
    pyproject = Path("pyproject.toml")
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    optional = data["project"]["optional-dependencies"]

    assert "research" in optional
    assert "all" in optional
    research_packages = {
        re.split(r"[<>=!~;\[]", dep, maxsplit=1)[0].strip().lower() for dep in optional["research"]
    }
    for package in (
        "litellm",
        "ollama",
        "fastmcp",
        "discretisedfield",
        "matplotlib",
        "pyvisa",
        "pyalex",
        "rank-bm25",
        "bibtexparser",
        "slack-bolt",
        "paramiko",
    ):
        assert package in research_packages


def test_setup_registry_has_slash_for_each_research_feature() -> None:
    expected = {
        "llm",
        "literature",
        "simulation",
        "figure",
        "instrument",
        "authoring",
        "review",
        "gateway",
        "mcp",
    }
    assert expected <= set(FEATURES)
    for key in expected:
        assert FEATURES[key].slash == f"/setup-{key}"


def test_render_setup_all_recommends_research_extra() -> None:
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, width=120)

    render_setup("all", console=console)

    output = stream.getvalue()
    assert RECOMMENDED_INSTALL in output
    assert "MagLab research feature setup" in output
    assert "/setup <feature>" in output


def test_render_setup_feature_shows_terminal_commands() -> None:
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, width=120)

    render_setup("llm", console=console)

    output = stream.getvalue()
    assert 'uv pip install -e ".[llm]"' in output
    assert "maglab auth codex" in output
    assert "/connect codex" in output


def test_render_setup_simulation_shows_doctor_commands() -> None:
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, width=120)

    render_setup("simulation", console=console)

    output = stream.getvalue()
    assert 'uv pip install -e ".[sim]"' in output
    assert "maglab sim doctor" in output
    assert "--probe-ssh" in output


def test_normalize_feature_aliases() -> None:
    assert normalize_feature("lit") == "literature"
    assert normalize_feature("sim") == "simulation"
    assert normalize_feature("research") == "all"
