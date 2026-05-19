# agents/ — Subagent definitions

A MagLab subagent is defined by a single `agents/<name>.md` file — YAML
frontmatter + body (= system prompt). Same file convention as skills (`skills/`) (§5.16).

The `core/subagents.py` loader discovers definitions from this directory and `.maglab/agents/`.

## Frontmatter fields

| Field | Meaning |
|---|---|
| `name` | Subagent identifier (kebab-case) |
| `description` | Trigger text that the orchestrator uses to decide delegation |
| `tools` | Allowed tools — least-privilege allowlist |
| `model` | `opus` / `sonnet` / `haiku` / `inherit` |
| `max_turns` | Internal loop upper bound |
| `effort` | Reasoning intensity hint (optional) |
| `context` | Default `isolated`; `fork` inherits parent context |
| `skills` | Skills to preload (optional) |
| `mcp_servers` | MCP servers scoped to this agent (optional) |
| `hooks` | Hooks to apply (optional) |

The body (everything after the frontmatter) is the system prompt.

## Six-element contract (§5.16)

Every subagent spec states in the body: ① single objective ② input specification
③ output schema (structured JSON — `status{success|partial|failed}` · results · `warnings`)
④ tool budget (`max_turns` · tool allowlist) ⑤ source guide (what to read / not read)
⑥ task boundaries & ambiguity handling (no guessing; return `failed` when ambiguous).

Subagents do not see the parent conversation — they see only the task prompt they receive.
They return compressed conclusions only (context isolation is their raison d'être).
Nested spawning is not allowed — maximum two levels of depth.

## Definition list

Filled in as Phases progress. P0 provides the format, loader, and core definitions —
`physics-validator` · `result-analyst`. Later entries such as `sim-designer` ·
`effect-fitter` · `figure-designer` · `reviewer-persona` are added in their
respective Phases (§5.4).
