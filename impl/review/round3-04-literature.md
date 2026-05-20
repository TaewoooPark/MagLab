# Round-3 Review — P5: Literature Intelligence, Persona Review, ELN

Reviewer: Claude Code (automated conformance review)
Date: 2026-05-19
Plan refs: `plan/07-literature.md` (§14), `plan/08-review.md` (§15)
Prior round: `impl/review/04-literature-review.md` (Round-1 findings)
Test run: 263 passed, 0 failed (all P5-domain tests)
CLI smoke: `maglab mat build "Ta(5)/CoFeB(1)"` ✓  |  `maglab lit --help` ✓

---

## Verdict

**GAPS REMAIN**

Round-2 patches closed 4 of the 8 Round-1 critical items. Four items remain open (two medium, two low). No regressions introduced.

---

## Closure Check

| Round-1 Finding | ID | Closed? | Evidence |
|---|---|---|---|
| OpenAlex abstract always empty (`connectors.py:334` bug) | A-dev | **CLOSED** | `connectors.py:197-222` — `_reconstruct_abstract()` added; line 367 calls it correctly |
| `maglab mat build` CLI entrypoint missing | I-miss | **CLOSED** | `cli.py:288-330` — `@mat_app.command("build")` wired; smoke test passes, returns CoFeB Ms/alpha from nemad_csv |
| Bundled CSVs not committed (SJR, Eigenfactor, NEMAD) | F/I-gap | **CLOSED** | All three present: `maglab/physics/data/sjr.csv` (30 lines), `eigenfactor.csv` (30 lines), `nemad.csv` (27 lines) with correct headers; journals.py and material_builder.py can now read them |
| `maglab review` does not surface MetaReviewer | M-partial | **CLOSED** | `p5_literature.py:597-629` — `MetaReviewer().synthesize(result)` called; consensus/dissent items rendered with spread ≥ 3 pts threshold |
| EvidenceMatrix not invoked from `lit search` | C-partial | **CLOSED** | `p5_literature.py:126-234` — `_build_evidence_matrix()` called by `lit_search`; OpenAlex search → `EvidenceEntry` accumulation → JSON persisted; P6 TODO documented in docstring |
| `harness.manifest.json` not created | C-partial | **PARTIAL — SEE BELOW** | `harness.manifest.json` exists at repo root; all 5 agent definitions present; but the 4 plan-required workflow names (`survey`, `paper-review`, `citation-map`, `local-gap`) are absent — actual names are `literature-review`, `physics-validation`, `result-analysis`, `hypothesis-generation` |
| MCP connectors `mcp.json` not created | C-miss | **OPEN** | No `mcp.json` file exists anywhere in the repo; `.maglab/` directory holds only `ralph_loop_c.md`; `maglab mcp list` will print "No MCP servers registered" |
| SPECTER2 not used in KeyBERT | D-miss | **OPEN** | `keywords.py:220`: `kw_model = KeyBERT()` — still default transformer, not `allenai/specter2_base`; comment at line 6 says "LLM re-ranking performed externally" |
| LLM domain re-ranking not integrated | D-partial | **OPEN** | No `rerank_with_domain_llm` step in `extract_keywords_from_folder()`; `keywords.py:6` explicitly defers this to caller; no injectable hook/stub added |
| APL Materials rubric missing | M-partial | **OPEN** | `rubrics.py:4` docstring names APL Materials; `_RUBRIC_REGISTRY` at line 408-415 has only 6 journals (general/prl/prb/prx/npj/nature_family); `apl_materials` absent |
| `maglab lab note list` subcommand missing | K-partial | **OPEN** | `lab_app` has only `note` (create) and `plan`; `ELNNotebook.list_entries()` exists but is not reachable via CLI |
| Loop A: no checkpoint save per round | N-partial | **OPEN** | `loop_a.py` calls `engine.step()` per round but never calls `checkpoint.save()`; `state_path` parameter is accepted but only passed to `RalphEngine` constructor — checkpoint write not verified |
| Loop A: grounding DOI integrity not enforced | N-partial | **OPEN** | `ManuscriptPatch.grounding_dois` field exists; dummy path always passes `grounding_dois=[]`; no retraction check assertion in `loop_a.py` for non-dummy patch path |
| D2 `explain_anomaly` RAG not injected from CLI | O-partial | **OPEN** | `p5_literature.py:799`: `explain_anomaly(data, min_candidates=min_candidates)` — `rag_search_fn` parameter not passed; `reasoning.py:477` accepts it as optional but CLI never instantiates `CorpusRAG` for this call |
| `corpus_rag.py` BM25 not shared with `literature/rag.py` | H-partial | **OPEN** | `corpus_rag.py:82` defines its own `_BM25Index`; no import from `maglab.literature.rag`; two separate implementations remain |
| Retraction block does not hard-raise at `graph.py` | G-note | **OPEN (LOW)** | `graph.py` returns `IntegrityResult(is_blocked=True)` but no `raise` — caller must enforce; no enforcement comment added in Round-2 |
| Opt-out registry in-memory only | M-low | **OPEN (LOW)** | `disclosure.py:127`: `_OPTOUT_REGISTRY: set[str] = set()` — no persistence to JSON/SQLite |

---

## Remaining or New Gaps

### GAP-R1: Workflow Names in `harness.manifest.json` Do Not Match Plan §14.7

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/harness.manifest.json:146-169`
**Severity:** Medium
**Detail:** Plan §14.7 specifies four named workflows registered in `harness.manifest.json`: `survey`, `paper-review`, `citation-map`, `local-gap`. The manifest has agent definitions for all five required agents (local-context-librarian, search-scout, citation-auditor, paper-reviewer, synthesis-editor) but only one composite workflow named `literature-review`. The three remaining workflow names from the plan (`survey`, `citation-map`, `local-gap`) do not appear as either workflow entries or aliases.
**Fix:** Add `survey`, `paper-review`, `citation-map`, `local-gap` as workflow entries in `harness.manifest.json`. `survey` and `paper-review` can map to the existing `literature-review` step sequence; `citation-map` to `[citation-auditor]`; `local-gap` to `[local-context-librarian]`.

---

### GAP-R2: `.maglab/mcp.json` Not Created (T-P5-03 entirely unmet)

**File:** `.maglab/mcp.json` (does not exist)
**Severity:** Medium
**Detail:** Plan §14.7 specifies `paperplain` (MIT), `@cyanheads/openalex-mcp-server` (Apache-2.0), and `cite-mcp` (MIT) registered in `.maglab/mcp.json` with `npx` launch commands, license comments, and role annotations. No `mcp.json` exists anywhere in the repo. `maglab mcp list` prints "No MCP servers registered." This is the same gap as Round-1 — Round-2 did not address it.
**Fix:** Create `.maglab/mcp.json` (at repo root, not `maglab/.maglab/`) containing a `"servers"` dict with entries for the three connectors. The `mcp_list` command reads `Path(".maglab") / "mcp.json"` relative to CWD.

---

### GAP-R3: SPECTER2 Not Used in KeyBERT; LLM Domain Re-ranking Not Integrated (T-P5-05 partial)

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/maglab/literature/keywords.py:220`
**Severity:** Medium (SPECTER2 gap), Low (LLM re-rank gap)
**Detail:** Plan §14.3 specifies "KeyBERT/specter" — meaning KeyBERT with SPECTER2 as the embedding model. `keywords.py:220` instantiates `KeyBERT()` with no model argument (uses default sentence-transformers). `allenai/specter2_base` is imported in `literature/rag.py` but never passed to KeyBERT. LLM re-ranking step is fully absent with no injectable hook or stub; the module docstring defers this unconditionally to the caller.
**Fix (SPECTER2):** Change `keywords.py:220` to `kw_model = KeyBERT("allenai/specter2_base")`. Add a fallback try/except for offline mode.
**Fix (LLM re-rank):** Add a `rerank_fn: Callable[[list[WeightedKeyword]], list[WeightedKeyword]] | None = None` parameter to `extract_keywords_from_folder()`; if not None, apply it after score fusion. Add a `# P6-TODO: inject domain LLM reranker` comment stub.

---

### GAP-R4: APL Materials Rubric Not Implemented (§15.4 partial)

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/maglab/reviewer/rubrics.py:408-415`
**Severity:** Low-Medium
**Detail:** Plan §15.4 explicitly lists APL Materials as a target journal rubric. The module docstring (line 4) names it. `_RUBRIC_REGISTRY` has 6 entries (general/prl/prb/prx/npj/nature_family); `apl_materials` is absent. `get_rubric("apl_materials")` silently falls back to the general rubric.
**Fix:** Add `_make_apl_materials_rubric()` (threshold: applied/computational work, short letter format, strong experimental validation required) and register as `"apl_materials"` in `_RUBRIC_REGISTRY`.

---

### GAP-R5: `maglab lab note list` Subcommand Not Exposed (§13.5 T-P5-17)

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/maglab/commands/p5_literature.py:636-701`
**Severity:** Low-Medium
**Detail:** `ELNNotebook.list_entries()` is fully implemented with date/tag/sample/type filters. No CLI subcommand exposes it. `lab_app` has only `note` (create) and `plan`. Round-2 did not address this gap.
**Fix:** Add `@lab_app.command("note-list")` that accepts `--date`, `--tag`, `--sample`, `--type` filters and calls `ELNNotebook(nb_dir).list_entries(...)`, printing a Rich table.

---

### GAP-R6: D2 Explain — RAG Not Injected from CLI (T-P5-25 partial)

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/maglab/commands/p5_literature.py:799`
**Severity:** Low-Medium
**Detail:** `explain_anomaly()` in `core/reasoning.py:477` accepts `rag_search_fn: Callable | None`. The CLI call at line 799 omits it; `CorpusRAG` is never instantiated for the explain command (it is instantiated for the review command at line 557 but not shared). Evidence DOIs in the output are from the built-in mechanism DB only, not from a live literature RAG search.
**Fix:** In `explain_command()`, instantiate `CorpusRAG()` and pass `rag_search_fn=rag.search` to `explain_anomaly()`.

---

### GAP-R7: Loop A — No Checkpoint Save Per Round; Grounding DOI Integrity Not Enforced (§15.5 T-P5-24)

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/maglab/reviewer/loop_a.py`
**Severity:** Low
**Detail (checkpoint):** `run_loop_a()` calls `engine.step()` per round but no `checkpoint.save()` call follows. `state_path` is passed to `RalphEngine` but whether RalphEngine itself persists round data cannot be verified from this review (read-only scope). Round provenance exists in `LoopAResult.round_reviews` / `round_meta_reviews` but is not written to disk mid-loop.
**Detail (grounding integrity):** `ManuscriptPatch.grounding_dois` defaults to `[]`. The dummy patch path (used when `patch_generator_fn is None`) always passes `grounding_dois=[]`. There is no assertion that non-dummy `grounding_dois` have passed T-P5-10 retraction checks before applying the patch.
**Fix (checkpoint):** After each `engine.step()` call in the while loop, call `checkpoint.save(state_path, {round data})` if `state_path` is set.
**Fix (grounding integrity):** Add a guard in `run_loop_a()` after patch generation: `if patch.grounding_dois: _validate_grounding_dois(patch.grounding_dois, kg)`.

---

### GAP-R8 (Carry-forward, Low): `corpus_rag.py` BM25 Not Shared with `literature/rag.py`

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/maglab/reviewer/corpus_rag.py:82`
**Severity:** Low
**Detail:** Two independent `BM25Index` implementations: `literature/rag.py` has `BM25Index`; `reviewer/corpus_rag.py` has `_BM25Index`. Plan states "literature/ and reviewer/ corpus share this index". Not closed in Round-2. Code duplication risk; algorithmic drift possible.
**Fix:** Refactor `corpus_rag.py` to import and use `literature.rag.BM25Index` instead of the local `_BM25Index`.

---

### GAP-R9 (Carry-forward, Low): Opt-Out Registry In-Memory Only

**File:** `/Users/taewoopark/Desktop/Obsidian-Sync/aimag/maglab/reviewer/disclosure.py:127`
**Severity:** Low
**Detail:** `_OPTOUT_REGISTRY: set[str] = set()` — resets on every process start. An author opt-out exercised in one session is invisible to subsequent sessions.
**Fix:** Load/save from `~/.maglab/optout.json` (or `platformdirs.user_data_dir("maglab")/optout.json`) on module import and each mutation.

---

## Summary Table

| Gap | File | Severity | Round-2 Status |
|---|---|---|---|
| R1: Workflow names wrong in harness.manifest.json | `harness.manifest.json` | Medium | Partial — manifest created but names wrong |
| R2: `mcp.json` not created | `.maglab/mcp.json` | Medium | Not addressed |
| R3: SPECTER2 not in KeyBERT; no LLM re-rank hook | `literature/keywords.py:220` | Medium/Low | Not addressed |
| R4: APL Materials rubric absent | `reviewer/rubrics.py` | Low-Medium | Not addressed |
| R5: `lab note list` CLI subcommand absent | `commands/p5_literature.py` | Low-Medium | Not addressed |
| R6: RAG not injected into explain CLI | `commands/p5_literature.py:799` | Low-Medium | Not addressed |
| R7: Loop A checkpoint + grounding DOI integrity | `reviewer/loop_a.py` | Low | Not addressed |
| R8: Dual BM25 implementations | `reviewer/corpus_rag.py` | Low | Not addressed |
| R9: Opt-out registry in-memory | `reviewer/disclosure.py` | Low | Not addressed |
