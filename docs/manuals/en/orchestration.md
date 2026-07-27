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

## Approval and Autonomy

Every tool call the model makes passes a hook layer before it runs: deny rules,
the physics sanity oracle, and an autonomy gate. The gate classifies each tool
from the hints it declares — read-only, destructive, whether it touches the
network — and the configured mode decides what happens:

| Mode | Runs without asking | Asks |
|---|---|---|
| `copilot` (default) | read-only, offline tools | anything that writes or reaches the network |
| `semi-auto` | the above plus read-only network tools | anything irreversible |
| `autonomous` | the above plus irreversible tools | destructive tools only |

On an interactive terminal an action that needs approval prompts on stderr and
waits for `y`. With no terminal — a piped `maglab -p`, CI, a cron job — there is
nobody to ask, so the action is refused and the reason is returned to the model
rather than the command dying. If that is not what you want for a batch run,
raise the mode explicitly:

```sh
maglab config set autonomy.mode semi-auto
maglab config show
```

Read-only tools such as `literature_search`, `provenance_query` and
`physics_compute` never prompt: they are classified from their own declared
hints, not from a hand-maintained list.

## Tools Across Backends

The `api` backend passes MagLab's tool schemas to the provider natively. The
delegated CLI backends (`codex`, `claude`, `gemini`) take no tool schema on the
command line, so MagLab describes the tools in the prompt and parses the reply
back into tool calls. Either way the call is executed by MagLab through the same
registry and the same hooks, so numbers and citations come from the
deterministic tools rather than from the model — and from whatever shell or file
tools the delegated CLI happens to ship with.

A model that ignores the protocol simply answers in prose. Nothing breaks; you
just get an answer without a tool-backed number.

These CLIs are agents, not completion endpoints, so they are slow to start:
`codex` sends roughly 19k tokens of context before answering and needs several
seconds for a one-word reply. The delegated-CLI timeout therefore defaults to
900 s. If a long research turn still overruns, the error names the setting:

```sh
maglab config set backend.delegated_cli.timeout 1800
```

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
maglab harness run literature-review --topic "Find SOT papers" --execute-local --local-max-steps 2 --output text
maglab harness pi-tool --payload-json '{"workflow":"literature-review","input":"Find SOT papers"}' --output text
maglab run "Find SOT papers" --harness-workflow literature-review
maglab harness worker search-scout --task "Find SOT papers"
maglab harness worker search-scout --task "Find SOT papers" --json
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
- Harness mode: `maglab harness ...` turns the manifest into inspectable
  execution plans. Planning is deterministic and offline — no provider is
  contacted — and `--execute-local` then runs the plan through MagLab's own
  subagent runner, so every step keeps the existing four-layer verification,
  hooks and budget accounting. Live PI execution is environment-gated and never
  faked.

Use `maglab harness doctor` to see what would stop a run: workflow steps that do
not resolve to a declared agent, agents with no `agents/*.md` behind them,
declared skills that are not installed, unregistered MCP servers, and whether an
LLM backend is configured. The two PI checks are reported but never block, since
local execution does not need PI — and a bare PI install has no `workflow` tool
anyway (that comes from pi-agents, not the base binary).

Use `maglab harness compile literature-review` to see the compiled workflow,
`maglab harness compile --write` to write the drift artifacts to
`.pi/workflows/`, and `maglab harness compile --check` to fail when the routing
table has drifted. The artifacts are machine-independent by construction — no
absolute paths, no local install state, no timestamps — so `--check` is safe to
wire into CI and fails only on a real manifest change.

`maglab harness run <workflow> --dry-run --output text` shows what would run in
a readable table; `--output json` (the default) emits the full contract:
`local_run_plan` with one entry per step, a topic-bound
`pi_agents_workflow_payload` for PI's `workflow` tool, and a `cross_links` block
carrying the PI flow id and any provenance activity. `ready` and `blockers`
always agree — anything that degrades a run without preventing it appears in
`warnings` instead, such as an MCP server that is declared but not registered.

Add `--execute-local` to run it here, `--local-max-steps 2` for a cheap live
smoke. The step limit is named for what it does: the subagent runner issues one
completion per step, so it bounds steps rather than turns inside a step. Each
step receives the topic plus a digest of what earlier steps returned, and a step
that fails verification stops the run rather than letting later work build on
it.

`maglab harness worker <agent> --task "..."` shows the plan for a single
subagent — model alias, resolved model, tools, which declared skills were found,
and which requested MCP servers are registered. Add `--json` for the machine
form.

Add `--record-provenance --provenance-db .maglab/harness-provenance.sqlite` to
record the *prepared* run as a W3C PROV activity with one entity per step,
before anything executes, so an interrupted run still leaves evidence of what
was attempted.

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
maglab lit search papers/sot --harness-plan --harness-plan --topic "SOT switching in CoFeB"
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
PI itself plus the pi-agents extension that provides the `workflow` tool. Until
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
