# Code Review Round 9 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-20
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit + targeted Python control-flow probes

---

## Verdict

**ISSUES FOUND** — 1 genuine defect. Max severity: LOW.

---

## R8 Fix Verification

Both R8 fixes are confirmed present and correct.

**R8-F1 (`SCPIIndex.load()` vocab restore before dimension probe):** Fixed. Lines 493–514 now restore the TF-IDF vocab sidecar unconditionally at the start of `load()`, before any embedder identity or dimension probing. The fix is structurally correct:

1. `vocab_path = self._db_path.with_suffix(".vocab.json")` (line 500).
2. `if vocab_path.is_file():` load model, duck-type check `hasattr(model, "_vocab") and hasattr(model, "_fitted")`, then restore `model._vocab` and set `model._fitted = True` (lines 501–514).
3. The dimension probe at lines 523–556 executes **after** the restore. A legitimate TF-IDF→TF-IDF cross-session reload therefore probes the corpus-sized vocab, producing the correct `current_dim` that matches `stored_dim`. No spurious warning fires.

Confirmed correct. The fix banner comment at lines 493–499 accurately describes the ordering rationale.

**R8-F2 (`render_3d()` `finally` block for `plotter.close()`):** Partially applied. The `screenshot()` call at line 642 is now wrapped in a `try/except/finally` block that:
- In the `except` branch: unlinks the auto-created temp file when `auto_tmp_path` is set (lines 643–646).
- In the `finally` branch: calls `plotter.close()` unconditionally (line 648).

This protects the `screenshot()` call. However, a residual resource leak remains — see Finding 1.

---

## Findings

### Finding 1 — LOW | `maglab/figure/renderers/simviz.py:render_3d()` lines 614–624 | PyVista plotter not closed when `add_mesh()`, `set_background()`, or `add_axes()` raises

**Defect.** The R8-F2 fix correctly wraps `plotter.screenshot()` in a `try/finally` that calls `plotter.close()`. However, the inner `try/finally` block begins at line 641 — **after** the plotter setup calls at lines 615–624:

```python
plotter = pv.Plotter(off_screen=True)          # line 614
plotter.add_mesh(                               # line 615
    glyphs,
    scalars="mz",
    cmap=colormap,
    clim=(-1, 1),
    show_scalar_bar=True,
    scalar_bar_args={"title": "m_z"},
)                                               # line 622
plotter.set_background("white")                 # line 623
plotter.add_axes()                              # line 624

auto_tmp_path: Path | None = None              # line 628
if output_path is None:                        # line 629
    ...                                        # line 630–633

try:                                           # line 641  ← finally block starts here
    plotter.screenshot(str(output_path))
...
finally:
    plotter.close()
```

If `add_mesh()` raises (e.g., `glyphs` is empty or has mismatched array shapes — a realistic failure mode when `grid.glyph()` produces zero cells), `plotter.close()` is never called. The outer `try/except` at line 652 catches the exception and emits a warning, but does not close the plotter.

**Realistic trigger:** In headless environments where PyVista is installed but the magnetization array `m` is degenerate (e.g., a uniform field where `mz` is constant and `grid.glyph()` produces zero glyphs), `add_mesh(glyphs, ...)` raises `ValueError` from VTK. Every such call leaves a `pv.Plotter` with an open VTK renderer pipeline unclosed. PyVista's garbage collector will eventually invoke `__del__`, but timing is non-deterministic and in long-running server processes (continuous figure rendering) the accumulated unclosed plotters can exhaust VTK renderer slots.

**Impact.** Resource leak: VTK/GPU renderer pipeline resources are not released synchronously. In headless CI or server environments, repeated degenerate `render_3d()` calls accumulate orphaned plotter objects. Severity is LOW (eventual GC reclaims resources, no correctness impact), but it is a genuine residual gap left by the R8-F2 fix.

**Fix.** Expand the `try/finally` to cover the entire plotter lifecycle from creation through `screenshot()`:

```python
plotter = pv.Plotter(off_screen=True)
try:
    plotter.add_mesh(
        glyphs,
        scalars="mz",
        cmap=colormap,
        clim=(-1, 1),
        show_scalar_bar=True,
        scalar_bar_args={"title": "m_z"},
    )
    plotter.set_background("white")
    plotter.add_axes()

    auto_tmp_path: Path | None = None
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        output_path = Path(tmp.name)
        auto_tmp_path = output_path
        tmp.close()
    else:
        output_path = Path(output_path)

    try:
        plotter.screenshot(str(output_path))
    except Exception:
        if auto_tmp_path is not None and auto_tmp_path.exists():
            auto_tmp_path.unlink(missing_ok=True)
        raise

finally:
    plotter.close()

return output_path
```

This ensures `plotter.close()` is called for **any** failure anywhere in the plotter lifecycle — whether `add_mesh()`, `set_background()`, `add_axes()`, or `screenshot()` raises.

---

## Non-Findings

The following items were investigated adversarially and found to be correct or non-issues:

- **R8-F1 fix (vocab restore before dim probe):** Confirmed correct. `load()` now restores vocab at lines 500–514 before probing at lines 523–556. A legitimate TF-IDF→TF-IDF cross-session reload no longer emits a spurious dim-mismatch warning. The probe on the restored 50-word vocab produces `current_dim=50 == stored_dim=50`. No false alarm.
- **R8-F2 fix (screenshot path):** The screenshot/finally pattern is correct. `plotter.close()` is called exactly once on both success and failure paths through the `screenshot()` call. The residual gap (Finding 1) is for pre-screenshot plotter setup, not for the screenshot call itself.
- **`plotter.close()` double-call risk:** Confirmed not present. On the success path, `finally` calls `plotter.close()` once. On the `screenshot()` failure path, the `except` re-raises and `finally` calls `plotter.close()` once. PyVista's `Plotter.close()` is not called a second time by any code path.
- **`SCPIIndex.load()` double `_load_model()` call:** `_load_model()` caches the model instance in `self._model` after the first call. Both the vocab-restore block (line 502) and the dim-probe block (line 526) call `self._embedder._load_model()` and receive the same cached instance. No inconsistency.
- **`SCPIIndex.load()` old index (no meta table) graceful degradation:** When `stored_meta = {}`, the class mismatch and dim checks are skipped entirely. This is intentional backward-compat behavior, documented in the code comments. If an old sentence-transformers index is loaded with TF-IDF, no warning fires, but this omission is the same pre-R7 behavior. Not a regression introduced by R7/R8 fixes.
- **`_TFIDFFallback.embed()` after vocab restore:** After `model._vocab` and `model._fitted` are restored from the sidecar, `embed(["probe"])` uses the corpus-sized vocab to produce a 50-dim vector. `_cosine_similarity(query_vec, stored_vec)` with matching 50-dim vectors produces correct scores. Safe.
- **SentenceTransformer with orphaned vocab sidecar:** If a `vocab.json` sidecar exists from a previous TF-IDF run but the current session uses `SentenceTransformer`, `hasattr(model, "_vocab")` returns `False` and the restore block is skipped. The dim probe then correctly checks the SentenceTransformer's 384-dim output. Safe.
- **`_load_ovf_numpy()` empty data lines:** When `vals=[]`, `m_flat = np.zeros((0, 3))` and the pad path fills `n_expected` rows with zeros. `m = pad.reshape((nx, ny, nz, 3))` succeeds. No crash.
- **`_load_ovf_numpy()` zero-size grid guard:** The `nx == 0 or ny == 0 or nz == 0` guard at line 145 raises `ValueError` before any reshape or downstream rendering. This prevents `IndexError` and `ZeroDivisionError` in slice index computation.
- **`render_2d()`, `render_hsl()`, `render_quiver()` matplotlib figure lifecycle:** All three functions return `(fig, ax)` to the caller; they do not call `plt.close()` internally. The caller (or `SimVizRenderer.render_panel()`'s `finally: plt.close(fig_tmp)`) is responsible. The `finally` block in `render_panel()` is confirmed present at line 733.
- **`DataPlotRenderer.render_single()` figure leak:** The `try/except` block at lines 351–357 calls `plt.close(fig)` in the `except` branch and then re-raises. `plt.rc_context().__exit__()` is called by the `with` statement regardless of exception. No leak and no dangling rcParams.
- **`FigureComposer.compose()` figure leak:** `plt.close(fig)` in the `except` block at line 106 confirmed present. The `with plt.rc_context(rcparams):` block calls `__exit__` on both normal and exceptional exit. No leak.
- **`SchematicRenderer._empty_svg()` XML comment injection:** `panel_id.replace("--", "__")` at line 476 prevents `--` sequences in XML comments. A `panel_id="test-->foo"` becomes `"test__>foo"` — `>` is legal inside XML comments. No malformed XML.
- **`assemble_svg()` provenance injection:** `provenance.replace("--", "__")` at line 183 applied before insertion. Safe.
- **`CatalogRegistry.load()` dynamic import:** Module registered as `maglab._catalog.<name>` where `<name>` comes from the developer-controlled catalog directory name (not user input). No user input reaches `sys.modules`. Safe.
- **`_model_to_class_name()` empty model edge case:** Returns `""` for empty or whitespace-only model strings. `generate_scaffold()` applies `or "GenericInstrument"` fallback. Safe.
- **`ScriptConfig` and `SweepConfig` validation:** `step_must_be_nonzero` validator rejects `step=0.0` at model construction time, preventing `ZeroDivisionError` in the generated `np.arange()` loop.
- **`generate_measurement_script()` skipping safety check:** Never passes `skip_safety_check=True`; the default is `False`. The flag is only accessible via the `ScriptGenerator.generate()` method, which is not exposed in the public convenience API.
- **`SafetyChecker.check_script_text()` lineno correction:** The `lineno_map.setdefault(sub, i)` loop at lines 521–522 maps each sub-command to its parent script line. The correction loop at lines 540–543 updates `v.line_number` for sub-commands. Confirmed correct per R4-F4 fix banner.
- **`SafetyChecker` OUTP OFF continue:** When `_OUTPUT_OFF_RE` matches, `output_active = False` and `continue` skips voltage/current checks. `OUTP OFF` carries no numeric parameter, so those checks would be vacuous no-ops anyway. Correct and intentional.
- **`SafetyChecker` compound line with init + volt setpoint:** `"*RST; SOUR:VOLT 5000"` splits into `["*RST", "SOUR:VOLT 5000"]`. `*RST` sets `initialized=True` and `continue`s. `SOUR:VOLT 5000` triggers the voltage limit check. The voltage violation is correctly flagged. The HIGH-1 fix is confirmed working.
- **`_cosine_similarity()` zero-norm guard:** `if norm_a == 0 or norm_b == 0: return 0.0` prevents division by zero. Safe.
- **`ManualSearcher._try_download()` path traversal:** `safe_mfr` and `safe_mdl` produced by `re.sub(r"[^\w\-]", "_", ...)`. `cache_dir / filename` joins sanitized components. Safe.
- **`SkillGenerator._write_skill_md()` YAML frontmatter:** String values use `repr()` (e.g., `f"{k}: {v!r}"`). `repr()` produces quoted Python string literals that are valid YAML scalar values. No YAML injection possible.
- **`_write_scpi_reference()` pipe in cmd:** `c.cmd` is wrapped in backtick code span `` `{c.cmd}` `` in the Markdown table. Pipe characters inside GFM code spans in table cells are treated as literal characters by compliant renderers. Not a defect.
- **SVG color escaping in all five R7-fixed primitives:** Confirmed still present. `html.escape(color, quote=True)` applied at parameter extraction time in `hall-bar/primitive.py` (line 102), `bloch-domain-wall/primitive.py` (lines 102–103), `mtj-pillar/primitive.py` (lines 75–77), and `coordinate-axes/primitive.py` (verified in R7/R8). All color attribute insertions use the escaped values.
- **`BlochSkyrmionPrimitive` core_color and arr_color:** `core_color` is a hardcoded string (`"#CC0000"` or `"#0055CC"`) selected by integer comparison. `arr_color = f"rgb({r_c},{g_c},{b_c})"` where `r_c, g_c, b_c` are all `int()` values — no user input. Safe.
- **`StyleProfile.rcparams()` KeyError:** Calls `self._data["column_width_mm"][column]` without a try/except. If the YAML file is missing `column_width_mm`, this raises `KeyError`. However, all four YAML files are developer-controlled and are verified to contain this key. Not a user-facing risk.
- **`load_style()` YAML injection:** Uses `yaml.safe_load()`. Safe.
- **`FigureSpec._collect_provenance()` `frozen=False`:** The model validator mutates `self.provenance_ids`. `model_config = {"frozen": False}` explicitly allows this mutation. Correct.
- **`AxisSpec.lim` min > max:** No validator enforces `lim[0] < lim[1]`. Reversed limits produce inverted axes in matplotlib — valid physics practice (e.g., binding energy in ARPES). Not a defect.

---

## Summary Table

| # | Severity | File | Location | Issue |
|---|----------|------|----------|-------|
| 1 | LOW | `figure/renderers/simviz.py` | `render_3d()` lines 614–624 | PyVista plotter not closed when `add_mesh()`, `set_background()`, or `add_axes()` raises — residual gap in R8-F2 fix that only protects `screenshot()` |
