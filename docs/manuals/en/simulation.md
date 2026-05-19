# Simulation

[Manual index](index.md) · [한국어](../ko/simulation.md)

Use this module when you need to move from material parameters to simulation
inputs and outputs across micromagnetic, DFT, atomistic, and device scales.

## Install

```sh
uv pip install -e ".[sim]"
```

External solvers may still need separate installation: OOMMF, MuMax3, magnum.np,
VAMPIRE, VASP, Quantum ESPRESSO, or HPC/GPU execution tools.

## Commands

```sh
maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4
maglab sim validate spec.json
maglab sim plot data.csv --journal nature --format pdf --output figure.pdf
maglab sim job

maglab sim dft --structure bcc_fe --engine qe --calc-type jij --output-dir runs/dft_fe
maglab sim atomistic --engine vampire --j-ij-k 398 --t-max-k 1300
maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock
```

## Workflow Patterns

**Micromagnetic preparation**

1. Query materials with `mat show` or `mat build`.
2. Estimate mesh size using `physics compute exchange_length`.
3. Create and validate a micromagnetic spec.
4. Run the chosen backend or use the generated spec as a handoff artifact.

**Multiscale handoff**

1. Generate DFT inputs for exchange, MAE, or DMI extraction.
2. Convert DFT-derived parameters into atomistic input.
3. Extract temperature-dependent parameters from atomistic runs.
4. Hand off to micromagnetic or device-level analysis.

## Mock Mode

Several commands support mock paths so you can test file generation, schema
validation, and provenance flow without a live solver. Use mock mode to debug
the research workflow before spending GPU or cluster time.

## Outputs

Simulation commands can produce:

- Input directories for external solvers.
- Parsed parameter records.
- Warnings and validation errors.
- Provenance chains for generated or parsed values.
- Quick-look plots and FigureSpec-compatible artifacts.

## Handoff

```sh
maglab analyze load simulation_output.csv
maglab figure spec --journal aps --kind xy
maglab device fom racetrack --j-drive 1e11 --alpha 0.01
```
