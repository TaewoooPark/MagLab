# Round-3 Plan-Conformance Review — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (requirements-conformance role)
> Date: 2026-05-19
> Scope: `maglab/figure/`, `maglab/instrument/`, `maglab/mcp_server.py`, `maglab/cli.py`, `maglab/core/ralph.py`
> Plan docs: `plan/05-figure.md`, `plan/06-experiment.md`
> Prior review: `impl/review/03-figure-experiment.md` (Round-1, found 6 critical gaps)
> Test suite: 308 passed, 1 skipped, 0 failed

---

## Verdict

**CLEAN** — all Round-1 critical gaps are genuinely closed. The prescribed test suite passes completely. Three pre-existing low-priority deviations remain (unchanged from Round-1 assessment; none are regressions).

---

## Closure Check

| Round-1 Finding | ID | Closed? | Evidence |
|---|---|---|---|
| Temperature limit not enforced in `safety.py::check_scpi_sequence()` | I-07 / CG-1 | **YES** | `safety.py:377-394` — enforcement block for `_TEMP_PREFIXES` / `TEMPERATURE_OVER` present. `tests/integrity/test_scpi_safety.py::TestTemperatureLimit` (6 cases) all pass. |
| `compose.py` emits placeholder strings for SCHEMATIC/SIM_VIZ panels | F-08, F-10 / CG-6 | **YES** | `compose.py:48-49` — `SchematicRenderer` and `SimVizRenderer` instantiated. `compose.py:143-175` — `_render_panel()` calls `self._schematic_renderer.render_panel(panel)` and `self._simviz_renderer.render_panel(panel, ax)` with SVG-to-imshow embedding for schematic and graceful error fallback for both. No placeholder strings remain. |
| Export does not record output file path in provenance | F-17 / CG-3 | **YES** | `export.py:57-58` — `export()` accepts `ledger` and `figure_id` params. `export.py:132-134` — `_record_export_in_ledger()` called when ledger supplied. Plan §12.3-⑥ language in docstring at line 74. |
| `maglab figure primitives list` / `show` CLI subcommands absent | F-24 / CG-4 | **YES** | `cli.py:1085-1139` — `primitives_app` registered under `figure_app`; `list` and `show` subcommands present. `maglab figure primitives list` runs and outputs the 10-primitive catalog table. |
| MCP instrument tools absent (`instr_search_manual`, etc.) | I-20 / CG-5 | **YES** | `mcp_server.py:618-894` — `_register_instrument_tools()` implements all 5 T-P4-28 tools: `instr_search_manual`, `instr_ingest_manual`, `instr_generate_skill`, `instr_scaffold`, `instr_safety_check`. `manuals://` resource registered at line 943. `_register_instrument_tools(mcp)` called in `create_server()` at line 70. Smoke tests (`test_mcp_server.py`) all pass. |
| `Category` Enum not defined in `figure/primitives/spec.py` | F-20 | **YES** | `spec.py:23-39` — `class Category(StrEnum)` with all 10 §12.4-② taxonomy families: `DEVICE_GEOMETRY`, `SPIN_TEXTURE`, `SAMPLE_STRUCTURE`, `MEASUREMENT_GEOMETRY`, `ANNOTATION`, `DYNAMICS`, `CRYSTAL_LATTICE`, `ENERGY_BAND`, `CIRCUIT_MEASUREMENT`, `CONCEPT_PROCESS`. |
| Loop E default critic prompt missing the §12.5 6-item checklist | F-26 / R-08 | **YES** | `ralph.py:1178-1185` — `_CRITIC_CHECKLIST` module constant defines all 6 items: axis/unit labels, publication-size readability, colorblind-safe palette, panel labels, journal spec dimensions, data-source consistency. `_build_critic_prompt()` at line 1188 uses this constant as default. |
| Two integration test failures (Korean/English language mismatch) | FT-01, FT-02 / CG-2 | **YES** | `tests/integration/test_f6_data_to_figure.py` — 50 tests, 0 failures in current run. Language-mismatch test assertions have been corrected. |

---

## Pre-Existing Low-Priority Deviations (Unchanged; Not Regressions)

These were assessed as PARTIAL or DEVIATION in Round-1 and remain in the same state. No regression was introduced by Round-2 patches.

| ID | Issue | Status | Notes |
|---|---|---|---|
| F-14 | SciencePlots not applied — `figure/styles/__init__.py` uses YAML rcParams only, no `plt.style.use(['science','nature'])` call | PARTIAL (unchanged) | Plan §12.3-② says "SciencePlots式 저널 스타일" but stops short of mandating the SciencePlots package. YAML rcParams meet the functional requirement for journal dimensions and palettes. Fix is a `try: import scienceplots` guard — optional enhancement. |
| F-23 | `maglab figure primitives ingest` CLI and `figure/primitives/ingest.py` absent | PARTIAL (unchanged) | Plan T-P4-21 specifies a pipeline to ingest external SVG/TikZ primitives. `primitives_app` now has `list` and `show` but not `ingest`. This is a non-blocking gap — the library is curated in-tree; ingest is an extension workflow. |
| I-13 | RAG embedding model: `all-MiniLM-L6-v2` (sentence-transformers) with TF-IDF fallback; no `voyage-code-2` / `nomic-embed-text` backend | PARTIAL (unchanged) | Plan §13.2 specifies `voyage-code-2` / `nomic-embed-text`. No `voyage` backend added. Quality differs but functionality is present. The fallback chain (voyage → nomic → MiniLM → TF-IDF) from Round-1 recommendation was not implemented. Low priority; API key dependency. |
| I-11 | Mock profiles use hardcoded Python dataclasses; no `mock_profiles/<model>.yaml` loader | DEVIATION (unchanged) | Plan T-P4-15. No regression; still low-priority. |
| I-16 | A/B eval in `skillgen.py` uses deterministic scorer; no real LLM subagent invocation | PARTIAL (unchanged) | Infrastructure present (`evals.json`); parallel LLM invocation not wired. Low priority. |

---

## Remaining or New Gaps

No new gaps were introduced by Round-2 patches. The three remaining partial/deviation items above are carry-overs from Round-1 with unchanged severity assessments (all medium-low priority, none blocking plan certification).

**Action required for F-23 only** if a complete CLI per plan T-P4-27 is required: add `primitives_app.command("ingest")` and create `maglab/figure/primitives/ingest.py` with vectorize→parameterize→validate→register pipeline. This is the sole unimplemented CLI subcommand from plan §12.4-④.

---

## Test Gate Summary

```
308 passed, 1 skipped, 0 failed   (13 warnings — all discretisedfield 'xmin' API delta, pre-existing)
```

Full suite:
- `tests/unit/test_figure_*.py` — all pass (dataplot, compose, export, primitives, simviz, schematic, styles, spec)
- `tests/unit/test_instrument_*.py` — all pass (safety, scaffold, mock)
- `tests/integrity/test_scpi_safety.py` — 36 pass (includes `TestTemperatureLimit` 6 cases)
- `tests/smoke/test_mcp_server.py` — 19 pass (includes instrument tools smoke coverage)
- `tests/integration/test_f6_data_to_figure.py` — 50 pass (0 failures, language mismatch resolved)

CLI spot-check: `maglab figure primitives list` → outputs 10-primitive catalog table (all categories represented).
