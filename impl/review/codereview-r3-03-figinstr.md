# Code Review Round 3 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-19
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit + targeted `uv run python` probes

---

## Verdict

**ISSUES FOUND** — 6 genuine defects across both domains, ranging from HIGH (safety gate false-negative, broken catalog wiring) to MEDIUM/LOW.

---

## Findings

### Finding 1 — HIGH | `maglab/instrument/safety.py:508–518` | Safety false-negative: `check_script_text` deduplication silently drops repeated SCPI commands in unsafe context

**Defect.**
`check_script_text()` builds an `ordered` list by walking the source file line by line and inserting each SCPI command into a `seen: set[str]` set. When the *same exact command string* appears more than once, only the *first occurrence* is kept; subsequent occurrences are silently discarded before the list is handed to `check_scpi_sequence()`.

This defeats the `OUTPUT_ACTIVE_PARAM_CHANGE` safety rule when:
1. The same voltage/current-setter command appears first in the CONFIG phase (output off — safe).
2. It then appears again after `OUTP ON` (output active — unsafe).

After deduplication the unsafe second occurrence is removed and the checker never sees it. The method returns `ok=True` even though the physical instrument would receive a parameter change while its output is live.

Verified by probe:
```python
script = """
instr.write('*RST')
instr.write(':SOUR:VOLT 1.0')   # safe: before OUTP ON
instr.write('OUTP ON')
instr.write(':SOUR:VOLT 1.0')   # UNSAFE: same string, deduped out
"""
result = checker.check_script_text(script)
# result.ok == True  ← wrong: should be False (OUTPUT_ACTIVE_PARAM_CHANGE)
```

**Fix.** Replace the `seen`-set deduplication with an approach that preserves all occurrences in program order, accepting that the same command may be checked multiple times. Alternatively, pass `(lineno, cmd)` tuples rather than plain strings so different-line instances are distinct. The line-number remap at the end of the method handles duplicates correctly once they are in the list.

---

### Finding 2 — HIGH | `maglab/figure/renderers/schematic.py:300–302` | `SchematicRenderer` always uses the empty P1 stub registry; 10-primitive catalog is dead code

**Defect.**
`SchematicRenderer.__init__` defaults to `spec.default_registry`:

```python
# schematic.py:300-302
from maglab.figure.primitives.spec import default_registry
self._registry = registry or default_registry
```

`spec.default_registry` is defined as `PrimitiveRegistry()` — the empty P1 stub (spec.py:194). The fully loaded `CatalogRegistry` (10 primitives in `catalog/`) is constructed by `make_default_registry()` in `registry.py` and is *never* assigned to `spec.default_registry`.

Consequence: `self._registry.search(query)` always returns `[]`. Every schematic panel
hits the "no results" branch and emits an empty SVG placeholder (`[schematic — no primitives]`)
regardless of the query. The entire primitive catalog — all 10 physics schematics — is unreachable
via the default `FigureComposer().compose(spec, ledger)` call path (the same path used by `cli.py` and `mcp_server.py`).

Verified by probe:
```python
renderer = SchematicRenderer()          # no explicit registry
print(len(renderer._registry))         # → 0
svg = renderer.render_panel(panel)
print('[schematic — no primitives]' in svg)  # → True
```

**Fix.** In `SchematicRenderer.__init__`, default to the loaded catalog:
```python
from maglab.figure.primitives.registry import make_default_registry
self._registry = registry or make_default_registry()
```

---

### Finding 3 — MEDIUM | `maglab/instrument/safety.py:207–214` | Bare `CURR` / `:CURR` prefix triggers false-positive current violations for non-setpoint commands

**Defect.**
`SafetyChecker._CURR_PREFIXES` includes the bare strings `"CURR"` and `":CURR"`:

```python
_CURR_PREFIXES = (
    ":SOUR:CURR", "CURR", "SOUR:CURR", ":CURR", ":OUTPUT:CURR", "OUTPUT:CURR"
)
```

`CURR:COMP` (current compliance limit), `CURR:RANG` (measurement range), `CURR:STEP`, and similar sub-tree commands all start with `CURR` and are matched as if they set the output current. When a profile has `max_current_a` defined, these commands trigger spurious `CURRENT_OVER` violations.

Verified:
```python
profile = SafetyProfile(model='test', max_current_a=1.0)
checker = SafetyChecker(profile)
result = checker.check_scpi_sequence(['*RST', 'CURR:COMP 2.0'])
# result.ok == False, violation: "Current 2 A exceeds the maximum limit of 1 A."
# WRONG: CURR:COMP sets the protection limit, not the output current.
```

**Fix.** Replace bare `"CURR"` / `":CURR"` with the explicit setpoint sub-nodes: `:SOUR:CURR:LEV`, `SOUR:CURR:LEV`, `:CURR:LEV`, `CURR:LEV`, `OUTPUT:CURR:LEV` (mirroring how `_VOLT_PREFIXES` excludes the bare `VOLT` sub-node per the existing `MEDIUM-3` comment at line 193).

---

### Finding 4 — MEDIUM | `maglab/cli.py:1258–1262, 1290–1295, 1326–1334` | Composed matplotlib figures are never closed after export — resource leak

**Defect.**
Three CLI commands — `figure render`, `figure compose`, and `figure export` — call `FigureComposer().compose()` and then `FigureExporter().export()` or `export_all()`, but never call `plt.close(fig)` afterwards. Each CLI invocation leaks one (or more for `export_all`) unclosed matplotlib figure.

For context: `maglab/sim/plot.py:352` and `maglab/mcp_server.py:539,603` correctly close the figure after export; the CLI commands do not.

```python
# cli.py ~1258-1262 (figure_render_cmd) — no plt.close(fig)
fig = composer.compose(spec, ledger)
saved = exporter.export(fig, out_path, fmt=fmt)
# ← fig is leaked
```

In a long-running server process or batch script that invokes these paths repeatedly, figures accumulate in matplotlib's global figure manager and consume memory.

**Fix.** Add `plt.close(fig)` (or a `try/finally` block) after `export()` / `export_all()` in all three CLI command functions.

---

### Finding 5 — MEDIUM | `maglab/instrument/scaffold.py:70–77` | `_model_to_class_name` returns an invalid Python identifier for digit-starting model names, generating syntactically broken code

**Defect.**
```python
def _model_to_class_name(model: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]", "", model)
    parts = cleaned.split()
    return "".join(p.capitalize() if not p[0].isdigit() else p for p in parts if p)
```

When the model name starts with a digit (e.g. `"2400"`, `"2182A"`), `p[0].isdigit()` is `True`, so `p` is used verbatim, and the joined result is `"2400"`. This non-empty string passes the `or "GenericInstrument"` fallback in `generate_scaffold()` (line 122: `class_name = _model_to_class_name(model) or "GenericInstrument"`), so the Jinja2 template receives `class_name="2400"` and emits:

```python
class 2400:   # SyntaxError
    ...
```

The generated scaffold is a syntactically invalid Python file.

Common real-world inputs: `maglab instr scaffold 2400`, `maglab instr scaffold 2182A`.

**Fix.**
```python
return "".join(p.capitalize() if not p[0].isdigit() else p for p in parts if p)
# Should prepend 'Instr' when the result starts with a digit:
result = "".join(...)
if result and result[0].isdigit():
    result = "Instr" + result
return result
```

---

### Finding 6 — MEDIUM | `maglab/figure/spec.py:111` / `maglab/figure/renderers/dataplot.py:292–296` | `AxisSpec.lim` accepts lists of any length; `_apply_axis_spec` raises `IndexError` for `lim=[]` or `lim=[x]`

**Defect.**
`AxisSpec.lim` is typed as `list[float] | None` with no length constraint. In `_apply_axis_spec()`:

```python
if panel.x_axis.lim is not None:
    xlim = panel.x_axis.lim
    ax.set_xlim((xlim[0], xlim[1]))   # IndexError if len(xlim) < 2
```

`lim=[]` raises `IndexError: list index out of range` at `xlim[0]`. `lim=[1.0]` raises the same at `xlim[1]`. Both are semantically invalid values that Pydantic currently accepts silently.

The `IndexError` propagates up through `render_panel()`, and is caught by `compose()`'s `try/except` which closes the figure and re-raises — so no resource leak occurs. But the caller receives a bare `IndexError` rather than a descriptive `ValueError`.

**Fix.** Add a Pydantic field validator to `AxisSpec`:
```python
@field_validator("lim")
@classmethod
def lim_must_have_two_elements(cls, v: list[float] | None) -> list[float] | None:
    if v is not None and len(v) != 2:
        raise ValueError(f"lim must have exactly 2 elements [min, max], got {len(v)}")
    return v
```

---

### Finding 7 — LOW | `maglab/instrument/manual_search.py:337` | Unsanitized `manufacturer` argument in `_try_download` filename enables path traversal

**Defect.**
In `_try_download()`:

```python
filename = f"{manufacturer}_{model}_manual.pdf".replace(" ", "_")
dest = cache_dir / filename
```

`manufacturer` is not sanitized here (unlike in `_cache_path()` which runs `re.sub`). If the user passes `--manufacturer '../../../tmp/evil'` via the CLI, then `filename = '../../../tmp/evil_model_manual.pdf'` and `dest` resolves outside the intended cache directory tree.

The path is only reached when `httpx` is installed and the download succeeds (both conditions must hold), so practical exploitability is very low for this local research tool. However, the security invariant of "no path traversal" is violated.

**Fix.** Apply the same sanitization used in `_cache_path()`:
```python
safe_mfr = re.sub(r"[^\w\-]", "_", manufacturer.strip())
safe_model = re.sub(r"[^\w\-]", "_", model.strip())
filename = f"{safe_mfr}_{safe_model}_manual.pdf"
```

---

## Summary Table

| # | Severity | File | Location | Issue |
|---|----------|------|----------|-------|
| 1 | HIGH | `instrument/safety.py` | L508–518 | `check_script_text` dedup silences `OUTPUT_ACTIVE_PARAM_CHANGE` when same SCPI cmd appears in safe then unsafe context |
| 2 | HIGH | `figure/renderers/schematic.py` | L300–302 | `SchematicRenderer` uses empty P1 stub registry; 10-primitive catalog is dead code |
| 3 | MEDIUM | `instrument/safety.py` | L207–214 | Bare `CURR`/`:CURR` prefixes produce false-positive violations for `CURR:COMP`, `CURR:RANG`, etc. |
| 4 | MEDIUM | `cli.py` | L1258–1262, 1290–1295, 1326–1334 | `plt.close(fig)` missing after export in three `figure` CLI commands |
| 5 | MEDIUM | `instrument/scaffold.py` | L70–77 | Digit-starting model names (e.g. `"2400"`) produce `class 2400:` — invalid Python syntax |
| 6 | MEDIUM | `figure/spec.py`, `figure/renderers/dataplot.py` | L111, L292–296 | `AxisSpec.lim` with < 2 elements raises `IndexError` in `_apply_axis_spec`; no validator |
| 7 | LOW | `instrument/manual_search.py` | L337 | Unsanitized `manufacturer` in filename allows path traversal when `httpx` download succeeds |
