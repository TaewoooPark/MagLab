"""SSH GPU server backend — direct execution on a single GPU server.

Design rationale: impl/04-P3-multiscale.md T-P3-13.

Implements the same abstraction as SshHpcBackend (submit·poll·fetch·cancel),
but executes directly on a single GPU server without Slurm.
Mock mode: local simulation without actual SSH connectivity.
"""

from __future__ import annotations

from pathlib import Path

from maglab.sim.backends.ssh_hpc import HpcJob, JobStatus, SshHpcBackend


class SshGpuBackend(SshHpcBackend):
    """Direct-execution backend for a single GPU server.

    Subclasses SshHpcBackend and overrides submission to run directly without Slurm.
    Used for MuMax3 GPU execution, Spirit GPU mode, etc.

    Parameters
    ----------
    host:
        GPU server hostname.
    user:
        SSH username.
    remote_work_dir:
        Remote working directory.
    gpu_id:
        GPU ID to use (e.g. 0, 1).
    mock:
        If True, operate in mock mode.
    """

    def __init__(
        self,
        host: str = "gpu-server.example.com",
        user: str = "",
        remote_work_dir: str = "/tmp/maglab_gpu",
        gpu_id: int = 0,
        mock: bool = True,
    ) -> None:
        super().__init__(host=host, user=user, remote_work_dir=remote_work_dir, mock=mock)
        self.gpu_id = gpu_id

    def submit(
        self,
        input_dir: Path | str,
        script: str,
        engine: str = "mumax3",
        n_cpus: int = 4,
        memory_gb: int = 8,
        walltime_h: int = 2,
    ) -> HpcJob:
        """Submit a job directly to the GPU server.

        Parameters
        ----------
        input_dir:
            Input file directory.
        script:
            Execution script content.
        engine:
            Solver engine name (mumax3, spirit, etc.).
        n_cpus:
            Number of CPUs (ignored in GPU mode).
        memory_gb:
            Memory [GB].
        walltime_h:
            Maximum wall time [hours].

        Returns
        -------
        HpcJob
        """
        input_dir = Path(input_dir)
        job = HpcJob(
            input_dir=input_dir,
            output_dir=input_dir / "output",
            engine=engine,
        )

        if self.mock:
            return self._submit_mock_gpu(job, script)
        else:
            return self._submit_real_gpu(job, script)

    def _submit_mock_gpu(self, job: HpcJob, script: str) -> HpcJob:
        """Mock GPU submission — simulates immediate completion."""
        import json

        job.slurm_job_id = f"gpu_{hash(job.job_id) % 10000}"
        job.status = JobStatus.RUNNING
        job.input_dir.mkdir(parents=True, exist_ok=True)
        job.output_dir.mkdir(parents=True, exist_ok=True)

        # Save the script
        (job.input_dir / "run.sh").write_text(
            f"#!/bin/bash\nexport CUDA_VISIBLE_DEVICES={self.gpu_id}\n\n{script}\n",
            encoding="utf-8",
        )

        # Generate mock output (MuMax3 table format)
        if job.engine in ("mumax3", "gpu"):
            self._generate_mock_mumax3_output(job)

        job.status = JobStatus.COMPLETED
        state = {"job_id": job.job_id, "slurm_job_id": job.slurm_job_id, "status": job.status}
        (job.input_dir / "job_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        self._jobs[job.job_id] = job
        return job

    def _generate_mock_mumax3_output(self, job: HpcJob) -> None:
        """Generate mock MuMax3 table output."""
        output_file = job.output_dir / "table.txt"
        lines = ["# t (s)\tmx ()\tmy ()\tmz ()\n"]
        import math

        for i in range(100):
            t = i * 1e-12
            # Simple damped precession (LLG analytical solution)
            alpha = 0.01
            omega = 2 * math.pi * 1e10
            mz = math.exp(-alpha * omega * t)
            mx = math.sqrt(max(0, 1 - mz**2)) * math.cos(omega * t)
            my = math.sqrt(max(0, 1 - mz**2)) * math.sin(omega * t)
            lines.append(f"{t:.6e}\t{mx:.6f}\t{my:.6f}\t{mz:.6f}\n")
        output_file.write_text("".join(lines), encoding="utf-8")

    def _submit_real_gpu(self, job: HpcJob, script: str) -> HpcJob:
        """Direct execution on a real GPU server (requires paramiko)."""
        raise NotImplementedError(
            "Real GPU server execution requires paramiko. Use mock mode for now."
        )
