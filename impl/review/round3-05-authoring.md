# Round-3 Review — Authoring, Integrity, and Cross-cutting CLI (P6)

Review date: 2026-05-19
Reviewer scope: Round-1 gap closure verification; plan/09–11 re-scan; Appendix A CLI walk; research-integrity invariant re-check.
Method: source code reading, `--help` CLI walk, pytest execution.

---

## Verdict

**GAPS REMAIN** — 4 of the 8 Round-1 findings remain open; 1 new documentation regression was introduced by a Round-2 patch. All 5 open items are low-to-medium severity with no security regressions. All 364 targeted tests pass.

---

## Closure Check

| # | Round-1 Finding | ID | Closed? | Evidence |
|---|---|---|---|---|
| 1 | `install_service` does not check 0600 credential permissions (SECURITY, T-P6-33) | CRITICAL-1 | **YES** | `runner.py:496–503` now imports `check_credential_permissions` and calls it at the top of `install_service` before writing any service file. Guard applies even when called programmatically. |
| 2 | `gateway_start` writes `os.getpid()` (parent) not `proc.pid` to PID file (SECURITY, T-P6-32) | CRITICAL-2 | **YES** | `p6_authoring.py:677–679` now writes `str(proc.pid)` directly to `_pid_path()`. Comment clarifies intent. `gateway_start` no longer calls `write_pid()`. |
| 3 | `_default_semantic_fn` returns UNCERTAIN (blocking), preventing all authoring without LLM (T-P6-08) | CRITICAL-3 | **YES** | `citation_auditor.py:272–301` now returns `SemanticLabel.PARTIAL` (non-blocking) with a `logging.warning`. Authoring proceeds with existence-verified citations when no `semantic_classify_fn` is injected. |
| 4 | `maglab comms rebuttal` CLI subcommand missing (T-P6-22) | CRITICAL-4 | **YES** | `p6_authoring.py:515–578` adds `@comms_app.command("rebuttal")` implementing `comms_rebuttal`. `maglab comms --help` lists it; `maglab comms rebuttal --help` works correctly. |
| 5 | `agents/hypothesis-gen.md` absent (T-P6-35 agent contract) | MISSING-1 | **YES** | `agents/hypothesis-gen.md` exists with valid §5.16 frontmatter (name, tools, model, max_turns, context) and all 6 contract sections (objective, input, output schema, tool budget, source guide, boundaries). `maglab agents list` shows it. |
| 6 | `agents/experiment-manager.md` absent (T-P6-39 agent contract) | MISSING-2 | **YES** | `agents/experiment-manager.md` exists with valid §5.16 frontmatter and all 6 contract sections. `maglab agents list` shows it. |
| 7 | `figure_spec.yaml` missing from every template dir; `word/` template dir absent (T-P6-01/02) | PARTIAL-1 | **NO** | `find maglab/authoring/templates/ -name figure_spec.yaml` returns empty. Each template dir still has only `preamble.tex` + `style_profile.yaml`. No `templates/word/` directory. `advanced-materials` alias absent from `JOURNAL_ALIASES`. |
| 8 | `present/templates/` subdirectory absent (T-P6-23) | PARTIAL-2 | **NO** | `maglab/authoring/present/` contains only `slide_drafter.py` and `poster_drafter.py`. No `templates/` subdirectory with beamer/pptx/marp stubs. |
| 9 | `skills/revision-letter/`, `skills/cover-letter/`, `skills/academic-email/` SKILL.md files absent (Appendix C) | MISSING-3 | **NO** | `maglab skill list` shows only 3 skills: `literature-review`, `literature-search`, `physics-oracle`. No comms-suite SKILL.md packages exist. |

**New finding introduced by Round-2 patch:**

| # | Finding | Severity | File | Details |
|---|---|---|---|---|
| NEW-1 | `audit_semantics` docstring contradicts implementation after PARTIAL patch | LOW | `citation_auditor.py:327,331` | Line 327 says "Missing keys are classified as UNCERTAIN"; line 331 says "fallback marks everything UNCERTAIN". Both are now incorrect — the fallback returns PARTIAL and missing-pool keys are passed to the classifier as empty strings. |

---

## CLI Tree Conformance (Appendix A)

All Appendix A commands verified by running `--help`:

| Command | Exists? | Works? | Notes |
|---|---|---|---|
| `maglab` (interactive REPL) | Yes | Yes | — |
| `maglab -p "<query>"` | Yes | Yes | — |
| `maglab auth set/list/test` | Yes | Yes | — |
| `maglab theme list/set` | Yes | Yes | — |
| `maglab physics compute/units/oracle` | Yes | Yes | — |
| `maglab mat list/show/search/build` | Yes | Yes | — |
| `maglab sim dft/atomistic/micro/pipeline/job/plot` | Yes | Yes | — |
| `maglab fit --effect <name> <data>` | Yes | Yes | — |
| `maglab analyze load/model/consistency/symmetry` | Yes | Yes | — |
| `maglab figure spec/render/compose/export/primitives` | Yes | Yes | — |
| `maglab instr scaffold/scpi/script/check/ingest/implement` | Yes | Yes | — |
| `maglab lit search/authors/keywords/journal/graph` | Yes | Yes | — |
| `maglab review "<manuscript>"` | Yes | Yes | — |
| `maglab write "<results>" --journal <name>` | Yes | Yes | — |
| `maglab comms revision` | Yes | Yes | — |
| `maglab comms cover-letter` | Yes | Yes | — |
| `maglab comms email` | Yes | Yes | — |
| `maglab comms abstract` | Yes | Yes | — |
| `maglab comms grant` | Yes | Yes | — |
| **`maglab comms rebuttal`** | **Yes** | **Yes** | Closed by Round-2 patch. |
| `maglab ralph start/status/cancel` | Yes | Yes | — |
| `maglab gateway setup/start/stop/status/install` | Yes | Yes | — |
| `maglab skill list` | Yes | Yes | `install` and `create` subcommands absent from `maglab skill --help`; only `list` shown. Appendix A lists all three. |
| `maglab ask "<natural language>"` | Yes | Yes | — |
| `maglab run "<goal>"` | Yes | Yes | — |
| `maglab lab note/plan` | Yes | Yes | — |
| `maglab present slides/poster` | Yes | Yes | — |
| `maglab hypotheses "<topic>"` | Yes | Yes | — |
| `maglab explain "<data/result>"` | Yes | Yes | — |
| `maglab device fom <spec>` | Yes | Yes | — |
| `maglab cost` | Yes | Yes | — |
| `maglab mcp add/list/enable/disable/serve` | Yes | Yes | — |
| `maglab agents list/show` | Yes | Yes | `hypothesis-gen` and `experiment-manager` now discoverable. |
| `maglab report/prov/config/task` | Yes | Yes | — |

**Summary:** 38/39 Appendix A P6 commands reachable (up from 37/39 in Round-1). One residual gap: `maglab skill install` and `maglab skill create` are listed in Appendix A but absent from `maglab skill --help` — this pre-existed Round-1 and is outside P6 scope (P0/P4 deliverable).

---

## Research Integrity Invariants

| Invariant | Status | Evidence |
|---|---|---|
| DataVault blocks unverified number injection (`{{dp:KEY}}`) | ENFORCED | `data_vault.py:inject_into_draft`; `AuthoringBlockedError` on unknown key; `tests/integrity/test_citation_audit.py` confirms. |
| LLM cites only verified keys; `audit_existence` blocks unknown keys | ENFORCED | `citation_auditor.py:220`; 19 integrity tests pass. |
| 4-class semantic verification (SUPPORTS/PARTIAL/UNSUPPORTED/UNCERTAIN) | ENFORCED | `citation_auditor.py:284`; blocking labels enforced; fallback now non-blocking PARTIAL (was UNCERTAIN — this is the correct fix). |
| Comms outputs carry HUMAN REVIEW REQUIRED header; no auto-send | ENFORCED | `comms/base.py:22` (HUMAN_REVIEW_HEADER); no `send_reply` in any comms agent; all outputs written to files. `rebuttal` agent conforms. |
| Loop C max 6 iterations (hard cap) | ENFORCED | `loop_c.py:169`: `max_iterations = min(max_iterations, 6)`. |
| Loop C human sign-off per section | ENFORCED | `loop_c.py:293`; rejects with EXTERNAL stop reason on rejection. |
| AI usage disclosure auto-appended | ENFORCED | `_AI_DISCLOSURE_FOOTER` in `loop_c.py:58–66`. |
| Gateway allowlists enforce deny-by-default | ENFORCED | `base.py:_user_allowed/_channel_allowed`; all 3 adapters check in `verify_request`. |
| PII not stored raw — SHA-256 hashed | ENFORCED | `session_db.py:74–79`; content hash at line 270. |
| D2 reasoning unchanged by P6 D1 additions | ENFORCED | `reasoning.py:316–503` (D2 unchanged); `test_reasoning_d2.py` all pass. |
| Honesty gate active | ENFORCED | `tests/integrity/test_honesty_gate.py` all pass. |
| `install_service` checks 0600 before writing daemon file | ENFORCED (NEWLY) | `runner.py:496–503`; defense-in-depth now present at function level, not just CLI. |
| PID file contains daemon subprocess PID | ENFORCED (NEWLY) | `p6_authoring.py:679`: `_pid_path().write_text(str(proc.pid))`. |

---

## Test Results

```
pytest tests/unit/test_authoring_{data_vault,bib_manager,comms,section_drafter,loop_c}.py
      tests/unit/test_gateway_{session_db,adapters,runner}.py
      tests/unit/test_cli_p6.py
      tests/unit/test_reasoning_d2.py
      tests/integrity/
      tests/smoke/test_gateway_smoke.py
      --timeout=120

364 passed in 0.72s
```

All P6-scoped tests pass. No regressions introduced by Round-2 patches.

---

## Remaining or New Gaps

### GAP-1 (PARTIAL, T-P6-01/02) — `figure_spec.yaml` and `word/` template missing

**Files:** `maglab/authoring/templates/` (all subdirs), `maglab/authoring/templates/__init__.py`
**Severity:** MEDIUM. `maglab write --journal advanced-materials` raises `ValueError` ("Unknown journal"). No `figure_spec.yaml` separate from `style_profile.yaml` as required by T-P6-01.
**Fix:**
1. Add `figure_spec.yaml` (figure width mm, resolution dpi, font size pt rules) to each of `sn-jnl/`, `scifile/`, `revtex4-2/`, `revtex4-2-aip/`, `IEEEtran/`, `elsarticle/`.
2. Create `maglab/authoring/templates/word/` with `advanced_materials.dotx` (python-docx stub) and `style_profile.yaml`.
3. Add `"advanced-materials": "word"`, `"word": "word"` to `JOURNAL_ALIASES` in `templates/__init__.py`.

### GAP-2 (PARTIAL, T-P6-23) — `present/templates/` subdirectory absent

**File:** `maglab/authoring/present/` (no `templates/` subdirectory)
**Severity:** LOW. `SlidesDrafter` and `PosterDrafter` generate inline LaTeX without loading external template files. Functional but not conformant with T-P6-23 ("template dirs: beamer, pptx, marp, beamerposter, svg").
**Fix:** Create `maglab/authoring/present/templates/beamer/`, `pptx/`, `marp/`, `beamerposter/`, `svg/` directories each with a stub template file (e.g., `template.tex` for beamer, `template.md` for marp, `template.pptx` stub for pptx).

### GAP-3 (MISSING, Appendix C) — `revision-letter`, `cover-letter`, `academic-email` SKILL.md files absent

**Directory:** `skills/`
**Severity:** LOW. Appendix C catalogs these three as bundle skills with SKILL.md. `maglab skill list` does not show them.
**Fix:** Create `skills/revision-letter/SKILL.md`, `skills/cover-letter/SKILL.md`, `skills/academic-email/SKILL.md` following the SKILL.md open standard (trigger description, inputs, outputs, references — see `skills/literature-review/SKILL.md` for format).

### NEW-1 (DOCUMENTATION REGRESSION) — `audit_semantics` docstring contradicts post-patch behavior

**File:** `maglab/authoring/citation_auditor.py:327,331`
**Severity:** LOW. The Round-2 patch changed `_default_semantic_fn` to return PARTIAL instead of UNCERTAIN, but two lines in the `audit_semantics` docstring still describe the old UNCERTAIN behavior:
- Line 327: "Missing keys are classified as UNCERTAIN." (incorrect — they are passed as empty-string to the classifier; the default classifier now returns PARTIAL)
- Line 331: "If `None`, the fallback marks everything UNCERTAIN." (incorrect — the fallback now returns PARTIAL)
**Fix:** Update both lines in the docstring:
- Line 327: "Missing keys are passed to the classifier with an empty paper_text string."
- Line 331: "If `None`, the built-in fallback returns PARTIAL (non-blocking) with a warning — semantic verification is effectively skipped."
