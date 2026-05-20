# Code Review Round 11 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-20
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**ISSUES FOUND** — 1 finding (1 LOW)

---

## R10 Fix Verification

### R10-F1: `gateway_install` catches `(RuntimeError, PermissionError)` from `install_service()`

**Status: CONFIRMED FIXED**

The fix is in place at `maglab/commands/p6_authoring.py:828–832`:

```python
try:
    service_path = install_service(maglab_executable=executable)
except (RuntimeError, PermissionError) as exc:
    console.print(f"[red]Service installation failed:[/] {exc}")
    raise typer.Exit(1) from exc
```

Both `RuntimeError` (unsupported platform) and `PermissionError` (insecure credential file permissions from `check_credential_permissions`) are now caught. The API contract of `install_service()` is fully honoured. Confirmed.

---

## Findings

### F1 — LOW | `maglab/commands/p6_authoring.py:1065–1068` | `hypotheses_command`: bare lazy import without `ImportError` guard

**Defect:**

`hypotheses_command` performs a lazy import of `maglab.core.reasoning` inside the function body (lines 1065–1068) without a `try/except ImportError` wrapper:

```python
from maglab.core.reasoning import (
    D1HypothesisEngine,
    HypothesisResult,
)
```

Every other command in `p6_authoring.py` that performs a lazy import wraps it in `try/except ImportError` and converts the failure to a user-friendly `[red]Missing dependency:[/]` message + `typer.Exit(1)`:

- `write_command` (line 137–146): `try/except ImportError` around `bib_manager`, `data_vault`, `loop_c` imports.
- `comms_revision` (line 243–247), `comms_cover_letter` (303–307), `comms_email` (366–370), `comms_abstract` (417–421), `comms_grant` (481–485), `comms_rebuttal` (539–543): all guarded.
- `gateway_start`, `gateway_stop`, `gateway_status`, `gateway_install` (lines 653–815): all guarded.
- `present_slides` (896–899), `present_poster` (997–999): both guarded.

`hypotheses_command` is the sole exception. If `maglab.core.reasoning` fails to import (e.g. partially broken installation, future optional dependency added to the module, or package installed in editable mode with missing files), the exception propagates as an unhandled `ImportError` traceback directly to the CLI user instead of the standard formatted error message.

**Current risk level:** LOW. `maglab.core.reasoning` currently imports only Python stdlib modules (`logging`, `random`, `re`, `collections.abc`, `dataclasses`, `enum`). There is no optional dependency and no third-party import at module level, so an `ImportError` is very unlikely under normal conditions. The gap is a defensive-programming inconsistency rather than an active defect.

**Impact:** LOW — If the import fails (e.g. editable install with a renamed file, future optional dep added to `reasoning.py`), the user sees a raw Python traceback instead of a helpful `[red]Missing dependency:[/]` message. Inconsistent with the module-wide contract stated in the docstring: "Missing dependency / credentials → clear message + raise typer.Exit(1)."

**Fix:**

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

---

## Non-Findings

The following areas were investigated and dismissed:

- **R10-F1 fix (`gateway_install` catches `PermissionError`):** Confirmed at `p6_authoring.py:830`. Both `RuntimeError` and `PermissionError` are caught. Clean.
- **`hypotheses_command` engine/result exception handling:** The `engine.run()` call at line 1074 is wrapped in `try/except Exception` (lines 1073–1081). Runtime failures (e.g. LLM call failure, oracle error) are caught and formatted cleanly. Only the import itself is unguarded (F1 above).
- **`maglab.core.reasoning` module-level imports:** Only stdlib (`logging`, `random`, `re`, `dataclasses`, `enum`). No third-party or optional deps at module level. The lazy `from maglab.physics.oracle import check as _oracle_check` inside `reflection_physics_check()` is inside a function body and guarded by the `try/except Exception` at the call site. Non-finding.
- **`_notification_loop` task_done() not called after exception:** `_send_notification()` (lines 299–327) catches all per-adapter exceptions internally. The only code paths that could escape to the outer `except Exception` at line 296 are `event.format_text()` and `event.payload.get()` — both trivially safe. In practice `task_done()` is always called. Furthermore `asyncio.Queue.join()` is never called anywhere in the gateway module, so the unfinished-task counter has no operational impact. Non-finding.
- **`figure_render` / `figure_export` `finally` with potentially unbound `fig`:** The compose step (`fig = FigureComposer().compose()`) is in its own `try/except` block that returns early on failure. The `finally: plt.close(fig)` block is in a separate nested `try` that only executes if `fig` is already bound. `fig` is guaranteed bound when `finally` is reached. Non-finding (confirmed from R10).
- **`sim_run` discards validated `MultiScaleSpec` object, passes raw `spec_dict` to `run_sim_overlay`:** `run_sim_overlay` performs its own `MultiScaleSpec.model_validate(spec_dict)` internally. The double-validation is redundant but the raw dict is safe to pass. Non-finding.
- **`sim_parse` path traversal:** `sim_parse` accepts arbitrary `file_path` from the MCP host. This is a local stdio MCP server — the "caller" is the same user's Claude Code process. Same-user self-attack vector, consistent with prior round non-finding verdicts. Non-finding.
- **All 16 MCP tool annotations:** Verified correct. 7 write-op tools carry `readOnlyHint=False, destructiveHint=False`; 9 read-only tools carry `readOnlyHint=True`. `instr_safety_check` is read-only (no file writes). Clean.
- **`gateway_start` background mode PID file orphan if `write_text` fails after `Popen`:** If `pid_file.write_text(str(proc.pid))` fails after a successful `Popen`, the daemon is orphaned and the empty sentinel file remains. However, `write_text` on a path the user just created with `open("x")` fails only on extreme conditions (disk full, revoked permissions). This is an edge case without a reasonable fix that doesn't require a much larger refactor (and cleaning up an orphan process requires knowing its PID, which the `Popen` object holds). Non-finding.
- **`gateway_setup` write-then-chmod race window:** Standard POSIX pattern. The file is in the user's own home directory. Not a defect.
- **`stop_daemon` exception coverage:** Catches `(ProcessLookupError, PermissionError)` — the complete set of exceptions `os.kill()` raises in Python 3.11+ (PEP 475 handles EINTR). Clean.
- **`is_running()` exception coverage:** Catches `(ProcessLookupError, PermissionError)` from `os.kill(pid, 0)`. Correct. Clean.
- **`generate_launchd_plist` XML injection:** Self-attack vector (user controls own LaunchAgent). Non-finding from prior rounds. Unchanged.
- **Slack `hmac.new` alias:** `hmac.new` is a valid Python stdlib alias for `hmac.HMAC` constructor. Verified: `python3 -c "import hmac, hashlib; hmac.new(b's', b'd', hashlib.sha256)"` succeeds. Clean.
- **Double `remove_pid()` in `_run_gateway_foreground`:** `_main`'s inner `finally` and the outer `finally` both call `remove_pid()`. `remove_pid()` uses `contextlib.suppress(OSError)` and `missing_ok=True`. Double-remove is safe. Non-finding from prior rounds. Unchanged.
- **`_gate_approve` / `_gate_reject` orphaned callbacks (Slack, Telegram adapters):** Known stub design — no action handler is wired at the MCP layer. The approval gate callbacks are set as instance attributes but never invoked through the MCP path. Design-level limitation, not a newly introduced defect. Non-finding from prior rounds.
- **`SessionDB` SQL queries — injection risk:** All SQL queries use parameterized placeholders (`?`). No string interpolation. Clean.
- **`cli.py:1625` P6 registration:** `p6_authoring.register(app)` correctly wires `comms`, `gateway`, `present`, `write`, and `hypotheses` commands. Clean.
- **`_COMMAND_REGISTRY` mutation at module import time:** All registrations complete before the event loop starts. Thread-safe. Clean.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | LOW | `commands/p6_authoring.py:1065–1068` | `hypotheses_command` performs bare lazy import of `maglab.core.reasoning` without `try/except ImportError` guard — inconsistent with every other command in the file; unhandled traceback on import failure instead of standard `[red]Missing dependency:[/]` message |
