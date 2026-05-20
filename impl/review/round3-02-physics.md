# Round-3 Physics / Simulation / Analysis — Conformance Re-Review

**Review scope:** `plan/03-physics-simulation.md`, `plan/04-analysis.md`  
**Baseline:** Round-1 report `impl/review/02-physics-sim-analysis.md`  
**Patches applied in Round-2:** Gaps 1–5, 7 (Gap 6 declared DEFERRED)  
**Review date:** 2026-05-19  
**Test run:**  
```
.venv/bin/pytest tests/ --timeout=120 -p no:warnings
2339 passed, 3 skipped in 67.58s
```
All 2339 tests pass; 3 skips are pre-existing (magnum.np binary absent — Gap 6 deferred item).

---

## Verdict

**CLEAN**

All 6 non-deferred Round-1 gaps are genuinely closed. No plan requirement remains unmet in the scope of this review. No regression was introduced by the Round-2 patches. Gap 6 (µMAG golden actual solver runs) remains an accepted DEFERRED item and does not change the verdict.

---

## Closure Check

| Round-1 Gap | Closed? | Evidence |
|---|---|---|
| **Gap 1** — SOT harmonic Hall: xi not fitted from 2ω data | CLOSED | `sot_harmonic_hall.py` fit() now accepts xi from `geometry["xi"]` or estimates it from co-supplied `data["V_1omega"]` via linear regression on the 1ω signal. After convergence, `phe_corrected()` is called automatically; `H_DL` and `H_FL` (corrected) appear in `FitResult.params` alongside the raw values. The physics reason xi is not a free 2ω parameter is documented in the module docstring (Hayashi 2014 §II.C). Tests: `TestSOTHarmonicHallXiFitting` — 6 tests, all pass. |
| **Gap 2** — ST-FMR xi_DL absent from FitResult | CLOSED | `stfmr.py` fit() now accepts optional `geometry={"Ms", "t_FM", "t_NM"}`. When present, ξ_DL is computed via `spin_hall_angle()` and stored as `FitResult.params["xi_DL"]`. When geometry is absent, xi_DL is not included (backward compatible). Tests: `TestSTFMRXiDL` — 3 tests, all pass including formula consistency check. |
| **Gap 3** — USMR effect model missing | CLOSED | `maglab/analysis/effects/usmr.py` created. Implements two fitting modes: current-sweep (`A(j) = ε·j + offset`) and angle-sweep (`A(φ) = ε·j₀·sin(φ) + offset`). Registered in `MagnetotransportProvider`; provider now lists 9 effects. References: Olejnik et al. Nat. Commun. 8, 15434 (2017); Avci et al. Nat. Phys. 11, 570 (2015). Tests: `TestUSMREffect` — 6 tests, all pass. |
| **Gap 4** — Device FoM: 4 of 7 types missing | CLOSED | `device_fom.py` now contains `mtj_fom()`, `spin_valve_sensor_fom()`, `spin_orbit_logic_fom()`, `magnon_device_fom()`. All 7 types registered in `_DEVICE_FOM_REGISTRY`; `list_devices()` returns all 7. Each function cites primary literature (Yuasa/Ikeda for MTJ, Dieny/Freitas for spin-valve, Manipatruni/Dieny for SOL, Chumak/Kruglyak for magnon). Tests: `TestDeviceFoMNewTypes` — 17 tests, all pass. |
| **Gap 5** — Macrospin and 2-sublattice LLG missing | CLOSED | `macrospin.py`: Stoner-Wohlfarth single-domain with STT/SOT torques; `sw_switching_field()` analytic astroid plus RK4 LLG dynamics; registered in `MagnetizationDynamicsProvider`. `llg_2sublattice.py`: coupled LLG for AFM/FiM with three fitting modes (AFMR analytic, FiM compensation frequency, RK4 dynamics); uses `afmr_frequency()` and `ferrimagnet_compensation_freq()` from `physics/formulas.py`; registered in `MagnetizationDynamicsProvider`. Tests: `TestMacrospinModel` (7 tests) and `TestLLG2SublatticeModel` (6 tests) — all pass. |
| **Gap 6** — µMAG golden tests: formula-only, no full solver run | DEFERRED | Status unchanged from Round-1. Problems #2–#5 verified via deterministic formulas; #1 skips if magnum.np absent. This is an accepted deferred item (binary dependency). Does not affect CLEAN verdict. |
| **Gap 7** — Magnetometry: Curie/compensation temperature model missing | CLOSED | `curie_temperature.py` created. Implements power-law M(T) = M_0·(1−T/T_C)^β fitting with T_C, M_0, β as free parameters (bounds: T_C≥1 K, 0.1≤β≤0.8). Compensation temperature T_comp is auto-extracted from M_net zero-crossing when `data["M_a"]` and `data["M_b"]` are supplied. Registered in `MagnetometryProvider`. References: Kittel (2004), Collins et al. Phys. Rev. 179, 417 (1969), Hansen et al. Phys. Rev. B 40, 11950 (1989). Tests: `TestCurieTemperatureModel` — 8 tests, all pass. |

---

## Remaining or New Gaps

### Accepted Deferred Item (does not make verdict GAPS REMAIN)

**Gap 6 — µMAG golden solver runs (unchanged from Round-1)**  
File: `tests/golden/test_mumag_golden.py`  
Status: Formula-only verification for problems #2–#5; problem #1 (magnum.np) skips when binary absent. This is a CI binary dependency issue, not a code error. Fix when magnum.np is added to `[sim]` extras.

### Residual Partial Finding (pre-existing, not in the 7 critical gaps)

**Spin mixing conductance placement in FMR provider**  
File: `maglab/analysis/providers/ferromagnetic_resonance.py`  
Status: `FMRProvider` still lists only `FMRKittel` and `GilbertDamping`. Spin mixing conductance (g↑↓) extraction is implemented in `spin_pumping_ishe.py` under the `spin_orbitronics` provider. Plan §11.1 places "스핀혼합전도도" under `ferromagnetic_resonance`. This was a PARTIAL finding in Round-1, was not listed as one of the 7 critical gaps, and was not patched in Round-2. It does not prevent Round-3 from being CLEAN (not in scope for this round), but is carried forward for completeness.  
Recommended fix: add a `SpinMixingConductance` wrapper effect to `FMRProvider`, re-using the linewidth-enhancement extraction logic from `spin_pumping_ishe.py`, or document the placement decision.

---

## Verifiable Orchestrator Integrity — Confirmed

| Check | Status |
|---|---|
| All `FitResult` objects created only via `run_fit()` | Confirmed — all new effects (`usmr.py`, `macrospin.py`, `llg_2sublattice.py`, `curie_temperature.py`, `sot_harmonic_hall.py`, `stfmr.py`) call `run_fit()` exclusively |
| New fields in `FitResult.params` are derived deterministically | Confirmed — `xi` stored from `geometry["xi"]` input (no LLM path); `H_DL`/`H_FL` from `phe_corrected()` (closed-form); `xi_DL` from `spin_hall_angle()` (closed-form); `T_comp` from zero-crossing interpolation |
| Physics bounds enforced | Confirmed — all new `ParamSpec` entries have physical lower/upper bounds where applicable (T_C≥1 K, 0.1≤β≤0.8, α∈[1e-6,1], |ξ|<0.5) |
| No fabricated constants | Confirmed — all new formulas cite primary literature in docstrings; CODATA constants from `maglab/physics/constants.py` |
| No regression in existing tests | Confirmed — 2339 passed, 3 skipped (same skips as before) |

---

*Read-only review. Only this file was modified.*
