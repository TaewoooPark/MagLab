# tests/ — Verification

Implements the verification framework from PLAN §20 · `impl/09-testing-and-ci.md`.

## Layers

| Directory | Target |
|---|---|
| `unit/` | Deterministic functions — units · oracle · formulas · EffectModel.forward |
| `golden/` | External benchmark reproduction — µMAG · VAMPIRE · literature values (`golden/data/`) |
| `integration/` | Pipelines — gen→validate→run→parse→fit · handoffs |
| `smoke/` | CLI · MCP · gateway startup |
| `integrity/` | Honesty gate · citation injection · promise-check · untagged figures |
| `ui/` | Banner responsiveness · NO_COLOR · non-TTY · theme load |
| `harness/` | Subagents · routing · Ralph circuit breaker |

## Invariant rules

- **LLM-as-judge is prohibited for quantitative, citation, and fitting verification** — deterministic checks only (§20).
- Figures are compared by *value*, not pixel.
- No real hardware VISA sessions, live LLM calls, or network dependencies — use mocks, caches, or VCR.
- Golden values are updated only from external benchmarks — never from code-generated output.
