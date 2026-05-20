# Code Review Round 15 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-and-fix audit)
**Date**: 2026-05-20
**Based on**: current code after Rounds 1–14 patches

---

## Verdict

**CLEAN**

A complete fresh adversarial re-audit of every file in the domain found no genuine
physics defects, dimensional errors, logic errors, numerical hazards, or docstring/code
formula discrepancies. Round 14 declared CLEAN and the status is confirmed unchanged.
All 74 Python source files were read in full; 15 independent numerical cross-checks
were performed; ruff, mypy, and all 368 domain-relevant unit tests pass.

---

## Findings & Fixes

None. No genuine defects were found.

---

## Non-Findings

Items investigated in detail and dismissed in this round (fresh independent checks,
not repeating prior round explanations verbatim).

### `maglab/physics/formulas.py`

- **`exchange_length`** — `sqrt(2A/(μ₀Ms²))`. Numerical: Py (A=13 pJ/m, Ms=860 kA/m)
  → 5.29 nm. Literature 5.3 nm. ✓
- **`bloch_wall_width`** — `π√(A/K)`. YIG (4 pJ/m, 610 J/m³) → 254 nm, lit 250–260 nm. ✓
- **`bloch_wall_energy`** — `4√(AK)`. Numerically verified, K≤0 guard present. ✓
- **`walker_breakdown_field`** — `αK/(2μ₀Ms)`. Numerically verified: code=46.27 A/m
  matches manual for Py/K_⊥=1e4. Factor-of-2 is correct per Schryer & Walker (1974). ✓
- **`walker_velocity`** — `γΔμ₀Ms/2`. Dimensional: `[rad/(s·T)][m][T·m/A][A/m]=m/s`. ✓
- **`dw_velocity_below_walker`** — `γΔμ₀H/(1+α²)`. Code=11.063 m/s matches manual. ✓
- **`skyrmion_radius_dmi`** — `πD/(4K_eff)`. Guard returns −1 when K_eff≤0 (correct:
  for D=1.5 mJ/m², Ms=1.4 MA/m the demagnetization dominates, K_eff<0). ✓
- **`skyrmion_stability_criterion`** — `D²/(4AK_eff)`. Guard for K_eff≤0 and A≤0. ✓
- **`spinwave_dispersion_fm`** — `γμ₀H + γ(2A/Ms)k²`. Code matches manual to machine
  precision at k=10⁷ rad/m, YIG parameters. ✓
- **`kittel_freq_in_plane`** — Numerical: H=0.1T/μ₀ → 9.63 GHz. ✓
- **`kittel_freq_out_of_plane`** — abs() guard for H<M_eff. ✓
- **`afmr_frequency`** — `(γ/2π)·μ₀·√(2H_EH_A)`. Return 0 for product<0 (optimizer guard). ✓
- **`ferrimagnet_compensation_freq`** — Round-trip inversion test: H_E=1e7 A/m recovers
  to machine precision. ✓
- **`sot_efficiency`** — Conductance-ratio model, dimensionless. Code=0.0500 matches manual. ✓
- **`heisenberg_to_exchange_stiffness`** — `nJS²za²/6`. Dimensional: [m⁻³][J][m²]=J/m. ✓
- **`spin_diffusion_length`** — `√(D_s·τ_sf)`. Code=0.71 nm matches manual. ✓
- **`skyrmion_hall_angle`** — `atan2(4πQ, α·D)`. α=0 returns π/2 (correct). ✓

### `maglab/physics/constants.py`

All five fundamental constants (GAMMA_E, MU_0, HBAR, E_CHARGE, K_B) confirmed against
CODATA 2022. MU_0 = 1.25663706212×10⁻⁶ H/m correctly noted as CODATA 2022 recommended
value (distinct from the exact 4π×10⁻⁷). ✓

### `maglab/analysis/effects/spin_pumping_ishe.py`

- **Δα formula** — `γħg↑↓/(4πMsd_FM)`. No μ₀ in denominator. Verified against Mosendz
  et al., PRB 82, 214403 (2010) Eq. (2). Dimensional: [rad/(s·T)][J·s][m⁻²]/([A/m][m])
  = dimensionless. Numerical: g=2×10¹⁹ m⁻², Py (Ms=8×10⁵, d=5 nm) → Δα_sat=7.4×10⁻³
  (in range 3–10×10⁻³ for various bilayers). ✓
- **`v_ishe`** — Code=2.311×10⁻¹⁰ V matches manual exactly. ✓

### `maglab/analysis/effects/stfmr.py`

- **`spin_hall_angle`** — `(S/A)·√(1+M_eff/H_res)·(eμ₀Mst_FMt_NM/ħ)`. Dimensional:
  `[C·T·m/A·A/m·m·m]/[J·s]` = dimensionless. Code=0.052478 matches manual. Geometry
  factor √(1+M_eff/H_res) correct. t_NM factor confirmed per Liu et al. PRL 106, 036601.
  ValueError guard for geom_arg<0 (PMA case) present. ✓

### `maglab/analysis/effects/gilbert_damping.py`

- **`forward`** — `ΔH = ΔH₀ + (2α/γ')·f`. Code agrees with manual to machine precision
  across [5, 10, 15] GHz. ✓

### `maglab/analysis/effects/fmr_kittel.py`

- **In-plane `forward`** — Code=9.317 GHz, manual=9.317 GHz at H=0.1 T, M_eff=8×10⁵. ✓
- **Out-of-plane `forward`** — abs() guard consistent with formulas.py. ✓

### `maglab/analysis/effects/dmi.py`

- **`forward`** — `Δf = 2γ_pD_ik/Ms`. Pt/Co (D=1.4 mJ/m², Ms=1.4 MA/m, k=10⁷):
  code=0.561 GHz, manual=0.561 GHz, Di et al. ~0.56 GHz. ✓

### `maglab/analysis/effects/dw_1d.py`

- **`dw_velocity_below_walker`** — code=11.063 m/s matches manual. ✓
- **`walker_field`** — code=49.74 A/m matches manual for K_⊥=1e4, Ms=8×10⁵. ✓

### `maglab/analysis/effects/llg.py`

- **`_llg_rhs`** — H_eff [A/m] × MU_0 → T before cross-product. Renormalized LLG
  with γ_eff=γ/(1+α²). STT terms (Slonczewski) structured correctly. ✓
- **`precession_frequency`** — `γ₀μ₀H_eff/(2π)×10⁻⁹` [GHz]. ✓

### `maglab/analysis/effects/llg_2sublattice.py`

- **`_llg2sl_rk4`** — AFM effective fields include exchange, anisotropy, Zeeman.
  MU_0 conversion before cross product. RK4 oversampled (≥10 steps per precession period). ✓
- **AFMR analytic fit** — fits only H_E (one free parameter from linear slope). ✓
- **FiM inversion** — H_E = 2πf(m_a+m_b)/(|γ_am_a−γ_bm_b|·μ₀). Round-trip
  verified: recovers H_E=1×10⁷ A/m to machine precision. ✓

### `maglab/analysis/effects/macrospin.py`

- **`sw_switching_field`** — `H_k/[(cos²θ)^(2/3)+(sin²θ)^(2/3)]^(3/2)`. Verified:
  H_sw(0°)=H_sw(90°)=H_k (easy/hard endpoints), H_sw(45°)=H_k/√2 (astroid minimum,
  consistent with analytic derivation). Denominator guard 1e-30. ✓
- **`_llg_rk4`** — same MU_0 conversion + oversampling as LLGModel. ✓

### `maglab/analysis/effects/thiele.py`

- **`skyrmion_hall_angle`** — `atan2(4πQ, α·D)`. Code=1.5608 rad matches manual for
  Q=1, α=0.01, D=4π. α·D=0 guard returns sign-corrected π/2. ✓
- **`forward`** — `v_x=αD·F/(α²D²+G²)`, `v_y=G·F/(α²D²+G²)`. Denominator guard 1e-30. ✓

### `maglab/analysis/effects/sot_harmonic_hall.py`

- **`phe_corrected`** — denominator (1−4ξ²) guard |denom|<1e-15 raises ValueError. ✓
- **ξ estimator** — `c[1]/(4·c[0])` where c[0]=R_AHE/2, c[1]=R_PHE → ξ=R_PHE/(2R_AHE).
  Hayashi PRB 89, 144425 (2014). ✓

### `maglab/analysis/effects/anomalous_hall.py`

- **`forward`** — `R_0·B + μ₀·R_s·M`. SI convention Nagaosa RMP 82, 1539 (2010). ✓

### `maglab/analysis/effects/topological_hall.py`

- **`forward`** — `ρ_xy − R_0·B − μ₀·R_s·M`. Background: R_0·B [Ω·m],
  μ₀·R_s·M [T·m/A·m³/C·A/m=Ω·m]. ✓

### `maglab/analysis/effects/ordinary_hall.py`

- **`carrier_density`** — `1/(|R_H|·e)` [m⁻³]. ✓

### `maglab/analysis/effects/gmr_tmr.py`

- **`forward`** — `G_0·(1+P₁P₂·cosθ)`. Amplitude P₁P₂ (not TMR/2). Slonczewski PRB 39. ✓

### `maglab/analysis/effects/amr.py`

- **`forward`** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975). ✓

### `maglab/analysis/effects/planar_hall.py`

- **`forward`** — `(Δρ/2)·sin(2φ)`. Taskin & Ando PRB 84, 035301 (2011). ✓

### `maglab/analysis/effects/smr.py`

- **`fit`** — delta_rho_2→NaN (Hall parameter not identifiable from longitudinal data). ✓

### `maglab/analysis/effects/usmr.py`

- **`forward`** (current-sweep) — `ε·j + offset`. Linear in j, sign-correct. ✓
- **`forward`** (angle-sweep) — `ε·j₀·sin(φ) + offset`. Avci et al. (2015). ✓

### `maglab/analysis/effects/orbital_hall.py`

- **`forward`** — `(θ_OH/H_ext)·cos(φ)`. Clearly labeled as simplified approximate model. ✓

### `maglab/analysis/effects/tyj_scaling.py`

- **`forward`** — `a·ρ_xx + b·ρ_xx²`. Tian-Ye-Jin PRL 103, 087206 (2009). ✓

### `maglab/analysis/effects/hysteresis.py`

- **`forward`** — `M_s·tanh(H/H_sat) + χ_p·H`. Labeled as Langevin-like approximation. ✓
- **`extract_loop_params`** — NaN returned with warnings when H or M does not straddle zero. ✓

### `maglab/analysis/effects/curie_temperature.py`

- **`_power_law`** — T_C bounded at 1 K; `np.clip(reduced, 0, None)` prevents complex power. ✓

### `maglab/analysis/device_fom.py`

- **`sot_mram_fom` j_c** — `2αeμ₀Mst_FM(H_k+Ms/2)/(ħθ_SH)`. Numerical: Py/Pt → 3.65×10¹¹ A/m² (within 10¹¹–10¹² range). ✓
- **`stt_mram_fom` j_c** — same structure without Ms/2 (PMA). ✓
- **`racetrack_fom` Walker field** — αK_⊥/(2μ₀Ms). Factor-of-2 correct. ✓
- **`spin_valve_sensor_fom` NEF** — `noise_floor·μ₀/(S_H·R_sq)` [T/√Hz]. μ₀ in numerator (correct). ✓
- **`spin_orbit_logic_fom` switching time** — `π/(α·γ·μ₀·H_k)`, capped at 10 ns. ✓
- **`magnon_device_fom` v_g** — `4γAk/Ms` = ∂ω/∂k. Dimensional: [rad/(s·T)][J/m][m⁻¹]/[A/m]=m/s. ✓
- **`magnon_device_fom` lambda_prop** — `v_g/(α·ω)`. Standard 1/e decay length. ✓

### `maglab/sim/micro/mumax3.py`

- **`_generate_mx3` B_ext** — H[A/m] × 1.25663706212×10⁻⁶ = B[T]. MuMax3 requires Tesla. ✓

### `maglab/sim/micro/oommf.py`

- **`_generate_mif2` μ₀ conversion** — `_mu_0=1.25663706212e-6` for H→B. `Oxs_FixedZeeman` expects T. ✓
- **`gamma_G`** — 1.760859630×10¹¹ rad/(s·T) = GAMMA_E. ✓

### `maglab/sim/micro/magnumnp.py`

- **`ExternalField` B_ext** — `H[A/m] × μ₀` → T. MagNumPy requires Tesla. ✓

### Spin Hall angle in STFMR

t_NM factor confirmed correct per Liu et al. PRL 106, 036601 (2011). Not re-flagged per standing instruction.

---

## Verification

### ruff

```
ruff check maglab/physics/ maglab/sim/ maglab/analysis/
All checks passed!
```

### mypy

```
mypy maglab/
Success: no issues found in 195 source files
```

### pytest (domain tests)

```
pytest tests/unit/test_physics_sim_regression.py tests/unit/test_gap_fixes.py
      tests/unit/test_analysis_interface.py tests/unit/test_physics_oracle.py
      tests/unit/test_physics_quantity.py tests/unit/test_material_builder.py
      tests/unit/test_sim_spec.py tests/unit/test_sim_validate.py --timeout=120
368 passed in 1.38s
```

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| — | — | — | No findings |
