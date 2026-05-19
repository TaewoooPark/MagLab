---
name: literature-search
description: >
  Broad literature search for magnetism & spintronics — OpenAlex REST query strategy,
  query family generation, tier classification, and evidence_matrix construction (§14.3·§14.7).
  Activated by the maglab lit search command and the research orchestration search-scout agent.
license: MIT
compatibility:
  claude-code: ">=1.0"
  maglab: ">=0.1"
user-invocable: true
allowed-tools:
  - mcp__arxiv-mcp-server__search_papers
  - mcp__arxiv-mcp-server__get_abstract
  - read_file
---

# literature-search — Magnetism & spintronics broad literature search skill

## Overview

This skill encodes the OpenAlex REST API query strategy and research orchestration workflow.
MCP connectors (paperplain·openalex-mcp·cite-mcp) are preferred; falls back to
`maglab/literature/connectors.py` direct API when unavailable.

## OpenAlex query strategy

### Query family generation (3–6 queries)

Generate a query family from the topic keywords using the following combinations:

1. **Core terms**: `"spin Hall effect"`, `"SOT switching"`
2. **Material + effect**: `"Ta CoFeB spin Hall"`, `"Pt Py SOT"`
3. **Methodology**: `"harmonic Hall measurement"`, `"ST-FMR"`
4. **Broader concept**: `"spin-orbit torque"`, `"spintronics"`
5. **Synonym variants**: `"spin-transfer torque"`, `"spin Hall magnetoresistance"`
6. **Recent keywords**: arXiv `cond-mat.mes-hall` category, last 1 year

### Tier classification criteria

| tier | criteria |
|---|---|
| T1 | Core papers directly addressing the topic (most-cited · methodology-founding · reviews) |
| T2 | Related papers supporting or applying the topic |
| T3 | Background, comparison, or general review papers |

Citation count > 100: T1 candidate; 10–100: T2; < 10: T3 default.
May be upgraded based on topic relevance.

### Search filters

- `filter=topics.id:<OpenAlex_topic_id>` — magnetism · spintronics topics
- `sort=cited_by_count:desc` — sort by citation count
- `filter=is_retracted:false` — exclude retractions
- `filter=publication_year:>2010` — prioritise recent literature (adjust per topic)

## evidence_matrix accumulation

Record the following fields for each candidate paper (§14.7):

```
ref_key | tier | title | authors | year | venue | doi | url |
openalex_id | s2_id | oa_status | retraction_status |
verification_status | notes
```

- Papers without `doi`: `verification_status: "pending"` (not blocked)
- Do not guess DOIs

## MCP connector priority

1. `openalex-mcp-server` — metadata quality · filters
2. `paperplain` — initial search (PubMed · arXiv · S2 aggregator)
3. `cite-mcp` — DOI detail · BibTeX

Falls back to `maglab.literature.connectors` direct API when unavailable.

## Execution procedure

1. Generate 3–6 query families from the input topic
2. Parallel search of OpenAlex + arXiv per query (up to 30 candidates)
3. Deduplicate by DOI
4. Tier classification (citation count + topic relevance)
5. Accumulate results into evidence_matrix
6. Delegate validation to citation-auditor agent
