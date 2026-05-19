"""DFT input file generator — VASP·QE·FLEUR.

Design rationale: impl/04-P3-multiscale.md T-P3-01 · plan/03-physics-simulation.md §10.1.

Accepts the DFT ``ScaleSpec`` from ``MultiScaleSpec`` (DFT parameters stored in the ``extra``
field) and serializes it into each engine's input file format. Handles SOC·MAE·DMI·J_ij
calculation tags.

File generation works even without solver binaries installed (execution is delegated to the backend).
"""

from __future__ import annotations

import textwrap
from enum import StrEnum
from pathlib import Path
from typing import Any


class DFTEngine(StrEnum):
    """Supported DFT solver engines."""

    VASP = "vasp"
    QE = "qe"
    FLEUR = "fleur"


class DFTCalcType(StrEnum):
    """DFT calculation type.

    - SCF   : Self-consistent field calculation (basic)
    - JIJ   : Exchange coupling J_ij extraction (includes TB2J preprocessing)
    - MAE   : Magnetocrystalline anisotropy energy
    - DMI   : Dzyaloshinskii-Moriya interaction
    """

    SCF = "scf"
    JIJ = "jij"
    MAE = "mae"
    DMI = "dmi"


# ---------------------------------------------------------------------------
# Built-in structure database — string ID → structure dictionary
# ---------------------------------------------------------------------------

# bcc Fe default values
# Sources: CRC Handbook 2022 (lattice constant), Coey 2010 p.126 (Ms)
_BUILTIN_STRUCTURES: dict[str, dict[str, Any]] = {
    "bcc_fe": {
        "species": ["Fe"],
        "positions_frac": [[0.0, 0.0, 0.0]],
        "lattice_ang": [2.87, 2.87, 2.87, 90.0, 90.0, 90.0],
        "natoms": 1,
    },
    "bcc_fe_2atom": {
        "species": ["Fe", "Fe"],
        "positions_frac": [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
        "lattice_ang": [2.87, 2.87, 2.87, 90.0, 90.0, 90.0],
        "natoms": 2,
    },
    "fcc_ni": {
        "species": ["Ni"],
        "positions_frac": [[0.0, 0.0, 0.0]],
        "lattice_ang": [3.52, 3.52, 3.52, 90.0, 90.0, 90.0],
        "natoms": 1,
    },
}


class DFTInputGenerator:
    """DFT input file generator.

    Parameters
    ----------
    engine:
        Target solver engine.
    calc_type:
        Calculation type.
    """

    def __init__(
        self,
        engine: DFTEngine = DFTEngine.QE,
        calc_type: DFTCalcType = DFTCalcType.SCF,
    ) -> None:
        self.engine = engine
        self.calc_type = calc_type

    def generate(
        self,
        structure: str | dict[str, Any],
        params: dict[str, Any] | None = None,
        output_dir: Path | str = Path("."),
    ) -> dict[str, Path]:
        """Generate input files and return a file-path dictionary.

        Parameters
        ----------
        structure:
            Crystal structure dictionary or structure ID string (e.g. "bcc_fe").
            When a string is given, the built-in bcc Fe defaults are used.
            When a dictionary is given, the minimum required keys are:
            - ``"species"``: Element list (e.g. ["Fe"])
            - ``"positions_frac"``: Fractional coordinate list [[x, y, z], ...]
            - ``"lattice_ang"``: Lattice constant list [a, b, c, alpha, beta, gamma]
        params:
            Engine-specific additional parameter dictionary. None uses defaults.
        output_dir:
            Output directory for the input files.

        Returns
        -------
        dict[str, Path]
            File role → path dictionary.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        params = params or {}

        # Honour an explicit calc_type passed via params (overrides __init__).
        if "calc_type" in params:
            ct = params["calc_type"]
            self.calc_type = ct if isinstance(ct, DFTCalcType) else DFTCalcType(ct)

        # Structure ID string → built-in bcc Fe defaults
        if isinstance(structure, str):
            struct: dict[str, Any] = _BUILTIN_STRUCTURES.get(
                structure.lower(), _BUILTIN_STRUCTURES["bcc_fe"]
            )
        else:
            struct = structure

        if self.engine == DFTEngine.QE:
            return self._generate_qe(struct, params, output_dir)
        elif self.engine == DFTEngine.VASP:
            return self._generate_vasp(struct, params, output_dir)
        elif self.engine == DFTEngine.FLEUR:
            return self._generate_fleur(struct, params, output_dir)
        else:
            raise ValueError(f"Unsupported engine: {self.engine}")

    # ------------------------------------------------------------------
    # Quantum ESPRESSO (QE) input generation
    # ------------------------------------------------------------------

    def _generate_qe(
        self,
        structure: dict[str, Any],
        params: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Path]:
        """Generate QE pw.x input file.

        bcc Fe defaults:
        - ecutwfc = 60 Ry — Appendix D DFT cutoff requirement
        - k-mesh  = 8×8×8 Monkhorst-Pack — Appendix D k-mesh density
        - SOC enabled automatically based on calc_type
        """
        species = structure.get("species", ["Fe"])
        positions = structure.get("positions_frac", [[0.0, 0.0, 0.0]])
        lattice = structure.get("lattice_ang", [2.87, 2.87, 2.87, 90.0, 90.0, 90.0])

        ecutwfc = params.get("ecutwfc", 60)
        k_mesh = params.get("k_mesh", "8 8 8 0 0 0")
        pseudo_dir = params.get("pseudo_dir", "./pseudo")
        nspin = 2  # always spin-polarized
        lspinorb = self.calc_type in (DFTCalcType.MAE, DFTCalcType.DMI)

        # Pseudopotential settings (PBE family by default)
        pseudo_map: dict[str, str] = {
            "Fe": "Fe.pbesol-spn-kjpaw_psl.0.2.1.UPF",
            "Co": "Co.pbesol-spn-kjpaw_psl.0.2.1.UPF",
            "Ni": "Ni.pbesol-spn-kjpaw_psl.0.2.1.UPF",
        }
        unique_species = list(dict.fromkeys(species))
        nat = len(positions)
        ntyp = len(unique_species)

        content = textwrap.dedent(f"""\
            &CONTROL
              calculation = 'scf'
              restart_mode = 'from_scratch'
              pseudo_dir = '{pseudo_dir}'
              outdir = './out'
              prefix = 'pwscf'
              verbosity = 'high'
            /
            &SYSTEM
              ibrav = 3
              celldm(1) = {lattice[0] * 1.8897259886:.6f}
              nat = {nat}
              ntyp = {ntyp}
              ecutwfc = {ecutwfc}.0
              ecutrho = {ecutwfc * 8}.0
              nspin = {nspin}
              {"lspinorb = .true." if lspinorb else ""}
              {"noncolin = .true." if lspinorb else ""}
              occupations = 'smearing'
              smearing = 'mv'
              degauss = 0.02
              starting_magnetization(1) = 1.0
            /
            &ELECTRONS
              conv_thr = 1.0d-8
              mixing_beta = 0.3
            /
            ATOMIC_SPECIES
        """)

        for sp in unique_species:
            pseudo = pseudo_map.get(sp, f"{sp}.pbe-spn-kjpaw_psl.UPF")
            # Atomic mass (default values)
            mass_map = {"Fe": 55.845, "Co": 58.933, "Ni": 58.693}
            mass = mass_map.get(sp, 50.0)
            content += f"  {sp}  {mass:.3f}  {pseudo}\n"

        content += "\nATOMIC_POSITIONS (crystal)\n"
        for sp, pos in zip(
            species if len(species) == nat else species * nat, positions, strict=False
        ):
            content += f"  {sp}  {pos[0]:.6f}  {pos[1]:.6f}  {pos[2]:.6f}\n"

        content += f"\nK_POINTS (automatic)\n  {k_mesh}\n"

        pw_path = output_dir / "pw.in"
        pw_path.write_text(content, encoding="utf-8")

        # Also generate a Wannier90 projections file for J_ij calculations
        result: dict[str, Path] = {"pw_input": pw_path}

        if self.calc_type == DFTCalcType.JIJ:
            w90_path = output_dir / "wannier90.win"
            w90_content = textwrap.dedent(f"""\
                ! Wannier90 input file — for TB2J J_ij extraction
                num_wann = {ntyp * 5}
                num_iter = 200

                begin projections
                  Fe: d
                end projections

                begin unit_cell_cart
                  ang
                  {lattice[0]:.4f} 0.0 0.0
                  0.0 {lattice[1]:.4f} 0.0
                  0.0 0.0 {lattice[2]:.4f}
                end unit_cell_cart

                begin atoms_frac
            """)
            for sp, pos in zip(
                species if len(species) == nat else species * nat, positions, strict=False
            ):
                w90_content += f"  {sp}  {pos[0]:.6f}  {pos[1]:.6f}  {pos[2]:.6f}\n"
            w90_content += "end atoms_frac\n"
            w90_path.write_text(w90_content, encoding="utf-8")
            result["wannier90_input"] = w90_path

        return result

    # ------------------------------------------------------------------
    # VASP input generation
    # ------------------------------------------------------------------

    def _generate_vasp(
        self,
        structure: dict[str, Any],
        params: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Path]:
        """Generate VASP input files (INCAR·KPOINTS·POSCAR).

        VASP requires a commercial license — use the mock backend in CI.
        """
        species = structure.get("species", ["Fe"])
        positions = structure.get("positions_frac", [[0.0, 0.0, 0.0]])
        lattice = structure.get("lattice_ang", [2.87, 2.87, 2.87, 90.0, 90.0, 90.0])
        a = lattice[0]

        lsorbit = self.calc_type in (DFTCalcType.MAE, DFTCalcType.DMI)
        encut = params.get("encut", 500)
        k_div = params.get("k_div", 8)

        incar = textwrap.dedent(f"""\
            SYSTEM = bcc_Fe DFT calculation
            ISTART = 0
            ICHARG = 2
            ENCUT = {encut}
            PREC = Accurate
            EDIFF = 1E-8
            NSW = 0
            ISMEAR = 1
            SIGMA = 0.05
            ISPIN = 2
            MAGMOM = 3*2.2
            {"LSORBIT = .TRUE." if lsorbit else "! LSORBIT = .FALSE."}
            {"SAXIS = 0 0 1" if lsorbit else ""}
            LORBIT = 11
        """)

        kpoints = textwrap.dedent(f"""\
            Automatic Mesh
            0
            Monkhorst-Pack
              {k_div}  {k_div}  {k_div}
              0  0  0
        """)

        poscar = textwrap.dedent(f"""\
            bcc Fe
            1.0
              {a:.6f}  0.000000  0.000000
              0.000000  {a:.6f}  0.000000
              0.000000  0.000000  {a:.6f}
        """)
        unique_species = list(dict.fromkeys(species))
        poscar += " ".join(unique_species) + "\n"
        from collections import Counter

        counts = Counter(species)
        poscar += " ".join(str(counts[sp]) for sp in unique_species) + "\n"
        poscar += "Direct\n"
        for pos in positions:
            poscar += f"  {pos[0]:.6f}  {pos[1]:.6f}  {pos[2]:.6f}\n"

        incar_path = output_dir / "INCAR"
        kpoints_path = output_dir / "KPOINTS"
        poscar_path = output_dir / "POSCAR"

        incar_path.write_text(incar, encoding="utf-8")
        kpoints_path.write_text(kpoints, encoding="utf-8")
        poscar_path.write_text(poscar, encoding="utf-8")

        return {
            "INCAR": incar_path,
            "KPOINTS": kpoints_path,
            "POSCAR": poscar_path,
        }

    # ------------------------------------------------------------------
    # FLEUR input generation (basic stub)
    # ------------------------------------------------------------------

    def _generate_fleur(
        self,
        structure: dict[str, Any],
        params: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Path]:
        """Generate a basic FLEUR inp.xml stub."""
        species = structure.get("species", ["Fe"])
        lattice = structure.get("lattice_ang", [2.87, 2.87, 2.87, 90.0, 90.0, 90.0])
        a = lattice[0]

        # Bohr units
        a_bohr = a * 1.8897259886

        content = textwrap.dedent(f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <!-- FLEUR inp.xml — bcc Fe (stub) -->
            <fleurInput mode="band">
              <atomGroups>
                <atomGroup species="{species[0]}">
                  <filmPos label="{species[0]}_1">
                    <relative>.0000000000 .0000000000 .0000000000</relative>
                  </filmPos>
                </atomGroup>
              </atomGroups>
              <cell>
                <bulkLattice latnam="bcc" scale="{a_bohr:.6f}">
                  <a1>{a_bohr:.6f}</a1>
                </bulkLattice>
              </cell>
            </fleurInput>
        """)

        inp_path = output_dir / "inp.xml"
        inp_path.write_text(content, encoding="utf-8")
        return {"inp_xml": inp_path}
