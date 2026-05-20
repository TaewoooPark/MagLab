# Code Review — Round 2, Domain 03: `maglab/figure/` & `maglab/instrument/`

Reviewer: Claude Sonnet 4.6 (adversarial static + dynamic analysis)
Date: 2026-05-19

---

## Verdict

**ISSUES FOUND**

---

## R1 Patch Verification

All seven Round-1 findings were re-probed against the current code and confirmed resolved:

| R1 ID | Fix | Verified |
|-------|-----|----------|
| HIGH-1 | Semicolon-split compound SCPI commands | `check_scpi_sequence(['*RST; SOUR:VOLT 1000'])` → `ok=False` |
| HIGH-2 | `plt.close(fig)` in `except` block in `compose.py` and `render_single` | Code path confirmed |
| MEDIUM-1 | `"SLVL"` / `":SLVL"` added to `_VOLT_PREFIXES` | `check_scpi_sequence(['*RST','SLVL 10'])` → violation caught |
| MEDIUM-2 | `row_end > nrows or col_end > ncols` guard in `_make_axes` | Code path confirmed |
| MEDIUM-3 | Bare `"VOLT"` removed from `_VOLT_PREFIXES`; `VOLT:RANG` no longer triggers false violation | `check_scpi_sequence(['*RST','VOLT:RANG 10'])` → `ok=True` |
| LOW-1 | `try/finally: plt.close(fig_tmp)` in `render_panel` | Code path confirmed |
| LOW-2 | Zero-size OVF guard before reshape | Code path confirmed |
| LOW-3 | `write_re.finditer` replaces `write_re.search` in `check_script_text` | Confirmed working |

---

## Findings

### [MEDIUM-1] `_render_hsl_direct` and `render_quiver` silently produce wrong output for `plane='y'`

**Files:** `maglab/figure/renderers/simviz.py` — `_render_hsl_direct` lines 382–391, `render_quiver` lines 485–494

**Defect:** Both functions handle all non-`'z'` planes with a single `else` branch that:
1. computes the default index as `m.shape[0] // 2` (the x-axis midpoint), and
2. slices the array as `m[idx, :, :, :]` (an x-plane slice — fixed x, free y and z).

For `plane='y'` the correct behavior is:
1. default index = `m.shape[1] // 2` (the y-axis midpoint), and
2. slice `m[:, idx, :, :]` (a y-plane slice — fixed y, free x and z).

The net effect: when `plane='y'` and `plane_index=None` (the most common call pattern), both functions silently render the x-midplane instead of the y-midplane. No error or warning is emitted. When `plane_index` is supplied explicitly the index value is used correctly, but the slice axis (`m[idx, :, :]`) remains wrong for `plane='y'`.

By contrast, `_render_2d_numpy` (the numpy fallback for `render_2d`) correctly handles `plane='y'` in a distinct `elif` branch with the right index and slice axis (lines 258–260).

**Concrete probe:**
```python
import numpy as np
m = np.zeros((10, 8, 6, 3))  # nx=10, ny=8, nz=6
# _render_hsl_direct plane='y': else branch
idx = m.shape[0] // 2   # 5 — x midpoint, not y midpoint
slice_ = m[idx, :, :, 0]  # shape (8,6) — x-plane slice
# Correct for plane='y':
idx_y = m.shape[1] // 2  # 4
slice_y = m[:, idx_y, :, 0]  # shape (10,6) — y-plane slice
```

The bug is a pre-existing design fault (not introduced by the R1 patches), but it is a genuine logic error in two separate functions.

**Fix:** Add a `elif plane == 'y'` branch to `_render_hsl_direct` and `render_quiver`, parallel to the one in `_render_2d_numpy`:
```python
elif plane == 'y':
    idx = plane_index if plane_index is not None else m.shape[1] // 2
    mx = m[:, idx, :, 0]
    my = m[:, idx, :, 1]
    mz = m[:, idx, :, 2]
else:  # plane == 'x'
    idx = plane_index if plane_index is not None else m.shape[0] // 2
    mx = m[idx, :, :, 0]
    my = m[idx, :, :, 1]
    mz = m[idx, :, :, 2]
```

---

### [MEDIUM-2] Module docstring advertises rule #3 (`output-active` parameter guard) but it is not implemented

**File:** `maglab/instrument/safety.py` lines 8–11

**Defect:** The module-level docstring enumerates four safety validation rules:
```
3. Reject parameter changes that exceed limits while output is active.
```

No such tracking exists in the implementation. `check_scpi_sequence` maintains an `initialized` flag but no `output_active` flag. When `OUTP ON` is detected at line 287, the code verifies that `initialized` is `True` (order check), but it does not set an `output_active` flag. Subsequent `SOUR:VOLT` or `SOUR:CURR` commands within the same sequence are checked only against absolute limits, not gated on whether the output is live.

**Demonstrated gap:**
```python
checker.check_scpi_sequence(['*RST', 'SOUR:VOLT 100', 'OUTP ON', 'SOUR:VOLT 5'])
# → ok=True, violations=[]
# Docstring rule #3 says this SOUR:VOLT 5 while output is active should be rejected.
```

This is not a bug in the limit checks themselves (5 V is within range), but the advertised rule — rejecting *any* parameter change while output is active — is silently absent.

**Severity rationale:** The safety consequence depends on context. Changing voltage while output is active can cause current surges on sensitive samples. The docstring creates a false assurance that this is guarded. Classified MEDIUM because the limit checks are still active (a dangerously high value would still be caught), but the output-active constraint is a documented invariant that is broken.

**Fix (two options):**
- **(a) Implement the rule:** Track `output_active` state: set it to `True` when `_OUTPUT_ON_RE` matches, set it to `False` when `_OUTPUT_OFF_RE` matches. Raise `ORDER_VIOLATION` for any `CONFIG`-phase sub-command (voltage / current setter) encountered while `output_active is True`.
- **(b) Retract the docstring claim:** Remove rule #3 from the module docstring and document it as a known limitation. This is the minimal fix if the rule is aspirational.

Option (a) is the correct fix; option (b) is acceptable as a stopgap with a `TODO` comment.

---

### [LOW-1] `SweepConfig.step = 0.0` is accepted and produces a `ZeroDivisionError` in the generated script

**File:** `maglab/instrument/script.py` lines 45–48 (`SweepConfig`); generated script template `measurement_script.py.j2`

**Defect:** `SweepConfig` is a Pydantic model with no validator on the `step` field. `step=0.0` is silently accepted. The Jinja2 template generates:
```python
for setpoint in np.arange(START_VALUE, STOP_VALUE + STEP_VALUE / 2, STEP_VALUE):
```
When `STEP_VALUE = 0.0`, `np.arange(..., 0.0)` raises:
```
ZeroDivisionError: float division by zero
```
The error occurs at runtime (human execution, Tier 3), not during script generation or safety validation.

**Verified by probe:**
```python
import numpy as np
np.arange(0.0, 1.0 + 0.0 / 2, 0.0)
# ZeroDivisionError: float division by zero
```

**Fix:** Add a Pydantic field validator to `SweepConfig`:
```python
from pydantic import field_validator

@field_validator('step')
@classmethod
def step_must_be_nonzero(cls, v: float) -> float:
    if v == 0.0:
        raise ValueError("sweep step must be non-zero")
    return v
```

---

## Summary Table

| ID | Severity | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| MEDIUM-1 | MEDIUM | `figure/renderers/simviz.py` | 382–391, 485–494 | `plane='y'` silently renders `plane='x'` in `_render_hsl_direct` and `render_quiver` |
| MEDIUM-2 | MEDIUM | `instrument/safety.py` | 8–11 | Docstring rule #3 (output-active param guard) advertised but not implemented |
| LOW-1 | LOW | `instrument/script.py` | 45–48 | `SweepConfig.step=0` accepted; generated script raises `ZeroDivisionError` at runtime |
