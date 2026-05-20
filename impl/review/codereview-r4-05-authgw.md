# Code Review Round 4 — auth/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-19
**Reviewer:** Claude Sonnet 4.6 (automated, read-only)

---

## Verdict

**ISSUES FOUND**

---

## Findings

### F1 — MEDIUM | `maglab/cli.py:390–391` | `theme set` destroys existing config when `tomli_w` is absent

**Defect:**
The `theme_set` command reads the existing TOML config file into `raw` (a full dict), updates `raw['ui']['theme']`, then attempts to write using `tomli_w`. When `tomli_w` is not installed (it is **not** in the current environment), the `except ImportError` fallback writes only a single-key stub:

```python
lines = [f'[ui]\ntheme = "{name}"\n']
cfg_path.write_text("\n".join(lines), encoding="utf-8")
```

This overwrites the **entire** config file with just `[ui]\ntheme = "…"`, silently discarding every other section (`[llm]`, `[provider]`, API credentials references, etc.). The updated `raw` dict — which contains all prior settings — is never used in the fallback path. This is data loss.

**Confirmed live:** `tomli_w` is not installed in this project's venv, so the fallback fires for every `theme set` call.

**Fix:** In the fallback, write `raw` manually instead of ignoring it:
```python
# Minimal hand-serialiser for the subset of TOML used by maglab config
lines_out: list[str] = []
for section, vals in raw.items():
    if isinstance(vals, dict):
        lines_out.append(f"[{section}]")
        for k, v in vals.items():
            lines_out.append(f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}")
        lines_out.append("")
cfg_path.write_text("\n".join(lines_out), encoding="utf-8")
```
Or add `tomli_w` as a mandatory (not optional) dependency.

---

### F2 — MEDIUM | `maglab/mcp_server.py:534–542, 594–610` | Matplotlib figure resource leak in `figure_render` and `figure_export` MCP tools

**Defect:**
Both MCP tools (`figure_render`, `figure_export`) call `FigureComposer().compose()` to create a `matplotlib.figure.Figure` and call `plt.close(fig)` **only on the success path**:

```python
try:
    fig = FigureComposer().compose(spec, ledger)
    saved = FigureExporter().export(fig, output_path, fmt=fmt)
    import matplotlib.pyplot as plt
    plt.close(fig)                          # ← only reached if export succeeds
    return {"ok": True, ...}
except Exception as exc:
    return {"ok": False, ..., "error": str(exc)}   # fig is never closed
```

If `FigureExporter().export()` raises (e.g., permission error, invalid format, disk full), `fig` is constructed but never closed. In a long-running MCP server process receiving repeated malformed requests, this leaks matplotlib figures and accumulates memory.

Contrast with the CLI counterparts (`figure_render_cmd`, `figure_compose_cmd`, etc.) which correctly use `try/finally` + `contextlib.suppress`:
```python
finally:
    with contextlib.suppress(Exception):
        plt.close(fig)
```

**Fix:** Wrap both MCP tool bodies in `try/finally`:
```python
fig = FigureComposer().compose(spec, ledger)
try:
    saved = FigureExporter().export(fig, output_path, fmt=fmt)
    return {"ok": True, "path": str(saved), "error": None}
except Exception as exc:
    return {"ok": False, "path": "", "error": str(exc)}
finally:
    import contextlib, matplotlib.pyplot as plt
    with contextlib.suppress(Exception):
        plt.close(fig)
```

---

### F3 — LOW | `maglab/authoring/section_drafter.py:273–295` | `DraftResult.remaining_placeholders` is dead — never populated in a returned object

**Defect:**
The `DraftResult.remaining_placeholders` field's docstring states:
> *"populated only in the `except AuthoringBlockedError` branch of `SectionDrafter.draft_section` before the exception is re-raised, so callers that catch `AuthoringBlockedError` can inspect it for diagnostics."*

This claim is false. In the exception branch:
```python
except AuthoringBlockedError:
    remaining = self._vault.validate_draft(raw_tex_with_disclosure)   # set here
    final_tex = raw_tex_with_disclosure
    raise    # ← re-raises immediately
```
The `DraftResult(…, remaining_placeholders=remaining, …)` return statement (line 291–296) is **never reached** when `raise` fires. No `DraftResult` object is ever constructed with a non-empty `remaining_placeholders`. The field is set in the local `remaining` variable but that variable is discarded when the exception propagates. Callers that catch `AuthoringBlockedError` cannot access `draft_result.remaining_placeholders` because `draft_result` is never returned.

Confirmed: `remaining_placeholders` is not referenced anywhere in `loop_c.py` or any other caller.

**Fix:** Either (a) eliminate the misleading docstring claim and remove the dead `remaining` assignment in the except block, or (b) attach diagnostic info to the exception itself so callers can actually inspect it:
```python
except AuthoringBlockedError as exc:
    exc.missing_keys = self._vault.validate_draft(raw_tex_with_disclosure)
    raise
```

---

### F4 — LOW | `maglab/authoring/citation_auditor.py:229–231` | `audit_existence` docstring inaccurate — report is returned on all non-exception paths

**Defect:**
The docstring for `audit_existence` says:
> *"Returns: `ExistenceReport` — only returned when `raise_on_missing=False`."*

The actual implementation returns the report in **two** cases:
1. All keys are present (regardless of `raise_on_missing`).
2. Keys are missing and `raise_on_missing=False`.

Callers passing `raise_on_missing=True` and having all keys present will receive the report — contradicting the docstring. While this does not cause incorrect behaviour (the report is valid in either case), the docstring misleads callers into thinking the return value should be ignored when `raise_on_missing=True`.

**Fix:** Update the Returns section:
```
Returns
-------
ExistenceReport
    Always returned when no exception is raised. Callers with
    ``raise_on_missing=True`` should still capture the return value
    to inspect ``missing_keys`` in a ``try/except`` block.
```

---

### F5 — LOW | `maglab/authoring/section_drafter.py:282–289` | Abstract word-count check measures boilerplate-inflated text

**Defect:**
The abstract word-limit check measures `len(final_tex.split())` where `final_tex` already contains:
- `HUMAN_REVIEW_MARKER` ("% HUMAN REVIEW REQUIRED\n" — 4 words)
- `_AI_DISCLOSURE` (multi-line LaTeX comment block — ~35 words)

For a 250-word abstract, the inflated count registers ~290 words, triggering a spurious word-limit warning that does not reflect the actual abstract content. The check fires too eagerly.

**Fix:** Strip LaTeX comments before counting, or count only the pre-disclosure text:
```python
word_count = len(raw_tex.split())   # use raw_tex before disclosure is appended
```

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | MEDIUM | `cli.py:390–391` | `theme set` silently destroys entire config file when `tomli_w` absent |
| F2 | MEDIUM | `mcp_server.py:534–542, 594–610` | Matplotlib figure resource leak in `figure_render` and `figure_export` MCP tools |
| F3 | LOW | `section_drafter.py:273–295` | `DraftResult.remaining_placeholders` dead — never set in a returned object |
| F4 | LOW | `citation_auditor.py:229–231` | `audit_existence` docstring says return "only when raise_on_missing=False", but return happens on all success paths |
| F5 | LOW | `section_drafter.py:282–289` | Abstract word count inflated by boilerplate markers — spurious over-limit warnings |

## Integrity invariants — no bypass found

All research-integrity blocking gates (`AuthoringBlockedError`, `HUMAN REVIEW REQUIRED` markers, `DataVault` injection guard, citation existence + semantic gates, `PreSectionFinalizeHook`) are correctly wired and non-bypassable. No auto-send paths were found. Gateway allowlist enforcement and Slack HMAC signature verification are sound (missing secret logs a warning and accepts requests, but the allowlist still applies — this is explicitly documented behavior).
