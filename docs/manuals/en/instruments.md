# Instruments

[Manual index](index.md) · [한국어](../ko/instruments.md)

Use this module when the bottleneck is turning an experiment idea into a safe,
reviewable instrument workflow. MagLab generates and checks scripts, but real
hardware execution remains a human-controlled Tier 3 action.

## Install

```sh
uv pip install -e ".[instr]"
```

## Commands

```sh
maglab instr scaffold "Keithley 2400" --iface GPIB --gpib-addr 24
maglab instr scpi "*IDN?" "SOUR:VOLT 0.1" "READ?"
maglab instr script "Keithley 2400" --description "field sweep Hall voltage measurement" --output hall_sweep.py
maglab instr check hall_sweep.py

maglab instr ingest "Keithley 2400" --manufacturer Keithley --manual-path manuals/keithley_2400.pdf
maglab instr skillgen "Keithley 2400" --manufacturer Keithley --safety-model keithley-2400
maglab instr implement "Measure Hall voltage while sweeping field" --instruments "Keithley 2400,Lakeshore 335"
```

## Safety Model

Instrument commands are intentionally conservative:

- The instrument model name must be confirmed by the user.
- Generated scripts are not executed automatically.
- `maglab instr check` should pass before any script touches hardware.
- SCPI sequences are statically inspected.
- Generated outputs include review warnings.

## Typical Workflow

1. Collect the instrument manual with `instr ingest`.
2. Generate a workspace-local instrument skill with `instr skillgen`.
3. Scaffold a driver or generate a measurement script.
4. Run `instr check` against the generated script.
5. Review addresses, current/voltage/temperature limits, timing, and shutdown.
6. Only then adapt the script for the real lab environment.

## Manual RAG

Manual ingest builds a local index from a PDF. Use this when the instrument has
non-obvious command names or safety constraints.

```sh
maglab instr ingest "SR830" --manufacturer Stanford --manual-path manuals/sr830.pdf
maglab instr skillgen "SR830" --manufacturer Stanford
```

Generated skills are written to `.maglab/skills` by default, so they travel
with the current research workspace instead of modifying the installed MagLab
package.

## Handoff

```sh
maglab lab note "Generated first Hall sweep script" --instrument "Keithley 2400"
maglab lab plan "Hall measurement for anomalous Hall effect"
maglab analyze load measured_hall.csv
```
