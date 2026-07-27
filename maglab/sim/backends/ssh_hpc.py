"""SSH HPC backend — Slurm cluster job submission, polling, and result retrieval.

Design rationale: impl/04-P3-multiscale.md T-P3-13 · plan/03-physics-simulation.md §10.2.

Implements the same abstraction as the P1 local/cpu backend (submit·poll·fetch·cancel).
Designed to be validated in the Mac development environment using ``--backend mock``:
- Mock mode: simulates submission, polling, and result retrieval using local files, without real SSH.
- Real HPC mode: uses paramiko (optional dependency) or subprocess ssh/rsync.

If paramiko is not installed: emits an explicit warning and falls back to mock mode.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.core.atomic import atomic_write_text

# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------


class JobStatus:
    """Slurm job status enumeration."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


@dataclass
class HpcJob:
    """HPC job tracking information.

    Attributes:
        job_id: Local job ID (UUID4).
        slurm_job_id: Job ID assigned by Slurm (arbitrary integer string in mock mode).
        status: Job status.
        submit_time: Submission timestamp (Unix timestamp).
        input_dir: Input file directory.
        output_dir: Result file directory.
        engine: Solver engine name.
        extra: Additional metadata.
    """

    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    slurm_job_id: str = ""
    status: str = JobStatus.PENDING
    submit_time: float = field(default_factory=time.time)
    input_dir: Path = field(default_factory=Path)
    output_dir: Path = field(default_factory=Path)
    engine: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SSH HPC backend
# ---------------------------------------------------------------------------


class SshHpcBackend:
    """Slurm cluster SSH backend.

    Parameters
    ----------
    host:
        HPC hostname (e.g. "cluster.example.com").
    user:
        SSH username.
    remote_work_dir:
        Remote working directory path.
    mock:
        If True, operate in mock mode — local simulation without real SSH.
    """

    def __init__(
        self,
        host: str = "localhost",
        user: str = "",
        remote_work_dir: str = "/tmp/maglab_hpc",
        mock: bool = True,
    ) -> None:
        self.host = host
        self.user = user
        self.remote_work_dir = Path(remote_work_dir)
        self.mock = mock
        self._jobs: dict[str, HpcJob] = {}

        # Check paramiko availability
        self._paramiko_available = False
        if not mock:
            try:
                import paramiko  # type: ignore[import-untyped]  # noqa: F401

                self._paramiko_available = True
            except ImportError:
                import warnings

                warnings.warn(
                    "paramiko is not installed. Falling back to mock mode.\n"
                    "Install it with: pip install paramiko",
                    UserWarning,
                    stacklevel=2,
                )
                self.mock = True

    def submit(
        self,
        input_dir: Path | str,
        script: str,
        engine: str = "vampire",
        n_cpus: int = 8,
        memory_gb: int = 4,
        walltime_h: int = 4,
    ) -> HpcJob:
        """Submit a job to the Slurm cluster.

        Parameters
        ----------
        input_dir:
            Input file directory (local).
        script:
            Execution script content (VAMPIRE input, etc.).
        engine:
            Solver engine name.
        n_cpus:
            Number of CPUs requested.
        memory_gb:
            Memory requested [GB].
        walltime_h:
            Maximum wall time [hours].

        Returns
        -------
        HpcJob
            Submitted job information.
        """
        input_dir = Path(input_dir)
        job = HpcJob(
            input_dir=input_dir,
            output_dir=input_dir / "output",
            engine=engine,
        )

        if self.mock:
            return self._submit_mock(job, script, n_cpus, memory_gb, walltime_h)
        else:
            return self._submit_real(job, script, n_cpus, memory_gb, walltime_h)

    def poll(self, job: HpcJob) -> str:
        """Check the status of a job.

        Parameters
        ----------
        job:
            Job to poll.

        Returns
        -------
        str
            JobStatus string.
        """
        if self.mock:
            return self._poll_mock(job)
        else:
            return self._poll_real(job)

    def fetch(self, job: HpcJob, local_dir: Path | str) -> Path:
        """Retrieve the results of a completed job to a local directory.

        Parameters
        ----------
        job:
            Completed job.
        local_dir:
            Local directory in which to store the results.

        Returns
        -------
        Path
            Retrieved results directory.
        """
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return self._fetch_mock(job, local_dir)
        else:
            return self._fetch_real(job, local_dir)

    def cancel(self, job: HpcJob) -> bool:
        """Cancel a job.

        Parameters
        ----------
        job:
            Job to cancel.

        Returns
        -------
        bool
            True if the cancellation succeeded.
        """
        if self.mock:
            job.status = JobStatus.CANCELLED
            self._save_job_state(job)
            return True
        else:
            return self._cancel_real(job)

    # ------------------------------------------------------------------
    # Mock implementation (local file simulation)
    # ------------------------------------------------------------------

    def _submit_mock(
        self,
        job: HpcJob,
        script: str,
        n_cpus: int,
        memory_gb: int,
        walltime_h: int,
    ) -> HpcJob:
        """Mock mode: simulate submission using local files."""
        # Simulate a Slurm job ID
        job.slurm_job_id = str(hash(job.job_id) % 100000)
        job.status = JobStatus.RUNNING

        # Save the job state file
        job.input_dir.mkdir(parents=True, exist_ok=True)
        job.output_dir.mkdir(parents=True, exist_ok=True)

        # Save the script file
        (job.input_dir / "job.sh").write_text(
            f"#!/bin/bash\n#SBATCH -n {n_cpus}\n#SBATCH --mem={memory_gb}G\n"
            f"#SBATCH -t {walltime_h}:00:00\n\n{script}\n",
            encoding="utf-8",
        )

        # Generate mock completion results (immediate completion simulation)
        self._generate_mock_output(job)
        job.status = JobStatus.COMPLETED
        self._save_job_state(job)

        self._jobs[job.job_id] = job
        return job

    def _poll_mock(self, job: HpcJob) -> str:
        """Mock mode: return the job status."""
        # Read from the state file
        state_file = job.input_dir / "job_state.json"
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return data.get("status", JobStatus.UNKNOWN)
        return job.status

    def _fetch_mock(self, job: HpcJob, local_dir: Path) -> Path:
        """Mock mode: copy result files to local_dir."""
        import shutil

        if job.output_dir.exists():
            for f in job.output_dir.iterdir():
                shutil.copy2(f, local_dir / f.name)
        return local_dir

    def _generate_mock_output(self, job: HpcJob) -> None:
        """Generate a mock atomistic output file (bcc Fe M(T) golden values)."""
        output_file = job.output_dir / "magnetisation"

        # bcc Fe M(T) mock data — β≈0.33 scaling
        # T_C = 1043 K (experimental value)
        lines = ["# Temperature  Mx  My  Mz  |M|  specific_heat\n"]
        T_C_ref = 1043.0
        for T in range(0, 1250, 50):
            if T_C_ref <= T:
                m = 0.0
            else:
                m = (1.0 - T / T_C_ref) ** 0.33
            lines.append(f"{T:.1f}  0.0  0.0  {m:.6f}  {m:.6f}  0.0\n")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("".join(lines), encoding="utf-8")

    def _save_job_state(self, job: HpcJob) -> None:
        """Save job state to JSON."""
        state = {
            "job_id": job.job_id,
            "slurm_job_id": job.slurm_job_id,
            "status": job.status,
            "engine": job.engine,
        }
        # Atomic: _status_mock reads this back with json.loads and no guard, so
        # a truncated write turns every later status query into a crash.
        atomic_write_text(job.input_dir / "job_state.json", json.dumps(state, indent=2))

    # ------------------------------------------------------------------
    # Real HPC implementation (requires paramiko)
    # ------------------------------------------------------------------

    def _submit_real(
        self, job: HpcJob, script: str, n_cpus: int, memory_gb: int, walltime_h: int
    ) -> HpcJob:
        """Real Slurm submission (requires paramiko)."""
        raise NotImplementedError("Real HPC submission requires paramiko. Use mock mode for now.")

    def _poll_real(self, job: HpcJob) -> str:
        """Real squeue polling (requires paramiko)."""
        raise NotImplementedError("Real HPC polling is not implemented. Use mock mode.")

    def _fetch_real(self, job: HpcJob, local_dir: Path) -> Path:
        """Real rsync file retrieval (requires paramiko/rsync)."""
        raise NotImplementedError("Real HPC result retrieval is not implemented. Use mock mode.")

    def _cancel_real(self, job: HpcJob) -> bool:
        """Real scancel execution (requires paramiko)."""
        raise NotImplementedError("Real HPC cancellation is not implemented. Use mock mode.")
