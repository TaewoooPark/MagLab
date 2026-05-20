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
