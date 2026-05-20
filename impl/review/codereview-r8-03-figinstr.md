# Code Review Round 8 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-19
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit + targeted Python probes

---

## Verdict

**ISSUES FOUND** — 2 genuine defects. Max severity: LOW.

---

## R7 Fix Verification

Both R7 fixes are confirmed present and correct.

**R7-F1 (SVG color params in attribute values — five primitives):** Fixed. All five primitives now import `html` and apply `html.escape(value, quote=True)` to user-controlled color parameters at every SVG attribute value insertion site:

- `hall-bar/primitive.py` lines 102–103: `color_attr = html.escape(color, quote=True)` — confirmed. All subsequent f-string attribute insertions use `color_attr`.
- `multilayer-stack/primitive.py` lines 114–115: `color_attr = html.escape(color, quote=True)` per layer — confirmed. Attribute insertion at line 118 uses `color_attr`.
- `bloch-domain-wall/primitive.py` lines 102–103: `color_up_attr = html.escape(color_up, quote=True)` and `color_down_attr = html.escape(color_down, quote=True)` — confirmed. Used in domain background rects (lines 108, 113) and label text fill attributes (lines 167, 170).
- `mtj-pillar/primitive.py` lines 75–77: `free_color`, `fixed_color`, `barrier_color` all escaped at parameter extraction time — confirmed. Propagated correctly into `rect fill=` and `arrow_svg` color attributes.
- `coordinate-axes/primitive.py` lines 43–45: `cx_col`, `cy_col`, `cz_col` all escaped — confirmed. Used in marker `<path fill=` defs and axis `stroke=` / `fill=` attributes.

**R7-F2 (Embedder identity persistence in `SCPIIndex.build()`/`load()`):** Fixed. `build()` (lines 422–459) now:
1. Determines `embedder_class = type(model).__name__` and `vec_dim = len(self._vecs[0])`.
2. Creates a `meta` table in SQLite and writes both values with `INSERT OR REPLACE`.
3. Writes the TF-IDF vocab sidecar when `hasattr(model, "_vocab") and hasattr(model, "_fitted")`.

`load()` (lines 474–554) now:
1. Reads `meta` table gracefully with `try/except Exception` for older indexes without the table.
2. Warns on class mismatch (`stored_class != current_class`).
3. Probes current dim and warns on dimension mismatch.
4. Restores TF-IDF vocab from sidecar when present.

Both fix sites are present and structurally correct. One ordering defect in `load()` is identified as a new Finding below.

---

## Findings

### Finding 1 — LOW | `maglab/instrument/manual_rag.py:SCPIIndex.load()` | Dimension probe fires before vocab restore → spurious `logging.warning` on legitimate TF-IDF cross-session reload

**Defect.** The R7 fix adds two code blocks to `load()` that execute in the wrong order:

1. **Dimension probe** (lines 511–530): calls `self._embedder.embed(["probe"])` to measure the current embedder's output dimension, then emits a `logging.warning` if `stored_dim != current_dim`.
2. **Vocab restore** (lines 532–552): reads `vocab.json` sidecar and restores `model._vocab` / `model._fitted` into the current `_TFIDFFallback` instance.

The probe (block 1) executes **before** the restore (block 2). When the index was built with TF-IDF (stored `embedder_class = '_TFIDFFallback'`, `vec_dim = 50`) and the current session is also TF-IDF (same class, same sidecar on disk), the dimension check enters the `elif stored_dim_str:` branch (line 511) because classes match. The probe calls `embed(["probe"])` on a freshly-created `_TFIDFFallback` whose `_fitted=False`. Inside `embed()`, the fitting block runs on the single word `"probe"`, setting `_vocab = {"probe": 0}` and `dim = 1`. The check at line 522 evaluates `50 != 1 → True` and emits:

```
WARNING: Embedder dimension mismatch: index has 50-dim vectors but the current embedder produces 1-dim vectors. Search results will be incorrect. Rebuild the index with the same embedder.
```

This warning is **factually incorrect**: the vocab sidecar exists and will correctly restore the 50-word vocab immediately after this warning fires. The search results after `load()` completes are correct (the restore at line 546 overwrites the probe-fitted `_vocab`). However, the user is falsely told that their index is broken and must be rebuilt.

**Side-effect:** the probe also mutates the `_TFIDFFallback` instance state (`_vocab = {"probe": 0}`, `_fitted = True`). This mutation is subsequently overwritten by the restore, so the net search behavior is correct. The mutation only matters if `_TFIDFFallback` is a shared instance and something reads its state between the probe and the restore — which does not occur in the current call sequence.

**Reproduction:**
1. Session A: `sentence-transformers` not installed. `pipeline.ingest("k2400", pdf_path)` — `_TFIDFFallback` fitted on 50-word corpus; `k2400.db` has `vec_dim=50`, `embedder_class='_TFIDFFallback'`; `k2400.vocab.json` written with 50-word vocab.
2. Session B: new process. `pipeline.search("k2400", "voltage range")` calls `index.load()`. The spurious warning fires even though the search returns correct results.

**Impact.** Every legitimate TF-IDF cross-session reload emits a false-alarm warning. The warning text instructs the user to rebuild the index, which is unnecessary work and erodes trust in the diagnostic system. The actual search correctness is unaffected.

**Fix.** Move the vocab restore block before the dimension probe block, or skip the dimension probe when the vocab sidecar is present (since sidecar presence guarantees correct restoration of the expected dimension):

```python
# Option A: restore vocab FIRST, then probe
vocab_path = self._db_path.with_suffix(".vocab.json")
if vocab_path.is_file():
    model = self._embedder._load_model()
    if hasattr(model, "_vocab") and hasattr(model, "_fitted"):
        try:
            vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
            model._vocab = vocab
            model._fitted = True
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not restore TF-IDF vocabulary from %s: %s", vocab_path, exc)

# Now probe is accurate — vocab already restored
if stored_meta:
    ...
    try:
        probe = self._embedder.embed(["probe"])
        current_dim = len(probe[0]) if probe else None
    ...

# Option B: skip dim probe when vocab sidecar is present (simpler)
elif stored_dim_str and not vocab_path.is_file():
    # Only probe when no sidecar — sidecar guarantees correct dim after restore
    ...
```

---

### Finding 2 — LOW | `maglab/figure/renderers/simviz.py:render_3d()` | PyVista plotter not closed in `finally` block → plotter leak and orphaned temp file when `plotter.screenshot()` raises

**Defect.** In `render_3d()` (lines 598–640), the PyVista plotter is created at line 614 and closed at line 635. The screenshot write at line 634 is not guarded by a `try/finally` block. The outer `except Exception` at line 638 catches any exception from the entire block, but `plotter.close()` at line 635 only executes when `plotter.screenshot()` succeeds:

```python
plotter = pv.Plotter(off_screen=True)           # line 614
# ... add_mesh, set_background, add_axes ...
plotter.screenshot(str(output_path))             # line 634 — may raise
plotter.close()                                  # line 635 — skipped on exception
return output_path                               # line 637

except Exception as exc:
    warnings.warn(f"PyVista 3D render failed: {exc}", ...)
    return None
```

When `screenshot()` raises (e.g., due to a missing OpenGL context in a headless environment, or an API change in a newer PyVista version), `plotter.close()` is skipped. The PyVista `Plotter` object holds GPU/windowing resources that are not immediately released.

Additionally, when `output_path is None` at line 626, a temp file is created via `NamedTemporaryFile(delete=False)`. If `screenshot()` raises, this temp file (empty or partially written) is not cleaned up:

```python
if output_path is None:
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    output_path = Path(tmp.name)
    tmp.close()
# If screenshot() raises after this point: temp file leaks on disk.
```

**Impact.** In headless CI environments where PyVista frequently fails due to missing GL context, every `render_3d()` call that raises leaves both a plotter resource and a temp file uncleaned. In long-running processes (e.g., the MagLab server daemon rendering many SIM_VIZ panels), this can accumulate unclosed plotter objects. PyVista's garbage collector will eventually clean up, but the timing is non-deterministic. The temp file leak on disk is minor (OS temp dir cleanup) but leaves debris.

**Fix.** Wrap the screenshot and plotter lifecycle in a `try/finally` block, and clean up the temp file on exception:

```python
plotter = pv.Plotter(off_screen=True)
# ... mesh setup ...

try:
    plotter.screenshot(str(output_path))
finally:
    plotter.close()

# Clean up temp file on exception when it was auto-created
```

Or more concisely:

```python
try:
    plotter.screenshot(str(output_path))
    plotter.close()
    return output_path
except Exception as exc:
    plotter.close()   # explicit cleanup before re-handling
    # clean up temp file if auto-created
    if auto_tmp and output_path.exists():
        output_path.unlink(missing_ok=True)
    warnings.warn(...)
    return None
```

---

## Non-Findings

The following items were investigated adversarially and found to be correct or non-issues:

- **R7-F1 fix (SVG color params in attribute values — five primitives):** Confirmed correct at all five primitives. `html.escape(value, quote=True)` is applied before every attribute insertion. All five fixes verified at the exact lines noted in R7.
- **R7-F2 fix (embedder identity persistence):** Confirmed structurally correct. `build()` writes `embedder_class` and `vec_dim` to `meta` table and writes vocab sidecar. `load()` reads them with graceful `try/except` for older indexes. See Finding 1 for the ordering sub-defect.
- **MTJ pillar `arrow_svg()` inner function color parameter:** `arrow_svg()` receives already-html-escaped color values (`free_color`, `fixed_color`, `barrier_color` are all escaped at lines 75–77 before being passed). The inner function's `color` parameter carries escaped values throughout. The `fill="{color}"` and `stroke="{color}"` insertions inside `arrow_svg()` are safe.
- **`BlochDomainWallPrimitive` computed `arr_color`:** `arr_color = f"rgb({r_c},{g_c},{b_c})"` where `r_c`, `g_c`, `b_c` are all `int()` values — only digits, no user input can reach this path. Safe.
- **`NeelDomainWallPrimitive` computed `arr_color`:** Same pattern as Bloch DW. All-integer f-string. Safe.
- **`BlochSkyrmionPrimitive` `core_color` and `arr_color`:** `core_color` is hardcoded `"#CC0000"` or `"#0055CC"` (conditional on `int()` coercion of `skyrmion_number`). `arr_color` is all-integer f-string. Safe.
- **`SpinTextureColorwheelPrimitive` `_hsl_to_hex()` output:** Returns `f"#{ri:02X}{gi:02X}{bi:02X}"` where `ri`, `gi`, `bi` are `int()` values. Always produces valid 7-char hex. Safe.
- **`LLGPrecessionPrimitive`:** No user-controlled color parameters. All SVG colors are hardcoded hex strings (`"#888"`, `"#0055CC"`, `"#CC0000"`, etc.). Safe.
- **`MeasurementGeometryPrimitive`:** No user-controlled color parameters. All colors hardcoded (`"#C00"`, `"#0055CC"`, `"#007700"`, `"#DDD"`). Safe.
- **`NeelDomainWallPrimitive` fixed domain background colors:** `fill="#0055CC"` and `fill="#CC0000"` are hardcoded at lines 52–57. Not user-controlled. Safe.
- **`_extract_svg_body()` greedy regex:** `re.search(r"<svg[^>]*>(.*)</svg>", ..., re.DOTALL)` is greedy and would incorrectly handle nested `<svg>` elements. However, no current primitive embeds another SVG document — all render self-contained `<svg>` with no nested `<svg>` children. Non-issue for the current catalog.
- **`SCPIIndex.load()` probe mutation side-effect:** After the probe fits `_TFIDFFallback` on `"probe"`, the vocab restore at lines 543–547 overwrites `model._vocab` with the correct corpus vocab. The net state after `load()` is correct. The search results are unaffected by the mutation.
- **`render_3d()` temp file on successful path:** When `output_path` is `None`, the temp file is created, `tmp.close()` is called immediately (releases OS handle), and then `plotter.screenshot()` writes to it. On success, the file is returned to the caller. Not a leak on the success path.
- **`DataPlotRenderer.render_single()` figure leak on exception:** `plt.close(fig)` in `except Exception` block confirmed present (line 356). No leak.
- **`FigureComposer.compose()` figure leak on exception:** `plt.close(fig)` in `except Exception` block confirmed present (line 106). No leak.
- **`SimVizRenderer.render_panel()` fig_tmp lifecycle:** `plt.close(fig_tmp)` in `finally` block confirmed present (line 720). No leak on canvas draw failure.
- **`SCPIIndex.load()` SQLite connection closure:** Uses `with sqlite3.connect(...) as conn:` context manager. Connection is always closed on exit, even on exception. No leak.
- **`SCPIIndex.build()` SQLite connection closure:** Same context manager pattern. No leak.
- **`CatalogRegistry.load()` dynamic import name collision:** Module registered as `maglab._catalog.<name>` where `<name>` is the catalog directory name (developer-controlled). No user input reaches `sys.modules`.
- **`_hsl_to_hex()` division by zero or float domain:** All inputs are computed from `angle % 360` and fixed saturation/lightness values. No user input flows through. No divide-by-zero risk.
- **`ManualSearcher._try_download()` path traversal:** `safe_mfr` and `safe_mdl` are produced by `re.sub(r"[^\w\-]", "_", ...)` before joining into `cache_dir / filename`. Safe.
- **`SafetyChecker.check_script_text()` lineno_map sub-command mapping:** `lineno_map.setdefault(sub, i)` at lines 521–522 confirmed present. Correction loop at lines 540–543 updates `v.line_number` when `v.command` is in the map. Correct.
- **`ScriptGenerator.generate()` `skip_safety_check` exposure:** `generate_measurement_script()` never passes `skip_safety_check`; defaults to `False`. The flag is `True` only in test scaffolding. Safe.
- **`_cosine_similarity()` zero-norm guard:** `if norm_a == 0 or norm_b == 0: return 0.0` — no division-by-zero.
- **`_TFIDFFallback.embed([])` with empty input:** `all_words = []`, `vocab_set = []`, `_vocab = {}`, `_fitted = True`, `dim = max(0, 1) = 1`, returns `[]` for empty input. No crash.
- **`FigureComposer._make_axes()` span validation:** Both start position and span-end bounds validated at lines 128–138. `row_end > nrows` and `col_end > ncols` properly caught.
- **`assemble_svg()` provenance comment injection:** `provenance_safe = provenance.replace("--", "__")` applied before SVG comment insertion. `SchematicRenderer.render_panel()` passes `f"panel_id={panel.panel_id}"` as provenance. Panel ID `"test-->foo"` becomes `"test__>foo"` in the comment — the `>` in an XML comment is legal. No malformed XML.
- **`load_style()` YAML injection:** Uses `yaml.safe_load()`. Safe.
- **`mock.py` `noise_amplitude=0.0` guard:** `resp_def.noise_amplitude or 1e-10` substitutes `1e-10` to avoid `gauss(0, 0)` which raises `ValueError`. Correct.

---

## Summary Table

| # | Severity | File | Location | Issue |
|---|----------|------|----------|-------|
| 1 | LOW | `instrument/manual_rag.py` | `SCPIIndex.load()` lines 511–530 | Dimension probe fires before vocab restore → spurious dim-mismatch warning on valid TF-IDF cross-session reload |
| 2 | LOW | `figure/renderers/simviz.py` | `render_3d()` lines 614–640 | PyVista plotter not closed in `finally` block; temp file not cleaned when `screenshot()` raises |
