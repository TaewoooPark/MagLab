# MagLab — Requirements Certification

> Final conformance record for the MagLab implementation against `plan/01–11`
> and `PLAN.md`.
>
> - **Phase 1** — P0–P6 implementation.
> - **Phase 2** — plan-matching review + iterative patch loop.
> - **Phase 3** — certification that every plan requirement is fulfilled.
>
> Evidence date: 2026-05-19. All paths are relative to the repository root.

---

## 1. Phase 1 — Implementation completeness

Foundation and phases P0–P6 are all implemented, tested, and integrated.

| Phase | Scope | Status |
|---|---|---|
| Foundation | repo · toolchain · package skeleton · CI | ✅ complete |
| P0 | verifiable-orchestrator core (harness · CLI · physics · provenance · MCP) | ✅ complete |
| P1 | micromagnetic single-scale sim · figure dataplot | ✅ complete |
| P2 | effect-fitting registry · analysis · device FoM | ✅ complete |
| P3 | multiscale sim (DFT→atomistic→micro) · simviz | ✅ complete |
| P4 | instrument workflow · Ralph loop engine · figure schematic | ✅ complete |
| P5 | literature intelligence · ELN · persona review | ✅ complete |
| P6 | journal authoring · messaging gateway · hypotheses | ✅ complete |

**Quality gates (whole repository):**

- Test suite: green — `pytest` exits 0 with zero failures and zero errors.
- Lint: `ruff check maglab/ tests/` — all checks pass.
- Types: `mypy maglab/` — no issues found in 195 source files.
- Language: zero Korean text outside the plan documents (`PLAN.md`, `plan/`,
  `impl/`); all code, comments, docstrings, skills, and agent definitions are
  English.
- CLI: every Appendix-A command is wired to a real implementation (no stubs).

---

## 2. Phase 2 — Plan-matching review & patch loop

### Round 1 — domain reviews + patches

Five domain reviews checked the implementation against the plan
requirement-by-requirement, from both a user perspective (is the feature
reachable and working?) and a backend perspective (is the logic correct,
tested, provenance-tracked, honest?). Reports: `impl/review/01–05`.

Every `MISSING` / `PARTIAL` / `DEVIATION` finding received a patch.

#### Domain 1 — Harness & Delivery (`impl/review/01-harness-delivery.md`)

Round-1 verdict: 47 MET / 7 PARTIAL / 3 MISSING / 1 DEVIATION.

| Finding | Patch applied |
|---|---|
| CRITICAL-1 — HonestyGate not applied at the REPL turn boundary | `Orchestrator.respond()` now runs `_apply_honesty_gate()` → `run_gate()`; violations surfaced as a warning header |
| CRITICAL-2 — oracle not in the PreToolUse hook chain | `oracle_hook()` added to `core/hooks.py`, registered first in `default_registry()`; blocks unphysical physics-tool calls |
| CRITICAL-3 — MCP client (A-role) absent | `maglab/llm/mcp_client.py` created; `mcp add/enable/disable` CLI subcommands added |
| HIGH-4 — `harness.manifest.json` absent | manifest created (10 agents · 3 skills · MCP server · 4 workflows · model routing); `core/manifest.py` loader; loaded by `Orchestrator` |
| HIGH-5 — orchestrator ignored `ModelRouter` | `Orchestrator` accepts an optional `ModelRouter`; stage-wise routing wired |
| #7 — experiment-manager subagent missing | `agents/experiment-manager.md` created |
| #19 — detached Ralph loop skipped git commits | `detached_loop(git_commit=...)` opt-in per-iteration commit |
| #25 — ResearchPool had no vector index | `ResearchPool.semantic_query()` — TF-IDF cosine relevance ranking (§5.13) |
| #54 — proactive gateway notifications not wired | `Orchestrator` accepts a gateway runner; `run()` emits a completion notification |
| #43 / #56 | verified already-satisfied / accepted naming deviation — no change needed |

#### Domain 2 — Physics / Simulation / Analysis (`impl/review/02-physics-sim-analysis.md`)

Round-1 verdict: substantially met, 7 gaps.

| Gap | Patch applied |
|---|---|
| Gap 3 — USMR effect missing | `analysis/effects/usmr.py` created, registered in the magnetotransport provider |
| Gap 4 — device FoM registry incomplete (3/7) | 4 device types added (`mtj`, `spin_valve_sensor`, `spin_orbit_logic`, `magnon`) — 7 total |
| Gap 1 — SOT harmonic-Hall `xi` not fitted | integrated PHE-correction path in `sot_harmonic_hall.py` |
| Gap 2 — ST-FMR `xi_DL` not in `FitResult` | `xi_DL` derived and stored in `FitResult.params` when geometry is supplied |
| Gap 5 — macrospin / 2-sublattice LLG missing | `macrospin.py`, `llg_2sublattice.py` created and registered |
| Gap 7 — Curie-temperature model missing | `curie_temperature.py` (power-law M(T) fit + compensation) created and registered |
| Gap 6 — µMAG golden uses formula checks | DEFERRED — actual solver runs require external binaries (magnum.np); golden formula checks remain in place |

#### Domain 3 — Figure / Experiment (`impl/review/03-figure-experiment.md`)

Round-1 verdict: 31 MET / 8 PARTIAL / 6 MISSING / 3 DEVIATION.

| Finding | Patch applied |
|---|---|
| CRITICAL — SCPI temperature limit not enforced | `check_scpi_sequence()` now enforces `max_temperature_k` → `TEMPERATURE_OVER` |
| `compose.py` placeholder panels | wired to `SchematicRenderer` + `SimVizRenderer` |
| figure export provenance not recorded | `figure/export.py` records the saved path in the provenance ledger |
| instrument-domain MCP tools absent | `instr_search_manual` · `instr_ingest_manual` · `instr_generate_skill` · `instr_scaffold` · `instr_safety_check` + `manuals://` resource |
| `maglab figure primitives` CLI missing | `figure primitives list/show` subcommand wired |
| `Category` enum for the primitive taxonomy | added to `figure/primitives/spec.py` |

#### Domain 4 — Literature / Review (`impl/review/04-literature-review.md`)

Round-1 verdict: substantially met, 8 partial + 2 missing.

| Finding | Patch applied |
|---|---|
| OpenAlex abstract always empty (bug) | `_reconstruct_abstract()` rebuilds the abstract from the inverted index |
| `maglab review` did not surface the meta-review | `review` now renders `MetaReviewer` consensus + dissent |
| bundled offline data CSVs absent | `sjr.csv` · `eigenfactor.csv` · `nemad.csv` created |
| `lit search` did not produce an evidence matrix | `lit search` builds and persists an `EvidenceMatrix` JSON |
| `maglab mat build` CLI missing | `mat build` subcommand wired to the F5 material builder |

#### Domain 5 — Authoring / Gateway / Integrity (`impl/review/05-authoring-integrity.md`)

Round-1 verdict: 33 MET / 4 PARTIAL / 3 MISSING / 1 DEVIATION.

| Finding | Patch applied |
|---|---|
| SECURITY — `install_service` skipped its 0600 credential check | check added at the top of `install_service` |
| SECURITY — `gateway start` wrote the parent PID | now writes the daemon subprocess PID |
| INTEGRITY — no-LLM semantic classifier hard-blocked all authoring | fallback returns `PARTIAL` (non-blocking) with a warning |
| `maglab comms rebuttal` missing | `comms rebuttal` subcommand added |
| `agents/hypothesis-gen.md` / `agents/experiment-manager.md` missing | both agent definitions created |

### Round 2 — patch verification

- **Full test suite**: green — `pytest` exits 0, zero failures, zero errors.
- **Lint / types**: `ruff` clean across `maglab/` + `tests/`; `mypy` clean (195 files).
- **Behavioral verification of critical gap closures**:
  - oracle hook blocks `alpha=50` / `T=-10` with a physics reason and runs
    first in the hook chain;
  - `Orchestrator.respond()` routes its output through `run_gate()`;
  - `maglab mcp` exposes `add` / `enable` / `disable`;
  - `maglab comms` exposes all six communications commands incl. `rebuttal`;
  - the SCPI safety gate blocks `TEMP 9999`;
  - `harness.manifest.json` is valid and loads 10 agents;
  - the OpenAlex abstract reconstruction produces real abstract text.

### Round 3 — final re-review + patches

Five re-review agents (`impl/review/round3-01..05`) re-checked each domain
against the plan, confirming every Round-1 gap was closed and scanning for
remaining or newly-introduced gaps. Every gap they raised was then patched.

| Domain | Round-3 verdict | Resolution |
|---|---|---|
| Figure / Experiment | CLEAN | all 8 Round-1 gaps confirmed closed |
| Physics / Sim / Analysis | CLEAN | all 6 non-deferred gaps confirmed closed; µMAG live-solver runs accepted as a deferral (external-binary dependency) |
| Harness & Delivery | GAPS REMAIN → closed | 2 test-coverage gaps (oracle-hook registration, detached git-commit) — regression tests added |
| Authoring / Gateway / Integrity | GAPS REMAIN → closed | `advanced-materials` journal template + Word `.dotx`, presentation templates, 3 bundle comms skills, docstring regression — all patched |
| Literature / Review | GAPS REMAIN → closed | OpenAlex / manifest workflows / APL rubric / `lab note list` / explain-RAG / Loop-A checkpoint / opt-out persistence / SPECTER2 — all patched |

After the Round-3 patches: full test suite green (`pytest` exit 0, zero
failures), `ruff` clean, `mypy` clean (195 files), zero Korean.

---

## 3. CLI surface — Appendix A conformance

Every command in the Appendix-A tree is wired to a real implementation:

`auth` · `theme` · `physics` · `mat` (incl. `build`) · `sim` · `fit` ·
`analyze` · `figure` (incl. `primitives`) · `instr` · `lit` · `review` ·
`write` · `comms` (incl. `rebuttal`) · `ralph` · `gateway` · `skill` ·
`ask` · `run` · `lab` · `present` · `hypotheses` · `explain` · `device` ·
`cost` · `mcp` (incl. `add`/`enable`/`disable`) · `agents` · `report` ·
`prov` · `config` · `task`.

No honest-stub placeholders remain.

---

## 4. Phase 3 — Certification verdict

**VERDICT: CERTIFIED.**

All three phases are complete and verified:

- **Phase 1** — Foundation and P0–P6 are implemented, integrated, and pass
  their gates.
- **Phase 2** — three review rounds executed: Round 1 (five-domain
  plan-conformance review + patches), Round 2 (patch verification — full
  suite + behavioural checks of every critical gap closure), Round 3
  (five-domain re-review + patches for every remaining gap).
- **Phase 3** — final verification on the patched codebase:
  - `pytest` — full suite passes (exit 0, zero failures, zero errors).
  - `ruff check maglab/ tests/` — all checks pass.
  - `mypy maglab/` — no issues found (195 source files).
  - zero Korean text outside the plan documents.
  - every Appendix-A CLI command wired to a real implementation (no stubs).
  - the verifiable-orchestrator invariants hold — honesty gate at the REPL
    boundary, oracle hook in the PreToolUse chain, W3C PROV provenance,
    no fabricated numbers or citations.

Every CRITICAL, HIGH, and MEDIUM finding across the five review reports —
and every Round-3 re-review gap — has been closed and verified.

### Accepted deferrals (documented, non-blocking)

Reviewed and explicitly accepted as out-of-scope; they do not block
certification:

- µMAG golden tests use deterministic formula checks rather than live solver
  runs — live runs require external binaries (magnum.np / OOMMF / MuMax3)
  absent from CI; the corresponding tests skip cleanly.
- Spin mixing conductance is implemented under the `spin_orbitronics`
  provider rather than `ferromagnetic_resonance` — a provider-placement
  cosmetic deviation, not a functional gap.
- A few LOW-priority items (e.g. an external-MCP-connector bootstrap file)
  are documented for a future iteration.

**The MagLab implementation fulfils the requirements of `plan/01–11` and
`PLAN.md`.**
