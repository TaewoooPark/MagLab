"""Tests for MagLab feature setup registry."""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from rich.console import Console

from maglab.setup import (
    FEATURES,
    RECOMMENDED_INSTALL,
    build_install_doctor_report,
    normalize_feature,
    render_setup,
)


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


def test_simulation_core_readiness_does_not_require_ssh_client() -> None:
    assert "paramiko" not in FEATURES["simulation"].imports
    assert "paramiko" in FEATURES["simulation"].optional_imports
    assert any(
        "missing Paramiko only blocks Python-native remote" in note
        for note in FEATURES["simulation"].notes
    )


def test_render_setup_all_recommends_research_extra() -> None:
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, width=120)

    render_setup("all", console=console)

    output = stream.getvalue()
    assert RECOMMENDED_INSTALL in output
    assert "MagLab research feature setup" in output
    assert "/setup <feature>" in output


def test_install_doctor_report_covers_global_and_workspace_paths() -> None:
    report = build_install_doctor_report()

    assert report["recommended_install"] == RECOMMENDED_INSTALL
    assert "python" in report
    assert "command" in report
    assert "workspace" in report
    workspace = report["workspace"]
    assert isinstance(workspace, dict)
    assert "root" in workspace
    assert "global_config" in workspace
    assert "global_cache" in workspace
    sim_row = next(row for row in report["features"] if row["key"] == "simulation")
    assert isinstance(sim_row["optional_python"], dict)
    assert "paramiko" in sim_row["optional_python"]
    assert "missing_optional_python" in sim_row
    assert sim_row["setup_command"] == "maglab setup simulation"


def test_install_doctor_recommends_setup_for_missing_optional_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "maglab.setup._module_ok",
        lambda name: name != "paramiko",
    )

    report = build_install_doctor_report()

    assert any("Optional Python packages" in action for action in report["next_actions"])


def test_cli_import_does_not_mutate_global_cache_env(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key != "XDG_CACHE_HOME"}
    env.pop("MPLCONFIGDIR", None)

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; import maglab.cli; print(os.environ.get('XDG_CACHE_HOME', ''))",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""


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
    assert "Optional Python packages" in output
    assert "paramiko:" in output
    assert "--probe-ssh" in output


def test_normalize_feature_aliases() -> None:
    assert normalize_feature("lit") == "literature"
    assert normalize_feature("sim") == "simulation"
    assert normalize_feature("research") == "all"
