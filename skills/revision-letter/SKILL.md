---
name: revision-letter
description: >
  Point-by-point peer-review response letter workflow for journal resubmission.
  Invokes RevisionLetterAgent to quote each reviewer comment verbatim, draft a response,
  and add a change-location marker. Outputs carry HUMAN REVIEW REQUIRED; no auto-send.
  A DOI or manuscript location is required for every factual response claim (§3.3).
license: MIT
compatibility:
  claude-code: ">=1.0"
  maglab: ">=0.1"
user-invocable: true
allowed-tools:
  - read_file
  - write_file
---

# revision-letter — Point-by-point reviewer response letter skill

## Overview

This skill drafts a structured revision response letter aligned with MagLab research
integrity principles (§3.3) and the Appendix C bundle comms workflow.

**Core principles**:
- Every reviewer comment is quoted verbatim before the response.
- The AI does not invent new experimental data or results — only the author can supply those.
- All personalisation fields (editor name, page/line numbers, new data references) are
  marked `[FILL]` for the author to complete.
- Output always begins with `HUMAN REVIEW REQUIRED`.
- The letter is never auto-sent — it is written to a file for human review.

**Agent**: `maglab.authoring.comms.revision_letter.RevisionLetterAgent`
**CLI command**: `maglab comms revision`

## Inputs

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `review_decision` | str | Yes | Full journal decision letter containing reviewer comments |
| `comment_notes` | list[str] | No | Author notes per reviewer comment (leave empty to use [FILL]) |
| `tone` | str | No | `formal` (default) \| `respectful` \| `assertive` |
| `manuscript_orig` | str | No | Original manuscript excerpt (for context) |
| `manuscript_rev` | str | No | Revised manuscript excerpt (for context) |

## Output

A `CommsResult` with:
- `text`: Full revision letter starting with `HUMAN REVIEW REQUIRED`.
- `fill_markers`: List of `[FILL]` positions requiring author personalisation.
- `word_count`: Approximate word count.

## Letter structure

```
HUMAN REVIEW REQUIRED

[FILL: Dear Dr. [FILL: editor name],]

We thank the reviewers for their careful reading of our manuscript.
Below we address each comment point by point.

---
Reviewer 1, Comment 1:
> [verbatim comment text]

Response:
[AI-drafted response based on author notes or [FILL]]

Change location: [FILL: page/line in revised manuscript]

---
[... additional comments ...]

Sincerely,
[FILL: Corresponding author name]
```

## Workflow

1. Prepare the journal decision letter and your per-comment notes.
2. Run `maglab comms revision` or invoke `RevisionLetterAgent.draft(inputs)`.
3. Review every `[FILL]` field — fill in editor name, page numbers, and personalised responses.
4. Add new experimental data or figures manually — the AI draft shows where they belong.
5. Submit the completed letter via the journal submission portal.

## Quality gate

Before sending the revision letter:
- [ ] Every `[FILL]` field has been completed.
- [ ] Each reviewer comment is quoted verbatim.
- [ ] All new data claims reference the revised manuscript location.
- [ ] No fabricated results — all claims are from the author's own data.
- [ ] HUMAN REVIEW REQUIRED header is intact.

## References

- `maglab/authoring/comms/revision_letter.py` — `RevisionLetterAgent`
- `maglab/authoring/comms/base.py` — `BaseCommsAgent`, `CommsResult`, guardrails
- MagLab §16.3 — Comms agent design and integrity rules
- MagLab Appendix C — Bundle skill catalogue
