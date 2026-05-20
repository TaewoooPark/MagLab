# Code Review Round 11 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-20
**Based on**: current code after Rounds 1–10 patches

---

## Verdict

**CLEAN**

Zero findings. The R10 fix is confirmed in place. An independent fresh audit of every file in the domain found no genuine physics defects, unit mismatches, sign errors, dimensional errors, or numerical safety issues. All formulas cross-checked against primary literature and dimensional analysis pass.

---

## R10 Fix Verification

| R10 Finding | Location | Status |
|---|---|---|
| `GMRTMREffect.forward()` and `model_fn` in `fit()` used `(tmr/2)*cos(θ)` as conductance amplitude instead of `P1*P2` (Slonczewski PRB 39, 6995, 1989) | `gmr_tmr.py:149,179` | **FIXED** — Line 149 now reads `return G_0 * (1.0 + P1 * P2 * np.cos(theta))`. Line 179 reads `return G_0 * (1.0 + P1 * P2 * np.cos(x))`. The docstring on `forward()` (lines 132–136) was also updated to explicitly warn against the `TMR/2` mistake and explain the physical reasoning. |

The `tmr_from_polarizations()` static method remains correctly unchanged: it computes the Julliere ratio `2P₁P₂/(1−P₁P₂)` for reporting only, not for the conductance oscillation amplitude.

---

## Findings

*None.*

---

## Non-Findings

Investigated and dismissed (no genuine defect found):

**Verified in this round (fresh audit):**

- **`GMRTMREffect.forward()`/`fit()` (`gmr_tmr.py:149,179`)** — R10 fix confirmed: amplitude is now `P1*P2` per Slonczewski (1989). ✓

- **`spinwave_dispersion_fm` exchange term (`formulas.py:337`)** — `omega_ex = gamma * (2*A/Ms) * k²`. Dimensional analysis: `[rad/(s·T)] × [J/m] / [A/m] × [1/m²]`. With `T = kg/(A·s²)` and `J = kg·m²/s²`, this yields `[rad/s]`. This is the correct Kalinikos-Slavin (1986) exchange term; no `μ₀` factor appears because the exchange effective field `H_ex = 2Ak²/μ₀Ms` multiplied by `γμ₀` gives `γ·2A·k²/Ms`. Numerically: Permalloy at `k = 10⁷ m⁻¹` → `ω_ex = 5.3×10⁸ rad/s = 0.085 GHz`. Physically consistent. ✓

- **`afmr_frequency` (`formulas.py:491`)** — `(γ/2π)·μ₀·√(2·H_E·H_A)`. Dimensional check: `[rad/(s·T)]×[T·m/A]×[A/m] = [rad/s]`. Verified against MnF₂ (H_E ≈ 4.3×10⁷ A/m, H_A ≈ 7.0×10⁵ A/m) → f = 273 GHz vs. literature 262 GHz (4% deviation, accounted for by approximate input values). ✓

- **`ferrimagnet_compensation_freq` (`formulas.py:531`)** — `ω = (|γ_a m_a − γ_b m_b|/(m_a+m_b))·μ₀·H_ex`. Dimensional analysis: `[rad/(s·T)]×[A/m]/[A/m]×[T·m/A]×[A/m] = [rad/s]`. The ratio `m_a/(m_a+m_b)` is dimensionless since both are in [A/m]. Consistent with Kittel (1949) and Kim et al. Nat. Mater. 21, 544 (2022). ✓

- **`SpinPumpingISHE.forward()` Δα formula (`spin_pumping_ishe.py:136`)** — `(γ·ħ·g_eff)/(4π·Ms·d_FM)`. Dimensional check: numerator `[rad/(s·T)]·[J·s]·[m⁻²] = [rad·J/(T·m²)]`; denominator `[A/m]·[m] = [A]`. With `T = kg/(A·s²)` and `J = kg·m²/s²`: ratio = `[rad·A·s²·m²/(kg·m²·m²)]·[kg·m²/(A·s²·m²)] = dimensionless`. Numerically: `Δα ≈ 0.0026` for Py/Pt defaults (literature 0.003–0.01). ✓

- **`SpinPumpingISHE.v_ishe()` (`spin_pumping_ishe.py:204`)** — `θ_SH·λ_sf·tanh(d/(2λ_sf))·ρ_NM·j_s·w`. Dimensional check: `[1]×[m]×[1]×[Ω·m]×[A/m²]×[m] = [Ω·m²·A/m²] = [Ω·A] = [V]`. ✓

- **`STFMREffect.spin_hall_angle()` t_NM factor (`stfmr.py:267`)** — `(S/A)·√(1+M_eff/H_res)·(e·μ₀·Ms·t_FM·t_NM/ħ)`. Full dimensional chain: `[C]·[T·m/A]·[A/m]·[m]·[m]/[J·s] = [A·s]·[kg·m/(A²·s²)]·[A/m]·[m²]/[kg·m²/s] = dimensionless`. Without `t_NM` the result would be `[m⁻¹]` — NOT dimensionless. The `t_NM` factor is dimensionally required. Per rounds R4–R7 consensus; not re-flagged. ✓

- **`TopologicalHallEffect.forward()` and `extract_the()` (`topological_hall.py:113,177`)** — `ρ_xy − R_0·B − μ₀·R_s·M`. Dimensional check: `R_0·B = [m³/C]·[T] = [m³·kg/(A²·s³)] = [Ω·m]`; `μ₀·R_s·M = [T·m/A]·[m³/C]·[A/m] = [m³·T/C] = [Ω·m]`. Consistent with Nagaosa et al. Rev. Mod. Phys. 82, 1539 (2010), Eq. (3). ✓

- **`FMRKittel.forward()` in-plane (`fmr_kittel.py:130`)** — `gamma_p·μ₀·√(H_Am·(H_Am+M_eff))`. With `H_res` [T] converted to [A/m] via `H_Am = H_res/μ₀`: numerically at H = 0.1 T, M_eff = 860 kA/m → f = 9.630 GHz (matches exact Kittel formula). ✓

- **`GilbertDamping.forward()` (`gilbert_damping.py:114`)** — `ΔH = ΔH₀ + (2α/γ')·f`. Units: `[T] + [1/(GHz/T)]·[GHz] = [T]`. Numerically: slope = 0.714 mT/GHz for α = 0.01 (literature 0.5–1 mT/GHz for Permalloy). ✓

- **`DMIEffect.forward()` (`dmi.py:118`)** — `2·γ_p·D_i·k/M_s`. No `μ₀` in denominator. Confirmed against Di et al. PRL 114, 047201 (2015), Eq. (2), SI unit form. ✓

- **`LLG2SublatticeModel._llg2sl_rk4` exchange field sign (`llg_2sublattice.py:254–261`)** — `H_eff_a = H_ext − H_E·m_b + H_A·m_a[2]·ẑ`. For AFM ground state (m_a = +ẑ, m_b = −ẑ): `H_eff_a = (H_E+H_A)·ẑ` (stabilises m_a = +ẑ ✓); `H_eff_b = −(H_E+H_A)·ẑ` (stabilises m_b = −ẑ ✓). Keffer-Kittel (1952) convention. ✓

- **`sot_mram_fom` j_c formula (`device_fom.py:101`)** — `2αeμ₀Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Dimensional check: `[A·s]·[kg·m/(A²·s²)]·[A/m]·[m]·[A/m]/[kg·m²/s] = [A/m²]`. Numerically: j_c ≈ 3.65×10¹¹ A/m² (expected). ✓

- **`stt_mram_fom` j_c formula (`device_fom.py:179`)** — Same dimensional structure without `Ms/2` term (PMA-STT geometry has no demagnetization correction for out-of-plane easy axis). ✓

- **`magnon_device_fom` v_g formula (`device_fom.py:702`)** — `4·γ·A·k/Ms`. Dimensional check: `[rad/(s·T)]·[J/m]·[m⁻¹]/[A/m] = [rad·J/(s·T·A)] = [m/s]`. YIG defaults: v_g = 63.2 m/s. ✓

- **`magnon_device_fom` lambda_prop (`device_fom.py:705`)** — `v_g/(α·ω)`. This is the spin-wave amplitude 1/e decay length (standard convention). YIG defaults: λ = 6.7 μm (physically consistent). ✓

- **`spin_valve_sensor_fom` NEF formula (`device_fom.py:455–456,472`)** — R9 fix retained: `NEF = noise_floor/(S_H·R_sq)` [A/(m·√Hz)], then `NEF_T = NEF·μ₀` [T/√Hz]. Formula string (line 472) correctly reads `"NEF=noise_floor·μ₀/(S_H·R_sq)"`. ✓

- **`racetrack_fom` Walker breakdown field and v_max (`device_fom.py:229–230`)** — `H_W = α·K_⊥/(2·μ₀·Ms)`, `v_max = γ·Δ·H_W·μ₀/(1+α²)`. Factor-of-2 R8 fix retained. ✓

- **`racetrack_fom` current-driven DW velocity estimate (`device_fom.py:233`)** — `v_drive = 1e-12·j`. This is a clearly labeled placeholder estimate (formula string: `"v≈1e-12·j"`), not a physics formula. Not flagged. ✓

- **`spin_orbit_logic_fom` switching time (`device_fom.py:566`)** — `τ_sw = π/(α·γ·μ₀·H_k)`. Standard Slonczewski macrospin switching time estimate. Numerically: τ_sw = 1.78 ns for defaults (physically reasonable). ✓

- **`MacrospinModel.sw_switching_field()` (`macrospin.py:159–164`)** — `H_k/[(cos²θ)^(2/3) + (sin²θ)^(2/3)]^(3/2)`. Stoner-Wohlfarth (1948) astroid formula. `denom` guard prevents division by zero. ✓

- **`DW1DModel.walker_field()` (`dw_1d.py:126`)** — `α·K_⊥/(2·μ₀·Ms)`. Factor-of-2 correct per Schryer-Walker (1974). ✓

- **`DW1DModel.dw_velocity_below_walker()` (`dw_1d.py:142`)** — `γ₀·Δ·μ₀·H/(1+α²)`. ✓

- **`SMREffect.fit()` delta_rho_2 → NaN (`smr.py:238`)** — Correctly identifies that `Δρ₂` is not identifiable from longitudinal data alone; reports NaN. R5 fix retained. ✓

- **`SOTHarmonicHall.fit()` ξ extraction (`sot_harmonic_hall.py:222`)** — `c[1]/(4·c[0])`. R7 fix: 1ω regression gives `c[0] = R_AHE/2` → `R_AHE = 2c[0]` → `ξ = R_PHE/(2·R_AHE) = c[1]/(4c[0])`. Correct per Hayashi (2014) §II.C. ✓

- **`SOTHarmonicHall.phe_corrected()` (`sot_harmonic_hall.py:296`)** — `(H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)`. Denominator guard ✓. ✓

- **`AMREffect.forward()` (`amr.py:117`)** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975). ✓

- **`AnomalousHallEffect.forward()` (`anomalous_hall.py:115`)** — `R_0·B + μ₀·R_s·M`. Nagaosa et al. (2010) SI convention with `μ₀·R_s·M`. Dimensional check: `[m³/C]·[T] + [T·m/A]·[m³/C]·[A/m] = [Ω·m]`. ✓

- **`OrdinaryHallEffect.carrier_density()` (`ordinary_hall.py:135`)** — `1/(|R_H|·e)`. `[1/([m³/C]·[C])] = [m⁻³]`. ✓

- **`TYJScaling.forward()` (`tyj_scaling.py:114`)** — `a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009). ✓

- **`ThieleModel.forward()` (`thiele.py:147–149`)** — `v_x = αD·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard ✓. Thiele (1973). ✓

- **`PlanarHallEffect.forward()` (`planar_hall.py:101`)** — `(Δρ/2)·sin(2φ)`. Correct PHE formula (Taskin & Ando 2011). ✓

- **`USMREffect.forward()` (`usmr.py:177,179`)** — `ε·j₀·sin(φ) + offset` and `ε·j + offset`. Correct USMR asymmetry models (Avci et al. 2015). ✓

- **`OrbitalHallEffect.forward()` (`orbital_hall.py:146`)** — `(θ_OH/H_ext)·cos(φ)`. Simplified model clearly labeled as approximate; dimensionally: `[1/(A/m)]·[1] = [m/A]` (angular derivative of voltage, proportional to orbital Hall angle). ✓

- **`CurieTemperatureModel._power_law()` (`curie_temperature.py:166–169`)** — `T_C` bounded at 1 K; `np.clip(reduced, 0, None)` prevents complex power. ✓

- **`HysteresisLoop`** — Loop parameter extraction warns (does not silently fail) when data lacks zero-crossing. No physics formula in this module. ✓

- **`CalibrationEntry.apply/unapply` (`calibration.py:65–73`)** — `corrected = value × factor + offset`. Zero-factor guard in `unapply`. ✓

- **`GUM UncertaintyBudget.total()` (`calibration.py:327`)** — `√(Σσᵢ²)`. JCGM 100:2008 ✓.

- **`MuMax3._generate_mx3` B_ext conversion (`mumax3.py:105`)** — `H[A/m] × 1.25663706212e-6 = B[T]`. MuMax3 requires `B_ext` in Tesla. Correct μ₀ value. ✓

- **`OOMMFGenerateMIF2` (`oommf.py:53,124`)** — `_mu_0 = 1.25663706212e-6` for H→B conversion; `gamma_G = 1.760859630e11` rad/(s·T) (= GAMMA_E). Both correct. ✓

- **`LLGModel._llg_rhs` (`llg.py:120–128`)** — H_eff [A/m] multiplied by μ₀ before cross product; `γ_eff = γ/(1+α²)`; STT torques `τ_DL·(m×m_p×m)`, `τ_FL·(m×m_p)`. Oversampled internal grid with normalization. ✓

- **`LLGModel.precession_frequency()` (`llg.py:299`)** — `γ₀·μ₀·H_eff/(2π)` [GHz]. Dimensional check: `[rad/(s·T)]·[T·m/A]·[A/m] = [rad/s]` → divided by `2π·10⁹` = [GHz]. ✓

- **`exchange_length` (`formulas.py:55`)** — `√(2A/(μ₀Ms²))`. Permalloy: 5.3 nm (literature 5.3 nm). ✓

- **`bloch_wall_width` (`formulas.py:100`)** — `π·√(A/K)`. YIG: 255 nm (literature ~255 nm). ✓

- **`bloch_wall_energy` (`formulas.py:127`)** — `4·√(AK)`. K≤0 guard ✓.

- **`skyrmion_radius_dmi` (`formulas.py:269`)** — `πD/(4K_eff)`, K_eff > 0 guard ✓.

- **`skyrmion_stability_criterion` (`formulas.py:296`)** — `D²/(4A·K_eff)`. Guards for K_eff≤0 and A≤0. ✓

- **`heisenberg_to_exchange_stiffness` (`formulas.py:575`)** — `n·J·S²·z·a²/6`. Dimensional check: `[m⁻³]·[J]·[m²] = [J/m]`. Coey (2010) Eq. (5.86). ✓

- **`spin_diffusion_length` (`formulas.py:597`)** — `√(D_s·τ_sf)`. `[m²/s·s]^½ = [m]`. ✓

- **`skyrmion_hall_angle` (`formulas.py:638`)** — `atan2(4πQ, α·D)`. Handles α=0 correctly (returns π/2). Thiele (1973). ✓

- **`sot_efficiency` (`formulas.py:451`)** — Conductance-ratio model; dimensionless result. ✓

- **`kittel_freq_in_plane` (`formulas.py:388`)** — Numerically verified: 9.63 GHz at H = 0.1 T, Ms = 860 kA/m. ✓

- **`kittel_freq_out_of_plane` (`formulas.py:412`)** — `abs()` guard for H < M_eff. ✓

- **`walker_breakdown_field` (`formulas.py:162`)** — `α·K/(2·μ₀·Ms)`. Factor of 2 confirmed Schryer-Walker (1974). ✓

- **`walker_velocity` (`formulas.py:193`)** — `γ·Δ·μ₀·Ms/2`. Dimensional check: `[rad/(s·T)]·[m]·[T·m/A]·[A/m] = [m/s]`. ✓

- **`dw_velocity_below_walker` (`formulas.py:227`)** — `γ·δ·μ₀·H/(1+α²)`. ✓

- **`Spin Hall angle in the STFMR effect`** — t_NM factor is dimensionally required per Liu et al. PRL 106, 036601 (2011). Not re-flagged (standing instruction from rounds R4–R7).

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| — | — | — | No findings |
