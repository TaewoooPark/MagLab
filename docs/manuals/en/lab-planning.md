# Lab Notebook and Planning

[Manual index](index.md) · [한국어](../ko/lab-planning.md)

Use this module when you need MagLab to remember what happened and translate a
research goal into a measurement plan.

## Commands

```sh
maglab lab note "Measured Pt/CoFeB/MgO Hall bar after anneal" --sample SOT-042 --instrument "PPMS" --type magnetotransport --tag anneal --tag hall
maglab lab note-list --sample SOT-042
maglab lab note-list --date-from 2026-05-01 --tag hall
maglab lab plan "SOT efficiency in Pt/CoFeB/MgO" --doe latin_hypercube --n-doe 16 --output sot_plan.yaml
```

## ELN Entries

`maglab lab note` writes structured Markdown entries with metadata such as:

- Entry ID.
- Date.
- Sample.
- Instrument.
- Measurement type.
- Tags.
- Draft status.

Use `--draft` for notes generated from rough observations that still need human
confirmation.

## Measurement Planning

`maglab lab plan` maps a research goal to measurement steps, geometry hints,
instrument hints, estimated hours, and optional DOE points.

Examples:

```sh
maglab lab plan "FMR damping in Py/Pt" --n-doe 12
maglab lab plan "temperature dependence of anomalous Hall in CoFeB" --doe full_factorial
```

## Practical Workflow

1. Record the experiment immediately after it happens.
2. Use consistent sample IDs and tags.
3. Generate a plan before instrument scripting.
4. Attach output files and provenance IDs in the note body.
5. Use note filters during paper writing and revision.

## Handoff

```sh
maglab instr script "Keithley 2400" --description "measurement step from sot_plan.yaml"
maglab analyze load data/sot_042.csv
maglab write "Use ELN entries for sample SOT-042 and verified fit outputs..."
```
