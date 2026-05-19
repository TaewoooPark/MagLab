# MagLab Manuals

[Back to README](../../../README.md) · [한국어](../ko/index.md)

These manuals are written for researchers who want to use MagLab as a practical
AI for Science harness. Each page starts from a real research bottleneck and
ends with commands you can run.

## Feature Guides

| Area | Use it when you need to... |
|---|---|
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

1. Start with [Materials and physics](materials-physics.md) to understand the deterministic core.
2. Read the guide closest to your current research task.
3. Use [Orchestration](orchestration.md) once you want MagLab to coordinate multiple tools.
4. Use [Authoring and communications](authoring-comms.md) only after you have verified results.

## Installation Reminder

```sh
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uv pip install -e ".[llm,literature,sim,figure,instr,authoring,gateway,mcp]"
```

Install only the extras you need on a real machine. Simulation backends such as
OOMMF, MuMax3, magnum.np, VAMPIRE, VASP, and Quantum ESPRESSO may require
separate installation outside MagLab.
