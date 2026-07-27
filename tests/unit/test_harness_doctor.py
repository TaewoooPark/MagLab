"""maglab.harness.doctor tests — readiness must be reported, never guessed.

The report has to work offline: a readiness check that needed credentials to
tell you whether you had credentials would be no use at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from maglab.core.manifest import AgentEntry, Manifest, WorkflowEntry
from maglab.harness.doctor import run_doctor


@pytest.fixture()
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return tmp_path


def _check(report, name: str):
    return next(c for c in report.checks if c.name == name)


class TestReportShape:
    def test_report_is_json_serialisable(self, isolated_home: Path) -> None:
        payload = run_doctor(root=isolated_home).to_dict()
        assert json.loads(json.dumps(payload))
        assert {"ok", "checks", "failing"} <= set(payload)

    def test_every_check_is_named_once(self, isolated_home: Path) -> None:
        names = [c.name for c in run_doctor(root=isolated_home).checks]
        assert len(names) == len(set(names))

    def test_pi_checks_never_block(self, isolated_home: Path) -> None:
        """A missing PI install must not stop local execution being reported ready."""
        report = run_doctor(root=isolated_home)
        assert _check(report, "pi-binary").blocking is False
        assert _check(report, "pi-workflow-tool").blocking is False


class TestManifestChecks:
    def test_empty_manifest_fails(self, isolated_home: Path) -> None:
        report = run_doctor(Manifest(), root=isolated_home)
        assert not _check(report, "manifest").ok

    def test_dangling_workflow_step_is_reported(self, isolated_home: Path) -> None:
        manifest = Manifest(
            agents=[AgentEntry(name="scout")],
            workflows=[WorkflowEntry(name="w", steps=["scout", "ghost"])],
        )
        check = _check(run_doctor(manifest, root=isolated_home), "workflow-steps")

        assert not check.ok
        assert "ghost" in check.detail

    def test_missing_agent_definition_is_reported(self, isolated_home: Path) -> None:
        manifest = Manifest(
            agents=[AgentEntry(name="definitely-not-an-agent")],
            workflows=[WorkflowEntry(name="w", steps=["definitely-not-an-agent"])],
        )
        check = _check(run_doctor(manifest, root=isolated_home), "agent-definitions")

        assert not check.ok
        assert "definitely-not-an-agent" in check.detail

    def test_missing_skill_is_reported(self, isolated_home: Path) -> None:
        manifest = Manifest(agents=[AgentEntry(name="scout", skills=["no-such-skill"])])
        check = _check(run_doctor(manifest, root=isolated_home), "agent-skills")

        assert not check.ok
        assert "no-such-skill" in check.detail

    def test_unregistered_mcp_server_gives_the_fix_command(self, isolated_home: Path) -> None:
        manifest = Manifest(agents=[AgentEntry(name="scout", mcp_servers=["some-server"])])
        check = _check(run_doctor(manifest, root=isolated_home), "mcp-servers")

        assert not check.ok
        assert "maglab mcp add some-server" in check.detail

    def test_registered_mcp_server_passes(self, isolated_home: Path) -> None:
        registry = isolated_home / ".maglab" / "mcp.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"servers": {"some-server": {}}}), encoding="utf-8")
        manifest = Manifest(agents=[AgentEntry(name="scout", mcp_servers=["some-server"])])

        assert _check(run_doctor(manifest, root=isolated_home), "mcp-servers").ok


class TestBackendCheck:
    def test_broken_config_is_reported_not_raised(self, isolated_home: Path) -> None:
        from maglab.config import ConfigError

        with patch("maglab.config.load_config", side_effect=ConfigError("config is broken")):
            check = _check(run_doctor(root=isolated_home), "llm-backend")

        assert not check.ok
        assert "broken" in check.detail

    def test_delegated_cli_missing_binary_is_reported(self, isolated_home: Path) -> None:
        from maglab.config import BackendConfig, Config, DelegatedCLIBackendConfig

        config = Config(
            backend=BackendConfig(
                mode="delegated_cli",
                delegated_cli=DelegatedCLIBackendConfig(tool="definitely-not-installed"),
            )
        )
        with patch("maglab.config.load_config", return_value=config):
            check = _check(run_doctor(root=isolated_home), "llm-backend")

        assert not check.ok
        assert "not on PATH" in check.detail

    def test_local_backend_needs_no_credentials(self, isolated_home: Path) -> None:
        from maglab.config import BackendConfig, Config

        with patch(
            "maglab.config.load_config", return_value=Config(backend=BackendConfig(mode="local"))
        ):
            assert _check(run_doctor(root=isolated_home), "llm-backend").ok


class TestPiChecks:
    def test_absent_pi_is_reported_without_running_it(self, isolated_home: Path) -> None:
        with patch("maglab.harness.doctor.shutil.which", return_value=None):
            report = run_doctor(root=isolated_home)

        assert not _check(report, "pi-binary").ok
        assert not _check(report, "pi-workflow-tool").ok

    def test_bare_pi_install_is_not_treated_as_ready(self, isolated_home: Path) -> None:
        """PI without pi-agents has no `workflow` tool, so the handoff cannot run."""
        from types import SimpleNamespace

        completed = SimpleNamespace(returncode=0, stdout="No packages installed.", stderr="")
        with (
            patch("maglab.harness.doctor.shutil.which", return_value="/usr/local/bin/pi"),
            patch("maglab.harness.doctor.subprocess.run", return_value=completed),
        ):
            report = run_doctor(root=isolated_home)

        assert _check(report, "pi-binary").ok
        assert not _check(report, "pi-workflow-tool").ok
        assert "pi-agents" in _check(report, "pi-workflow-tool").detail

    def test_pi_with_workflow_tool_passes(self, isolated_home: Path) -> None:
        from types import SimpleNamespace

        completed = SimpleNamespace(returncode=0, stdout="pi-agents (workflow, task)", stderr="")
        with (
            patch("maglab.harness.doctor.shutil.which", return_value="/usr/local/bin/pi"),
            patch("maglab.harness.doctor.subprocess.run", return_value=completed),
        ):
            assert _check(run_doctor(root=isolated_home), "pi-workflow-tool").ok

    def test_pi_that_cannot_be_run_is_reported(self, isolated_home: Path) -> None:
        with (
            patch("maglab.harness.doctor.shutil.which", return_value="/usr/local/bin/pi"),
            patch("maglab.harness.doctor.subprocess.run", side_effect=OSError("boom")),
        ):
            check = _check(run_doctor(root=isolated_home), "pi-workflow-tool")

        assert not check.ok
        assert "could not run" in check.detail


class TestShippedManifestReadiness:
    """The repo's own manifest must be internally consistent."""

    def test_repo_manifest_has_no_structural_gaps(self, isolated_home: Path) -> None:
        report = run_doctor(root=isolated_home)
        structural = ("manifest", "workflow-steps", "agent-definitions", "agent-skills")
        broken = [name for name in structural if not _check(report, name).ok]

        assert broken == [], f"shipped manifest is inconsistent: {broken}"
