# Literature Intelligence

[Manual index](index.md) · [한국어](../ko/literature.md)

Use this module when the research bottleneck is not "write me a paragraph" but
"find the right evidence, check it, and organize it before I decide what to do."

## What It Does

- Extracts weighted keywords from paper folders or free text.
- Searches literature sources through connector modules.
- Builds an evidence matrix with DOI, open-access, retraction, and tier fields.
- Finds authoritative authors for a topic.
- Queries open journal metrics.
- Traverses local citation and knowledge-graph records.

## Install

```sh
uv pip install -e ".[literature]"
```

## Core Commands

```sh
maglab lit search papers/spin_orbit_torque --top-n 40 --show 15
maglab lit search papers/spin_orbit_torque --matrix-out evidence_matrix.json
maglab lit keywords "spin Hall magnetoresistance in Pt/YIG bilayers"
maglab lit authors "orbital Hall effect ferromagnet"
maglab lit journal "Physical Review Letters"
maglab lit graph "spin Hall effect"
maglab lit graph "spin Hall effect" --cite-map "10.1103/PhysRevLett.xxx"
```

## Typical Workflow

1. Put downloaded papers or text files in a project folder.
2. Run `maglab lit search <folder>` to extract keywords and create an evidence matrix.
3. Use `maglab lit authors <topic>` to identify researchers whose work should be checked.
4. Use `maglab lit journal <journal>` when choosing where a result might fit.
5. Hand the evidence matrix to analysis, review, or authoring workflows.

## Output Files

`maglab lit search` writes an evidence matrix JSON when matrix generation is
enabled. Treat it as a working research artifact: inspect it, delete weak
records, add notes, then reuse it in review or authoring.

## Practical Notes

- The keyword stage can run locally on folders.
- Live search depends on API availability and optional connector packages.
- Retraction and verification fields are flags for researcher review, not a
substitute for reading the paper.

## Handoff

After literature triage:

```sh
maglab lab plan "SOT efficiency in Pt/CoFeB/MgO"
maglab review draft.md --journal prl
maglab write "Verified evidence matrix plus key measured results..." --journal prl
```
