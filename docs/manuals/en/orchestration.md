# Orchestration, Agents, MCP, and Gateway

[Manual index](index.md) · [한국어](../ko/orchestration.md)

Use this module when you want MagLab to coordinate several research tools rather
than run a single command.

## Terminal Walkthrough

Real MagLab CLI one-shot orchestration through Anthropic Haiku:

![MagLab Haiku orchestration terminal capture](../../assets/terminal/orchestration-haiku.png)

PI can also host the same operation interactively. Its startup screen should
show the loaded skills/extensions without a skill-conflict warning:

![PI interactive startup terminal capture](../../assets/terminal/pi-agents.png)

Inside PI, MagLab commands are run through the `!` operator:

![PI Haiku orchestration terminal capture](../../assets/terminal/pi-orchestration-haiku.png)

Harness readiness and handoff flows are still explicit CLI actions:

![PI harness orchestration terminal capture](../../assets/terminal/pi-orchestration-harness.png)

## Interactive and One-Shot Use

```sh
maglab
maglab -p "Plan a reproducible SOT analysis workflow for Pt/CoFeB/MgO"
maglab doctor
maglab doctor --smoke
maglab workspace brief
maglab workspace tree --summary --type docs --max-depth 2
maglab workspace tree --changed
```

The REPL is the natural-language surface. It should route work into deterministic
tools, notebooks, literature workflows, analysis, and authoring.

`maglab doctor` is the first command to run after installation. It checks the
current workspace, `MAGLAB.md`, configured backend, optional research extras,
external solvers, and simulation readiness without printing secrets.
By default it performs fast registration checks; add `--smoke` when you want a
live LLM sentinel prompt to verify that delegated CLI/API output is parsed as
plain model content.

Use `workspace brief` before asking project-specific questions. Use
`workspace tree --type docs|code|data`, `--max-depth`, and `--changed` when the
folder is large and you want MagLab or the model to focus on the right slice.

## Credentials and Configuration

```sh
maglab auth codex
maglab auth anthropic
maglab auth grok
maglab auth deepseek
maglab auth qwen
maglab auth kimi
maglab auth gemini
maglab auth openai
maglab auth list
maglab auth test anthropic
maglab auth status
maglab doctor --feature llm
maglab config
maglab cost
maglab theme list
maglab theme set mono
```

For Codex, authenticate with the official Codex CLI first. Then run
`maglab auth codex` or use `/connect codex` inside the REPL. MagLab stores only
the backend selection in `config.toml`; Codex OAuth tokens stay with the
official CLI.

In the REPL, `/help quick` shows the first-run path, `/help all` shows the full
tree, and `/help workspace`, `/help llm`, `/help sim`, or `/help figure` focus
on one area.

For direct API providers, run the provider command and enter the key through
hidden terminal input. The REPL equivalents are `/connect anthropic`,
`/connect grok`, `/connect deepseek`, `/connect qwen`, `/connect kimi`,
`/connect gemini`, and `/connect openai`. Each provider loads a MagLab runtime
profile so the model is told that it is operating as the MagLab research
orchestration agent, with provider-specific planning and verification guidance.

## Subagents and Skills

```sh
maglab agents list
maglab agents show citation-auditor
maglab skill list
maglab harness doctor
maglab harness compile literature-review
maglab harness compile --write
maglab harness compile --check
maglab harness run literature-review --dry-run --output text
maglab harness run literature-review --topic "Find SOT papers" --execute-local --local-max-turns 2 --output text
maglab harness pi-tool --payload-json '{"workflow":"literature-review","input":"Find SOT papers"}' --output text
maglab run "Find SOT papers" --harness-workflow literature-review
maglab harness worker search-scout --task "Find SOT papers"
maglab harness worker search-scout --task-json '{"workflow":"literature-review","input":"Find SOT papers"}' --execute
```

Subagents are declared in `harness.manifest.json`. They represent bounded roles
such as local corpus checking, search scouting, citation auditing, paper review,
physics validation, result analysis, experiment management, hypothesis
generation, and communications writing.

There are three execution surfaces today:

- Legacy MagLab CLI/REPL mode: `maglab`, `maglab -p ...`, Ralph, and the current
  orchestrator route model calls through MagLab's existing backend layer.
- Deterministic commands: `maglab physics ...`, `maglab lit ...`,
  `maglab analyze ...`, `maglab figure ...`, and similar commands run concrete
  MagLab modules. They do not require an LLM key unless the specific feature
  says so.
- PI harness mode: `maglab harness ...` is the transition surface for running
  manifest workflows through PI plus smolagents workers. The current CLI can
  inspect readiness, compile the `literature-review` workflow graph, write and
  check project-local `.pi/` wrappers, validate manifest references, and show
  workflow or worker plans. It does not fake live PI execution.

Use `maglab harness doctor` to see PI, smolagents, LiteLLM, and MCP readiness
separately. Use `maglab harness compile literature-review` to validate the
manifest workflow translation, `maglab harness compile --write` to write
`.pi/agents` and `.pi/workflows`, `maglab harness compile --check` to detect
generated wrapper or manifest-reference drift, and
`maglab harness run literature-review --dry-run --output text` to inspect what
would run without starting PI or a live model worker in a beginner-readable
summary. Use `--output json` or omit `--output` when automation needs the full
machine contract. That dry-run JSON record includes the
local worker subprocess plan in `local_run_plan` and a topic-bound
`pi_agents_workflow_payload` for PI's `workflow` tool; the payload contains the
concrete worker JSON for each spawn task. Use
`maglab harness run literature-review --topic "..." --execute-local` to run the
workflow locally through the same workers without PI. For cheap live smoke,
add `--local-max-turns 2`; text mode prints step start/done progress and hides
raw smolagents logs unless `--show-agent-log` is set. Use `maglab harness worker
<agent> --task "..."` to inspect the smolagents runtime plan for one worker, or
`--execute --task-json ...` when provider credentials are configured and you
want the local worker subprocess contract to run. Worker dry-run output shows
the model alias, resolved model, LiteLLM config source, tools, and runtime
availability. Live worker failures print short next-step guidance instead of a
traceback, including whether to install `.[harness]`, set `ANTHROPIC_API_KEY`,
or point `LITELLM_CONFIG_PATH` at a proxy/custom model config.
Use `maglab harness run literature-review --topic "..." --pi-handoff` to emit
the concrete PI CLI handoff command and prompt. The handoff prefers the
project-local `.pi/npm/node_modules/.bin/pi` binary when present and restricts
the parent PI process to the `workflow` tool with `--no-builtin-tools --tools
workflow`. `--execute-pi` runs that command explicitly; it may call a live
provider and is meant for environment-gated smoke or real runs, not default test
paths.
When a PI flow id already exists, pass `--pi-flow-id` on `harness run` so the
dry-run record matches the provenance cross-link contract. Add
`--record-provenance --provenance-db .maglab/harness-provenance.sqlite` to
write that prepared run as a W3C PROV activity and echo the created
`provenance_activity_id` in the dry-run JSON.
Use `maglab harness pi-tool --payload-json ... --output json|text` when PI or a
wrapper needs the MagLab side of the workflow-tool contract directly. Harness
responses include `cross_links` so PI flow ids, detected PI workflow/session ids,
and MagLab provenance ids are visible in one block. The root command
`maglab run "..." --harness-workflow literature-review` is the migration path; without
`--harness-workflow`, `maglab run` remains the legacy orchestrator fallback.

Harness runs that connect live MCP tools use the run-scoped `McpRunSession`
contract. A workflow/run opens MCP sessions only for that run and closes them
with `close_all()` on normal exit or error. Disabled servers in
`.maglab/mcp.json` are validated and displayed during discovery/doctor checks
but do not start external MCP processes.

`maglab lit search` also has an opt-in harness-plan path for the first migrated
workflow:

```sh
maglab lit search papers/sot --harness-plan --dry-run --topic "SOT switching in CoFeB"
maglab lit search papers/sot --harness-plan --harness-json
```

That path still extracts local keywords from the folder, then prepares the
`literature-review` PI payload. It skips the legacy direct OpenAlex connector
and does not write `evidence_matrix.json`; run plain `maglab lit search` when
you want the current direct evidence-matrix behavior.

The files under `.pi/workflows` are static generated artifacts used for drift
checks against `harness.manifest.json`. They are intentionally not the live
topic/input-bound PI execution payload; use the dry-run
`pi_agents_workflow_payload` for that handoff.

Live PI execution remains environment-gated. It requires installing and
configuring PI separately and running MagLab in an environment with the
`harness` extra, including smolagents and LiteLLM provider configuration. Until
that provider-backed bridge is configured, use deterministic commands or the
legacy CLI/REPL for real work, and treat harness dry-runs or `--pi-handoff`
output as workflow validation and PI handoff inspection.
Install PI/pi-agents from the PI package instructions and then run
`maglab harness doctor`; if `.pi/npm/node_modules/.bin/pi` exists in the project,
MagLab prefers that binary. For LiteLLM, either set `LITELLM_CONFIG_PATH` to a
proxy config or provide direct provider credentials such as `ANTHROPIC_API_KEY`.
When `LITELLM_CONFIG_PATH` is set, live `maglab harness worker ... --execute`
uses that file for both planning and execution. The bundled
`configs/litellm.example.yaml` is not treated as live readiness by `harness
doctor`; it must be copied to a real config path or replaced by direct provider
credentials. Dry-runs and PI handoff inspection remain available when live
provider readiness is incomplete.

Workspace skills live under `.maglab/skills/<skill-name>/` and are discovered
before user-global and bundled skills. The local helper layer is deterministic
and offline:

- `maglab skill create <name> --description "..."`
  creates a loadable `SKILL.md` package with `references/`, `scripts/`, and
  `evals/` directories.
- `maglab skill install <path>` copies an existing local skill package into
  `.maglab/skills` after validating its frontmatter.
- Both helpers are idempotent. If the same skill is already present, they skip
  without overwriting local edits.

The same surfaces are available in the REPL as `/skill create`, `/skill install`,
and `/skill list`. Use `maglab instr skillgen` for instrument-specific skills.

## Ralph Loop

Ralph is the autonomous research-loop engine. Use it for bounded exploration,
not for unsupervised claims.

```sh
maglab ralph start "Optimize SOT measurement plan for Pt/CoFeB/MgO" --max-iter 10
maglab ralph status
maglab ralph cancel
```

## Hypotheses

```sh
maglab hypotheses "orbital Hall torque in light-metal/ferromagnet bilayers" --n 8 --json-out hypotheses.json
```

Treat generated hypotheses as ranked suggestions. They need physical checks,
literature checks, and experiments.

## MCP

MagLab can expose tools through MCP and register external MCP servers.

```sh
maglab mcp serve
maglab mcp list
maglab mcp add arxiv "npx -y @modelcontextprotocol/server-arxiv" --trust-level trusted
maglab mcp enable arxiv
maglab mcp disable arxiv
```

## Gateway Bots

Gateway support lets a lab interact with MagLab through Slack, Telegram, or
Discord.

```sh
maglab gateway setup
maglab gateway start
maglab gateway status
maglab gateway stop
maglab gateway install
```

Keep gateway credentials private and restrict allowed users/channels.

## Practical Pattern

Use individual deterministic commands while developing a workflow. Once the
steps are clear, move to the REPL, Ralph, or subagent workflows to coordinate
the same steps repeatedly.
