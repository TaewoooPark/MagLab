# Code Review Round 11 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-20
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit, targeted Python execution probes, API verification

---

## Verdict

**ISSUES FOUND** — 3 genuine defects. Max severity: LOW.

---

## R10 Fix Verification

**R10-F1 (`buffer_rgba()` replacement in `SimVizRenderer.render_panel()`):** Fixed and verified correct.

Lines 730–742 in `maglab/figure/renderers/simviz.py` now contain the replacement with a fix-banner comment:

```python
# R10-F1 fix: replaced fig_tmp.canvas.tostring_rgb() (removed in matplotlib
# 3.8) with the modern buffer_rgba() equivalent. ...
try:
    fig_tmp.canvas.draw()
    buf = np.frombuffer(fig_tmp.canvas.buffer_rgba(), dtype=np.uint8)
    img_array = buf.reshape(fig_tmp.canvas.get_width_height()[::-1] + (4,))[:, :, :3]
finally:
    plt.close(fig_tmp)
```

An execution probe on the installed matplotlib 3.10.8 confirms `buffer_rgba()` returns the correct `(500, 500, 3)` uint8 array. The `fig_tmp` is now also guaranteed to be closed inside the `try/finally` block even when `canvas.draw()` raises. The R10 fix is confirmed correct and complete.

---

## Findings

### Finding 1 — LOW | `maglab/figure/primitives/catalog/neel-domain-wall/primitive.py:72` | `ZeroDivisionError` when `wall_width=0`

**Defect.** `NeelDomainWallPrimitive._render_svg()` divides by `wall_width` without guarding against zero:

```python
t = (x - (total_w * 0.5 - wall_width / 2)) / wall_width  # line 72
```

If a caller passes `params={"wall_width": 0.0}` (or `0`), this raises `ZeroDivisionError`. The default is `120.0`, so this requires an explicit user override.

**Impact.** `assemble_svg()` in `schematic.py` wraps every `prim.render()` call in a `try/except Exception` (line 173), so the exception is caught, logged as a warning, and the primitive is replaced with `<!-- render error: neel-domain-wall -->` in the output SVG. No crash, no resource leak. The composed figure silently omits the primitive with a log warning but no user-visible error unless the caller inspects the SVG.

**Fix.** Add a guard at the top of `_render_svg`:

```python
wall_width = float(params.get("wall_width", 120.0))
if wall_width <= 0.0:
    wall_width = 1.0  # degenerate but non-crashing
```

---

### Finding 2 — LOW | `maglab/figure/primitives/catalog/bloch-domain-wall/primitive.py:128` | `ZeroDivisionError` when `wall_width=0`

**Defect.** Identical pattern to Finding 1. `BlochDomainWallPrimitive._render_svg()` line 128:

```python
t = (x - (total_w * 0.5 - wall_width / 2)) / wall_width
```

Same trigger (`wall_width=0`), same `ZeroDivisionError`, same catch-and-degrade impact as Finding 1.

**Fix.** Same guard as Finding 1: clamp `wall_width` to a minimum of `1.0` after extraction.

---

### Finding 3 — LOW | `maglab/figure/primitives/catalog/spin-texture-colorwheel/primitive.py:78` | `ZeroDivisionError` when `n_sectors=0`

**Defect.** `SpinTextureColorwheelPrimitive.render()` line 78:

```python
sector_angle = 360.0 / n
```

If a caller passes `params={"n_sectors": 0}` (or `0`), this raises `ZeroDivisionError`. The default is `36`, so this requires an explicit user override.

**Impact.** Same as Findings 1 and 2: caught by `assemble_svg()` `try/except`, degrades to error comment in output SVG. No crash or resource leak.

**Fix.** Add a guard after extracting `n`:

```python
n = max(1, int(params.get("n_sectors", 36)))
```

---

## Non-Findings

The following items were investigated adversarially and found to be correct or non-issues:

- **R10-F1 fix completeness:** The `try/finally` block at lines 736–742 of `simviz.py` now covers both `canvas.draw()` and `buffer_rgba()`. `plt.close(fig_tmp)` fires on any exception. No residual gap.
- **`buffer_rgba()` shape correctness:** Execution probe confirms `buf.reshape(get_width_height()[::-1] + (4,))[:, :, :3]` produces the expected `(h, w, 3)` uint8 array on matplotlib 3.10.8.
- **`render_3d()` plotter lifecycle (R9-F1 fix):** Confirmed at lines 614–652. The inner `try/finally` begins immediately after `pv.Plotter(off_screen=True)` and calls `plotter.close()` for every failure path including `add_mesh()`, `set_background()`, `add_axes()`, and `screenshot()`.
- **`render_quiver()` meshgrid shape vs U/V consistency:** Verified by execution probe. `np.meshgrid(xs, ys, indexing="ij")` with `indexing="ij"` produces `X.shape == U.shape == V.shape == C.shape` for all field sizes and subsample values. No shape mismatch.
- **`render_quiver()` figure leak when `show_hsl=False`:** `plt.subplots()` creates a figure; the subsequent `ax.quiver()` and `plt.colorbar()` calls operate on numpy arrays and effectively never raise. No practical leak risk.
- **`render_hsl()` / `render_2d()` figure leak:** No `try/finally` wrapping, but all post-`plt.subplots()` operations (imshow, colorbar, set_title) are infallible in practice. The figure is returned to the caller who is responsible for closing.
- **`FigureComposer.compose()` figure leak on error:** `plt.close(fig)` in the `except` branch at line 106. No leak.
- **`DataPlotRenderer.render_single()` figure leak on error:** `plt.close(fig)` in the `except` branch at line 356. No leak.
- **`FigureExporter.export()` `backend` parameter in `savefig()`:** Verified that `fig.savefig(..., backend='pdf')` and `fig.savefig(..., backend='ps')` are both valid and produce correct output on matplotlib 3.10.8 (documented in `savefig.__doc__`). Not a deprecated API.
- **`SchematicRenderer.render_to_file()` temp SVG file leak:** The `try/finally` at lines 417–421 calls `tmp_path.unlink()` via `contextlib.suppress(OSError)`. Always cleaned up. No leak.
- **`assemble_svg()` / `_empty_svg()` XML comment injection:** `provenance.replace("--", "__")` and `panel_id.replace("--", "__")` prevent `--` sequences in XML comments. Safe.
- **`_extract_xy()` length-2 with scalar DataPoints:** For `len(dps)==2` where both are scalars, `np.asarray([scalar])` produces single-point arrays. The plot renders as a single marker. Not the most useful output, but not a crash or integrity violation.
- **`SafetyChecker.check_scpi_sequence()` compound semicolon handling:** Verified that `*RST; SOUR:VOLT 5000` correctly checks both sub-commands. `*RST` sets `initialized=True` and `continues`; `SOUR:VOLT 5000` is then checked against limits. Control flow is correct.
- **`SafetyChecker` `OUTPUT_ACTIVE_PARAM_CHANGE` ordering:** Confirmed that `OUTP ON` (`_OUTPUT_ON_RE.search()`) hits the `continue` before the param-change check, so the output activation command is never incorrectly flagged as a param change while active.
- **`SCPIIndex.build()` sqlite3 connection lifecycle:** The `with sqlite3.connect(...) as conn:` context manager commits on clean exit; `conn` is closed by garbage collection immediately after the `with` block in CPython. Not a functional leak.
- **`SCPIIndex.load()` vocab-restore ordering:** Vocab sidecar is restored before the dimension probe, so TF-IDF→TF-IDF cross-session reloads produce the correct corpus-sized dimension. Correct.
- **`ManualExtractor` section_stack management:** Depth calculation `header_num.count(".")` correctly handles nested sections: `"1"→depth=0`, `"1.1"→depth=1`, `"1.1.1"→depth=2`. The `while len(stack) > depth: stack.pop()` correctly trims before appending. No off-by-one.
- **`_load_ovf_numpy()` zero-size grid guard:** `nx==0 or ny==0 or nz==0` raises `ValueError` before the reshape, preventing ZeroDivisionError. Correct.
- **`_load_ovf_numpy()` truncate/pad reshape:** Handles over-length and under-length data. Correct.
- **`CatalogRegistry.load()` hyphenated module names in `sys.modules`:** Verified by execution probe that `sys.modules["maglab._catalog.hall-bar"]` works correctly — `sys.modules` is a plain dict and accepts any string key. Dynamic import of all hyphenated primitives succeeds.
- **`_parse_primitive_md()` tag regex `[\w·/\-]+`:** Correctly handles hyphens, slashes, and multi-word tag entries like `"magnetic tunnel junction"` (split into individual words, which is acceptable for keyword search).
- **`_model_to_class_name()` SR-830 docstring inaccuracy:** The function produces `"Sr830"` for `"SR-830"` (not `"SR830"` as the docstring example claims). However, `"Sr830"` is a valid Python identifier and `capitalize()` is deterministic. This is a docstring inaccuracy, not a functional defect.
- **`HallBarPrimitive` / `MTJPillarPrimitive` / `MultilayerStackPrimitive` color injection:** `html.escape(color, quote=True)` applied at all color attribute insertion points. Safe.
- **`BlochDomainWallPrimitive` color injection:** `html.escape(color_up, quote=True)` and `html.escape(color_down, quote=True)` applied. The computed `arr_color = f"rgb({r_c},{g_c},{b_c})"` uses `int()` arithmetic on bounded floats — safe.
- **`NeelDomainWallPrimitive` / `BlochSkyrmionPrimitive` `arr_color`:** `rgb(int, int, int)` strings computed from bounded arithmetic. No injection possible.
- **`SpinTextureColorwheelPrimitive` `_hsl_to_hex()` output:** Returns `#RRGGBB` hex strings from `int()` arithmetic — always safe SVG color values.
- **`LLGPrecessionPrimitive` division safety:** No user-controlled division. `prec_rx = radius * math.sin(theta)` uses bounded `sin()`. Safe.
- **`MeasurementGeometryPrimitive` division safety:** No division operations. `r = size * 0.35` is multiplication. Safe.
- **`ManualSearcher._try_download()` path traversal:** `re.sub(r"[^\w\-]", "_", ...)` sanitizes both manufacturer and model before path construction. Safe.
- **`SkillGenerator._write_skill_md()` YAML frontmatter injection:** String values use `f"{k}: {v!r}"` (repr-quoted). Boolean values use explicit `.lower()` strings. No YAML injection possible.
- **`SweepConfig.step_must_be_nonzero` validator:** Rejects `step=0.0` at model construction time. Correct.
- **`_TFIDFFallback.embed()` dimension guard:** `dim = max(len(self._vocab), 1)` prevents zero-length vectors. Correct.
- **`StyleProfile.rcparams()` `KeyError` on missing YAML keys:** All four YAML files contain the required `column_width_mm`, `font_size_pt`, `line_width_pt`, and `palette` keys. Verified by direct YAML inspection.
- **`_make_prop_cycle()` with empty palette:** `cycler("color", [])` does not raise — returns an empty cycler that matplotlib handles gracefully. All four style YAML files have 8-color palettes.
- **`measurement_script.py.j2` `instr` VISA resource leak on exception:** Pre-existing template design choice noted in R10. The `finally: rm.close()` closes the ResourceManager; `instr` may not be closed on failure paths between `open_resource()` and `instr.close()`. Accepted per the template's stated "human must review before execution" purpose.

---

## Summary Table

| # | Severity | File | Location | Issue |
|---|----------|------|----------|-------|
| 1 | LOW | `figure/primitives/catalog/neel-domain-wall/primitive.py` | line 72 | `ZeroDivisionError` when `wall_width=0` — caught by `assemble_svg` try/except, degrades to SVG error comment |
| 2 | LOW | `figure/primitives/catalog/bloch-domain-wall/primitive.py` | line 128 | `ZeroDivisionError` when `wall_width=0` — same pattern as Finding 1 |
| 3 | LOW | `figure/primitives/catalog/spin-texture-colorwheel/primitive.py` | line 78 | `ZeroDivisionError` when `n_sectors=0` — caught by `assemble_svg` try/except, degrades to SVG error comment |
