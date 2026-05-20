# Code Review — Round 8, Core Domain

**Reviewer:** automated adversarial audit
**Scope:** `maglab/core/`, `maglab/provenance/`, `maglab/report/`, `maglab/llm/`, `maglab/ui/`, `maglab/config.py`, `maglab/repl.py`, `maglab/__main__.py`, `maglab/__init__.py`
**Date:** 2026-05-19
**Basis:** Independent fresh re-audit after R7 fix verification. All domain files read in full.

---

## Verdict

**ISSUES FOUND** — 1 genuine defect, MEDIUM severity: `MCPClientRegistry._ensure_connected()` in `maglab/llm/mcp_client.py` stores a session inside an `async with` context manager block and exits that context immediately, leaving a closed (dead) session in `self._sessions`. Every subsequent `call_tool()` call on that session will fail, and the early-return guard at line 562 (`if server_name in self._sessions: return`) prevents reconnection.

---

## R7 Fix Verification

The R7 finding was that `WorkingContext.compact()` replaced the conversation history with a `role="system"` message, causing `get_messages_for_llm()` to return two system-role messages — a violation of the Anthropic API contract.

**Status: FIXED and CONFIRMED.**

Live code at `maglab/core/context.py:140-145`:

```python
new_ctx = WorkingContext()
new_ctx.messages = [{"role": "user", "content": f"[Conversation summary]\n{full_summary}"}]
new_ctx.provenance_ids = list(self.provenance_ids)
new_ctx.job_ids = list(self.job_ids)
new_ctx.param_names = list(self.param_names)
new_ctx.token_count = max(1, len(full_summary) // 4)
```

The compacted summary is stored as `role="user"` with a `[Conversation summary]` prefix. `ContextEngine.get_messages_for_llm()` at line 257-263 prepends exactly one `role="system"` message and returns `[system_msg] + self._working.messages`. After compaction the resulting list is:

```
[{"role": "system", "content": <system prompt>},
 {"role": "user",   "content": "[Conversation summary]\n<compacted summary>"},
 ...]
```

This is valid for both Anthropic and OpenAI APIs. The R7 fix is correctly in place.

---

## Findings

### FINDING 1 — MEDIUM: `MCPClientRegistry._ensure_connected()` stores a dead session

**File:** `maglab/llm/mcp_client.py:549–605`

**Defect:**

`_ensure_connected()` uses `async with` to manage both the transport and the `ClientSession` lifetime:

```python
async with (
    stdio_client(server_params) as (read_stream, write_stream),
    ClientSession(read_stream, write_stream) as session,
):
    await session.initialize()
    self._sessions[server_name] = session          # stored at line 590
    await self._index_tools(server_name, session, cfg)
# <-- async with exits here, closing ClientSession and stdio_client
```

The `async with` block exits when `_index_tools` returns, which triggers both the `ClientSession.__aexit__` and `stdio_client.__aexit__` cleanup, closing the underlying transport streams. The reference stored in `self._sessions[server_name]` now points to a closed session object.

When `call_tool()` is subsequently called (line 537-542):

```python
await self._ensure_connected(server_name)  # returns immediately: guard at 562 fires
session = self._sessions.get(server_name)  # retrieves the dead session
result = await session.call_tool(tool_name, arguments or {})  # fails on closed transport
```

The early-return guard at line 562 (`if server_name in self._sessions: return`) prevents any reconnection attempt because `self._sessions[server_name]` is still set (to the dead session object). The system is permanently stuck in a broken state for the affected server after the first connection attempt.

The same defect is present in the HTTP/SSE path at lines 599-605.

**Impact:**

Every `call_tool()` call for any MCP server will raise an exception (likely `ClosedResourceError` or equivalent from `anyio`/`asyncio`) after the first `_ensure_connected` call. The tool_log will record every MCP tool as a failure. No MCP-backed tool can execute successfully. The error is silent at the REPL level (caught by `_execute_tool`'s broad except at `orchestrator.py:627`) and surfaced only as `[Error] Tool execution failed: ...` in the LLM's tool result.

This is a correctness defect, not a latent one — it fires on every MCP tool invocation.

**Concrete fix:**

The session lifetime must extend beyond `_ensure_connected`. The correct pattern is to keep the context managers alive with a persistent task or use an `asyncio.TaskGroup` / `anyio` background task. A minimal fix without architectural changes is to store the context-manager objects so they can be closed explicitly on teardown:

```python
# Add to __init__:
self._cm_stack: dict[str, contextlib.AsyncExitStack] = {}

async def _ensure_connected(self, server_name: str) -> None:
    if server_name in self._sessions:
        return
    ...
    stack = contextlib.AsyncExitStack()
    if cfg.transport == "stdio":
        read_stream, write_stream = await stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
    else:
        read_stream, write_stream = await stack.enter_async_context(
            sse_client(cfg.url)
        )
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
    await session.initialize()
    await self._index_tools(server_name, session, cfg)
    self._sessions[server_name] = session
    self._cm_stack[server_name] = stack  # keep context alive

# Add a close_all() or __aexit__ method to clean up stacks:
async def close_all(self) -> None:
    for stack in self._cm_stack.values():
        await stack.aclose()
    self._cm_stack.clear()
    self._sessions.clear()
```

---

## Non-Findings

Items investigated and dismissed:

- **R7 fix: `WorkingContext.compact()` role="user" change:** Confirmed in place at `context.py:141`. One system-role message invariant holds. No regression.

- **`_tool_loop` system-role message handling:** `get_messages_for_llm()` includes the system-role message as the first element of the flat messages list. LiteLLM's `APIBackend._call_litellm()` passes the full list (including system messages in dict form) to `litellm.completion(messages=msg_dicts)`. LiteLLM handles system-role messages in the messages array correctly for both OpenAI and Anthropic providers, extracting them to the top-level `system` parameter as needed. No API contract violation.

- **`_tool_loop` missing ASSISTANT message before TOOL messages (R7 non-finding retained):** When `response.content is None` and tool calls are present, no preceding ASSISTANT message is appended. Still unreachable because `complete()` is never called with a `tools=` argument in the current `_tool_loop`, so `response.tool_calls` is always `[]`.

- **`_tool_loop` `msg_objects` list mutation across loop iterations:** The accumulated message list is intentional — it grows as the tool-use conversation progresses (user turn → assistant tool call → tool result → next assistant response). Correct per API contracts.

- **`subagents.py` system-role message in messages list:** `SubagentRunner._execute()` inserts `Message(role=Role.SYSTEM, ...)` as the first element of `full_messages`. This is passed to the backend's `complete()`. LiteLLM handles this correctly. No defect.

- **`run_loop_b` early `return` inside `with tempfile.TemporaryDirectory()` at lines 864 and 883:** Python's `with` statement correctly calls `__exit__` on early return; the temp directory is cleaned up. No resource leak.

- **`run_loop_b` `current_code` not updated on `code_improver_fn` exception:** When the improver raises, the previous (broken) code runs again next iteration. The repeated-error circuit breaker (`error_limit=5`) terminates the loop after 5 identical failures. Acceptable design.

- **`CircuitBreakerState.record_output`: `last_output_hash` not updated on OUTPUT_SIMILARITY trigger:** The loop stops immediately via `_stop()` setting `active=False`. The stale hash is never read again. Not exploitable.

- **`CircuitBreakerState.last_score` sentinel `None`:** Correctly prevents spurious no-progress on the first iteration when score=0.0. R7 non-finding retained; confirmed still in place.

- **`ContextEngine.needs_compaction()` character/4 token estimate:** Affects when compaction fires but not correctness of the compaction itself. Non-finding retained.

- **`ProvenanceStore.__init__` `check_same_thread=False`:** Latent for future multi-threaded use; not exploitable in current single-threaded architecture. R7 non-finding retained.

- **`BudgetTracker._check_budget` not called from `record_tool` / `record_sim`:** By design — only LLM spend counts toward the USD budget gate. R7 non-finding retained.

- **`check_promises` write-tool suppression applies globally:** One write-tier tool logged anywhere in the session suppresses ALL promise violations. Accepted design tradeoff. R7 non-finding retained.

- **`APIBackend._inject_api_key` environment variable race:** Not exploitable in single-threaded architecture. R7 non-finding retained.

- **`MCPClientRegistry.disable_server()` closes sessions dict entry with `pop` but does not close the connection:** `self._sessions.pop(name, None)` removes the dead session from the cache. Since the session is already closed (per Finding 1), there is no resource leak in the current broken state. Once Finding 1 is fixed (session kept alive via `AsyncExitStack`), `disable_server` must also call `await self._cm_stack[name].aclose()`. This is a secondary implication of Finding 1, not an independent defect.

- **`_parse_critic_response` PASSED detection (last line, word boundary):** R5 fix at `ralph.py:1239-1246` remains in place. No regression.

- **`ReportBuilder.build()` `effective_vault_ids` merge:** `(vault_ids | known_ids) if vault_ids is not None else None` at `reporting.py:235` confirmed still in place. R4 F1 fix intact.

- **`RalphEngine.detached_loop()` `reset_no_progress()` before `step()`:** R4 F2 fix at `ralph.py:621` intact.

- **`_ABSOLUTE_ZERO_RE` regex (reasoning.py):** Out of scope for this domain review (core domain only). No regression visible from core files.

- **`ProvenanceStore._flush_to_db` per-record JSON attributes:** R5 fix verified still in place at `store.py:342`. Lineage queries work on individual row IDs, not full document dumps.

- **`HonestyViolation` / `HonestyViolationError` alias at `honesty_gate.py:98`:** Alias is the same class object. `except HonestyViolation` in `reporting.py:246` correctly catches `HonestyViolationError` instances. No defect.

- **`_tool_loop` filter `if m.get("content")` drops empty-content messages:** The system prompt and compacted summary always have non-empty content. No legitimate message in the current flow has empty content. Not a defect in practice.

- **`MCPClientRegistry.call_tool` split on "::":** `namespaced_name.split("::", 1)` correctly handles tool names containing `::`. The maxsplit=1 prevents accidental splitting on tool names with embedded `::`. No defect.

- **`get_registry()` singleton ignores `registry_path` after first call:** Documented behavior: "Ignored after the first call unless `registry_path` differs from the cached one." The `if _registry is None` guard means the path argument is only honoured on the first call. This is a design choice (module-level singleton), not a defect.
