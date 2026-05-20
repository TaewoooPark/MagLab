# Code Review Round 9 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-20
**Based on**: current code after Rounds 1–8 patches

---

## Verdict

**ISSUES FOUND** — 1 finding, max severity LOW.

---

## R8 Fix Verification

All three R8 findings have been correctly applied in `maglab/analysis/device_fom.py`.

| R8 Finding | Location | Status |
|---|---|---|
| `racetrack_fom` Walker breakdown field missing factor of 2 | `device_fom.py:229` | **FIXED** — Line 229 now reads `H_W = alpha * K_perp / (2.0 * MU_0 * Ms)`. The accompanying comment block (lines 225–228) correctly cites Schryer & Walker (1974) and notes consistency with `formulas.py` and `dw_1d.py`. Numerical verification: H_W = 49.74 A/m, v_max = 0.055 m/s (both halved from prior wrong values). |
| `magnon_device_fom` group velocity dimensionally wrong | `device_fom.py:702` | **FIXED** — Line 702 now reads `v_g = 4.0 * gamma_0 * A * k_mode / Ms`. The surrounding comment block (lines 691–700) gives the full derivation and dimensional analysis, including an explicit note that the prior formula `2*A*k/(μ₀*Ms)` had units of A not m/s. Numerical verification: v_g = 63.2 m/s (vs. 1.43×10⁻⁴ m/s before fix). |
| `spin_valve_sensor_fom` `noise_floor` docstring corrected to `[Ω/√Hz]` | `device_fom.py:435–441` | **FIXED** — Argument docstring now reads `Resistance noise spectral density [Ω/√Hz]` with a full dimensional-analysis proof showing that [Ω/√Hz] / ([m/A] × [Ω]) = [A/(m·√Hz)] ✓. The previous erroneous `[V/√Hz]` documentation is removed. |

---

## Findings

### FINDING 1 — LOW: `spin_valve_sensor_fom` FoM table formula string has μ₀ in the wrong position — μ₀ is in the denominator but should be in the numerator

**File / line:** `maglab/analysis/device_fom.py:472`

**Defect:**

```python
# device_fom.py line 469–473
"noise_equivalent_field_T_sqrtHz": {
    "value": float(NEF_T_sqrtHz),
    "unit": "T/sqrt(Hz)",
    "formula": "NEF=noise_floor/(S_H·R_sq·μ₀)",   # ← WRONG: μ₀ is in denominator
},
```

The formula string claims `NEF_T = noise_floor / (S_H · R_sq · μ₀)`, but the actual computation (lines 455–456) is:

```python
NEF_Am_sqrtHz = noise_floor / (S_H * R_sq)   # [A/(m·√Hz)]
NEF_T_sqrtHz = NEF_Am_sqrtHz * MU_0           # [T/√Hz] = [A/(m·√Hz)] × [T·m/A]
```

The actual formula is `NEF_T = noise_floor · μ₀ / (S_H · R_sq)` — μ₀ is a **multiplier**, not a divisor.

**Dimensional analysis — proof of error in label:**

If the formula string were correct (μ₀ in denominator):
```
[Ω/√Hz] / ([m/A] × [Ω] × [T·m/A])
= [Ω/√Hz] / [Ω·T·m²/A²]
= [A²/(T·m²·√Hz)]   ← NOT [T/√Hz]
```

If the code computation is used (μ₀ as multiplier):
```
[Ω/√Hz] / ([m/A] × [Ω]) × [T·m/A]
= [A/(m·√Hz)] × [T·m/A]
= [T/√Hz]   ✓
```

**Numerical impact:**

The computed **value** `NEF_T_sqrtHz` is physically correct — the bug is solely in the formula annotation string shown to users in the FoM table.

A user who tries to reproduce the FoM from the displayed formula will get:
```
noise_floor / (S_H · R_sq · μ₀) ≈ 0.796 T/√Hz   (wrong)
```
instead of the correct:
```
noise_floor · μ₀ / (S_H · R_sq) ≈ 1.26 × 10⁻¹² T/√Hz
```
The discrepancy factor is μ₀² ≈ 1.58 × 10⁻¹², making the label 12 orders of magnitude off from the computed value.

**Impact:** The FoM value stored in `DeviceFoMResult.foms["noise_equivalent_field_T_sqrtHz"]["value"]` is correct. Only the `"formula"` annotation string is wrong. This is a documentation bug, not a computation bug, but it will cause confusion for any user who inspects or re-derives the formula from the table.

**Concrete fix:**

```python
# device_fom.py line 472 — fix μ₀ position in formula string
"formula": "NEF=noise_floor·μ₀/(S_H·R_sq)",
```

**Reference:** Freitas, P. P. et al., *J. Phys.: Condens. Matter* 19, 165221 (2007), Eq. (3): NEF = S_n · μ₀ / (S_H · R), where S_n is the resistance noise.

---

## Non-Findings

Investigated and dismissed (no genuine defect found):

- **R8 `racetrack_fom` H_W fix** — `alpha * K_perp / (2.0 * MU_0 * Ms)`. Confirmed fixed with factor of 2. Comment block correctly references Schryer & Walker (1974).
- **R8 `magnon_device_fom` v_g fix** — `4.0 * gamma_0 * A * k_mode / Ms`. Confirmed: `[rad/(s·T)] × [J/m] × [1/m] / [A/m] = [m/s]`. Yields v_g = 63.2 m/s for YIG defaults. Correct per Kalinikos & Slavin (1986).
- **R8 `spin_valve_sensor_fom` noise_floor docstring** — Confirmed corrected to `[Ω/√Hz]` with full dimensional-analysis justification in the docstring.
- **`walker_breakdown_field` (`formulas.py:162`)** — `alpha * K / (2.0 * MU_0 * Ms)`. Correct with factor of 2. Consistent with `dw_1d.py:126` and `device_fom.py:229`.
- **`dw_velocity_below_walker` (`formulas.py:227`)** — `gamma * delta * MU_0 * H / (1+alpha²)`. Schryer-Walker (1974). Correct.
- **`walker_velocity` (`formulas.py:193`)** — `gamma * Delta * MU_0 * Ms / 2.0`. R6 fix retained. Dimensional check: `[rad/(s·T)] × [m] × [T·m/A] × [A/m] = [m/s]` ✓.
- **`spinwave_dispersion_fm` (`formulas.py:336–338`)** — `omega_H + omega_ex` = `gamma*MU_0*H + gamma*(2A/Ms)*k²`. MU_0 cancels in exchange term. Correct per Kalinikos-Slavin (1986).
- **`afmr_frequency` (`formulas.py:491`)** — `(gamma/2π)*MU_0*sqrt(2*H_E*H_A)`. Correct Keffer-Kittel (1952) formula; `product<0` guard prevents complex sqrt. Verified.
- **`ferrimagnet_compensation_freq` (`formulas.py:535`)** — Returns `omega/(2π)` [Hz]. R5 fix retained. Correct.
- **`bloch_wall_width` (`formulas.py:100`)** — `π·sqrt(A/K)`. K≤0 guard. Yields 254 nm for YIG (literature 255 nm). Correct.
- **`bloch_wall_energy` (`formulas.py:129`)** — `4·sqrt(A·K)`. K≤0 guard. Correct per Hubert & Schäfer (1998).
- **`exchange_length` (`formulas.py:55`)** — `sqrt(2A/(μ₀Ms²))`. Yields 5.3 nm for Permalloy (literature 5.3 nm). Correct.
- **`skyrmion_radius_dmi` (`formulas.py:269`)** — `π·D/(4·K_eff)`, K_eff = K − μ₀Ms²/2. Negative K_eff guard returns −1.0. Correct per Bogdanov & Rößler (2001).
- **`skyrmion_stability_criterion` (`formulas.py:296`)** — κ = D²/(4·A·K_eff). Guards for K_eff≤0 and A≤0. Correct.
- **`skyrmion_hall_angle` (`formulas.py:638`)** — `atan2(G, alpha*D_norm)`. Thiele (1973). Correct.
- **`heisenberg_to_exchange_stiffness` (`formulas.py:575`)** — `n*J*S²*z*a²/6`. Coey (2010). Dimensional check: `[m⁻³]×[J]×[m²] = [J/m]` ✓. Correct.
- **`spin_diffusion_length` (`formulas.py:597`)** — `sqrt(D_s*tau_sf)`. Valet & Fert (1993). `[m²/s × s]^½ = [m]` ✓.
- **`kittel_freq_in_plane/out_of_plane` (`formulas.py:388, 412`)** — Standard Kittel formulas with `abs()` guard. Correct.
- **`sot_efficiency` (`formulas.py:453`)** — Conductance-ratio model, dimensionless result. Correct.
- **`sot_mram_fom` j_c formula (`device_fom.py:101`)** — `2αeμ₀Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Dimensional analysis: `[A·s]×[T·m/A]×[A/m]×[m]×[A/m] / [J·s] = [A/m²]` ✓. Factor (H_k + Ms/2) dimensionally consistent [both A/m]. Correct per Dieny et al. Nat. Electron. 3, 446 (2020).
- **`stt_mram_fom` j_c formula (`device_fom.py:179`)** — Same form without Ms/2 (different geometry). Dimensionally correct.
- **`mtj_fom` RA product (`device_fom.py:321`)** — `R_P * A_bit * 1e12`. Unit conversion m² → μm² correct.
- **`spin_orbit_logic_fom` tau_sw formula** — `τ_sw = π/(α·ω₀)`, ω₀ = γ·μ₀·H_k. Dimensional check: `[rad/s]` ✓. Capped at 10 ns. Correct.
- **`spin_orbit_logic_fom` E_sw formula** — `I_c²·R_NM·τ_sw`. Dim: `[A²·Ω·s] = [W·s] = [J]` ✓. Correct.
- **`racetrack_fom` current-driven v_drive** — `1e-12 * j_drive`. Documented as `simple proportionality (spin transfer velocity)` with key name `current_driven_DW_velocity_estimate`. This is a deliberate rough estimate, not a precision formula. No physics error.
- **`magnon_device_fom` transit time** — `L/v_g = 100μm / 63 m/s = 1.58 μs`. Physically consistent with slow exchange spin waves at k = π/μm in YIG. No defect.
- **`DW1DModel.walker_field` (`dw_1d.py:126`)** — `alpha*K_perp/(2*MU_0*Ms)`. Factor of 2 confirmed. Consistent with `formulas.py:162`.
- **`DW1DModel.dw_velocity_below_walker` (`dw_1d.py:142`)** — `gamma_0 * Delta * MU_0 * H / (1+alpha²)`. Correct.
- **`FMRKittel.forward()` and `fit()` (`fmr_kittel.py:121–180`)** — H_res [T] → H_Am [A/m] via `/MU_0`. `np.abs()` guard in sqrt. R4 fix retained. Correct.
- **`GilbertDamping.forward()` (`gilbert_damping.py:113`)** — `ΔH = ΔH₀ + (2α/γ')·f`. Dim: in GHz/T units consistent. Correct.
- **`DMIEffect.forward()` (`dmi.py:118`)** — `2*gamma_p*D_i*k/Ms`. No μ₀ in denominator (verified: Di et al. PRL 114, 047201 (2015) in SI units). Correct.
- **`SpinPumpingISHE.forward()` (`spin_pumping_ishe.py:136`)** — `(gamma_rad*HBAR*g_eff)/(4π*Ms*d_FM)`. No μ₀ in denominator. R5 fix retained. Correct per Mosendz PRB 82, 214403 (2010).
- **`SpinPumpingISHE.v_ishe` (`spin_pumping_ishe.py:203`)** — `θ_SH·λ·tanh(d/(2λ))·ρ·j_s·w`. Dim: `[m]×[Ω·m]×[A/m²]×[m] = [V]` ✓. Correct.
- **`SMREffect.fit()` (`smr.py:192`)** — Restricts to ρ₀ and Δρ₁; Δρ₂ reported as NaN. R5 fix retained. Correct.
- **`STFMREffect.spin_hall_angle()` (`stfmr.py:267`)** — Per rounds R4–R7 consensus: t_NM factor is dimensionally required (Liu et al. PRL 106, 036601, 2011). Not re-flagged per standing instruction.
- **`SOTHarmonicHall.fit()` ξ extraction (`sot_harmonic_hall.py:222`)** — `c[1] / (4.0 * c[0])`. R7 fix confirmed. Hayashi PRB 89, 144425 (2014). Correct.
- **`SOTHarmonicHall.phe_corrected()` (`sot_harmonic_hall.py:296–301`)** — `H_DL = (H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)`. Division guard `abs(denom) < 1e-15`. Correct per Hayashi (2014) Eq. (S7).
- **`LLG2SublatticeModel._llg2sl_rk4` (`llg_2sublattice.py:252–271`)** — Exchange field: `H_eff_a = H_ext − H_E*m_b + H_A*m_a[2]*ẑ`. Sign correct for AFM coupling. MU_0 conversion in mxH. Oversampled internal grid. Normalization present. Correct.
- **`MacrospinModel._llg_rk4` (`macrospin.py:188–241`)** — DL torque `tau_DL*(m×m_p×m)`, FL torque `tau_FL*(m×m_p)`. Oversampled internal grid. Normalization present. Ring-down model correct. R4 fix retained. Correct.
- **`ThieleModel.forward()` (`thiele.py:120–152`)** — `v_x = αD·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard present. Thiele (1973). Correct.
- **`AnomalousHallEffect.forward()` (`anomalous_hall.py:115`)** — `ρ_xy = R_0·B + μ₀·R_s·M`. Dim: `[m³/C]×[T] + [T·m/A]×[m³/C]×[A/m] = [Ω·m]` ✓. Correct.
- **`TopologicalHallEffect`** — Same formula structure as AHE. Correct.
- **`CurieTemperatureModel._power_law` (`curie_temperature.py:166`)** — T_C guard `max(T_C, 1.0)`, `np.clip(reduced, 0, None)` prevents complex power. Correct.
- **`HysteresisLoop.extract_loop_params` (`hysteresis.py:165–195`)** — Warns (not silently fails) when data lacks zero-crossing. No physics error.
- **`TYJScaling.forward()` (`tyj_scaling.py:113`)** — `ρ_AHE = a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009). Initial values via lstsq. Correct.
- **`GMRTMREffect.forward()` (`gmr_tmr.py:129`)** — `G_0·(1 + (TMR/2)·cosθ)` with Julliere formula. Guard `abs(denom) < 1e-15`. Correct.
- **`LLGModel._llg_rhs` (`llg.py:120–128`)** — H_eff multiplied by MU_0 before cross product. gamma_eff = γ/(1+α²). STT torques correct. Correct.
- **`AMREffect.forward()` (`amr.py:117`)** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975). Correct.
- **`OrbitalHallEffect` rank-3 tensor** — Shape (3,3,3) enforced. Antisymmetric component applied. No physics issue.
- **`PlanarHallEffect.forward()` (`planar_hall.py:101`)** — `(Δρ/2)·sin(2φ)`. Standard PHE formula. Correct.
- **`OrdinaryHallEffect.carrier_density()` (`ordinary_hall.py:135`)** — `1/(|R_H|·e)`. Dim: `1/([m³/C]×[C]) = [m⁻³]` ✓. Correct.
- **`USMREffect.forward()` (`usmr.py:177–180`)** — `ε·j₀·sin(φ) + offset` (angle mode) and `ε·j + offset` (current mode). Consistent with Avci et al. 2015. Correct.
- **`CalibrationEntry.apply/unapply` (`calibration.py:65–73`)** — `corrected = value × factor + offset`. Inverse with zero-factor guard. Correct.
- **`CorrectionPipeline.total_uncertainty()` (`calibration.py:239`)** — GUM quadrature `sqrt(Σσ²)`. Correct.
- **`GUM UncertaintyBudget.total()` (`calibration.py:327`)** — `sqrt(Σσᵢ²)`. JCGM 100:2008. Correct.
- **`MuMax3._generate_mx3` B_ext conversion (`mumax3.py:105`)** — `H[A/m] × 1.25663706212e-6 [T·m/A] = B[T]`. MuMax3 takes B_ext in Tesla. Correct.
- **`OOMMFGenerateMIF2` (`oommf.py:53, 105`)** — `_mu_0 = 1.25663706212e-6` for H→B conversion. OOMMF `Oxs_FixedZeeman` and gamma_G=1.760859630e11 (= GAMMA_E). Both correct.
- **`AFMR formula` consistency between `formulas.py:491` and `llg_2sublattice.py`** — Both use the same `afmr_frequency()` imported from `formulas.py`. No independent reimplementation. Correct.

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **LOW** | `analysis/device_fom.py:472` | `spin_valve_sensor_fom` FoM table formula string `"NEF=noise_floor/(S_H·R_sq·μ₀)"` has μ₀ in the denominator, but the actual code multiplies by μ₀: `NEF_T = (noise_floor/(S_H*R_sq))*MU_0`. The computed value is correct; only the annotation string is wrong. A user who reproduces the formula from the table would get a result off by a factor of μ₀² ≈ 1.58×10⁻¹². Fix: change formula string to `"NEF=noise_floor·μ₀/(S_H·R_sq)"`. |
