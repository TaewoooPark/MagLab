# Orchestration, Agents, MCP, and Gateway

[Manual index](index.md) · [한국어](../ko/orchestration.md)

Use this module when you want MagLab to coordinate several research tools rather
than run a single command.

## Interactive and One-Shot Use

```sh
maglab
maglab -p "Plan a reproducible SOT analysis workflow for Pt/CoFeB/MgO"
maglab doctor
```

The REPL is the natural-language surface. It should route work into deterministic
tools, notebooks, literature workflows, analysis, and authoring.

`maglab doctor` is the first command to run after installation. It checks the
current workspace, `MAGLAB.md`, configured backend, optional research extras,
external solvers, and simulation readiness without printing secrets.

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
```

Subagents are declared in `harness.manifest.json`. They represent bounded roles
such as local corpus checking, search scouting, citation auditing, paper review,
physics validation, result analysis, experiment management, hypothesis
generation, and communications writing.

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
