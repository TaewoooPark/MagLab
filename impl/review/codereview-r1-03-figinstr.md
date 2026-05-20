# Code Review — Round 1, Domain 03: `maglab/figure/` & `maglab/instrument/`

Reviewer: Claude Sonnet 4.6 (adversarial static + dynamic analysis)
Date: 2026-05-19

---

## Verdict

**ISSUES FOUND**

---

## Findings

### [HIGH-1] Safety gate bypass via SCPI compound-command (semicolon chaining)

**File:** `maglab/instrument/safety.py` lines 263–265

**Defect:** `SafetyChecker.check_scpi_sequence()` uses `INIT_RE.search(cmd_stripped)` to detect initialization commands. When the regex matches (e.g., `*RST` is found anywhere in the line), the method sets `initialized = True` and immediately executes `continue`, skipping all subsequent limit checks for that line. Because SCPI standard allows semicolons to chain multiple commands on a single physical line, the input string `'*RST; SOUR:VOLT 1000'` causes `INIT_RE` to match on `*RST`, the `continue` fires, and the voltage `1000 V` — which exceeds a `210 V` keithley-2400 limit — is never evaluated.

**Verified by probe:**

```
checker.check_scpi_sequence(['*RST; SOUR:VOLT 1000'])
# -> SafetyCheckResult(ok=True, violations=[])
# Expected: voltage_over_limit violation
```

The bypass also works for `*CLS; SOUR:VOLT 1000`, and it defeats the order-violation check via `'*RST; OUTP ON'` (the output activation on the same compound line is neither blocked nor recorded).

This bypass is reachable via `check_file()` on a Python script that contains `instr.write('*RST; SOUR:VOLT 1000')`, because `check_script_text` extracts the entire string literal as a single SCPI command and passes it verbatim to `check_scpi_sequence`.

**Fix:** Split each command on semicolons before processing, then apply limit checks to each sub-command independently:

```python
# In check_scpi_sequence, replace direct processing with:
sub_commands = [s.strip() for s in cmd_stripped.split(';')]
for sub_cmd in sub_commands:
    # Apply INIT detection and limit checks to sub_cmd
```

---

### [HIGH-2] `FigureComposer.compose()` leaks matplotlib Figure on any rendering error

**File:** `maglab/figure/compose.py` lines 85–102

**Defect:** `compose()` allocates `fig = plt.figure(figsize=figsize)` inside `with plt.rc_context(rcparams):` and then iterates over panels. If any panel raises an exception during `_render_panel()` (most commonly `IntegrityError` from `_require_datapoints()`, or a `ValueError` from `_make_axes()`), the exception propagates out of the `with` block without `plt.close(fig)` ever being called. The figure object is returned to no one and orphaned in matplotlib's internal figure manager.

**Verified by probe:**

```python
initial = len(plt.get_fignums())   # 0
composer.compose(spec_with_bad_dp, {})  # raises IntegrityError
after = len(plt.get_fignums())     # 1  — LEAKED
```

In long-running CLI sessions or batch workflows this accumulates leaked figures and consumes memory.

The same pattern applies in `DataPlotRenderer.render_single()` (lines 348–352): `fig, ax = plt.subplots()` is called, then `render_panel()` raises `IntegrityError` before returning, and `fig` is never closed.

**Fix:** Wrap the figure lifetime in a try/except or use a context manager pattern:

```python
fig = plt.figure(figsize=figsize)
try:
    # ... render panels ...
    return fig
except Exception:
    plt.close(fig)
    raise
```

---

### [MEDIUM-1] SR830 SLVL voltage command not covered by voltage-limit check (false negative)

**File:** `maglab/instrument/safety.py` lines 191–207 (`_VOLT_PREFIXES`)

**Defect:** The SR830 safety profile correctly sets `max_voltage_v = 5.0` (the maximum sine output amplitude). However, the SR830's actual voltage output command is `SLVL` (Sine Level), not any variant of `VOLT`. `SLVL` does not appear in `_VOLT_PREFIXES`, so `SLVL 10` (10 V excitation, exceeding the 5 V limit) passes the safety gate silently.

**Verified by probe:**

```python
checker = SafetyChecker(get_profile('sr830'))
checker.check_scpi_sequence(['*RST', 'SLVL 10'])
# -> SafetyCheckResult(ok=True, violations=[])
# Expected: voltage_over_limit (10 V > 5 V)
```

The `max_voltage_v` field on the SR830 profile has no enforcement path for the SR830's real output command.

**Fix (two-part):** Either (a) add `"SLVL"` to `_VOLT_PREFIXES`, acknowledging that its semantics match the voltage limit, or (b) add an instrument-specific command→limit mapping to `SafetyProfile` so that the SR830 profile can map `SLVL` to the voltage limit. The simpler and immediately correct fix is (a).

---

### [MEDIUM-2] `_make_axes` span-overflow check is incomplete

**File:** `maglab/figure/compose.py` lines 121–126

**Defect:** `_make_axes()` validates that the panel's starting position is inside the grid:

```python
if pos.row >= nrows or pos.col >= ncols:
    raise ValueError(...)
```

But it does not validate that `row_end = pos.row + pos.row_span` or `col_end = pos.col + pos.col_span` remain within bounds. A panel with `row=0, row_span=3` in a `nrows=2` grid starts legally at row 0 but its span overflows. Matplotlib's `GridSpec` slicing silently clips the overshoot, resulting in the panel occupying only the available rows with no error and no warning. The rendered figure will not match the declared layout.

**Fix:** Add a span-end check after the start-position check:

```python
if row_end > nrows or col_end > ncols:
    raise ValueError(
        f"Panel '{panel.panel_id}': span [{pos.row}:{row_end}, {pos.col}:{col_end}] "
        f"exceeds layout bounds ({nrows}×{ncols})."
    )
```

---

### [MEDIUM-3] `VOLT:RANG` range-code false positive in voltage limit check

**File:** `maglab/instrument/safety.py` lines 287–319

**Defect:** `_VOLT_PREFIXES` includes the bare prefix `"VOLT"`, which matches `VOLT:RANG` (a measurement range configuration command on many instruments). `VOLT:RANG 10` sets the measurement range to mode-code 10 — it does not set an output voltage of 10 V — but the checker extracts `10` via `_extract_number()` and compares it to `max_voltage_v`. On the SR830 profile (limit 5 V), `VOLT:RANG 10` raises a false `voltage_over_limit` violation, blocking a valid configuration command.

**Fix:** Use a more specific prefix that excludes `VOLT:RANG`, `VOLT:RANG:AUTO`, and similar range-selection sub-commands, e.g. require that `VOLT` is immediately followed by whitespace or end-of-string (i.e. it is a direct value-setting command, not a sub-node). Alternatively, use a suffix exclusion list.

---

### [LOW-1] `SimVizRenderer.render_panel`: intermediate `fig_tmp` can leak on canvas draw failure

**File:** `maglab/figure/renderers/simviz.py` lines 685–699

**Defect:** `render_panel()` calls `render_2d` / `render_hsl` / `render_quiver`, each of which creates a new matplotlib figure `(fig_tmp, ax_tmp)`. The code then calls `fig_tmp.canvas.draw()` to rasterize and immediately calls `plt.close(fig_tmp)`. If `fig_tmp.canvas.draw()` raises an exception (e.g., due to a degenerate axes state), `plt.close(fig_tmp)` is never reached and `fig_tmp` is orphaned.

The outer catch in `compose.py` (line 178–191) catches the exception but does not have access to `fig_tmp` to close it.

**Fix:** Wrap the `fig_tmp` block:

```python
try:
    fig_tmp.canvas.draw()
    img_array = np.frombuffer(fig_tmp.canvas.tostring_rgb(), dtype=np.uint8)
    img_array = img_array.reshape(fig_tmp.canvas.get_width_height()[::-1] + (3,))
finally:
    plt.close(fig_tmp)
```

---

### [LOW-2] `_render_2d_numpy` and `_render_hsl_direct` crash on zero-dimension OVF files

**File:** `maglab/figure/renderers/simviz.py` lines 248–265, 375–384

**Defect:** When `_load_ovf_numpy()` parses an OVF file whose header reports `xnodes=0` (or `ynodes=0`, `znodes=0`), `n_expected = 0`. The reshape succeeds (`(0, 0, 0, 3)` is valid), but when `_render_2d_numpy` subsequently tries:

```python
idx = plane_index if plane_index is not None else m.shape[2] // 2  # = 0
slice_data = m[:, :, idx, 2]   # IndexError: index 0 is out of bounds for axis 2 with size 0
```

an `IndexError` is raised. This propagates through `render_panel` and is caught by `compose.py`'s broad exception handler, but it leaves a stale error text in the panel and an orphaned `fig_tmp`.

**Fix:** Add a guard after reshape in `_load_ovf_numpy`:

```python
if m.shape[0] == 0 or m.shape[1] == 0 or m.shape[2] == 0:
    raise ValueError(f"OVF file reports zero-size grid: ({nx}, {ny}, {nz})")
```

---

### [LOW-3] `check_script_text` misses write() calls when multiple appear on the same source line

**File:** `maglab/instrument/safety.py` lines 441–460

**Defect:** `check_script_text` uses `write_re.search(line)` (not `findall`) to extract SCPI commands. `re.search` returns only the first match per line. If a script contains:

```python
instr.write('*RST'); instr.write('SOUR:VOLT 300')
```

on one physical line, only `*RST` is extracted; `SOUR:VOLT 300` is silently omitted from validation. The voltage violation is not detected.

This is less severe than HIGH-1 because multiple `write()` calls on one line are uncommon style, and the docstring acknowledges limitations of static analysis. Still, it is an unannounced gap.

**Fix:** Replace `write_re.search(line)` with `write_re.findall(line)` (adjusting the extraction loop to iterate over all matches per line) or use `finditer`.

---

## Summary Table

| ID | Severity | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| HIGH-1 | HIGH | `instrument/safety.py` | 263–265 | Semicolon-chained SCPI command bypasses safety gate |
| HIGH-2 | HIGH | `figure/compose.py` | 85–102 | Figure leaked on rendering error |
| MEDIUM-1 | MEDIUM | `instrument/safety.py` | 191–207 | SR830 SLVL not in voltage-limit check (false negative) |
| MEDIUM-2 | MEDIUM | `figure/compose.py` | 121–126 | Grid span-overflow not detected |
| MEDIUM-3 | MEDIUM | `instrument/safety.py` | 287–319 | `VOLT:RANG N` falsely triggers voltage limit |
| LOW-1 | LOW | `figure/renderers/simviz.py` | 685–699 | `fig_tmp` leaks on canvas draw error |
| LOW-2 | LOW | `figure/renderers/simviz.py` | 248–265, 375–384 | Crash on zero-dimension OVF data |
| LOW-3 | LOW | `instrument/safety.py` | 441–460 | Only first `write()` per source line is checked |
