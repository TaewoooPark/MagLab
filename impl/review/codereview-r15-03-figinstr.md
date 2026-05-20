# Code Review Round 15 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-20
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Fresh read-only source audit of every file, static control-flow tracing, edge-case simulation

---

## Verdict

**FIXED** — 1 genuine defect found and patched.

---

## R14 Fix Verification

The R14 fix is present and correct.

**R14-F1 (`dataplot.py:_extract_xy()` — shape mismatch in 2-DataPoint panel):**
Confirmed at lines 99–113 of `maglab/figure/renderers/dataplot.py`. The guard reads:

```python
if x.shape != y.shape:
    raise ValueError(
        f"DataPoint shape mismatch in 2-DataPoint panel: "
        f"x has shape {x.shape} (DataPoint '{dps[0].id}') but "
        f"y has shape {y.shape} (DataPoint '{dps[1].id}'). "
        "Both DataPoints must produce arrays of equal length."
    )
```

All five R14 regression tests (`TestR14Finding1ExtractXYShapeMismatch`) pass without modification.

---

## Findings & Fixes

### Finding 1 — MEDIUM | `maglab/figure/renderers/dataplot.py:136` | `_extract_xy()` multi-DataPoint branch raises cryptic `IndexError` on empty-list DataPoint value

**Defect.** The `_extract_xy()` fallback branch (entered when `len(dps) >= 3`, or `len(dps) >= 2` and not all inputs are the same length) handles list-valued DataPoints by extracting only the first element:

```python
if isinstance(dp.value, list):
    warnings.warn(...)
    ys.append(float(dp.value[0]))  # ← IndexError when dp.value == []
```

When `dp.value` is an empty list (`[]`), `dp.value[0]` raises:

```
IndexError: list index out of range
```

This error provides no diagnostic information — no DataPoint ID, no panel ID, no indication of which binding is problematic. A user who accidentally records an empty measurement array into a DataPoint and then tries to plot three DataPoints together sees only a bare `IndexError` with no path to the offending binding.

**Reproducibility.** Confirmed via direct simulation:

```python
val = []
float(val[0])  # → IndexError: list index out of range
```

**Impact.** Any `DataPlotRenderer.render_panel()` call on a panel with 3+ DataPoints where one DataPoint holds an empty list (`value=[]`) raises a cryptic `IndexError`. The R14-F1 shape-mismatch check does not cover this case (it guards the `len(dps) == 2` branch only). A user building a multi-point calibration series where one channel returned no samples would see an undiagnosed exception.

**Fix applied (`maglab/figure/renderers/dataplot.py`, before line 136):**

```python
# R15-F1 fix: guard against an empty list before indexing.
# dp.value[0] on an empty list raises IndexError with no diagnostic
# context (no DataPoint ID or file info). Raise a clear ValueError
# here instead so the caller can identify the offending binding.
if len(dp.value) == 0:
    raise ValueError(
        f"DataPoint '{dp.id}' has an empty list value in a multi-DataPoint "
        "panel. Cannot extract the first element for plotting. "
        "Ensure the DataPoint value is a non-empty list or a scalar."
    )
```

**Regression tests added (`tests/unit/test_figure_dataplot.py`, class `TestR15Finding1ExtractXYEmptyListMultiDP`):**

Four tests covering:
1. `test_empty_list_in_3dp_branch_raises_clear_error` — 3-DataPoint panel with one empty-list DataPoint → `ValueError` with `"empty list"`.
2. `test_empty_list_message_contains_dp_id` — error message includes the offending DataPoint's ID.
3. `test_nonempty_list_in_3dp_branch_warns_and_succeeds` — non-empty list DataPoint in 3-DP panel still warns (existing behavior preserved) and succeeds.
4. `test_all_scalars_in_3dp_branch_succeeds` — three scalar DataPoints in the fallback path succeed without error (regression guard).

---

## Non-Findings

The following items were adversarially investigated and found to be non-issues:

- **R14-F1 completeness:** `x.shape != y.shape` guard in the 2-DataPoint branch is correct and remains intact.
- **R13-F1 completeness:** `arrow_svg()` up/down branches in `mtj-pillar/primitive.py` are correct and tested.
- **R12-F1 completeness:** `color="{arr_color}"` on every `<line>` in `bloch-domain-wall/primitive.py`. Confirmed correct.
- **R11-F1/F2/F3 zero-divisor clamps:** All three remain intact.
- **`_extract_xy()` len(dps) >= 3, non-empty list DataPoint:** `dp.value[0]` on a non-empty list is safe; the existing `UserWarning` fires and the first element is used. Not broken by R15-F1 fix.
- **`_extract_xy()` len(dps) == 1, empty list:** `v = []`, `isinstance(v, list)=True`, `y = np.asarray([], dtype=float)`, `x = np.arange(0)`. Both empty arrays. `ax.plot([], [])` is a matplotlib no-op. Safe.
- **`_load_ovf_numpy()` `int(header.get("xnodes", 1))`:** If a non-conformant OVF file writes `xnodes: 4.0` (float string), `int("4.0")` raises `ValueError`. However, OVF 1.0 and 2.0 specifications mandate integer xnodes/ynodes/znodes, and all standard OVF writers (OOMMF, MuMax3) emit integer strings. This is a theoretical edge case for non-conformant files and does not qualify as a genuine defect; it is a low-priority robustness limitation. Not fixed here.
- **`assemble_svg()` `provenance.replace("--", "__")`:** XML comment injection guard intact.
- **`SchematicRenderer.render_to_file()` temp SVG leak:** `try/finally` with `contextlib.suppress(OSError)`. Confirmed correct.
- **`DataPlotRenderer.render_single()` figure leak on exception:** `plt.close(fig)` in `except` block. Confirmed correct.
- **`SimVizRenderer.render_panel()` `fig_tmp` leak in `finally`:** `plt.close(fig_tmp)` in `finally`. Confirmed intact.
- **`render_3d()` plotter lifecycle:** `try/finally: plotter.close()` covers the entire lifecycle. Confirmed intact.
- **`SCPIIndex.build()` connection lifecycle:** `with sqlite3.connect(...) as conn:` closes on exit. Correct.
- **`SCPIIndex.load()` vocab restore ordering:** TF-IDF vocab restored before dimension probe. Confirmed intact.
- **`SafetyChecker.check_scpi_sequence()` compound semicolon handling:** All sub-commands checked independently. Correct.
- **`ManualSearcher._try_download()` path traversal:** `re.sub(r"[^\w\-]", "_", ...)` applied to manufacturer and model. Safe.
- **`SweepConfig.step_must_be_nonzero` validator:** Rejects `step=0.0` at construction time. Correct.
- **`_model_to_class_name()` empty/all-special-char input:** `result=""`, guarded by `result or "GenericInstrument"`. Safe.
- **`BlochDomainWallPrimitive` color injection:** `color_up_attr` / `color_down_attr` escaped with `html.escape(quote=True)`. Safe.
- **`HallBarPrimitive` color injection:** `color_attr = html.escape(color, quote=True)`. Safe.
- **`MultilayerStackPrimitive` color injection:** `color_attr = html.escape(color, quote=True)`. Safe.
- **`CoordinateAxesPrimitive` color injection:** `cx_col`, `cy_col`, `cz_col` escaped with `html.escape(..., quote=True)`. Safe.
- **`NeelDomainWallPrimitive` `arr_color` injection:** Always computed as `f"rgb({r_c},{g_c},{b_c})"` from integer arithmetic. Not user-controlled. Safe.
- **`BlochSkyrmionPrimitive` `arr_color` injection:** Same `rgb(...)` pattern. Safe.
- **`LLGPrecessionPrimitive` color injection:** All colors hardcoded. No user-controlled strings. Safe.
- **`MeasurementGeometryPrimitive` color injection:** All colors hardcoded in marker defs. Safe.
- **`MTJPillarPrimitive` label injection:** Label is always `""` at both `arrow_svg()` call sites. Not exploitable. Confirmed.
- **`_cosine_similarity()` zero-vector guard:** `if norm_a == 0 or norm_b == 0: return 0.0`. Confirmed safe.
- **`_TFIDFFallback.embed([])` edge case:** Returns `[]`. Safe.
- **`SkillGenerator._write_skill_md()` SCPI cmd in Markdown:** `c.cmd` appears inside a backtick code span; no markdown injection risk.
- **`NeelDomainWallPrimitive` `fill="inherit"` in SVG marker:** Uses `fill="inherit"` in `<path>` within `<marker>`. In SVG, `inherit` in a marker context is implementation-defined (different from `currentColor`), which may render arrowheads in black on some renderers. This is a rendering quality concern, not a crash or security defect. Pre-existing behavior — not introduced in any recent round.

---

## Verification

### ruff

```
$ .venv/bin/ruff check maglab/figure/renderers/dataplot.py tests/unit/test_figure_dataplot.py
All checks passed!
```

### mypy

```
$ .venv/bin/mypy maglab/figure/ maglab/instrument/ --ignore-missing-imports
Success: no issues found in 21 source files
```

### pytest

```
$ .venv/bin/python -B -m pytest -q tests/unit/test_figure_*.py tests/unit/test_instrument_*.py --timeout=120
404 passed, 19 warnings in 100.53s
```

(Prior baseline after R14: 263 passed. 4 new regression tests added for R15-F1. Full count includes all previously accumulated tests across all review rounds.)
