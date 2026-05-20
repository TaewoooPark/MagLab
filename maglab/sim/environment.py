"""Simulation environment diagnosis for CPU, local GPU, and SSH backends."""

from __future__ import annotations

import importlib.util
import io
import shutil
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from typing import Any

from maglab.sim.backends.cpu import CPUBackendRouter


@dataclass(frozen=True)
class EnvCheck:
    """One environment prerequisite check."""

    name: str
    ok: bool
    detail: str
    action: str = ""


@dataclass(frozen=True)
class BackendPath:
    """User-facing execution path with deterministic setup guidance."""

    key: str
    label: str
    status: str
    detail: str
    next_command: str
    setup_commands: list[str]
    notes: list[str]


def _module_ok(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _binary_path(binary: str) -> str | None:
    return shutil.which(binary)


def _binary_check(binary: str, *, action: str = "") -> EnvCheck:
    path = _binary_path(binary)
    return EnvCheck(
        name=binary,
        ok=path is not None,
        detail=path or "not found on PATH",
        action=action if path is None else "",
    )


def _module_check(module: str, *, action: str = "") -> EnvCheck:
    ok = _module_ok(module)
    return EnvCheck(
        name=module,
        ok=ok,
        detail="importable" if ok else "not importable",
        action=action if not ok else "",
    )


def _run_ssh_probe(target: str, timeout_s: float) -> EnvCheck:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={max(1, int(timeout_s))}",
        target,
        "printf maglab-ok",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s + 1.0,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - subprocess and SSH failures vary by platform
        return EnvCheck(
            name="ssh probe",
            ok=False,
            detail=str(exc),
            action="Configure SSH keys or omit --probe-ssh until credentials are ready.",
        )

    ok = proc.returncode == 0 and "maglab-ok" in proc.stdout
    detail = proc.stdout.strip() if ok else (proc.stderr.strip() or proc.stdout.strip())
    return EnvCheck(
        name="ssh probe",
        ok=ok,
        detail=detail or f"exit code {proc.returncode}",
        action="" if ok else "Run ssh manually first, then retry with --probe-ssh.",
    )


def _available_cpu_engines() -> list[str]:
    """Detect CPU engines without letting third-party import banners leak to stdout."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return CPUBackendRouter.available_engines()


def _format_remote_doctor_command(
    backend: str,
    *,
    host: str | None,
    user: str | None,
    probe_ssh: bool,
) -> str:
    command = f"maglab sim doctor --backend {backend} --host {host or '<host>'}"
    command += f" --user {user or '<user>'}"
    if probe_ssh:
        command += " --probe-ssh"
    return command


def _ssh_probe_status(ssh_checks: list[EnvCheck], *, probe_ssh: bool, host: str | None) -> str:
    if not host:
        return "needs-target"
    if not probe_ssh:
        return "not-probed"
    probe = next((check for check in ssh_checks if check.name == "ssh probe"), None)
    if probe and probe.ok:
        return "ssh-ready"
    return "ssh-blocked"


def _build_backend_paths(
    *,
    cpu_engines: list[str],
    local_gpu_ready: bool,
    has_mumax: bool,
    has_gpu_probe: bool,
    host: str | None,
    user: str | None,
    ssh_target: str,
    probe_ssh: bool,
    ssh_checks: list[EnvCheck],
) -> list[BackendPath]:
    """Return deterministic setup/run paths without probing remote solver state."""
    cpu_ready = bool(cpu_engines)
    gpu_missing: list[str] = []
    if not has_mumax:
        gpu_missing.append("mumax3")
    if not has_gpu_probe:
        gpu_missing.append("nvidia-smi")

    ssh_status = _ssh_probe_status(ssh_checks, probe_ssh=probe_ssh, host=host)
    remote_target = ssh_target or "<user>@<host>"

    return [
        BackendPath(
            key="mock",
            label="No-GPU dry run",
            status="ready",
            detail="Artifact-only pipeline; no solver, GPU, or SSH connection required.",
            next_command=(
                "maglab sim pipeline --structure bcc_fe "
                "--scales dft,atomistic,micro,device --backend mock"
            ),
            setup_commands=[],
            notes=[
                "Use this first on laptops or fresh installs to validate specs and provenance.",
                "Mock mode does not claim physical solver results.",
            ],
        ),
        BackendPath(
            key="cpu",
            label="Local CPU fallback",
            status="ready" if cpu_ready else "needs-setup",
            detail=(
                f"Detected CPU engine(s): {', '.join(cpu_engines)}."
                if cpu_ready
                else "No Python CPU micromagnetic engine detected."
            ),
            next_command=(
                "maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4"
                if cpu_ready
                else 'pipx inject maglab "maglab[sim]"'
            ),
            setup_commands=[
                'pipx inject maglab "maglab[sim]"',
                "maglab sim doctor --backend cpu",
            ],
            notes=[
                "Keep meshes modest on CPU; start around 64^3 cells or smaller.",
                "CPU is the preferred real-compute fallback when no local GPU is present.",
            ],
        ),
        BackendPath(
            key="local-gpu",
            label="Local NVIDIA GPU",
            status="ready" if local_gpu_ready else "needs-setup",
            detail=(
                "MuMax3 and nvidia-smi are both visible on PATH."
                if local_gpu_ready
                else f"Missing local GPU prerequisite(s): {', '.join(gpu_missing)}."
            ),
            next_command=(
                "maglab sim doctor --backend local-gpu"
                if local_gpu_ready
                else "maglab sim doctor --backend local-gpu"
            ),
            setup_commands=[
                "mumax3 -h",
                "nvidia-smi",
                "maglab sim doctor --backend local-gpu",
            ],
            notes=[
                "MagLab only checks local command visibility here; it does not run a GPU job.",
                "Use this path for real MuMax3 execution after a small validated mock/CPU run.",
            ],
        ),
        BackendPath(
            key="ssh-gpu",
            label="SSH GPU server",
            status=ssh_status,
            detail=(
                f"Remote target configured as {remote_target}."
                if host
                else "No SSH host supplied; remote GPU path is not configured."
            ),
            next_command=_format_remote_doctor_command(
                "ssh-gpu", host=host, user=user, probe_ssh=True
            ),
            setup_commands=[
                "ssh <user>@<host>",
                _format_remote_doctor_command("ssh-gpu", host=host, user=user, probe_ssh=False),
                _format_remote_doctor_command("ssh-gpu", host=host, user=user, probe_ssh=True),
            ],
            notes=[
                "Without --probe-ssh, MagLab records the target but opens no remote connection.",
                "Remote solver modules are not inferred; load MuMax3/CUDA on the host before runs.",
            ],
        ),
        BackendPath(
            key="ssh-hpc",
            label="SSH HPC / Slurm",
            status=ssh_status,
            detail=(
                f"Remote login target configured as {remote_target}."
                if host
                else "No cluster login host supplied; HPC path is not configured."
            ),
            next_command=_format_remote_doctor_command(
                "ssh-hpc", host=host, user=user, probe_ssh=True
            ),
            setup_commands=[
                "ssh <user>@<login-host>",
                _format_remote_doctor_command("ssh-hpc", host=host, user=user, probe_ssh=False),
                _format_remote_doctor_command("ssh-hpc", host=host, user=user, probe_ssh=True),
            ],
            notes=[
                "Local sbatch/squeue checks are advisory only; real Slurm is checked on the cluster.",
                "Keep --probe-ssh off until key-based, non-interactive SSH works in your terminal.",
            ],
        ),
    ]


def diagnose_sim_environment(
    *,
    backend: str = "auto",
    host: str | None = None,
    user: str | None = None,
    remote_work_dir: str = "/tmp/maglab",
    probe_ssh: bool = False,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Return a structured diagnosis of simulation execution readiness.

    The diagnosis is intentionally conservative. It never opens a remote
    connection unless ``probe_ssh`` is true and ``host`` is supplied.
    """
    backend_key = backend.strip().lower().replace("_", "-")
    if backend_key == "gpu":
        backend_key = "ssh-gpu" if host else "local-gpu"
    if backend_key == "hpc":
        backend_key = "ssh-hpc"

    python_checks = [
        _module_check("discretisedfield", action='Install with: pipx inject maglab "maglab[sim]"'),
        _module_check(
            "micromagneticmodel", action='Install with: pipx inject maglab "maglab[sim]"'
        ),
        _module_check("oommfc", action='Install with: pipx inject maglab "maglab[sim]"'),
        _module_check("magnumnp", action='Install with: pipx inject maglab "maglab[sim]"'),
        _module_check("paramiko", action='Install with: pipx inject maglab "maglab[sim]"'),
    ]
    binary_checks = [
        _binary_check("mumax3", action="Install MuMax3 or use mock/CPU backends."),
        _binary_check("oommf", action="Install OOMMF or use magnum.np/mock."),
        _binary_check("oommf.tcl", action="Install OOMMF or set OOMMF on PATH."),
        _binary_check("tclsh", action="Install Tcl/Tk for OOMMF."),
        _binary_check("nvidia-smi", action="Use CPU/mock locally or an SSH GPU backend."),
        _binary_check("vampire", action="Install VAMPIRE for real atomistic runs."),
        _binary_check("spirit", action="Install Spirit for real atomistic runs."),
        _binary_check("pw.x", action="Install Quantum ESPRESSO for real QE DFT runs."),
        _binary_check("vasp", action="Configure licensed VASP separately."),
        _binary_check("sbatch", action="Use SSH HPC or load Slurm on the cluster login node."),
        _binary_check("squeue", action="Use SSH HPC or load Slurm on the cluster login node."),
        _binary_check("scancel", action="Use SSH HPC or load Slurm on the cluster login node."),
        _binary_check("ssh", action="Install OpenSSH client for remote execution."),
        _binary_check("rsync", action="Install rsync for remote result transfer."),
    ]

    cpu_engines = _available_cpu_engines()
    has_mumax = any(c.name == "mumax3" and c.ok for c in binary_checks)
    has_gpu_probe = any(c.name == "nvidia-smi" and c.ok for c in binary_checks)
    local_gpu_ready = has_mumax and has_gpu_probe

    ssh_target = ""
    ssh_checks: list[EnvCheck] = []
    if host:
        ssh_target = f"{user}@{host}" if user else host
        ssh_checks.append(
            EnvCheck(
                name="remote target",
                ok=True,
                detail=f"{ssh_target}:{remote_work_dir}",
            )
        )
        if probe_ssh:
            ssh_checks.append(_run_ssh_probe(ssh_target, timeout_s))
        else:
            ssh_checks.append(
                EnvCheck(
                    name="ssh probe",
                    ok=False,
                    detail="not probed",
                    action="Add --probe-ssh after SSH keys are configured.",
                )
            )

    recommended_backend = "mock"
    if backend_key in {"cpu", "local-cpu"}:
        recommended_backend = "cpu" if cpu_engines else "mock"
    elif backend_key == "local-gpu":
        recommended_backend = "local-gpu" if local_gpu_ready else "mock"
    elif backend_key in {"ssh-gpu", "ssh-hpc"}:
        recommended_backend = backend_key if host else "mock"
    elif backend_key == "auto":
        if local_gpu_ready:
            recommended_backend = "local-gpu"
        elif cpu_engines:
            recommended_backend = "cpu"
        else:
            recommended_backend = "mock"

    backend_paths = _build_backend_paths(
        cpu_engines=cpu_engines,
        local_gpu_ready=local_gpu_ready,
        has_mumax=has_mumax,
        has_gpu_probe=has_gpu_probe,
        host=host,
        user=user,
        ssh_target=ssh_target,
        probe_ssh=probe_ssh,
        ssh_checks=ssh_checks,
    )

    recommendations: list[str] = []
    recommendations.append(f"Recommended backend now: {recommended_backend}.")
    recommendations.append(
        "No-GPU safe start: maglab sim pipeline --structure bcc_fe "
        "--scales dft,atomistic,micro,device --backend mock"
    )
    if recommended_backend == "mock":
        recommendations.append(
            "Use mock mode before spending solver time; it validates schemas and provenance only."
        )
    if cpu_engines:
        recommendations.append(
            f"CPU fallback available via {cpu_engines[0]!r}; keep meshes modest "
            "(roughly <= 64^3 cells)."
        )
    else:
        recommendations.append(
            "No CPU solver was detected; install the simulation extra or an external solver."
        )
    if local_gpu_ready:
        recommendations.append("Local GPU path looks usable for MuMax3-style GPU execution.")
    else:
        recommendations.append(
            "Local GPU setup: install MuMax3, confirm `nvidia-smi`, then rerun "
            "`maglab sim doctor --backend local-gpu`."
        )
    if not host:
        recommendations.append(
            "SSH GPU/HPC setup: rerun without probing first: "
            "maglab sim doctor --backend ssh-gpu --host <host> --user <user>; "
            "add --probe-ssh only after terminal SSH works."
        )
    elif probe_ssh:
        recommendations.append(
            f"Remote target checked: {ssh_target}. Confirm solver modules on the host before real runs."
        )
    else:
        recommendations.append(
            f"Remote target recorded as {ssh_target}; no connection was opened. "
            "Add --probe-ssh after keys are configured."
        )

    return {
        "backend_requested": backend_key,
        "recommended_backend": recommended_backend,
        "cpu_engines": cpu_engines,
        "local_gpu_ready": local_gpu_ready,
        "ssh_target": ssh_target,
        "backend_paths": [asdict(path) for path in backend_paths],
        "python": [asdict(c) for c in python_checks],
        "binaries": [asdict(c) for c in binary_checks],
        "ssh": [asdict(c) for c in ssh_checks],
        "recommendations": recommendations,
    }
