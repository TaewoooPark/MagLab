# Code Review Round 13 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-20
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit, static control-flow tracing, numerical simulation of edge cases

---

## Verdict

**ISSUES FOUND** — 1 genuine defect. Max severity: LOW.

---

## R12 Fix Verification

The R12 fix is present and correct.

**R12-F1 (`BlochDomainWallPrimitive` — `color="{arr_color}"` on `<line>` elements):** Fixed at line 156 of
`maglab/figure/primitives/catalog/bloch-domain-wall/primitive.py`:

```python
parts.append(
    f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
    f'x2="{x2:.1f}" y2="{y2:.1f}" '
    f'stroke="{arr_color}" stroke-width="1.5" '
    f'marker-end="url(#arrBloch)" color="{arr_color}"/>'
)
```

The `color="{arr_color}"` attribute is present on every `<line>` element. The `currentColor` reference in the `fill="currentColor"` marker path will now resolve to the physics-computed blend color rather than defaulting to black. Confirmed correct and complete. All previously confirmed R11 fixes (three zero-divisor clamps in NeelDomainWallPrimitive, BlochDomainWallPrimitive, and SpinTextureColorwheelPrimitive) remain intact.

---

## Findings

### Finding 1 — LOW | `maglab/figure/primitives/catalog/mtj-pillar/primitive.py:88-106` | `arrow_svg()` silently produces empty SVG for documented `up`/`down` directions

**Defect.** The `MTJPillarPrimitive._render_svg()` method defines an inner function `arrow_svg()` that handles the magnetization direction arrow for free and fixed layers. The parameter schema at lines 54 and 59 documents four valid direction values:

```python
{"name": "free_direction", ..., "description": "Free layer magnetization direction (left/right/up/down)"},
{"name": "fixed_direction", ..., "description": "Fixed layer magnetization direction"},
```

However, the `arrow_svg()` implementation (lines 88–106) handles only `"right"` and `"left"`:

```python
def arrow_svg(direction: str, ax: float, ay: float, color: str, label: str) -> str:
    if direction == "right":
        return (...)   # returns full SVG line + text
    if direction == "left":
        return (...)   # returns SVG line only
    return ""          # "up", "down", any other value -> empty string, silently
```

When `free_direction="up"` or `free_direction="down"` (or `"Up"`, `"UP"`, etc.) is passed, `arrow_svg()` returns `""`, which is appended to `parts` without any error or warning. The arrow disappears from the rendered SVG without any indication that the parameter was ignored. The user-visible result is an MTJ cross-section with no magnetization arrow at all, misrepresenting the device geometry silently.

**Impact.** Visual rendering defect. A user who sets `free_direction="up"` (to indicate perpendicular magnetic anisotropy, which is physically common for PMA-CoFeB-based MTJs) receives a figure with no magnetization indicator rather than an upward/downward arrow. The primitive silently contradicts its own documented API contract. No crash, no security issue, no data corruption.

**Fix.** Implement `"up"` and `"down"` cases in `arrow_svg()`, or explicitly raise `ValueError` on unsupported directions so the failure is not silent:

```python
def arrow_svg(direction: str, ax: float, ay: float, color: str, label: str) -> str:
    if direction == "right":
        return (
            f'<line x1="{ax - 12:.1f}" y1="{ay:.1f}" '
            f'x2="{ax + 8:.1f}" y2="{ay:.1f}" '
            f'stroke="{color}" stroke-width="2" '
            f'marker-end="url(#arrMTJ)"/>'
            f'<text x="{ax + 12:.1f}" y="{ay + 4:.1f}" '
            f'font-size="9" fill="{color}">{label}</text>'
        )
    if direction == "left":
        return (
            f'<line x1="{ax + 12:.1f}" y1="{ay:.1f}" '
            f'x2="{ax - 8:.1f}" y2="{ay:.1f}" '
            f'stroke="{color}" stroke-width="2" '
            f'marker-end="url(#arrMTJ)"/>'
        )
    if direction == "up":
        return (
            f'<line x1="{ax:.1f}" y1="{ay + 12:.1f}" '
            f'x2="{ax:.1f}" y2="{ay - 8:.1f}" '
            f'stroke="{color}" stroke-width="2" '
            f'marker-end="url(#arrMTJ)"/>'
        )
    if direction == "down":
        return (
            f'<line x1="{ax:.1f}" y1="{ay - 12:.1f}" '
            f'x2="{ax:.1f}" y2="{ay + 8:.1f}" '
            f'stroke="{color}" stroke-width="2" '
            f'marker-end="url(#arrMTJ)"/>'
        )
    return ""  # unknown direction
```

Alternatively, the `marker-end="url(#arrMTJ)"` on the up/down cases requires the marker `orient="auto"` to work correctly (the existing marker uses `orient="auto"`, so rotation is automatic — this fix is complete as shown).

---

## Non-Findings

The following items were investigated adversarially and found to be correct, pre-existing design decisions, or non-issues:

- **R12-F1 completeness:** `color="{arr_color}"` is present on every `<line>` element at line 156 of `bloch-domain-wall/primitive.py`. Fix is correct and complete.
- **R11-F1/F2/F3 zero-divisor clamps:** All three remain intact. `wall_width` clamped in both `neel-domain-wall` and `bloch-domain-wall`; `n_sectors` clamped in `spin-texture-colorwheel`.
- **`BlochDomainWallPrimitive` `n_spins=0`:** `xs = [total_w * (i + 0.5) / n for i in range(n)]` — `range(0)` is empty; the comprehension body is never evaluated; no `ZeroDivisionError`. Verified by simulation.
- **`NeelDomainWallPrimitive` `n_spins=0`:** Same pattern. Confirmed safe (R12 non-finding, re-verified).
- **`BlochSkyrmionPrimitive` `n_per_ring=0`:** Inner loop is `for j in range(n_per_ring)` — empty; `2 * math.pi * j / n_per_ring` is never evaluated. Safe.
- **`LLGPrecessionPrimitive` `parts.insert(0, defs)`:** At the time `defs` is inserted, `parts` already contains the ellipse, equator, and z-axis elements. `insert(0, defs)` correctly places `<defs>` before all rendering elements in the SVG body. Verified by simulation.
- **`LLGPrecessionPrimitive` `prec_rx=0` guard:** The `if prec_rx > 2:` guard at lines 111 and 120 prevents rendering of degenerate (zero-radius) precession ellipses. `math.sin(0) = 0` → `prec_rx = 0` when `theta_deg=0`; guard activates correctly.
- **`HallBarPrimitive` SVG `viewBox` correctness:** `viewBox="{-scl:.0f} 0 {total_w:.0f} {total_h:.0f}"` — verified numerically that the right edge reaches exactly `sl + scl`, covering both current contacts and the main channel. Correct.
- **`HallBarPrimitive` `label` injection:** `html.escape(label)` at line 163. Safe.
- **`MTJPillarPrimitive` `color` injection:** `html.escape(str(...), quote=True)` applied to `free_color`, `fixed_color`, and `barrier_color` at lines 75–77. Safe.
- **`MTJPillarPrimitive` `arrow_svg` label injection (latent):** `label` is not passed through `html.escape()`. However, both call sites pass the literal empty string `""` as `label`, making this not currently exploitable. Flagging as dismissed (latent only).
- **`MultilayerStackPrimitive` `thickness_scale=0`:** When `ts=0`, all layer heights are 0. `total_h = max(total_h, 10.0)` prevents zero total height; no `ZeroDivisionError` occurs (only multiplications and `max()`). Safe.
- **`MultilayerStackPrimitive` label injection:** `html.escape(label_text)` at line 133; `html.escape(color, quote=True)` at line 115. Safe.
- **`CoordinateAxesPrimitive` label injection:** `html.escape(lx)`, `html.escape(ly)`, `html.escape(lz)` applied; color values also escaped with `quote=True`. Safe.
- **`SpinTextureColorwheelPrimitive` `_hsl_to_hex()` numerical stability:** With `h % 360` normalization, all six branches of the if/elif chain are covered for h in [0, 360). `m = lightness - c / 2` cannot produce values outside [0, 1] when `s=1.0` and `lightness=0.5` (c=1.0, m=0.0). No numerical anomaly.
- **`MeasurementGeometryPrimitive` no injection risk:** No user-controlled strings are interpolated unescaped into SVG attribute positions. All color and label strings in this primitive are hardcoded (not from params).
- **`SimVizRenderer.render_panel` `"3d"` render_type:** Falls silently to the `else` → `render_hsl` branch. This is a pre-existing design constraint: `render_3d()` returns `Path | None` (a PNG file path) rather than a `(Figure, Axes)` pair and cannot be composed into an existing `Axes`. The panel-composition path intentionally degrades to HSL. Not a newly introduced regression; the documented `"3d"` value refers to `render_standalone` usage only.
- **`SimVizRenderer.render_panel` figure leak on exception:** `try/finally: plt.close(fig_tmp)` at lines 736–742 covers all failure paths including `canvas.draw()` and `buffer_rgba()` exceptions. No leak.
- **`render_quiver` figure lifecycle when `show_hsl=True`:** `render_hsl()` returns `(fig, ax)` without closing the figure; `render_quiver` returns the same `fig`; the caller (`render_panel`) closes it in the `finally` block. No leak.
- **`_render_2d_numpy` `plane_index` out-of-bounds:** A user-supplied `plane_index` outside the array bounds raises a standard NumPy `IndexError` that propagates visibly to the caller. This is expected Python behavior for array indexing with unchecked user input; no hidden silent failure.
- **`_TFIDFFallback.embed([])` edge case:** `range(0)` produces an empty loop; `dim = max(0, 1) = 1`; returns `[]`. Safe.
- **`SCPIIndex.build()` SQLite connection:** `with sqlite3.connect(...) as conn:` closes the connection on exit. Explicit `conn.commit()` for forward-compatibility. Correct.
- **`SCPIIndex.load()` vocab restore ordering:** TF-IDF vocabulary restored before the dimension probe (R8-F1 fix). Confirmed intact.
- **`_cosine_similarity()` zero-vector guard:** `if norm_a == 0 or norm_b == 0: return 0.0` prevents division by zero. Confirmed safe for empty vectors and zero-padded vectors.
- **`SafetyChecker.check_scpi_sequence()` compound semicolon handling:** All sub-commands on a semicoloned line are checked independently. Confirmed correct (R11 finding, re-verified).
- **`SafetyChecker` `OUTPUT_ACTIVE_PARAM_CHANGE` ordering:** `OUTP ON` hits `continue` before the param-change check; output activation is never mis-flagged. Confirmed correct (R11 finding, re-verified).
- **`ManualSearcher._try_download()` path traversal:** `re.sub(r"[^\w\-]", "_", ...)` applied to both `manufacturer` and `model` before constructing the filename. Safe.
- **`SweepConfig.step_must_be_nonzero` validator:** Rejects `step=0.0` at Pydantic construction time. Confirmed correct.
- **`measurement_script.py.j2` VISA resource lifecycle:** `instr.close()` in normal flow; `rm.close()` in `finally`. In pyvista, `ResourceManager.close()` also closes all open sessions, so an exception between `open_resource()` and `instr.close()` is cleaned up by `rm.close()`. Potential double-close of `instr` on the normal path is harmless in pyvisa. Consistent with R11 design-intent acceptance.
- **`_model_to_class_name()` empty/special-char inputs:** Returns `""` for all-special-char inputs; caller uses `or "GenericInstrument"` fallback. Safe.
- **`assemble_svg()` provenance XML injection:** `provenance.replace("--", "__")` prevents malformed XML comments. Confirmed correct.
- **`SchematicRenderer.render_to_file()` temp SVG file leak:** `try/finally` with `contextlib.suppress(OSError)` ensures cleanup. Confirmed correct.
- **`DataPlotRenderer.render_single()` figure leak on error:** `plt.close(fig)` in the `except` branch. Correct.
- **Duplicate marker IDs for multiple primitive instances in `assemble_svg()`:** SVG renderers use the first definition; consistent rendering for the first instance. Not a logic or data defect. Pre-existing design tradeoff documented in R12.
