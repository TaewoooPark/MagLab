# Requirements-Conformance Review — Figure Engine & Experiment/Instrument Layer

> Reviewer: Claude Sonnet 4.6 (requirements-conformance role)
> Date: 2026-05-19
> Scope: `maglab/figure/`, `maglab/instrument/`, `maglab/core/ralph.py` (Loop B/E portions)
> Plan docs: `plan/05-figure.md`, `plan/06-experiment.md`
> Impl docs: `impl/02-P1-figure-sim.md`, `impl/05-P4-instrument-figure.md`
> Test counts: 357 passed, 2 failed, 1 skipped (full suite run)

---

## Summary

Overall verdict: **Solid P1 core; P4 mostly implemented; several gaps requiring attention.**

| Status | Count |
|---|---|
| MET | 31 |
| PARTIAL | 8 |
| MISSING | 6 |
| DEVIATION | 3 |

**Critical observations:**
1. Two integration test failures due to error-message language mismatch (Korean expected, English produced) — easy fix but currently breaking the test gate.
2. Temperature limit check is defined in `SafetyProfile` and `ViolationType` but the enforcement block in `SafetyChecker.check_scpi_sequence()` is missing.
3. `compose.py` does not wire `SimVizRenderer` or `SchematicRenderer` — both P3/P4 panels emit placeholder text stubs only.
4. `figure export.py` does not record the output file path in provenance — the plan requires this.
5. `maglab figure primitives` CLI subcommand is absent (plan: `maglab figure primitives list`/`ingest`).
6. MCP instrument tools (`instr_search_manual`, `instr_ingest_manual`, `instr_generate_skill`, `instr_scaffold`, `instr_safety_check`, `manuals://` resource) are absent from `mcp_server.py`.
7. RAG embedding model deviates from plan: plan specifies `voyage-code-2` / `nomic-embed-text`; implementation uses `all-MiniLM-L6-v2` (sentence-transformers) with TF-IDF fallback.
8. ELN (`lab/notebook`), measurement planning (`lab/planning`), and active-learning DOE (`§13.5–§13.7`) are absent — these are planned for P5 but are listed in `plan/06-experiment.md`; the P4 impl doc correctly defers them, so this is a phase boundary, not a gap.

---

## Findings

### Figure Engine (plan/05-figure.md · impl/02-P1-figure-sim.md)

| # | Requirement | Status | Evidence | Gap | Recommended Fix |
|---|---|---|---|---|---|
| F-01 | FigureSpec IR — panels, data binding, layout, journal target, caption, provenance_ids auto-collection | **MET** | `maglab/figure/spec.py:202-260`; `tests/unit/test_figure_spec.py` (all pass) | — | — |
| F-02 | Honesty gate: DATA_PLOT panel with empty `data_point_ids` raises `ValidationError` | **MET** | `spec.py:153-165`; `test_figure_spec.py::test_data_plot_requires_data_point_ids`; `test_figure_dataplot.py::TestIntegrityGate` | — | — |
| F-03 | DATA_PLOT panel must specify `plot_kind` | **MET** | `spec.py:167-174`; `test_figure_spec.py::test_data_plot_requires_plot_kind` | — | — |
| F-04 | PlotKind catalog: HYSTERESIS, HALL, FMR, DISPERSION, XY | **MET** | `spec.py:35-49`; `test_figure_spec.py::test_all_plot_kinds` | — | — |
| F-05 | DataPlotRenderer — renders from DataPoint only; value accuracy validated at Line2D level | **MET** | `maglab/figure/renderers/dataplot.py`; `test_figure_dataplot.py::TestDataValueAccuracy` (all plot kinds pass with `np.testing.assert_array_almost_equal`) | — | — |
| F-06 | DataPlotRenderer — overlay DataPoints | **MET** | `dataplot.py:304-321`; `test_figure_dataplot.py::test_overlay_values_exact` | — | — |
| F-07 | SchematicRenderer — LLM→SVG on top of primitives, provenance comments, Inkscape/cairosvg PDF | **MET** | `maglab/figure/renderers/schematic.py`; `test_figure_schematic.py` (all pass) | — | — |
| F-08 | SchematicRenderer wired into `compose.py` for SCHEMATIC panels | **MISSING** | `compose.py:134-144` only renders a placeholder text `"[schematic — P4]"`. `SchematicRenderer` is never called. | Users cannot produce a schematic panel in a composed multi-panel figure via `FigureComposer`. | `compose.py`: import and instantiate `SchematicRenderer`; call `render_panel()` and embed the returned SVG into the matplotlib axes via `ax.imshow()` or embed as a `FigureImage`. |
| F-09 | SimVizRenderer — 2D slice, HSL color wheel, quiver overlay, 3D PyVista | **MET** | `maglab/figure/renderers/simviz.py`; `test_figure_simviz.py` (all pass; warns on discretisedfield API delta but falls back correctly) | — | — |
| F-10 | SimVizRenderer wired into `compose.py` for SIM_VIZ panels | **MISSING** | `compose.py:145-155` only renders `"[sim-viz — P3]"` placeholder. `SimVizRenderer` is never imported or called. | Users cannot render OVF/micromagnetic panels in a composed multi-panel figure. | `compose.py`: import `SimVizRenderer`; call `renderer_simviz.render_panel(panel, ax)`. |
| F-11 | Journal style profiles — Nature 89/183 mm, APS 86/178 mm, IEEE 88.9/182 mm, Elsevier 90/190 mm | **MET** | `figure/styles/nature.yaml:5-6`, `aps.yaml`, `ieee.yaml`, `elsevier.yaml` all match plan Appendix G | — | — |
| F-12 | StyleProfile loads YAML and injects rcParams (fonttype, palette, line widths) | **MET** | `figure/styles/__init__.py`; `test_figure_styles.py` (all pass) | — | — |
| F-13 | Colorblind-safe palette (Wong 2011 / Okabe-Ito) in all style YAMLs | **MET** | `nature.yaml:27-36` (Wong 2011 8-color); all other journal YAMLs include equivalent palettes | — | — |
| F-14 | SciencePlots integration for journal-style rcParams | **MISSING** | `scienceplots` is not imported or called anywhere in `maglab/figure/`. Plan §12.3-② specifies "SciencePlots式 저널 스타일". | SciencePlots preset styles (e.g. `plt.style.use(['science','nature'])`) are not applied; YAML-only rcParams substitute. | `figure/styles/__init__.py::StyleProfile.rcparams()`: attempt `import scienceplots; plt.style.use([journal])` before applying YAML overrides, guarded by `try/except ImportError`. |
| F-15 | FigureComposer — GridSpec multi-panel, panel labels a/b/c, journal column width | **MET** | `compose.py:35-178`; `test_figure_compose.py` (all pass) | — | — |
| F-16 | FigureExporter — PDF (fonttype=42), EPS, SVG (fonttype=none), TIFF | **MET** | `export.py:77-116`; `test_figure_export.py` (all pass) | — | — |
| F-17 | Export records output file path in provenance | **MISSING** | `export.py` has no provenance recording. Plan §12.3-⑥: "내보낸 파일 경로를 provenance에 기록". | The export event is not tracked in the provenance ledger. | `export.py::FigureExporter.export()`: accept an optional `ledger` parameter; call `ledger.record_figure_export(out_path, ...)` on save. |
| F-18 | Primitive contract (`Primitive` protocol) — name, category, tags, description, parameters, render(), physics_convention, references, provenance, preview, journal_styles | **MET** | `figure/primitives/spec.py:22-84`; protocol attributes all declared | — | — |
| F-19 | PrimitiveRegistry — search, load, list_all interfaces (P1 keyword, P4 full implementation) | **MET** | `figure/primitives/spec.py:87-174` (P1 keyword search); `figure/primitives/registry.py` (P4 `CatalogRegistry` with dynamic import); `test_figure_primitives.py` (all pass) | — | — |
| F-20 | Category taxonomy as Enum | **PARTIAL** | `spec.py` defines `Primitive` Protocol but `Category` Enum is not defined. P4 impl doc (T-P4-18) specifies "카테고리 택소노미를 `Category` Enum으로 정의". Catalog entries use free-form strings. | No enum enforcement on `category` field. | `figure/primitives/spec.py`: add `class Category(StrEnum)` with all 10 taxonomy families from §12.4-②. |
| F-21 | Core primitive catalog — minimum 10 primitives spanning 5+ categories | **MET** | Catalog has 10 primitives: `bloch-domain-wall`, `coordinate-axes`, `hall-bar`, `llg-precession`, `measurement-geometry`, `mtj-pillar`, `multilayer-stack`, `neel-domain-wall`, `skyrmion-bloch`, `spin-texture-colorwheel`. Covers: device geometry, spin texture, annotation, dynamics, measurement geometry. | — | — |
| F-22 | Missing taxonomy categories in catalog: crystal/lattice, energy/band, circuit/measurement | **PARTIAL** | Plan §12.4-② lists 10 families; current catalog covers 5 of them. "결정/격자", "에너지/밴드", "회로/계측", "개념/공정", "동역학(Walker/마그논 분산)" are absent or partial. | Research-grade schematics for reciprocal-space and circuit figures cannot be constructed from primitives. | T-P4-20 specifies "최소 10개" across 5 categories — current state passes the count threshold but taxonomy breadth is narrow. Prioritize Brillouin zone / k-path and lock-in circuit primitives for real workflows. |
| F-23 | Primitive ingest pipeline (`maglab figure primitives ingest`) | **MISSING** | `figure/primitives/ingest.py` does not exist. Plan T-P4-21. | No workflow to bring in external SVG/TikZ primitives. | Create `maglab/figure/primitives/ingest.py` with vectorize→parameterize→validate→register pipeline; add `maglab figure primitives ingest` CLI. |
| F-24 | `maglab figure primitives list` / `ingest` CLI | **MISSING** | CLI at `maglab/cli.py` has no `primitives` subgroup under `figure`. Running `maglab figure primitives --help` errors. T-P4-27. | Users cannot list or ingest primitives via CLI. | `cli.py`: add `primitives_app = typer.Typer()`; register `list` and `ingest` under `figure_app`. |
| F-25 | Loop E (Figure refinement Ralph) — render → rasterize → vision critic → fix → repeat | **MET** | `core/ralph.py::run_loop_e()`; `test_ralph_loops.py::TestLoopEBasic` (all pass including no-vision-model skip, applies-fixes-and-passes, circuit-breaker-max-iter) | — | — |
| F-26 | Loop E vision critic checklist (axis labels, colorblind, panel labels, journal spec, data provenance) | **PARTIAL** | `ralph.py` calls `vision_critic_fn` with a prompt string; prompt content defined at `ralph.py` lines ~1280-1310 but the actual checklist items in the prompt are a generic template. Plan §12.5 specifies 6 specific items; implementation leaves the prompt as a parameter injectable by the caller. | Caller must supply a well-formed prompt — no built-in enforcement of the 6-item checklist. | `ralph.py::run_loop_e()`: define `_DEFAULT_CRITIC_PROMPT` with all 6 §12.5 items as a module-level constant and use it when `critic_prompt` kwarg is None. |
| F-27 | F6 pipeline (`maglab sim plot`) — CSV → infer PlotKind → DataPoint → FigureSpec → render → PDF | **MET** | `maglab/sim/plot.py`; CLI `maglab sim plot`; integration tests in `test_f6_data_to_figure.py` (mostly pass) | — | — |

---

### Integration Test Failures (test_f6_data_to_figure.py)

| # | Test | Status | Evidence | Gap | Recommended Fix |
|---|---|---|---|---|---|
| FT-01 | `TestLoadCsvDatapoints::test_header_only_raises_value_error` | **DEVIATION** | Test expects `match="수치 데이터가 없습니다"` (Korean); `sim/plot.py:114` raises `"CSV contains no numeric data: ..."` (English). Korean-→English migration in progress but test regex is still Korean. | Test gate broken. | Either: update `sim/plot.py:114` message to Korean, OR (preferred after language migration) update test to `match="no numeric data"`. Fix: `sim/plot.py:114` → `raise ValueError(f"No numeric data in CSV: {path}")` and update test match string accordingly. |
| FT-02 | `TestBuildFigureSpec::test_empty_col_dps_raises` | **DEVIATION** | Test expects `match="비어 있습니다"` (Korean); `sim/plot.py:227` raises `"DataPoint is empty. Load data from CSV first."` (English). Same language-mismatch pattern. | Test gate broken. | `sim/plot.py:227` → keep English; update test `match` to `"empty"` or `"Empty"`. |

---

### Instrument Layer (plan/06-experiment.md · impl/05-P4-instrument-figure.md)

| # | Requirement | Status | Evidence | Gap | Recommended Fix |
|---|---|---|---|---|---|
| I-01 | PyVISA scaffold generation (`scaffold.py`, Jinja2 `scaffold.py.j2`) | **MET** | `maglab/instrument/scaffold.py`; `templates/scaffold.py.j2`; `test_instrument_scaffold.py` (all pass) | — | — |
| I-02 | SCPI sequence generation (`SCPIGenerator`) with safe ordering | **MET** | `maglab/instrument/scpi.py:294-378`; `test_instrument_scpi.py`; `test_scpi_safety.py::TestNormalSequences::test_generator_output_passes_safety` | — | — |
| I-03 | SCPI static validation — command-order rules (INIT→CONFIG→OUTPUT→MEASURE→CLEANUP) | **MET** | `scpi.py:202-286`; `test_scpi_safety.py::TestCommandOrderViolation` (all pass) | — | — |
| I-04 | SCPI safety: voltage limit enforcement (over/under) | **MET** | `safety.py:286-319`; `test_scpi_safety.py::TestVoltageLimit` (all pass including boundary) | — | — |
| I-05 | SCPI safety: current limit enforcement | **MET** | `safety.py:321-354`; `test_scpi_safety.py::TestCurrentLimit` (all pass) | — | — |
| I-06 | SCPI safety: magnetic field limit enforcement | **MET** | `safety.py:356-374`; `test_scpi_safety.py::TestFieldLimit` (all pass) | — | — |
| I-07 | SCPI safety: temperature limit enforcement | **MISSING** | `SafetyProfile.max_temperature_k` field and `ViolationType.TEMPERATURE_OVER` are declared (`safety.py:41,122`), `_TEMP_PREFIXES` list is declared (`safety.py:217-221`), but the enforcement block is **absent** from `check_scpi_sequence()`. The loop handles voltage/current/field but has no temperature check block. | A `TEMP 400` command (400K > any limit) passes silently. Safety claim in plan Appendix D is unmet for temperature. | `safety.py::SafetyChecker.check_scpi_sequence()`: add a temperature limit check block after the field block, mirroring the field pattern using `_TEMP_PREFIXES` and `self._profile.max_temperature_k`. Add a test to `test_scpi_safety.py::TestFieldLimit` or a new `TestTemperatureLimit` class. |
| I-08 | SCPI safety: script text validation (extract `.write()` calls) | **MET** | `safety.py:401-450`; `test_scpi_safety.py::TestScriptTextValidation` (all pass) | — | — |
| I-09 | Built-in safety profiles: keithley-2400, sr830, keithley-2182 | **MET** | `safety.py:49-100`; tests exercise both keithley-2400 and sr830 paths | — | — |
| I-10 | Mock instrument (`MockResource`, `MockResourceManager`, built-in SR830/Keithley profiles) | **MET** | `maglab/instrument/mock.py`; `test_instrument_mock.py` (all pass) | — | — |
| I-11 | Mock profile YAML files (`mock_profiles/<model>.yaml`) | **DEVIATION** | Plan T-P4-15 specifies "모델별 목 프로파일(`mock_profiles/<model>.yaml`)로 파라미터 설정". Implementation uses hardcoded Python dataclasses in `mock.py`, not YAML files. | No YAML-based profile overrides possible without code changes. | Low-priority deviation for correctness; YAML loading would allow user-supplied profiles. Add `~/.local/share/maglab/mock_profiles/<model>.yaml` loader as optional override path. |
| I-12 | Manual search (`manual_search.py` — web search, SHA256 cache) | **MET** | `maglab/instrument/manual_search.py`; `test_instrument_manual_rag.py` exercises the cache path | — | — |
| I-13 | Manual RAG — SCPI-per-chunk, LanceDB / sqlite-vec index | **PARTIAL** | `manual_rag.py` implements SCPI chunking and a sqlite-vec index. Plan §13.2 specifies `voyage-code-2` (online) or `nomic-embed-text` (local Ollama) embeddings. Implementation uses `all-MiniLM-L6-v2` (sentence-transformers) with TF-IDF fallback. | Embedding quality differs from plan specification. `voyage-code-2` is optimized for code/SCPI commands and gives materially better recall. | `manual_rag.py::LocalEmbedder.__init__()`: add optional `voyage` backend using the `voyageai` package when API key is present; default model fallback chain: voyage-code-2 → nomic-embed-text (Ollama) → all-MiniLM-L6-v2 → TF-IDF. |
| I-14 | `maglab instr ingest <model>` CLI (search → extract → index pipeline) | **MET** | CLI `maglab instr ingest` present and wired; `test_instrument_manual_rag.py` tests pipeline | — | — |
| I-15 | Skill generation — `skillgen.py` producing SKILL.md + SCPI_REFERENCE.md + LIMITS.md + scripts/ + evals/ | **MET** | `maglab/instrument/skillgen.py`; `test_instrument_skillgen.py` (all pass) | — | — |
| I-16 | A/B evaluation pipeline (`skillgen.py` — skill-loaded vs baseline scoring) | **PARTIAL** | `skillgen.py` generates `evals/results.json` format but the actual parallel subagent invocation (plan T-P4-10) is simulated by a deterministic scorer only; no real LLM A/B comparison occurs. | A/B results may not meaningfully discriminate skill quality without real LLM calls. | Low-priority; the infrastructure (evals.json, results.json) is present. Wire `core/subagents.py` parallel invocation when a real eval harness is needed. |
| I-17 | Measurement script generation (`script.py`) | **MET** | `maglab/instrument/script.py`; `test_instrument_script.py` (all pass) | — | — |
| I-18 | Model name guessing prohibition in `manual_search.py` | **MET** | `manual_search.py:4-5` docstring: "★ Always confirm the instrument model name — never guess"; CLI enforces user-provided model. | — | — |
| I-19 | `maglab instr` CLI — all 6 subcommands (scaffold, scpi, script, check, ingest, implement) | **MET** | `maglab instr --help` shows all 6 subcommands | — | — |
| I-20 | MCP instrument tools (T-P4-28): `instr_search_manual`, `instr_ingest_manual`, `instr_generate_skill`, `instr_scaffold`, `instr_safety_check`, `manuals://` resource | **MISSING** | `mcp_server.py` only contains P0/P1 tools (physics, sim, figure_render, figure_export). No instrument-domain MCP tools are registered. | Claude Code MCP clients cannot call instrument tools programmatically. | `mcp_server.py`: add `_register_instrument_tools(mcp)` function with the 5 tools listed in T-P4-28; add `manuals://` URI resource listing cached manuals. |

---

### Ralph Loop Engine (plan/01-harness.md §6 · impl/05-P4-instrument-figure.md Group A)

| # | Requirement | Status | Evidence | Gap | Recommended Fix |
|---|---|---|---|---|---|
| R-01 | Ralph in-session mode — `<promise>DONE</promise>` signal, state file, max_iterations=20/50 | **MET** | `core/ralph.py::RalphEngine`; `run_loop_b/d/e`; `test_ralph_loops.py::TestLoopBBasic::test_loop_b_passes_on_first_try` | — | — |
| R-02 | Ralph detached fresh-context mode — state file persistence across processes | **MET** | `ralph.py::RalphEngine.detached_loop()`; `test_ralph_loops.py::TestLoopResume::test_ralph_engine_detached_mode_state_persistence` | — | — |
| R-03 | Circuit breaker — 4 conditions: no-progress×3, repeated-error×5, similarity>0.95, budget-exceeded | **MET** | `ralph.py::CircuitBreakerState`; `test_ralph_loops.py` covers all 4 stop reasons across Loop B/D/E | — | — |
| R-04 | `maglab ralph start/status/cancel` CLI | **MET** | `maglab ralph --help` shows all 3 subcommands | — | — |
| R-05 | Loop B — experiment code: mock pytest dry-run → failure parsing → fix | **MET** | `ralph.py::run_loop_b()`; `test_ralph_loops.py::TestLoopBBasic` (passes, fixes-failing-code, circuit-breaker, max-iter, budget all verified) | — | — |
| R-06 | Loop D — effect fitting: chi2/R2 check, residuals randomness, physics boundary | **MET** | `ralph.py::run_loop_d()`; `ralph.py::_check_fit_quality()`; `test_ralph_loops.py::TestLoopDBasic` + `TestFitCheckResult` all pass | — | — |
| R-07 | Loop E — figure refinement: render → rasterize → critic → fix | **MET** | `ralph.py::run_loop_e()`; `test_ralph_loops.py::TestLoopEBasic` all pass | — | — |
| R-08 | Default Loop E critic prompt enumerates all 6 §12.5 checklist items | **PARTIAL** | Prompt parameter is caller-supplied with no enforced default checklist. See F-26. | — | See F-26. |

---

## Critical Gaps (Ranked by Severity)

### CRITICAL — Safety

**CG-1: Temperature limit not enforced in `safety.py`** (I-07)
- File: `maglab/instrument/safety.py`, line ~374 (after field block, before unknown-command block)
- `_TEMP_PREFIXES` is declared but no enforcement block exists. A command like `TEMP 9999` passes silently regardless of `SafetyProfile.max_temperature_k`.
- Fix: Add temperature check block; add unit test in `test_scpi_safety.py`.

### HIGH — Test Gate

**CG-2: Two integration test failures due to error-message language mismatch** (FT-01, FT-02)
- Files: `tests/integration/test_f6_data_to_figure.py:194` and `:325`; `maglab/sim/plot.py:114,227`
- Test regexes expect Korean strings; implementation uses English.
- Fix: Align all error messages to English (consistent with the concurrent language migration) and update test `match=` patterns.

### HIGH — Provenance Integrity

**CG-3: Export does not record output file path in provenance** (F-17)
- File: `maglab/figure/export.py`
- Plan §12.3-⑥ requires the saved file path to be recorded in the provenance system.
- Fix: Accept optional ledger; call provenance record after `fig.savefig(out, ...)`.

### HIGH — User Reachability

**CG-4: `maglab figure primitives` CLI missing** (F-24)
- File: `maglab/cli.py`
- `maglab figure primitives list` and `ingest` subcommands do not exist. The registry implementation (`figure/primitives/registry.py`) is ready; CLI wiring is absent.
- Fix: Add `primitives_app` under `figure_app` in `cli.py`.

**CG-5: MCP instrument tools absent** (I-20)
- File: `maglab/mcp_server.py`
- None of the P4 instrument-domain MCP tools (T-P4-28) are registered. The CLI works; MCP access does not.
- Fix: Add `_register_instrument_tools(mcp)` in `mcp_server.py`.

### MEDIUM — Rendering Correctness

**CG-6: `compose.py` does not dispatch to `SchematicRenderer` or `SimVizRenderer`** (F-08, F-10)
- File: `maglab/figure/compose.py:134-155`
- Both P4 panel types render placeholder text only. Standalone renderers (`schematic.py`, `simviz.py`) are fully implemented and tested, but `FigureComposer` never calls them.
- Fix: Import and call `SchematicRenderer.render_panel()` and `SimVizRenderer.render_panel()` in `_render_panel()`.

---

## User-Perspective Check

What the plan promises that a user **cannot** do today:

| CLI / Workflow | Plan Promise | Actual State |
|---|---|---|
| `maglab figure primitives list` | List all catalog primitives | Command does not exist → error |
| `maglab figure primitives ingest <svg>` | Register external SVG/TikZ as primitive | `ingest.py` does not exist |
| Compose a figure with a SCHEMATIC panel | Multi-panel with Hall bar schematic overlaid on data plot | Placeholder text `"[schematic — P4]"` shown instead |
| Compose a figure with a SIM_VIZ panel in multi-panel layout | OVF magnetization beside data plot | Placeholder text `"[sim-viz — P3]"` shown (standalone `SimVizRenderer` works; compose wiring absent) |
| MCP tool `instr_safety_check` | Check script safety via MCP client | Tool not registered in `mcp_server.py` |
| MCP resource `manuals://` | List cached instrument manuals | Resource not registered |
| Export file tracked in provenance | Auto-audit which figures were saved | Not implemented |
| Temperature limit in safety gate | Script with `TEMP 500` on a 400K-limited cryostat is blocked | Passes silently |
| SciencePlots journal presets | `plt.style.use(['science','nature'])` applied to plots | Not applied; YAML rcParams only |

The following P5 features are correctly absent (phase boundary, not gaps):
- ELN (`maglab lab note`)
- Measurement planning (`maglab lab plan`)
- Active-learning DOE (§13.7)
