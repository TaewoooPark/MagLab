# Code Review Round 7 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-19
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit + targeted Python probes

---

## Verdict

**ISSUES FOUND** — 2 genuine defects. Max severity: LOW.

---

## R6 Fix Verification

Both R6 patches are confirmed present and correct.

**R6-F1 (SVG text content XML injection — three primitives):** Fixed. All three primitives now import `html` and apply `html.escape()` at every user-controlled `<text>` content insertion site:

- `multilayer-stack/primitive.py` line 132: `html.escape(label_text)` — confirmed.
- `hall-bar/primitive.py` line 160: `html.escape(label)` — confirmed.
- `coordinate-axes/primitive.py` lines 69, 79, 94: `html.escape(lx)`, `html.escape(ly)`, `html.escape(lz)` — confirmed.

**R6-F2 (`_TFIDFFallback` vocab persistence):** Fixed. `SCPIIndex.build()` (lines 444–448) now performs a duck-type check (`hasattr(model, "_vocab") and hasattr(model, "_fitted")`) and writes `<model_key>.vocab.json` when the TF-IDF fallback is active. `SCPIIndex.load()` (lines 470–484) restores the vocab from the sidecar when present, with a guarded `try/except (json.JSONDecodeError, OSError)` and explicit graceful fallback. Both fix sites are correct and the model instance is consistent because `_load_model()` caches `self._model`.

---

## Findings

### Finding 1 — LOW | `maglab/figure/primitives/catalog/hall-bar/primitive.py`, `multilayer-stack/primitive.py`, `bloch-domain-wall/primitive.py`, `mtj-pillar/primitive.py`, `coordinate-axes/primitive.py` | User-controlled color parameters inserted into SVG attribute values without XML-escaping — `<` in color value causes `cairosvg` `XMLSyntaxError` → silent grey placeholder

**Defect.** The R6 fix correctly escaped user-controlled strings in SVG `<text>` *content* nodes. However, the same primitives (and others) also insert user-controlled color parameters directly into SVG *attribute values* using f-string interpolation without any XML-escaping. The XML specification forbids the literal `<` character in attribute values. The affected insertion patterns and files are:

`hall-bar/primitive.py` lines 102–105 (channel rect) and 164–167 (dimension text):
```python
f'fill="{color}" stroke="#000" stroke-width="1"/>'  # color from params["color"]
```

`multilayer-stack/primitive.py` line 116:
```python
f'fill="{color}" stroke="#333" stroke-width="0.5"/>'  # color from each layer["color"]
```

`bloch-domain-wall/primitive.py` lines 103–109:
```python
f'fill="{color_up}" opacity="0.15"/>'  # color_up from params["color_up"]
f'fill="{color_down}" opacity="0.15"/>'  # color_down from params["color_down"]
```

`mtj-pillar/primitive.py` lines 117–119:
```python
f'fill="{fixed_color}" stroke="#333" stroke-width="0.8"/>'  # fixed_color from params
# similarly free_color, barrier_color
```

`coordinate-axes/primitive.py` lines 51–56 (marker fill attributes):
```python
f'<path d="M0,0 L6,3 L0,6 Z" fill="{cx_col}"/>'  # cx_col from params["color_x"]
```

**Reproduction:** A `params = {"color": "red<invalid>"}` call to `hall-bar` produces `fill="red<invalid>"`, which is invalid XML. `cairosvg` (which uses `lxml` for parsing) raises `XMLSyntaxError`. The `except Exception` clause in `compose.py` (line 169 in the schematic panel branch) silently catches this and renders a grey placeholder. The user receives no error message.

Confirmed via Python probe:
```
xml.etree.ElementTree.ParseError: not well-formed (invalid token): line 1, column 20
```

A color with a double-quote (e.g., `'#FFF" onmouseover="evil'`) injects extra SVG attributes into the element. In a local-rendering context (cairosvg → PNG), such injected event attributes have no effect since there is no browser execution, but the attribute values are silently misassigned (the fill color is wrong) without any diagnostic.

**Impact.** Any schematic panel whose LLM layout function or `panel.extra["params"]` dict supplies a non-standard color string containing `<` silently produces a grey box instead of the intended schematic. In the magnetism research context this is unlikely with typical hex codes (`#AABB CC`) but is reachable from LLM-generated params (e.g., `url(#gradient<1>)`, CSS gradient strings).

**Fix.** Define a small helper and apply it to all color param insertions:

```python
def _svg_attr(value: str) -> str:
    """Escape a string for safe insertion as an SVG attribute value."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
```

Apply at every color-in-attribute insertion:
```python
# hall-bar/primitive.py
f'fill="{_svg_attr(color)}" stroke="#000" stroke-width="1"/>'

# multilayer-stack/primitive.py
f'fill="{_svg_attr(color)}" stroke="#333" stroke-width="0.5"/>'

# bloch-domain-wall/primitive.py
f'fill="{_svg_attr(color_up)}" opacity="0.15"/>'
f'fill="{_svg_attr(color_down)}" opacity="0.15"/>'

# mtj-pillar/primitive.py
f'fill="{_svg_attr(fixed_color)}" stroke="#333" stroke-width="0.8"/>'
# ... and free_color, barrier_color

# coordinate-axes/primitive.py (marker definitions)
f'<path d="M0,0 L6,3 L0,6 Z" fill="{_svg_attr(cx_col)}"/>'
```

Alternatively, validate that all color params match the regex `^#[0-9A-Fa-f]{3,6}$|^rgb\([^)]+\)$|^[a-zA-Z]+$` before use, and reject anything else with a clear error.

---

### Finding 2 — LOW | `maglab/instrument/manual_rag.py:SCPIIndex.load()` | Cross-class embedder type mismatch produces wrong search results without warning when the index was built with `sentence-transformers` and loaded in a session without it

**Defect.** The R6 fix correctly addresses the TF-IDF→TF-IDF cross-session vocabulary mismatch. However, a distinct cross-class mismatch remains unaddressed: if `SCPIIndex.build()` runs in a session where `sentence-transformers` is installed (producing 384-dimensional vectors for `all-MiniLM-L6-v2`), no `.vocab.json` sidecar is written (correct — `hasattr(model, "_vocab")` is `False` for `SentenceTransformer`). In a subsequent session without `sentence-transformers`, `_load_model()` creates a fresh `_TFIDFFallback`. `load()` finds no sidecar (none was written), so the fallback remains unfitted. When `search()` calls `self._embedder.embed([query])`, the fallback fits on the single-word query, producing a vector of dimension 1–5. `_cosine_similarity` then truncates the stored 384-dim vectors to match the 5-dim query, discarding 379 dimensions. The resulting similarities are effectively random. No error or warning is emitted.

**Reproduction path:**
1. Session A: `sentence-transformers` installed. `pipeline.ingest("k2400", pdf_path)` — 384-dim vectors stored in SQLite.
2. Session B (new process, no `sentence-transformers`): `pipeline.search("k2400", "voltage range")` — TF-IDF fallback used. Query dim=2. Stored dim=384. Similarities are random.

**Impact.** SCPI RAG search returns wrong results silently in a common deployment scenario: the developer machine has `sentence-transformers` but the user machine (or CI runner) does not. The index appears to function (returns results), but the results are semantically meaningless.

**Fix.** Persist the embedder type in the SQLite database metadata at build time, and verify it at load time:

```python
# build(): record embedder type in a metadata table
with sqlite3.connect(self._db_path) as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    embedder_type = "sentence-transformers" if hasattr(model, "encode") and not hasattr(model, "_vocab") else "tfidf"
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('embedder_type', ?)", (embedder_type,))
    ...

# load(): check for mismatch
with sqlite3.connect(self._db_path) as conn:
    meta_row = conn.execute("SELECT value FROM meta WHERE key='embedder_type'").fetchone()
    ...
stored_type = meta_row[0] if meta_row else "unknown"
current_type = "tfidf" if isinstance(self._embedder._load_model(), _TFIDFFallback) else "sentence-transformers"
if stored_type != "unknown" and stored_type != current_type:
    log.warning(
        "Embedder type mismatch: index was built with '%s' but current session uses '%s'. "
        "Search results will be incorrect. Rebuild the index with the same embedder.",
        stored_type, current_type
    )
```

At minimum, add a docstring warning to `_TFIDFFallback` stating that cross-class session mismatches produce wrong results without error.

---

## Non-Findings

The following items were investigated adversarially and found to be correct:

- **R6-F1 fix (SVG text content escaping):** Confirmed correct at all three primitive sites. `html.escape()` is imported and applied to all `<text>` node content strings derived from user params.
- **R6-F2 fix (vocab persistence):** Confirmed correct. Build writes sidecar, load restores it with `try/except`. Model instance is consistent across the two `_load_model()` calls in `build()`.
- **`_empty_svg()` panel_id in SVG comment:** `<` and `&` are valid characters inside XML comments per the XML 2.5 spec (`Char` includes `#x3C`). The existing `--` → `__` sanitization is sufficient. No injection surface.
- **`MTJPillarPrimitive.arrow_svg()` label parameter:** The `label` argument is always `""` (empty string) at both call sites (lines 124, 147). The f-string `{label}` in SVG `<text>` content never receives user input. No injection surface.
- **`BlochSkyrmionPrimitive` skyrmion_number in text:** `f"Bloch skyrmion (Q={skn})"` where `skn = int(params.get("skyrmion_number", -1))`. After `int()` coercion, only digits, `-`, and `+` are possible. Safe.
- **`_render_hsl_direct` slice shape for plane='y' and 'x':** Variable shadowing of `nx`, `ny` with the 2D slice dimensions is intentional and correct. `rgb_image` shape and indexing are consistent.
- **`render_quiver` plane='y'/'x' slicing:** `xs`/`ys`/`X`/`Y` correctly reflect the 2D slice dimensions; quiver `U`/`V`/`C` shapes match.
- **`SCPIIndex.search()` lazy load:** Correctly calls `self.load()` only when `_chunks` is empty; no double-load risk.
- **`_TFIDFFallback.embed([])` with empty list:** Returns `[]` correctly. `_fitted = True`, `_vocab = {}`, `dim = max(0, 1) = 1`. No crash.
- **`_cosine_similarity` zero-norm guard:** `if norm_a == 0 or norm_b == 0: return 0.0` — no division-by-zero.
- **`FigureComposer._make_axes` span validation:** Both start position and span-end bounds are validated (`row_end > nrows`, `col_end > ncols`).
- **`DataPlotRenderer.render_single()` figure leak on exception:** `plt.close(fig)` in `except Exception` block confirmed present (line 356).
- **`FigureComposer.compose()` figure leak on exception:** `plt.close(fig)` in `except Exception` block confirmed present (line 106).
- **`SimVizRenderer.render_panel()` fig_tmp lifecycle:** `plt.close(fig_tmp)` in `finally` block confirmed present (line 720). No leak on canvas draw failure.
- **`assemble_svg()` provenance comment injection:** `provenance_safe = provenance.replace("--", "__")` applied before insertion into SVG comment. Confirmed.
- **`CatalogRegistry.load()` dynamic import name collision:** Module registered as `maglab._catalog.<name>` where `<name>` is the catalog directory name (developer-controlled, fixed at package time). No user input reaches this path.
- **`check_script_text()` line number map for sub-commands:** `lineno_map.setdefault(sub, i)` for all semicolon-split sub-commands confirmed present (lines 521–522). The correction loop iterates `result.violations + result.warnings` and updates `v.line_number` when `v.command` is in the map. Correct.
- **`ScriptGenerator.generate()` `skip_safety_check` exposure:** The public `generate_measurement_script()` never passes `skip_safety_check`; it calls `generator.generate(config, output_path=output_path)` using the default `False`. Safe.
- **`_model_to_class_name` all-digit model string:** Returns `"Instr2400"` for `"2400"`. Returns `""` for all-symbol input; caught by `or "GenericInstrument"` on line 131. Correct.
- **`manual_search.py` path traversal:** `re.sub(r"[^\w\-]", "_", ...)` applied to both `manufacturer` and `model` before `Path` join. Safe.
- **`_load_ovf_numpy` zero-size grid guard:** `nx == 0 or ny == 0 or nz == 0` check precedes reshape. `ValueError` raised with descriptive message.
- **`skillgen.py` SCPI command description truncation:** `c.description[:60]` is used in Markdown table cells with `|` escaped (`replace("|", "\\|")`). No SVG or XML surface.
- **`mock.py` `noise_amplitude=0.0` guard:** `resp_def.noise_amplitude or 1e-10` substitutes `1e-10` to avoid `gauss(0, 0)` which raises `ValueError`. Correct.
- **`load_style()` YAML injection:** Uses `yaml.safe_load()`. Safe against YAML deserialization attacks.

---

## Summary Table

| # | Severity | File(s) | Location | Issue |
|---|----------|---------|----------|-------|
| 1 | LOW | `hall-bar/primitive.py`, `multilayer-stack/primitive.py`, `bloch-domain-wall/primitive.py`, `mtj-pillar/primitive.py`, `coordinate-axes/primitive.py` | Color param f-string insertions | Unescaped color params in SVG attribute values — `<` causes `cairosvg` `XMLSyntaxError` → silent grey placeholder |
| 2 | LOW | `instrument/manual_rag.py` | `SCPIIndex.load()` | Cross-class embedder type mismatch (sentence-transformers build → TF-IDF load) — search returns wrong results without warning |
