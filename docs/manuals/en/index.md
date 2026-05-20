# MagLab Manuals

[Back to README](../../../README.md) · [한국어](../ko/index.md)

These manuals are written for researchers who want to use MagLab as a practical
AI for Science harness. Each page starts from a real research bottleneck and
ends with commands you can run.

## Feature Guides

| Area | Use it when you need to... |
|---|---|
| [Quickstart and operating manual](quickstart-operations.md) | Install MagLab globally, open a research folder, connect an LLM backend, and run the first reproducible workflow. |
| [Literature intelligence](literature.md) | Search papers, extract keywords, build an evidence matrix, inspect authors, journal metrics, and citation graphs. |
| [Materials and physics](materials-physics.md) | Query magnetic materials, build stacks, compute physics formulae, convert units, and run plausibility checks. |
| [Simulation](simulation.md) | Prepare micromagnetic, DFT, atomistic, and multiscale simulation workflows. |
| [Analysis and fitting](analysis-fitting.md) | Load data, inspect models, fit spintronic effects, check consistency, and compute device figures of merit. |
| [Figures](figures.md) | Build `FigureSpec` files, render journal-aware figures, compose panels, export vector files, and inspect primitives. |
| [Instruments](instruments.md) | Scaffold PyVISA drivers, validate SCPI, ingest manuals, generate measurement scripts, and check safety. |
| [Lab notebook and planning](lab-planning.md) | Record ELN entries, list notes, generate measurement plans, DOE designs, and active-learning suggestions. |
| [Review and anomaly explanation](review-explain.md) | Run manuscript review panels and generate mechanism candidates for anomalous results. |
| [Authoring and communications](authoring-comms.md) | Draft papers, revision letters, cover letters, emails, abstracts, grant text, slides, and posters. |
| [Orchestration, agents, MCP, gateway](orchestration.md) | Use the REPL, one-shot prompts, Ralph loops, subagents, skills, MCP, gateway bots, and cost/config tooling. |

## Recommended Reading Order

1. Start with [Quickstart and operating manual](quickstart-operations.md) to install the global CLI and understand the folder model.
2. Read [Materials and physics](materials-physics.md) to understand the deterministic core.
3. Read the guide closest to your current research task.
4. Use [Orchestration](orchestration.md) once you want MagLab to coordinate multiple tools.
5. Use [Authoring and communications](authoring-comms.md) only after you have verified results.

## Installation Reminder

```sh
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uv pip install -e ".[research]"
maglab doctor
maglab setup all
maglab manual --lang en
```

For a working research machine, the recommended path is the all-in-one
`.[research]` extra. `maglab doctor` gives the first-run readiness report for
the active folder, backend, extras, external tools, and simulation stack.
`maglab setup all` shows what is already ready, what still needs terminal setup,
and the matching REPL slash commands. Use `maglab setup <feature>` or
`/setup-<feature>` for targeted setup checks.

The same manuals are bundled into the installed CLI. Use `maglab manual --lang
en` to list them, or `maglab manual figures --lang ko` to jump directly to a
Korean topic.

Simulation backends such as OOMMF, MuMax3, magnum.np, VAMPIRE, VASP, and
Quantum ESPRESSO may require separate installation outside MagLab.
