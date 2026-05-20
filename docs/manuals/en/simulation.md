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

`maglab setup simulation` and `maglab install doctor` separate core Python
packages from optional remote-execution packages. Missing `paramiko` only blocks
Python-native SSH execution; it does not block mock mode, local CPU checks, or
local solver-spec generation.

## Commands

```sh
maglab sim doctor
maglab sim doctor --explain
maglab sim doctor --backend ssh-gpu --host gpu.cluster.edu --user alice
maglab sim doctor --backend ssh-hpc --host login.cluster.edu --user alice --probe-ssh

maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4
maglab sim validate spec.json
maglab sim plot data.csv --journal nature --format pdf --output figure.pdf
maglab sim job

maglab sim dft --structure bcc_fe --engine qe --calc-type jij --output-dir runs/dft_fe
maglab sim atomistic --engine vampire --j-ij-k 398 --t-max-k 1300
maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock
```

## Environment Doctor

Run `maglab sim doctor` before spending real solver, GPU, or cluster time. It
checks MagLab's Python simulation packages, local solver binaries, GPU
visibility, SSH/HPC utilities, and the currently recommended backend.

The doctor prints both a human-readable checklist and a JSON contract. The
JSON includes `backend_paths`, where each path has `status`, `next_command`,
`setup_commands`, and notes. This is designed for terminal setup flows: MagLab
can tell you what to run next without opening SSH sessions or guessing remote
module state.

Use `maglab sim doctor --explain` when you want the path-by-path decision table
in the terminal. It separates no-GPU mock mode, local CPU fallback, local GPU,
SSH GPU, and SSH HPC instead of collapsing them into one ambiguous status.

Use these paths depending on where the compute will run:

- No GPU or no solver installed: start with `maglab sim pipeline --backend mock`
  and use the generated artifacts to validate the workflow.
- CPU fallback: install `maglab[sim]`, keep meshes modest, and confirm the
  doctor reports a CPU engine such as `magnumnp`.
- Local GPU: install MuMax3 and NVIDIA drivers, then confirm both `mumax3` and
  `nvidia-smi` are reported ready.
- SSH GPU or HPC: confirm `paramiko` in the optional Python package row, pass
  `--host` and `--user`, and add `--probe-ssh` only after SSH keys work from
  the terminal. The default command does not open a remote connection.

### Setup flows

**No GPU / fresh laptop**

```sh
maglab sim doctor --backend auto
maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock --json
```

The mock pipeline writes `pipeline_result.json` in the work directory. Treat it
as a schema/provenance artifact, not as a physical solver result.

**Local CPU fallback**

```sh
pipx inject maglab "maglab[sim]"
maglab sim doctor --backend cpu
maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4
```

**Local NVIDIA GPU**

```sh
mumax3 -h
nvidia-smi
maglab sim doctor --backend local-gpu
```

**SSH GPU / HPC**

```sh
pipx inject maglab "maglab[sim]"   # includes paramiko for Python-native SSH
maglab sim doctor --backend ssh-gpu --host gpu.cluster.edu --user alice
ssh alice@gpu.cluster.edu
maglab sim doctor --backend ssh-gpu --host gpu.cluster.edu --user alice --probe-ssh
```

For HPC login nodes, use `--backend ssh-hpc`. MagLab only probes SSH when
`--probe-ssh` is present, and it does not infer remote CUDA, MuMax3, or Slurm
module availability from your local machine.

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
