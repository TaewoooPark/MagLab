# Code Review Round 10 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-20
**Based on**: current code after Rounds 1–9 patches

---

## Verdict

**ISSUES FOUND** — 1 finding, max severity MEDIUM.

---

## R9 Fix Verification

The R9 finding (μ₀ position in `spin_valve_sensor_fom` FoM table formula string) has been correctly applied.

| R9 Finding | Location | Status |
|---|---|---|
| `spin_valve_sensor_fom` formula string: μ₀ was in the denominator, should be a numerator multiplier | `device_fom.py:472` | **FIXED** — Line 472 now reads `"formula": "NEF=noise_floor·μ₀/(S_H·R_sq)"`. The code at lines 455–456 computes `NEF_Am_sqrtHz = noise_floor / (S_H * R_sq)` then `NEF_T_sqrtHz = NEF_Am_sqrtHz * MU_0`, which is exactly what the corrected formula string says. |

---

## Findings

### FINDING 1 — MEDIUM: `GMRTMREffect.forward()` conductance amplitude uses `TMR/2` instead of `P1·P2`

**File / line:** `maglab/analysis/effects/gmr_tmr.py:129`

**Defect:**

```python
# gmr_tmr.py line 128-129
tmr = self.tmr_from_polarizations(P1, P2)
return G_0 * (1.0 + (tmr / 2.0) * np.cos(theta))
```

The function `tmr_from_polarizations` returns the Julliere TMR ratio (line 108):

```python
return 2.0 * P1 * P2 / denom   # denom = 1 - P1*P2
```

So `tmr / 2.0 = P1·P2 / (1 − P1·P2)`.

The Slonczewski (1989) conductance formula requires the amplitude to be **P1·P2**, not `P1·P2/(1 − P1·P2)`:

```
G(θ) = G₀ · (1 + P₁P₂ · cosθ)   ← Slonczewski PRB 39, 6995 (1989), Eq. (4)
```

The code uses `TMR_Julliere / 2 = P₁P₂/(1 − P₁P₂)` as the amplitude, which inflates it by a factor of `1/(1 − P₁P₂)` relative to the correct formula.

**Dimensional analysis / algebraic proof of error:**

The Slonczewski formula at θ = 0 (parallel, P) and θ = π (antiparallel, AP):

```
G_P = G_0·(1 + P₁P₂)
G_AP = G_0·(1 − P₁P₂)
TMR_Julliere = (G_P − G_AP)/G_AP = 2·P₁P₂/(1 − P₁P₂)   ✓  (matches Julliere 1975)
```

The code formula at θ = 0 and θ = π:

```
G_P_code = G_0·(1 + P₁P₂/(1 − P₁P₂)) = G_0/(1 − P₁P₂)
G_AP_code = G_0·(1 − P₁P₂/(1 − P₁P₂)) = G_0·(1 − 2P₁P₂)/(1 − P₁P₂)
G_P_code/G_AP_code = 1/(1 − 2P₁P₂)
```

Correct Slonczewski ratio:

```
G_P/G_AP = (1 + P₁P₂)/(1 − P₁P₂)
```

These are unequal for all P₁P₂ > 0. For typical spin polarizations:

| P₁ = P₂ | P₁P₂ | Correct G_P/G_AP | Code G_P/G_AP | Amplitude error |
|---|---|---|---|---|
| 0.32 | 0.10 | 1.222 | 1.250 | +11% |
| 0.55 | 0.30 | 1.857 | 2.500 | +43% |
| 0.71 | 0.50 | 3.000 | ∞ (G_AP → 0) | → ∞ as P₁P₂ → 0.5 |

At P₁P₂ = 0.5 the code formula produces `G_AP = 0` (conductance singularity), which is non-physical. The correct formula has G_AP = G_0/2 at P₁P₂ = 0.5.

**Numerical impact:**

- `forward()` computes angular conductance G(θ) with inflated amplitude.
- `fit()` calls `forward()` in the curve-fit model, so extracted P1, P2, G_0 from G(θ) data are also wrong: G_0 will be underestimated and the polarizations overestimated.
- The `tmr_from_polarizations()` static method itself is correct (pure Julliere formula) and unaffected.
- The error scales as `P₁P₂/(1 − P₁P₂) − P₁P₂ = P₁P₂²/(1 − P₁P₂)`: second-order in P₁P₂ for small polarization but first-order for typical values (~0.5–0.7 for CoFeB/MgO).

**Concrete fix:**

Replace the TMR-based amplitude with the direct P1·P2 product in `forward()` and in the `model_fn` closure inside `fit()`:

```python
# gmr_tmr.py line 129 — in forward()
# Before:
return G_0 * (1.0 + (tmr / 2.0) * np.cos(theta))

# After:
return G_0 * (1.0 + P1 * P2 * np.cos(theta))
```

```python
# gmr_tmr.py line 158 — model_fn inside fit()
# Before:
def model_fn(x: np.ndarray, G_0: float, P1: float, P2: float) -> np.ndarray:
    tmr = self.tmr_from_polarizations(P1, P2)
    return G_0 * (1.0 + (tmr / 2.0) * np.cos(x))

# After:
def model_fn(x: np.ndarray, G_0: float, P1: float, P2: float) -> np.ndarray:
    return G_0 * (1.0 + P1 * P2 * np.cos(x))
```

The `tmr_from_polarizations()` method and its use in reporting remain unchanged (it computes the Julliere TMR for display only).

The docstring should also be updated to reflect that the conductance amplitude is `P₁P₂` (Slonczewski convention), and the FoM table `tmr` key already reports the standard Julliere TMR correctly.

**References:**
- Slonczewski, J. C., *Phys. Rev. B* 39, 6995 (1989), Eq. (4): G(θ) = G_0(1 + P₁P₂ cosθ).
- Julliere, M., *Phys. Lett. A* 54, 225 (1975): TMR = 2P₁P₂/(1 − P₁P₂) — this applies to the ratio, not the conductance amplitude.

---

## Non-Findings

Investigated and dismissed (no genuine defect found):

- **R9 `spin_valve_sensor_fom` NEF formula string fix** — Line 472 confirmed: `"NEF=noise_floor·μ₀/(S_H·R_sq)"`. Fix correctly applied.
- **`walker_breakdown_field` (`formulas.py:162`)** — `alpha * K / (2.0 * MU_0 * Ms)`. Factor of 2 confirmed correct per Schryer & Walker (1974). Consistent with `dw_1d.py:126` and `device_fom.py:229`.
- **`walker_velocity` (`formulas.py:193`)** — `gamma * Delta * MU_0 * Ms / 2.0`. Dimensional check: `[rad/(s·T)] × [m] × [T·m/A] × [A/m] = [m/s]` ✓.
- **`spinwave_dispersion_fm` (`formulas.py:336–338`)** — Exchange term `gamma*(2A/Ms)*k²` does not have a μ₀ factor (cancels in SI). ✓
- **`magnon_device_fom` group velocity (`device_fom.py:702`)** — `v_g = 4.0 * gamma_0 * A * k_mode / Ms`. Dimensional check: `[rad/(s·T)] × [J/m] × [m⁻¹] / [A/m] = [m/s]` ✓. Numerically: v_g = 63.2 m/s for YIG at k = π/μm ✓.
- **`magnon_device_fom` propagation length (`device_fom.py:705`)** — `lambda_prop = v_g / (alpha * omega)`. This is the standard exchange spin-wave 1/e decay length per Chumak et al. (2015): λ = v_g · τ_sw where τ_sw = 1/(α·ω). Dimensionally: `[m/s] / ([rad/s]) = [m/rad] ≈ [m]` ✓. Numerically: λ = 6.7 μm for YIG defaults, physically consistent.
- **`sot_mram_fom` j_c formula (`device_fom.py:101`)** — `2αeμ₀Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Dimensional check: `[A·s]×[T·m/A]×[A/m]×[m]×[A/m]/([J·s]) = [A/m²]` ✓. The Ms/2 demagnetization term is physically correct for PMA-SOT geometry. Numerical: j_c ≈ 3.65×10¹¹ A/m² (higher than IRDS target because default Ms is large; formula is correct).
- **`stt_mram_fom` j_c formula (`device_fom.py:179`)** — Same form without Ms/2, correct for Slonczewski STT in PMA MTJ geometry where the easy axis is out-of-plane. Dimensional check consistent with SOT formula. Numerical: j_c ≈ 8.1×10¹⁰ A/m² ✓.
- **`racetrack_fom` Walker breakdown + DW velocity** — `H_W = alpha*K_perp/(2*MU_0*Ms)`, `v_max = gamma_0*MU_0*Delta_dw*H_W/(1+alpha²)`. Both correct per Schryer-Walker (1974). R8 fix retained.
- **`afmr_frequency` (`formulas.py:491`)** — `(gamma/(2π))·μ₀·√(2·H_E·H_A)`. Dimensional check: `[rad/(s·T)]×[T·m/A]×[A/m] = [rad/s]` ✓. Numerical: H_E=1e6, H_A=1e4 → f=4.98 GHz (physically reasonable). `product<0` guard prevents complex sqrt. ✓
- **`ferrimagnet_compensation_freq` (`formulas.py:535`)** — `ω = (|γ_a m_a − γ_b m_b|/(m_a+m_b))·μ₀·H_ex`. Dimensional check: `[rad/(s·T)]×[A/m]/[A/m]×[T·m/A]×[A/m] = [rad/s]` ✓. Returns f = ω/(2π) [Hz] ✓. Zero denominator guard present ✓.
- **`exchange_length` (`formulas.py:55`)** — `√(2A/(μ₀Ms²))`. Yields 5.3 nm for Permalloy (literature 5.3 nm), 18.0 nm for YIG (literature ~17 nm) ✓.
- **`bloch_wall_width` (`formulas.py:100`)** — `π·√(A/K)`. K≤0 guard ✓. Yields 255 nm for YIG (literature ~255 nm) ✓.
- **`skyrmion_radius_dmi` (`formulas.py:269`)** — `π·D/(4·K_eff)`, K_eff guard ✓.
- **`skyrmion_stability_criterion` (`formulas.py:296`)** — κ = D²/(4·A·K_eff). Guards for K_eff≤0 and A≤0 ✓.
- **`heisenberg_to_exchange_stiffness` (`formulas.py:575`)** — `n·J·S²·z·a²/6`. Dimensional check: `[m⁻³]×[J]×[m²] = [J/m]` ✓. Coey (2010) Eq. (5.86) ✓.
- **`spin_diffusion_length` (`formulas.py:597`)** — `√(D_s·τ_sf)`. Dimensional check: `[m²/s×s]^½ = [m]` ✓.
- **`skyrmion_hall_angle` (`formulas.py:638`)** — `atan2(G, α·D_norm)`. Thiele (1973). G=4πQ, atan2 handles α=0 correctly ✓.
- **`kittel_freq_in_plane` (`formulas.py:388`)** — Standard Kittel in-plane formula. Numerical: H=0.1T, M_eff=860 kA/m → f=9.63 GHz (matches exact Kittel formula check) ✓.
- **`kittel_freq_out_of_plane` (`formulas.py:412`)** — `abs()` guard for H < M_eff case ✓.
- **`sot_efficiency` (`formulas.py:453`)** — Conductance-ratio model, dimensionless result ✓.
- **`FMRKittel.forward()` (`fmr_kittel.py:121–138`)** — H_res [T] → H_Am [A/m] via `/MU_0`. `np.abs()` guard in sqrt. In-plane: `f = gamma_p * MU_0 * sqrt(H_Am*(H_Am+M_eff))` — verified matches exact Kittel formula independently ✓. Out-of-plane: `f = gamma_p * MU_0 * |H_Am − M_eff|` ✓.
- **`FMRKittel.fit()` initial estimates** — In-plane: `M_eff_init = (f/gamma_p/mu_0)²/H − H` (exact inversion of Kittel) ✓. Out-of-plane: `M_eff_init = H − f/(gamma_p*mu_0)` ✓.
- **`GilbertDamping.forward()` (`gilbert_damping.py:113`)** — `ΔH = ΔH₀ + (2α/γ')·f`. Slope = 2α/γ' [T/GHz]; α=0.01 → slope=0.714 mT/GHz (literature: ~0.5–1 mT/GHz for low-α metals) ✓.
- **`DMIEffect.forward()` (`dmi.py:118`)** — `Δf = 2·γ_p·D_i·k/Ms`. No μ₀ in denominator (verified against Di et al. PRL 114, 047201 (2015) SI units). Dimensional check: `[Hz/T]×[J/m²]×[m⁻¹]/[A/m] = [Hz]` ✓. Numerical: D=2 mJ/m², k=14.7 μm⁻¹ → Δf=1.9 GHz (consistent with literature) ✓.
- **`SpinPumpingISHE.forward()` (`spin_pumping_ishe.py:136`)** — `(γ·ħ·g↑↓)/(4π·Ms·d_FM)` — no μ₀ in denominator. Mosendz PRB 82, 214403 (2010), Eq. (2) ✓.
- **`SpinPumpingISHE.v_ishe` (`spin_pumping_ishe.py:203`)** — `θ_SH·λ·tanh(d/(2λ))·ρ·j_s·w`. Dim: `[m]×[Ω·m]×[A/m²]×[m] = [V]` ✓.
- **`SMREffect.fit()` (`smr.py:192`)** — Restricts to ρ₀ and Δρ₁; Δρ₂ reported as NaN (not identifiable from longitudinal signal alone). R5 fix retained ✓.
- **`STFMREffect.spin_hall_angle()` (`stfmr.py:267`)** — `(S/A)·√(1+M_eff/H_res)·(e·μ₀·Ms·t_FM·t_NM/ħ)`. Dimensional check: e[C]×μ₀[T·m/A]×Ms[A/m]×t_FM[m]×t_NM[m]/ħ[J·s] = `[kg·m²/s]/[kg·m²/s] = dimensionless` ✓. Per rounds R4–R7 consensus: t_NM factor is dimensionally required (Liu et al. PRL 106, 036601, 2011). Not re-flagged.
- **`SOTHarmonicHall.fit()` ξ extraction (`sot_harmonic_hall.py:222`)** — `c[1] / (4.0 * c[0])`. R7 fix confirmed ✓.
- **`SOTHarmonicHall.phe_corrected()` (`sot_harmonic_hall.py:296–301`)** — `H_DL = (H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)`. Denominator guard `abs(denom) < 1e-15` ✓.
- **`LLGModel._llg_rhs` (`llg.py:120–128`)** — H_eff multiplied by MU_0 before cross product (`mxH = cross(m, MU_0*H_eff)`). γ_eff = γ/(1+α²). STT torques `tau_DL*(m×m_p×m)`, `tau_FL*(m×m_p)`. Oversampled internal grid, normalization present ✓.
- **`LLG2SublatticeModel._llg2sl_rk4` (`llg_2sublattice.py:252–271`)** — AFM exchange sign: H_eff_a = H_ext − H_E·m_b + H_A·m_a[2]·ẑ. For ground state m_a=+z, m_b=−z: H_eff_a = H_E+H_A pointing +z (stabilizes m_a=+z) ✓; H_eff_b = −H_E−H_A pointing −z (stabilizes m_b=−z) ✓. Keffer-Kittel sign convention ✓.
- **`MacrospinModel._llg_rk4` (`macrospin.py:188–241`)** — Identical structure to LLGModel. DL torque `tau_DL*(m×m_p×m)`, FL torque `tau_FL*(m×m_p)`. Normalization and oversampling present ✓.
- **`ThieleModel.forward()` (`thiele.py:120–152`)** — `v_x = αD·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard ✓. Thiele (1973) ✓.
- **`AnomalousHallEffect.forward()` (`anomalous_hall.py:115`)** — `ρ_xy = R_0·B + μ₀·R_s·M`. Dim: `[m³/C]×[T] + [T·m/A]×[m³/C]×[A/m] = [Ω·m]` ✓.
- **`CurieTemperatureModel._power_law` (`curie_temperature.py:166`)** — `T_C` guard `max(T_C, 1.0)`, `np.clip(reduced, 0, None)` prevents complex power ✓.
- **`HysteresisLoop.extract_loop_params`** — warns (not silently fails) when data lacks zero-crossing. No physics error.
- **`TYJScaling.forward()`** — `ρ_AHE = a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009). Initial values via lstsq ✓.
- **`MuMax3._generate_mx3` B_ext conversion (`mumax3.py:105`)** — `H[A/m] × 1.25663706212e-6 [T·m/A] = B[T]`. MuMax3 takes B_ext in Tesla ✓.
- **`OOMMFGenerateMIF2` (`oommf.py:53, 105`)** — `_mu_0 = 1.25663706212e-6` for H→B conversion; `gamma_G=1.760859630e11` (= GAMMA_E). Both correct ✓.
- **`DW1DModel.walker_field` (`dw_1d.py:126`)** — `alpha*K_perp/(2*MU_0*Ms)`. Factor of 2 confirmed ✓.
- **`DW1DModel.dw_velocity_below_walker` (`dw_1d.py:142`)** — `gamma_0 * Delta * MU_0 * H / (1+alpha²)` ✓.
- **`AMREffect.forward()` (`amr.py:117`)** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975) ✓.
- **`OrdinaryHallEffect.carrier_density()` (`ordinary_hall.py:135`)** — `1/(|R_H|·e)`. Dim: `1/([m³/C]×[C]) = [m⁻³]` ✓.
- **`GMRTMREffect.tmr_from_polarizations()` (`gmr_tmr.py:100–108`)** — `2*P1*P2/(1-P1*P2)`. This is the correct Julliere formula. Only `forward()` and `fit()` use it incorrectly. The static method itself is correct.
- **`CalibrationEntry.apply/unapply` (`calibration.py:65–73`)** — `corrected = value × factor + offset`. Inverse with zero-factor guard ✓.
- **`GUM UncertaintyBudget.total()` (`calibration.py:327`)** — `sqrt(Σσᵢ²)`. JCGM 100:2008 ✓.
- **Spin Hall angle in the STFMR effect** — t_NM factor is dimensionally required per Liu et al. PRL 106, 036601 (2011). Not re-flagged (standing instruction from rounds R4–R7).

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **MEDIUM** | `analysis/effects/gmr_tmr.py:129,158` | `GMRTMREffect.forward()` and its embedded `model_fn` use `tmr/2.0` as the conductance oscillation amplitude, where `tmr = 2·P₁P₂/(1−P₁P₂)` (Julliere formula). The correct Slonczewski (1989) amplitude is `P₁P₂`, not `P₁P₂/(1−P₁P₂)`. The error inflates the modulation amplitude by factor `1/(1−P₁P₂)`: ~11% for P~0.32, ~43% for P~0.55, →∞ as P₁P₂→0.5. Fix: replace `(tmr / 2.0) * np.cos(theta)` with `P1 * P2 * np.cos(theta)` in both `forward()` and `model_fn`. |
