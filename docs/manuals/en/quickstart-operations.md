# Quickstart and Operating Manual

[Manual index](index.md) · [한국어](../ko/quickstart-operations.md)

Use this guide when you want MagLab to behave like a global research CLI:
install once, open any project folder, connect the model provider you prefer,
and run deterministic scientific tools from the same terminal session.

## Mental Model

MagLab has three layers:

1. The global program: `maglab` is installed into your shell path.
2. The current research folder: MagLab reads and writes project artifacts
   relative to the directory where you launch it.
3. The user app directories: credentials, config, cache, and provider settings
   live outside the cloned repository.

This lets you clone MagLab for development, install it as a tool, then open a
separate experiment folder exactly as you would with Codex, Claude Code, or a
normal terminal editor.

## Recommended Install

For normal research use, install the research bundle. It includes the MagLab
features that scientists usually expect to be present together: physics,
materials, fitting, figures, literature, instruments, authoring, simulation
helpers, MCP, and gateway support.

```sh
git clone https://github.com/TaewoooPark/MagLab.git
cd MagLab
pipx install --python python3.12 --editable ".[research]"
maglab install doctor
maglab doctor
maglab setup all
```

If `pipx` is missing:

```sh
uv tool install pipx --python python3.12
pipx ensurepath
pipx install --python python3.12 --editable ".[research]"
```

For MagLab development instead of end-user installation:

```sh
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev,research]"
maglab doctor
```

## Open a Research Folder

Run MagLab from the folder that contains your papers, data, scripts, figures,
or notes.

```sh
cd ~/research/pt-cofeb-mgo-sot
maglab workspace init
maglab workspace brief
maglab workspace tree --summary --type docs --max-depth 2
maglab workspace tree --changed
maglab
```

`workspace init` creates a local `MAGLAB.md` context file. Keep durable project
facts there: sample naming conventions, device stack, geometry, measurement
sign conventions, file locations, and claims that must not be forgotten.

## Connect a Model Provider

MagLab can run deterministic commands without a model. Connect an LLM only when
you want natural-language orchestration, code/file assistance, review, or
drafting.

Codex delegates to the official authenticated Codex CLI. MagLab does not store
Codex OAuth tokens.

```sh
codex login
maglab auth codex
maglab auth status
maglab auth test codex
maglab doctor --smoke
```

Direct API-key providers use hidden terminal input:

```sh
maglab auth anthropic
maglab auth grok
maglab auth deepseek
maglab auth qwen
maglab auth kimi
maglab auth gemini
maglab auth openai
maglab auth status
maglab auth test
```

Local Ollama:

```sh
ollama serve
ollama pull qwen2.5-coder:7b
maglab auth ollama
maglab auth test ollama
```

Inside the REPL, use the slash-command versions:

```text
/connect codex
/connect anthropic
/connect qwen
/connect ollama
/connect status
```

## First Hour Checklist

Run this sequence before trusting a new setup.

```sh
maglab install doctor
maglab doctor
maglab setup all
maglab manual --lang en
maglab workspace init
maglab workspace brief
maglab physics units 1000 Oe T
maglab physics compute exchange_length A=13e-12 Ms=860e3
maglab analyze model stfmr
maglab figure primitives list
```

If a backend is connected, add:

```sh
maglab auth status
maglab auth test
maglab doctor --smoke
maglab -p "Summarize this workspace and propose the first safe MagLab command to run."
```

## REPL Basics

Start the interactive agent:

```sh
maglab
```

Useful first commands:

```text
/help quick
/help all
/workspace brief
/workspace tree --summary --type data
/doctor
/setup all
/manual en simulation
/theme list
/theme set mono
/reset config
```

Prompt naturally after the workspace is clear:

```text
Read the README, inspect the data folder, and propose a reproducible ST-FMR
analysis workflow. Do not fit anything yet.
```

MagLab prints a loop separator between user/assistant turns and shows compact
activity while the LLM is running. The trace may include elapsed time, stop
instruction, tool names, Python file references, and workspace files when they
are visible to the harness. Hidden model reasoning is not displayed.

## Practical Workflows

### Literature to Experiment Plan

```sh
maglab lit search papers/pt_cofeb_mgo --top-n 40
maglab lit keywords papers/pt_cofeb_mgo --top-n 30
maglab lit authors "spin orbit torque CoFeB MgO"
maglab lab plan "SOT efficiency in Pt/CoFeB/MgO" --n-doe 16 --output plans/sot_plan.yaml
```

Check that the evidence matrix contains the exact papers you intend to cite.
Never let a generated summary become the only source for a claim.

### Measurement CSV to Fitted Result

```sh
maglab analyze load data/stfmr.csv --columns frequency,field,voltage
maglab analyze model stfmr
maglab fit --effect stfmr data/stfmr.csv --method least_squares --json
maglab analyze consistency data/stfmr.csv --effect stfmr
```

Before reporting the fit, inspect parameter bounds, residuals, sign
conventions, device geometry, and whether the extracted quantity is really
identified by the measurement.

### Result to Journal Figure

```sh
maglab figure spec --journal aps --kind xy --output figures/stfmr_spec.json
maglab figure render figures/stfmr_spec.json --format pdf --output figures/stfmr.pdf
maglab figure export figures/stfmr_spec.json --format svg --output figures/stfmr.svg
```

Bind figures to DataPoint/provenance records when numbers come from fitted
results or processed data. Prefer vector output for manuscript figures.

### Simulation Preparation

```sh
maglab sim doctor --explain
maglab physics compute exchange_length A=13e-12 Ms=860e3
maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4 --output spec.json
maglab sim validate spec.json
```

Use mock or validation mode to debug the workflow before spending GPU or
cluster time. For remote clusters, run `sim doctor` without `--probe-ssh` first;
add `--probe-ssh` only after normal shell SSH works.

### Instrument Script Draft

```sh
maglab instr ingest "Keithley 2400" --manufacturer Keithley --manual-path manuals/keithley_2400.pdf
maglab instr script "Keithley 2400" --description "field sweep Hall voltage measurement" --output scripts/hall_sweep.py
maglab instr check scripts/hall_sweep.py
```

Generated scripts are starting points. Check current limits, compliance,
interlocks, sweep ranges, delays, and device safety before hardware execution.

### Authoring After Verification

```sh
maglab write "ST-FMR fit gives xi_DL=0.12 with provenance IDs ..." --journal prl --dry-run
maglab comms cover-letter --journal "Physical Review Letters" --title "Spin-orbit torque ..."
maglab present slides "Key results and figures from the SOT study" --template aps-12min --format beamer --n-slides 10
maglab present poster "Key results and figures from the SOT study" --template aps-march-poster --format svg
```

Authoring commands deliberately keep human review visible. Fill missing claims,
citations, and figure references yourself.

## Trust Checklist

Before a MagLab output goes into a paper, talk, poster, or lab decision, check:

- Did every reported number come from data, a deterministic formula, a fitter,
  a simulation record, a literature record, or explicit user input?
- Are units and sign conventions written down?
- Is the provenance path preserved?
- Does the cited paper actually support the sentence?
- Did a mock simulation path accidentally get treated as a real solver result?
- Are instrument limits and hardware safety constraints checked by a human?
- Are generated manuscripts, emails, rebuttals, slides, and posters marked for
  human review?

## Recovery and Reset

```sh
maglab config path
maglab config show
maglab config restore
maglab config reset
```

Inside the REPL:

```text
/reset config
/reset defaults
```

Use `restore` when a previous backup is available and `reset` only when you want
to return to a clean default configuration.

## Troubleshooting

| Symptom | First check |
|---|---|
| `maglab` not found | Run `pipx ensurepath`, restart the shell, then `maglab install doctor`. |
| Provider says no credentials | Run `maglab auth status`, then reconnect with `maglab auth <provider>`. |
| Codex works in shell but not MagLab | Run `codex exec "Reply exactly: OK"` and `maglab auth test codex`. |
| LLM output ignores MagLab identity | Re-run `maglab auth <provider>` so provider-specific runtime guidance is selected. |
| Simulation doctor is partial | Read `maglab sim doctor --explain`; missing external solvers are expected on laptops. |
| Manual command cannot find docs | Reinstall from the repo or wheel with `docs/manuals` package data included. |

## Daily Operating Pattern

1. Open the project folder.
2. Run `maglab workspace brief`.
3. Run the deterministic command closest to your task.
4. Ask the REPL to coordinate only after the deterministic path is clear.
5. Save generated specs, figures, logs, and notes in the workspace.
6. Run `maglab doctor` or feature-specific doctor commands when the environment
   changes.
7. Treat final scientific judgment as the researcher's responsibility.
