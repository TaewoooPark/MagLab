# Code Review Round 10 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-20
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit, targeted Python execution probes, matplotlib API verification

---

## Verdict

**ISSUES FOUND** — 1 genuine defect. Max severity: HIGH.

---

## R9 Fix Verification

The R9-F1 fix is confirmed present and correct.

**R9-F1 (`render_3d()` full plotter lifecycle in `try/finally`):** Fixed. Lines 622–652 in `maglab/figure/renderers/simviz.py` now expand the `try/finally` to begin immediately after `pv.Plotter(off_screen=True)` is constructed, covering `add_mesh()`, `set_background()`, `add_axes()`, the temp-path setup, and `screenshot()` — with the `finally: plotter.close()` guaranteed to execute for any failure at any point. The fix banner comment at lines 615–621 accurately describes the ordering rationale. Confirmed correct. The residual gap identified in R9 is fully closed.

---

## Findings

### Finding 1 — HIGH | `maglab/figure/renderers/simviz.py:735` | `tostring_rgb()` removed in matplotlib 3.8 — unconditional crash on any modern installation

**Defect.** `SimVizRenderer.render_panel()` at line 735 calls:

```python
img_array = np.frombuffer(fig_tmp.canvas.tostring_rgb(), dtype=np.uint8)
```

`FigureCanvasAgg.tostring_rgb()` was deprecated in matplotlib 3.4 and **removed in matplotlib 3.8** (released November 2023). The environment under test uses matplotlib 3.10.8. Calling this method raises `AttributeError: 'FigureCanvasAgg' object has no attribute 'tostring_rgb'` unconditionally. The call is confirmed to fail with a direct execution probe:

```
FAIL - AttributeError: 'FigureCanvasAgg' object has no attribute 'tostring_rgb'
```

**Realistic trigger:** Any call to `SimVizRenderer.render_panel()` or `FigureComposer.compose()` with a `PanelType.SIM_VIZ` panel using a `render_type` of `"2d"`, `"hsl"`, or `"quiver"`. The 3D render path (`render_type="3d"`) is not affected because it calls `render_3d()` instead of entering this code path. This is therefore a complete functional regression for all 2D/HSL/quiver SIM_VIZ panel rendering on matplotlib >= 3.8.

**Impact.** The `try/finally` block at lines 732–738 means `fig_tmp` is correctly closed via `plt.close(fig_tmp)` even when the `AttributeError` is raised. There is no resource leak. However, the `AttributeError` propagates out of `render_panel()`. In `FigureComposer._render_panel()` (compose.py line 192), this exception is caught and logged, displaying an error placeholder instead of the rendered panel — so composed figures silently degrade. When `render_panel()` is called directly by user code (not through composer), the unhandled `AttributeError` crashes the caller entirely. Either way, 2D SIM_VIZ rendering is completely broken on any installation using matplotlib >= 3.8.

**Fix.** Replace `tostring_rgb()` with `buffer_rgba()` and drop the alpha channel:

```python
# Old (removed in matplotlib 3.8):
img_array = np.frombuffer(fig_tmp.canvas.tostring_rgb(), dtype=np.uint8)
img_array = img_array.reshape(fig_tmp.canvas.get_width_height()[::-1] + (3,))

# New (correct for matplotlib >= 3.8):
buf = np.frombuffer(fig_tmp.canvas.buffer_rgba(), dtype=np.uint8)
img_array = buf.reshape(fig_tmp.canvas.get_width_height()[::-1] + (4,))[:, :, :3]
```

`buffer_rgba()` returns a flat RGBA buffer of shape `(h * w * 4,)`. Reshaping to `(h, w, 4)` and slicing `[:, :, :3]` produces an identical `(h, w, 3)` uint8 array to what `tostring_rgb()` previously returned. `get_width_height()[::-1]` correctly yields `(h, w)` and remains unchanged. Verified to produce the correct `(480, 640, 3)` shape in the probe environment.

---

## Non-Findings

The following items were investigated adversarially and found to be correct or non-issues:

- **R9-F1 fix (full plotter lifecycle in `try/finally`):** Confirmed correct at lines 614–652. `plotter.close()` now fires for any failure in `add_mesh()`, `set_background()`, `add_axes()`, or `screenshot()`. No residual gap.
- **`render_3d()` double `plotter.close()` risk:** Not present. The inner `finally` runs `plotter.close()` exactly once on all paths (normal exit, `screenshot()` exception, `add_mesh()`/setup exception). The outer `except Exception` at line 656 does not re-call `close()`.
- **`SimVizRenderer.render_panel()` fig_tmp leak when `tostring_rgb()` raises:** `plt.close(fig_tmp)` is in the `finally` block (line 738) and runs before the `AttributeError` propagates. No leak.
- **`_render_2d_numpy()` off-by-one in plane_index:** Defaults are `m.shape[dim] // 2` for 0-based indexing. For a 10-element axis, default is index 5 — the center element. Correct.
- **`_load_ovf_numpy()` robust reshape:** Truncate-or-pad logic at lines 154–158 correctly handles over-length and under-length data. The zero-size guard at line 145 prevents ZeroDivisionError/reshape errors. Correct.
- **`render_hsl()` / `_render_hsl_direct()` AttributeError fallback:** When `field_data.array` raises `AttributeError`, falls back to `np.zeros((10, 10, 1, 3))` with `m[:,:,0,0] = 1.0`. The synthetic field produces a valid but flat rendering. Correct and intentional.
- **`render_quiver()` `show_hsl=True` figure leak:** When `show_hsl=True`, `render_hsl()` creates a figure that is returned as `fig`. The function returns `(fig, ax)` to the caller — no double-creation or leak. Correct.
- **`FigureComposer.compose()` figure leak on error:** The outer `except Exception` at line 102 calls `plt.close(fig)` before re-raising. The `with plt.rc_context(rcparams):` `__exit__` runs regardless. No leak.
- **`DataPlotRenderer.render_single()` figure leak on error:** `plt.close(fig)` in the `except` branch at line 356, then re-raise. No leak.
- **`SchematicRenderer.render_to_file()` temp SVG file leak:** The `try/finally` at lines 417–421 calls `tmp_path.unlink()` in the `finally` block using `contextlib.suppress(OSError)`. The temp file is always cleaned up regardless of `svg_to_pdf()` success or failure. Correct.
- **`assemble_svg()` / `_empty_svg()` XML comment injection:** `provenance.replace("--", "__")` and `panel_id.replace("--", "__")` prevent `--` sequences from appearing inside XML comments. Correct.
- **`CatalogRegistry.load()` dynamic import — path traversal:** Module name is `maglab._catalog.<name>` where `<name>` comes from the developer-controlled catalog directory (iterated by `catalog_dir.iterdir()`). No user input flows into `sys.modules` key or `spec_from_file_location`. Safe.
- **`_parse_primitive_md()` malformed frontmatter:** Falls back to `{"name": md_path.parent.name, ...}` when there is no `---` delimiter. Lines without `:` are skipped. No crash on malformed input.
- **`SafetyChecker.check_scpi_sequence()` compound semicolon splitting:** Confirmed that all sub-commands of `"*RST; SOUR:VOLT 5000"` are individually checked. `*RST` sets `initialized=True` and `continue`s; `SOUR:VOLT 5000` is then checked against voltage limits. Correct.
- **`SafetyChecker.check_scpi_sequence()` `output_active` state after `*RST` in compound:** The `_INIT_RE` match also sets `output_active = False`. A compound `"OUTP ON; *RST"` would activate then deactivate (in sub-command order). Correct — `*RST` resets state.
- **`SafetyChecker.check_script_text()` lineno correction for duplicate sub-commands:** When the same sub-command text (e.g., `"SOUR:VOLT 5"`) appears in two compound strings on different lines, `setdefault` preserves the first (earliest) line number. A violation on the second occurrence is reported at the first line. This is a diagnostic inaccuracy (wrong line number in the report) but is NOT a safety failure — the violation IS detected and flagged. Acceptable limitation of static text analysis; not a functional defect.
- **`_TFIDFFallback.embed()` dimension 0 guard:** `dim = max(len(self._vocab), 1)` prevents `[0.0] * 0` from producing an empty vector. Correct.
- **`_cosine_similarity()` dimension mismatch truncation:** `min_dim = min(len(a), len(b))` truncation when lengths differ is a silent semantic degradation, but it is an intentional design choice (with a warning emitted by `SCPIIndex.load()`). Not a defect introduced in R10.
- **`ManualSearcher._try_download()` PDF magic byte check:** `content[:4] != b"%PDF"` guard rejects non-PDF HTTP responses. Combined with `re.sub(r"[^\w\-]", "_", ...)` filename sanitization, no path traversal is possible. Safe.
- **`ScriptGenerator.generate()` `skip_safety_check=True`:** Only accessible via `ScriptGenerator.generate()` — not exposed in the public `generate_measurement_script()` convenience function. No unsafe default path. Safe.
- **`SweepConfig.step_must_be_nonzero` validator:** Rejects `step=0.0` at model construction time, preventing `ZeroDivisionError` in the generated `np.arange()` loop. Correct.
- **`_model_to_class_name()` empty model edge case:** Returns `""` for empty/whitespace-only input; `generate_scaffold()` applies `or "GenericInstrument"` fallback. Safe.
- **`MockResource._generate_response()` regex on unchecked user input:** `cmd` comes from the test harness's own `write()`/`query()` calls — not from external user input. No injection risk.
- **`SkillGenerator._write_skill_md()` YAML frontmatter serialization:** String values use `f"{k}: {v!r}"` (repr-quoted) and boolean values use explicit `.lower()` strings. No YAML injection possible from model/manufacturer strings.
- **`SkillGenerator._write_scpi_reference()` pipe in `c.cmd`:** `c.cmd` is wrapped in backtick code span in a GFM table cell. Pipe inside code spans is treated as literal by compliant renderers. Not a defect.
- **`StyleProfile.rcparams()` KeyError on missing `column_width_mm`:** All four YAML style files are developer-controlled and contain `column_width_mm`. Not a user-facing risk.
- **`FigureSpec._collect_provenance()` model mutation with `frozen=False`:** Intentional and documented. `model_config = {"frozen": False}` explicitly allows this. Correct.
- **`BlochSkyrmionPrimitive.render()` arithmetic safety:** `sz_core`, `r_c`, `g_c`, `b_c` all use `int()`-bounded arithmetic from `math.cos()` which is bounded to `[-1, 1]`. No overflow or NaN risk.
- **`SVG color escaping` in hall-bar, bloch-domain-wall, mtj-pillar, coordinate-axes primitives:** `html.escape(color, quote=True)` confirmed present at parameter extraction points. All color attribute insertions use escaped values. Safe.
- **`measurement_script.py.j2` VISA resource leak when exception before `instr.close()`:** The `finally: rm.close()` at line 98 of the template closes the ResourceManager. However, `instr` is closed at line 96 (before the `finally`) only on the success path — if an exception occurs after `instr = rm.open_resource(...)` but before `instr.close()`, the `instr` VISA session leaks. This is a pre-existing template design choice (the template is a skeleton, not production code), and the scaffold comment explicitly states "human must review before execution." The template also has `# TODO: replace` comments throughout. Accepted as-is per the template's stated purpose.

---

## Summary Table

| # | Severity | File | Location | Issue |
|---|----------|------|----------|-------|
| 1 | HIGH | `figure/renderers/simviz.py` | line 735 | `FigureCanvasAgg.tostring_rgb()` removed in matplotlib 3.8 — unconditional `AttributeError` on all modern installations; all 2D/HSL/quiver SIM_VIZ panel rendering is completely broken |
