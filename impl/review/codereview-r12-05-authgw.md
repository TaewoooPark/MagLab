# Code Review Round 12 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-20
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**ISSUES FOUND** — 1 finding (1 LOW)

---

## R11 Fix Verification

### R11-F1: `hypotheses_command` wraps lazy `maglab.core.reasoning` import in `try/except ImportError`

**Status: CONFIRMED FIXED**

The fix is in place at `maglab/commands/p6_authoring.py:1065–1072`:

```python
try:
    from maglab.core.reasoning import (
        D1HypothesisEngine,
        HypothesisResult,
    )
except ImportError as exc:
    console.print(f"[red]Missing dependency:[/] {exc}")
    raise typer.Exit(1) from exc
```

The pattern is now fully consistent with every other lazy import in the file: `try/except ImportError`, standard `[red]Missing dependency:[/]` message, `raise typer.Exit(1) from exc`. Confirmed.

---

## Findings

### F1 — LOW | `maglab/commands/p6_authoring.py:1121–1126` | `hypotheses_command`: unguarded file write for `--json-out` path

**Defect:**

The optional JSON output block (lines 1121–1126) writes to `out_path` without any exception handling:

```python
if json_out:
    import json

    out_path = Path(json_out)
    out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    console.print(f"[green]JSON result written:[/] {out_path}")
```

This block executes after the main `try/except Exception` guard (lines 1077–1085) has already exited. If `out_path.write_text(...)` raises (e.g. `PermissionError` on a read-only path, `FileNotFoundError` when the parent directory does not exist, `OSError` on disk-full), the exception propagates as a raw Python traceback directly to the user.

Every other post-processing file write in the file is either inside a `try/except Exception` or writes to a path that was explicitly `mkdir(parents=True, exist_ok=True)` earlier (e.g. `_write_human_review_marker`, `out_dir`-based writes in `present_slides`/`present_poster`). The `--json-out` path is a raw user-supplied string with no parent-directory guarantee.

**Distinguishing from non-finding candidates:**

- This is distinct from the unguarded `_print_comms_result.write_text` (line 201): comms output paths default to simple filenames in CWD (always writable if the CWD itself is writable); the comms CLI also does not expose an arbitrary file path option — the `--output` value goes directly to `Path(output)` in CWD. Same risk profile as the module docstring contract for "credentials/dependency" does not explicitly extend to I/O errors.
- However, `--json-out` specifically exists to write to an arbitrary user-supplied path (including `/read-only/dir/result.json` or `no-such-dir/result.json`), making the failure more likely and user-visible. The hypothesis cards are already printed to console before the `json_out` block executes, so a write failure means the user sees successful output and then an unformatted traceback — more confusing than a clean exit-code 1.
- The module docstring's contract ("Missing dependency / credentials → clear message + raise typer.Exit(1)") does not explicitly cover file I/O failures. Severity is LOW because (a) the hypothesis results are already displayed on stdout before the write, so no data is lost, and (b) the traceback itself is readable and reveals the path and error.

**Impact:** LOW — User sees a raw `PermissionError` / `FileNotFoundError` / `OSError` traceback when `--json-out` points to an unwritable or non-existent path, instead of a clean `[red]JSON write failed:[/]` message. Hypothesis cards are already displayed; no data is lost. Severity matches R11-F1 pattern (inconsistency, not an active data-loss risk).

**Fix:**

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

---

## Non-Findings

The following areas were investigated and dismissed:

- **R11-F1 fix (`hypotheses_command` lazy import):** Confirmed at `p6_authoring.py:1065–1072`. Fully consistent with every other guarded import in the file. Clean.
- **`hypotheses_command` engine/result exception handling:** `engine.run()` at line 1079 is wrapped in `try/except Exception` (lines 1077–1085). All runtime failures are caught and formatted cleanly. Clean.
- **`_print_comms_result.write_text` (line 201) — unguarded write:** All comms callers pass either a user-supplied `--output` value or a default filename in CWD. The module docstring contract ("Missing dependency / credentials → clear message") does not extend to general file I/O errors, and the failure mode (readable `OSError` traceback) is distinguishable from a hidden/silent failure. Explicitly distinguished from F1 above: comms paths are simpler and less likely to fail than arbitrary `--json-out` paths. Non-finding.
- **`_notification_loop` `task_done()` not called after exception from `_send_notification`:** `_send_notification` catches all per-adapter exceptions internally. The only code paths that escape to the outer `except Exception` are `event.format_text()` (trivially safe dict/str operation) and `list(self._adapters.items())` (dict iteration, safe). Practically impossible to miss `task_done()`. Furthermore `Queue.join()` is never called anywhere in the module — the unfinished-task counter has no operational impact. Non-finding (confirmed from R11).
- **`gateway_start` background mode PID file orphan if `write_text` fails after `Popen`:** `pid_file.write_text(str(proc.pid))` at line 755 is unguarded. However, `write_text` on a path the user successfully `open("x")`-created moments before fails only under extreme conditions (disk full, permissions revoked between open and write). Orphaned daemon PID cannot be cleaned up without the PID itself. Non-finding (confirmed from R11).
- **`stop_daemon` removes PID file before daemon exits:** Intentional Unix SIGTERM semantics — the daemon's `finally: remove_pid()` provides a safe double-remove via `contextlib.suppress(OSError)`. Non-finding from prior rounds.
- **`_gate_approve` / `_gate_reject` orphaned callbacks (Slack, Telegram adapters):** Known stub design — no action handler is wired at the MCP layer. Design-level limitation, not a newly introduced defect. Non-finding from prior rounds.
- **`generate_launchd_plist` XML injection via `maglab_executable`:** Self-attack vector (user controls own LaunchAgent). Non-finding from prior rounds. Unchanged.
- **`gateway_setup` write-then-chmod race window:** Standard POSIX pattern in the user's own home directory. Non-finding from prior rounds.
- **`SessionDB` SQL queries — injection risk:** All SQL queries use parameterized placeholders (`?`). No string interpolation. Clean.
- **`Slack._verify_slack_signature` timestamp rejection when `signing_secret` is absent:** Correct — the code emits a per-request `log.warning` when `signing_secret` is not configured and skips HMAC (accepted without verification). The warning is always visible to the operator. Clean.
- **`child_env = {**os.environ, ...}` leaking credentials to child process:** The daemon subprocess needs the same environment as the parent (API keys, PATH, etc.) to function. This is the correct and standard approach for spawning a daemon. Non-finding.
- **All 16 MCP tool annotations:** Verified correct. 7 write-op tools carry `readOnlyHint=False, destructiveHint=False`; 9 read-only tools carry `readOnlyHint=True`. `instr_safety_check` is read-only (no file writes). Clean.
- **`figure_render` / `figure_export` `finally: plt.close(fig)` with potentially unbound `fig`:** The compose step (`fig = FigureComposer().compose()`) is in its own `try/except` that returns early on failure. The `finally` is in a separate nested `try` that only executes if `fig` is already bound. Non-finding (confirmed from R11).
- **`cli.py:1625` P6 registration:** `p6_authoring.register(app)` correctly wires `comms`, `gateway`, `present`, `write`, and `hypotheses` commands. Clean.
- **`_COMMAND_REGISTRY` mutation at module import time:** All registrations complete before the event loop starts. Thread-safe. Clean.
- **`is_running()` / `stop_daemon()` exception coverage:** Catches `(ProcessLookupError, PermissionError)` — the complete set of exceptions `os.kill()` raises in Python 3.11+ (PEP 475 handles EINTR). Clean.
- **`read_pid()` race condition:** PID file can disappear between `exists()` and `read_text()`. The inner `except (ValueError, OSError): return None` handles this. Clean.
- **`asyncio.wait_for` `TimeoutError` identity (Python 3.11+):** `TimeoutError is asyncio.TimeoutError` is `True` in Python 3.11+. The `except TimeoutError: continue` clause is correct. Clean.
- **`comms_revision` `notes_text: list[str]` type:** `RevisionLetterAgent._generate_draft` handles both `list[str]` and `str` for `comment_notes`. Empty list `[]` is handled correctly. Clean.
- **`MissingFillMarkerError` from `agent.draft()` uncaught at CLI level:** `MissingFillMarkerError` is a subclass of `Exception`, caught by `except Exception as exc` in every comms command callback. Formatted as `[red]Draft failed:[/] {exc}`. Clean.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | LOW | `commands/p6_authoring.py:1121–1126` | `hypotheses_command` `--json-out` write block executes outside any exception handler; `PermissionError`/`FileNotFoundError`/`OSError` on an unwritable or non-existent path produces a raw Python traceback instead of a clean `[red]JSON write failed:[/]` message + `typer.Exit(1)` |
