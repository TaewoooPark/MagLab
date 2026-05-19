---
name: cover-letter
description: >
  Journal submission cover letter workflow (≤250 words). Invokes CoverLetterAgent
  to draft a concise novelty-focused cover letter from the author's key results.
  Output carries HUMAN REVIEW REQUIRED; no auto-send. All personal/institutional fields
  are marked [FILL] for the author to complete (§16.3).
license: MIT
compatibility:
  claude-code: ">=1.0"
  maglab: ">=0.1"
user-invocable: true
allowed-tools:
  - read_file
  - write_file
---

# cover-letter — Journal submission cover letter skill

## Overview

This skill drafts a ≤250 word cover letter for journal manuscript submission, aligned with
MagLab research integrity principles (§3.3) and the Appendix C bundle comms workflow.

**Core principles**:
- Body must be ≤250 words (excluding salutation and sign-off).
- The AI constructs novelty statements only from the author-provided `key_results` input.
- The AI never invents results, citations, or claims beyond the provided inputs.
- All personalisation fields (editor name, affiliation, email) are marked `[FILL]`.
- Output always begins with `HUMAN REVIEW REQUIRED`.
- The letter is never auto-sent — it is written to a file for human review.

**Agent**: `maglab.authoring.comms.cover_letter.CoverLetterAgent`
**CLI command**: `maglab comms cover-letter`

## Inputs

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `journal` | str | Yes | Target journal name (e.g. `"Physical Review Letters"`) |
| `title` | str | Yes | Manuscript title |
| `key_results` | list[str] or str | Yes | 1–3 key results to highlight in the novelty statement |
| `related_pubs` | list[str] | No | Related published papers by the authors |

## Output

A `CommsResult` with:
- `text`: Cover letter (≤250 words) starting with `HUMAN REVIEW REQUIRED`.
- `fill_markers`: List of `[FILL]` positions requiring author personalisation.
- `word_count`: Approximate word count (logged as a warning if >250).

## Letter structure

```
HUMAN REVIEW REQUIRED

[FILL: Dear Editor-in-Chief / Dr. [FILL: editor name],]

We submit our manuscript "[title]" for consideration in [journal].

[Novelty statement based on key_results — 1–2 sentences]

[Relationship to related_pubs — 1 sentence, if provided]

All authors have read and approved the manuscript.
The manuscript is not under consideration elsewhere.

[FILL: Corresponding author name, affiliation, email]
```

## Workflow

1. Collect the manuscript title, target journal, and 1–3 key results.
2. Run `maglab comms cover-letter` or invoke `CoverLetterAgent.draft(inputs)`.
3. Review every `[FILL]` field — fill in editor name and corresponding author details.
4. Verify the word count is ≤250 words.
5. Submit the letter alongside the manuscript via the journal portal.

## Quality gate

Before submitting the cover letter:
- [ ] Every `[FILL]` field has been completed.
- [ ] Word count ≤250 (body only).
- [ ] Novelty statement is grounded in the author's own results.
- [ ] No fabricated citations or claims.
- [ ] HUMAN REVIEW REQUIRED header is intact.

## References

- `maglab/authoring/comms/cover_letter.py` — `CoverLetterAgent`
- `maglab/authoring/comms/base.py` — `BaseCommsAgent`, `CommsResult`, guardrails
- MagLab §16.3 — Comms agent design and integrity rules
- MagLab Appendix C — Bundle skill catalogue
