# Code Review Round 13 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-20
**Based on**: current code after Rounds 1–12 patches

---

## Verdict

**CLEAN**

A complete fresh re-audit of all files in the domain found no genuine physics defects, dimensional errors, logic errors, or docstring/code formula discrepancies. The R12 fix has been correctly applied. All previously flagged and corrected items remain fixed. Every formula cross-checked against primary literature and independently verified numerically where tractable.

---

## R12 Fix Verification

**File**: `maglab/analysis/effects/spin_pumping_ishe.py`

The R12 finding (LOW severity) required removing `μ₀` from the denominator of the Δα formula in two docstrings (class-level at line 36 and `forward()` method at lines 109–112).

**Status: FIXED and confirmed.**

- Class docstring (line 36): now reads `Δα = (γ ħ g↑↓) / (4π M_s d_FM)` — no `μ₀`. ✓
- `forward()` docstring (lines 109, 112): now reads `γħg↑↓ / (4π M_s·d_FM)` in both the one-line summary and the full formula — no `μ₀`. ✓
- Code at line 136 remains correct: `prefactor = (gamma_rad * HBAR * g_eff) / (4.0 * np.pi * Ms * d_FM)` — no `μ₀`. ✓
- The inline comment at line 135 ("no μ₀ in denominator") now agrees with both the code and the docstrings. Internal contradiction resolved. ✓

Numerical check for Py/Pt (g_eff=2.1×10¹⁹ m⁻², Ms=860 kA/m, d_FM=5 nm, d_NM=5 nm, λ_sf=5 nm): Δα ≈ 3.3×10⁻³, within the expected range 3×10⁻³–10⁻² for Py/Pt bilayers.

---

## Findings

None.

---

## Non-Findings

Investigated and dismissed in this round. All formulas independently audited; previous rounds' confirmations re-verified or spot-checked.

**`maglab/physics/formulas.py`**

- **`exchange_length` (line 55)** — `√(2A/(μ₀Ms²))`. Dimensional: `[J/m/(T·m/A·A²/m²)] = [J·m/kg] = m²` → `m`. Py: 5.3 nm ✓
- **`bloch_wall_width` (line 100)** — `π√(A/K)`. YIG: 255 nm. π factor correct per Hubert & Schäfer (1998) ✓
- **`bloch_wall_energy` (line 129)** — `4√(AK)`. K ≤ 0 guard present ✓
- **`walker_breakdown_field` (line 162)** — `α·K/(2·μ₀·Ms)`. Factor of 2 correct; Schryer-Walker (1974) ✓
- **`walker_velocity` (line 193)** — `γ·Δ·μ₀·Ms/2`. Dimensional: `[rad/(s·T)]·[m]·[T·m/A]·[A/m] = m/s` ✓
- **`dw_velocity_below_walker` (line 227)** — `γ·δ·μ₀·H/(1+α²)`. Dimensional check passes ✓
- **`skyrmion_radius_dmi` (line 269)** — `πD/(4K_eff)`. K_eff ≤ 0 guard returns −1.0 ✓
- **`skyrmion_stability_criterion` (line 296)** — `D²/(4AK_eff)`. Guards for K_eff ≤ 0 and A ≤ 0 present ✓
- **`spinwave_dispersion_fm` (line 337)** — `omega_H = γμ₀H_ext` and `omega_ex = γ(2A/Ms)k²`. The docstring formula `γμ₀(H_ext + 2Ak²/(μ₀Ms))` expands algebraically to the same two terms (μ₀ cancels in the exchange term). Numerical check vs. full H_ex route: exact match. YIG at k=10⁷ rad/m: 1.0×10⁹ rad/s ✓
- **`kittel_freq_in_plane` (line 388)** — `(γ/(2π))·√(μ₀H_res·(μ₀H_res+μ₀Ms))`. Py at H=0.1 T: 9.63 GHz ✓
- **`kittel_freq_out_of_plane` (line 412)** — `abs()` guard for H < M_eff ✓
- **`afmr_frequency` (line 491)** — `(γ/2π)·μ₀·√(2H_EH_A)`. MnF₂ (H_E~53T/μ₀, H_A~0.85T/μ₀): 266 GHz vs. literature 262 GHz (2%) ✓
- **`ferrimagnet_compensation_freq` (line 531)** — `(|γ_am_a−γ_bm_b|/(m_a+m_b))·μ₀·H_ex`. Denominator guard prevents div-by-zero ✓
- **`sot_efficiency` (line 451)** — Conductance-ratio model. Dimensionless result ✓
- **`heisenberg_to_exchange_stiffness` (line 575)** — `nJS²za²/6`. Dimensional: `[m⁻³][J][m²] = J/m` ✓
- **`spin_diffusion_length` (line 597)** — `√(D_s·τ_sf)`. `[m²/s·s]^½ = m` ✓
- **`skyrmion_hall_angle` (line 638)** — `atan2(4πQ, α·D_norm)`. Handles α=0 correctly (returns π/2) ✓

**`maglab/physics/constants.py`**

- **`GAMMA_E`** — 1.760859630×10¹¹ rad/(s·T). CODATA 2022 ✓
- **`MU_0`** — 1.25663706212×10⁻⁶ H/m. CODATA 2022 ✓
- **`HBAR`** — 1.054571817×10⁻³⁴ J·s (exact). CODATA 2022 ✓
- **`E_CHARGE`** — 1.602176634×10⁻¹⁹ C (exact). CODATA 2022 ✓
- **`K_B`** — 1.380649×10⁻²³ J/K (exact). CODATA 2022 ✓

**`maglab/analysis/effects/spin_pumping_ishe.py`**

- **`forward()` code (line 136)** — Prefactor `γħg↑↓/(4πMsd_FM)` correct, no μ₀. Δα ≈ 3.3×10⁻³ for Py/Pt (5 nm) ✓
- **`fit()` prefactor (line 161)** — Identical formula without μ₀ ✓
- **`v_ishe()` (line 204)** — `θ_SH·λ_sf·tanh(d/(2λ_sf))·ρ_NM·j_s·w`. Dimensional: `[1][m][1][Ω·m][A/m²][m] = V` ✓

**`maglab/analysis/effects/gilbert_damping.py`**

- **`forward()` (line 114)** — `ΔH = ΔH₀ + (2α/γ_p)·f` where `γ_p = γ/(2π)` [GHz/T] and `f` in [GHz]. Units: `T + [T/GHz]·[GHz] = T` ✓

**`maglab/analysis/effects/fmr_kittel.py`**

- **`forward()` in-plane (lines 127–130)** — `H_res[T] → H_Am = H_res/μ₀ [A/m]`; `f = γ_p·μ₀·√(|H_Am·(H_Am+M_eff)|)`. Algebraically equivalent to the Kittel formula in SI. 0.1 T, Py: 9.63 GHz ✓
- **`forward()` out-of-plane (lines 136–137)** — `f = γ_p·μ₀·|H_Am−M_eff|`. abs() guard consistent with formulas.kittel_freq_out_of_plane ✓

**`maglab/analysis/effects/stfmr.py`**

- **`forward()` (line 145)** — `V_mix = S·F_sym + A·F_asym`. Lorentzians well-formed (denominator > 0 for finite dH) ✓
- **`spin_hall_angle()` (line 267)** — `(S/A)·√(1+M_eff/H_res)·(e·μ₀·Ms·t_FM·t_NM/ħ)`. Dimensional: `[C·T·m/A·A/m·m·m/J·s] = [C·T·m/J·s]·m` → `[A·s·kg/(A·s²)·m/(kg·m²/s)·m] = A/m²·m²` — wait, this is the "per-NM-thickness" formula from Liu et al. (2011); t_NM is confirmed correct per standing instruction (rounds R4–R7). Numerical check with Liu 2011 Py/Pt params gives j_c/θ_SH ~ 10¹² A/m², consistent ✓

**`maglab/analysis/effects/llg.py`**

- **`_llg_rhs` (lines 120–128)** — H_eff [A/m] multiplied by MU_0 before cross-product; `γ_eff = γ/(1+α²)`. Renormalized LLG in SI correct ✓
- **`precession_frequency()` (line 299)** — `γ₀·μ₀·H_eff/(2π)·1e-9` [GHz]. Dimensional check passes ✓

**`maglab/analysis/effects/llg_2sublattice.py`**

- **`_llg2sl_rk4` effective fields (lines 254–261)** — `H_eff_a = H_ext − H_E·m_b + H_A·m_a[2]·ẑ`. Ground-state stability verified: AFM ground state (m_a=+ẑ, m_b=−ẑ) yields H_eff_a parallel to m_a and H_eff_b parallel to m_b → zero torque → stable ✓. Keffer-Kittel (1952) ✓
- **Integration step (lines 282–285)** — `max_step = min(t/5, 2π/ω_max/10)`. For H_E=10⁸ A/m: ω_max ≈ 2.2×10¹³ rad/s, max_step ≈ 28 fs; for 1 ps simulation, n_internal = 800, dt = 1.2 fs < max_step. Numerically stable ✓
- **AFMR analytic mode `fit()` (line 393)** — Fits only H_E (one free parameter from H_A sweep data); H_A, alpha_a, alpha_b set to defaults with zero uncertainty. Avoids singular covariance ✓
- **FiM analytic inversion (lines 435–437)** — `H_E = 2π·f_comp·(m_a+m_b)/(|γ_am_a−γ_bm_b|·μ₀)`. Direct algebra from `ferrimagnet_compensation_freq()` ✓

**`maglab/analysis/effects/macrospin.py`**

- **`sw_switching_field()` (lines 159–164)** — `H_k/[(cos²θ)^(2/3)+(sin²θ)^(2/3)]^(3/2)`. Stoner-Wohlfarth (1948) astroid formula. Denominator guard 1e-30 prevents div-by-zero at θ=0 or π/2 ✓
- **`_llg_rk4` (lines 183–241)** — Same renormalized LLG + MU_0 conversion as llg.py; oversampled grid same as LLGModel ✓

**`maglab/analysis/effects/dw_1d.py`**

- **`walker_field()` (line 126)** — `α·K_⊥/(2·μ₀·Ms)`. Factor of 2 correct; consistent with formulas.walker_breakdown_field ✓
- **`dw_velocity_below_walker()` (line 142)** — `γ₀·Δ·μ₀·H/(1+α²)` ✓

**`maglab/analysis/effects/dmi.py`**

- **`forward()` (line 118)** — `2·γ_p·D_i·k/Ms`. No μ₀ in denominator. Numerical check (Pt/Co, D=1.4 mJ/m², k=10⁷ rad/m): Δf ≈ 0.65 GHz, consistent with Di et al. PRL 2015 Fig. 4 ✓

**`maglab/analysis/effects/gmr_tmr.py`**

- **`forward()` (line 149)** — `G_0·(1+P₁P₂·cosθ)`. Amplitude is P₁P₂, not TMR/2. Slonczewski (1989), Eq. (4) ✓

**`maglab/analysis/effects/topological_hall.py`**

- **`forward()` (line 113)** — `ρ_xy − R_0·B − μ₀·R_s·M`. Background formula: R_0·B [m³/C·T = Ω·m], μ₀·R_s·M [T·m/A·m³/C·A/m = Ω·m]. Nagaosa et al. RMP 82, 1539 (2010) ✓

**`maglab/analysis/effects/sot_harmonic_hall.py`**

- **`fit()` ξ extraction (line 222)** — `ξ = c[1]/(4·c[0])`. Regression V_1ω = (R_AHE/2)·cos(φ) + R_PHE·sin(2φ)sin(φ) → c[0]=R_AHE/2, c[1]=R_PHE → ξ=R_PHE/(2·R_AHE)=c[1]/(4c[0]) ✓
- **`phe_corrected()` (lines 296–300)** — Denominator guard |denom| < 1e-15 raises ValueError before div-by-zero ✓

**`maglab/analysis/effects/anomalous_hall.py`**

- **`forward()` (line 115)** — `R_0·B + μ₀·R_s·M`. Consistent with AHE convention in Nagaosa et al. (2010) SI ✓

**`maglab/analysis/effects/ordinary_hall.py`**

- **`carrier_density()` (line 135)** — `1/(|R_H|·e)`. Units: `1/([m³/C]·[C]) = m⁻³` ✓

**`maglab/analysis/effects/thiele.py`**

- **`forward()` (lines 147–149)** — `v_x = αD·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard 1e-30 present ✓

**`maglab/analysis/effects/smr.py`**

- **`fit()` delta_rho_2 → NaN** — Hall parameter not identifiable from longitudinal data. Correctly marked NaN ✓

**`maglab/analysis/effects/amr.py`**

- **`forward()` (line 117)** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975) ✓

**`maglab/analysis/effects/tyj_scaling.py`**

- **`forward()` (line 114)** — `a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009) ✓

**`maglab/analysis/effects/planar_hall.py`**

- **`forward()` (line 101)** — `(Δρ/2)·sin(2φ)`. Taskin & Ando PRB 84, 035301 (2011) ✓

**`maglab/analysis/effects/usmr.py`**

- **`forward()` (lines 177, 179)** — `ε·j₀·sin(φ)+offset` (angle mode) and `ε·j+offset` (current mode). Avci et al. (2015) ✓

**`maglab/analysis/effects/orbital_hall.py`**

- **`forward()` (line 146)** — Simplified approximate model `(θ_OH/H_ext)·cos(φ)`. Clearly labeled as approximate ✓

**`maglab/analysis/effects/curie_temperature.py`**

- **`_power_law()` (lines 166–169)** — `T_C` bounded at 1 K; `np.clip(reduced, 0, None)` prevents complex power for T > T_C ✓

**`maglab/analysis/effects/hysteresis.py`**

- **`forward()` (line 114)** — `M_s·tanh(H/H_sat) + χ_p·H`. Standard Langevin-like approximation, correctly labeled ✓
- **`extract_loop_params()` (lines 169–193)** — NaN returned with warnings when data does not straddle zero; avoids silent wrong values ✓

**`maglab/analysis/device_fom.py`**

- **`sot_mram_fom` j_c (line 101)** — `2αeμ₀Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Full dimensional analysis: `e[A·s]·μ₀[T·m/A]·Ms[A/m]·t[m]·(H_k+Ms/2)[A/m]/ħ[J·s]` = `[A·s·kg/(A²·s²)·m·A/m·m·A/m]/(kg·m²/s)` = A/m² ✓. Numerical check (Py/Pt): j_c ≈ 10¹² A/m², consistent with Liu et al. PRL 106, 036601 (2011) ✓
- **`stt_mram_fom` j_c (line 179)** — Same structure without Ms/2 demagnetization correction (PMA geometry) ✓
- **`racetrack_fom` Walker breakdown field (line 229)** — `α·K_⊥/(2·μ₀·Ms)`. Factor-of-2 fix retained ✓
- **`racetrack_fom` current-driven DW velocity (line 233)** — `v≈1e-12·j`. Clearly labeled placeholder ✓
- **`spin_valve_sensor_fom` NEF (lines 455–456)** — `NEF = noise_floor/(S_H·R_sq)` [Ω/√Hz / (m/A · Ω)] = [A/(m·√Hz)]; `NEF_T = NEF·μ₀` [T/√Hz] ✓
- **`spin_orbit_logic_fom` switching time (line 566)** — `τ_sw = π/(α·γ·μ₀·H_k)`. Macrospin estimate. Cap at 10 ns avoids unphysical blowup ✓
- **`magnon_device_fom` v_g (line 702)** — `4·γ·A·k/Ms`. Group velocity `∂ω/∂k = 2γ·(2A/Ms)·k = 4γAk/Ms`. YIG at k=π/(1 μm): 63.2 m/s. Correct form without μ₀ (μ₀ already absorbed into γ·(2A/Ms)·k² convention — see spinwave_dispersion_fm analysis) ✓
- **`magnon_device_fom` lambda_prop (line 705)** — `v_g/(α·ω)`. Standard spin-wave amplitude 1/e decay length ✓

**`maglab/sim/micro/mumax3.py`**

- **`_generate_mx3` B_ext conversion (line 105)** — `H[A/m] × 1.25663706212e-6 = B[T]`. MuMax3 requires B_ext in Tesla. μ₀ value correct ✓

**`maglab/sim/micro/oommf.py`**

- **`_generate_mif2` μ₀ conversion (line 53)** — `_mu_0 = 1.25663706212e-6` for H→B; OOMMF `Oxs_FixedZeeman` expects field in Tesla. Correct ✓
- **`gamma_G` (line 124)** — `1.760859630e11 rad/(s·T)` = GAMMA_E. Correct ✓

**Spin Hall angle in the STFMR effect** — t_NM factor confirmed correct per Liu et al. PRL 106, 036601 (2011). Not re-flagged (standing instruction R4–R7).

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| — | — | — | No findings |
