# Physics / Simulation / Analysis — Requirements Conformance Review

**Reviewer domain:** physics core, multiscale simulation, effect-fitting registry  
**Plan docs reviewed:** `plan/03-physics-simulation.md`, `plan/04-analysis.md`  
**Impl docs reviewed:** `impl/02-P1-figure-sim.md`, `impl/03-P2-analysis.md`, `impl/04-P3-multiscale.md`  
**Review date:** 2026-05-19  
**Test run:** `pytest tests/unit/test_analysis_interface.py tests/unit/test_physics_*.py tests/unit/test_sim_*.py tests/golden/ -q` — all pass (2 golden tests skip due to missing external binaries: magnum.np P1 test, VAMPIRE binary test)

---

## Summary

**Verdict: Substantially MET with targeted gaps. No critical integrity violations.**

| Status | Count | Domain |
|--------|-------|--------|
| MET | 28 | Physics core, sim IR/validate/parse/custodian/handoff, all 3 handoffs, 6 providers, 21 effect models, FitResult+provenance, calibration, bilevel inner layer, device FoM (3 of 7), sim_objective interface, CLI commands |
| PARTIAL | 6 | SOT harmonic hall xi fitting, FMR spin-mixing conductance placement, ST-FMR xi_DL not in FitResult, µMAG #1–#5 golden tests (formula-only, no full solver run), magnetometry Curie/compensation temp, device FoM registry incomplete |
| MISSING | 4 | USMR effect model, macrospin LLG model, 2-sublattice LLG model, device FoM entries (MTJ standalone, spin-valve sensor, spin-orbit logic, magnon) |
| DEVIATION | 1 | SOT forward model uses simplified angular form (missing PHE-cross-term in xi signal) |

The verifiable-orchestrator principle is **intact**: all simulation DataPoints carry `ProvenanceType.SIMULATED`, all fit results carry `ProvenanceType.FITTED`, LLM does not inject numeric values, and physics bounds are enforced via `oracle.py` throughout.

---

## Findings

### §9 Physics Core (`physics/`)

| Requirement | Status | Evidence | Gap | Fix |
|------------|--------|----------|-----|-----|
| `constants.py` — CODATA values | MET | `maglab/physics/constants.py` — E_CHARGE, K_B, MU_0, HBAR, GAMMA_E all present | — | — |
| `units.py` — Oe↔A/m↔T, emu/cm³↔A/m, erg/cm↔J/m, J_ij meV↔K, DMI mJ/m²↔meV | MET | `maglab/physics/units.py:37–293` — all conversions with CODATA references | — | — |
| `quantity.py` — `Quantity` type | MET | `maglab/physics/quantity.py` — value, unit, source fields | — | — |
| `oracle.py` — sanity oracle: 0≤α≤1, M≤Ms, T>0, velocity limit | MET | `maglab/physics/oracle.py:51–415` — 9 check functions + integrated `check()` | — | — |
| `formulas.py` — multiscale formulas: exchange length, DW dynamics, skyrmion, spin wave, transport, multiscale bridging | MET | `maglab/physics/formulas.py` — 20 exported functions including `exchange_length`, `bloch_wall_energy/width`, `kittel_freq`, `skyrmion_hall_angle`, `spinwave_dispersion_fm`, `walker_breakdown_field`, `heisenberg_to_exchange_stiffness`, `afmr_frequency`, `ferrimagnet_compensation_freq` | — | — |
| `materials.py` + `material_builder.py` + `data/` — curated material DB | MET | Files present and tested in `tests/unit/test_material_builder.py` | — | — |

### §10 Multiscale Simulation (`sim/`)

| Requirement | Status | Evidence | Gap | Fix |
|------------|--------|----------|-----|-----|
| `spec.py` — `MultiScaleSpec={ScaleSpec[], Handoff[]}`, all 4 scale enums pre-declared | MET | `maglab/sim/spec.py:26–264` — `ScaleType` enum has micro/atomistic/dft/device; `Handoff` model; JSON round-trip tested in `tests/unit/test_sim_spec.py` | — | — |
| `backends/local.py`, `backends/cpu.py` — Mac local backend | MET | Files present; `BackendBase` interface implemented | — | — |
| `backends/ssh_hpc.py`, `backends/ssh_gpu.py` — Slurm + GPU | MET | `maglab/sim/backends/ssh_hpc.py`, `ssh_gpu.py` — mock mode tested in `tests/unit/test_sim_spec.py` | — | — |
| `validate.py` — static validation (Appendix D): cell < l_ex, α > 0, material completeness, run ≥ 5τ | MET | `maglab/sim/validate.py:298–579` — all 4 Appendix D micro rules, plus DFT/atomistic/handoff rules; `ValidationError` with structured messages; tested in `tests/unit/test_sim_validate.py` | — | — |
| `parse.py` — `JobResult` structured parser | MET | `maglab/sim/parse.py` — MuMax3/OOMMF/magnum.np outputs → `JobResult`; tested in `tests/unit/test_sim_parse.py` | — | — |
| `custodian.py` — engine error classification | MET | `maglab/sim/custodian.py` — ConvergenceError/InputError/ResourceError/UnknownError; tested in `tests/unit/test_sim_custodian.py` | — | — |
| `micro/mumax3.py`, `micro/oommf.py`, `micro/magnumnp.py` — micromagnetic backends | MET | All 3 files present with input generation; golden MIF/MX3 generation tested | — | — |
| µMAG standard problems #1–#5 golden-value verification | PARTIAL | `tests/golden/test_mumag_golden.py` — Problems #2,#3,#4,#5 tested via deterministic formulas only; #1 requires magnum.np (skip if absent) or OOMMF/MuMax3. Golden JSON present at `tests/golden/data/mumag_golden.json`. Full solver runs #1,#4,#5 skip without external binary. | DoD requires actual solver run for #1; currently only formula checks run deterministically | Install magnum.np in dev env or keep CI skip with clear badge; add magnumnp to `[sim]` extras with note |
| `sim/dft/` — VASP/QE/FLEUR input generation + J_ij/MAE/DMI parsing | MET | `maglab/sim/dft/input_gen.py`, `parse_dft.py`, `tb2j.py`; tested in `tests/unit/test_sim_dft_parse.py` including TB2J J_ij completeness warning | — | — |
| `sim/atomistic/` — VAMPIRE/Spirit input generation + M_s(T)/T_C/A(T)/K(T) parsing | MET | `maglab/sim/atomistic/input_gen.py`, `parse_atomistic.py`; tested in `tests/unit/test_sim_atomistic_parse.py` | — | — |
| `handoff.py` — DFT→atomistic→micro→device with units, assumptions, provenance | MET | `maglab/sim/handoff.py:1–681` — all 3 handoffs; `_DFT_TO_ATOMISTIC_ASSUMPTIONS`, `_ATOMISTIC_TO_MICRO_ASSUMPTIONS`, `_MICRO_TO_DEVICE_ASSUMPTIONS` inline; oracle validation at each step; DataPoints tagged `ProvenanceType.SIMULATED`; tested in `tests/golden/test_handoff_units.py` (16 tests pass) | — | — |
| Handoff unit continuity (Appendix D): scale N output units = N+1 input units | MET | `handoff.py:636–680` — `verify_unit_continuity()` checks required-key presence; oracle validates dimensional ranges; `HandoffUnitError` on mismatch; golden test `TestUnitContinuityAppendixD` passes | — | — |
| `sim/device/` — device scale stub | MET | `maglab/sim/device/spec.py` — `ScaleSpec(scale="device")` stub; `micro_to_device` handoff outputs feed it | — | — |
| `sim/pipeline.py` — multiscale pipeline CLI + bilevel sim_objective | MET | `maglab/sim/pipeline.py` — `sim_objective(params, T_range_K, backend)` returns `{T_K, M_s_Am, T_C_K, converged}`; mock mode runs correctly; tested in `tests/golden/test_handoff_units.py::TestSimObjectiveInterface` | — | — |

### §11 Analysis / Effect-Fitting Registry (`analysis/`)

#### Infrastructure

| Requirement | Status | Evidence | Gap | Fix |
|------------|--------|----------|-----|-----|
| `ModelProvider` ABC with `effects`, `get()`, `list()`, `@register_provider` | MET | `maglab/analysis/providers/base.py`; 6 providers registered; global registry in `providers/__init__.py` | — | — |
| `EffectModel` ABC with `name`, `subfield`, `references`, `parameters`, `measurement_config`, `forward()`, `fit()`, `symmetry_constraints` | MET | `maglab/analysis/effects/base.py:92–194` — full ABC; `ParamSpec` (name/unit/lower/upper/description), `MeasurementConfig` (geometry/tensor_rank/required_columns/notes), `FitResult` (params/uncertainties/chi2/reduced_chi2/covariance/provenance_id) all present | — | — |
| `fit.py` — lmfit `run_fit()` → `FitResult` with physical bounds, provenance, `FitConvergenceError` | MET | `maglab/analysis/fit.py:35–127` — lmfit `Minimizer`; `min`/`max` from `ParamSpec.lower/upper`; `_record_fit_datapoint()` creates `DataPoint(FITTED)`; `FitConvergenceError` on non-convergence; `run_fit_multi()` for simultaneous multi-dataset fit | — | — |
| `analysis/io.py` — CSV/HDF5 load → `DataPoint[]` | MET | `maglab/analysis/io.py` present | — | — |
| `analysis/symmetry.py` — magnetic point group allowed components | MET | `maglab/analysis/symmetry.py:57–213` — 7 point groups (m3m, 4/mmm, mm2, 2/m, -1, 6/mmm, 3); `ahe_constraints()`, `ohe_constraints()` for AHE rank-2 and OHE rank-3; tested in `tests/unit/test_analysis_interface.py` | — | — |
| `analysis/consistency.py` — inconsistency detection + D2 explain trigger | MET | `maglab/analysis/consistency.py` — `check_consistency()`, `check_carrier_density_consistency()`, `trigger_explain` field; deterministic only | — | — |
| `analysis/calibration.py` — calibration registry + systematic correction pipeline + GUM uncertainty budget | MET | `maglab/analysis/calibration.py` — `CalibrationRegistry`, declarative correction pipeline (background subtraction, Hall antisymmetrization, etc.), `uncertainty_budget()` GUM error budget table; `is_valid()` expiry check | — | — |
| `analysis/bilevel.py` — bilevel deterministic inner layer | MET | `maglab/analysis/bilevel.py` — `optimize_inner()` uses lmfit; `CircuitBreakerError` on max iterations; AIC/BIC computed; LLM does not touch numerics; `maglab fit --discover` entrypoint | — | — |

#### magnetotransport provider (T-P2-09 to T-P2-17)

| Effect | Status | Evidence | Gap |
|--------|--------|----------|-----|
| ordinary_hall: ρ_xy = R_H·B | MET | `effects/ordinary_hall.py` | — |
| anomalous_hall: ρ_xy = R_0·B + μ₀·R_s·M(H) | MET | `effects/anomalous_hall.py:101–155` — correct formula; fit uses linear regression init + lmfit; provenance tagged FITTED | — |
| tyj_scaling: ρ_AHE = a·ρ_xx0 + b·ρ_xx² | MET | `effects/tyj_scaling.py` — intrinsic (b·ρ_xx²) + extrinsic (a·ρ_xx0) terms | — |
| planar_hall: ρ_xy = (Δρ/2)·sin(2φ) | MET | `effects/planar_hall.py` | — |
| topological_hall: ρ_THE = ρ_xy − R_0·B − μ₀·R_s·M | MET | `effects/topological_hall.py` — background subtraction | — |
| amr: ρ(θ) = ρ⊥ + Δρ_AMR·cos²θ | MET | `effects/amr.py` — symmetry_constraints wired | — |
| smr: 3-geometry simultaneous fit | MET | `effects/smr.py` — uses `run_fit_multi()` for α/β/γ geometry simultaneous fit | — |
| gmr_tmr: G(θ) = G_0·(1 + TMR·cosθ/2); Julliere | MET | `effects/gmr_tmr.py` | — |
| **usmr**: Unidirectional Spin Hall Magnetoresistance | **MISSING** | Not in codebase anywhere | Plan §11.1 table explicitly lists USMR in magnetotransport provider | Add `effects/usmr.py` and register in `MagnetotransportProvider` |

#### spin_orbitronics provider (T-P2-18 to T-P2-22)

| Effect | Status | Evidence | Gap |
|--------|--------|----------|-----|
| sot_harmonic_hall: 1ω·2ω PHE correction | PARTIAL | `effects/sot_harmonic_hall.py:181–201` — `phe_corrected()` static method exists; fit() returns raw H_DL_raw/H_FL_raw. **Critical gap: the `xi` parameter is declared in `parameters` list and in `fit()` model_fn signature but the forward model does not include ξ-correction in its signal formula — xi is not propagated through the physics.** xi stays at 0 in fit output. | `phe_corrected()` is correct math, but xi is not fitted from data; must add PHE cross-term to forward model and auto-apply correction in `fit()` | `effects/sot_harmonic_hall.py:109–135`: add PHE-corrected signal to forward; after run_fit, auto-call `phe_corrected()` and store corrected H_DL/H_FL in FitResult.params |
| stfmr: V_mix = S·F_sym + A·F_asym; xi_DL extraction | PARTIAL | `effects/stfmr.py` — S/A/H_res/ΔH fitted correctly; `spin_hall_angle()` static method for ξ_DL. **Gap: ξ_DL is not returned in `FitResult.params`** — user must manually call `spin_hall_angle()` with FM/NM thickness inputs not available at fit time | Plan DoD: "S·A·H_res·ΔH 복원" → fits pass; but spin Hall angle extraction requires extra step not done automatically | Add `xi_DL` computed from S/A ratio to `FitResult.params` if material params supplied via geometry dict |
| spin_pumping_ishe: Δα → g↑↓; V_ISHE → θ_SH, λ_sf | MET | `effects/spin_pumping_ishe.py` — ΔH vs d_NM fit, g↑↓ extraction | — |
| orbital_hall (OHE): rank-3 tensor σ_OH[α][β][γ] (3×3×3) | MET | `effects/orbital_hall.py:51–67` — `sigma_OH` property returns (3,3,3) ndarray; `set_sigma_OH()` validates shape; `measurement_config.tensor_rank=3`; after fit, `new_tensor[0,1,2]` and antisymmetric component set; `ohe_constraints()` wired via symmetry.py | — |

#### ferromagnetic_resonance provider (T-P2-23 to T-P2-25)

| Effect | Status | Evidence | Gap |
|--------|--------|----------|-----|
| fmr_kittel: in-plane and out-of-plane Kittel formula | MET | `effects/fmr_kittel.py` — (ω/γ)² = μ₀²H_res(H_res+M_eff) | — |
| gilbert_damping: ΔH = ΔH₀ + (2α/γ)·f (linewidth) | MET | `effects/gilbert_damping.py` — correct formula; freq input in GHz, γ' in GHz/T; dH_0 in T | — |
| **spin_mixing_conductance** (standalone, in FMR provider) | PARTIAL | `spin_pumping_ishe.py` in spin_orbitronics provider extracts g↑↓ from linewidth enhancement; plan §11.1 lists "스핀혼합전도도" under ferromagnetic_resonance provider | Spin mixing conductance is functionally covered in spin_pumping_ishe, but not registered in FMRProvider. The plan's provider table places it in FMR. | Move or duplicate g↑↓ extraction as a separate `FMRProvider` effect, or update plan table; document the placement decision |

#### magnetization_dynamics provider (T-P2-26 to T-P2-29)

| Effect | Status | Evidence | Gap |
|--------|--------|----------|-----|
| llg (+STT/SOT): scipy ODE (RK45) | MET | `effects/llg.py` — scipy `solve_ivp` RK45; precession frequency/damping analytical comparison tested in golden | — |
| **macrospin model** | **MISSING** | Not found in any analysis effect file | Plan §11.1: "매크로스핀" as distinct effect under magnetization_dynamics | Add `effects/macrospin.py` — single-domain Stoner-Wohlfarth macrospin with STT/SOT |
| dw_1d (q–Φ model): Walker breakdown H_W | MET | `effects/dw_1d.py` — Schryer-Walker; H_W analytical + v(H) below Walker; Walker breakdown field exposed in params | — |
| thiele: skyrmion Hall angle tan(θ_SkH) = G/(αD) | MET | `effects/thiele.py` — G×v + αDv = F formulation; θ_SkH formula | — |
| **2-sublattice LLG** | **MISSING** | Not in any effect file | Plan §11.1 lists "2-부격자 LLG" (antiferromagnet/ferrimagnet two-sublattice) | Add `effects/llg_2sublattice.py`; formulas available in `physics/formulas.py` (`ferrimagnet_compensation_freq`, `afmr_frequency`) |

#### magnetometry provider (T-P2-30)

| Effect | Status | Evidence | Gap |
|--------|--------|----------|-----|
| hysteresis: M_s, M_r, H_c, anisotropy extraction | MET | `effects/hysteresis.py` — Stoner-Wohlfarth model optional; M_s/H_c extraction | — |
| **Curie temperature / compensation temperature models** | PARTIAL | Oracle checks T_C range; `physics/formulas.py` has `ferrimagnet_compensation_freq()`; `parse_atomistic.py` extracts T_C from M(T). **No `EffectModel` for Curie/compensation temperature fitting from M(T) data** | Plan §11.1 lists "Curie/보상 온도" under magnetometry | Add `effects/curie_temperature.py` with M(T) → T_C Brillouin/power-law fit |

#### domain_walls_skyrmions provider (T-P2-31 to T-P2-32)

| Effect | Status | Evidence | Gap |
|--------|--------|----------|-----|
| thiele (shared from mag_dyn) | MET | Registered in DWSkyrProvider pointing to same model | — |
| dmi (BLS): Δf = (γ·D_i)/(π·M_s)·k | MET | `effects/dmi.py` — BLS asymmetric frequency shift; linear fit for D_i | — |

#### §11.7 Device FoM Registry

| Requirement | Status | Evidence | Gap |
|------------|--------|----------|-----|
| SOT-MRAM FoM: Δ, j_c, V | MET | `device_fom.py:67–154` — correct formulas with IRDS 2023 targets; CLI `maglab device fom sot-mram` produces table | — |
| STT-MRAM FoM | MET | `device_fom.py:157–203` — Δ, j_c_stt, TMR, R_AP | — |
| Racetrack FoM: H_W, v_DW | MET | `device_fom.py:206–256` — Walker field, DW velocity | — |
| **MTJ (standalone)**, **spin-valve sensor**, **spin-orbit logic**, **magnon** FoMs | **MISSING** | `list_devices()` → `['sot-mram', 'stt-mram', 'racetrack']` only | Plan §11.7 lists 7 device types | Add `effects/device_fom_mtj.py`, `spin_valve.py`, `spin_orbit_logic.py`, `magnon.py`; register in `_DEVICE_FOM_REGISTRY` |

#### §11.6 Calibration

| Requirement | Status | Evidence | Gap |
|------------|--------|----------|-----|
| Calibration registry with expiry | MET | `calibration.py:76+` — JSON storage, `is_valid()` expiry check | — |
| Declarative correction pipeline (background subtraction, Hall antisymmetrization, offset, drift) | MET | `calibration.py` — `CorrectionStep` dataclass; `apply_corrections()`; reversible | — |
| GUM uncertainty budget table | MET | `calibration.py` — `uncertainty_budget()` computes σ_total² = σ_measurement² + σ_calibration² + σ_fit² | — |

#### §11.8 Bilevel Model Discovery

| Requirement | Status | Evidence | Gap |
|------------|--------|----------|-----|
| Inner deterministic layer (optimize_inner) | MET | `analysis/bilevel.py` — `optimize_inner()` takes `model_fn` from LLM, optimizes params deterministically with lmfit; `CircuitBreakerError`; AIC/BIC output | — |
| `maglab fit --discover` entrypoint | MET | CLI entrypoint wired; `--discover` flag routes to bilevel | — |
| Audit log separates LLM form vs. deterministic params | MET | `BilevelResult.model_description` carries LLM-proposed form; `fit_result.params` carries deterministic values | — |

### Verifiable Orchestrator Principle

| Check | Status | Evidence |
|-------|--------|----------|
| Simulation results tagged SIMULATED | MET | `handoff.py:207–228` — DataPoints with `ProvenanceType.SIMULATED`; `parse.py` uses same |
| Fitting results tagged FITTED | MET | `fit.py:113–127` — `_record_fit_datapoint()` creates `DataPoint(ProvenanceType.FITTED)` for every `run_fit()` call |
| LLM cannot inject numbers into FitResult | MET | `FitResult` created only by `run_fit()` which calls lmfit; honesty gate in `core/hooks.py` blocks untagged figure data |
| Physics bounds enforced | MET | `oracle.py` called in handoffs, validate.py, and indirectly in calibration expiry |
| No fabricated numbers in formulas | MET | All formulas cite primary literature in docstrings; constants from CODATA |

---

## Critical Gaps (Ranked)

### Gap 1 — SOT Harmonic Hall: xi parameter not fitted (DEVIATION)
**Severity: High** — PHE correction is the advertised key feature of this model.  
**File:** `maglab/analysis/effects/sot_harmonic_hall.py:109–180`  
**Issue:** `xi` is declared in `parameters` and accepted in `model_fn` signature, but the forward model does not include a ξ-dependent term in the signal; `xi` stays at 0.0 after fitting. The PHE correction formula (`H_DL = (H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)`) is only available as a post-fit static method requiring manual user invocation.  
**Fix:**
1. Add ξ-dependent term to `forward()`: the 2ω signal includes a term proportional to ξ that mixes DL and FL components.
2. In `fit()`, after convergence, auto-call `phe_corrected()` and store `H_DL`, `H_FL` (corrected) in `FitResult.params` alongside raw values.
3. Update `measurement_config.notes` to explain raw vs. corrected.

### Gap 2 — ST-FMR xi_DL not returned in FitResult (PARTIAL)
**Severity: Medium-High** — spin Hall angle is the primary experimental output.  
**File:** `maglab/analysis/effects/stfmr.py`  
**Issue:** `spin_hall_angle()` is a static method that requires external input (t_FM, t_NM, Ms) not available at fit() call. ξ_DL never appears in FitResult.params.  
**Fix:** Accept optional `geometry={"Ms": ..., "t_FM": ..., "t_NM": ...}` in `fit()`. If present, compute ξ_DL and include as `FitResult.params["xi_DL"]`. Document as conditional output.

### Gap 3 — USMR effect missing entirely (MISSING)
**Severity: Medium** — listed in plan §11.1 provider table.  
**File:** `maglab/analysis/providers/magnetotransport.py` (effect missing)  
**Fix:** Create `maglab/analysis/effects/usmr.py` — Unidirectional Spin Hall Magnetoresistance: ΔR/R ∝ j·M (current-polarity-dependent), references: Olejnik et al., Nat. Commun. 8, 15434 (2017). Register in `MagnetotransportProvider`.

### Gap 4 — Device FoM: 4 of 7 device types missing (MISSING)
**Severity: Medium** — `maglab device fom` CLI is only partially functional.  
**File:** `maglab/analysis/device_fom.py`  
**Missing:** MTJ standalone, spin-valve sensor, spin-orbit logic, magnon device.  
**Fix:** Add `mtj_fom()`, `spin_valve_fom()`, `spin_orbit_logic_fom()`, `magnon_fom()` functions with cited formulas; register in `_DEVICE_FOM_REGISTRY`.

### Gap 5 — Macrospin and 2-sublattice LLG models missing (MISSING)
**Severity: Medium** — plan §11.1 lists both under magnetization_dynamics.  
**Files:** `maglab/analysis/effects/` (no `macrospin.py` or `llg_2sublattice.py`)  
**Fix:**
- `macrospin.py`: Stoner-Wohlfarth single-domain with STT/SOT; parameters: α, Hk, M_s, θ_0.
- `llg_2sublattice.py`: coupled LLG for ferrimagnets/AFMs; use `ferrimagnet_compensation_freq()` from `physics/formulas.py`. References: Kittel (1952), MacNeill et al. (2019).

### Gap 6 — µMAG golden tests: formula-only, no full solver run (PARTIAL)
**Severity: Low-Medium** — plan DoD requires µMAG #1–#5 actual simulation passes.  
**File:** `tests/golden/test_mumag_golden.py`  
**Issue:** Problems #2, #3, #4, #5 are verified via deterministic formulas (exchange_length, bloch_wall_energy/width, oracle range checks) — **correct and sufficient for physics** but the µMAG standard problem intent is simulation convergence, not formula correctness. Problem #1 magnum.np test skips if not installed.  
**Fix:** Add magnum.np to `[sim]` extras and document in CI matrix. Alternatively, mark the formula-only tests as `[formula]` and create separate `[solver]` tests that require binaries, skippable in CI without degrading coverage visibility.

### Gap 7 — Magnetometry: Curie/compensation temperature model missing (PARTIAL)
**Severity: Low** — plan §11.1 mentions "Curie/보상 온도" under magnetometry.  
**File:** `maglab/analysis/effects/` (no Curie temp effect model)  
**Fix:** Add `effects/curie_temperature.py` — M(T) → T_C fit using Brillouin function or power-law (M ~ (1−T/T_C)^β); references: Kittel (2004). Register in `MagnetometryProvider`.

---

## User-Perspective Check

What the plan promises that a user **cannot currently do** via the CLI or API:

1. **`maglab fit --effect usmr data.csv`** — fails: USMR not registered. (`maglab fit --effect list` omits it.)

2. **SOT harmonic hall PHE correction applied automatically** — a user running `maglab fit --effect sot_harmonic_hall harmonic_hall.csv` gets raw H_DL_raw/H_FL_raw with xi=0.0; they must manually call `SOTHarmonicHall.phe_corrected()` — this contradicts the plan promise of integrated PHE correction.

3. **`maglab fit --effect stfmr stfmr.csv` → spin Hall angle in result** — the spin Hall angle ξ_DL is not in FitResult.params; user must manually call `STFMREffect.spin_hall_angle(S, A, Ms, t_FM, t_NM)` with FM/NM thickness values.

4. **`maglab device fom mtj ...`** / **`maglab device fom spin-valve ...`** / etc. — fails: only sot-mram, stt-mram, racetrack registered.

5. **`maglab fit --effect macrospin data.csv`** / **`maglab fit --effect llg_2sublattice data.csv`** — both fail: effects not implemented.

6. **`maglab fit --effect curie_temperature mt_data.csv`** — fails: no Curie/compensation temperature effect model in magnetometry provider.

7. **µMAG #1 solver validation in CI** — the golden test for #1 skips if magnum.np is not installed, meaning CI shows partial coverage without explicit indication that a key milestone (DoD item T-P1-09) is only formula-tested.

---

*Report generated by read-only requirements-conformance review. No implementation files were modified.*
