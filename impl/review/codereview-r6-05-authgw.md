# Code Review Round 6 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-19
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**ISSUES FOUND** — 2 findings (1 HIGH, 1 MEDIUM)

---

## R5 Fix Verification

All three R5 fixes are confirmed in place:

### R5-F1: `_WRITE_ANNOTATIONS` on file-writing MCP tools
`mcp_server.py` lines 83–88 define:
```python
_READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True)
_WRITE_ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
```
The five originally-flagged write-capable tools now correctly carry `annotations=write_op`:
- `figure_render` → line 507: `annotations=write_op` ✓
- `figure_export` → line 571: `annotations=write_op` ✓
- `instr_ingest_manual` → line 700: `annotations=write_op` ✓
- `instr_generate_skill` → line 757: `annotations=write_op` ✓
- `instr_scaffold` → line 807: `annotations=write_op` ✓

The module-level docstring (lines 34–37) also documents the invariant. Confirmed clean.

### R5-F2: Foreground PID claim atomic guard
`p6_authoring.py` lines 663–676 now apply the same `pid_file.open("x")` exclusive-create guard before calling `_run_gateway_foreground()`:
```python
pid_file = _pid_path()
try:
    fd = pid_file.open("x")  # atomic create — fails if file already exists
    fd.close()
except FileExistsError:
    console.print("[yellow]Gateway is already starting or running.[/] ...")
    return
```
The fix is present — however, see **F1** below for a newly identified logic error this fix introduced in the background startup path.

### R5-F3: `_AI_DISCLOSURE` on critic-revised section drafts
`loop_c.py` line 259:
```python
revised_tex_with_header = HUMAN_REVIEW_MARKER + revised_tex + _AI_DISCLOSURE
```
`_AI_DISCLOSURE` is imported at line 37 and correctly appended. Confirmed clean.

---

## Findings

### F1 — HIGH | `maglab/commands/p6_authoring.py:670,697` | Background-mode gateway startup never runs the event loop

**Defect:**

Background `gateway start` (the default mode) forks a subprocess using:
```python
proc = subprocess.Popen(
    [maglab_exe, "-m", "maglab", "gateway", "start", "--foreground"],
    ...
)
```
(line 696–701). The parent then records `proc.pid` in the PID file (line 709).

The subprocess re-enters `gateway_start()` with `foreground=True`. It then tries the atomic PID claim (line 670):
```python
fd = pid_file.open("x")   # atomic create — fails if file already exists
```
**The parent process already created this file at line 688.** The child therefore hits `FileExistsError`, prints the "already starting or running" message, and **returns immediately without starting the gateway event loop**.

Result:
- The parent prints "Gateway started (PID=N)" and exits.
- The child exits without running the gateway.
- `gateway status` shows the PID as running (the OS reuses the PID slot slowly), but no messages are ever handled.
- `gateway stop` sends SIGTERM to PID N which by that point may already be dead or reused.

**This means background-mode daemon start is completely broken.** Only `gateway start --foreground` (invoked directly by the user) works correctly because the user's terminal is the one that creates the PID file.

**Impact:** HIGH — The primary (default) mode for running the messaging gateway daemon produces a zombie PID entry with no running event loop. All gateway message routing is unavailable in background mode.

**Fix:** The subprocess spawned by background mode must NOT go through the atomic PID claim logic. Two clean options:

Option A — Add a `--skip-pid-claim` internal flag for the subprocess:
```python
proc = subprocess.Popen(
    [maglab_exe, "-m", "maglab", "gateway", "start",
     "--foreground", "--skip-pid-claim"],
    ...
)
```
Then guard the atomic-claim block with `if not skip_pid_claim`.

Option B (simpler) — Move the foreground event-loop logic into a separate internal entry point that background mode calls directly, bypassing `gateway_start()` entirely:
```python
proc = subprocess.Popen(
    [maglab_exe, "-m", "maglab", "gateway", "_run_daemon"],
    ...
)
```
Where `_run_daemon` is a hidden typer command that calls `_run_gateway_foreground()` without the PID claim check.

Option C — Have the background parent delete the PID file **before** spawning the subprocess, and let the foreground subprocess claim it normally:
```python
# Parent claims file, writes placeholder, then removes it so child can claim
pid_file.unlink(missing_ok=True)  # give child a fresh claim
proc = subprocess.Popen(...)
```
(This is less safe for the race window but simpler than option A/B.)

---

### F2 — MEDIUM | `maglab/mcp_server.py:656` | `instr_search_manual` carries `readOnlyHint=True` but downloads and writes files to disk

**Defect:**

The R5 review explicitly listed `instr_search_manual` as a tool that "correctly carries `readOnlyHint=True`". However, inspection of the underlying `ManualSearcher.search_and_download()` (called at `mcp_server.py:675`) reveals that it **writes files to disk**:

1. `cache_dir.mkdir(parents=True, exist_ok=True)` — creates the cache directory.
2. `dest.write_bytes(content)` (`manual_search.py:341`) — writes the downloaded PDF to `~/.local/share/maglab/manuals/<mfr>/<model>/<model>_manual.pdf`.
3. `checksum_file.write_text(sha256 + "\n")` (`manual_search.py:345`) — writes a `sha256.txt` checksum file.

The tool description itself explicitly states: "Search the web for an instrument manual PDF and **download it to the local cache**."

Per the MCP specification, `readOnlyHint=True` means "the tool does not modify its environment." Writing a PDF and checksum to the local filesystem is a clear environment modification.

The R5 fix applied `write_op` correctly to the other five file-writing tools but missed this sixth one, because its name ("search") implies read-only semantics. The description and implementation both confirm it writes files.

**Impact:** MEDIUM — MCP clients that rely on `readOnlyHint` for sandboxing or permission decisions (e.g., "approve only read-only tools automatically") will incorrectly auto-approve `instr_search_manual` without user confirmation, even though it modifies the filesystem.

**Fix:** In `_register_instrument_tools`, change the annotation for `instr_search_manual` from `read_only` to `write_op`:
```python
@mcp.tool(
    name="instr_search_manual",
    description=(...),
    annotations=write_op,   # <-- was read_only
)
```

---

## Non-Findings

The following areas were investigated and found to be clean:

- **`loop_c.py` success flag logic** (lines 356–358): `success` correctly ORs `DONE_SIGNAL` with a full `section_drafts` completion check. Vacuously correct even when `state` is None.
- **`session_db.py` double-hashing risk**: `get_or_create_session` receives an already-hashed `user_id_hash` from `UnifiedMessage`. The internal `_hash_user_id` helper is defined but never called from `get_or_create_session`. No double-hashing occurs.
- **Slack HMAC `hmac.new` correctness**: `hmac.new(key, msg, digestmod)` is the correct Python `hmac` module API (not `hmac.HMAC`). Confirmed via runtime check.
- **Slack replay-attack window**: Timestamp rejection (>300s) correctly gates before signature check. Missing timestamp with a configured secret is rejected, not silently accepted.
- **`poster_drafter.py` vault soft-failure**: The poster drafter logs a warning and leaves `{{dp:KEY}}` in the SVG when vault keys are missing, rather than raising `AuthoringBlockedError`. This is an intentional design relaxation for presentation materials (as opposed to the journal authoring pipeline), not a gate bypass.
- **`_write_output_files` idempotency**: The `main.tex` is only written if it doesn't already exist (line 428 check). No overwrite of a correctly compiled document.
- **CLI command registration**: All comms (`revision`, `cover-letter`, `email`, `abstract`, `grant`, `rebuttal`), gateway (`setup`, `start`, `stop`, `status`, `install`), present (`slides`, `poster`), `write`, and `hypotheses` commands are correctly registered via `register()` and `app.add_typer()`.
- **`sim_run` annotation** (`read_only`): `run_sim_overlay` returns DataPoints in memory; it does not write simulation output files. The annotation is correct.
- **`sim_parse` annotation** (`read_only`): It only reads an existing file; it does not write anything. Annotation is correct.
- **`instr_search_manual` manufacturer guessing**: `_guess_manufacturer` is only called after the user provides a model name; the model name is explicitly documented as user-confirmed. No guessing of model identity.
- **`_run_gateway_foreground` PID cleanup**: `remove_pid()` is called in both the `asyncio.CancelledError` path (line 1178 inside `_main.finally`) and the outer `finally` block (line 1185). The outer `finally` ensures cleanup even if `asyncio.run()` throws unexpectedly.
- **No auto-send path**: All six comms agents and all CLI commands write output to files only. Confirmed no subprocess or API call sends content automatically.
- **`DataVault.inject_into_draft` gate on critic revisions**: The revised draft is re-run through `vault.inject_into_draft` (loop_c.py:264), so vault blocking applies to critic-revised drafts too.
- **`check_credential_permissions` security**: Correctly enforces `stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH` and is a no-op on Windows only (intentional).
- **`gateway_setup` permission check**: The config template is written with `os.chmod(cfg, 0o600)` immediately after creation. Pre-existing files with wrong permissions generate a warning, not a silent pass.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | HIGH | `p6_authoring.py:670,697` | Background gateway start spawns a foreground subprocess that immediately exits due to atomic PID claim collision — event loop never starts |
| F2 | MEDIUM | `mcp_server.py:656` | `instr_search_manual` annotated `readOnlyHint=True` but downloads and writes PDF + checksum to local cache — R5 reviewer error |
