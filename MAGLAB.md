# MAGLAB.md — persistent project context

> The **immortal context** file always loaded by the MagLab orchestrator at session start
> (§5.5). Survives compaction. Contains *principles*, not code.

## Identity

MagLab — magnetism/spintronics research lifecycle copilot. Standalone CLI agent.
Integrates the full lifecycle — discovery → design → execution → analysis → review → authoring —
in a single tool.

## Invariant principles — verifiable orchestrator (§3)

The three layers are separated from the start and must never blur:

1. **LLM** — reasoning, planning, tool selection, narrative drafting, figure code authoring. Nothing beyond this.
2. **Deterministic tools** — simulation, fitting, theoretical formulae, units, materials, literature, citation verification, figure rendering.
   All numbers, citations, and figure data originate exclusively here.
3. **Provenance** — source and lineage of every DataPoint, citation, and decision (W3C PROV).

**Core prohibition**: the LLM does not compute numbers, does not fabricate citations, and does not generate figure data. Humans are the authors and bear responsibility.

## Directory map

- `maglab/` — package. `physics/` (deterministic physics) · `sim/` (multiscale simulation) ·
  `analysis/` (effect fitting) · `figure/` (figure engine) · `instrument/` (instrumentation) ·
  `literature/` · `reviewer/` · `authoring/` · `provenance/` · `core/` (harness) ·
  `llm/` · `ui/` · `gateway/` · `report/` · `lab/`.
- `PLAN.md` + `plan/` — design specification. `impl/` — implementation execution plan (Phase P0–P6).
- `agents/` sub-agents · `skills/` SKILL.md skills · `themes/` themes ·
  `tests/` tests · `configs/` configuration.

## Build and test

- Install: `uv pip install -e ".[dev]"` (core installs without GPU or LLM)
- Lint/type: `ruff check .` · `mypy maglab`
- Test: `pytest` — **LLM-as-judge is prohibited for quantitative, citation, and fitting validation** (§20)

## Roadmap

Implementation follows Phase P0–P6 (see `impl/`). P0–P3 = verifiable orchestrator core,
P4–P6 = lifecycle layers. Progress is tracked in `impl/README.md` §7.
