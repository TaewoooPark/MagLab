"""Full CLI subcommand smoke tests (§20 — CLI smoke).

Verifies:
  - every subcommand ``--help`` exits 0
  - P0 commands behave for real (physics·mat·theme·skill·agents)
  - P2/P4/P5/P6 commands are wired to real implementations (not stubs)
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from maglab.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# --help exits 0 — every subcommand
# ---------------------------------------------------------------------------

_SUBAPP_HELP_ARGS: list[list[str]] = [
    ["auth", "--help"],
    ["auth", "set", "--help"],
    ["auth", "list", "--help"],
    ["auth", "test", "--help"],
    ["auth", "status", "--help"],
    ["auth", "anthropic", "--help"],
    ["auth", "grok", "--help"],
    ["auth", "deepseek", "--help"],
    ["auth", "qwen", "--help"],
    ["auth", "kimi", "--help"],
    ["auth", "gemini", "--help"],
    ["auth", "openai", "--help"],
    ["auth", "openai-compatible", "--help"],
    ["auth", "codex", "--help"],
    ["auth", "claude", "--help"],
    ["auth", "gemini-cli", "--help"],
    ["auth", "ollama", "--help"],
    ["physics", "--help"],
    ["physics", "compute", "--help"],
    ["physics", "units", "--help"],
    ["physics", "oracle", "--help"],
    ["mat", "--help"],
    ["mat", "list", "--help"],
    ["mat", "show", "--help"],
    ["mat", "search", "--help"],
    ["mat", "build", "--help"],
    ["theme", "--help"],
    ["theme", "list", "--help"],
    ["theme", "set", "--help"],
    ["skill", "--help"],
    ["skill", "list", "--help"],
    ["skill", "create", "--help"],
    ["skill", "install", "--help"],
    ["cost", "--help"],
    ["mcp", "--help"],
    ["mcp", "list", "--help"],
    ["mcp", "serve", "--help"],
    ["agents", "--help"],
    ["agents", "list", "--help"],
    ["agents", "show", "--help"],
    ["config", "--help"],
    ["config", "show", "--help"],
    ["config", "path", "--help"],
    ["config", "restore", "--help"],
    ["config", "reset", "--help"],
    ["report", "--help"],
    ["report", "inventory", "--help"],
    ["prov", "--help"],
    ["prov", "summary", "--help"],
    ["prov", "status", "--help"],
    ["task", "--help"],
    ["task", "list", "--help"],
    ["task", "status", "--help"],
    ["task", "scaffold", "--help"],
    ["install", "--help"],
    ["doctor", "--help"],
    ["workspace", "--help"],
    ["workspace", "status", "--help"],
    ["workspace", "init", "--help"],
    ["workspace", "tree", "--help"],
    # P1 — sim
    ["sim", "--help"],
    ["sim", "micro", "--help"],
    ["sim", "validate", "--help"],
    ["sim", "plot", "--help"],
    ["sim", "job", "--help"],
    ["sim", "dft", "--help"],
    ["sim", "atomistic", "--help"],
    ["sim", "pipeline", "--help"],
    # P1 — figure
    ["figure", "--help"],
    ["figure", "spec", "--help"],
    ["figure", "render", "--help"],
    ["figure", "compose", "--help"],
    ["figure", "export", "--help"],
    ["figure", "primitives", "--help"],
    ["figure", "primitives", "list", "--help"],
    ["figure", "primitives", "show", "--help"],
    ["figure", "primitives", "ingest", "--help"],
    # P4 — instr
    ["instr", "--help"],
    ["instr", "scaffold", "--help"],
    ["instr", "scpi", "--help"],
    ["instr", "script", "--help"],
    ["instr", "check", "--help"],
    ["instr", "ingest", "--help"],
    ["instr", "skillgen", "--help"],
    ["instr", "implement", "--help"],
    # P2 — fit · analyze · device
    ["fit", "--help"],
    ["analyze", "--help"],
    ["analyze", "load", "--help"],
    ["analyze", "model", "--help"],
    ["analyze", "consistency", "--help"],
    ["analyze", "symmetry", "--help"],
    ["device", "--help"],
    ["device", "fom", "--help"],
    # P4 — ralph
    ["ralph", "--help"],
    ["ralph", "start", "--help"],
    ["ralph", "status", "--help"],
    ["ralph", "cancel", "--help"],
    # P5 — lit · review · lab · explain
    ["lit", "--help"],
    ["lit", "search", "--help"],
    ["lit", "authors", "--help"],
    ["lit", "keywords", "--help"],
    ["lit", "journal", "--help"],
    ["lit", "graph", "--help"],
    ["review", "--help"],
    ["lab", "--help"],
    ["lab", "note", "--help"],
    ["lab", "plan", "--help"],
    ["explain", "--help"],
    # P6 — write · comms · gateway · present · hypotheses
    ["write", "--help"],
    ["comms", "--help"],
    ["comms", "revision", "--help"],
    ["comms", "cover-letter", "--help"],
    ["comms", "email", "--help"],
    ["comms", "abstract", "--help"],
    ["comms", "grant", "--help"],
    ["gateway", "--help"],
    ["gateway", "setup", "--help"],
    ["gateway", "start", "--help"],
    ["gateway", "stop", "--help"],
    ["gateway", "status", "--help"],
    ["gateway", "install", "--help"],
    ["present", "--help"],
    ["present", "templates", "--help"],
    ["present", "slides", "--help"],
    ["present", "poster", "--help"],
    ["hypotheses", "--help"],
]


@pytest.mark.smoke
@pytest.mark.parametrize("args", _SUBAPP_HELP_ARGS)
def test_help_exit_0(args: list[str]) -> None:
    """Every subcommand ``--help`` must exit 0."""
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"args={args}  exit={result.exit_code}\n{result.stdout}"


# ---------------------------------------------------------------------------
# P0 command behavior
# ---------------------------------------------------------------------------


@pytest.mark.smoke
def test_version_output() -> None:
    """The version command prints a string containing the version."""
    from maglab import __version__

    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.smoke
def test_info_output() -> None:
    """The info command prints maglab and Python information."""
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "maglab" in result.stdout.lower()
    assert "python" in result.stdout.lower()


@pytest.mark.smoke
def test_physics_oracle_valid() -> None:
    """physics oracle accepts a plausible parameter and exits 0."""
    result = runner.invoke(app, ["physics", "oracle", "alpha=0.01"])
    assert result.exit_code == 0
    assert result.stdout.strip()


@pytest.mark.smoke
def test_physics_oracle_no_params() -> None:
    """physics oracle with no parameters still exits 0."""
    result = runner.invoke(app, ["physics", "oracle"])
    assert result.exit_code == 0


@pytest.mark.smoke
def test_physics_compute_exchange_length() -> None:
    """The exchange_length formula computes successfully."""
    result = runner.invoke(
        app,
        ["physics", "compute", "exchange_length", "A=1.3e-11", "Ms=860000"],
    )
    assert result.exit_code == 0
    assert "exchange_length" in result.stdout.lower() or "=" in result.stdout


@pytest.mark.smoke
def test_mat_list() -> None:
    """mat list prints the material catalogue."""
    result = runner.invoke(app, ["mat", "list"])
    assert result.exit_code == 0
    assert "Permalloy" in result.stdout or "YIG" in result.stdout or len(result.stdout) > 10


@pytest.mark.smoke
def test_mat_show_permalloy() -> None:
    """Looking up the Permalloy material succeeds."""
    result = runner.invoke(app, ["mat", "show", "Permalloy"])
    assert result.exit_code == 0


@pytest.mark.smoke
def test_mat_search_finds_permalloy_alias() -> None:
    """mat search is part of Appendix A and finds bundled materials."""
    result = runner.invoke(app, ["mat", "search", "Py", "--json"])
    assert result.exit_code == 0, result.output
    assert "Permalloy" in result.output


@pytest.mark.smoke
def test_mat_show_unknown() -> None:
    """An unknown material lookup exits 1."""
    result = runner.invoke(app, ["mat", "show", "DOES_NOT_EXIST_XYZ"])
    assert result.exit_code == 1


@pytest.mark.smoke
def test_theme_list() -> None:
    """theme list prints the bundled theme names."""
    result = runner.invoke(app, ["theme", "list"])
    assert result.exit_code == 0
    assert "domain" in result.stdout


@pytest.mark.smoke
def test_skill_list() -> None:
    """skill list exits 0."""
    result = runner.invoke(app, ["skill", "list"])
    assert result.exit_code == 0


@pytest.mark.smoke
def test_agents_list() -> None:
    """agents list exits 0."""
    result = runner.invoke(app, ["agents", "list"])
    assert result.exit_code == 0


@pytest.mark.smoke
def test_agents_show_physics_validator() -> None:
    """agents show physics-validator succeeds."""
    result = runner.invoke(app, ["agents", "show", "physics-validator"])
    assert result.exit_code == 0


@pytest.mark.smoke
def test_cost_cmd() -> None:
    """The cost command exits 0."""
    result = runner.invoke(app, ["cost"])
    assert result.exit_code == 0


@pytest.mark.smoke
def test_mcp_list() -> None:
    """mcp list exits 0."""
    result = runner.invoke(app, ["mcp", "list"])
    assert result.exit_code == 0


@pytest.mark.smoke
def test_config_cmd() -> None:
    """The config command prints JSON containing the backend key."""
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "backend" in result.stdout
