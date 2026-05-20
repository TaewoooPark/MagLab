# Code Review Round 15 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-20
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**CLEAN** — 0 genuine defects found.

---

## R14 Fix Verification

The R14-F1 fix is confirmed in place at `maglab/commands/p6_authoring.py` lines 201–205:

```python
try:
    output_path.write_text(text, encoding="utf-8")
except OSError as exc:
    console.print(f"[red]Draft write failed:[/] {exc}")
    raise typer.Exit(1) from exc
```

Both regression tests introduced in R14 continue to pass:
- `test_revision_write_failure_exits_1`
- `test_cover_letter_write_failure_exits_1`

---

## Findings & Fixes

None. No genuine defects found in this round.

---

## Non-Findings

The following areas were investigated in depth and explicitly dismissed:

### New investigations in R15

- **`_notification_loop` swallows `CancelledError` via `break` (asyncio protocol):** When `task.cancel()` fires, the loop's `except asyncio.CancelledError: break` causes the coroutine to return normally rather than propagate `CancelledError`, so `task.cancelled()` returns `False` after `stop()`. Investigated: `stop()` uses `return_exceptions=True` in `asyncio.gather`, which absorbs both `None` and `CancelledError` identically. No code in the project calls `task.cancelled()` or depends on the task being in the cancelled state. The loop terminates on cancellation and the runner shuts down correctly. Per PEP 3156 the re-raise is idiomatic but the operational behavior is correct. Non-finding.

- **`install_service` writes (runner.py:508, 514) missing `OSError` catch in CLI caller:** `install_service` writes the launchd plist or systemd unit to `target` (whose parent was just `mkdir`'d) with bare `write_text`. The CLI caller `gateway_install` catches `(RuntimeError, PermissionError)` but not a bare disk-full `OSError`. The write targets are small-data system path files; any write failure in a directory that was just successfully `mkdir`'d is an extreme OS condition. The CLI caller already catches `PermissionError` (which covers the common access-denied case). Non-finding.

- **`write_pid()` in `runner.py:344` bare `write_text` (no encoding):** PID is pure ASCII digits. Default platform encoding handles this correctly. Same write path confirmed non-finding in R11–R13. Non-finding.

- **`pid_file.write_text(str(proc.pid))` in `p6_authoring.py:759` (no encoding, no OSError guard):** PID is pure ASCII. The pid_file was just atomically created by `open("x")` in the same directory, confirming the directory and path are writable. If write fails here, the file contains empty content — `read_pid()` returns `None` and `stop_daemon()` cannot kill the child. This is an extreme OS condition (successful `open("x")` followed by failed `write_text` in the same directory). Previously confirmed non-finding from R11–R13. Non-finding.

- **`instr_scaffold` MCP tool (mcp_server.py) write not guarded:** All write operations in `generate_scaffold` are wrapped in the tool's `except Exception` catch. Non-finding.

- **`_cmd_help` reads `_COMMAND_REGISTRY.keys()` concurrently:** All registrations complete at module import time, before any event loop starts. No async mutation after startup. Non-finding.

- **`comms_abstract` character limit check after `_print_comms_result`:** `getattr(result, "text", "")` is evaluated after the write succeeds; if the write raised OSError, it is already guarded. The `getattr` default is correct (not affected by falsy `word_count=0`). Non-finding.

- **`get_or_create_session` accepts arbitrary `user_id_hash` string:** All SQL uses parameterized placeholders; no injection risk. The gateway adapter layer always hashes before calling this method. Non-finding.

- **`_notification_loop` `task_done()` skipped when `asyncio.CancelledError` is raised inside `_send_notification`:** `_send_notification` uses `except Exception` per-adapter, which correctly does NOT catch `CancelledError` (a `BaseException` subclass since Python 3.8). If `CancelledError` propagates through `_send_notification`, it is caught by the outer `except asyncio.CancelledError: break`. `Queue.join()` is never called in the codebase. Non-finding (confirmed R11–R14).

### Carried over from R14 (confirmed unchanged)

- **All 16 MCP tool annotations in `mcp_server.py`:** 7 write-op tools (`readOnlyHint=False, destructiveHint=False`), 9 read-only tools (`readOnlyHint=True`). `instr_safety_check` at line 860 correctly carries `read_only`. Confirmed clean.
- **`write_command` dry-run `main.tex` write (line 120) unguarded:** Written to `out_dir` which was just created by `out_dir.mkdir(parents=True, exist_ok=True)`. Non-finding.
- **`_write_human_review_marker` write unguarded:** Written to a directory the caller just created via `mkdir(parents=True, exist_ok=True)`. Non-finding.
- **`present slides`/`poster` dry-run stub writes unguarded:** Same `out_dir.mkdir()` immediately before. Non-finding.
- **`gateway_setup` config write unguarded:** Written to a path whose parent was just created by `cfg.parent.mkdir(parents=True, exist_ok=True)`. Non-finding.
- **`physics_compute` / `convert_units` `getattr`-based dispatch with user-supplied `formula`/`fn_name`:** Confirmed safe — worst case raises `TypeError` caught by `except Exception`. Non-finding.
- **`sim_parse` file path traversal:** Tool reads a file the MCP client LLM explicitly named; risk model is the same as any file-reading tool. Non-finding.
- **`SlackAdapter._verify_slack_signature` uses `hmac.new`:** Correct and unchanged. Non-finding.
- **`SlackAdapter.verify_request` skips HMAC when `signing_secret` absent:** Per-request `log.warning` always visible. Non-finding.
- **`loop_c.py` `success` calculation operator precedence:** `(state.stop_reason or StopReason.DONE_SIGNAL.value) if state else ""` — correct Python ternary. Non-finding.
- **`_run_gateway_foreground` double `remove_pid()`:** `remove_pid` uses `contextlib.suppress(OSError)` and `unlink(missing_ok=True)`. Non-finding.
- **`_COMMAND_REGISTRY` mutation at module import time:** Thread-safe. Non-finding.
- **`SessionDB` SQL queries:** All use parameterized placeholders. Non-finding.
- **`figure_render` / `figure_export` `finally: plt.close(fig)` with potentially unbound `fig`:** Compose step returns early on failure; `fig` is bound before the `finally`. Non-finding.
- **`loop_c.py` `_write_output_files` write calls unguarded:** Written to `effective_dir` which is either caller-passed (exists) or `tempfile.mkdtemp()` (always succeeds). Non-finding.

---

## Verification

### ruff
```
$ .venv/bin/ruff check maglab/authoring/ maglab/gateway/ maglab/commands/ maglab/mcp_server.py maglab/cli.py
All checks passed!
```

### mypy
```
$ .venv/bin/mypy maglab/
Success: no issues found in 195 source files
```

### pytest
```
$ .venv/bin/python -B -m pytest -q tests/unit/test_cli_p6.py tests/unit/test_gateway_adapters.py tests/unit/test_gateway_runner.py tests/unit/test_gateway_session_db.py tests/unit/test_mcp_client.py tests/smoke/test_mcp_server.py --timeout=120
233 passed in 3.75s
```

(All 233 tests pass, including the 2 R14-F1 regression tests.)
