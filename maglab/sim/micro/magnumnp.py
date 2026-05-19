"""magnum.np CPU micromagnetic simulation wrapper.

Design rationale: impl/02-P1-figure-sim.md T-P1-08.

Calls the magnum.np Python API directly from a ``ScaleSpec`` (micro) to run
CPU micromagnetic simulations. Operates Python-natively without external binaries;
it is the default CPU fallback engine for the Mac development environment.

Based on magnum.np 2.x API (MinimizerBB energy minimization + LLGSolver time integration).
"""

from __future__ import annotations

import time

from maglab.sim.custodian import classify_exception
from maglab.sim.parse import JobResult, parse_magnumnp_result
from maglab.sim.spec import ScaleSpec, ScaleType


def _estimate_memory_mb(nx: int, ny: int, nz: int) -> float:
    """Estimate memory usage from the grid size [MB].

    Based on: magnetization vector field (3 float32) + effective field (3 float32)
    + demagnetizing field (6 float32).

    Parameters:
        nx, ny, nz: Number of grid cells.

    Returns:
        Estimated memory [MB].
    """
    n_cells = nx * ny * nz
    bytes_per_cell = 3 * 4 * 5  # 5 vector fields, float32
    return n_cells * bytes_per_cell / 1e6


def run(
    spec: ScaleSpec,
    *,
    dm_tol: float = 1.0,
    max_steps_minimize: int = 2000,
    dt_s: float = 1e-12,
    progress_interval: int = 100,
) -> JobResult:
    """Run a magnum.np CPU simulation from a ScaleSpec and return a JobResult.

    Returns an error JobResult when magnum.np is not installed.

    Operating modes:
        - t_sim_ns = 0: MinimizerBB energy minimization (static equilibrium).
        - t_sim_ns > 0: LLGSolver time integration (dynamics).

    Parameters:
        spec: Micromagnetic ScaleSpec.
        dm_tol: MinimizerBB convergence tolerance (dm_max < dm_tol).
        max_steps_minimize: Maximum MinimizerBB iterations.
        dt_s: LLG time step [s].
        progress_interval: Logging interval during time integration (in steps).

    Returns:
        JobResult.
    """
    if spec.scale != ScaleType.micro:
        raise ValueError(f"magnumnp wrapper only supports scale='micro'. Got: {spec.scale}")

    # Check magnum.np import
    try:
        import magnumnp as mn
        import torch
    except ImportError as exc:
        custodian = classify_exception(exc, "magnumnp")
        return JobResult(
            job_id="magnumnp",
            engine="magnumnp",
            converged=False,
            error_message=f"[{custodian.error_class}] magnum.np not installed: {exc}",
        )

    if spec.material is None or spec.geometry is None:
        return JobResult(
            job_id="magnumnp",
            engine="magnumnp",
            error_message="material and geometry parameters are required.",
        )

    mat = spec.material
    geom = spec.geometry

    # Memory estimate warning
    mem_mb = _estimate_memory_mb(geom.nx, geom.ny, geom.nz)
    if mem_mb > 4000:
        import warnings

        warnings.warn(
            f"Grid {geom.nx}×{geom.ny}×{geom.nz} → estimated memory {mem_mb:.0f} MB. "
            "CPU RAM may be insufficient. Consider reducing the grid size.",
            ResourceWarning,
            stacklevel=2,
        )

    start = time.monotonic()
    converged: bool | None = None
    result_data: dict[str, object] = {}

    try:
        # Create mesh
        dx = geom.dx_nm * 1e-9
        dy = geom.dy_nm * 1e-9
        dz = geom.dz_nm * 1e-9
        pbc = (int(geom.pbc_x), int(geom.pbc_y), int(geom.pbc_z))

        mesh = mn.Mesh(
            n=(geom.nx, geom.ny, geom.nz),
            dx=(dx, dy, dz),
            pbc=pbc,
        )

        # Initialize state
        state = mn.State(mesh, scale=1e9)  # scale=1e9: VTK output in nm units

        # Set material parameters
        state.material = {
            "Ms": mat.Ms_Am,
            "A": mat.A_Jm,
            "alpha": mat.alpha,
        }

        if mat.K_Jm3 != 0.0:
            state.material["Ku"] = mat.K_Jm3
            ax, ay, az = mat.K_axis
            state.material["axis1"] = [ax, ay, az]

        # Set initial magnetization
        mx0, my0, mz0 = spec.initial_m_dir
        if spec.initial_state == "random":
            state.m = state.RandM()
        else:
            state.m = state.Constant([mx0, my0, mz0])
            # Normalize
            import torch

            state.m = torch.nn.functional.normalize(state.m, dim=-1)

        # Assemble energy terms
        terms: list[object] = [
            mn.ExchangeField(),
            mn.DemagField(),
        ]

        if mat.K_Jm3 != 0.0:
            terms.append(mn.UniaxialAnisotropyField())

        # External magnetic field
        if spec.field_sweep is not None:
            hx, hy, hz = spec.field_sweep.H_start_Am
            _mu_0 = 1.25663706212e-6
            terms.append(mn.ExternalField([hx * _mu_0, hy * _mu_0, hz * _mu_0]))

        # Run simulation
        if spec.t_sim_ns <= 0.0:
            # Energy minimization mode
            minimizer = mn.MinimizerBB(terms)
            converged = minimizer.minimize(
                state,
                maxiter=max_steps_minimize,
                dm_tol=dm_tol,
            )

            # Extract average magnetization
            m_avg = state.avg(state.m)
            mx_val = float(m_avg[..., 0].mean())
            my_val = float(m_avg[..., 1].mean())
            mz_val = float(m_avg[..., 2].mean())

            result_data = {
                "mx": mx_val,
                "my": my_val,
                "mz": mz_val,
            }

        else:
            # Time integration mode (LLG)
            llg = mn.LLGSolver(terms)
            t_end = spec.t_sim_ns * 1e-9  # ns → s

            # Collect time-series data
            t_list: list[float] = []
            mx_list: list[float] = []
            my_list: list[float] = []
            mz_list: list[float] = []

            step = 0
            while float(state.t) < t_end:
                llg.step(state, dt_s)
                step += 1

                if step % progress_interval == 0 or float(state.t) >= t_end:
                    m_avg = state.avg(state.m)
                    t_list.append(float(state.t))
                    mx_list.append(float(m_avg[..., 0].mean()))
                    my_list.append(float(m_avg[..., 1].mean()))
                    mz_list.append(float(m_avg[..., 2].mean()))

            converged = True
            result_data = {
                "t": t_list,
                "mx": mx_list,
                "my": my_list,
                "mz": mz_list,
            }

    except Exception as exc:
        custodian_result = classify_exception(exc, "magnumnp")
        elapsed_s = time.monotonic() - start
        return JobResult(
            job_id="magnumnp",
            engine="magnumnp",
            converged=False,
            elapsed_s=elapsed_s,
            error_message=(
                f"[{custodian_result.error_class}] {custodian_result.message} | "
                f"Hint: {custodian_result.hint}"
            ),
            raw_stderr=str(exc),
        )

    elapsed_s = time.monotonic() - start

    return parse_magnumnp_result(
        data=result_data,
        job_id="magnumnp",
        elapsed_s=elapsed_s,
        converged=converged,
        source_ref="magnumnp:cpu",
    )
