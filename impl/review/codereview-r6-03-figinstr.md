# Code Review Round 6 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-19
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit + targeted Python probes

---

## Verdict

**ISSUES FOUND** — 2 genuine defects. Max severity: LOW.

---

## R5 Fix Verification

Both R5 patches are confirmed present and correct:

**R5-F1 (`manual_rag.py` SQLite connection leak):** Fixed. Both `SCPIIndex.build()` (lines 423–436) and `SCPIIndex.load()` (lines 446–449) now use `with sqlite3.connect(self._db_path) as conn:`. The connection is always released on both clean exit and exception. Comments explain the context manager semantics.

**R5-F2 (`schematic.py` SVG XML comment injection):** Fixed. `assemble_svg()` (line 183) now applies `provenance_safe = provenance.replace("--", "__")` before inserting into the `_SVG_HEADER_TEMPLATE`. `SchematicRenderer._empty_svg()` (line 476) applies `safe_panel_id = panel_id.replace("--", "__")` before inserting into its inline SVG comment. Both fix sites are correct.

---

## Findings

### Finding 1 — LOW | `maglab/figure/primitives/catalog/multilayer-stack/primitive.py:131`, `hall-bar/primitive.py:158`, `coordinate-axes/primitive.py:68,78,93` | Unsanitized user-controlled strings inserted as SVG text node content — XML special characters cause cairosvg parse failure

**Defect.**
Three primitives insert user-controlled string parameters directly into SVG `<text>` element content without XML-escaping. The `<`, `>`, and `&` characters are forbidden in XML text nodes without entity encoding (`&lt;`, `&gt;`, `&amp;`), but none of the following insertion points perform this escaping:

`multilayer-stack/primitive.py` line 131:
```python
f'fill="#222">{label_text}</text>'  # label_text includes lay["name"] verbatim
```

`hall-bar/primitive.py` line 158:
```python
f'fill="#FFF">{label}</text>'  # label from params["label"]
```

`coordinate-axes/primitive.py` lines 68, 78, 93:
```python
f'...font-style="italic">{lx}</text>'  # lx, ly, lz from params
```

This is not a hypothetical XSS risk — it is a practical correctness bug. Material notation commonly used in magnetism research contains these characters: `CoFeB<10nm>`, `Fe₂O₃ & TiO₂`, `H<sub>eff</sub>`, `< 5 nm`. A `params = {"label": "CoFeB<10nm>"}` call on `hall-bar` or a `{"layers": [{"name": "CoFeB<10nm>", "thickness_nm": 1.0, "color": "#C00"}]}` call on `multilayer-stack` produces invalid XML. Verified with Python's `xml.etree.ElementTree`:

```
xml.etree.ElementTree.ParseError: not well-formed (invalid token): line 2, column 102
```

Since `cairosvg` uses `lxml` for SVG parsing — the same strict XML parser — it raises `XMLSyntaxError` on the malformed output. The `except Exception` clause in `compose.py` (line 169) silently catches this and renders a grey placeholder, giving the user no visible error message and an incorrect figure.

**Impact.** Any schematic panel that uses one of these three primitives with a label containing `<`, `>`, or `&` silently produces a grey box instead of the intended schematic. The user must investigate logs to find the cause.

**Fix.** Apply `html.escape()` (available in the stdlib, no new dependency) to all user-controlled strings before inserting them into SVG text content:

```python
import html

# multilayer-stack/primitive.py line 131
parts.append(
    f'<text x="{label_x:.1f}" y="{y + h / 2:.1f}" '
    f'font-size="{font_size:.1f}" dominant-baseline="middle" '
    f'fill="#222">{html.escape(label_text)}</text>'
)

# hall-bar/primitive.py line 158
parts.append(
    f'<text x="{sl / 2:.1f}" y="{sw * 1.5:.1f}" '
    f'font-size="9" text-anchor="middle" '
    f'dominant-baseline="middle" fill="#FFF">{html.escape(label)}</text>'
)

# coordinate-axes/primitive.py lines 68, 78, 93
f'...font-style="italic">{html.escape(lx)}</text>'
f'...font-style="italic" text-anchor="middle">{html.escape(ly)}</text>'
f'...font-style="italic">{html.escape(lz)}</text>'
```

`html.escape()` converts `<` → `&lt;`, `>` → `&gt;`, `&` → `&amp;`, which are the three characters that break SVG XML. It preserves all printable ASCII and Unicode safely.

---

### Finding 2 — LOW | `maglab/instrument/manual_rag.py:_TFIDFFallback` | Vocabulary dimension mismatch between `build()` and `search()` when index is loaded in a new Python session without sentence-transformers

**Defect.**
`_TFIDFFallback.embed()` fits its vocabulary from the first batch of texts it receives. When `SCPIIndex.build()` is called, the embedder is fitted on the chunk corpus (potentially hundreds of unique SCPI terms). The resulting dense vectors of dimension N are persisted to the SQLite database as JSON.

In a subsequent Python session (e.g., a CLI invocation after the index was already built), `ManualRAGPipeline.get_index()` creates a new `SCPIEmbedder` (with a fresh, unfitted `_TFIDFFallback` when `sentence-transformers` is absent). When `SCPIIndex.load()` is called, it restores `self._vecs` from the database (dimension N from the original corpus). When `search()` then calls `self._embedder.embed([query])[0]`, the fallback fits its vocabulary on the single-query batch. The query vocabulary typically has 1–5 unique words, producing a vector of dimension 1–5.

`_cosine_similarity()` handles mismatched dimensions by truncating to `min(N, 1–5)`, discarding almost the entire information content. In practice this means all stored vectors are evaluated on only the first word (alphabetically) of the query, producing essentially random similarity scores. The search returns incorrect results silently — no exception, no warning.

Reproduction path:
1. `sentence-transformers` not installed (TF-IDF fallback active).
2. Session A: `pipeline.ingest("model", pdf_path)` — builds index, embedder fitted on corpus.
3. Session B (new process): `pipeline.search("model", "voltage range")` — loads index, fresh embedder refits on `["voltage range"]` → dim=2. Stored vecs have dim=N. Similarities are random.

**Impact.** SCPI RAG search returns wrong results silently when `sentence-transformers` is not installed and the index was built in a different Python session. This is the primary offline-use path for the TF-IDF fallback.

**Fix.** The simplest fix is to persist the vocabulary alongside the index. In `SCPIIndex.build()`, serialize `_TFIDFFallback._vocab` to a JSON sidecar; in `SCPIIndex.load()`, restore it if present:

```python
# build(): after fitting, if using _TFIDFFallback
if hasattr(self._embedder._load_model(), "_vocab"):
    vocab_path = self._db_path.with_suffix(".vocab.json")
    vocab_path.write_text(
        json.dumps(self._embedder._load_model()._vocab), encoding="utf-8"
    )

# load(): restore vocabulary
vocab_path = self._db_path.with_suffix(".vocab.json")
if vocab_path.is_file():
    model = self._embedder._load_model()
    if hasattr(model, "_vocab"):
        model._vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
        model._fitted = True
```

Alternatively, prefer `sentence-transformers` installation in CI and document the fallback limitation clearly in the `_TFIDFFallback` docstring. The fallback is already documented as lower quality; making the cross-session failure explicit is the minimum acceptable fix.

---

## Non-Findings

The following items were investigated adversarially and found to be correct:

- **R5-F1 fix (SQLite connection leak)**: Confirmed correct — both `build()` and `load()` now use context manager form.
- **R5-F2 fix (SVG XML comment injection)**: Confirmed correct — `assemble_svg()` and `_empty_svg()` both apply `--` → `__` sanitization.
- **`render_quiver` figure lifecycle when `show_hsl=True`**: `render_hsl()` returns its figure to the caller. `render_quiver()` reuses that figure (no double-close). The `SimVizRenderer.render_panel()` closes `fig_tmp` in the `finally` block. No leak.
- **`render_2d` / `render_hsl` unguarded figure creation**: These are public functions that return `(fig, ax)` to the caller, who is responsible for closing. The `render_panel` path correctly wraps the returned figure in `try/finally plt.close(fig_tmp)`. The `render_standalone` path returns the figure to the caller — same contract as any matplotlib utility function.
- **`_TFIDFFallback.embed([])` with empty texts**: Correctly returns `[]` (empty list). `_fitted` is set to `True` with `_vocab = {}`, `dim = max(0, 1) = 1`. Subsequent query embeds produce a [0.0] vector. No crash.
- **`_cosine_similarity` with mismatched dimensions**: Truncates to `min(len(a), len(b))` — no divide-by-zero because zero-norm check is in place. Semantically wrong (see Finding 2) but not a crash.
- **`SCPIIndex.build()` with empty chunks**: Correctly returns early with a warning log; embedder is never called with empty list.
- **`assemble_svg()` primitive render error handling**: `except Exception` catches render failures and inserts an SVG comment `<!-- render error: <name> -->`. This comment text uses `prim.name` which comes from the primitive registry (not user input). Safe.
- **`SchematicRenderer._resolve_layout` LLM layout function error handling**: Correctly wraps the entire `llm_layout_fn` call in `except Exception` and falls back to the first-match heuristic.
- **`FigureComposer._make_axes` span validation**: Correctly checks both start position (`pos.row >= nrows`) and span end (`row_end > nrows`).
- **`DataPlotRenderer._extract_xy` with `len(dps) == 0`**: Unreachable — `_require_datapoints` is always called first and raises `IntegrityError` when `data_point_ids` is empty.
- **`SweepConfig.step = 0` validation**: Correctly rejected by `step_must_be_nonzero` validator.
- **`ScriptGenerator.generate()` `skip_safety_check=True` bypass exposure**: The public `generate_measurement_script()` convenience function never passes `skip_safety_check`; it calls `generator.generate(config, output_path=output_path)` with the default `False`.
- **`scaffold.py` `_model_to_class_name` with all-symbol model string**: Returns `""`, caught by `or "GenericInstrument"` on the same line.
- **`manual_search.py` path traversal in `_cache_path`**: `re.sub(r"[^\w\-]", "_", manufacturer)` and same for `model` sanitize both components before `Path` join.
- **`manual_search.py` `_try_download` filename construction**: Uses `safe_mfr` and `safe_mdl` (both pre-sanitized) for the filename. No `url` component in the filename. No traversal surface.
- **`skillgen.py` YAML frontmatter SCPI command injection**: `c.description[:60]` is truncated and used only in Markdown table cells with `|` escaped. No SVG or XML path.
- **`mock.py` `noise_amplitude=0.0` Gaussian noise**: `random.gauss(0.0, 1e-10)` is used when `noise_amplitude is None or 0`. `1e-10` replaces zero to avoid `gauss(0, 0)` which raises `ValueError` in Python's `random.gauss`. Correct.
- **`_load_ovf_numpy` zero-size grid guard**: `nx == 0 or ny == 0 or nz == 0` check correctly precedes the reshape. `ValueError` is raised with a descriptive message.
- **`safety.py` `_VOLT_PREFIXES` / `_CURR_PREFIXES` exclusion of bare `VOLT`/`CURR`**: Intentional and documented. Prevents false positives on range/compliance sub-node commands.
- **`check_script_text` lineno correction for sub-commands**: `lineno_map.setdefault(sub, i)` is inserted for all sub-commands at construction time (R4-F4 fix). The line-number correction loop `for v in result.violations + result.warnings` correctly updates `v.line_number` when `v.command` (the sub-command) is in the map.
- **`compose.py` `plt.close(fig)` on exception**: Present in the `except Exception: plt.close(fig); raise` block inside `compose()`. Also present in `DataPlotRenderer.render_single()`.
- **`styles/__init__.py` `load_style()` YAML injection**: Uses `yaml.safe_load()` — safe against YAML deserialization attacks.
- **`PrimitiveRegistry.load()` dynamic module import**: Registers module under `maglab._catalog.<name>` in `sys.modules`. Name comes from `md_path.parent.name` (directory name in the catalog). The directory names are developer-controlled and fixed at package time — no user input reaches this path.

---

## Summary Table

| # | Severity | File | Location | Issue |
|---|----------|------|----------|-------|
| 1 | LOW | `figure/primitives/catalog/multilayer-stack/primitive.py`, `hall-bar/primitive.py`, `coordinate-axes/primitive.py` | L131, L158, L68/78/93 | Unsanitized user-controlled strings in SVG `<text>` node content — `<`, `>`, `&` cause cairosvg `XMLSyntaxError` → silent grey placeholder |
| 2 | LOW | `instrument/manual_rag.py` | `_TFIDFFallback.embed()` | TF-IDF vocabulary not persisted — cross-session dimension mismatch produces wrong search results without sentence-transformers |
