# Harness & Delivery — Round-3 Conformance Re-Review

> Reviewer scope: `plan/01-harness.md` (§5–§6) and `plan/02-delivery.md` (§7–§8)
> Evidence gathered: 2026-05-19
> Test run: `pytest tests/unit/test_core_hooks.py tests/unit/test_core_orchestrator.py tests/unit/test_mcp_client.py tests/smoke/ --timeout=120` → **267 passed, 0 failed**
> Full unit suite: **1784 passed, 1 skipped** (0 failures)
> Integration suite (f6): **50 passed** (Korean→English regression resolved)

---

## Verdict

**GAPS REMAIN**

Every CRITICAL/HIGH Round-1 gap has been closed at the code level. Two lower-priority gaps survive in diminished form: the `oracle_hook` registration in `default_registry` lacks an explicit test assertion, and the `detached_loop` git-commit path lacks test coverage. Neither represents a functional regression or a plan-invariant violation; both are test coverage gaps only. The underlying code is correct and wired.

---

## Closure check

| R1 Finding | Status | Evidence |
|---|---|---|
| **CRITICAL-1** — HonestyGate not applied at REPL turn boundary (#12) | **CLOSED** | `orchestrator.py:380–383` calls `_apply_honesty_gate(response_text)` before returning. `TestHonestyGateOnRespond` (3 tests) in `test_core_orchestrator.py:398–440` confirm violation flagging and non-suppression. |
| **CRITICAL-2** — Oracle not in PreToolUse hook chain (#14) | **CLOSED** | `hooks.py:151–200` defines `oracle_hook()`; `hooks.py:339` registers it with `prepend=True` in `default_registry()`. Code-level confirmation: oracle_hook is the first hook to execute in every `default_registry()` call. |
| **CRITICAL-3** — MCP client (A role) absent (#36) | **CLOSED** | `maglab/llm/mcp_client.py` exists (691 lines): `MCPClientRegistry` with `add_server`, `enable_server`, `disable_server`, lazy `_ensure_connected`, tool namespacing `server::tool`, `trust_level` enforcement. CLI: `mcp add/enable/disable` registered in `cli.py:510–603`. Test: 49 tests in `test_mcp_client.py` all pass. |
| **HIGH-4** — Harness manifest absent (#55) | **CLOSED** | `harness.manifest.json` exists at repo root with 10 agent entries, 3 skills, 1 MCP server, 4 workflows, and `model_routing` table. `maglab/core/manifest.py` (236 lines) loads it. `Orchestrator.__init__` calls `load_manifest(manifest_path)`. `TestManifestLoader` (4 tests) in `test_core_orchestrator.py:540–605` verify load, missing-file no-op, bad JSON no-op, and orchestrator wiring. |
| **HIGH-5** — Orchestrator does not use ModelRouter (#8) | **CLOSED** | `Orchestrator.__init__` accepts `model_router: Any | None` (`orchestrator.py:320,337`). `_tool_loop(stage)` resolves `stage_model = self._model_router.model_for(stage)` (`orchestrator.py:533–535`) and passes it to `backend.complete(..., model=stage_model)`. `_process_node` calls `_tool_loop(stage="build")`. `TestModelRouterIntegration` (5 tests) in `test_core_orchestrator.py:444–530` verify wiring and stage routing. |
| **#7** — `experiment-manager` agent spec absent (#7) | **CLOSED** | `agents/experiment-manager.md` exists with full 6-element contract (YAML frontmatter + objective/input/output-schema/tool-budget/source-guide/boundaries). Also registered in `harness.manifest.json` agents list. |
| **#19** — Ralph `detached_loop` missing git commit (DEVIATION) | **CLOSED (code)** | `ralph.py:547–600`: `detached_loop` accepts `git_commit: bool = False`; calls `_git_commit_iteration()` after each successful step. `_git_commit_iteration()` (`ralph.py:620–653`) runs `git add -A` + `git commit -m "ralph: <type> iteration N"` with CalledProcessError/FileNotFoundError/TimeoutExpired suppression. **Residual gap**: no test exercises `git_commit=True` in `test_core_ralph.py`. |
| **#25** — `ResearchPool` no vector index slot (#25) | **SUPERSEDED** | `memory.py:391–441` implements `semantic_query()` with TF-IDF cosine similarity — a working relevance-ranked search that exceeds the stub requirement. No `_vector_index`/`_build_index` named stub was added, but the P5 upgrade path is effectively the `semantic_query()` method signature itself (replacing TF-IDF implementation body with lancedb). The original fix recommendation is moot. |
| **#43** — Subagent raw-text response not wrapped in schema | **CLOSED** | `subagents.py:277–283`: `_parse_structured_output(raw_output)` returns None on failure → fallback wraps as `{"status": "partial", "raw": raw_output, "warnings": ["..."]}`. |
| **#54** — Gateway not wired to orchestrator completion (#54) | **CLOSED** | `orchestrator.py:479,492,505` calls `_notify_gateway(task_id, goal, result)` at all three exit paths (`goal_achieved`, `all_pruned`, `partial`). `_notify_gateway` (`orchestrator.py:823–866`) puts `NotificationEvent(kind="research_complete", ...)` on `gateway_runner.notification_queue`. `TestGatewayNotification` (4 tests) in `test_core_orchestrator.py:645–719` verify queueing and no-op when `gateway_runner=None`. |
| **#58** — Korean→English integration test failures | **CLOSED** | `tests/integration/test_f6_data_to_figure.py`: 50 passed, 0 failed. Pattern mismatch resolved. |

---

## Remaining or new gaps

### GAP-R3-A — `oracle_hook` in `default_registry` not asserted by any test

**Severity:** LOW (test coverage gap only; code is correct)

**File:** `tests/unit/test_core_hooks.py:246–255`

**Problem:** `test_default_registry_returns_hook_registry` only asserts `isinstance(reg, HookRegistry)`. It does not assert that `oracle_hook` is registered (i.e., `"oracle_hook" in reg.registered_hook_names`). If someone accidentally removes the `registry.register("oracle_hook", oracle_hook(), prepend=True)` line from `hooks.py:339`, no test would catch it.

**Fix:** Add to `test_core_hooks.py`:
```python
def test_default_registry_includes_oracle_hook() -> None:
    reg = default_registry()
    assert "oracle_hook" in reg.registered_hook_names
    # oracle_hook must run first (prepended) so physics is gated before tier/plan checks
    assert reg.registered_hook_names[0] == "oracle_hook"
```

---

### GAP-R3-B — `detached_loop(git_commit=True)` path untested

**Severity:** LOW (test coverage gap only; `_git_commit_iteration` code is correct)

**File:** `tests/unit/test_core_ralph.py`

**Problem:** No test passes `git_commit=True` to `detached_loop`. The git-subprocess path (`subprocess.run(["git", "add", "-A"])` etc.) is never exercised in the test suite. The error-suppression branches (non-git-repo, nothing-to-commit) are also untested.

**Fix:** Add a test that mocks `subprocess.run`, passes `git_commit=True`, and asserts `git add -A` + `git commit` calls were made with the expected iteration label. A second test confirms non-git-repo does not raise.

---

## Plan conformance summary

All plan/01-harness.md and plan/02-delivery.md requirements that were PARTIAL, MISSING, or DEVIATION in Round 1 are now implemented in code. The two residual items above are test-coverage gaps only and do not affect runtime behavior or the verifiable-orchestrator guarantee. No regression was introduced by the Round-2 patches.

| Category | Previously PARTIAL/MISSING/DEVIATION | Now |
|---|---|---|
| HonestyGate at REPL boundary (CRITICAL-1) | PARTIAL | MET |
| Oracle in PreToolUse hook chain (CRITICAL-2) | PARTIAL | MET |
| MCP client A-role (CRITICAL-3) | MISSING | MET |
| Harness manifest (HIGH-4) | MISSING | MET |
| ModelRouter wired in Orchestrator (HIGH-5) | PARTIAL | MET |
| experiment-manager agent spec (#7) | MISSING | MET |
| Ralph detached git commit (#19) | DEVIATION | MET (code); test coverage gap remains |
| ResearchPool semantic search (#25) | PARTIAL | MET (superseded by TF-IDF impl) |
| Subagent output schema enforcement (#43) | PARTIAL | MET |
| Gateway notification wiring (#54) | PARTIAL | MET |
| Korean→English integration failures (#58) | PARTIAL | MET |
