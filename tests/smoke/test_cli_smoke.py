"""CLI startup smoke tests (§20 — CLI smoke)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from maglab import __version__
from maglab.cli import app
from maglab.config import Config
from tests.harness.cli_runner import isolated_filesystem

runner = CliRunner()


@pytest.mark.smoke
def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.smoke
def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "maglab" in result.stdout.lower()


@pytest.mark.smoke
def test_setup_command_recommends_research_extra() -> None:
    result = runner.invoke(app, ["setup", "all"])
    assert result.exit_code == 0, result.output
    assert 'pipx install --python python3.12 --editable ".[research]"' in result.output
    assert 'uv pip install -e ".[research]"' in result.output
    assert "/setup <feature>" in result.output


@pytest.mark.smoke
def test_install_command_recommends_global_workspace_usage() -> None:
    result = runner.invoke(app, ["install"])
    assert result.exit_code == 0, result.output
    assert 'pipx install --python python3.12 --editable ".[research]"' in result.output
    assert "open any research folder and run" in result.output
    assert "maglab install doctor" in result.output


@pytest.mark.smoke
def test_install_doctor_json_reports_preflight() -> None:
    result = runner.invoke(app, ["install", "doctor", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert (
        payload["recommended_install"]
        == 'pipx install --python python3.12 --editable ".[research]"'
    )
    assert "python" in payload
    assert "workspace" in payload
    assert "features" in payload
    simulation = next(item for item in payload["features"] if item["key"] == "simulation")
    assert "optional_python" in simulation
    assert "paramiko" in simulation["optional_python"]


@pytest.mark.smoke
def test_workspace_status_shows_current_folder_paths() -> None:
    result = runner.invoke(app, ["workspace", "status"])
    assert result.exit_code == 0, result.output
    assert "workspace root" in result.output
    assert "global config" in result.output


@pytest.mark.smoke
def test_workspace_status_json_is_machine_readable() -> None:
    result = runner.invoke(app, ["workspace", "status", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "workspace_root" in payload
    assert "global_config" in payload


@pytest.mark.smoke
def test_workspace_tree_json_reports_visible_entries() -> None:
    with isolated_filesystem(runner):
        Path("MAGLAB.md").write_text("# Project\n", encoding="utf-8")
        Path("data").mkdir()
        Path("data/sample.csv").write_text("x,y\n0,0\n", encoding="utf-8")

        result = runner.invoke(app, ["workspace", "tree", "--json", "--max", "10"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["maglab_md"]
    assert "data/" in payload["entries"]


@pytest.mark.smoke
def test_workspace_tree_filters_docs_code_data() -> None:
    with isolated_filesystem(runner):
        Path("README.md").write_text("# Demo\n", encoding="utf-8")
        Path("maglab").mkdir()
        Path("maglab/cli.py").write_text("print('x')\n", encoding="utf-8")
        Path("data").mkdir()
        Path("data/sample.csv").write_text("x,y\n0,0\n", encoding="utf-8")

        docs = runner.invoke(app, ["workspace", "tree", "--type", "docs", "--json"])
        code = runner.invoke(app, ["workspace", "tree", "--type", "code", "--json"])
        data = runner.invoke(app, ["workspace", "tree", "--type", "data", "--json"])

    assert docs.exit_code == 0, docs.output
    assert code.exit_code == 0, code.output
    assert data.exit_code == 0, data.output
    assert "README.md" in json.loads(docs.output)["entries"]
    assert "maglab/cli.py" in json.loads(code.output)["entries"]
    assert "data/sample.csv" in json.loads(data.output)["entries"]


@pytest.mark.smoke
def test_workspace_tree_depth_and_all_flags() -> None:
    with isolated_filesystem(runner):
        Path(".github").mkdir()
        Path(".github/workflow.yml").write_text("ci\n", encoding="utf-8")
        Path("demo.egg-info").mkdir()
        Path("demo.egg-info/PKG-INFO").write_text("generated\n", encoding="utf-8")
        Path(".maglab/runtime").mkdir(parents=True)
        Path(".maglab/runtime/budget.db").write_text("x\n", encoding="utf-8")
        Path("a/b").mkdir(parents=True)
        Path("a/b/c.md").write_text("# deep\n", encoding="utf-8")

        shallow = runner.invoke(app, ["workspace", "tree", "--max-depth", "1", "--json"])
        default = runner.invoke(app, ["workspace", "tree", "--json"])
        full = runner.invoke(app, ["workspace", "tree", "--all", "--json"])

    assert shallow.exit_code == 0, shallow.output
    assert default.exit_code == 0, default.output
    assert full.exit_code == 0, full.output
    assert all("/" not in entry.rstrip("/") for entry in json.loads(shallow.output)["entries"])
    assert all(".github" not in entry for entry in json.loads(default.output)["entries"])
    assert all(".maglab" not in entry for entry in json.loads(default.output)["entries"])
    assert all(".egg-info" not in entry for entry in json.loads(default.output)["entries"])
    assert any(".maglab/runtime" in entry for entry in json.loads(full.output)["entries"])
    assert any(".github" in entry for entry in json.loads(full.output)["entries"])
    assert any(".egg-info" in entry for entry in json.loads(full.output)["entries"])


@pytest.mark.smoke
def test_workspace_brief_prioritizes_key_paths() -> None:
    with isolated_filesystem(runner):
        Path("README.md").write_text("# Demo\n", encoding="utf-8")
        Path("plan").mkdir()

        result = runner.invoke(app, ["workspace", "brief"])

    assert result.exit_code == 0, result.output
    assert "High-signal paths" in result.output
    assert "README.md" in result.output
    assert "plan/" in result.output


@pytest.mark.smoke
def test_instr_skillgen_creates_workspace_skill() -> None:
    with isolated_filesystem(runner):
        result = runner.invoke(
            app,
            ["instr", "skillgen", "SR830", "--manufacturer", "SRS"],
        )

        assert result.exit_code == 0, result.output
        assert "Instrument Skill Generated" in result.output
        assert Path(".maglab/skills/srs-sr830/SKILL.md").is_file()


@pytest.mark.smoke
def test_doctor_json_reports_workspace_and_features() -> None:
    result = runner.invoke(app, ["doctor", "--no-sim", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert "workspace" in report
    assert "backend" in report
    assert "features" in report
    assert "optional_python" in report["features"][0]
    assert "ux_contract" in report


@pytest.mark.smoke
def test_doctor_prints_plan_ux_contract() -> None:
    result = runner.invoke(app, ["doctor", "--no-sim"])
    assert result.exit_code == 0, result.output
    assert "Optional Python" in result.output
    assert "Plan UX contract" in result.output
    assert "First folder read" in result.output
    assert "Language support" in result.output


@pytest.mark.smoke
def test_manual_command_lists_korean_manuals() -> None:
    result = runner.invoke(app, ["manual", "--lang", "ko"])
    assert result.exit_code == 0, result.output
    assert "MagLab manuals (ko)" in result.output


@pytest.mark.smoke
def test_manual_command_accepts_language_first_topic() -> None:
    result = runner.invoke(app, ["manual", "ko", "orchestration"])
    assert result.exit_code == 0, result.output
    assert "lang: ko" in result.output
    assert "orchestration" in result.output


@pytest.mark.smoke
def test_manual_command_accepts_language_first_listing() -> None:
    result = runner.invoke(app, ["manual", "ko"])
    assert result.exit_code == 0, result.output
    assert "MagLab manuals (ko)" in result.output
    assert "figures" in result.output


@pytest.mark.smoke
def test_sim_doctor_preserves_extra_name_markup() -> None:
    with (
        patch("maglab.sim.environment._module_ok", return_value=False),
        patch("maglab.sim.environment._binary_path", return_value=None),
        patch(
            "maglab.sim.environment.CPUBackendRouter.available_engines",
            staticmethod(lambda: []),
        ),
    ):
        result = runner.invoke(app, ["sim", "doctor"])
    assert result.exit_code == 0, result.output
    assert "maglab[sim]" in result.output


@pytest.mark.smoke
def test_prompt_invocation_calls_orchestrator() -> None:
    class _FakeOrchestrator:
        def __init__(self, config: Config, backend: object | None = None) -> None:
            self.config = config
            self.backend = backend

        def respond(self, prompt: str) -> str:
            return f"orchestrated: {prompt}"

        def close(self) -> None:
            return None

    cfg = Config()

    with (
        patch("maglab.cli.load_config", return_value=cfg),
        patch("maglab.core.orchestrator.Orchestrator", _FakeOrchestrator),
    ):
        result = runner.invoke(app, ["-p", "plan a skyrmion experiment"])

    assert result.exit_code == 0, result.output
    assert "orchestrated: plan a skyrmion experiment" in result.output
    assert "Non-interactive mode" not in result.output


@pytest.mark.smoke
def test_ask_command_calls_orchestrator() -> None:
    class _FakeOrchestrator:
        def __init__(self, config: Config, backend: object | None = None) -> None:
            self.config = config
            self.backend = backend

        def respond(self, prompt: str) -> str:
            return f"asked: {prompt}"

        def close(self) -> None:
            return None

    with (
        patch("maglab.cli.load_config", return_value=Config()),
        patch("maglab.core.orchestrator.Orchestrator", _FakeOrchestrator),
    ):
        result = runner.invoke(app, ["ask", "compare CoFeB and YIG"])

    assert result.exit_code == 0, result.output
    assert "asked: compare CoFeB and YIG" in result.output


@pytest.mark.smoke
def test_run_command_starts_research_loop() -> None:
    from maglab.core.orchestrator import OrchestratorResult

    class _FakeOrchestrator:
        def __init__(self, config: Config, backend: object | None = None) -> None:
            self.config = config
            self.backend = backend

        def run(self, goal: str) -> OrchestratorResult:
            return OrchestratorResult(status="partial", summary=f"running: {goal}")

        def close(self) -> None:
            return None

    with (
        patch("maglab.cli.load_config", return_value=Config()),
        patch("maglab.core.orchestrator.Orchestrator", _FakeOrchestrator),
    ):
        result = runner.invoke(app, ["run", "optimize skyrmion racetrack stack"])

    assert result.exit_code == 0, result.output
    assert "partial" in result.output
    assert "running: optimize skyrmion racetrack stack" in result.output


@pytest.mark.smoke
def test_auth_status_uses_configured_backend_without_network(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg = Config.model_validate(
        {
            "backend": {
                "mode": "delegated_cli",
                "delegated_cli": {
                    "tool": "codex",
                    "model": None,
                },
            }
        }
    )
    backend = MagicMock()
    backend.health_check.return_value = True
    backend.get_cli_version.return_value = "codex-cli-test"

    with (
        patch("maglab.config.config_path", return_value=cfg_file) as mock_config_path,
        patch("maglab.config.load_config", return_value=cfg),
        patch("maglab.llm.factory.create_llm_backend", return_value=backend) as mock_factory,
        patch("maglab.llm.auth.verify_connection", side_effect=AssertionError("network call")),
        patch("subprocess.run", side_effect=AssertionError("real CLI call")),
    ):
        result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0, result.output
    mock_config_path.assert_called_once_with()
    mock_factory.assert_called_once_with(cfg)
    backend.health_check.assert_called_once_with()
    assert "codex" in result.output.lower()


@pytest.mark.smoke
def test_auth_test_without_provider_checks_configured_backend(tmp_path: Path) -> None:
    from maglab.llm.base import LLMResponse

    cfg = Config.model_validate(
        {
            "backend": {
                "mode": "delegated_cli",
                "delegated_cli": {
                    "tool": "codex",
                    "model": None,
                },
            }
        }
    )
    backend = MagicMock()
    backend.complete.return_value = LLMResponse(content="MAGLAB_OK")

    with (
        patch("maglab.config.load_config", return_value=cfg),
        patch("maglab.llm.factory.create_llm_backend", return_value=backend),
        patch("maglab.llm.auth.verify_connection", side_effect=AssertionError("API call")),
    ):
        result = runner.invoke(app, ["auth", "test"])

    assert result.exit_code == 0, result.output
    assert "Backend ready" in result.output
    backend.complete.assert_called_once()


@pytest.mark.smoke
def test_auth_test_codex_argument_uses_delegated_backend_without_api_lookup() -> None:
    from maglab.llm.base import LLMResponse

    captured: dict[str, Config] = {}
    backend = MagicMock()
    backend.complete.return_value = LLMResponse(content="MAGLAB_OK")

    def _capture_backend(config: Config):
        captured["config"] = config
        return backend

    with (
        patch("maglab.llm.factory.create_llm_backend", side_effect=_capture_backend),
        patch("maglab.llm.auth.verify_connection", side_effect=AssertionError("API call")),
    ):
        result = runner.invoke(app, ["auth", "test", "codex", "--model", "gpt-5.5"])

    assert result.exit_code == 0, result.output
    assert "Backend ready" in result.output
    assert captured["config"].backend.mode == "delegated_cli"
    assert captured["config"].backend.delegated_cli.tool == "codex"
    assert captured["config"].backend.delegated_cli.model == "gpt-5.5"
    backend.complete.assert_called_once()


@pytest.mark.smoke
def test_auth_codex_saves_delegated_config_without_cli_call(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    saved: dict[str, object] = {}

    def _capture_save(config: Config, path: Path | None = None) -> None:
        saved["config"] = config
        saved["path"] = path

    with (
        patch("maglab.config.config_path", return_value=cfg_file) as mock_config_path,
        patch("maglab.config.load_config", return_value=Config()),
        patch("maglab.config.save_config", side_effect=_capture_save) as mock_save,
        patch("subprocess.run", side_effect=AssertionError("real CLI call")),
    ):
        result = runner.invoke(app, ["auth", "codex"])

    assert result.exit_code == 0, result.output
    mock_config_path.assert_called_once_with()
    mock_save.assert_called_once()
    assert saved["path"] == cfg_file
    saved_config = saved["config"]
    assert isinstance(saved_config, Config)
    assert saved_config.backend.mode == "delegated_cli"
    assert saved_config.backend.delegated_cli.tool == "codex"
    assert saved_config.backend.delegated_cli.model is None


@pytest.mark.smoke
def test_auth_grok_saves_api_config_without_network(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    saved: dict[str, object] = {}

    def _capture_save(config: Config, path: Path | None = None) -> Path:
        saved["config"] = config
        saved["path"] = path
        return cfg_file

    with (
        patch("maglab.config.config_path", return_value=cfg_file) as mock_config_path,
        patch("maglab.config.load_config", return_value=Config()),
        patch("maglab.config.save_config", side_effect=_capture_save) as mock_save,
        patch("maglab.llm.auth.store_api_key", side_effect=AssertionError("secret prompt")),
        patch("litellm.completion", side_effect=AssertionError("network call")),
    ):
        result = runner.invoke(app, ["auth", "grok", "--model", "grok-4.3", "--no-store-key"])

    assert result.exit_code == 0, result.output
    mock_config_path.assert_called_once_with()
    mock_save.assert_called_once()
    saved_config = saved["config"]
    assert isinstance(saved_config, Config)
    assert saved_config.backend.mode == "api"
    assert saved_config.backend.api.provider == "grok"
    assert saved_config.backend.api.model == "grok-4.3"
    assert saved_config.routing.plan == "xai/grok-4.3"


def test_source_tree_version_matches_pyproject() -> None:
    """The uninstalled-source fallback must not drift from pyproject.

    It was a hard-coded "0.0.3" that stayed put through two releases, so a
    source tree without an install reported a long-stale version — the exact
    drift the metadata lookup was introduced to eliminate.
    """
    import tomllib
    from pathlib import Path

    import maglab

    pyproject = Path(maglab.__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as fh:
        declared = tomllib.load(fh)["project"]["version"]

    assert maglab._version_from_source_tree() == declared


def test_installed_version_matches_pyproject() -> None:
    import tomllib
    from pathlib import Path

    import maglab

    pyproject = Path(maglab.__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as fh:
        declared = tomllib.load(fh)["project"]["version"]

    assert maglab.__version__ == declared, (
        "installed metadata is stale — reinstall, or the release bumped only one of the two"
    )
