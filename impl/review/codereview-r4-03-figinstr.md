# Code Review Round 4 — Figure Engine & Instrument Layer

> Reviewer: Claude Sonnet 4.6 (adversarial code-quality role)
> Date: 2026-05-19
> Scope: `maglab/figure/`, `maglab/instrument/`
> Method: Read-only source audit + targeted `uv run python` probes

---

## Verdict

**ISSUES FOUND** — 4 genuine defects across both domains. All R3 patches are confirmed in place and functioning correctly.

---

## R3 Patch Verification

All 7 R3 findings have been patched and verified:
- R3-1 (dedup safety false-negative): fixed — `check_script_text` now preserves all occurrences in program order.
- R3-2 (empty stub registry): fixed — `SchematicRenderer` now calls `make_default_registry()`, all 10 primitives are reachable.
- R3-3 (bare `CURR`/`:CURR` false positives): fixed — bare prefixes removed from `_CURR_PREFIXES`.
- R3-5 (digit-starting class names): fixed — `"Instr"` prefix prepended.
- R3-6 (`AxisSpec.lim` length): fixed — `field_validator` added.
- R3-7 (path traversal in `_try_download`): fixed — `re.sub` sanitization added.
- R3-4 (CLI figure leak): not re-verified here (out-of-scope for this domain file set).

---

## Findings

### Finding 1 — MEDIUM | `maglab/figure/primitives/catalog/hall-bar/primitive.py:143–146` | Duplicate `y1` attribute in SVG `<line>` element renders current arrow as degenerate zero-height line

**Defect.**
The `HallBarPrimitive._render_svg()` method builds the current-direction arrow with:

```python
# hall-bar/primitive.py:143–146
parts.append(
    f'<line x1="{-scl:.1f}" y1="{arrow_y:.1f}" '
    f'x2="{-4:.1f}" y1="{arrow_y:.1f}" '   # ← y1 repeated; y2 is absent
    f'stroke="#C00" stroke-width="2" '
    f'marker-end="url(#arr)"/>'
)
```

Line 144 uses `y1=` for the second coordinate instead of `y2=`. The SVG specification prohibits duplicate attributes; browser/renderer behaviour on encountering them is to use the last declared value. The `x2` endpoint therefore has no `y2` defined: the line degenerates to a zero-height arrowhead invisible at any reasonable stroke width. The current arrow (`I` label still appears but the line itself is invisible).

Verified by generating the SVG and inspecting the tag:
```
<line x1="-16.0" y1="60.0" x2="-4.0" y1="60.0" stroke="#C00" .../>
   y1 count: 2   y2 count: 0   ← DEFECT
```

**Fix.** Replace `y1=` on line 144 with `y2=`:
```python
f'x2="{-4:.1f}" y2="{arrow_y:.1f}" '
```

---

### Finding 2 — MEDIUM | `maglab/figure/primitives/catalog/measurement-geometry/primitive.py:118–120` | Same duplicate `y1`/missing `y2` bug in current-arrow `<line>` element

**Defect.**
`MeasurementGeometryPrimitive._render_svg()` contains the identical bug:

```python
# measurement-geometry/primitive.py:118–120
parts.append(
    f'<line x1="{cx - r:.1f}" y1="{cy:.1f}" '
    f'x2="{x2 - 4:.1f}" y1="{cy:.1f}" '   # ← y1 repeated; y2 is absent
    f'stroke="#C00" stroke-width="2" marker-end="url(#arrowR)"/>'
)
```

Same consequence: the horizontal current-direction arrow (the `I` indicator) is rendered as a degenerate zero-height line. This is the primary visual element showing the applied current direction in a Hall measurement geometry schematic.

**Fix.** Replace the second `y1=` on line 119 with `y2=`:
```python
f'x2="{x2 - 4:.1f}" y2="{cy:.1f}" '
```

---

### Finding 3 — LOW | `maglab/instrument/safety.py:488` | Docstring claims `.query(…)` calls are extracted; only `.write(…)` calls are actually checked

**Defect.**
The docstring for `SafetyChecker.check_script_text()` states:

```
Extracts string literals from .write(…) and .query(…) calls.
```

The implementation uses a single regex that matches only `.write(…)`:

```python
write_re = re.compile(r'\.write\s*\(\s*["\']([^"\']+)["\']\s*\)')
```

There is no corresponding regex for `.query(…)`. SCPI commands sent via `instr.query('OUTP ON')` (unusual but valid, since some instruments accept write-style commands on the query wire) are silently ignored by the static validator. This is a docstring-vs-behaviour contradiction. The safety check itself is otherwise sound — the limitation is not documented anywhere in the code.

**Fix.** Either add a `query_re` covering `.query(…)` (preferred, to honour the docstring) or update the docstring to read "Extracts string literals from `.write(…)` calls only (`.query(…)` arguments are not checked)."

---

### Finding 4 — LOW | `maglab/instrument/safety.py:527–530` | Incorrect line numbers reported for safety violations arising from sub-commands within compound semicolon-separated SCPI strings in script text

**Defect.**
`check_script_text()` handles compound SCPI strings such as `instr.write('OUTP ON; SOUR:VOLT 999')` correctly at the *safety-check level* (the violation is caught). However, the **violation line numbers** reported to the caller are inaccurate.

Root cause:
1. `lineno_map` maps the full compound string `'OUTP ON; SOUR:VOLT 999'` → actual script line (e.g. 5).
2. `check_scpi_sequence()` splits the compound string on `;` and produces sub-commands `'OUTP ON'` and `'SOUR:VOLT 999'`. Violations are recorded with `v.command = sub_cmd` and `v.line_number = position_in_cmd_list` (e.g. 3 if there are 2 earlier `.write()` calls).
3. The line-number correction loop at lines 527–530 checks `if v.command in lineno_map` — but `lineno_map` only holds full compound strings, not individual sub-commands. The lookup fails for every sub-command, so `v.line_number` is never corrected from the cmd-list position (3) to the actual script line (5).

Verified:
```python
script = """instr.write('*RST')
instr.write('*CLS')
instr.write('SENS:VOLT:RANG 1')
x = instr.query('*IDN?')
instr.write('OUTP ON; SOUR:VOLT 999')"""  # actual line 5

result = checker.check_script_text(script)
# output_active_param_change: reported_line=4  (should be 5)
# voltage_over_limit:          reported_line=4  (should be 5)
```

The safety check itself is correct — the violation IS reported. Only the diagnostic line number is wrong, making it harder for the user to locate the offending line in a long script.

**Fix.** After splitting compound strings, track the sub-command's origin line using the parent compound string's lineno from `ordered`:

```python
# Build (lineno, cmd, parent_cmd) triples; after check_scpi_sequence,
# use parent_cmd lookup in lineno_map when sub_cmd is not found directly.
```

Alternatively, also insert individual sub-commands into `lineno_map` at construction time:
```python
for i, cmd in ordered:
    for sub in [s.strip() for s in cmd.split(";") if s.strip()]:
        lineno_map.setdefault(sub, i)
```

---

## Summary Table

| # | Severity | File | Location | Issue |
|---|----------|------|----------|-------|
| 1 | MEDIUM | `figure/primitives/catalog/hall-bar/primitive.py` | L143–146 | SVG `<line>` has `y1` twice, `y2` missing — current arrow is invisible |
| 2 | MEDIUM | `figure/primitives/catalog/measurement-geometry/primitive.py` | L118–120 | Same duplicate `y1`/missing `y2` bug — current arrow is invisible |
| 3 | LOW | `instrument/safety.py` | L488 | Docstring claims `.query(…)` calls extracted; only `.write(…)` is checked |
| 4 | LOW | `instrument/safety.py` | L527–530 | Wrong line numbers for sub-command violations from compound SCPI strings |
