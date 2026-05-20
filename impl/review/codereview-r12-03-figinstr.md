# Code Review Round 12 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-20
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit, static SVG spec analysis, control-flow tracing

---

## Verdict

**ISSUES FOUND** — 1 genuine defect. Max severity: LOW.

---

## R11 Fix Verification

All three R11 fixes are present and correct:

**R11-F1 (`NeelDomainWallPrimitive` — `wall_width=0` clamp):** Fixed at line 44 of
`maglab/figure/primitives/catalog/neel-domain-wall/primitive.py`:

```python
# R11-F1: clamp wall_width to a positive minimum so division never raises
wall_width = max(1.0, float(params.get("wall_width", 120.0)))
```

The fix is correctly placed before the division on line 73 (`/ wall_width`). Confirmed.

**R11-F2 (`BlochDomainWallPrimitive` — `wall_width=0` clamp):** Fixed at line 89 of
`maglab/figure/primitives/catalog/bloch-domain-wall/primitive.py`:

```python
# R11-F2: clamp wall_width to a positive minimum so division never raises
wall_width = max(1.0, float(params.get("wall_width", 120.0)))
```

The fix is correctly placed before the division on line 129 (`/ wall_width`). Confirmed.

**R11-F3 (`SpinTextureColorwheelPrimitive` — `n_sectors=0` clamp):** Fixed at line 70 of
`maglab/figure/primitives/catalog/spin-texture-colorwheel/primitive.py`:

```python
# R11-F3: clamp n_sectors to a positive minimum so division never raises
n = max(1, int(params.get("n_sectors", 36)))
```

The fix is correctly placed before the division on line 79 (`sector_angle = 360.0 / n`). Confirmed.

All three R11 clamp fixes are correct and complete.

---

## Findings

### Finding 1 — LOW | `maglab/figure/primitives/catalog/bloch-domain-wall/primitive.py:155-156` | Arrowhead color stuck at black due to `currentColor` without `color=` attribute

**Defect.** `BlochDomainWallPrimitive._render_svg()` renders spin arrows using a marker
(`id="arrBloch"`) whose path has `fill="currentColor"`:

```python
defs = (
    '<defs><marker id="arrBloch" markerWidth="6" markerHeight="6" '
    'refX="5" refY="3" orient="auto">'
    '<path d="M0,0 L6,3 L0,6 Z" fill="currentColor"/>'
    "</marker></defs>"
)
```

The `<line>` elements that reference this marker set `stroke="{arr_color}"` but do **not** set
the `color` CSS property:

```python
parts.append(
    f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
    f'x2="{x2:.1f}" y2="{y2:.1f}" '
    f'stroke="{arr_color}" stroke-width="1.5" '
    f'marker-end="url(#arrBloch)"/>'      # ← no color= attribute
)
```

Per the SVG 1.1 specification, `fill="currentColor"` inside a marker resolves to the `color`
CSS property of the element referencing the marker. When no `color` attribute is present, the
CSS `color` property defaults to black (inheriting from the root SVG element, which has no
`color` attribute either). As a result, all arrowhead tips render **black regardless of the
computed `arr_color` value**, while the line shafts correctly show the blend color. The
magnetization z-component color encoding (blue→red via `blend`) is visually broken only for
arrowheads.

**Compare** `NeelDomainWallPrimitive` and `BlochSkyrmionPrimitive`: both correctly set
`color="{arr_color}"` on each `<line>` element to supply the `currentColor` reference value
for the marker. The Bloch domain wall primitive uniquely omits this.

**Impact.** Visual rendering defect in all SVG-capable viewers (browsers, Inkscape, cairosvg,
matplotlib imshow). Arrowhead tips are black rather than the physics-correct blue/red blend
color. The arrow shafts show correct colors, so the primitive is not entirely useless, but the
figure misrepresents the magnetization direction at the arrowhead tips. No crash or security
issue.

**Fix.** Add `color="{arr_color}"` to each `<line>` element, matching the pattern in
`NeelDomainWallPrimitive` and `BlochSkyrmionPrimitive`:

```python
parts.append(
    f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
    f'x2="{x2:.1f}" y2="{y2:.1f}" '
    f'stroke="{arr_color}" stroke-width="1.5" '
    f'marker-end="url(#arrBloch)" color="{arr_color}"/>'
)
```

---

## Non-Findings

The following items were investigated adversarially and found to be correct or non-issues:

- **R11-F1/F2/F3 completeness:** All three zero-divisor clamps are at the correct positions and applied before any division. No residual gap.
- **`_build_placement_plan()` division when `n=0`:** Guard `if n == 0: return []` at line 115 of `schematic.py` prevents the `col_width = canvas_width / n` division. Safe.
- **`NeelDomainWallPrimitive` `n_spins=0`:** `xs = [total_w * (i + 0.5) / n for i in range(n)]` — `range(0)` produces an empty list; the comprehension is never evaluated and no `ZeroDivisionError` occurs.
- **`BlochSkyrmionPrimitive` `n_per_ring=0`:** Inner loop is `for j in range(n_per_ring)` — empty when `n_per_ring=0`; the `2 * math.pi * j / n_per_ring` expression is never evaluated.
- **`BlochSkyrmionPrimitive` arrowhead color:** Uses `fill="inherit"` on marker path AND sets `color="{arr_color}"` on each `<line>` element. The `color=` attribute provides the `currentColor` value, and `fill="inherit"` in marker context typically resolves via the referencing element in conformant SVG renderers. Consistent with prior R11 non-finding assessment.
- **`NeelDomainWallPrimitive` / `BlochSkyrmionPrimitive` `fill="inherit"` pattern:** Same approach documented and dismissed in R11. Not re-flagged.
- **`MTJPillarPrimitive` marker `fill="inherit"`:** Same pattern as `fill="inherit"` on neel/skyrmion markers (no color= on lines), noted but consistent with prior review findings. Not a fresh finding.
- **`MultilayerStackPrimitive` `thickness_scale=0`:** `h = thick_nm * ts` where `ts = float(params.get("thickness_scale", 20.0))`. If `ts=0`, all layer heights are 0. `total_h = max(total_h, 10.0)` prevents zero total height. No ZeroDivisionError anywhere (only multiplications and `max()`).
- **`CoordinateAxesPrimitive` SVG label injection:** `html.escape(lx)`, `html.escape(ly)`, `html.escape(lz)` applied. Color attributes also `html.escape`'d with `quote=True`. Safe.
- **`HallBarPrimitive` label injection:** `html.escape(label)` applied at line 163. Safe.
- **`MultilayerStackPrimitive` layer label injection:** `html.escape(label_text)` at line 133 and `html.escape(color, quote=True)` at line 115. Safe.
- **`CatalogRegistry.load()` module re-execution:** `sys.modules[f"maglab._catalog.{name}"]` is set before `exec_module()`, preventing repeated module execution on duplicate `load()` calls for the same name. Correct.
- **`_parse_primitive_md()` frontmatter with missing `---` delimiters:** Falls back to `{"name": md_path.parent.name, ...}` safely at line 65. No crash.
- **`assemble_svg()` provenance XML injection:** `provenance_safe = provenance.replace("--", "__")` prevents malformed XML comments. Verified in R11, still correct.
- **`SchematicRenderer.render_to_file()` temp SVG file leak:** `try/finally` with `contextlib.suppress(OSError)` at lines 417–421 ensures cleanup. Verified in R11, still correct.
- **`DataPlotRenderer.render_single()` figure leak on error:** `plt.close(fig)` in the `except` branch at line 356. Correct.
- **`FigureComposer.compose()` figure leak on error:** `plt.close(fig)` in the `except` branch at line 106. Correct.
- **`SimVizRenderer.render_panel()` `fig_tmp` lifecycle:** `try/finally: plt.close(fig_tmp)` at lines 736–742 ensures `fig_tmp` is always closed. R10-F1 fix confirmed correct.
- **`render_3d()` plotter lifecycle:** Inner `try/finally: plotter.close()` at line 651 covers all failure paths including `add_mesh()`, `set_background()`, `add_axes()`, and `screenshot()`. Verified correct.
- **`render_3d()` auto_tmp_path cleanup on screenshot failure:** Inner `try/except` unlinks `auto_tmp_path` when screenshot raises, then re-raises for the outer `except` to degrade gracefully. Correct.
- **`SCPIIndex.build()` SQLite connection:** `with sqlite3.connect(...) as conn:` closes connection on exit. Explicit `conn.commit()` for clarity. Correct.
- **`SCPIIndex.load()` vocab restore ordering:** TF-IDF vocabulary is restored before the dimension probe, ensuring probe uses corpus-sized vocabulary. R8-F1 fix confirmed intact.
- **`_cosine_similarity()` empty vectors:** When both vectors are empty after truncation (`min_dim=0`), `norm_a=0` and `norm_b=0`, returning `0.0` safely via the `if norm_a == 0 or norm_b == 0` guard.
- **`_render_hsl_direct()` `arctan2(0, 0)`:** Python returns `0.0` for this case; subsequent `% (2*pi) / (2*pi)` is valid and `colorsys.hls_to_rgb()` handles all inputs without division.
- **`SkillGenerator._write_initialize_script()` code generation injection:** The f-string uses triple-single-quote delimiter (`'''`) at source level; runtime `model` values (including embedded single-quotes) are interpolated into the generated Python docstring which uses triple-double-quotes (`"""`). Single quotes in `model` cannot close the outer f-string or break the generated docstring. Safe.
- **`_model_to_class_name()` empty string:** Returns `""` when `model` contains only non-alphanumeric characters. The caller at `scaffold.py:131` handles this via `_model_to_class_name(model) or "GenericInstrument"`. Safe.
- **`SafetyChecker.check_scpi_sequence()` compound semicolon handling:** Each sub-command on a semicolon-separated line is checked independently. `*RST` sets `initialized=True` and `continues`; subsequent sub-commands receive full limit checks. R11 verified, still correct.
- **`SafetyChecker` `OUTPUT_ACTIVE_PARAM_CHANGE` ordering:** `OUTP ON` hits the `continue` before the param-change check, ensuring output activation is never mis-flagged as a param change. R11 verified, still correct.
- **`ManualSearcher._try_download()` path traversal:** `re.sub(r"[^\w\-]", "_", ...)` applied to both `manufacturer` and `model` before constructing the filename. Safe.
- **`SweepConfig.step_must_be_nonzero` validator:** Rejects `step=0.0` at Pydantic model construction time, preventing ZeroDivisionError in the generated `np.arange` loop. Correct.
- **`measurement_script.py.j2` VISA resource leak on exception:** `finally: rm.close()` closes the ResourceManager; `instr` may not be closed on exception between `open_resource()` and `instr.close()`. Accepted per template's "human must review before execution" design intent (documented in R11).
- **`StyleProfile.rcparams()` KeyError on missing YAML keys:** All four YAML files contain the required `column_width_mm`, `font_size_pt`, `line_width_pt`, and `palette` keys. Verified in R11, still correct.
- **`_make_prop_cycle()` with empty palette:** `cycler("color", [])` does not raise. All four style YAML files have populated palettes.
- **Duplicate marker IDs when same primitive placed multiple times in `assemble_svg()`:** SVG renderers use the first definition when IDs are duplicated; rendering behavior is consistent (not incorrect). The physical output shows correct arrows for the first instance; not a logic or data defect.
