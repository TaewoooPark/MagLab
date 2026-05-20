"""Tests for simulation environment diagnosis."""

from __future__ import annotations

import types

from maglab.sim.environment import diagnose_sim_environment


def test_diagnose_prefers_local_gpu_when_mumax_and_nvidia_are_available(monkeypatch) -> None:
    bins = {"mumax3", "nvidia-smi", "ssh", "rsync"}

    monkeypatch.setattr(
        "maglab.sim.environment._binary_path",
        lambda name: f"/usr/bin/{name}" if name in bins else None,
    )
    monkeypatch.setattr(
        "maglab.sim.environment._module_ok",
        lambda name: name in {"discretisedfield", "micromagneticmodel", "oommfc", "magnumnp"},
    )
    monkeypatch.setattr(
        "maglab.sim.environment.CPUBackendRouter.available_engines",
        staticmethod(lambda: ["magnumnp"]),
    )

    report = diagnose_sim_environment()

    assert report["recommended_backend"] == "local-gpu"
    assert report["local_gpu_ready"] is True
    assert report["cpu_engines"] == ["magnumnp"]
    assert "paramiko" not in {item["name"] for item in report["python"]}
    assert "paramiko" in {item["name"] for item in report["remote_python"]}
    paths = {item["key"]: item for item in report["backend_paths"]}
    assert paths["local-gpu"]["status"] == "ready"
    assert paths["cpu"]["status"] == "ready"
    assert "maglab sim doctor --backend local-gpu" in paths["local-gpu"]["next_command"]


def test_diagnose_uses_mock_when_no_solver_is_detected(monkeypatch) -> None:
    monkeypatch.setattr("maglab.sim.environment._binary_path", lambda name: None)
    monkeypatch.setattr("maglab.sim.environment._module_ok", lambda name: False)
    monkeypatch.setattr(
        "maglab.sim.environment.CPUBackendRouter.available_engines",
        staticmethod(lambda: []),
    )

    report = diagnose_sim_environment()

    assert report["recommended_backend"] == "mock"
    assert report["local_gpu_ready"] is False
    assert "paramiko" not in {item["name"] for item in report["python"]}
    assert "paramiko" in {item["name"] for item in report["remote_python"]}
    paths = {item["key"]: item for item in report["backend_paths"]}
    assert paths["mock"]["status"] == "ready"
    assert paths["cpu"]["status"] == "needs-setup"
    assert paths["local-gpu"]["status"] == "needs-setup"
    assert any("No-GPU safe start" in item for item in report["recommendations"])


def test_diagnose_ssh_target_without_probe_is_non_destructive(monkeypatch) -> None:
    monkeypatch.setattr("maglab.sim.environment._binary_path", lambda name: None)
    monkeypatch.setattr("maglab.sim.environment._module_ok", lambda name: False)
    monkeypatch.setattr(
        "maglab.sim.environment.CPUBackendRouter.available_engines",
        staticmethod(lambda: []),
    )

    report = diagnose_sim_environment(backend="ssh-gpu", host="gpu.example.edu", user="alice")

    assert report["recommended_backend"] == "ssh-gpu"
    assert report["ssh_target"] == "alice@gpu.example.edu"
    assert report["ssh"][1]["name"] == "ssh probe"
    assert report["ssh"][1]["detail"] == "not probed"
    paths = {item["key"]: item for item in report["backend_paths"]}
    assert paths["ssh-gpu"]["status"] == "not-probed"
    assert "no connection was opened" in " ".join(report["recommendations"])


def test_diagnose_ssh_probe_runs_only_when_requested(monkeypatch) -> None:
    monkeypatch.setattr("maglab.sim.environment._binary_path", lambda name: "/usr/bin/ssh")
    monkeypatch.setattr("maglab.sim.environment._module_ok", lambda name: False)
    monkeypatch.setattr(
        "maglab.sim.environment.CPUBackendRouter.available_engines",
        staticmethod(lambda: []),
    )

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="maglab-ok", stderr="")

    monkeypatch.setattr("maglab.sim.environment.subprocess.run", fake_run)

    report = diagnose_sim_environment(
        backend="ssh-hpc",
        host="cluster.example.edu",
        user="alice",
        probe_ssh=True,
    )

    assert report["ssh"][1]["ok"] is True
    paths = {item["key"]: item for item in report["backend_paths"]}
    assert paths["ssh-hpc"]["status"] == "ssh-ready"
    assert calls and calls[0][0] == "ssh"
