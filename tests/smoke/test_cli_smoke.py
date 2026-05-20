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
    assert 'pipx install --editable ".[research]"' in result.output
    assert 'uv pip install -e ".[research]"' in result.output
    assert "/setup <feature>" in result.output


@pytest.mark.smoke
def test_install_command_recommends_global_workspace_usage() -> None:
    result = runner.invoke(app, ["install"])
    assert result.exit_code == 0, result.output
    assert 'pipx install --editable ".[research]"' in result.output
    assert "open any research folder and run" in result.output


@pytest.mark.smoke
def test_workspace_status_shows_current_folder_paths() -> None:
    result = runner.invoke(app, ["workspace", "status"])
    assert result.exit_code == 0, result.output
    assert "workspace root" in result.output
    assert "global config" in result.output


@pytest.mark.smoke
def test_instr_skillgen_creates_workspace_skill() -> None:
    with runner.isolated_filesystem():
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
    assert "ux_contract" in report


@pytest.mark.smoke
def test_doctor_prints_plan_ux_contract() -> None:
    result = runner.invoke(app, ["doctor", "--no-sim"])
    assert result.exit_code == 0, result.output
    assert "Plan UX contract" in result.output
    assert "First folder read" in result.output
    assert "Language support" in result.output


@pytest.mark.smoke
def test_manual_command_lists_korean_manuals() -> None:
    result = runner.invoke(app, ["manual", "--lang", "ko"])
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
        result = runner.invoke(app, ["auth", "grok", "--model", "grok-4.20", "--no-store-key"])

    assert result.exit_code == 0, result.output
    mock_config_path.assert_called_once_with()
    mock_save.assert_called_once()
    saved_config = saved["config"]
    assert isinstance(saved_config, Config)
    assert saved_config.backend.mode == "api"
    assert saved_config.backend.api.provider == "grok"
    assert saved_config.backend.api.model == "grok-4.20"
    assert saved_config.routing.plan == "xai/grok-4.20"
