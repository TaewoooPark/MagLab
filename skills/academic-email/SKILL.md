---
name: academic-email
description: >
  Professional academic email workflow (≤200 words). Invokes AcademicEmailAgent
  to draft a concise email with subject line and follow-up action for one of five
  standard email types: collaboration, question, interview, recommendation, or application.
  Output carries HUMAN REVIEW REQUIRED; no auto-send (§16.3).
license: MIT
compatibility:
  claude-code: ">=1.0"
  maglab: ">=0.1"
user-invocable: true
allowed-tools:
  - read_file
  - write_file
---

# academic-email — Professional academic email skill

## Overview

This skill drafts a ≤200 word professional academic email, aligned with MagLab research
integrity principles (§3.3) and the Appendix C bundle comms workflow.

**Core principles**:
- Body must be ≤200 words.
- Output includes a subject line on the first line and a follow-up action at the end.
- The AI does not invent results, claims, or institutional affiliations.
- All personalisation fields (sender name, greeting, follow-up date) are marked `[FILL]`.
- Output always begins with `HUMAN REVIEW REQUIRED`.
- Auto-send is prohibited — the draft is returned to the researcher for review and manual sending.

**Agent**: `maglab.authoring.comms.academic_email.AcademicEmailAgent`
**CLI command**: `maglab comms email`

## Inputs

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `email_type` | str | Yes | One of: `collaboration` \| `question` \| `interview` \| `recommendation` \| `application` |
| `recipient` | str | Yes | Recipient's name or title (e.g. `"Professor Smith"`) |
| `topic` | str | Yes | Main purpose of the email |
| `related_papers` | list[str] | No | Relevant papers by the author or recipient |

## Email types

| Type | Intent |
|------|--------|
| `collaboration` | Express interest in a research collaboration on a shared topic |
| `question` | Ask a specific technical or scientific question politely |
| `interview` | Request a meeting or informational interview |
| `recommendation` | Request a letter of recommendation with context |
| `application` | Express interest in a position, program, or grant |

## Output

A `CommsResult` with:
- `text`: Email draft (≤200 words) starting with `HUMAN REVIEW REQUIRED`.
- `fill_markers`: List of `[FILL]` positions requiring author personalisation.
- `word_count`: Approximate word count (logged as a warning if >200).

## Email structure

```
HUMAN REVIEW REQUIRED

Subject: [concise subject line]

[FILL: Dear Professor / Dr. [FILL: name],]

[Email body — ≤200 words, based on email_type instruction]

Follow-up: [FILL: suggested date or action]

Best regards,
[FILL: Sender name, affiliation]
```

## Workflow

1. Identify the email type, recipient, and topic.
2. Run `maglab comms email` or invoke `AcademicEmailAgent.draft(inputs)`.
3. Review every `[FILL]` field — personalise greeting, sender info, and follow-up date.
4. Verify the body is ≤200 words.
5. Send the email manually from your own email client.

## Quality gate

Before sending the email:
- [ ] Every `[FILL]` field has been completed.
- [ ] Word count ≤200 (body only).
- [ ] No fabricated claims or institutional details.
- [ ] HUMAN REVIEW REQUIRED header is intact.
- [ ] Email is sent manually — no auto-send.

## References

- `maglab/authoring/comms/academic_email.py` — `AcademicEmailAgent`
- `maglab/authoring/comms/base.py` — `BaseCommsAgent`, `CommsResult`, guardrails
- MagLab §16.3 — Comms agent design and integrity rules
- MagLab Appendix C — Bundle skill catalogue
