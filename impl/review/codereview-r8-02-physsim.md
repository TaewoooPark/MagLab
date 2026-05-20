# Code Review Round 8 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19
**Based on**: current code after Rounds 1–7 patches

---

## Verdict

**ISSUES FOUND** — 3 findings, max severity MEDIUM.

---

## R7 Fix Verification

The R7 fix for the ξ auto-estimation in `SOTHarmonicHall.fit()` is correctly applied.

| R7 Finding | Status |
|---|---|
| `sot_harmonic_hall.py:219` — ξ inflated 4× (used `c[1]/c[0]` instead of `c[1]/(4*c[0])`) | **FIXED** — Line 222 now reads `xi_val = float(c[1] / (4.0 * c[0])) if abs(c[0]) > 1e-30 else 0.0`, with a corrected comment block (lines 219–221) that correctly derives `ξ = R_PHE / (2·R_AHE) = c[1] / (4·c[0])`. The fix matches the Hayashi PRB 89, 144425 (2014) definition exactly. |

---

## Findings

### FINDING 1 — MEDIUM: `racetrack_fom` Walker breakdown field missing factor of 2 — H_W inflated 2× relative to Schryer-Walker (1974)

**File / line:** `maglab/analysis/device_fom.py:225`

**Defect:**

```python
H_W = alpha * K_perp / (MU_0 * Ms)          # line 225 — WRONG (missing /2)
v_max_walker = gamma_0 * MU_0 * Delta_dw * H_W / (1.0 + alpha**2)  # line 226
```

**Dimensional analysis and reference:**

The Walker breakdown field from Schryer & Walker, *J. Appl. Phys.* 45, 5406 (1974) for a 1D uniaxial DW model is:

```
H_W = α·K_⊥ / (2·μ₀·M_s)
```

This is the formula used consistently elsewhere in the codebase:
- `maglab/physics/formulas.py:162`: `return alpha * K / (2.0 * MU_0 * Ms)`
- `maglab/analysis/effects/dw_1d.py:126`: `return alpha * K_perp / (2.0 * MU_0 * Ms)` (the comment there even says "The factor of 2 was previously missing")

The `racetrack_fom` at line 225 drops the factor of 2, doubling H_W. Since `v_max_walker` (line 226) scales linearly with H_W, the maximum DW velocity is also doubled.

**Numerical impact** (default parameters: α=0.01, K_⊥=10⁴ J/m³, Ms=8×10⁵ A/m, Δ=5 nm):

| Quantity | Code (wrong) | Correct |
|---|---|---|
| H_W | 99.47 A/m | 49.74 A/m |
| v_max_walker | 0.110 m/s | 0.055 m/s |

Both the Walker field and max DW velocity are inflated 2× in the FoM table. This error is confined to `device_fom.racetrack_fom`; the canonical implementations in `formulas.py` and `dw_1d.py` are correct.

**Reference:** Schryer, N. L., Walker, L. R., *J. Appl. Phys.* 45, 5406 (1974), Eq. (8). Also confirmed by Thiaville et al., *EPL* 69, 990 (2005), Eq. (6): H_W = αK_⊥/(2μ₀Ms).

**Concrete fix:**

```python
# device_fom.py line 225 — add the missing factor of 2
H_W = alpha * K_perp / (2.0 * MU_0 * Ms)    # Schryer-Walker (1974): H_W = αK_⊥/(2μ₀Ms)
```

---

### FINDING 2 — MEDIUM: `magnon_device_fom` spin-wave group velocity formula is dimensionally wrong — missing gyromagnetic ratio γ

**File / line:** `maglab/analysis/device_fom.py:677`

**Defect:**

```python
# device_fom.py line 677
v_g = 2.0 * A * k_mode / (MU_0 * Ms)  # ∂ω/∂k at exchange limit
```

**Dimensional analysis — proof of error:**

The exchange spin-wave dispersion (Kalinikos & Slavin, *J. Phys. C* 19, 7013, 1986, Eq. 2.17; same as `formulas.spinwave_dispersion_fm`, line 305) is:

```
ω(k) = γ·μ₀·H_0 + γ·(2A/Ms)·k²
```

The group velocity is:

```
v_g = ∂ω/∂k = 2·γ·(2A/Ms)·k = 4·γ·A·k/Ms
```

Dimensions of the correct formula: `[rad/(s·T)] × [J/m] × [1/m] / [A/m]`
= `[A·s²/kg] × [kg·m²·s⁻²/m/m] × [m/A]` = `[m/s]` ✓

Dimensions of the code formula `2·A·k/(μ₀·Ms)`:
- Numerator: `[J/m] × [1/m]` = `[kg·s⁻²]`
- Denominator: `[T·m/A] × [A/m]` = `[T]` = `[kg·A⁻¹·s⁻²]`
- Result: `[kg·s⁻²] / [kg·A⁻¹·s⁻²]` = `[A]` — not m/s ✗

The code drops γ from the group velocity, replacing `4γ` with `2/μ₀`. Since `4γ ≈ 7.04×10¹¹` but `2/μ₀ ≈ 1.59×10⁶`, the code underestimates v_g by a factor of `4γμ₀/2 = 2γμ₀ ≈ 4.4×10⁵`.

**Numerical impact** (YIG defaults: A=4 pJ/m, Ms=1.4×10⁵ A/m, d_waveguide=1 μm, k=π/d=3.14×10⁶ rad/m):

| Quantity | Code (wrong) | Correct |
|---|---|---|
| v_g | 1.43×10⁻⁴ m/s | 63.2 m/s |
| λ_prop = v_g/(α·ω) | ~10⁻¹¹ m | ~7 μm |
| transit time τ | ~10⁶ ps | ~1.6 ns |

All downstream FoMs (`magnon_propagation_length_lambda`, `waveguide_transit_time_tau`, `magnon_FoM_xi`) are consequently wrong by the same factor of ~4.4×10⁵.

**Reference:** Kalinikos & Slavin, *J. Phys. C* 19, 7013 (1986); Chumak et al., *Nature Physics* 11, 453 (2015), Eq. (1). Group velocity ∂ω/∂k = 4γAk/Ms.

**Concrete fix:**

```python
# device_fom.py line 677 — add gamma to the group velocity formula
from maglab.physics.constants import GAMMA_E
gamma_0 = abs(GAMMA_E)
v_g = 4.0 * gamma_0 * A * k_mode / Ms  # dω/dk = 4γAk/Ms [m/s]
```

---

### FINDING 3 — LOW: `spin_valve_sensor_fom` NEF formula has parameter unit mismatch — `noise_floor` documented as [V/√Hz] but formula requires [Ω/√Hz]

**File / line:** `maglab/analysis/device_fom.py:442–443`

**Defect:**

```python
# noise_floor documented as [V/sqrt(Hz)] at line 432
NEF_Am_sqrtHz = noise_floor / (S_H * R_sq)   # line 442
NEF_T_sqrtHz = NEF_Am_sqrtHz * MU_0           # line 443
```

where `S_H = GMR / H_sat` [dimensionless / (A/m)] = [m/A].

**Dimensional analysis:**

If `noise_floor` has the documented unit [V/√Hz]:
```
S_H × R_sq: [m/A] × [Ω] = [m·V/A²]
NEF = [V/√Hz] / [m·V/A²] = [A²/(m·√Hz)]   ← not [A/(m·√Hz)]
```

The formula is dimensionally self-consistent **only if** `noise_floor` is interpreted as resistance noise spectral density [Ω/√Hz]:
```
NEF = [Ω/√Hz] / ([m/A] × [Ω]) = [A/(m·√Hz)]   ✓
NEF_T = NEF × μ₀: [A/m/√Hz] × [T·m/A] = [T/√Hz]   ✓
```

The docstring on line 432 documents `noise_floor` as "Voltage noise spectral density [V/√Hz] (white-noise floor)." But a physical voltage noise [V/√Hz] requires a bias current to convert to a field-equivalent noise; the formula never includes a bias current, which means the intent must have been resistance noise [Ω/√Hz].

**Impact:** Any caller who provides the Johnson-Nyquist voltage noise `S_n = sqrt(4·k_B·T·R)` [V/√Hz] will get NEF inflated by a dimensionally meaningless factor proportional to 1/A. The computed `noise_equivalent_field_T_sqrtHz` FoM is correct only if the user happens to supply resistance noise in the `noise_floor` argument despite the [V/√Hz] documentation.

**Concrete fix:** Change the parameter docstring from `[V/√Hz]` to `[Ω/√Hz]`, and update the default value accordingly (Johnson noise of 20 Ω at 300 K in 1 Hz BW is √(4·k_B·T·R) ≈ 1.8×10⁻¹⁰ V/√Hz, or in resistance noise terms √(4·k_B·T/R) ≈ 9×10⁻¹² Ω/√Hz — quite different from the default 1×10⁻⁹). The formula itself is then correct.

```python
# device_fom.py argument documentation fix:
noise_floor: float = 1e-9,  # Resistance noise spectral density [Ω/√Hz]
# And in docstring:
#     noise_floor: Resistance noise spectral density [Ω/√Hz] (white-noise floor of sensor resistance).
```

---

## Non-Findings

Investigated and dismissed (no genuine defect found):

- **R7 ξ fix (`sot_harmonic_hall.py:222`)** — Confirmed fixed: `c[1] / (4.0 * c[0])`. Comment block above correctly derives this from R_AHE=2·c[0]. See R7 Fix Verification section.
- **`walker_breakdown_field` (`formulas.py:162`)** — `alpha * K / (2.0 * MU_0 * Ms)`. Correct with factor of 2. Not affected by FINDING 1 (which is in `device_fom.py` only).
- **`dw_velocity_below_walker` (`formulas.py:227`)** — `gamma * delta * MU_0 * H / (1+alpha²)`. Correct Schryer-Walker formula. Verified.
- **`walker_velocity` (`formulas.py:193`)** — R6 fix `gamma * Delta * MU_0 * Ms / 2.0` confirmed. Dim: [rad/(s·T)] × [m] × [T·m/A] × [A/m] = m/s. Correct.
- **`spinwave_dispersion_fm` (`formulas.py:336–338`)** — `omega_H + omega_ex = gamma*MU_0*H + gamma*(2A/Ms)*k²`. Verified: μ₀ cancels in exchange term. Correct (Kalinikos-Slavin 1986). NOTE: `magnon_device_fom` derives v_g from this dispersion but makes an error in differentiation — that is FINDING 2, not a defect in `formulas.py`.
- **`afmr_frequency` (`formulas.py:491`)** — `(gamma/2π)*MU_0*sqrt(2*H_E*H_A)`. Correct with product<0 guard. Numerically verified for MnF2. Correct.
- **`ferrimagnet_compensation_freq` (`formulas.py:535`)** — Returns `omega/(2π)` in Hz. R5 fix retained. Correct.
- **`bloch_wall_width/energy` (`formulas.py:100, 129`)** — `π·sqrt(A/K)` and `4·sqrt(AK)`. K≤0 guard. Correct per Hubert & Schäfer (1998).
- **`skyrmion_radius_dmi` / `skyrmion_stability_criterion` (`formulas.py:269, 296`)** — K_eff = K − μ₀Ms²/2. Guards for K_eff≤0 and A≤0. Correct per Bogdanov & Hubert (1994).
- **`skyrmion_hall_angle` (`formulas.py:638`)** — Uses `atan2(G, alpha*D_norm)` correctly. Thiele (1973). Correct.
- **`heisenberg_to_exchange_stiffness` (`formulas.py:575`)** — `n_atoms*J*S²*z*a²/6`. Coey (2010) Eq.(5.86). Correct.
- **`spin_diffusion_length` (`formulas.py:597`)** — `sqrt(D_s*tau_sf)`. Valet & Fert (1993). Correct.
- **`kittel_freq_in_plane/out_of_plane` (`formulas.py:388, 412`)** — Standard Kittel formulas. `abs()` guards against PMA regime in OOP. Correct.
- **`sot_efficiency` (`formulas.py:453`)** — Conductance-ratio model. Dimensionless. Correct.
- **`DW1DModel.walker_field` (`dw_1d.py:126`)** — `alpha*K_perp/(2*MU_0*Ms)`. Factor of 2 confirmed correct. Note: `racetrack_fom` does NOT call this function; it reimplements the formula with the missing factor (FINDING 1).
- **`FMRKittel.forward()/fit()` (`fmr_kittel.py`)** — H_Am = H_res/MU_0 conversion correct. `np.abs(H_Am*(H_Am+M_eff))` guards sqrt. R4 fix retained. Correct.
- **`GilbertDamping.forward()/fit()` (`gilbert_damping.py`)** — ΔH = ΔH₀ + (2α/γ')·f. Dim consistent in GHz/T units. Correct.
- **`DMIEffect.forward()/fit()` (`dmi.py`)** — `2*gamma_p*D_i*k/Ms` (μ₀ cancels). Consistent with Di et al. PRL 114, 047201 (2015). Correct.
- **`SpinPumpingISHE.forward()/fit()` (`spin_pumping_ishe.py`)** — `(gamma_rad*HBAR*g_eff)/(4π·Ms·d_FM)`. R5 fix confirmed. No MU_0 in denominator. Consistent with Mosendz PRB 82, 214403 (2010). Correct.
- **`SpinPumpingISHE.v_ishe`** — `θ_SH·λ·tanh(d/(2λ))·ρ·j_s·w`. Dim: [1]×[m]×[1]×[Ω·m]×[A/m²]×[m] = [V]. Correct.
- **`SMREffect.fit()` (`smr.py`)** — `long_specs` restricts to ρ₀ and Δρ₁; Δρ₂ reported as NaN. R5 fix retained. Correct.
- **`STFMREffect.spin_hall_angle()` (`stfmr.py:267`)** — Per rounds R4–R7 consensus: t_NM factor is dimensionally required. Not re-flagged per standing instruction.
- **`SOTHarmonicHall.phe_corrected()` (`sot_harmonic_hall.py:296–301`)** — `H_DL = (H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)`. Correct Hayashi (2014) Eq.(S7). Division guard `abs(denom) < 1e-15`. Correct.
- **`LLG2SublatticeModel._llg2sl_rk4` (`llg_2sublattice.py:252–271`)** — Exchange field sign: `H_eff_a = H_ext − H_E·m_b + H_A·m_a[2]·ẑ`. Sign correct for AFM coupling (H_E > 0, opposes sublattice b). LLG form uses gamma_eff = γ/(1+α²). MU_0 conversion in mxH. Normalization present. Correct.
- **`MacrospinModel._llg_rk4` (`macrospin.py:188–241`)** — Slonczewski DL torque `tau_DL*(m×m_p×m)`, FL torque `tau_FL*(m×m_p)`. Oversampled internal grid present. Normalization step present. Ring-down model `mz(t) = 1−A·exp(−α·ω₀·t)·cos(ω₀·t)` correct (underdamped FMR). R4 fix retained. Correct.
- **`ThieleModel.forward()` (`thiele.py:120–152`)** — `v_x = α·D·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard present. Thiele (1973). Correct.
- **`AnomalousHallEffect`/`TopologicalHallEffect`** — `ρ_xy = R_0·B + μ₀·R_s·M`. Dim: [m³/C]×[T] + [T·m/A]×[m³/C]×[A/m] = [Ω·m]. Both correct.
- **`CurieTemperatureModel._power_law` (`curie_temperature.py:151`)** — T_C guard `max(T_C, 1.0)`, `np.clip(reduced, 0, None)` prevents complex power. Zero-crossing by interpolation. Correct.
- **`HysteresisLoop.extract_loop_params` (`hysteresis.py:149–195`)** — M_r/H_c warns (not silently fails) when data doesn't cross zero. No physics issue.
- **`TYJScaling` (`tyj_scaling.py`)** — `ρ_AHE = a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009). Linear init via lstsq. Correct.
- **`MuMax3._generate_mx3` B_ext conversion (`mumax3.py:105`)** — `H[A/m] × 1.25663706212e-6 [T·m/A] = B[T]`. MuMax3 takes B_ext in Tesla. Correct.
- **`OOMMFGenerateMIF2` (`oommf.py:53`)** — `_mu_0 = 1.25663706212e-6` used for H→B conversion. OOMMF `Oxs_FixedZeeman` takes field in Tesla. Conversion correct.
- **`SOTHarmonicHall.forward()` (`sot_harmonic_hall.py:164–166`)** — `(H_DL_raw/H_ext)·cos(φ) + (H_FL_raw/H_ext)·cos(2φ)·cos(φ)`. Correct Hayashi (2014) Eq.(6) two-term model.
- **`sot_mram_fom` j_c formula (`device_fom.py:101`)** — `j_c = 2α·e·μ₀·Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Dim: [A·s²·kg⁻¹] × [kg·m·A⁻²·s⁻²] × [A/m] × [m] × [A/m] / [kg·m²·s⁻¹] = A/m². Numerically consistent with Dieny et al. Nat. Electron. 3, 446 (2020). Correct.
- **`stt_mram_fom` j_c formula (`device_fom.py:179`)** — Same form without the Ms/2 term (different geometry). Dimensionally correct.
- **`spin_orbit_logic_fom` tau_sw formula (`device_fom.py:553`)** — `τ_sw = π/(α·ω₀)` with ω₀ = γ·μ₀·H_k. Capped at 10 ns. Sensible estimate for damping-determined switching. No formula error.
- **`magnon_device_fom` propagation length formula (`device_fom.py:680`)** — `λ_prop = v_g / (α·ω)`. Formula is correct in structure, but v_g is wrong (FINDING 2). The formula itself would give correct λ with correct v_g.
- **`OrbitalHallEffect` rank-3 tensor (`orbital_hall.py:51–197`)** — Shape (3,3,3) enforced. Antisymmetric component correctly applied. No physics issue.
- **`PlanarHallEffect.forward()` (`planar_hall.py:101`)** — `(Δρ/2)·sin(2φ)`. Standard PHE formula. Correct.
- **`OrdinaryHallEffect.carrier_density()` (`ordinary_hall.py:135`)** — `1/(|R_H|·e)`. Correct.
- **`USMREffect.forward()` (`usmr.py:177–180`)** — `ε·j₀·sin(φ) + offset` (angle mode) and `ε·j + offset` (current mode). Consistent with Avci et al. 2015. Correct.
- **`GMRTMREffect.forward()` (`gmr_tmr.py:129`)** — `G_0·(1 + (TMR/2)·cosθ)` with Julliere formula `TMR = 2P₁P₂/(1−P₁P₂)`. Guard `abs(denom) < 1e-15`. Correct.
- **`LLGModel._llg_rhs` (`llg.py:120–128`)** — H_eff multiplied by MU_0 before cross product. gamma_eff = γ/(1+α²). STT torques correctly structured. Correct.
- **`AMREffect.forward()` (`amr.py:117`)** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975). Correct.
- **`CalibrationEntry.apply/unapply` (`calibration.py:65–73`)** — `corrected = value × factor + offset`. Inverse `(corrected − offset) / factor` with zero-factor guard. Correct.
- **`CorrectionPipeline.total_uncertainty()` (`calibration.py:239`)** — GUM quadrature `sqrt(Σσ²)`. Correct.
- **`GUM UncertaintyBudget.total()` (`calibration.py:327`)** — `sqrt(Σσᵢ²)` combined standard uncertainty per JCGM 100:2008. Correct.

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **MEDIUM** | `analysis/device_fom.py:225` | `racetrack_fom` Walker breakdown field missing factor of 2: uses `alpha*K_perp/(MU_0*Ms)` instead of `alpha*K_perp/(2*MU_0*Ms)`. Inflates H_W and max DW velocity by 2× relative to Schryer-Walker (1974). Inconsistent with `formulas.py:162` and `dw_1d.py:126` which both use the factor of 2. |
| 2 | **MEDIUM** | `analysis/device_fom.py:677` | `magnon_device_fom` spin-wave group velocity `v_g = 2*A*k/(mu0*Ms)` is dimensionally wrong (yields A not m/s). Correct formula from dispersion ω(k) = γμ₀H₀ + γ(2A/Ms)k² is `v_g = ∂ω/∂k = 4γAk/Ms`. Code underestimates v_g by factor ~4.4×10⁵. All magnon FoMs (propagation length, transit time, magnon FoM ξ) are wrong by the same factor. |
| 3 | **LOW** | `analysis/device_fom.py:432, 442–443` | `spin_valve_sensor_fom` parameter `noise_floor` is documented as [V/√Hz] but the NEF formula `noise_floor/(S_H*R_sq)` requires [Ω/√Hz] for dimensional consistency. If a caller supplies voltage noise as documented, the NEF result is physically meaningless. Fix: update documentation to [Ω/√Hz] (resistance noise spectral density). |
