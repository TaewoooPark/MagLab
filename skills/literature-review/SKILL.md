---
name: literature-review
description: >
  Systematic literature review workflow — search → screening → quality assessment → topic-centred synthesis.
  Includes local-gap analysis. A DOI citation is required for every factual claim (§14.7).
  Activated by the maglab lit search command and the synthesis-editor agent.
license: MIT
compatibility:
  claude-code: ">=1.0"
  maglab: ">=0.1"
user-invocable: true
allowed-tools:
  - mcp__arxiv-mcp-server__search_papers
  - mcp__arxiv-mcp-server__read_paper
  - read_file
---

# literature-review — Systematic literature review workflow skill

## Overview

This skill implements a PRISMA (Preferred Reporting Items for Systematic Reviews)-based
systematic review workflow aligned with MagLab research integrity principles (§3.3).

**Core principles**:
- Every factual claim → DOI citation required
- The LLM does not generate numerical values or material properties — citations from the paper text only
- Consensus and controversy are stated transparently

## Four-stage workflow

### Stage 1: Search

- Use the `literature-search` skill to generate a query family and collect candidates
- Multiple sources: OpenAlex · arXiv · Semantic Scholar
- Record search queries, dates, and filters (reproducibility)

### Stage 2: Screening

**Inclusion criteria**:
- Directly relevant to magnetism or spintronics
- Contains experimental, theoretical, or simulation results
- Available in English or with an English abstract

**Exclusion criteria**:
- Retracted or corrected papers (`retraction_status: "retracted"`)
- Off-topic (may also be excluded at T3)
- Failed DOI/metadata validation (`verification_status: "failed"`)

### Stage 3: Quality assessment

For each paper:
- Methodological validity (measurement geometry · control group · statistics)
- Reproducibility (parameters · data access)
- Bias risk (sample selection · measurement uncertainty)

Record assessment results in the `notes` field.

### Stage 4: Synthesis

**Format**: Paper-by-paper summary listing is prohibited — **topic-centred** synthesis is required.

Synthesis structure:
```
## [Topic/perspective]
[Evidence sentence (DOI citation format: [AuthorYear, DOI:xxx])]

### Consensus
[Common findings · methodology]

### Controversy
[Conflicting reports · method differences · interpretation differences]

### Gaps
[Open questions · unexplored areas]
```

## Local-gap analysis

Compare local corpus with new search results to identify gaps:

1. List of locally held papers (local-context-librarian results)
2. Identify papers in new search results not in local corpus
3. Generate coverage map by topic and method
4. Report 3–5 priority gaps

## DOI citation format

In-text citation: `[Smith2022, DOI:10.1103/PhysRevLett.106.036601]`
References: APA format + DOI URL

Claims without a DOI must not be written — use `[could not be confirmed]` instead.

## Quality gate

Check before outputting synthesis:
- [ ] Every factual claim has at least one DOI
- [ ] No retracted papers included
- [ ] DOI coverage ≥ 80%
- [ ] Synthesis is topic-centred, not a paper-by-paper list
- [ ] Consensus and controversy stated

DOI coverage < 80% → return `status: "partial"`.
