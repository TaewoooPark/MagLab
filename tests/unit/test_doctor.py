"""Unit tests for the first-run MagLab doctor report."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.doctor import run_doctor


def test_doctor_reports_active_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("# Project\nSpin Hall study.\n", encoding="utf-8")
    (tmp_path / "data.csv").write_text("field,voltage\n0,0\n", encoding="utf-8")

    report = run_doctor(feature="llm", include_sim=False)

    assert report["workspace"]["root"] == str(tmp_path)
    assert report["workspace"]["maglab_md"] == str(tmp_path / "MAGLAB.md")
    assert "data.csv" in report["workspace"]["visible_entries"]
    assert report["features"][0]["key"] == "llm"
    assert "backend" in report
    assert "ux_contract" in report
    keys = {item["key"] for item in report["ux_contract"]}
    assert {"first-run", "models", "gpu-ssh-cpu", "language", "physics-integrity"} <= keys
    assert "recommendations" in report


def test_doctor_recommends_workspace_init_when_marker_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    report = run_doctor(feature="llm", include_sim=False)

    assert report["workspace"]["maglab_md"] is None
    assert any("maglab workspace init" in item for item in report["recommendations"])


def test_doctor_surfaces_sim_backend_path_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("maglab.sim.environment._binary_path", lambda name: None)
    monkeypatch.setattr("maglab.sim.environment._module_ok", lambda name: False)
    monkeypatch.setattr(
        "maglab.sim.environment.CPUBackendRouter.available_engines",
        staticmethod(lambda: []),
    )

    report = run_doctor(feature="llm", include_sim=True)

    paths = {item["key"]: item for item in report["simulation"]["backend_paths"]}
    assert paths["mock"]["status"] == "ready"
    ux = {item["key"]: item for item in report["ux_contract"]}
    assert "mock:ready" in ux["gpu-ssh-cpu"]["evidence"]
    assert ux["gpu-ssh-cpu"]["status"] == "partial"


def test_doctor_model_connection_is_partial_without_live_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "maglab.llm.factory.backend_status",
        lambda config: type(
            "Status",
            (),
            {
                "ok": True,
                "mode": "delegated_cli",
                "label": "codex:CLI default · delegated CLI",
                "detail": "codex 1.0",
                "action": "",
            },
        )(),
    )

    report = run_doctor(feature="llm", include_sim=False)

    ux = {item["key"]: item for item in report["ux_contract"]}
    assert ux["models"]["status"] == "partial"
    assert "smoke not run" in ux["models"]["evidence"]


def test_doctor_recommendations_use_backend_action_for_failed_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def _failed_smoke(config):
        return type(
            "Status",
            (),
            {
                "ok": False,
                "mode": "delegated_cli",
                "label": "codex:gpt-5.5 · delegated CLI",
                "detail": "usage limit reached",
                "action": "Wait for quota reset or switch backend with `/connect openai`.",
            },
        )()

    monkeypatch.setattr("maglab.llm.factory.test_llm_backend", _failed_smoke)

    report = run_doctor(feature="llm", include_sim=False, smoke=True)

    assert any("quota reset" in item for item in report["recommendations"])
    assert not any("maglab auth codex" in item for item in report["recommendations"])
