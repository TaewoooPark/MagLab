"""Multiscale pipeline — DFT → atomistic → micromagnetic → device chaining.

Design rationale: impl/04-P3-multiscale.md T-P3-12·T-P3-19 · plan/03-physics-simulation.md §10.1.

``maglab sim pipeline`` CLI calls this module. Each scale is executed in order,
connected by handoffs, and all results are recorded as provenance DataPoints.

T-P3-19 bilevel simulation interface: ``sim_objective(params)`` is a callable
that runs atomistic simulation and returns M(T)/T_C — P2 analysis/ calls this
function from the outer fitting loop.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.provenance.datapoint import DataPoint, ProvenanceType
from maglab.sim.atomistic.input_gen import AtomisticEngine, AtomisticInputGenerator
from maglab.sim.atomistic.parse_atomistic import (
    AtomisticResult,
    parse_vampire_output,
)
from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator
from maglab.sim.dft.parse_dft import DFTResult, parse_dft_output
from maglab.sim.handoff import (
    HandoffResult,
    atomistic_to_micro,
    dft_to_atomistic,
    micro_to_device,
)


@dataclass
class PipelineResult:
    """Full multiscale pipeline result.

    Attributes:
        pipeline_id: Unique pipeline ID.
        scales_run: List of scales that were executed.
        dft_result: DFT scale result.
        atomistic_result: Atomistic scale result.
        handoff_dft_to_atm: DFT→atomistic handoff result.
        handoff_atm_to_micro: Atomistic→micromagnetic handoff result.
        handoff_micro_to_dev: Micromagnetic→device handoff result.
        micro_params: Micromagnetic parameter dictionary (atomistic→micro handoff output).
        device_params: Device parameter dictionary.
        provenance_chain: All DataPoints in order.
        errors: Per-stage error messages.
        warnings: Per-stage warning messages.
    """

    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    scales_run: list[str] = field(default_factory=list)
    dft_result: DFTResult | None = None
    atomistic_result: AtomisticResult | None = None
    handoff_dft_to_atm: HandoffResult | None = None
    handoff_atm_to_micro: HandoffResult | None = None
    handoff_micro_to_dev: HandoffResult | None = None
    micro_params: dict[str, Any] = field(default_factory=dict)
    device_params: dict[str, Any] = field(default_factory=dict)
    provenance_chain: list[DataPoint] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return a summary text."""
        tc_str = ""
        if self.atomistic_result and self.atomistic_result.T_C_K:
            tc_str = f" | T_C={self.atomistic_result.T_C_K:.0f} K"
        return (
            f"pipeline [{self.pipeline_id}] | "
            f"scales: {' → '.join(self.scales_run)}{tc_str} | "
            f"errors: {len(self.errors)} | "
            f"provenance: {len(self.provenance_chain)}"
        )


def run_pipeline(
    structure: dict[str, Any] | None = None,
    scales: list[str] | None = None,
    target_temp_K: float = 300.0,
    dft_engine: str = "qe",
    atomistic_engine: str = "vampire",
    backend: str = "mock",
    work_dir: Path | str = Path("./pipeline_work"),
    J_ij_meV_override: list[float] | None = None,
    T_K_override: list[float] | None = None,
    M_s_Am_override: list[float] | None = None,
) -> PipelineResult:
    """Run the multiscale pipeline.

    Parameters
    ----------
    structure:
        Crystal structure dictionary. If None, uses bcc Fe defaults.
    scales:
        List of scales to run. Default: ["dft", "atomistic", "micro"].
    target_temp_K:
        Target temperature for micromagnetic parameter extraction [K].
    dft_engine:
        DFT engine name ("qe" / "vasp" / "fleur").
    atomistic_engine:
        Atomistic engine name ("vampire" / "spirit").
    backend:
        Execution backend ("mock" / "local" / "ssh_hpc").
        "mock" simulates using golden values without a real solver.
    work_dir:
        Working directory.
    J_ij_meV_override:
        Directly specified DFT J_ij values (used in mock mode).
    T_K_override:
        Directly specified atomistic M(T) temperature array (mock mode).
    M_s_Am_override:
        Directly specified atomistic M(T) magnetization array (mock mode).

    Returns
    -------
    PipelineResult
    """
    scales = scales or ["dft", "atomistic", "micro"]
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    result = PipelineResult()

    # bcc Fe default structure
    if structure is None:
        structure = {
            "species": ["Fe"],
            "positions_frac": [[0.0, 0.0, 0.0]],
            "lattice_ang": [2.87, 2.87, 2.87, 90.0, 90.0, 90.0],
        }

    # ----------------------------------------------------------------
    # Scale 1: DFT
    # ----------------------------------------------------------------
    if "dft" in scales:
        result.scales_run.append("dft")

        if backend == "mock" or J_ij_meV_override is not None:
            # Mock DFT result — bcc Fe golden values
            # J_ij: Pajda et al., Phys. Rev. B 64, 174402 (2001)
            # 1NN: ~34.3 meV (= 398 K)
            J_mock = J_ij_meV_override or [34.3]
            dft_r = DFTResult(
                engine=f"{dft_engine}(mock)",
                converged=True,
                J_ij_meV=J_mock,
                m_muB=2.22,  # bcc Fe experimental value [μ_B/atom]
                MAE_meV_atom=0.0414,  # bcc Fe MAE ~0.41 μeV/atom → ~0.041 meV (experiment)
                # Source: Jansen, J. Phys. F: Metal Phys. 18, L117 (1988)
                total_energy_eV=None,
            )
        else:
            # Real DFT execution
            gen = DFTInputGenerator(
                engine=DFTEngine(dft_engine),
                calc_type=DFTCalcType.JIJ,
            )
            gen.generate(structure, output_dir=work_dir / "dft")
            # Actual execution handled by the backend — stub here
            dft_out = work_dir / "dft" / "pw.out"
            dft_r = parse_dft_output(dft_out, engine=dft_engine)
            if not dft_r.converged:
                result.errors.append(f"DFT convergence failed: {dft_r.engine}")
                return result

        result.dft_result = dft_r
        result.provenance_chain.extend(dft_r.quantities.values())

    # ----------------------------------------------------------------
    # Handoff 1: DFT → atomistic
    # ----------------------------------------------------------------
    if "dft" in scales and "atomistic" in scales:
        dft_r_opt = result.dft_result
        if dft_r_opt is None or not dft_r_opt.J_ij_meV:
            result.warnings.append("DFT J_ij not available — using atomistic defaults")
            j_ij = [34.3]
            mae_meV: float | None = None
            m_mub: float | None = 2.22
        else:
            j_ij = dft_r_opt.J_ij_meV
            mae_meV = dft_r_opt.MAE_meV_atom
            m_mub = dft_r_opt.m_muB

        try:
            h1 = dft_to_atomistic(
                J_ij_meV=j_ij,
                MAE_meV_atom=mae_meV,
                m_muB=m_mub,
                source_ref=f"pipeline/{result.pipeline_id}/dft->atomistic",
            )
            result.handoff_dft_to_atm = h1
            result.provenance_chain.extend(h1.provenance_datapoints)
        except Exception as exc:
            result.errors.append(f"DFT→atomistic handoff failed: {exc}")
            return result

    # ----------------------------------------------------------------
    # Scale 2: atomistic
    # ----------------------------------------------------------------
    if "atomistic" in scales:
        result.scales_run.append("atomistic")

        if backend == "mock" or (T_K_override is not None and M_s_Am_override is not None):
            # Mock atomistic result — bcc Fe golden values
            # M(T): Pajda 2001, T_C = 1043 K (experiment)
            if T_K_override and M_s_Am_override:
                T_mock = T_K_override
                M_mock = M_s_Am_override
            else:
                # Experiment-based M_s(T) approximation (Bloch T^(3/2) law)
                # M_s(0) = 1.71e6 A/m (bcc Fe experimental value)
                # T_C = 1043 K (bcc Fe experimental value)
                T_C_ref = 1043.0
                Ms_0 = 1.71e6
                T_mock_arr = [float(t) for t in range(0, 1250, 50)]
                # Simple mean-field approximation: M = M_s_0 × sqrt(1 - T/T_C) for T < T_C
                M_mock_arr = []
                for T in T_mock_arr:
                    if T_C_ref <= T:
                        M_mock_arr.append(0.0)
                    else:
                        # beta ~ 0.33 (bcc Fe Heisenberg 3D)
                        m_norm = (1.0 - T / T_C_ref) ** 0.33
                        M_mock_arr.append(Ms_0 * m_norm)
                T_mock = T_mock_arr
                M_mock = M_mock_arr

            import numpy as np

            from maglab.sim.atomistic.parse_atomistic import _extract_tc_from_mt

            T_arr = np.array(T_mock)
            M_arr = np.array(M_mock)
            M_norm = M_arr / (np.max(M_arr) + 1e-30)
            T_C_extracted = _extract_tc_from_mt(T_arr, M_norm)

            quantities: dict[str, DataPoint] = {}
            if T_C_extracted is not None:
                quantities["T_C_K"] = DataPoint(
                    value=T_C_extracted,
                    units="K",
                    provenance_type=ProvenanceType.SIMULATED,
                    source_ref=f"pipeline/{result.pipeline_id}/atomistic(mock)",
                    conditions={"engine": f"{atomistic_engine}(mock)"},
                )

            atm_r = AtomisticResult(
                engine=f"{atomistic_engine}(mock)",
                source_file="mock",
                T_K=T_mock,
                M_s_Am=M_mock,
                T_C_K=T_C_extracted,
                converged=True,
                quantities=quantities,
            )
        else:
            # Real atomistic execution
            atm_params = result.handoff_dft_to_atm.params if result.handoff_dft_to_atm else {}
            atm_gen = AtomisticInputGenerator(engine=AtomisticEngine(atomistic_engine))
            atm_gen.generate(
                {
                    "J_ij_pairs": atm_params.get("J_ij_pairs_K", [(1, 1, 398.0)]),
                    "K_J": atm_params.get("K_J", 4.28e-24),
                    "m_muB": atm_params.get("m_muB", 2.22),
                },
                output_dir=work_dir / "atomistic",
            )
            atm_out_dir = work_dir / "atomistic"
            atm_r = parse_vampire_output(atm_out_dir)
            if not atm_r.converged:
                result.errors.append("Atomistic simulation failed to converge or produced no output")
                return result

        result.atomistic_result = atm_r
        result.provenance_chain.extend(atm_r.quantities.values())

    # ----------------------------------------------------------------
    # Handoff 2: atomistic → micromagnetic
    # ----------------------------------------------------------------
    if "atomistic" in scales and "micro" in scales:
        atm_r_opt = result.atomistic_result
        if atm_r_opt is None or not atm_r_opt.T_K:
            result.errors.append("No atomistic result — atomistic→micro handoff not possible")
            return result

        # J_1 [K] — obtain from handoff parameters
        j_1_K: float | None = None
        if result.handoff_dft_to_atm:
            j_list = result.handoff_dft_to_atm.params.get("J_ij_K", [])
            j_1_K = j_list[0] if j_list else None

        try:
            h2 = atomistic_to_micro(
                T_K=atm_r_opt.T_K,
                M_s_Am=atm_r_opt.M_s_Am,
                T_target_K=target_temp_K,
                J_1_K=j_1_K,
                source_ref=f"pipeline/{result.pipeline_id}/atomistic->micro",
            )
            result.handoff_atm_to_micro = h2
            result.micro_params = h2.params
            result.provenance_chain.extend(h2.provenance_datapoints)
        except Exception as exc:
            result.errors.append(f"Atomistic→micro handoff failed: {exc}")
            return result

    # ----------------------------------------------------------------
    # Scale 3: micromagnetic (parameter forwarding check)
    # ----------------------------------------------------------------
    if "micro" in scales:
        result.scales_run.append("micro")
        # Actual micromagnetic simulation is handled by the sim/micro/ backend
        # Only parameter validation is performed here
        mp = result.micro_params
        if not mp:
            result.warnings.append("Micromagnetic parameters are empty.")

    # ----------------------------------------------------------------
    # Handoff 3: micromagnetic → device (optional)
    # ----------------------------------------------------------------
    if "micro" in scales and "device" in scales:
        mp = result.micro_params
        if mp:
            try:
                h3 = micro_to_device(
                    Ms_Am=mp.get("Ms_Am", 1.71e6),
                    A_Jm=mp.get("A_Jm", 2.1e-11),
                    alpha=0.01,
                    K_Jm3=mp.get("K_Jm3", 0.0),
                    D_Jm2=mp.get("D_Jm2", 0.0),
                    source_ref=f"pipeline/{result.pipeline_id}/micro->device",
                )
                result.handoff_micro_to_dev = h3
                result.device_params = h3.params
                result.provenance_chain.extend(h3.provenance_datapoints)
                result.scales_run.append("device")
            except Exception as exc:
                result.warnings.append(f"Micro→device handoff failed: {exc}")

    return result


# ---------------------------------------------------------------------------
# Bilevel simulation optimization interface (T-P3-19)
# ---------------------------------------------------------------------------


def sim_objective(
    params: dict[str, float],
    T_range_K: list[float] | None = None,
    engine: str = "vampire",
    backend: str = "mock",
) -> dict[str, Any]:
    """Callable that runs atomistic simulation and returns M(T)/T_C.

    T-P3-19: P2 ``analysis/`` calls this function from the outer fitting loop.
    Inner deterministic layer of bilevel optimization.

    Interface contract:
    - Input: J_ij[meV], MAE[meV/atom], DMI[meV] parameter dictionary.
    - Output: M(T) curve/T_C dictionary.

    Parameters
    ----------
    params:
        Optimization parameters. Key fields:
        - ``"J_1_meV"``: Nearest-neighbor exchange coupling [meV].
        - ``"MAE_meV_atom"``: MAE [meV/atom].
        - ``"DMI_meV"``: DMI [meV].
    T_range_K:
        Temperature range [K]. None defaults to [0, 1300, 50].
    engine:
        Atomistic engine.
    backend:
        Execution backend.

    Returns
    -------
    dict
        - ``"T_K"``: Temperature array [K].
        - ``"M_s_Am"``: Saturation magnetization array [A/m].
        - ``"T_C_K"``: Curie temperature [K] (may be None).
        - ``"converged"``: Convergence status.
    """
    import numpy as np

    J_1_meV = params.get("J_1_meV", 34.3)
    MAE = params.get("MAE_meV_atom", 0.041)
    DMI = params.get("DMI_meV", 0.0)

    if T_range_K is None:
        T_range_K = [float(t) for t in range(0, 1300, 50)]

    if backend == "mock":
        # Mean-field approximation M(T) curve — J_1 used for T_C estimate
        # T_C (mean-field) = z × J₁ / (3 × k_B) × S(S+1)
        # bcc Fe: z=8, S=1, k_B=1 → T_C_mf = 8 × J₁[K] / 3
        # J₁[K] = J₁[meV] × 11.6045 K/meV
        mev_to_K = 11.6045  # approximation (use physics/constants.py for exact value)
        J_1_K = J_1_meV * mev_to_K
        T_C_mf = 8.0 * J_1_K / 3.0  # mean-field (z=8, S=1)

        T_arr = np.array(T_range_K)
        M_arr = np.zeros_like(T_arr)
        Ms_0 = 1.71e6  # bcc Fe [A/m]

        for i, T in enumerate(T_arr):
            if T_C_mf > T:
                M_arr[i] = Ms_0 * (1.0 - T / T_C_mf) ** 0.33
            else:
                M_arr[i] = 0.0

        from maglab.sim.atomistic.parse_atomistic import _extract_tc_from_mt

        M_norm = M_arr / (np.max(M_arr) + 1e-30)
        T_C = _extract_tc_from_mt(T_arr, M_norm)

        return {
            "T_K": T_arr.tolist(),
            "M_s_Am": M_arr.tolist(),
            "T_C_K": T_C,
            "converged": True,
            "params_used": {"J_1_meV": J_1_meV, "MAE": MAE, "DMI": DMI},
        }
    else:
        # Real atomistic pipeline execution
        pr = run_pipeline(
            scales=["dft", "atomistic"],
            J_ij_meV_override=[J_1_meV],
            atomistic_engine=engine,
            backend=backend,
        )
        if pr.atomistic_result:
            return {
                "T_K": pr.atomistic_result.T_K,
                "M_s_Am": pr.atomistic_result.M_s_Am,
                "T_C_K": pr.atomistic_result.T_C_K,
                "converged": pr.atomistic_result.converged,
            }
        return {"T_K": [], "M_s_Am": [], "T_C_K": None, "converged": False}
