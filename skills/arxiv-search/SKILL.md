---
name: arxiv-search
description: >
  arXiv preprint search for magnetism & spintronics — category-scoped queries,
  version and DOI resolution, and the preprint caveats that must survive into the
  evidence matrix (§14.3·§14.7). Used by the search-scout agent alongside
  literature-search, which covers the published record.
license: MIT
compatibility:
  claude-code: ">=1.0"
  maglab: ">=0.1"
user-invocable: true
allowed-tools:
  - mcp__arxiv-mcp-server__search_papers
  - mcp__arxiv-mcp-server__get_abstract
  - mcp__arxiv-mcp-server__read_paper
  - read_file
---

# arxiv-search — preprint discovery for magnetism & spintronics

## Overview

`literature-search` covers the peer-reviewed record through OpenAlex. This skill
covers what is not there yet: preprints, and the several-month gap between
posting and publication that matters in a fast-moving field.

Preprints are evidence, but weaker evidence. Everything below exists to keep
that distinction visible downstream rather than letting an unrefereed number
enter a synthesis as though it were established.

## Category scoping

Scope queries to the categories where this field posts, or the result set fills
with unrelated matches for the same acronyms (`SOT`, `DMI`, `AHE`):

| Category | Covers |
|---|---|
| `cond-mat.mtrl-sci` | thin films, interfaces, growth, characterisation |
| `cond-mat.mes-hall` | mesoscopic transport, Hall effects, spin transport |
| `cond-mat.str-el` | correlated magnetism, exchange, ordering |
| `physics.app-ph` | device demonstrations, MRAM, integration |

Query form: `cat:cond-mat.mtrl-sci AND (abs:"spin-orbit torque" OR abs:"SOT")`.

## Query families (3–6 per topic)

Generate the same query families as `literature-search`, then add the two that
only make sense for preprints:

1. Canonical term — `"spin-orbit torque"`
2. Acronym plus disambiguator — `"SOT" AND "magnetization switching"`
3. Material-specific — `"Ta/CoFeB/MgO"`
4. Measurement-specific — `"harmonic Hall"`, `"ST-FMR"`
5. **Recency window** — the last 12 months, to catch what OpenAlex has not indexed
6. **Author follow-up** — authors already in the evidence matrix, for newer work

## Version and DOI resolution

An arXiv entry is not one document. Before recording anything:

- Record the **specific version** used (`arXiv:2401.01234v3`), never the bare id.
  Conclusions change between versions, and `v1` is frequently not what was
  published.
- Check for a resolved DOI. When present, the published record supersedes the
  preprint — record the DOI, keep the arXiv id as a secondary reference, and
  extract from the published version.
- When a paper is found both here and via `literature-search`, they are one
  entry, deduplicated on DOI. Do not let it count twice as corroboration.

## Tier classification

Preprints never enter as T1:

| Tier | Condition |
|---|---|
| T2 | Published DOI resolved; extraction came from the published version |
| T3 | Preprint only, no DOI yet |
| flag | Withdrawn, or replaced by a version with materially different conclusions |

Set `retraction_status` to `withdrawn` when arXiv reports a withdrawal — a
withdrawn preprint is not simply an older version.

## Output contract

Return the same record shape `literature-search` produces, plus:

```json
{
  "arxiv_id": "2401.01234v3",
  "doi": "10.1103/PhysRevB.109.000000",
  "published": true,
  "preprint_only": false,
  "posted": "2024-01-02",
  "tier": "T2",
  "retraction_status": "none | withdrawn"
}
```

## Task boundaries

- Do not present a preprint value as an established result; downstream synthesis
  reads `preprint_only` to decide how to phrase it
- Do not extract numbers from an abstract when the full text is available — the
  abstract rounds and omits uncertainties
- Do not treat a high citation count on a preprint as peer review
- If a topic returns only preprints, say so in `warnings`: it is a real finding
  about the field's maturity, not a search failure
