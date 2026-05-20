# Code Review Round 7 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-19
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**ISSUES FOUND** — 1 finding (1 HIGH)

---

## R6 Fix Verification

### R6-F1: Background gateway startup PID-claim handoff (env var strategy)

**Status: PARTIALLY FIXED — new regression introduced**

The R6 fix correctly identified that the background parent must claim the PID file atomically before spawning the child, and must signal the child (via `MAGLAB_GATEWAY_PID_CLAIMED=1`) to skip the re-claim. The `open("x")` double-claim is indeed prevented by the env var check at `p6_authoring.py:678–689`.

However, the fix introduced a new regression: the child subprocess hits the `is_running()` check at **line 659 before** the env var guard at line 678. See F1 below for full analysis.

The double-start guard is still correctly in place:
- Background double-start: blocked at the parent level by `open("x")` at lines 710–719.
- Direct foreground double-start: blocked by `open("x")` at lines 681–689.
- An already-running daemon is correctly detected by `is_running()` before any claim attempt (for non-claimed invocations).

### R6-F2: `instr_search_manual` carries `write_op` annotation

**Status: CONFIRMED FIXED**

`mcp_server.py` line 656: `annotations=write_op,  # downloads PDF + sha256.txt to local cache — not read-only`

The annotation is correct. The module-level docstring (lines 34–36) also lists `instr_search_manual` among the file-writing tools: `readOnlyHint=False (figure_render, figure_export, instr_search_manual, instr_ingest_manual, instr_generate_skill, instr_scaffold)`. All six write-op tools carry `annotations=write_op`; all ten read-only tools carry `annotations=read_only`. Annotation inventory is fully consistent.

---

## Findings

### F1 — HIGH | `maglab/commands/p6_authoring.py:659` | Background daemon child exits prematurely due to `is_running()` firing before env-var guard

**Defect:**

The R6 fix introduces `MAGLAB_GATEWAY_PID_CLAIMED=1` in the child's environment to tell it to skip the `open("x")` atomic claim. The guard lives at lines 678–689 inside the `if foreground:` branch. However, `is_running()` is called unconditionally at **line 659**, before the code reaches the foreground branch and the env-var check.

The execution trace in background mode:

1. **Parent (line 712–713):** creates an empty PID file via `pid_file.open("x"); fd.close()`.
2. **Parent (lines 727–733):** spawns child subprocess via `subprocess.Popen(...)` — child process is launched by the OS.
3. **Parent (line 741):** `pid_file.write_text(str(proc.pid))` — writes the child's PID to the file. This runs in microseconds after `Popen()` returns.
4. **Child:** Python interpreter initialization takes approximately 50–200 ms before any Python code executes.
5. **Child (line 659):** `if is_running():` — by this point the parent has already written `proc.pid` (= the child's own PID) to the file. `read_pid()` returns `proc.pid`; `os.kill(proc.pid, 0)` (signal 0 to itself) **always succeeds** (a process can always signal itself). `is_running()` returns `True`.
6. **Child (line 660–661):** prints `"Gateway is already running."` and `return`s — **the daemon event loop never starts**.

This is deterministic, not a race: the gap between `Popen()` returning and the child's first line of Python executing is dominated by Python interpreter startup time (~50–200 ms), while the parent's `write_text()` call completes in microseconds. The parent will always write the PID before the child reads it.

The result is identical to the R6 bug it was meant to fix: `gateway start` (background mode) prints a success message and exits, but no event loop ever runs. Only `gateway start --foreground` (direct invocation, no env var) works correctly.

**Impact:** HIGH — Background-mode daemon start is completely broken. All gateway message routing is unavailable in background mode. Users running `gateway start` (the default) get a false success message with no running daemon.

**Fix:**

Move the `MAGLAB_GATEWAY_PID_CLAIMED` check to before the `is_running()` call, or gate `is_running()` on the absence of the env var:

```python
import os

# Must check env var BEFORE is_running() — when the background parent spawns us,
# it has already written our PID to the file; is_running() would return True and
# cause us to exit prematurely.
pid_already_claimed = os.environ.get("MAGLAB_GATEWAY_PID_CLAIMED") == "1"

if not pid_already_claimed and is_running():
    console.print("[yellow]Gateway is already running.[/] Use 'maglab gateway status'.")
    return

if foreground:
    pid_file = _pid_path()
    if not pid_already_claimed:
        # Direct foreground invocation — claim atomically.
        try:
            fd = pid_file.open("x")
            fd.close()
        except FileExistsError:
            console.print(
                "[yellow]Gateway is already starting or running.[/] "
                "Use 'maglab gateway status'."
            )
            return
    console.print("[cyan]Starting gateway in foreground mode...[/]")
    _run_gateway_foreground()
else:
    # Background mode — identical to current code
    ...
```

This preserves all existing guards:
- Running daemon: detected by `is_running()` for non-claimed invocations.
- Background double-start: blocked at parent level by `open("x")`.
- Direct foreground double-start: blocked by `open("x")` in the foreground branch.
- Background child: skips `is_running()` entirely (it knows the PID belongs to itself).

---

## Non-Findings

The following areas were investigated and found to be clean:

- **`instr_search_manual` annotation (R6-F2):** Confirmed `annotations=write_op` at `mcp_server.py:656`. Module docstring also updated. Full annotation inventory audited: 6 write-op tools and 10 read-only tools all carry correct annotations.
- **`instr_safety_check` annotation (`read_only`):** `check_scpi` and `check_script` in `instrument/safety.py` perform static SCPI validation only; they do not write files. Annotation is correct.
- **Double `remove_pid()` in `_run_gateway_foreground`:** The inner `_main.finally` (line 1210) and outer `finally` (line 1217) both call `remove_pid()`. This is safe: `remove_pid()` wraps `unlink(missing_ok=True)` in `contextlib.suppress(OSError)`, so the second call is a no-op.
- **`TimeoutError` catching in adapter approval gates:** All three adapters (`slack.py:330`, `telegram.py:229`, `discord.py:242`) catch `TimeoutError` from `asyncio.wait_for`. `pyproject.toml` requires `python >= 3.11`, where `asyncio.TimeoutError is TimeoutError`. Correct.
- **Service unit files (`generate_systemd_unit`, `generate_launchd_plist`):** Both call `gateway start --foreground` without `MAGLAB_GATEWAY_PID_CLAIMED`. These invoke the direct foreground path (`pid_already_claimed=False` after the fix), which atomically claims the PID file. Unaffected by F1.
- **CLI command registration:** All comms (`revision`, `cover-letter`, `email`, `abstract`, `grant`, `rebuttal`), gateway (`setup`, `start`, `stop`, `status`, `install`), present (`slides`, `poster`), `write`, and `hypotheses` commands are correctly registered. `cli.py:1625` calls `p6_authoring.register(app)`.
- **`hypotheses_command` missing `ImportError` guard:** `maglab.core.reasoning` is a core module (not in optional extras) and `reasoning.py` exists. `D1HypothesisEngine` is defined at line 1133 of that file. The unguarded import is safe.
- **Discord channel `int(channel)` parsing:** `int(channel)` is wrapped inside `try/except Exception` in `send_reply` (line 161–164 of `discord.py`). A non-numeric channel silently logs an error and returns; no crash.
- **Stale PID file blocking foreground restart:** If a previous daemon crashed without cleaning up the PID file, `is_running()` returns `False` (process gone) but `open("x")` fails with `FileExistsError`, blocking the restart. This is pre-existing behavior, not introduced by R6, and is outside R7 scope.
- **`SessionDB.get_or_create_session` double-hashing:** Accepts pre-hashed `user_id_hash` from `UnifiedMessage`; does not call `_hash_user_id` internally. No double-hashing.
- **Slack HMAC `hmac.new` correctness:** `hmac.new(key, msg, digestmod)` is the correct `hmac` module API. Timing-safe `hmac.compare_digest` used for signature comparison.
- **No auto-send path:** All comms agents and CLI commands write output to files only. Confirmed.
- **`DataVault.inject_into_draft` gate on critic revisions:** `loop_c.py:264` re-runs vault injection on critic-revised drafts. Vault blocking applies to revisions too.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | HIGH | `p6_authoring.py:659` | `is_running()` fires before `MAGLAB_GATEWAY_PID_CLAIMED` env-var guard; child subprocess reads its own PID written by parent and returns prematurely — daemon never starts in background mode |
