# Repository Metadata

This page keeps the public-facing repository metadata in version control so the
GitHub About panel, topics, and social-preview copy stay aligned with the
README.

## Short Description

Use this as the GitHub repository description:

```text
AI for Science harness for magnetism and spintronics research: literature, physics, simulation, fitting, figures, instruments, authoring, and provenance in one CLI.
```

## Topics

Use these GitHub topics:

```text
ai-for-science
magnetism
spintronics
micromagnetics
materials-science
scientific-computing
research-automation
llm-agents
cli
provenance
simulation
data-analysis
scientific-figures
instruments
open-science
```

## Thumbnail and Social Preview Copy

Short thumbnail line:

```text
MagLab: AI for Science harness for magnetism and spintronics.
```

Long thumbnail/social preview description:

```text
MagLab turns the magnetism and spintronics research lifecycle into a verifiable CLI workflow: LLM orchestration wrapped around deterministic tools, provenance, simulation, fitting, figures, instruments, and scientific writing.
```

Suggested alt text for a social preview image:

```text
Black terminal-style MagLab banner showing the magnetism and spintronics research lifecycle, deterministic tools, verification layer, and W3C provenance ledger.
```

## Visual Direction

Use `image1.png` for the lifecycle thumbnail when the platform requires a
single image. It communicates that MagLab is not only an LLM wrapper: it covers
literature, materials, physics, simulation, fitting, analysis, instruments,
figures, authoring, communications, open science, and provenance.

Use `image2.png` when the goal is to explain the agent architecture. It focuses
on the LLM layer, deterministic tools, verification layer, and W3C PROV ledger.

## GitHub CLI Command

The description and topics can be updated with:

```sh
gh repo edit TaewoooPark/MagLab \
  --description "AI for Science harness for magnetism and spintronics research: literature, physics, simulation, fitting, figures, instruments, authoring, and provenance in one CLI." \
  --add-topic ai-for-science \
  --add-topic magnetism \
  --add-topic spintronics \
  --add-topic micromagnetics \
  --add-topic materials-science \
  --add-topic scientific-computing \
  --add-topic research-automation \
  --add-topic llm-agents \
  --add-topic cli \
  --add-topic provenance \
  --add-topic simulation \
  --add-topic data-analysis \
  --add-topic scientific-figures \
  --add-topic instruments \
  --add-topic open-science
```

GitHub social preview image upload is managed in the repository web UI. This
file stores the copy and image direction so the setup remains reproducible.
