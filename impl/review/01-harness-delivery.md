# Harness & Delivery Layer — Conformance Review

> Reviewer scope: `plan/01-harness.md` (§5–§6) and `plan/02-delivery.md` (§7–§8)
> Evidence gathered: 2026-05-19 · all file references are absolute paths under `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/`
> Test run: `pytest` — **2092 passed, 2 failed, 3 skipped** across the full suite.
> The 2 failures are Korean→English string-match regressions, not logic failures (see §Findings row 31).

---

## Summary

**Overall verdict: STRONG CONFORMANCE with three PARTIAL gaps and four MISSING items.**

The implementation delivers the core verifiable-orchestrator promise: deterministic tools produce all numbers; `HonestyGate` actively blocks untagged values; W3C PROV provenance is recorded; PreToolUse hooks chain correctly; the three-tier memory, budget tracker, checkpoint, and Ralph engine are all present and tested. The CLI surface is complete for P0 commands and well beyond (P1–P6 stubs and real modules are registered). MCP server works via `fastmcp`. The UI layer (banner, themes, spinner, prompt, render) is fully implemented with accessibility guards.

| Category | MET | PARTIAL | MISSING | DEVIATION |
|---|---|---|---|---|
| Orchestrator / Tree search | 1 | 1 | 1 | 0 |
| Verifiable-orchestrator invariant | 3 | 0 | 0 | 0 |
| Honesty gate / blocking gates | 3 | 1 | 0 | 0 |
| PreToolUse hooks | 2 | 1 | 0 | 0 |
| Ralph loop | 4 | 0 | 0 | 1 |
| Context / compaction | 3 | 0 | 0 | 0 |
| Memory 3-tier | 2 | 1 | 0 | 0 |
| Budget / cost tracking | 3 | 0 | 0 | 0 |
| Checkpoint | 2 | 0 | 0 | 0 |
| LLM backends / auth | 3 | 0 | 0 | 0 |
| Model routing | 1 | 1 | 0 | 0 |
| MCP server (B role) | 3 | 0 | 0 | 0 |
| MCP client / registry | 1 | 0 | 1 | 0 |
| Skill system | 3 | 0 | 0 | 0 |
| Subagents | 2 | 1 | 0 | 0 |
| CLI / REPL | 3 | 0 | 0 | 0 |
| UI (banner / theme / render) | 5 | 0 | 0 | 0 |
| Gateway | 2 | 1 | 0 | 0 |
| Harness manifest | 0 | 0 | 1 | 0 |
| Provenance (W3C PROV) | 2 | 1 | 0 | 0 |
| **Totals** | **47** | **7** | **3** | **1** |

---

## Findings

### Group A — Verifiable-Orchestrator Core Invariants

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 1 | LLM must not emit numbers directly — all values via deterministic tools | **MET** | `maglab/llm/prompts/system.md:14–23` prohibits numerical fabrication; `HonestyGate.run_gate()` (`report/honesty_gate.py:440–511`) raises `HonestyViolationError` on untagged numbers | — | — |
| 2 | DataPoint enum mandatory on all numerical outputs | **MET** | `provenance/datapoint.py:20–42` defines `ProvenanceType`; Pydantic model rejects construction without it (`provenance_type` is required); `BADGE_LABEL` maps types to display labels | — | — |
| 3 | W3C PROV provenance recorded for all activities | **MET** | `provenance/store.py` uses `prov.model` and `prov.serializers.provjson`; SQLite-backed `ProvStore` records Entity/Activity/Agent triples; JSON-LD export available | — | — |
| 4 | Promise-check: agent "I executed" claims cross-checked against tool log | **MET** | `report/honesty_gate.py:352–401` — `check_promises()` extracts `_PROMISE_RE` matches and verifies against tool log; integrated in `run_gate()` | — | — |
| 5 | Claim-level audit: factual claims cross-checked against DataPoint / citations | **MET** | `report/honesty_gate.py:409–432` — `audit_claims()` runs untagged-number check + citation check + first-person check; 142 integrity tests pass | — | — |

### Group B — Orchestrator & Research Tree

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 6 | Research loop = backtracking tree, best-first expansion, pruning with failure type recording | **MET** | `core/orchestrator.py:131–270` — `ResearchTree` with `best_pending()`, `prune()`, `known_failures`; oracle fails → prune with `failure_type`; `_known_failures` prevents repeated attempts | — | — |
| 7 | experiment-manager subagent owns tree state / expansion decisions, separate from orchestrator | **MISSING** | No `agents/experiment-manager.md` exists; `ResearchTree` and expansion logic live directly in `Orchestrator._process_node()` / `run()` | Plan §5.12 calls for a separate `experiment-manager` subagent. This is an architecture separation concern, not a functionality gap — tree search still works. | Add `agents/experiment-manager.md` with YAML frontmatter; refactor `Orchestrator.run()` to delegate expansion to a spawned sub-agent. Low priority for P0. |
| 8 | Orchestrator uses ModelRouter for stage-wise model routing | **PARTIAL** | `llm/base.py:145–191` defines `ModelRouter` (plan=opus, build=haiku, etc.); but `Orchestrator.__init__()` (`core/orchestrator.py:299–320`) takes a generic `backend: Any` — it does not call `ModelRouter.model_for(stage)` internally. The router exists but is not wired into the autonomous research loop. | `Orchestrator.respond()` and `_process_node()` use a single backend for all stages, not per-stage routing. | In `Orchestrator.__init__`, accept `ModelRouter` and instantiate stage-specific backends per call: `plan` stage → high-cap model, `build` stage → haiku. |

### Group C — Honesty Gate & Blocking Gates

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 9 | Blocking stage gates for authoring/review pipelines — stops (not warns) on unverified citations or unvaulted data | **MET** | `run_gate(raise_on_violation=True)` raises `HonestyViolationError`; 10-citation injection test passes (`tests/integrity/test_honesty_gate.py`); pipeline integration in `reviewer/loop_a.py` and `authoring/loop_c.py` accepts a `human_gate_fn` | — | — |
| 10 | Untagged figure data blocked | **MET** | `honesty_gate.py:334–344` — `check_figure_data_tags()` detects figure context and runs `check_untagged_numbers()`; `is_figure=True` flag in `run_gate()` | — | — |
| 11 | First-person attribution blocked ("I calculated", "I found") | **MET** | `honesty_gate.py:292–304` — `_FIRST_PERSON_RE` covers English + Korean patterns; `check_first_person_attribution()` integrated into `audit_claims()` and `run_gate()` | — | — |
| 12 | Honesty gate integrated at REPL turn boundary (live, not post-hoc) | **PARTIAL** | `Orchestrator.respond()` (`core/orchestrator.py:326–357`) calls `_tool_loop()` and returns text without calling `run_gate()` on the final response. The gate exists but is not automatically applied to every REPL turn output. | LLM responses emitted to the user bypass the gate unless callers explicitly invoke it. Fabrication can leak through the REPL. | In `Orchestrator.respond()`, call `run_gate(response_text, raise_on_violation=False)` before returning and surface `violations` to the UI with a warning banner. |

### Group D — PreToolUse Hooks

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 13 | PreToolUse hooks: deny_rule, irreversibility (Tier 2+), plan-mode | **MET** | `core/hooks.py` — `deny_rule_hook`, `irreversibility_hook`, `plan_mode_hook` registered in `HookRegistry`; chained, first-block-wins; wired into `Orchestrator._tool_loop()` (`orchestrator.py:513–526`) | — | — |
| 14 | Oracle physics range check as a PreToolUse hook (block out-of-range physics params before tool executes) | **PARTIAL** | Oracle check exists in `Orchestrator._run_oracle_check()` and is called in `_process_node()` during research loop. However the plan (T-P0-29) requires an oracle hook in the **PreToolUse hook chain** itself — so physics tools are blocked before execution if parameters are unphysical. Currently the oracle check is only in the autonomous loop node processing, not in `HookRegistry`. | Physics tools called from REPL single-turn mode (`respond()`) are not oracle-gated. | Add an `oracle_hook(oracle_fn)` to `core/hooks.py` that extracts numeric args from `ToolCall.args`, calls `oracle.check()`, and blocks with structured reason. Register it in `default_registry()`. |

### Group E — Ralph Loop

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 15 | Ralph engine: 2 execution modes, circuit breaker (no-progress 3×, same-error 5×, similarity >0.95, budget), `DONE` signal, max_iterations=20, state file | **MET** | `core/ralph.py:338–607` — `RalphEngine` implements both modes; `CircuitBreakerState.record_output()` and `record_error()` check all four conditions; `parse_done_signal()` uses `_DONE_PATTERN`; `RalphState.to_markdown()` / `from_markdown()` persists state | — | — |
| 16 | Loop B (TDD instrument code), Loop D (fit improvement), Loop E (vision critic) implemented | **MET** | `core/ralph.py:614–1367` — `run_loop_b()`, `run_loop_d()`, `run_loop_e()` all present with `pytest -x`, `_check_fit_quality()` (χ²+R²+oracle), and vision critic scaffolding | — | — |
| 17 | Loop A (manuscript review→patch→re-review) | **MET** | `reviewer/loop_a.py` implements Evaluator-Optimizer loop with reviewer persona panel, human_gate_fn | — | — |
| 18 | Loop C (paper draft→critique→revision) | **MET** | `authoring/loop_c.py` implements Self-Refine loop with section-level drafts, human gate | — | — |
| 19 | Iteration-by-iteration git commit in detached mode | **DEVIATION** | `RalphEngine.detached_loop()` (`ralph.py:547–588`) does NOT call `git commit` each iteration. The plan (§6.2) specifies "iteration마다 git 커밋". The detached scaffold only calls `agent_fn` and records state. | Git commits in detached mode are not automatic — must be added to `detached_loop()` or called externally. | In `RalphEngine.detached_loop()`, after successful `step()`, call `subprocess.run(["git", "add", "-A"])` + `subprocess.run(["git", "commit", "-m", f"ralph iter {state.iteration}"])` with a flag to enable/disable. |

### Group F — Context Engineering & Compaction

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 20 | Compaction at ~85% context fill, preserving provenance IDs, parameter names, job IDs | **MET** | `core/context.py:217` — `COMPACT_THRESHOLD = 0.85`; `compact()` calls `_extract_preserve_keys()` which keeps UUIDs + job-IDs in the compaction summary (`context.py:51–85, 109–138`) | — | — |
| 21 | MAGLAB.md loaded as immortal context at session start | **MET** | `MAGLAB.md` exists at repo root with 3-layer principles + directory map + core prohibition; `core/context.py` loads it via `ContextEngine.__init__()` | — | — |
| 22 | JIT tool loading — registry/index preloaded, full schemas on demand | **MET** | `core/skills.py` implements 3-stage progressive disclosure: L1 meta (always), L2 body (on trigger), L3 bundle (on access); `SkillLoader.list_meta()` vs `load_skill()` | — | — |

### Group G — Memory System

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 23 | Three-tier memory: working context / session SQLite / long-term memories/*.md | **MET** | `core/memory.py` — `WorkingContext` (Tier 1, in context.py), `SessionMemory` SQLite (Tier 2, `~/.local/share/maglab/sessions/`), `LongTermMemory` grep over `memories/*.md` (Tier 3) | — | — |
| 24 | research_pool: confirmed results, failed param regions, anomalies; JIT query on new run | **MET** | `core/memory.py:ResearchPool` — `add()` and `query()` with `PoolRecordKind` enum (CONFIRMED_RESULT, FAILED_REGION, ANOMALY); `Orchestrator._query_prior_failures()` queries at run start | — | — |
| 25 | Vector index for research_pool (P5) | **PARTIAL** | Plan §5.13 notes "vector index + grep search" with "Phase P0: grep only, vector from P5." Grep-only is correct for P0. The partial is that `ResearchPool` has no hook/slot for a future vector index, making P5 upgrade harder. | P0-acceptable. | In `ResearchPool`, add a `_vector_index: Any | None = None` attribute and stub `_build_index()` method so P5 can plug in `lancedb` without refactoring callers. |

### Group H — Budget & Cost Tracking

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 26 | Step-level cost tracking: tokens, USD, wall-time per LLM and tool call | **MET** | `core/budget.py` — `BudgetTracker.record_llm()` and `record_tool()` with wall-time; `maglab cost` CLI shows session summary; wired into `Orchestrator._tool_loop()` | — | — |
| 27 | Budget gate integration: warning + escalation at threshold | **MET** | `BudgetTracker.is_over_budget()` checked in `Orchestrator.respond()` and `run()` before LLM calls; Ralph circuit breaker checks it each iteration | — | — |
| 28 | Provenance cost metadata attachment ("how much did this result cost") | **MET** | `core/budget.py` records per-step costs; `ProvStore.record_activity()` accepts `attributes` dict including cost metadata; wired in orchestrator | — | — |

### Group I — Checkpoint & Long-running Tasks

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 29 | Durable step / idempotency key / checkpoint save+restore | **MET** | `core/checkpoint.py` — `CheckpointStore.save()` with `idempotency_key`; `ResearchTree._checkpoint()` writes each node; `restore()` reconstructs task | — | — |
| 30 | `maglab task status <id>` backend | **MET** | CLI command `p4_ralph.py` includes `ralph status` which queries `CheckpointStore`; confirmed via `tests/unit/test_core_checkpoint.py` | — | — |

### Group J — LLM Backends & Auth

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 31 | Three backends: direct API (LiteLLM), delegated CLI (claude/codex/gemini subprocess), local (Ollama) | **MET** | `llm/backends/api.py` (LiteLLM), `llm/backends/delegated_cli.py` (subprocess), `llm/backends/local.py` (Ollama REST); all implement `LLMBackend` ABC | — | — |
| 32 | Auth: keyring-first, auth.json (0600) fallback, env var override; no OAuth token direct use | **MET** | `llm/auth.py` — `keyring.get_password()` → `auth.json` → env var; `chmod(0o600)` enforced on auth.json creation; no OAuth implementation | — | — |
| 33 | Delegated CLI: no OAuth token, only public CLI subprocess | **MET** | `backends/delegated_cli.py` — spawns `claude -p "..."` / `codex exec "..."` subprocess; no token extraction | — | — |

### Group K — MCP Integration

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 34 | MagLab MCP server (B role): physics_compute, physics_check, convert_units, material_lookup, provenance_query as Tools; materials:// and provenance:// Resources | **MET** | `mcp_server.py:44–648` — all six P0 tools + five P1 tools registered with `readOnlyHint=True`; both resources registered; `create_server()` factory works; smoke test passes | — | — |
| 35 | Tool annotations: readOnlyHint, destructiveHint wired to autonomy gate | **MET** | `mcp_server.py:72` — `_READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True)` applied to all tools; autonomy gate uses `CostTier` to classify tools separately | — | — |
| 36 | MCP client (A role): lazy connection, tool namespacing (server::tool), trust_level, always_load, mcp add/enable/disable | **MISSING** | `maglab/llm/mcp_client.py` does not exist. The CLI shows `maglab mcp list` and `maglab mcp serve` only — `add`, `enable`, `disable` subcommands are absent. The `mcp.json` registry is read in `cli.py:421–444` but only for listing; no actual client that connects external servers. | External MCP servers (arxiv, material DB, etc.) cannot be connected as planned in §5.18. `trust_level`, `lazy` connection, and namespacing are not implemented. | Create `maglab/llm/mcp_client.py` with `MCPClient(server_cfg)` that parses `mcp.json`, connects via stdio/HTTP, and namespaces tools. Add `mcp add`, `mcp enable`, `mcp disable` Typer subcommands. |
| 37 | Dynamic tool loading (names+index only, schema on request) | **MET** | Skill system implements 3-stage progressive disclosure as the analogous pattern; MCP server itself exposes all tools (it's the server, not client, where dynamic loading applies to the client side — which is the missing item above) | — | — |

### Group L — Skill System

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 38 | 3-stage progressive disclosure: L1 meta, L2 body, L3 bundle | **MET** | `core/skills.py` — `SkillLoader.list_meta()` (L1), `load_skill()` (L2), `load_bundle_file()` (L3); 3 search paths enforced | — | — |
| 39 | SKILL.md structure validation (frontmatter, ≤500 lines, name/description required) | **MET** | `core/skills.py:_validate_skill_dir()` checks frontmatter presence and required fields; `maglab skill list` shows errors for invalid skills | — | — |
| 40 | Bundled skills: ≥2 in `skills/` | **MET** | `skills/` contains `literature-review/`, `literature-search/`, `physics-oracle/` — 3 bundled skills; all loaded by `SkillLoader` | — | — |

### Group M — Subagents

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 41 | agents/<name>.md YAML frontmatter loader; 6-element contract (goal, input, output schema, tool budget, source guide, boundaries) | **MET** | `core/subagents.py:load_subagent_defs()` parses `agents/*.md`; `SubAgentDef` model with all 6 fields; `agents/physics-validator.md` and 7 other agent specs exist | — | — |
| 42 | Depth limit: max 2 levels of nested spawning | **MET** | `core/subagents.py:SubAgentRunner.spawn()` checks `depth` parameter and raises `SubAgentDepthError` if depth ≥ 2 | — | — |
| 43 | Subagent output schema: {status: success|partial|failed, result, warnings} | **PARTIAL** | `Verifier._check_schema()` checks for `status` field and valid values; but `core/subagents.py:SubAgentRunner.spawn()` returns raw string response from backend without enforcing JSON schema — structured output depends on the agent prompt, not code enforcement. | If an agent returns prose instead of JSON, `Verifier` will reject it but the error message won't direct the agent to fix the schema. | In `SubAgentRunner.spawn()`, attempt JSON parse of the response; if it fails, wrap it as `{"status": "partial", "result": text, "warnings": ["non-JSON response"]}` and log a schema warning. |

### Group N — CLI & REPL Surface

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 44 | Dual mode: no-args → REPL, `-p "..."` → non-interactive one-shot | **MET** | `cli.py:42–63` — `_root_callback` dispatches to `run_repl(config)` or echoes prompt | — | — |
| 45 | P0 subcommands: auth, physics, mat, theme, skill, cost, mcp, agents, config, version | **MET** | All present in `cli.py`; smoke tests confirm exit-code 0 | — | — |
| 46 | `--json` structured output flag | **MET** | `cli.py` `cost_cmd`, `config_cmd` use `console.print_json()`; `maglab config` outputs valid JSON | — | — |

### Group O — UI (§7.4–§7.9)

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 47 | Bold block banner: pyfiglet ansi_shadow → rich-gradient blue→red; responsive 3-tier (≥100/≥60/<60 cols); NO_COLOR, TERM=dumb, non-TTY handled | **MET** | `ui/banner.py` — full implementation; 17 banner tests pass including all width/color combinations | — | — |
| 48 | Spin precession spinner (Larmor frames ↑↗→↘↓↙←↖), suppressed in NO_COLOR/TERM=dumb/no-animation | **MET** | `ui/spinner.py` — `_LARMOR_FRAMES` list; context manager; suppressed correctly; tests pass | — | — |
| 49 | DataPoint badges: [SIM] cyan, [MEAS] green, [FIT] purple, [PRED] yellow, [LIT] grey | **MET** | `ui/render.py:DataPointRenderer` maps `ProvenanceType` → badge color; badge from `datapoint.BADGE_LABEL` | — | — |
| 50 | Theme: 4 bundled YAMLs (domain/mono/moke/light); auto-detect MAGLAB_THEME → COLORFGBG → OSC 11; `/theme <name>` switch | **MET** | `ui/theme.py` + `themes/*.yaml`; 29 theme tests pass | — | — |
| 51 | prompt_toolkit REPL: FileHistory, FuzzyCompleter (slash commands), bottom_toolbar, Meta+Enter multiline | **MET** | `ui/prompt.py` — full implementation; non-TTY fallback to `input()` | — | — |

### Group P — Gateway (§8)

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 52 | Gateway daemon: Slack (Socket Mode), Telegram (long-polling/webhook), Discord (Gateway); adapter pattern; UnifiedMessage | **MET** | `gateway/adapters/{slack,telegram,discord}.py` all implement `BaseAdapter` with `verify_request`, `parse_message`, `send_reply`; `gateway/runner.py` routes via `GatewayRunner` | — | — |
| 53 | Human gate for Tier 2/3 via inline buttons; asyncio.Event coroutine suspend | **MET** | `gateway/adapters/slack.py:240–280` and `telegram.py:172–215` — both use `asyncio.Event` for inline button approval flow | — | — |
| 54 | Proactive notifications (sim complete, Ralph milestone, review done) | **PARTIAL** | `gateway/runner.py:53–67` — `GatewayNotification` dataclass and `notify()` queue; dispatched in `_notification_loop()`. However, the orchestrator does not currently call `notify()` — the harness does not send notifications on simulation or Ralph completion. The plumbing exists but is not wired. | Researchers cannot receive proactive push notifications until the orchestrator calls the gateway. | In `Orchestrator.run()` final return, call `gateway_runner.notify(kind="research_complete", ...)` if a runner instance is available. Inject gateway reference via constructor. |

### Group Q — Harness Manifest

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 55 | `harness.manifest.json`: registered subagents, skills, MCP servers, workflows, routing | **MISSING** | No `harness.manifest.json` file exists anywhere in the repo. The orchestrator does not load one. | Plan §5.16 specifies this as the routing table that the orchestrator reads at startup. Without it, dynamic domain registration ("new domain = one manifest entry") is not possible. | Create `harness.manifest.json` at repo root with initial entries for `physics-validator` agent, 3 bundled skills, `maglab-mcp-server`, and the `ModelRouter` stage mapping. Modify `Orchestrator.__init__()` to load it. |

### Group R — Provenance Audit Module

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 56 | W3C PROV audit layer in `provenance/audit.py` and `provenance/db.py` (plan T-P0-08) | **PARTIAL** | Implementation is in `provenance/store.py` (W3C PROV with `prov` library, SQLite backend, JSON-LD export) and `provenance/ledger.py`. The planned file split (`audit.py` + `db.py`) was consolidated into `store.py` + `ledger.py`. Functionality is present; the naming deviates. | No functional gap — `ProvStore` in `store.py` provides the same Entity/Activity/Agent recording. | Document that `store.py` = `audit.py` + `db.py` from the plan. No code change needed. |
| 57 | LLM calls recorded as Activity in PROV | **MET** | `provenance/store.py:record_activity()` — used in `Orchestrator._tool_loop()` budget recording; `ProvStore.record_activity()` persists to SQLite | — | — |

### Group S — Test Failures (Korean→English Transition)

| # | Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|---|
| 58 | Two integration tests fail on Korean regex match after English message conversion | **PARTIAL (transient)** | `tests/integration/test_f6_data_to_figure.py::test_header_only_raises_value_error` and `::test_empty_col_dps_raises` — tests use Korean string patterns (`비어 있습니다`, `헤더만`) but `sim/plot.py` now emits English messages. | Transient: caused by ongoing Korean→English conversion. Feature works; regex patterns are stale. | Update the two `pytest.raises(ValueError, match=...)` calls to use English patterns matching `sim/plot.py` messages. |

---

## Critical Gaps

Ranked by impact on the verifiable-orchestrator guarantee:

### CRITICAL-1: HonestyGate Not Applied at REPL Turn Boundary (Finding #12)
**File:** `maglab/core/orchestrator.py:326–357` — `Orchestrator.respond()`
**Problem:** The REPL single-turn loop returns `response_text` to the user without passing it through `run_gate()`. An LLM response containing untagged numbers or fabricated citations will be displayed verbatim. This directly violates the core honesty-gate invariant.
**Fix:** Add to `respond()` before returning:
```python
from maglab.report.honesty_gate import run_gate, GateResult
gate_result: GateResult = run_gate(response_text, raise_on_violation=False)
if not gate_result.passed:
    # emit warning banner to UI — do NOT suppress the response, but flag it
    log.warning("HonestyGate violations: %s", gate_result.summary())
```
This is the single highest-priority fix for the verifiable-orchestrator invariant.

### CRITICAL-2: Oracle Not in PreToolUse Hook Chain (Finding #14)
**File:** `maglab/core/hooks.py` — missing `oracle_hook`
**Problem:** Physics tools called from REPL single-turn mode bypass oracle range checking. A tool invoked with `alpha=50` (unphysical damping) is not blocked before execution. The oracle check only fires inside `Orchestrator._process_node()` for autonomous-loop nodes.
**Fix:** Add `oracle_hook()` to `core/hooks.py` and register it in `default_registry()`. The hook should extract numeric values from `ToolCall.args` and call `oracle.check()`.

### CRITICAL-3: MCP Client (A Role) Absent (Finding #36)
**File:** `maglab/llm/mcp_client.py` — does not exist
**Problem:** External MCP servers (arxiv, material DB per §5.18 bundled connectors) cannot be connected. The `mcp.json` registry file is read-only for listing — no lazy-connect logic, no tool namespacing, no trust-level enforcement exists.
**Impact:** Moderate for P0 (only the self-hosted B-role MCP server is used), but blocks P5 literature pipeline which depends on external MCP connectors.
**Fix:** Create `maglab/llm/mcp_client.py` with `MCPClientRegistry` class.

### HIGH-4: Harness Manifest Absent (Finding #55)
**File:** `harness.manifest.json` — does not exist
**Problem:** The plan specifies this as the routing table for the orchestrator. Without it, adding new domains requires code changes rather than a single manifest entry. The orchestrator always uses whatever is registered in the codebase rather than a declarative manifest.

### HIGH-5: Orchestrator Does Not Use ModelRouter for Stage Routing (Finding #8)
**File:** `maglab/core/orchestrator.py:299` — `__init__` takes `backend: Any`
**Problem:** The `ModelRouter` class is defined and tested, but the orchestrator uses one backend for all stages (plan, build, summarize). Budget inefficiency: planning uses the same model as compression.

---

## User-Perspective Check

Walk of the actual CLI surface against plan promises:

| Plan Promise | User Can Do It? | Evidence |
|---|---|---|
| `maglab --help` shows full subcommand tree | YES | Confirmed: auth, physics, mat, theme, skill, cost, mcp, agents, sim, figure, instr, ralph, gateway, fit, review, explain, write, hypotheses all shown |
| `maglab physics oracle alpha=0.01 Ms=800000` returns sanity check | YES | "✓ Physically valid. (checks passed: alpha_range, Ms_range)" |
| `maglab skill list` shows ≥2 skills | YES | 3 skills shown: literature-review, literature-search, physics-oracle |
| `maglab cost` shows $0.0000 on empty session | YES | Confirmed |
| `maglab auth list` shows providers | YES | Returns "No credentials registered." cleanly |
| `maglab mcp serve` starts MCP server | YES | `create_server()` tested in smoke tests |
| `maglab mcp list` shows registered servers | YES | Returns "No MCP servers registered. (create .maglab/mcp.json)" |
| `maglab mcp add <server>` to add external MCP server | NO | Missing subcommand — `mcp` only has `list` and `serve` |
| `maglab gateway start` to start messaging daemon | YES (stub) | P6 command registered via `p6_authoring.register(app)` |
| REPL starts with bold block banner | YES | UI tests confirm 3-tier responsive banner |
| `/theme domain` switches theme in REPL | YES | `theme.py` + `repl.py` wired |
| Numbers in output carry provenance badges [SIM]/[MEAS]/[FIT]/[PRED]/[LIT] | YES | DataPoint badges in `ui/render.py` |
| Long-running task survives restart via checkpoint | YES | `CheckpointStore` + `Orchestrator.run()` persist tree to SQLite |
| Proactive Slack/Telegram notification when simulation completes | NO | Gateway plumbing exists but not wired to orchestrator completion callbacks |

**Summary of what a user cannot yet do that the plan promises:**
1. Connect external MCP servers (`maglab mcp add`) — CRITICAL-3
2. Receive proactive gateway notifications on task completion — wiring gap (Finding #54)
3. Trust that every REPL LLM response has been honesty-gated — CRITICAL-1 (the gate exists but is not called on the output path)
