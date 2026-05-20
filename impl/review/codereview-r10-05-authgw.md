# Code Review Round 10 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-20
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**ISSUES FOUND** — 1 finding (1 LOW)

---

## R9 Fix Verification

### R9-F1: `sim_run` MCP tool wraps `run_sim_overlay()` in `try/except Exception`

**Status: CONFIRMED FIXED**

The fix is in place at `mcp_server.py:405–412`:

```python
try:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        dps = run_sim_overlay(spec_dict)
        for warning in w:
            caught.append(str(warning.message))
except Exception as exc:
    return {"ok": False, "job_id": "", "summary": "", "error": str(exc)}
```

The `run_sim_overlay()` call is fully wrapped in `try/except Exception`. A multi-scale `MultiScaleSpec` that triggers `single_scale_spec()` → `ValueError` will now be caught and returned as a structured `{"ok": False, "error": "..."}` dict instead of propagating to the MCP host. Confirmed.

---

## Findings

### F1 — LOW | `maglab/commands/p6_authoring.py:828–832` | `gateway_install`: uncaught `PermissionError` from `install_service` escapes to the CLI user as an unhandled exception

**Defect:**

`gateway_install` catches only `RuntimeError` from `install_service()`:

```python
try:
    service_path = install_service(maglab_executable=executable)
except RuntimeError as exc:
    console.print(f"[red]Service installation failed:[/] {exc}")
    raise typer.Exit(1) from exc
```

`install_service()` in `runner.py` calls `check_credential_permissions(cred_file)` (runner.py:503), which raises `PermissionError` (not `RuntimeError`) when the credential file has insecure permissions (`check_credential_permissions` raises `PermissionError` at base.py:92–97).

The `gateway_install` command contains a pre-flight permission check (lines 819–826) that detects the same insecure permissions via `oct(cfg.stat().st_mode)[-3:] != "600"`. This pre-check catches the problem in normal operation, so the gap only matters in a race condition (the file permissions change between the CLI pre-check and the `install_service` call). In that narrow window, `PermissionError` propagates to the CLI user as an unhandled Python exception instead of a formatted `[red]...[/]` error message.

**Impact:** LOW — The pre-check makes the race window very narrow. However, the contract of `install_service` documents that it raises `PermissionError` and `RuntimeError`, but the caller only handles `RuntimeError`. This is an API contract violation and produces a user-hostile traceback in the edge case.

**Fix:**

```python
try:
    service_path = install_service(maglab_executable=executable)
except (RuntimeError, PermissionError) as exc:
    console.print(f"[red]Service installation failed:[/] {exc}")
    raise typer.Exit(1) from exc
```

---

## Non-Findings

The following areas were investigated in full and found to be clean or out of scope for new findings:

- **R9-F1 sim_run fix:** Confirmed fixed at mcp_server.py:405–412 with `try/except Exception` wrapping `run_sim_overlay()`. Verified.
- **Other MCP tools for uncaught-exception gap (R9 pattern):** All 16 tools examined:
  - `physics_compute`: has `try/except Exception` around `fn(**params)`. Clean.
  - `physics_check`: no try/except around `check(params)`. However, `check()` in `oracle.py` never raises (all sub-check functions return `OracleResult` and never raise). FastMCP also applies Pydantic `TypeAdapter.validate_python()` before the function body, so malformed `dict[str, float]` input is rejected by FastMCP before `check()` is called. Not a defect.
  - `convert_units`: has `try/except Exception` around `fn(value)`. Clean.
  - `material_lookup`: early-returns `None` on missing material; no exception path. Clean.
  - `material_search`: calls `search(query)` which only iterates and filters — never raises. Clean.
  - `provenance_query`: creates ephemeral `ProvenanceLedger()` (always empty); always returns `None`. This is a functional limitation (tool is useless without a persistent store), not a newly introduced defect, and prior rounds did not flag it. Not a new finding.
  - `sim_validate`: first try/except catches Pydantic parse errors; second try/except catches `ValidationError`. `validate()` only raises `ValidationError` or accumulates violations — the `validate_micro` `ValueError` branch is guarded by the `scale_spec.scale == ScaleType.micro` check in `validate()`. Clean.
  - `sim_run`: R9 fix verified — fully wrapped. Clean.
  - `sim_parse`: has `try/except Exception` around the parse call. Clean.
  - `figure_render`: first `try/except` for spec parse, second for compose, third for export — all covered. The `finally plt.close(fig)` references `fig` which is guaranteed to be bound when the inner `finally` block executes. Clean.
  - `figure_export`: same pattern as `figure_render`. Clean.
  - `instr_search_manual`, `instr_ingest_manual`, `instr_generate_skill`, `instr_scaffold`, `instr_safety_check`: all wrapped in `try/except Exception`. Clean.
- **`sim_validate` gap — `validate()` raises non-`ValidationError`:** `validate()` only raises `ValidationError`. Inner helpers only append to violation lists. The `validate_micro` `ValueError` path is unreachable from `validate()` (scale guard prevents it). Not a defect.
- **`physics_check` missing try/except:** Protected by FastMCP input coercion (Pydantic TypeAdapter) before function body. `oracle.check()` never raises. Not a defect.
- **`provenance_query` always returns `None`:** `ProvenanceLedger()` creates an in-memory store (`":memory:"` default) with empty `_cache`. The tool always returns `None`. The `provenance://` resource similarly always returns `[]`. This is an architectural limitation (no persistent shared ledger in the MCP server), not a newly introduced defect. Not flagged in prior rounds. Out of scope as a fresh finding (design-level, not a defect introduced in code under review).
- **Double `remove_pid()` call in `_run_gateway_foreground()`:** Both `_main`'s `finally` and the outer `finally` call `remove_pid()`. `remove_pid()` uses `contextlib.suppress(OSError)` and `missing_ok=True`, so the double-remove is safe. Not a defect.
- **`gateway_install` permission check via `oct()[-3:]`:** The string comparison `!= "600"` correctly detects any permission bits beyond owner-read-write because any extra bits change the last 3 octal digits. The pre-check catches the same cases as `check_credential_permissions`. The TOCTOU race window is narrow. Pre-check is consistent with `check_credential_permissions` behavior.
- **`generate_launchd_plist` XML injection:** F-string interpolation of `maglab_executable` into a plist XML is a self-attack vector (user controls their own LaunchAgent). Confirmed non-finding from prior rounds.
- **Discord `int(channel)` in `send_reply`:** Wrapped in `try/except Exception`. Safe.
- **Slack HMAC `hmac.new` alias:** Valid Python standard library alias. Clean.
- **`_gate_approve` / `_gate_reject` dynamic attributes on Slack/Telegram adapters:** These are set as instance attributes via `self._gate_approve = _approve`. There is no action handler registered in the MCP layer to call these callbacks — the approval gate stubs are currently orphaned. This is a known stub design (the Platform SDK handler wires them at runtime). Not a new defect.
- **`asyncio.CancelledError` handling in `_main`:** Reachable when `asyncio.run()` shuts down the event loop and cancels pending tasks. `runner.stop()` and `remove_pid()` are correctly called in the `finally` block. Clean.
- **All 16 MCP tool annotations:** Previously verified correct in R8/R9 and confirmed unchanged. All 7 write-op tools carry `annotations=write_op`; all 9 read-only tools carry `annotations=read_only`. Clean.
- **`_COMMAND_REGISTRY` mutation at module import time:** All registrations complete before the event loop starts. Thread-safe. Clean.
- **CLI command registration:** `p6_authoring.register(app)` at `cli.py:1625` wires all five P6 command surfaces correctly. Clean.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | LOW | `commands/p6_authoring.py:828–832` | `gateway_install` catches only `RuntimeError` from `install_service()`; `PermissionError` (documented in `install_service` API contract) propagates as unhandled exception in a narrow TOCTOU race window |
