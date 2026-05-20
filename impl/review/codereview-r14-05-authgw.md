# Code Review Round 14 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-20
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**FIXED** — 1 defect found and patched.

---

## Findings & Fixes

### R14-F1 — MEDIUM — `maglab/commands/p6_authoring.py:201` — `_print_comms_result` write unguarded

**Severity:** MEDIUM

**File:Line:** `maglab/commands/p6_authoring.py:201`

**Defect:**  
`_print_comms_result` wrote the draft text to `output_path` with a bare
`output_path.write_text(text, encoding="utf-8")` — no `try/except OSError`
guard.  This helper is the sole write-to-disk path for all six comms
subcommands (`comms revision`, `comms cover-letter`, `comms email`,
`comms abstract`, `comms grant`, `comms rebuttal`).

When `output_path` is unwritable (user-supplied `--output` pointing to a
non-existent parent directory, a read-only filesystem, or a permission-denied
location), the resulting `OSError`/`FileNotFoundError` propagated as a raw
Python traceback through all six callers instead of producing a user-friendly
`[red]Draft write failed:[/]` message and `typer.Exit(1)`.

This is the exact same defect class fixed by R12-F1 for the
`hypotheses_command` `--json-out` write block.  The pattern was applied
consistently everywhere else in the file but was missed in the shared helper.

**Fix applied:**

```python
# before
output_path.write_text(text, encoding="utf-8")

# after
try:
    output_path.write_text(text, encoding="utf-8")
except OSError as exc:
    console.print(f"[red]Draft write failed:[/] {exc}")
    raise typer.Exit(1) from exc
```

**Regression tests added:**
- `tests/unit/test_cli_p6.py::TestCommsWriteFailure::test_revision_write_failure_exits_1`
  — verifies `comms revision` exits 1 with `"Draft write failed"` when the
  output parent directory does not exist (FileNotFoundError ⊂ OSError).
- `tests/unit/test_cli_p6.py::TestCommsWriteFailure::test_cover_letter_write_failure_exits_1`
  — same guard verified for `comms cover-letter`.

---

## Non-Findings

The following areas were investigated and explicitly dismissed:

- **All 16 MCP tool annotations in `mcp_server.py`:** Counts unchanged from R13. 7 write-op tools (`readOnlyHint=False, destructiveHint=False`), 9 read-only tools (`readOnlyHint=True`). `instr_safety_check` at line 860 correctly carries `read_only`. Confirmed clean.
- **`_notification_loop` `task_done()` skipped when `asyncio.CancelledError` is raised inside `_send_notification`:** `_send_notification` catches all per-adapter exceptions via `except Exception`. The only code paths that execute before that guard are trivially safe. Additionally, `Queue.join()` is never called in the codebase so the unfinished-task counter has no operational impact. Non-finding (confirmed R11–R13).
- **`_print_comms_result` write — existing comms tests already guard against write failures:** The existing tests only invoke the comms commands with valid `tmp_path` destinations, so they did not catch the unguarded write. The regression tests (R14-F1) exercise the failure path explicitly.
- **`write_command` dry-run `main.tex` write (line 120) unguarded:** Written to `out_dir` which was just created by `out_dir.mkdir(parents=True, exist_ok=True)` in the same call frame. Directory is known to exist and be writable. Non-finding (confirmed R13).
- **`_write_human_review_marker` write unguarded (line 1141):** Also written to a directory the caller just created via `mkdir(parents=True, exist_ok=True)`. Non-finding (confirmed R13).
- **`present slides`/`poster` dry-run stub writes (lines 883, 986) unguarded:** Same `out_dir.mkdir()` immediately before. Non-finding.
- **`gateway_setup` config write (line 632) unguarded:** Written to a path whose parent was just created by `cfg.parent.mkdir(parents=True, exist_ok=True)`. Non-finding.
- **`pid_file.write_text(str(proc.pid))` (line 755) unguarded:** Non-finding from R11–R13; path was atomically created by `open("x")` in the same frame; any write failure here is an extreme OS-level error that should propagate.
- **`physics_compute` / `convert_units` `getattr`-based dispatch with user-supplied `formula`/`fn_name`:** Confirmed safe — user-supplied string can only dispatch to functions the module explicitly exports; worst case raises `TypeError` caught by `except Exception`. Non-finding (R13).
- **`sim_parse` file path traversal (user-supplied `file_path`):** The tool resolves `Path(file_path)` and checks `fp.exists()`. A path traversal like `../../etc/passwd` would succeed the existence check and attempt to parse it as mumax3/oommf output — which would fail safely with a parse error returned as `{"ok": False, "error": "..."}`. The tool reads a file that the MCP client's LLM has explicitly named; the risk model is the same as any file-reading tool. Non-finding.
- **`SlackAdapter._verify_slack_signature` uses `hmac.new`:** Confirmed correct and unchanged from R13. Non-finding.
- **`SlackAdapter.verify_request` skips HMAC when `signing_secret` absent:** Per-request `log.warning` always visible. Non-finding (R13).
- **`loop_c.py` `success` calculation with `state.stop_reason`:** The operator-precedence of `state.stop_reason or StopReason.DONE_SIGNAL.value if state else ""` is `(state.stop_reason or StopReason.DONE_SIGNAL.value) if state else ""` — correct Python ternary. Non-finding.
- **`_run_gateway_foreground` double `remove_pid()`:** Both `_main` coroutine `finally` and outer `except KeyboardInterrupt` `finally` call `remove_pid()`. `remove_pid` uses `contextlib.suppress(OSError)` and `unlink(missing_ok=True)`. Double call is safe. Non-finding (R13).
- **`_COMMAND_REGISTRY` mutation at module import time:** All registrations complete before event loop starts. Thread-safe. Non-finding (R13).
- **`SessionDB` SQL queries:** All use parameterized placeholders (`?`). No string interpolation. Non-finding (R13).
- **`figure_render` / `figure_export` `finally: plt.close(fig)` with potentially unbound `fig`:** Compose step is in its own `try/except` that returns early on failure. The `finally` is in a separate nested `try` that only executes when `fig` is bound. Non-finding (R13).
- **`loop_c.py` `_write_output_files` write calls unguarded:** Written to `effective_dir` which was either passed in by the caller (already exists) or created by `tempfile.mkdtemp` (always succeeds). Non-finding.

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
$ .venv/bin/python -B -m pytest -v tests/unit/test_cli_p6.py tests/unit/test_gateway_adapters.py tests/unit/test_gateway_runner.py tests/unit/test_gateway_session_db.py tests/unit/test_mcp_client.py tests/smoke/test_mcp_server.py --timeout=120
233 passed in 3.70s
```

(231 tests passed before the fix; 2 new regression tests added for R14-F1.)
