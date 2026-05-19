# Orchestration, Agents, MCP, and Gateway

[Manual index](index.md) · [한국어](../ko/orchestration.md)

Use this module when you want MagLab to coordinate several research tools rather
than run a single command.

## Interactive and One-Shot Use

```sh
maglab
maglab -p "Plan a reproducible SOT analysis workflow for Pt/CoFeB/MgO"
```

The REPL is the natural-language surface. It should route work into deterministic
tools, notebooks, literature workflows, analysis, and authoring.

## Credentials and Configuration

```sh
maglab auth set anthropic sk-ant-...
maglab auth list
maglab auth test anthropic
maglab config
maglab cost
maglab theme list
maglab theme set mono
```

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
