# Code Review Round 9 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-20
**Reviewer:** Claude Sonnet 4.6 (automated, adversarial)

---

## Verdict

**ISSUES FOUND** — 1 finding (1 MEDIUM)

---

## R8 Fix Verification

### R8-F1: `sim_run` carries `readOnlyHint=False` annotation and appears in docstring + comment

**Status: CONFIRMED FIXED**

All three required changes are in place:

1. **`mcp_server.py:381`** — `annotations=write_op` (was `read_only`). Confirmed.
2. **`mcp_server.py:35`** — Module docstring line reads:
   ```
   readOnlyHint=False (figure_render, figure_export, sim_run,
   instr_search_manual, instr_ingest_manual, instr_generate_skill, instr_scaffold).
   ```
   `sim_run` is present. Confirmed.
3. **`mcp_server.py:86–90`** — `_WRITE_ANNOTATIONS` comment reads:
   ```python
   # Annotation for tools that write files to disk (figure_render, figure_export,
   # sim_run, instr_ingest_manual, instr_generate_skill, instr_scaffold,
   # instr_search_manual).
   ```
   `sim_run` is present. Confirmed.

---

## Findings

### F1 — MEDIUM | `maglab/sim/plot.py:402` + `maglab/mcp_server.py:407` | `sim_run` MCP tool: uncaught `ValueError` from `single_scale_spec()` escapes `run_sim_overlay` into `sim_run` with no exception handler

**Defect:**

`sim_run` (mcp_server.py:383) validates the incoming spec with `MultiScaleSpec.model_validate(spec_dict)` (line 396) and returns a clean `{"ok": False, ...}` dict on Pydantic parse errors. However, the subsequent call to `run_sim_overlay(spec_dict)` at line 407 can raise an uncaught `ValueError` that propagates all the way to the MCP host:

**Root cause in `maglab/sim/plot.py`:**

`run_sim_overlay` (lines 361–412) converts every foreseeable error to a `warnings.warn(...)` + `return []` — except for one gap. After `validate()` succeeds (lines 392–399), `single_scale_spec()` is called at line 402, which is **outside any try/except block**:

```python
# plot.py lines 400-412 (abridged):
try:
    validate(multi_spec)       # catches ValidationError
except Exception as exc:
    warnings.warn(...)
    return []

scale_spec = multi_spec.single_scale_spec()  # ← NOT in try/except
engine = scale_spec.engine

try:
    return _run_backend(scale_spec, engine)  # catches everything from here
except Exception as exc:
    warnings.warn(...)
    return []
```

`single_scale_spec()` (spec.py:247–255) raises `ValueError` when `len(self.scales) != 1`:

```python
def single_scale_spec(self) -> ScaleSpec:
    if len(self.scales) != 1:
        raise ValueError(f"Not a single-scale spec (number of scales: {len(self.scales)}).")
    return self.scales[0]
```

**Triggering path:**

A `MultiScaleSpec` with two or more `ScaleSpec` entries:
1. Passes `model_validate` — Pydantic requires only `len(scales) >= 1` (enforced by `_validate_scales_nonempty`).
2. Passes `validate()` — the validator iterates over all scales without rejecting multi-scale inputs.
3. Reaches `single_scale_spec()`, raises `ValueError("Not a single-scale spec …")`.
4. `ValueError` escapes `run_sim_overlay` uncaught.

**In `sim_run` (mcp_server.py:400–417):**

```python
with warnings.catch_warnings(record=True) as w:   # captures warnings, NOT exceptions
    warnings.simplefilter("always")
    dps = run_sim_overlay(spec_dict)               # ← ValueError propagates here
    for warning in w:
        caught.append(str(warning.message))
```

`warnings.catch_warnings` is a warning filter context manager. It does not suppress exceptions. The `ValueError` propagates out of the `with` block and out of `sim_run` entirely, reaching the MCP host as an unhandled exception rather than a structured `{"ok": False, "error": "..."}` response.

**Impact:** MEDIUM — Any MCP client that sends a multi-scale `MultiScaleSpec` (e.g. a P3 `dft + micro` pipeline spec) will receive an unhandled exception from the MCP host instead of a clean `{"ok": False}` response. Depending on the MCP host implementation, this may cause tool-call failure with an opaque error, break the calling agent's error handling, or surface a stack trace to the caller. The fix is straightforward.

**Fix:**

**Option A (fix in `mcp_server.py`)** — wrap `run_sim_overlay` in a try/except in `sim_run`:

```python
# mcp_server.py sim_run (replace lines 400-417):
import warnings

dps: list[Any] = []
caught: list[str] = []

try:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        dps = run_sim_overlay(spec_dict)
        for warning in w:
            caught.append(str(warning.message))
except Exception as exc:
    return {"ok": False, "job_id": "", "summary": "", "error": str(exc)}
```

**Option B (fix in `maglab/sim/plot.py`)** — wrap `single_scale_spec()` inside `run_sim_overlay`:

```python
# plot.py (replace lines 401-403):
try:
    scale_spec = multi_spec.single_scale_spec()
except ValueError as exc:
    warnings.warn(str(exc), stacklevel=2)
    return []
engine = scale_spec.engine
```

Option A is preferred because it is a smaller, more contained change at the MCP boundary and ensures `sim_run` never propagates unhandled exceptions regardless of future changes to `run_sim_overlay`.

---

## Non-Findings

The following areas were investigated in full and found to be clean:

- **R8-F1 sim_run annotation fix:** Confirmed fixed at mcp_server.py:381 (`annotations=write_op`), module docstring line 35, and `_WRITE_ANNOTATIONS` comment lines 86–90. All three locations verified.
- **`hmac.new` in `slack.py:91`:** `hmac.new` is a valid alias for `hmac.HMAC()` constructor in Python's standard library (confirmed: `dir(hmac)` returns `'new'`). No defect.
- **`getattr(formula_module, formula_name, None)` — formula injection:** `maglab.physics.formulas` and `maglab.physics.units` do not expose any dangerous callables (no `exec`, `eval`, `open`, `__import__`, or other system-level functions) via `getattr`. The modules only export domain-specific physics functions and a `Quantity` class. No injection risk.
- **`sim_parse` path traversal:** `sim_parse` accepts a user-provided `file_path` and reads it with no path restriction. This is by design for a local MCP tool (the server runs as the local user). No privilege escalation is possible. Confirmed non-finding from R8.
- **`figure_render` / `figure_export` write-path injection:** Output paths (`output_path`, `stem`) are user-controlled writes. Same local-tool design reasoning; no privilege escalation. By design.
- **`generate_launchd_plist` — `maglab_executable` XML injection:** The `--executable` argument is inserted unsanitized into an XML plist. This is a self-attack vector (the CLI user writes their own LaunchAgent). No escalation of privilege.
- **`GatewayRunner()` constructed with no adapters in `_run_gateway_foreground`:** `GatewayRunner` with `adapters={}` is functional (notification loop runs, `handle_message` returns `None` for unknown platforms). No crash, no security risk. Adapters are added at runtime by the runner's platform startup logic.
- **`MAGLAB_GATEWAY_PID_CLAIMED` env-var race (R7 fix):** Confirmed clean from R8. All four cases (background child, direct foreground, double-start rejection, TOCTOU guard) verified correct at p6_authoring.py:674–706.
- **`pid_file.write_text(str(proc.pid))` vs child `write_pid(os.getpid())`:** Both writes are the same value (`proc.pid` is the child's PID). No race condition or inconsistency.
- **`stop_daemon()` removes PID file after SIGTERM:** `stop_daemon()` at runner.py:376 sends SIGTERM then calls `remove_pid()`. Even if the daemon's `finally` block cannot run on SIGTERM, the CLI-side cleanup is correct. Confirmed non-finding.
- **`GatewayRunner.stop()` SQLite close race:** All DB access occurs on the single asyncio event loop. `stop()` cancels all tasks then calls `self._db.close()`. No concurrent access possible.
- **All 16 MCP tool annotations:** Verified against actual I/O behavior:
  - 7 write-op tools (figure_render:509, figure_export:573, sim_run:381, instr_search_manual:658, instr_ingest_manual:702, instr_generate_skill:759, instr_scaffold:809) all carry `annotations=write_op`. Correct.
  - 9 read-only tools (physics_compute:111, physics_check:156, convert_units:189, material_lookup:237, material_search:266, provenance_query:293, sim_validate:331, sim_parse:442, instr_safety_check:857) all carry `annotations=read_only`. Correct.
- **`instr_safety_check` annotation (`read_only`):** `check_scpi` / `check_script` perform static regex analysis only. No file writes. Correct.
- **`comms_revision` notes type mismatch:** `notes_text` is `list[str]` (containing at most one string). `RevisionLetterAgent.draft()` receives `{"comment_notes": notes_text}`. The agent accepts whatever the dict provides; no type contract violation.
- **SQLite FK enforcement in `session_db.py`:** `log_message` is only ever called after `get_or_create_session`, which always returns a valid session with a real `id`. No orphaned rows can be inserted.
- **`sim_run` warns-only path for empty `dps`:** When `not dps and caught`, returns `{"ok": False, "error": ...}`. When `not dps and not caught` (e.g. engine returns empty list silently), returns `{"ok": True, "job_id": ..., "datapoints": []}`. This edge case is a valid success path (spec valid, engine ran, zero DataPoints produced), not a defect.
- **`_COMMAND_REGISTRY` global mutation thread safety:** `register_command` mutates `_COMMAND_REGISTRY` at module import time. All registrations complete before the asyncio event loop starts. No concurrent mutation. Safe.
- **CLI command registration completeness:** `register()` at p6_authoring.py:61 wires `comms_app`, `gateway_app`, `present_app`, `write_command`, and `hypotheses_command`. `cli.py:1625` calls `p6_authoring.register(app)`. All P6 commands are correctly wired.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | MEDIUM | `sim/plot.py:402` + `mcp_server.py:407` | `single_scale_spec()` raises uncaught `ValueError` for multi-scale specs; escapes `run_sim_overlay` and propagates unhandled through `sim_run`, reaching the MCP host as an unhandled exception instead of `{"ok": False, ...}` |
