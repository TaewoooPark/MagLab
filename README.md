# MagLab

Magnetism/spintronics research lifecycle copilot — standalone CLI agent.

Discovery → design → execution → analysis → review → authoring. **Verifiable orchestrator**:
the LLM handles reasoning and planning only; numbers, citations, and figures come from
deterministic tools; all outputs carry provenance.

## Installation

Requirements: Python 3.11+ (3.12 recommended).

```sh
uv venv --python 3.12
uv pip install -e .          # core (no GPU or LLM required)
uv pip install -e ".[all]"   # full feature set
```

## Quick start

```sh
maglab --help     # subcommands
maglab version
```

## Documentation

- [`PLAN.md`](PLAN.md) · [`plan/`](plan/) — design specification
- [`impl/`](impl/) — implementation execution plan (Phase P0–P6)
- [`MAGLAB.md`](MAGLAB.md) — persistent project context

## License

MIT. See [`LICENSE`](LICENSE).
