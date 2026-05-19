"""Atomistic simulation input file generator — VAMPIRE·Spirit.

Design rationale: impl/04-P3-multiscale.md T-P3-04 · plan/03-physics-simulation.md §10.1.

Accepts handoff parameters (J_ij·MAE·DMI·m) supplied by ``handoff.py`` and
serializes them into VAMPIRE or Spirit input file formats.
Supports temperature-sweep runs for M_s(T)·T_C extraction.
"""

from __future__ import annotations

import textwrap
from enum import StrEnum
from pathlib import Path
from typing import Any


class AtomisticEngine(StrEnum):
    """Supported atomistic solver engines."""

    VAMPIRE = "vampire"
    SPIRIT = "spirit"


class AtomisticInputGenerator:
    """Atomistic simulation input file generator.

    Parameters
    ----------
    engine:
        Target solver engine.
    """

    def __init__(self, engine: AtomisticEngine = AtomisticEngine.VAMPIRE) -> None:
        self.engine = engine

    def generate(
        self,
        params: dict[str, Any],
        output_dir: Path | str = Path("."),
    ) -> dict[str, Path]:
        """Generate input files and return a file-path dictionary.

        Parameters
        ----------
        params:
            Atomistic simulation parameter dictionary. Key parameters:
            - ``"J_ij_K"``:    Exchange coupling list [K] (post-handoff units).
            - ``"J_ij_pairs"``: Exchange-pair index list [(i, j, J_K), ...].
            - ``"K_J"``:        Anisotropy constant [J] (uniaxial).
            - ``"m_muB"``:      Magnetic moment [μ_B/atom].
            - ``"D_J"``:        DMI magnitude [J].
            - ``"T_start_K"``:  Temperature sweep start [K].
            - ``"T_end_K"``:    Temperature sweep end [K].
            - ``"T_step_K"``:   Temperature step [K].
            - ``"n_cells"``:    Supercell size (default 10×10×10).
            - ``"equilibration_steps"``: Equilibration MC steps.
            - ``"measurement_steps"``:  Measurement MC steps.
        output_dir:
            Output directory for the input files.

        Returns
        -------
        dict[str, Path]
            File role → path dictionary.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.engine == AtomisticEngine.VAMPIRE:
            return self._generate_vampire(params, output_dir)
        elif self.engine == AtomisticEngine.SPIRIT:
            return self._generate_spirit(params, output_dir)
        else:
            raise ValueError(f"Unsupported engine: {self.engine}")

    # ------------------------------------------------------------------
    # VAMPIRE input generation
    # ------------------------------------------------------------------

    def _generate_vampire(self, params: dict[str, Any], output_dir: Path) -> dict[str, Path]:
        """Generate VAMPIRE input and material files.

        VAMPIRE documentation: https://vampire.york.ac.uk/
        Default values based on bcc Fe literature:
        - J_ij [K]: Pajda et al., Phys. Rev. B 64, 174402 (2001).
        - K [J]: Ono et al., J. Magn. Magn. Mater. 198-199, 377 (1999).
        - m [μ_B/atom]: 2.22 (experimental value).
        """
        # Extract parameters (defaults: bcc Fe)
        J_ij_pairs: list[tuple[int, int, float]] = params.get(
            "J_ij_pairs",
            [(1, 1, 398.0)],  # 1NN bcc Fe: ~398 K (Pajda 2001)
        )
        K_J: float = params.get("K_J", 4.28e-24)  # bcc Fe MAE ~48 μeV/atom = 4.28e-24 J
        m_muB: float = params.get("m_muB", 2.22)  # bcc Fe
        D_J: float = params.get("D_J", 0.0)

        T_start: float = params.get("T_start_K", 0.0)
        T_end: float = params.get("T_end_K", 1200.0)
        T_step: float = params.get("T_step_K", 50.0)

        n_cells: int = params.get("n_cells", 10)
        eq_steps: int = params.get("equilibration_steps", 10000)
        meas_steps: int = params.get("measurement_steps", 50000)

        # material file — VAMPIRE format
        # μ_B = 9.274e-24 J/T
        mu_B_J = 9.2740100657e-24
        mu_s_J = m_muB * mu_B_J  # [J/T]

        mat_content = textwrap.dedent(f"""\
            material:num-materials=1
            material[1]:material-name=Fe
            material[1]:damping-constant=0.1
            material[1]:exchange-matrix[1][1]={J_ij_pairs[0][2]:.6f}
            material[1]:uniaxial-anisotropy-constant={K_J:.6e}
            material[1]:atomic-spin-moment={mu_s_J:.6e} !muB
            material[1]:material-element=Fe
        """)

        # Additional exchange pairs (2NN and beyond)
        for i, j, j_val in J_ij_pairs[1:]:
            mat_content += f"material[{i}]:exchange-matrix[{i}][{j}]={j_val:.6f}\n"

        if D_J != 0.0:
            mat_content += f"material[1]:dmi-constant={D_J:.6e}\n"

        # input file — VAMPIRE format
        n_T_steps = max(1, int((T_end - T_start) / T_step) + 1)
        input_content = textwrap.dedent(f"""\
            #-------------------------------------------------------------------
            # VAMPIRE input file — bcc Fe atomistic simulation
            # Reference: VAMPIRE (https://vampire.york.ac.uk/)
            # J_ij source: handoff parameters (DFT → atomistic)
            #-------------------------------------------------------------------

            create:crystal-structure=bcc

            dimensions:unit-cell-size=2.87 !angstroms
            dimensions:system-size-x={n_cells} !unit cells
            dimensions:system-size-y={n_cells} !unit cells
            dimensions:system-size-z={n_cells} !unit cells

            sim:temperature={T_start:.1f}
            sim:equilibration-temperature={T_start:.1f}
            sim:minimum-temperature={T_start:.1f}
            sim:maximum-temperature={T_end:.1f}
            sim:temperature-increment={T_step:.1f}
            sim:equilibration-time-steps={eq_steps}
            sim:loop-time-steps={meas_steps}
            sim:total-time-steps={n_T_steps * (eq_steps + meas_steps)}

            sim:integrator=monte-carlo
            output:magnetisation
            output:magnetisation-length
            output:temperature
            output:specific-heat

            material:file=mat.mat
        """)

        mat_path = output_dir / "mat.mat"
        input_path = output_dir / "input"
        mat_path.write_text(mat_content, encoding="utf-8")
        input_path.write_text(input_content, encoding="utf-8")

        return {"input": input_path, "material": mat_path}

    # ------------------------------------------------------------------
    # Spirit input generation
    # ------------------------------------------------------------------

    def _generate_spirit(self, params: dict[str, Any], output_dir: Path) -> dict[str, Path]:
        """Generate a Spirit cfg.json input file.

        Spirit documentation: https://spirit-code.github.io/
        """
        import json

        J_ij_pairs = params.get("J_ij_pairs", [(1, 1, 398.0)])
        K_J = params.get("K_J", 4.28e-24)
        m_muB = params.get("m_muB", 2.22)
        D_J = params.get("D_J", 0.0)
        T_start = params.get("T_start_K", 0.0)
        T_end = params.get("T_end_K", 1200.0)
        T_step = params.get("T_step_K", 50.0)

        mu_B_J = 9.2740100657e-24

        cfg: dict[str, Any] = {
            "geometry": {
                "lattice_constant": 2.87,
                "bravais_lattice": "BCC",
                "n_cells": [10, 10, 10],
            },
            "hamiltonian": {
                "exchange_magnitude": [
                    {"i": p[0], "j": p[1], "J": p[2] * 1.380649e-23}  # K → J
                    for p in J_ij_pairs
                ],
                "anisotropy": {"magnitude": K_J, "normal": [0.0, 0.0, 1.0]},
                "dmi": {"magnitude": D_J, "chirality": "Bloch"},
            },
            "parameters": {
                "n_iterations": 100000,
                "n_iterations_log": 1000,
                "temperature": T_start,
                "temperature_end": T_end,
                "temperature_step": T_step,
                "mu_s": m_muB * mu_B_J,
            },
        }

        cfg_path = output_dir / "cfg.json"
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return {"config": cfg_path}
