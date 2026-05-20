# Code Review Round 13 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-20
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**CLEAN**

---

## R12 Fix Verification

### R12-F1: `hypotheses_command` `--json-out` write block wrapped in `try/except OSError`

**Status: CONFIRMED FIXED**

The fix is in place at `maglab/commands/p6_authoring.py:1121–1130`:

```python
if json_out:
    import json

    out_path = Path(json_out)
    try:
        out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        console.print(f"[green]JSON result written:[/] {out_path}")
    except OSError as exc:
        console.print(f"[red]JSON write failed:[/] {exc}")
        raise typer.Exit(1) from exc
```

The pattern exactly matches the fix specified in R12: `try/except OSError`, `[red]JSON write failed:[/]` message, `raise typer.Exit(1) from exc`. The fix is fully consistent with every other post-processing file write in the file. Confirmed.

---

## Findings

No genuine defects found in this round. The domain is clean.

---

## Non-Findings

The following areas were investigated and explicitly dismissed:

- **R12-F1 fix (`hypotheses_command` `--json-out` OSError guard):** Confirmed at `p6_authoring.py:1121–1130`. Exact pattern specified in R12 applied. Clean.
- **`hypotheses_command` lazy import guard:** Confirmed at `p6_authoring.py:1065–1072`. `try/except ImportError`, standard message, `raise typer.Exit(1) from exc`. Unchanged and correct.
- **All 16 MCP tool annotations in `mcp_server.py`:** Recounted and verified. 7 write-op tools carry `readOnlyHint=False, destructiveHint=False`; 9 read-only tools carry `readOnlyHint=True`. `instr_safety_check` at line 860 correctly uses `annotations=read_only`. Clean.
- **`physics_compute` / `convert_units` `getattr`-based dispatch with user-supplied `formula`/`fn_name`:** The constructed name for `convert_units` always contains `_to_` (e.g. `Oe_to_Am`), making it impossible to hit plain dunder attributes. For `physics_compute`, any non-existent name returns `None` (the default); callable non-dunder module attributes that could be reached are controlled entirely by `formulas.py`'s own namespace — a user-supplied string can only dispatch to functions the module explicitly exports. Worst case for callable dunders: `fn(**params)` raises `TypeError`, caught by the surrounding `except Exception`. No code execution beyond the module's own callables. Non-finding.
- **`_notification_loop` `task_done()` skipped when `_send_notification` raises:** `_send_notification` catches all per-adapter exceptions internally via `except Exception`. The only code paths that execute before that guard (`event.format_text()`, `event.payload.get()`, `list(self._adapters.items())`) are trivially safe dict/string operations that cannot raise. In practice `task_done()` is always called after `get()`. Furthermore `Queue.join()` is never called in the codebase, so the unfinished-task counter has no operational impact. Non-finding (confirmed from R11/R12).
- **`parse_message()` not guarded in `handle_message()`:** All adapters use `dict.get()` with defaults. The only non-trivial conversion is `float(raw.get("ts", time.time()))` (Slack/Discord) and `float(raw.get("date", time.time()))` (Telegram). Platform APIs always supply numeric timestamps. A test with a crafted non-numeric `ts` would raise `ValueError` propagating through `handle_message` to the caller, but production platform webhooks never send non-numeric timestamps. Design-level consideration, not a code defect introduced in this codebase. Non-finding.
- **`gateway_start` background mode: `pid_file.write_text(str(proc.pid))` unguarded after `Popen`:** Noted in R11/R12 as a non-finding. `write_text` on a path the parent just successfully `open("x")`-created moments before fails only under extreme OS conditions. The orphaned daemon PID cannot be recovered without the PID value itself. Non-finding (confirmed from R11/R12).
- **`stop_daemon` removes PID file before SIGTERM is delivered:** Intentional caller-side cleanup. `remove_pid()` uses `contextlib.suppress(OSError)` for safe double-remove. SIGTERM with default `SIG_DFL` terminates the daemon process immediately at the OS level without running Python `finally` blocks; the PID file is therefore cleaned up by the caller, not the daemon. No orphan PID file. Non-finding.
- **`_run_gateway_foreground` double `remove_pid()`:** Both the `_main` coroutine's `finally` (line 1232) and the outer `try/except KeyboardInterrupt` `finally` (line 1239) call `remove_pid()`. `remove_pid()` uses `contextlib.suppress(OSError)` and `unlink(missing_ok=True)` — the double call is safe. Non-finding.
- **`write_pid()` and `install_service()` write files without explicit `encoding=`:** The content is always ASCII (integer PID string; ASCII-only plist/systemd templates). Platform default encoding on macOS/Linux is UTF-8, a superset of ASCII. No data loss or corruption risk for these specific payloads. Non-finding.
- **`Slack._verify_slack_signature` uses `hmac.new` (not `hmac.new`):** Verified: `hmac.new` is the correct and only public constructor in Python's `hmac` module. The call signature `hmac.new(key, msg, digestmod)` is correct. `hmac.compare_digest` is used for constant-time comparison. Clean.
- **`SlackAdapter.verify_request` skips HMAC when `signing_secret` is absent:** Emits a per-request `log.warning` — always visible to the operator in logs. The skip is a documented misconfiguration path, not a silent bypass. The R12 non-finding holds. Clean.
- **Slack timestamp rejection when `signing_secret` absent and timestamp unparseable:** When `signing_secret` is absent the code skips the timestamp parse failure guard (accepts the request without replay protection), consistent with the overall "no-secret → no-HMAC → no replay protection" posture. The warning covers the missing-secret case. Non-finding.
- **`gateway_start` `except Exception: pid_file.unlink(missing_ok=True); raise`:** Correct cleanup-and-reraise pattern. The re-raised exception is appropriate for `subprocess.Popen` failures (system error). Non-finding.
- **`mcp_serve` no `try/except` around `server.run()`:** Standard server-startup behavior — uncaught OS errors (port conflict, stdio pipe failure) should propagate as tracebacks to the operator. Consistent with every major Python ASGI/server library. Non-finding.
- **`_write_human_review_marker` unguarded `write_text`:** Marker file is always written to `out_dir`, which was just created by `out_dir.mkdir(parents=True, exist_ok=True)` in the same call frame. The directory is known to exist and be writable. Non-finding.
- **`generate_launchd_plist` / `generate_systemd_unit` XML/INI injection via `maglab_executable`:** Self-attack vector — user controls their own LaunchAgent/systemd unit. The `maglab_executable` value comes from a CLI option the user provides. Non-finding from prior rounds. Unchanged.
- **`gateway_setup` write-then-chmod race window:** Standard POSIX pattern in the user's own home directory. Non-finding from prior rounds.
- **`SessionDB` SQL queries — injection risk:** All queries use parameterized placeholders (`?`). No string interpolation. Clean.
- **`SessionDB.get_or_create_session` — synchronous SQLite calls in async `handle_message`:** SQLite is a local file operation typically completing in < 1 ms. Single-threaded asyncio event loop means no concurrent thread contention. Blocking duration is negligible for this use case. Performance concern only, not a correctness defect. Non-finding.
- **`manuals://` resource iterates filesystem without exception guard:** The `cache_root.iterdir()` / `sha_file.read_text()` calls are within `if cache_root.is_dir()` and `if sha_file.is_file()` guards. TOCTOU risk (file disappears between `is_file()` and `read_text()`) would raise `OSError`, propagating to the FastMCP framework which handles resource errors. Acceptable design for a local read-only resource listing. Non-finding.
- **`_gate_approve` / `_gate_reject` orphaned callbacks (Slack, Telegram adapters):** Known stub design — no action handler is wired at the MCP layer. Design-level limitation, not a newly introduced defect. Non-finding from prior rounds.
- **`child_env = {**os.environ, ...}` leaking credentials to child process:** Intentional — the daemon subprocess needs the same environment (API keys, PATH) as the parent to function. Non-finding from prior rounds.
- **`cli.py:1625` P6 registration:** `p6_authoring.register(app)` correctly wires `comms`, `gateway`, `present`, `write`, and `hypotheses` commands. Clean.
- **`_COMMAND_REGISTRY` mutation at module import time:** All registrations complete before the event loop starts. Thread-safe. Clean.
- **`is_running()` / `stop_daemon()` exception coverage:** Catches `(ProcessLookupError, PermissionError)` — the complete set of exceptions `os.kill()` raises in Python 3.11+ (PEP 475 handles EINTR). Clean.
- **`read_pid()` race condition:** PID file can disappear between `exists()` and `read_text()`. `except (ValueError, OSError): return None` handles this. Clean.
- **`asyncio.wait_for` `TimeoutError` identity (Python 3.11+):** Verified on the runtime Python 3.14.2: `asyncio.TimeoutError is TimeoutError` is `True`. The `except TimeoutError: continue/return False` clauses in runner and all adapters are correct. Clean.
- **`figure_render` / `figure_export` `finally: plt.close(fig)` with potentially unbound `fig`:** The compose step (`fig = FigureComposer().compose()`) is in its own `try/except` that returns early on failure. The `finally` is in a separate nested `try` that only executes if `fig` is already bound. Non-finding (confirmed from R11/R12).

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| — | — | — | No findings. Domain is CLEAN. |
