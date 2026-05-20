# Review 05 — Authoring, Integrity, and Cross-cutting CLI (P6)

Review date: 2026-05-19  
Reviewer scope: §16 authoring, §8 gateway, §5.10 D1 hypotheses, §5.15/§17 integrity, Appendix A CLI tree.  
Method: code reading, `--help` CLI walk, pytest execution.

---

## Summary

**Verdict: SUBSTANTIALLY MET with 5 concrete gaps.**

| Status     | Count |
|------------|-------|
| MET        | 33    |
| PARTIAL    | 4     |
| MISSING    | 3     |
| DEVIATION  | 1     |

Overall test health: **2092 passed, 2 failed** (both failures are in `tests/integration/test_f6_data_to_figure.py` — a Korean→English message-string mismatch in a P1 figure test, entirely outside P6 scope). All P6-specific unit, integrity, and smoke tests pass (100%).

---

## Findings

### Bundle 1 — Templates and Data Vault

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-01: templates/ with 5+ publisher dirs, `style_profile.yaml`, `figure_spec.yaml` | PARTIAL | `sn-jnl/`, `scifile/`, `revtex4-2/`, `revtex4-2-aip/`, `IEEEtran/`, `elsarticle/` all exist with `preamble.tex` + `style_profile.yaml`. | **`figure_spec.yaml` is missing from every template dir** — T-P6-01 explicitly requires a separate `figure_spec.yaml` alongside `style_profile.yaml`. Currently all figure dimension data lives inside `style_profile.yaml`. Also, **`word/` dir for Wiley Advanced Materials is absent**. | Add `figure_spec.yaml` (figure width, resolution, font rules) as a separate file in each template dir. Create `templates/word/` with a `.dotx` stub. |
| T-P6-02: Wiley Word template (`word/advanced_materials.dotx`) | MISSING | `ls maglab/authoring/templates/` shows no `word/` directory. | The Advanced Materials Word template is entirely absent. | Create `maglab/authoring/templates/word/advanced_materials.dotx` via `python-docx`; add `word` alias to `JOURNAL_ALIASES` in `templates/__init__.py`. |
| T-P6-03: DataVault with `get_locked_value`, `inject_into_draft`, blocking gate | MET | `maglab/authoring/data_vault.py`: `DataVault.get_locked_value` (line 92), `inject_into_draft` (line 106), `validate_draft` (line 158). Raises `AuthoringBlockedError` on missing key. Tests: `tests/unit/test_authoring_data_vault.py` — all pass. | — | — |
| T-P6-04: BibManager with `add_verified`, `get_verified_keys`, DOI verification | MET | `maglab/authoring/bib_manager.py`: `add_verified` (line 88), `add_unverified` hard-blocked (line 156), `export_bib` (line 178). Tests: `tests/unit/test_authoring_bib_manager.py` — all pass. | — | — |
| T-P6-05: `maglab write` CLI with HUMAN_REVIEW_REQUIRED.txt auto-creation | MET | `maglab/commands/p6_authoring.py` `write_command` (line 84); dry-run confirmed working. `HUMAN_REVIEW_REQUIRED.txt` written in both dry-run and loop paths. | — | — |

### Bundle 2 — Citation Pipeline

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-06: `preflight_citations` — DOI-verified pool before drafting | MET | `citation_auditor.py:154`. Works in offline mode (empty pool) and with injected `search_fn`/`doi_verify_fn`. Tests: `test_authoring_section_drafter.py`, `test_citation_audit.py`. | — | — |
| T-P6-07: `audit_existence` — `\cite{KEY}` vs. verified pool, raises on MISSING | MET | `citation_auditor.py:220`. Raises `AuthoringBlockedError` when `raise_on_missing=True`. `tests/integrity/test_citation_audit.py` — all 19 pass. | — | — |
| T-P6-08: `audit_semantics` — 4-class SUPPORTS/PARTIAL/UNSUPPORTED/UNCERTAIN + blocking gate | MET | `citation_auditor.py:284`. `_default_semantic_fn` falls back to UNCERTAIN when no LLM (UNCERTAIN is a blocking label — see DEVIATION below). `tests/integrity/test_citation_audit.py` mock classifiers cover all 4 labels. | — | — |
| T-P6-09: `PreSectionFinalizeHook` chains existence + semantic + data vault | MET | `citation_auditor.py:377`. `hook.run()` fires all three checks in order. Integrated into `loop_c.py` at step 3. Tests: `test_citation_audit.py::TestPreSectionFinalizeHook`. | — | — |
| T-P6-10: End-to-end citation test | MET | `tests/integrity/test_citation_audit.py` covers injected UNSUPPORTED → blocked, valid pool → passes, DataPoint missing → blocked. All deterministic. | — | — |

### Bundle 3 — Section Drafter and Loop C

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-11/12: `draft_section` for all 7 section types, verified-key-only, `{{dp:KEY}}` placeholders | MET | `section_drafter.py:211`. `DRAFTING_ORDER` = Methods→Results→Discussion→Conclusion→Intro→Abstract→Title. System prompt explicitly forbids inventing numbers or cite-keys. Abstract word limit warning logged. Tests: `test_authoring_section_drafter.py`. | — | — |
| T-P6-13: `compile_draft` — tectonic subprocess wrapper | MET | `section_drafter.py:361`. Returns `CompileResult(success, pdf_path, log)`. Handles `FileNotFoundError` and timeout. Tests: `test_authoring_section_drafter.py::test_compile_draft_tectonic_not_found`. | — | — |
| T-P6-14: `readback_pdf` — vision model or heuristic PDF layout check | MET | `section_drafter.py:427`. Heuristic path (no vision_fn) checks file existence and size. Vision path parses for "overflow", "missing figure", etc. Tests: `test_authoring_section_drafter.py`. | — | — |
| T-P6-15: `LoopC` / `run_loop_c` — max-6-iteration cap, human gate, AI disclosure | MET | `loop_c.py`. `max_iterations = min(max_iterations, 6)` (line 169). Human gate per section (lines 292–313). `_AI_DISCLOSURE_FOOTER` written to `main.tex`. `HUMAN_REVIEW_REQUIRED.txt` written by `_write_output_files`. Tests: `test_authoring_loop_c.py`. | — | — |

### Bundle 4 — Communications Suite

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-16: `BaseCommsAgent` with HUMAN REVIEW REQUIRED header, [FILL] enforcement, no auto-send | MET | `comms/base.py`. `HUMAN_REVIEW_HEADER` prepended, `_validate_fill_markers` raises `MissingFillMarkerError` if too few [FILL] markers. Tests: `test_authoring_comms.py`. | — | — |
| T-P6-17: `revision-letter` agent | MET | `comms/revision_letter.py`. `RevisionLetterAgent` subclasses `BaseCommsAgent`. CLI: `maglab comms revision`. Tests: `test_authoring_comms.py`. | — | — |
| T-P6-18: `cover-letter` agent (≤250 words) | MET | `comms/cover_letter.py`. Word limit enforced with warning. CLI: `maglab comms cover-letter`. | — | — |
| T-P6-19: `academic-email` agent (5 types, ≤200 words, [FILL]) | MET | `comms/academic_email.py`. 5 email types validated in CLI (`p6_authoring.py:358`). | — | — |
| T-P6-20: `conference-abstract` agent (char limit, DataPoint injection) | MET | `comms/conference_abstract.py`. Char limit check in CLI (`p6_authoring.py:444–450`). | — | — |
| T-P6-21: `grant-text` agent (NSF/DOE, [FILL], page limit) | MET | `comms/grant_text.py`. CLI: `maglab comms grant`. | — | — |
| T-P6-22: `rebuttal` agent AND `maglab comms rebuttal` CLI subcommand | PARTIAL | `comms/rebuttal.py` and `RebuttalAgent` exist and are exported from `comms/__init__.py`. **However `@comms_app.command("rebuttal")` is NOT wired in `p6_authoring.py`** — confirmed by `maglab comms --help` which shows only 5 subcommands. | `maglab comms rebuttal` is unreachable from the CLI. | Add `@comms_app.command("rebuttal")` handler in `maglab/commands/p6_authoring.py` mirroring the other comms commands (lines 215–277 pattern). |

### Bundle 5 — Presentation Materials

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-23: `present/` package with template dirs (beamer, pptx, marp, beamerposter, svg) | PARTIAL | `present/__init__.py`, `slide_drafter.py`, `poster_drafter.py` exist. `{{figure:SPEC}}` placeholder constant defined (`slide_drafter.py:FIGURE_PLACEHOLDER`). **Template subdirectory structure (`present/templates/`) is absent** — no actual Beamer template files. | No real presentation templates on disk; slide drafter generates inline LaTeX strings without loading an external template. | Create `maglab/authoring/present/templates/beamer/`, `pptx/`, `marp/` dirs with stub templates. |
| T-P6-24/25: `SlidesDrafter.draft_slides` and `PosterDrafter.draft_poster` | MET | Both classes implemented with vault injection, `HUMAN REVIEW REQUIRED` markers. `SlideFormat` enum covers beamer/pptx/marp. CLI wired. Tests: `test_authoring_section_drafter.py` (present). | — | — |
| T-P6-26: `maglab present slides` and `maglab present poster` CLI | MET | Both commands registered via `@present_app.command`. Dry-run confirmed. honesty gate present indirectly via vault. | — | — |

### Bundle 6 — Messaging Gateway

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-27: `session_db.py` — SQLite, user_id SHA-256 hash, no raw PII | MET | `gateway/session_db.py`. `_hash_user_id` (line 74), `get_or_create_session` stores only hash (line 183). Schema in `_init_schema`. Tests: `test_gateway_session_db.py`. | — | — |
| T-P6-28: `BaseAdapter` with `verify_request`, `parse_message`, `send_reply`, allowlist, 0600 check | MET | `gateway/adapters/base.py`. `check_credential_permissions` (line 76) enforces 0600 on Unix. `_user_allowed`/`_channel_allowed` enforce allowlists. Tests: `test_gateway_adapters.py`. | — | — |
| T-P6-29: Slack adapter with HMAC-SHA256 signature verification | MET | `gateway/adapters/slack.py`. `_verify_slack_signature` (line 80) uses `hmac.compare_digest`. Allowlist checked in `verify_request` (line 106). Tests: `test_gateway_adapters.py`. | — | — |
| T-P6-30: Telegram adapter | MET | `gateway/adapters/telegram.py`. Bot-token allowlist check. Tests: `test_gateway_adapters.py`. | — | — |
| T-P6-31: Discord adapter | MET | `gateway/adapters/discord.py`. Allowlist check. Tests: `test_gateway_adapters.py`. | — | — |
| T-P6-32: `GatewayRunner` — asyncio router, notification bus, PID file daemon | MET | `gateway/runner.py`. `write_pid`/`read_pid`/`remove_pid`/`is_running`/`stop_daemon` (lines 342–390). Notification loop (`_notification_loop` line 285). CLI `maglab gateway start/stop/status` all registered. | **PID race condition**: `gateway_start` (p6_authoring.py:605-612) forks the subprocess with `Popen` then calls `write_pid()` which writes the **parent's** PID (`os.getpid()`) — not the child subprocess's PID. `stop_daemon` would then kill the wrong process. | In `gateway_start`, replace `write_pid()` with `_pid_path().write_text(str(proc.pid))`. |
| T-P6-33: `gateway install` — systemd/launchd, 0600 pre-check | PARTIAL | `install_service` in `runner.py` (line 470) writes the correct platform file. The CLI `gateway_install` checks `~/.maglab/gateway.yaml` permissions before calling `install_service`. **However `install_service` itself does not check credential file permissions** — the docstring claims it does ("credential directory is checked for 0600 permissions before writing") but the body does no such check (lines 494–507). | If `install_service` is called directly (not via CLI), the 0600 check is bypassed. | Add `check_credential_permissions(Path.home() / ".maglab" / "gateway.yaml")` at the top of `install_service` in `runner.py`. |
| T-P6-34: Gateway smoke tests | MET | `tests/smoke/test_gateway_smoke.py` and `tests/unit/test_gateway_runner.py`. All pass. Allowlist enforcement tested. | — | — |

### Bundle 7 — D1 Hypothesis Engine

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-35: `generate_candidates` with novelty cite-key validation vs. verified pool | MET | `core/reasoning.py:805`. `verified_cite_pool` filter applied (line 881). Seed templates used when LLM absent. Tests: `test_reasoning_d1.py`. | — | — |
| T-P6-36: `rank_by_elo` — 4-criterion Elo tournament, no ties | MET | `core/reasoning.py:900`. All 4 criteria (novelty/testability/feasibility/impact) iterated. Tie broken by `feasibility_score + impact_score` (line 984). Tests: `test_reasoning_d1.py`. | — | — |
| T-P6-37: `reflection_physics_check` — oracle/formula check, `valid=False` on contradiction | MET | `core/reasoning.py:994`. Keyword pattern list (line 1031): energy conservation, perpetual motion, absolute zero, FTL, negative Gilbert damping. Oracle integration attempted via import (line 1022). Tests: `test_reasoning_d1.py`. | — | — |
| T-P6-38: `maglab hypotheses` CLI — Rich Panel cards, AI label, Elo score | MET | `p6_authoring.py:891`. Rich Panel per hypothesis (line 963). "AI suggestion" label from `rh.ai_label`. Elo score displayed. Disclaimer printed. | — | — |
| D2 non-modification (P6 adds D1 only — D2 must not be touched) | MET | `reasoning.py:1` — single file. D2 classes (`AnomalyExplainer`, `explain_anomaly`) intact at lines 316–503. D1 classes begin at line 507. `explain_anomaly` imported and functional. Tests: `test_reasoning_d2.py` — all pass. | — | — |

### Agent Definitions

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| T-P6-35: `agents/hypothesis-gen.md` sub-agent definition | MISSING | `ls agents/` shows no `hypothesis-gen.md`. | Sub-agent contract file (§5.16 format) absent. | Create `agents/hypothesis-gen.md` with frontmatter + system prompt defining D1 constraints. |
| T-P6-39: `agents/experiment-manager.md` P6 integration | MISSING | `ls agents/` shows no `experiment-manager.md`. | Experiment manager sub-agent definition absent. | Create `agents/experiment-manager.md` with authoring/comms/hypotheses node types documented. |

### Bundle Skills (Appendix C)

| Requirement | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| Appendix C: `revision-letter`, `academic-email`, `cover-letter` SKILL.md bundle skills | MISSING | `ls skills/` shows only `literature-review/`, `literature-search/`, `physics-oracle/`. None of the P6 comms skills exist as SKILL.md directories. | The three SKILL.md skill files required by Appendix C for the comms suite are absent. | Create `skills/revision-letter/SKILL.md`, `skills/cover-letter/SKILL.md`, `skills/academic-email/SKILL.md` with trigger descriptions, inputs, outputs per SKILL.md open standard. |

---

## Critical Gaps (Ranked)

### 1. SECURITY — `install_service` skips 0600 credential permission check (PARTIAL, T-P6-33)

**File:** `maglab/gateway/runner.py:470–507`  
**Risk:** HIGH. The `install_service` function's docstring claims it checks credential permissions, but the implementation does not. A caller that invokes `install_service` directly (e.g., from code, not via `maglab gateway install` CLI) will register a system daemon without enforcing the 0600 requirement. The CLI wrapper does check permissions but provides no defense-in-depth.  
**Fix:** Insert at the top of `install_service`:
```python
from maglab.gateway.adapters.base import check_credential_permissions
cred_file = Path.home() / ".maglab" / "gateway.yaml"
if cred_file.exists():
    check_credential_permissions(cred_file)
```

### 2. SECURITY — PID race condition in `gateway start` background mode (DEVIATION, T-P6-32)

**File:** `maglab/commands/p6_authoring.py:605–612`  
**Risk:** MEDIUM. `write_pid()` writes `os.getpid()` (the parent CLI process PID), not the subprocess `proc.pid`. When `maglab gateway stop` reads the PID file and sends SIGTERM, it kills the parent (which may already have exited) rather than the actual daemon subprocess. `gateway status` would also misreport.  
**Fix:** Replace `write_pid()` call on line 611 with:
```python
_pid_path().write_text(str(proc.pid))
```

### 3. RESEARCH INTEGRITY — Default semantic classifier blocks all drafting without LLM (PARTIAL, T-P6-08)

**File:** `maglab/authoring/citation_auditor.py:269–281`  
**Risk:** MEDIUM. `_default_semantic_fn` marks every citation as UNCERTAIN when no `semantic_classify_fn` is injected. UNCERTAIN is a blocking label (`blocking_findings` includes UNCERTAIN at line 106). This means `audit_semantics` with `raise_on_blocking=True` (the default in `PreSectionFinalizeHook`) will **always block** authoring when run without a real LLM — even for fully verified citations.  
**Mitigation already present:** `loop_c.py` passes `semantic_classify_fn` explicitly. Tests inject mocks. But a user calling `SectionDrafter` without the full Loop C setup will encounter silent blocking.  
**Fix:** Change the default fallback to PARTIAL (non-blocking) when no `semantic_classify_fn` is provided, or emit a warning and skip semantic checking (rather than block) in offline/no-LLM mode. Document the behavior explicitly.

### 4. FUNCTIONALITY — `maglab comms rebuttal` unreachable (MISSING CLI binding, T-P6-22)

**File:** `maglab/commands/p6_authoring.py`  
**Risk:** LOW-MEDIUM. `RebuttalAgent` is fully implemented and exported but the `@comms_app.command("rebuttal")` decorator is absent. Users cannot access the rebuttal agent via CLI. The plan specifies this as a required comms subcommand.  
**Fix:** Add a `comms_rebuttal` function with `@comms_app.command("rebuttal")` between lines 512 and 515 in `p6_authoring.py`, mirroring the pattern of `comms_revision`.

### 5. COMPLETENESS — Missing bundle SKILL.md files for comms suite (MISSING, Appendix C)

**Directory:** `skills/`  
**Risk:** LOW. Appendix C catalogs `revision-letter`, `academic-email`, `cover-letter` as bundle skills with SKILL.md. None exist. These are required for Claude Code skill discovery and portability.  
**Fix:** Create `skills/revision-letter/SKILL.md`, `skills/cover-letter/SKILL.md`, `skills/academic-email/SKILL.md` per SKILL.md open standard format.

---

## CLI Tree Conformance (Appendix A)

All Appendix A commands verified by running `maglab <cmd> --help`:

| Appendix A Command | Exists? | Works? | Notes |
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
| `maglab lit search/authors/keywords/journal` | Yes | Yes | — |
| `maglab lit graph` | Yes | Yes | — |
| `maglab review "<manuscript>"` | Yes | Yes | — |
| `maglab write "<results>" --journal <name>` | Yes | Yes | Dry-run confirmed. |
| `maglab comms revision` | Yes | Yes | — |
| `maglab comms cover-letter` | Yes | Yes | — |
| `maglab comms email` | Yes | Yes | — |
| `maglab comms abstract` | Yes | Yes | — |
| `maglab comms grant` | Yes | Yes | — |
| **`maglab comms rebuttal`** | **NO** | **NO** | Agent exists, CLI binding missing. |
| `maglab ralph start/status/cancel` | Yes | Yes | — |
| `maglab gateway setup` | Yes | Yes | — |
| `maglab gateway start` | Yes | Yes | PID bug (see Critical Gap 2). |
| `maglab gateway stop` | Yes | Yes | — |
| `maglab gateway status` | Yes | Yes | — |
| `maglab gateway install` | Yes | Yes | 0600 check only in CLI, not in `install_service`. |
| `maglab skill list/install/create` | Yes | Yes | — |
| `maglab ask "<natural language>"` | Yes | Yes | — |
| `maglab run "<goal>"` | Yes | Yes | — |
| `maglab lab note/plan` | Yes | Yes | — |
| `maglab present slides` | Yes | Yes | — |
| `maglab present poster` | Yes | Yes | — |
| `maglab hypotheses "<topic>"` | Yes | Yes | — |
| `maglab explain "<data/result>"` | Yes | Yes | — |
| `maglab device fom <spec>` | Yes | Yes | — |
| `maglab cost` | Yes | Yes | — |
| `maglab mcp add/list/enable/disable/serve` | Yes | Yes | — |
| `maglab agents list/show` | Yes | Yes | — |
| `maglab report/prov/config/task` | Yes | Yes | — |

**Summary:** 38/39 Appendix A commands reachable and functional. One missing: `maglab comms rebuttal`.

---

## User-Perspective Check

What the plan promises that a user **cannot yet do**:

1. **`maglab comms rebuttal`** — The rebuttal agent exists and works programmatically, but the CLI subcommand is not registered. A user invoking `maglab comms rebuttal` gets "No such command". **Impact: HIGH** — this is a spec'd P6 deliverable.

2. **`maglab write --journal advanced-materials`** — The Wiley Advanced Materials Word template does not exist. Loading this alias would fall through to an error in `templates/__init__.py`. **Impact: MEDIUM** — Advanced Materials is a top venue for spintronics.

3. **Skills discovery for comms agents** — Bundle skills `revision-letter`, `cover-letter`, `academic-email` are not in the `skills/` directory. A user running `maglab skill list` will not find them. **Impact: LOW** — skills are listed in source but not as discoverable SKILL.md packages.

4. **Offline/no-LLM authoring** — Without a real LLM injected, `audit_semantics` blocks every section via the UNCERTAIN fallback. A user attempting to draft without LLM credentials will see `AuthoringBlockedError` from semantics, not a meaningful "configure LLM first" message. **Impact: LOW-MEDIUM** — confusing UX rather than a research integrity failure.

5. **`hypothesis-gen` and `experiment-manager` sub-agent definitions** — These agent spec files don't exist. A user who tries `maglab agents show hypothesis-gen` or `maglab agents show experiment-manager` will get "not found". **Impact: LOW** — runtime behavior is unaffected; only the agent catalog is incomplete.

---

## Research Integrity Invariants — Hard Verification

| Invariant | Status |
|---|---|
| LLM cannot invent numbers — DataVault `inject_into_draft` blocks unknown `{{dp:KEY}}` | **ENFORCED** — `AuthoringBlockedError` raised; `tests/integrity/test_citation_audit.py` confirms. |
| LLM cites only verified keys — system prompt forbids inventing keys; `audit_existence` blocks unknown keys | **ENFORCED** — `citation_auditor.py:220`, `tests/integrity/test_citation_audit.py`. |
| Citation semantic verification (4-class) blocks UNSUPPORTED/UNCERTAIN | **ENFORCED** — `citation_auditor.py:340`; all integrity tests pass. Note: fallback marks everything UNCERTAIN (see Critical Gap 3). |
| Comms outputs carry HUMAN REVIEW REQUIRED and are never auto-sent | **ENFORCED** — `comms/base.py:HUMAN_REVIEW_HEADER`; no `send_reply` in any comms agent; all outputs written to files. |
| Loop C max 6 iterations (hard cap) | **ENFORCED** — `loop_c.py:169`: `max_iterations = min(max_iterations, 6)`. |
| Loop C human sign-off per section | **ENFORCED** — `loop_c.py:292`; loop aborts with `EXTERNAL` stop reason on rejection (line 313). |
| AI usage disclosure appended automatically | **ENFORCED** — `_AI_DISCLOSURE_FOOTER` in `loop_c.py:58–66`; `_AI_DISCLOSURE` in `section_drafter.py:166`. |
| Gateway allowlists enforce deny-by-default | **ENFORCED** — `base.py:_user_allowed/_channel_allowed`; all 3 adapters check in `verify_request`. `tests/smoke/test_gateway_smoke.py` verifies blocked paths. |
| PII not stored raw — user_id SHA-256 hashed | **ENFORCED** — `session_db.py:_hash_user_id`; message content also hashed (`log_message` line 270). |
| D2 reasoning unchanged by P6 D1 addition | **ENFORCED** — D2 code lines 1–503 unmodified; `test_reasoning_d2.py` — all pass. |
| Honesty gate `report/honesty_gate.py` active | **ENFORCED** — `tests/integrity/test_honesty_gate.py` — 55 pass. |
