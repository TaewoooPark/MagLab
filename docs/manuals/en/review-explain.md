# Review and Anomaly Explanation

[Manual index](index.md) · [한국어](../ko/review-explain.md)

Use this module when you want structured scientific criticism or mechanism
candidates for surprising data.

## Install

```sh
uv pip install -e ".[reviewer,literature]"
```

## Commands

```sh
maglab review manuscript.md --journal prl
maglab review manuscript.md --journal prb --author reviewer-a --author reviewer-b

maglab explain "AHE sign reverses above 200 K in Pt/CoFeB/MgO" --min-candidates 3
maglab explain "ST-FMR linewidth broadens nonlinearly with current" --json
```

## Review Panel

The review command runs a persona-style panel and then synthesizes consensus and
dissent. Use it before submission, before a group meeting, or after major
rewrites.

Good inputs:

- A manuscript Markdown file.
- A section draft.
- A response-to-reviewer draft.
- A technical abstract.

## Anomaly Explanation

The `explain` command is for abductive reasoning. It proposes mechanism
candidates and discriminating tests. Treat the output as a hypothesis list, not
as a conclusion.

Good prompts:

```sh
maglab explain "SMR changes sign after oxygen annealing"
maglab explain "FMR linewidth has a low-temperature upturn"
maglab explain "domain-wall velocity saturates at unexpectedly low current"
```

## Safety and Interpretation

- Review output is not a real peer review.
- Anomaly explanation is not proof.
- Use the output to design checks: repeat measurements, control samples,
temperature sweeps, angular dependence, thickness dependence, and literature
triage.

## Handoff

```sh
maglab lab plan "discriminate between Joule heating and spin torque artifact"
maglab lit search papers/anomaly_followup --top-n 30
maglab comms rebuttal --reviews reviews.txt --notes author_notes.md
```
