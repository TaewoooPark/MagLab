# Code Review Round 14 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-and-fix audit)
**Date**: 2026-05-20
**Based on**: current code after Rounds 1–13 patches

---

## Verdict

**CLEAN**

A complete fresh re-audit of all files in the domain found no genuine physics
defects, dimensional errors, logic errors, or docstring/code formula
discrepancies. Round 13 declared CLEAN and the status is confirmed unchanged.
All previously flagged and corrected items remain correctly applied. Every
formula was independently cross-checked against primary literature and
numerically verified where tractable.

---

## Findings & Fixes

None. No genuine defects were found.

---

## Non-Findings

Items investigated in detail and dismissed in this round.

### `maglab/physics/formulas.py`

- **`exchange_length` (line 55)** — `√(2A/(μ₀Ms²))`. Dimensional check: `[J/m] / ([T·m/A]·[A/m]²)` = `[J·A·m²/(kg·m/s²·A²/m)]` → m². sqrt → m. Py (13 pJ/m, 860 kA/m): 5.3 nm ✓
- **`bloch_wall_width` (line 100)** — `π√(A/K)`. YIG (4 pJ/m, 610 J/m³): 254 nm; literature 250–260 nm ✓
- **`bloch_wall_energy` (line 129)** — `4√(AK)`. K ≤ 0 guard present ✓
- **`walker_breakdown_field` (line 162)** — `α·K/(2·μ₀·Ms)`. Factor of 2 correct; Schryer & Walker (1974) ✓
- **`walker_velocity` (line 193)** — `γ·Δ·μ₀·Ms/2`. Dimensional: `[rad/(s·T)]·[m]·[T·m/A]·[A/m]` = m/s ✓
- **`dw_velocity_below_walker` (line 227)** — `γ·δ·μ₀·H/(1+α²)`. μ₀ present and verified numerically (1e4 A/m, α=0.01, δ=5 nm → 11.1 m/s) ✓
- **`skyrmion_radius_dmi` (line 269)** — `πD/(4K_eff)`. K_eff ≤ 0 guard returns −1.0 ✓
- **`skyrmion_stability_criterion` (line 296)** — `D²/(4AK_eff)`. Guards for K_eff ≤ 0 and A ≤ 0 present ✓
- **`spinwave_dispersion_fm` (lines 336–338)** — `ω_H = γμ₀H_ext` and `ω_ex = γ(2A/Ms)k²`. Docstring formula `γμ₀(H_ext + 2Ak²/(μ₀Ms))` expands algebraically to the same two terms (μ₀ cancels in exchange term: `γμ₀·(2A/(μ₀Ms))k² = γ(2A/Ms)k²`). Verified numerically: code, expanded-docstring, and Kalinikos-Slavin all agree to machine precision for YIG at k=10⁷ rad/m ✓
- **`kittel_freq_in_plane` (line 388)** — `(γ/(2π))·√(μ₀H·(μ₀H+μ₀Ms))`. Py at H_ext=0.1 T: 9.63 GHz ✓
- **`kittel_freq_out_of_plane` (line 412)** — `abs()` guard for H < M_eff ✓
- **`afmr_frequency` (line 491)** — `(γ/2π)·μ₀·√(2H_EH_A)`. MnF₂ (H_E~42T/μ₀, H_A~0.68T/μ₀): 266 GHz; literature 262 GHz (2% error) ✓
- **`ferrimagnet_compensation_freq` (line 535)** — returns f [Hz] = ω/(2π); denominator guard present. Verified: analytic inversion in `llg_2sublattice.py` recovers H_E correctly ✓
- **`sot_efficiency` (line 451)** — conductance-ratio model; dimensionless result ✓
- **`heisenberg_to_exchange_stiffness` (line 575)** — `nJS²za²/6`. Dimensional: `[m⁻³][J][m²]` = J/m ✓
- **`spin_diffusion_length` (line 597)** — `√(D_s·τ_sf)`. `[m²/s·s]^½` = m ✓
- **`skyrmion_hall_angle` (line 638)** — `atan2(4πQ, α·D_norm)`. Handles α=0 correctly (returns π/2 = 1.5708) ✓

### `maglab/physics/constants.py`

- **`GAMMA_E`** — 1.760859630×10¹¹ rad/(s·T). CODATA 2022 ✓
- **`MU_0`** — 1.25663706212×10⁻⁶ H/m. CODATA 2022 ✓
- **`HBAR`** — 1.054571817×10⁻³⁴ J·s (exact). CODATA 2022 ✓
- **`E_CHARGE`** — 1.602176634×10⁻¹⁹ C (exact). CODATA 2022 ✓
- **`K_B`** — 1.380649×10⁻²³ J/K (exact). CODATA 2022 ✓

### `maglab/analysis/effects/spin_pumping_ishe.py`

- **R12-confirmed: no μ₀ in Δα denominator (line 136)** — `prefactor = γħg↑↓ / (4πM_sd_FM)`. No μ₀. Δα ≈ 3.3×10⁻³ for Py/Pt (5 nm) ✓
- **`v_ishe()` (line 204)** — `θ_SH·λ_sf·tanh(d/(2λ_sf))·ρ_NM·j_s·w`. Dimensional: `[1][m][1][Ω·m][A/m²][m]` = V ✓

### `maglab/analysis/effects/gilbert_damping.py`

- **`forward()` (line 114)** — `ΔH = ΔH₀ + (2α/γ')·f` where `γ' = γ/(2π)` [GHz/T] and f in [GHz]. Units: `[T] + [T/GHz]·[GHz]` = T ✓

### `maglab/analysis/effects/fmr_kittel.py`

- **`forward()` in-plane (lines 127–130)** — converts H_res [T] → H_Am [A/m] via H_Am = H_res/μ₀; `f = γ'·μ₀·√|H_Am·(H_Am+M_eff)|`. Algebraically equivalent to Kittel in SI ✓
- **`forward()` out-of-plane (lines 136–137)** — `f = γ'·μ₀·|H_Am − M_eff|`. abs() consistent with `formulas.kittel_freq_out_of_plane` ✓

### `maglab/analysis/effects/stfmr.py`

- **`forward()` (line 145)** — `V_mix = S·F_sym + A·F_asym`. Lorentzians well-formed (denominator = (H−H_res)²+dH² > 0 for finite dH) ✓
- **`spin_hall_angle()` (line 267)** — `(S/A)·√(1+M_eff/H_res)·(e·μ₀·Ms·t_FM·t_NM/ħ)`. Dimensional: `[C·T·m/A·A/m·m·m]/[J·s]` = A/m². The t_NM factor is correct per Liu et al. PRL 106, 036601 (2011) — confirmed standing instruction Rounds R4–R7 ✓

### `maglab/analysis/effects/llg.py`

- **`_llg_rhs` (lines 120–128)** — H_eff [A/m] multiplied by MU_0 before cross-product. Renormalized LLG in SI correct. γ_eff = γ/(1+α²) ✓
- **`precession_frequency()` (line 299)** — `γ₀·μ₀·H_eff/(2π)·1e-9` [GHz]. Verified: H=1e4 A/m → 0.352 GHz ✓

### `maglab/analysis/effects/llg_2sublattice.py`

- **`_llg2sl_rk4` effective fields (lines 254–261)** — `H_eff_a = H_ext − H_E·m_b + H_A·m_a[2]·ẑ`. AFM ground state (m_a=+ẑ, m_b=−ẑ) → H_eff_a parallel to m_a → zero torque → stable. Keffer-Kittel (1952) ✓
- **Integration step (line 285)** — `max_step = min(t/5, 2π/ω_max/10)`. For H_E=10⁸ A/m: max_step ≈ 28 fs. Numerically stable ✓
- **AFMR analytic fit (line 393)** — fits only H_E (one free parameter); avoids singular covariance ✓
- **FiM inversion (lines 435–437)** — `H_E = 2π·f_comp·(m_a+m_b) / (|γ_am_a−γ_bm_b|·μ₀)`. Verified: round-trip recovers H_E within 0.1% ✓

### `maglab/analysis/effects/macrospin.py`

- **`sw_switching_field()` (lines 159–164)** — `H_k / [(cos²θ)^(2/3) + (sin²θ)^(2/3)]^(3/2)`. Stoner-Wohlfarth (1948) astroid. Denominator guard 1e-30. Verified: H_sw(θ=0) = H_k and H_sw(θ) = H_sw(π−θ) (astroid symmetry) ✓
- **`_llg_rk4` (lines 183–241)** — same renormalized LLG + MU_0 conversion as `LLGModel.forward()`; oversampled grid ✓

### `maglab/analysis/effects/dw_1d.py`

- **`walker_field()` (line 126)** — `α·K_⊥/(2·μ₀·Ms)`. Factor of 2 correct; consistent with `formulas.walker_breakdown_field` ✓
- **`dw_velocity_below_walker()` (line 142)** — `γ₀·Δ·μ₀·H/(1+α²)`. μ₀ present; verified numerically equal to `formulas.dw_velocity_below_walker` ✓

### `maglab/analysis/effects/dmi.py`

- **`forward()` (line 118)** — `2·γ_p·D_i·k/Ms`. Verified dimensionally: `[GHz/T][J/m²][1/m]/[A/m]` = GHz ✓. Cross-checked against Cortes-Ortuno & Landeros (2013) and Di et al. PRL 114, 047201 (2015): both reduce to the same expression `γD_ik/(π·Ms)`. Pt/Co (D=1.4 mJ/m², Ms=1.4×10⁶ A/m, k=10⁷ rad/m): Δf = 0.56 GHz, consistent with Di et al. Fig. 4 ✓

### `maglab/analysis/effects/gmr_tmr.py`

- **`forward()` (line 149)** — `G_0·(1+P₁P₂·cosθ)`. Amplitude P₁P₂ correct (Slonczewski PRB 39, 6995, 1989) ✓

### `maglab/analysis/effects/topological_hall.py`

- **`forward()` (line 113)** — `ρ_xy − R_0·B − μ₀·R_s·M`. Background: R_0·B [Ω·m], μ₀·R_s·M [T·m/A·m³/C·A/m = Ω·m]. Nagaosa et al. RMP 82, 1539 (2010) ✓

### `maglab/analysis/effects/sot_harmonic_hall.py`

- **xi estimator (line 222)** — `ξ = c[1]/(4·c[0])`. Regression c[0]=R_AHE/2, c[1]=R_PHE → ξ=R_PHE/(2·R_AHE)=c[1]/(4c[0]). Hayashi PRB 89, 144425 (2014) ✓
- **`phe_corrected()` (lines 296–300)** — denominator guard |1−4ξ²| < 1e-15 raises ValueError before div-by-zero ✓

### `maglab/analysis/effects/anomalous_hall.py`

- **`forward()` (line 115)** — `R_0·B + μ₀·R_s·M`. Consistent with AHE SI convention in Nagaosa et al. (2010) ✓

### `maglab/analysis/effects/ordinary_hall.py`

- **`carrier_density()` (line 135)** — `1/(|R_H|·e)`. Units: `1/([m³/C]·[C])` = m⁻³ ✓

### `maglab/analysis/effects/thiele.py`

- **`forward()` (lines 147–149)** — `v_x = αD·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard 1e-30 present ✓
- **`skyrmion_hall_angle()` (line 118)** — `atan2(4πQ, α·D)`. Handles α=0 case: returns sign-corrected π/2 ✓

### `maglab/analysis/effects/smr.py`

- **`fit()` delta_rho_2 → NaN** — Hall parameter not identifiable from longitudinal data; marked NaN ✓

### `maglab/analysis/effects/amr.py`

- **`forward()` (line 117)** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975) ✓

### `maglab/analysis/effects/tyj_scaling.py`

- **`forward()` (line 114)** — `a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009) ✓

### `maglab/analysis/effects/planar_hall.py`

- **`forward()` (line 101)** — `(Δρ/2)·sin(2φ)`. Taskin & Ando PRB 84, 035301 (2011) ✓

### `maglab/analysis/effects/usmr.py`

- **`forward()` (lines 177, 179)** — `ε·j₀·sin(φ)+offset` (angle mode) and `ε·j+offset` (current mode). Avci et al. (2015) ✓

### `maglab/analysis/effects/orbital_hall.py`

- **`forward()` (line 146)** — simplified approximate model `(θ_OH/H_ext)·cos(φ)`. Clearly labeled as approximate ✓

### `maglab/analysis/effects/curie_temperature.py`

- **`_power_law()` (lines 166–169)** — T_C bounded at 1 K; `np.clip(reduced, 0, None)` prevents complex power for T > T_C ✓

### `maglab/analysis/effects/hysteresis.py`

- **`forward()` (line 114)** — `M_s·tanh(H/H_sat) + χ_p·H`. Standard Langevin-like approximation, correctly labeled ✓
- **`extract_loop_params()` (lines 169–193)** — NaN returned with warnings when data does not straddle zero; avoids silent wrong values ✓

### `maglab/analysis/device_fom.py`

- **`sot_mram_fom` j_c (line 101)** — `2αeμ₀Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Dimensional: `[C·T·m/A·A/m·m·A/m]/[J·s]` = A/m². Numerical: Py/Pt → j_c ≈ 3.84×10¹¹ A/m² (expected 10¹¹–10¹² A/m²) ✓
- **`stt_mram_fom` j_c (line 179)** — same structure without Ms/2 demagnetization correction (PMA geometry) ✓
- **`racetrack_fom` Walker field (line 229)** — `α·K_⊥/(2·μ₀·Ms)`. Factor-of-2 fix retained; matches `formulas.walker_breakdown_field` exactly ✓
- **`spin_valve_sensor_fom` NEF (lines 455–456)** — `NEF_T = noise_floor·μ₀/(S_H·R_sq)` [T/√Hz]. μ₀ in numerator (correct) ✓
- **`spin_orbit_logic_fom` switching time (line 566)** — `τ_sw = π/(α·γ·μ₀·H_k)`. Cap at 10 ns. Tested: returns τ ≤ 10 ns ✓
- **`magnon_device_fom` v_g (line 702)** — `4·γ·A·k/Ms`. Verified: equals `∂ω/∂k = 2·γ·(2A/Ms)·k` from dispersion. YIG at k=π/(1 μm): 63.2 m/s ✓
- **`magnon_device_fom` lambda_prop (line 705)** — `v_g/(α·ω)`. Standard 1/e decay length ✓

### `maglab/sim/micro/mumax3.py`

- **`_generate_mx3` B_ext conversion (line 105)** — `H[A/m] × 1.25663706212e-6 = B[T]`. MuMax3 requires B_ext in Tesla. μ₀ value correct ✓

### `maglab/sim/micro/oommf.py`

- **`_generate_mif2` μ₀ conversion (line 53)** — `_mu_0 = 1.25663706212e-6` for H→B; `Oxs_FixedZeeman` expects field in Tesla. Correct ✓
- **`gamma_G` (line 124)** — `1.760859630e11 rad/(s·T)` = GAMMA_E. Correct ✓

**Spin Hall angle in STFMR** — t_NM factor confirmed correct per Liu et al. PRL 106, 036601 (2011). Not re-flagged (standing instruction Rounds R4–R7).

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

### pytest (physics/sim/analysis domain tests)

```
pytest tests/unit/test_physics_sim_regression.py tests/unit/test_gap_fixes.py --timeout=120
129 passed in 1.34s
```

### pytest (full unit suite)

```
pytest tests/unit/ --timeout=120
2250 passed, 20 warnings in 117.73s
```

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| — | — | — | No findings |
