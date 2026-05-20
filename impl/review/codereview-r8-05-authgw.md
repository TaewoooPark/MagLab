# Code Review Round 8 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-19
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**ISSUES FOUND** — 1 finding (1 MEDIUM)

---

## R7 Fix Verification

### R7-F1: Background gateway startup — `is_running()` order relative to env-var guard

**Status: CONFIRMED FIXED — all four control-flow cases verified**

The R7 fix is correctly in place at `p6_authoring.py:659–678`. The fix reads `pid_already_claimed` from `os.environ` **before** calling `is_running()`, and the `is_running()` call is gated on `not pid_already_claimed`. All four cases are verified:

**Case 1 — Background-spawned child (env var set):**
- `pid_already_claimed = True` (line 674: `os.environ.get("MAGLAB_GATEWAY_PID_CLAIMED") == "1"`)
- Guard at line 676: `if not pid_already_claimed and is_running()` → short-circuits; `is_running()` is **never called**
- Child skips both `is_running()` and the `open("x")` atomic claim (line 693: `if not pid_already_claimed`)
- Child proceeds directly to `_run_gateway_foreground()` at line 706 → event loop starts correctly
- **FIXED**

**Case 2 — Direct foreground invocation (`gateway start --foreground`, no env var):**
- `pid_already_claimed = False`
- `is_running()` is called; if a daemon is genuinely running it returns `True` and the function returns early at line 678
- If not running, proceeds to `open("x")` atomic claim at line 696
- **CORRECT**

**Case 3 — Background double-start (two concurrent `gateway start` in background mode):**
- Both parents attempt `pid_file.open("x")` at line 726; only one wins — loser gets `FileExistsError` at line 728 and exits cleanly
- **CORRECT**

**Case 4 — Atomic TOCTOU guard:**
- Parent performs `open("x")` (O_CREAT|O_EXCL) before spawning child (lines 726–727); only one winner per filesystem atomicity guarantee
- Child is signalled via `MAGLAB_GATEWAY_PID_CLAIMED=1` (line 737) to skip re-claiming; no double-`open("x")` on the same file
- **CORRECT**

---

## Findings

### F1 — MEDIUM | `maglab/mcp_server.py:379` | `sim_run` carries `readOnlyHint=True` but writes temp files to disk

**Defect:**

The `sim_run` MCP tool is annotated `annotations=read_only` (`ToolAnnotations(readOnlyHint=True)`) at line 379. However, the execution path through `sim_run` always writes to disk before any external-solver availability check:

1. `sim_run` calls `run_sim_overlay(spec_dict)` (via `_run_backend` in `sim/plot.py`).
2. `_run_backend` dispatches to `_run_mumax3`, `_run_oommf`, or `_run_magnumnp` in `sim/plot.py`.
3. `_run_mumax3` calls `maglab.sim.micro.mumax3.run(scale_spec)`.
4. `mumax3.run()` calls `generate_mx3_file(spec, output_dir)` **unconditionally** (line 181 of `mumax3.py`).
5. `generate_mx3_file` calls `tempfile.mkdtemp(prefix="maglab_mumax3_")` and then `script_path.write_text(mx3_text)` (line 160 of `mumax3.py`).

The same pattern exists for `_run_oommf` → `oommf.py` → `generate_mif_file()` which likewise calls `tempfile.mkdtemp` and `mif_path.write_text()` (line 188 of `oommf.py`).

Critically, the `.mx3`/`.mif` file is written **before** `run_mumax3()` checks whether the MuMax3 binary is on PATH (`check_binary("mumax3")` at line 104 of `backends/local.py`). Even when the solver is absent, a temp file has already been written to disk.

The module-level docstring at lines 34–36 explicitly lists the non-read-only tools:
```
readOnlyHint=False (figure_render, figure_export, instr_search_manual,
instr_ingest_manual, instr_generate_skill, instr_scaffold).
```
`sim_run` is absent from this list, and the `_WRITE_ANNOTATIONS` comment at lines 85–86 also omits it. Both the annotation and the documentation are incorrect.

**Impact:** MEDIUM — The MCP host uses `readOnlyHint` to determine whether a tool may modify system state and whether it can be called in a restricted-write context. An MCP client enforcing read-only mode (e.g. `--no-write` sandbox) will call `sim_run` believing it is safe, but it will write to the filesystem. This violates the MCP tool annotation contract and can cause unexpected write failures in restricted environments or mislead operators about the tool's side effects. The annotation inconsistency also affects any automated tooling that uses the hint to classify tools for approval-gate purposes.

**Fix:**

Change the `sim_run` annotation from `read_only` to `write_op` at `mcp_server.py:379`:

```python
# Before (incorrect):
annotations=read_only,

# After (correct):
annotations=write_op,
```

Also update the module-level docstring (line 35) and the `_WRITE_ANNOTATIONS` comment (line 86) to include `sim_run`:

```python
# Module docstring (lines 34-36):
#   readOnlyHint=False (figure_render, figure_export, sim_run,
#   instr_search_manual, instr_ingest_manual, instr_generate_skill, instr_scaffold).

# _WRITE_ANNOTATIONS comment (lines 85-86):
# Annotation for tools that write files to disk (figure_render, figure_export, sim_run,
# instr_ingest_manual, instr_generate_skill, instr_scaffold).
```

---

## Non-Findings

The following areas were investigated in full and found to be clean:

- **R7-F1 gateway startup fix (all four cases):** Confirmed fixed at `p6_authoring.py:674–706`. Background child, direct foreground, double-start rejection, and TOCTOU guard all verified correct.
- **`sim_validate` annotation (`read_only`):** `validate()` in `sim/validate.py` performs static checks only; no file I/O. Annotation is correct.
- **`sim_parse` annotation (`read_only`):** Reads an existing file and returns a `JobResult`. No writes. Annotation is correct.
- **`sim_run` temp file cleanup:** Temp directories created by `mumax3.run()` / `oommf.run()` are system temp directories (under `/tmp`). They are not cleaned up by the tool, but this is an OS-managed temp directory leak rather than a security issue.
- **Slack `verify_request` — allowlist enforced without signing_secret:** Even when `signing_secret` is absent (HMAC skipped with a per-request log warning), the user-ID and channel allowlist checks at lines 160–168 of `slack.py` are still executed. No auth bypass.
- **Slack replay-attack protection — unparseable timestamp:** When `signing_secret` is configured and the timestamp is unparseable, the code correctly rejects the request at lines 132–139 of `slack.py`. When `signing_secret` is absent the timestamp check is non-fatal (replay protection is already absent without the secret). Correct.
- **Telegram `verify_request` — missing HMAC:** Telegram adapter does not implement webhook HMAC verification. This is a known limitation (noted in R6 non-findings) and is mitigated by user/channel allowlist enforcement. Not introduced by recent changes.
- **Discord `verify_request` — missing HMAC:** Same situation as Telegram. Allowlist is correctly enforced.
- **`stop_daemon()` PID file cleanup after SIGTERM:** `stop_daemon()` at `runner.py:386` calls `remove_pid()` immediately after `os.kill(pid, SIGTERM)`. The daemon's `finally` blocks may not run on SIGTERM (Python `asyncio.run` does not convert SIGTERM to `CancelledError`), but the stop command itself cleans up the PID file. No stale PID file problem.
- **Double `remove_pid()` in `_run_gateway_foreground`:** The inner `_main.finally` (line 1224) and outer `finally` (line 1231) both call `remove_pid()`. Safe: `remove_pid()` wraps `unlink(missing_ok=True)` in `contextlib.suppress(OSError)`.
- **Background daemon zombie process:** The parent CLI process does not call `proc.wait()` after `Popen`. With `start_new_session=True` and `stdout/stderr=DEVNULL`, the child is immediately reparented to init (PID 1) when the parent exits. No zombie accumulation.
- **`SessionDB.check_same_thread=False` thread safety:** `session_db.py:115` opens with `check_same_thread=False`, but all `SessionDB` access occurs on the single-threaded asyncio event loop (no `asyncio.to_thread` calls on DB methods). Concurrent access is impossible. Annotation is a correctness aid, not a safety risk.
- **No auto-send path in comms agents:** All six comms commands (`revision`, `cover-letter`, `email`, `abstract`, `grant`, `rebuttal`) write output to files only. `_print_comms_result` at line 195 calls `output_path.write_text(text)` and prints to console. No network transmission. Confirmed.
- **CLI command registration completeness:** `register()` at line 61 correctly wires `comms_app`, `gateway_app`, `present_app`, `write_command`, and `hypotheses_command`. All are called from `cli.py:1625`. No missing commands.
- **`hypotheses_command` unguarded import:** `maglab.core.reasoning` is a core module; `D1HypothesisEngine` is defined in `reasoning.py`. No `ImportError` guard needed.
- **`gateway_install` TOCTOU on config permissions:** CLI checks permissions at lines 819–826, then `install_service()` checks again at `runner.py:503`. Double-check is benign; permissions can only change via the user's own action between calls. Not a security issue.
- **`gateway_install` service file overwrite:** `target.write_text()` overwrites an existing service file silently. This is intentional reinstall behavior.
- **`instr_search_manual` annotation (`write_op`):** Confirmed `annotations=write_op` at `mcp_server.py:656`. Correct.
- **All six write-op tools annotated correctly:** `figure_render` (507), `figure_export` (571), `instr_search_manual` (656), `instr_ingest_manual` (700), `instr_generate_skill` (757), `instr_scaffold` (807) all carry `annotations=write_op`. Ten read-only tools carry `annotations=read_only`. Only `sim_run` (F1) is misannotated.
- **`gateway_setup` config file permissions:** Newly created config gets `os.chmod(cfg, 0o600)` at line 633. Correct.
- **`ServiceDB.get_or_create_session` double-hashing:** Accepts pre-hashed `user_id_hash` from `UnifiedMessage`; does not re-hash internally. No double-hashing.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | MEDIUM | `mcp_server.py:379` | `sim_run` carries `annotations=read_only` but writes `.mx3`/`.mif` temp files unconditionally via `generate_mx3_file()` / `generate_mif_file()` — violates `readOnlyHint=True` MCP contract |
