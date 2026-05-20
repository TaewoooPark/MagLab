# Code Review Round 14 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-20
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Fresh read-only source audit of every file, static control-flow tracing, numerical simulation of edge cases

---

## Verdict

**FIXED** — 1 genuine defect found and patched.

---

## R13 Fix Verification

The R13 fix is present and correct.

**R13-F1 (`MTJPillarPrimitive.arrow_svg()` — silent empty SVG for `"up"`/`"down"` directions):**
The `arrow_svg()` inner function now implements all four direction branches. Confirmed at lines 124–143 of `maglab/figure/primitives/catalog/mtj-pillar/primitive.py`:

- `"up"` branch (lines 124–133): constructs a vertical `<line>` with `x1=ax, x2=ax` (x-coords equal) and `y2 < y1` (tip above tail in SVG coordinates, arrowhead points upward).
- `"down"` branch (lines 135–143): constructs a vertical `<line>` with `x1=ax, x2=ax` and `y2 > y1` (arrowhead points downward).
- Both branches correctly reference `marker-end="url(#arrMTJ)"`. The marker uses `orient="auto"`, so the arrowhead rotates to face the tip endpoint automatically.
- The docstring on `arrow_svg()` is accurate and complete (lines 89–107).
- All R13 regression tests (`TestR13Finding1MTJPillarVerticalArrow`) pass without modification.

All previously confirmed fixes (R11 zero-divisor clamps, R12 Bloch arrowhead `color=` attribute) remain intact.

---

## Findings & Fixes

### Finding 1 — MEDIUM | `maglab/figure/renderers/dataplot.py:94-99` | `_extract_xy()` produces array-shape mismatch that silently propagates to matplotlib

**Defect.** The `_extract_xy()` function handles the 2-DataPoint case (lines 94–99) by converting each DataPoint's value independently:

```python
x = np.asarray(x_raw if isinstance(x_raw, list) else [x_raw], dtype=float)
y = np.asarray(y_raw if isinstance(y_raw, list) else [y_raw], dtype=float)
return x, y
```

When `dps[0].value` is a list of N elements and `dps[1].value` is a scalar (or vice-versa), this yields `x.shape=(N,)` and `y.shape=(1,)` (or the reversed pair). The mismatched arrays are returned without any check and passed directly to `matplotlib.axes.Axes.plot()`, which raises:

```
ValueError: x and y must have same first dimension, but have shapes (3,) and (1,)
```

This error originates deep inside matplotlib and does not identify which DataPoints are involved or why, making it very hard to diagnose. The same path is triggered for two list-valued DataPoints of different lengths (e.g. `N=3` vs `M=5`).

**Reproducibility.** Verified via simulation:

```python
x = np.asarray([1.0, 2.0, 3.0], dtype=float)  # from dp[0].value=[1,2,3]
y = np.asarray([5.0], dtype=float)             # from dp[1].value=5.0
ax.plot(x, y)   # → ValueError (cryptic)
```

**Impact.** Any `DataPlotRenderer.render_panel()` call where the two DataPoints have incompatible array lengths raises a cryptic internal matplotlib ValueError with no diagnosis. The error is not caught or re-wrapped anywhere in the renderer stack, so it propagates as an unhandled exception.

**Fix applied (`maglab/figure/renderers/dataplot.py`, lines 99–109):**

```python
# R14-F1 fix: detect shape mismatch before passing to matplotlib.
# When one DataPoint holds an N-element array and the other a scalar,
# the code above yields x.shape=(N,) vs y.shape=(1,) (or vice-versa).
# Similarly, two list-valued DataPoints of different lengths produce
# x.shape=(N,) and y.shape=(M,) with N≠M.  In either case matplotlib
# raises a cryptic ValueError("x and y must have same first dimension").
# Raise a clear ValueError here instead so the caller receives a
# diagnostic message that identifies the data-binding issue.
if x.shape != y.shape:
    raise ValueError(
        f"DataPoint shape mismatch in 2-DataPoint panel: "
        f"x has shape {x.shape} (DataPoint '{dps[0].id}') but "
        f"y has shape {y.shape} (DataPoint '{dps[1].id}'). "
        "Both DataPoints must produce arrays of equal length."
    )
```

**Regression tests added (`tests/unit/test_figure_dataplot.py`, class `TestR14Finding1ExtractXYShapeMismatch`):**

Five tests covering:
1. `test_list_x_scalar_y_raises_clear_error` — list(3) vs scalar → `ValueError` with `"shape mismatch"`.
2. `test_scalar_x_list_y_raises_clear_error` — scalar vs list(3) → same.
3. `test_list_x_list_y_same_length_no_error` — list(3) vs list(3) → no error.
4. `test_scalar_x_scalar_y_no_error` — scalar vs scalar → no error (single point plot).
5. `test_mismatched_list_lengths_raises_clear_error` — list(3) vs list(5) → `ValueError` with `"shape mismatch"`.

---

## Non-Findings

The following items were adversarially investigated and found to be non-issues:

- **R13-F1 completeness:** `arrow_svg()` up/down branches are correctly implemented and tested. Confirmed correct.
- **R12-F1 completeness:** `color="{arr_color}"` on every `<line>` in `bloch-domain-wall/primitive.py` line 156. Confirmed correct.
- **R11-F1/F2/F3 zero-divisor clamps:** All three remain intact — `wall_width` clamped in both `neel-domain-wall` and `bloch-domain-wall`, `n_sectors` clamped in `spin-texture-colorwheel`.
- **`NeelDomainWallPrimitive` n_spins=−1:** `int(-1) = -1`, `range(-1)` is empty, list comprehension body never evaluates. Safe.
- **`BlochDomainWallPrimitive` n_spins=−1:** Same pattern. Safe.
- **`MTJPillarPrimitive` direction="" (unknown):** `arrow_svg()` returns `""` — silently ignored. This is the only remaining silent-ignore branch; it is pre-existing design (not newly introduced) and affects only truly unrecognized strings, not documented API values.
- **`MTJPillarPrimitive` label injection in arrow_svg():** Label is always passed as `""` at both call sites (lines 164 and 187). Not exploitable. R13 non-finding confirmed.
- **`_extract_svg_body` greedy regex in `schematic.py:86`:** The regex `r"<svg[^>]*>(.*)</svg>"` is greedy with `re.DOTALL`. No MagLab primitive SVG contains nested `<svg>` elements, so the greedy match always captures the entire body correctly. No defect.
- **`_model_to_class_name()` empty-string input:** `cleaned=""`, `parts=[]`, `result=""`, guarded by `result or "GenericInstrument"` at call site. Safe.
- **`_model_to_class_name()` all-special-char input:** Same empty-result path. Safe.
- **`SpinTextureColorwheelPrimitive` n_sectors=1:** `sector_angle=360.0`, `large=1` (arc-flag), single full-circle sector. Produces valid (if unusual) SVG. Safe.
- **`BlochDomainWallPrimitive` color injection:** `color_up_attr` and `color_down_attr` escaped with `html.escape(quote=True)` at lines 103–104. Used in rect fill attributes. Safe.
- **`NeelDomainWallPrimitive` color injection:** `arr_color` is always computed as `f"rgb({r_c},{g_c},{b_c})"` from integer arithmetic — never user-controlled. Safe.
- **`BlochSkyrmionPrimitive` color injection:** `core_color` hardcoded, `arr_color` computed as `f"rgb({r_c},{g_c},{b_c})"`. No user-controlled strings. Safe.
- **`LLGPrecessionPrimitive` color injection:** All colors hardcoded (`#0055CC`, `#CC0000`, `#888`, `#666`, `#CCC`, `#F8F8FF`). No user-controlled strings. Safe.
- **`MeasurementGeometryPrimitive` color injection:** All colors hardcoded in marker defs and line elements. No user-controlled color parameters. Safe.
- **`_extract_xy()` len(dps)==1 with empty list:** `v = []`, `isinstance(v, list)=True`, `y = np.asarray([], dtype=float)`, `x = np.arange(0, dtype=float)`. Both empty arrays. `ax.plot([], [])` is a no-op in matplotlib. Safe (no crash).
- **`_extract_xy()` len(dps)==0:** Never reached — `_require_datapoints()` raises `IntegrityError` before `_extract_xy` is called when `data_point_ids` is empty. Safe.
- **`DataPlotRenderer.render_single()` figure leak on exception:** `plt.close(fig)` in the `except` block at lines 352–357. Confirmed correct (R-prior fix, still intact).
- **`_load_ovf_numpy()` zero-size grid guard:** `if nx == 0 or ny == 0 or nz == 0: raise ValueError(...)` at line 146. Confirmed intact.
- **`SCPIIndex.build()` connection lifecycle:** `with sqlite3.connect(...) as conn:` closes on exit; explicit `conn.commit()` for forward compatibility. Correct.
- **`SCPIIndex.load()` vocab restore ordering:** TF-IDF vocab restored before dimension probe. Confirmed intact (R8-F1 fix).
- **`SafetyChecker.check_scpi_sequence()` compound semicolon handling:** All sub-commands checked independently. Confirmed correct (R11 finding, re-verified).
- **`SafetyChecker` `OUTPUT_ACTIVE_PARAM_CHANGE` ordering:** `OUTP ON` hits `continue` before param-change check; output activation is never mis-flagged. Confirmed correct.
- **`ManualSearcher._try_download()` path traversal:** `re.sub(r"[^\w\-]", "_", ...)` applied to both `manufacturer` and `model` before filename construction. Safe.
- **`SweepConfig.step_must_be_nonzero` validator:** Rejects `step=0.0` at Pydantic construction time. Confirmed correct.
- **`render_3d()` plotter lifecycle:** `try/finally: plotter.close()` wraps the entire plotter lifecycle from construction. Confirmed intact (R9-F1 fix).
- **`SimVizRenderer.render_panel()` figure leak in finally:** `plt.close(fig_tmp)` in `finally` at lines 741–742. Confirmed intact (R10-F1 fix).
- **`assemble_svg()` provenance XML injection:** `provenance.replace("--", "__")` prevents malformed XML comments. Confirmed correct.
- **`SchematicRenderer.render_to_file()` temp SVG leak:** `try/finally` with `contextlib.suppress(OSError)` ensures cleanup. Confirmed correct.
- **`_TFIDFFallback.embed([])` edge case:** `range(0)` produces empty loop; `dim = max(0, 1) = 1`; returns `[]`. Safe.
- **`_cosine_similarity()` zero-vector guard:** `if norm_a == 0 or norm_b == 0: return 0.0`. Confirmed safe.

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
263 passed, 19 warnings in 87.50s
```

(Prior baseline: 258 passed. 5 new regression tests added for R14-F1.)
