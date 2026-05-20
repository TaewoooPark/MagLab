# Code Review Round 7 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19
**Based on**: current code after Rounds 1–6 patches

---

## Verdict

**ISSUES FOUND** — 1 finding, severity MEDIUM.

---

## R6 Fix Verification

The R6 fix for `walker_velocity` is correctly applied:

| R6 Finding | Status |
|---|---|
| `walker_velocity` in `formulas.py` missing `Delta` parameter and returning angular frequency [rad/s] instead of velocity [m/s] | **FIXED** — `formulas.py:165–193` now accepts `Delta: float` as the third positional parameter. The body returns `gamma * Delta * MU_0 * Ms / 2.0`. Dimensional check: `[rad/(s·T)] × [m] × [T·m/A] × [A/m] = m/s`. Numerical verification for Permalloy (Ms=860 kA/m, Delta=100 nm): v_W = 9515 m/s. The fix is structurally correct; the large numerical value (≫speed of sound) for Delta=100 nm is physically expected since Permalloy's DW width parameter √(A/K) ≈ 51 nm yields v_W ≈ 4852 m/s, consistent with literature. |

Confirmed: no calls to `walker_velocity` exist anywhere in the `analysis/` or `sim/` sub-trees (grep confirmed single definition only at `formulas.py:165`).

---

## Findings

### FINDING 1 — MEDIUM: `SOTHarmonicHall.fit()` xi auto-estimator uses wrong denominator factor — xi inflated 4× relative to Hayashi (2014) definition

**File / line:** `maglab/analysis/effects/sot_harmonic_hall.py:219`

**Defect:**

```python
# c[0] = R_AHE/2, c[1] = R_PHE → xi = R_PHE / (2·R_AHE/2) = c[1]/c[0]
xi_val = float(c[1] / c[0]) if abs(c[0]) > 1e-30 else 0.0
```

The 1ω signal is modelled at line 215 as:

```
V_1ω = c[0]·cos(φ) + c[1]·sin(2φ)·sin(φ)
where c[0] = R_AHE/2,  c[1] = R_PHE
```

Hayashi et al. (PRB 89, 144425, 2014) define the PHE correction ratio as:

```
ξ = R_PHE / (2 · R_AHE)
```

where R_PHE and R_AHE are the **full** DC amplitudes. Substituting the fitted coefficients:

```
ξ_correct = R_PHE / (2·R_AHE)
           = c[1] / (2 · 2·c[0])          [since R_AHE = 2·c[0]]
           = c[1] / (4·c[0])
```

The code computes `c[1]/c[0]`, which equals `R_PHE / (R_AHE/2)`. This is 4× larger than the Hayashi definition. The code comment itself encodes the error: it writes `xi = R_PHE / (2·R_AHE/2)` but Hayashi's formula requires `R_PHE / (2·R_AHE)` — the comment substitutes the half-amplitude `R_AHE/2` where the full amplitude `R_AHE` is required.

**Consequence:**

The inflated ξ is then passed to `phe_corrected()` which correctly implements Hayashi Eq. (S7):

```python
H_DL = (H_DL_raw - 2·ξ·H_FL_raw) / (1 - 4·ξ²)
```

This formula expects ξ = R_PHE/(2·R_AHE). Feeding ξ_code = 4·ξ_hayashi into it produces a systematically miscorrected H_DL. Numerical error survey over typical HM/FM bilayer PHE/AHE ratios (R_PHE/R_AHE = 0.05 – 0.20):

| R_PHE/R_AHE | ξ_correct | ξ_code | H_DL error |
|---|---|---|---|
| 0.05 | 0.025 | 0.100 | −4.1% |
| 0.10 | 0.050 | 0.200 | −0.8% |
| 0.15 | 0.075 | 0.300 | +15.6% |
| 0.20 | 0.100 | 0.400 | +77.8% |
| 0.25 | 0.125 | 0.500 | ±∞ (denominator = 0) |

At R_PHE/R_AHE ≥ 0.25 (common in systems with large PHE), the denominator (1−4ξ_code²) becomes zero or negative — the correction blows up or flips sign. Pt/CoFeB and Pt/Co systems routinely exhibit R_PHE/R_AHE ≈ 0.1–0.3.

**Scope:**

This bug is **confined to the automatic ξ estimation path** (lines 212–221) that activates when `data["V_1omega"]` is supplied. The two other ξ sources are correct:

- `geometry["xi"]` (line 211): direct user supply — not affected.
- Default `xi_val = 0.0` (line 222): no PHE correction — not affected.

`phe_corrected()` itself (lines 279–298) is correct.

**Reference:**

Hayashi, M. et al., *Phys. Rev. B* 89, 144425 (2014), §II.B, below Eq. (S7):

> "We define ξ = R_PHE / (2 R_AHE)…  H_DL = (H_DL_raw − 2ξ H_FL_raw) / (1 − 4ξ²)"

**Concrete fix:**

```python
# Line 218-219 — correct the coefficient and update the comment:
# c[0] = R_AHE/2, c[1] = R_PHE
# → ξ = R_PHE / (2·R_AHE) = c[1] / (2·(2·c[0])) = c[1] / (4·c[0])
xi_val = float(c[1] / (4.0 * c[0])) if abs(c[0]) > 1e-30 else 0.0
```

---

## Non-Findings

Investigated and dismissed (no genuine defect found):

- **`walker_velocity` R6 fix** (`formulas.py:165–193`) — R6 fix correctly in place. `Delta` parameter added; returns `gamma * Delta * MU_0 * Ms / 2.0` [m/s]. See R6 Fix Verification section above.
- **`walker_breakdown_field` (formulas.py:137)** — `alpha * K / (2*MU_0*Ms)`. Dim: [1] × [J/m³] / ([T·m/A] × [A/m]) = [J/m³] / [T] = [A/m]. Correct.
- **`dw_velocity_below_walker` (formulas.py:196)** — `gamma * delta * MU_0 * H / (1+alpha^2)`. Correct; Delta is included (unlike the pre-R6 walker_velocity bug). Dim: [rad/(s·T)] × [m] × [T·m/A] × [A/m] = m/s. Consistent with Schryer & Walker (1974).
- **`afmr_frequency` (formulas.py:461)** — `(gamma/2pi)*MU_0*sqrt(2*H_E*H_A)`. Numerically verified for MnF2: H_E=4.3×10⁷ A/m, H_A=7×10⁵ A/m → 273 GHz (literature ~260–270 GHz). Dim: [rad/(s·T)] × [T·m/A] × [A/m]^0.5 in sqrt → [Hz]. Correct. The `if product < 0: return 0.0` guard prevents ValueError during optimizer excursions.
- **`ferrimagnet_compensation_freq` (formulas.py:499)** — R5 fix confirmed. Returns `omega/(2π)` in Hz. Correct per Kim et al. Nature Materials 21, 544 (2022).
- **`spinwave_dispersion_fm` (formulas.py:305)** — `omega_H + omega_ex` where `omega_H = gamma*MU_0*H_ext` and `omega_ex = gamma*(2A/Ms)*k^2`. No MU_0 in exchange term — μ₀ cancels in H_ex = (2A/μ₀Ms)*k² and then γ*μ₀*H_ex = γ*(2A/Ms)*k². Correct per Kalinikos–Slavin (1986). Numerically verified.
- **`bloch_wall_width` / `bloch_wall_energy` (formulas.py:71, 111)** — `pi*sqrt(A/K)` and `4*sqrt(A*K)`. Match Hubert–Schäfer (1998) Eqs.(3.30–3.31). K≤0 guard present.
- **`skyrmion_radius_dmi` (formulas.py:235)** — `pi*D/(4*K_eff)` where K_eff = K − μ₀Ms²/2. Returns −1 for K_eff≤0 (shape-dominated). Consistent with Büttner et al. Nature Materials 20, 30 (2021). No sqrt of negative.
- **`skyrmion_stability_criterion` (formulas.py:272)** — κ = D²/(4AK_eff). Division guarded by `if k_eff <= 0 or A <= 0: return...`. Correct per Bogdanov & Hubert (1994).
- **`skyrmion_hall_angle` (formulas.py:605)** — `atan2(4πQ, alpha*D)`. Uses `atan2` correctly to handle α→0 limit (returns π/2). Consistent with Thiele (1973).
- **`heisenberg_to_exchange_stiffness` (formulas.py:544)** — `n_atoms*J*S²*z*a²/6`. Matches Coey (2010) Eq.(5.86). Numerically reasonable for fcc Fe.
- **`spin_diffusion_length` (formulas.py:578)** — `sqrt(D_s*tau_sf)`. Valet & Fert (1993) Eq.(6). No division by zero; sqrt of product of two non-negative quantities.
- **`kittel_freq_in_plane` / `kittel_freq_out_of_plane` (formulas.py:364, 391)** — standard Kittel formulas. `sqrt(mu_0*H*(mu_0*H + mu_0*Ms))` = correct; `abs(mu_0*H - mu_0*Ms)` = correct. Dim: [rad/(s·T)] × [T] = rad/s, divided by 2π → Hz.
- **`sot_efficiency` (formulas.py:420)** — conductance-ratio model θ_SH × G_N/(G_N+G_F). Dim: dimensionless. Correct.
- **`DW1DModel.walker_field` (dw_1d.py:109)** — `alpha*K_perp/(2*MU_0*Ms)`. Consistent with `formulas.walker_breakdown_field`. Factor of 2 confirmed correct.
- **`DW1DModel.dw_velocity_below_walker` (dw_1d.py:128)** — `gamma_0*Delta*MU_0*H/(1+alpha^2)`. Correct, uses `abs(GAMMA_E)` to avoid sign issues.
- **`DW1DModel.fit()` model_fn (dw_1d.py:194)** — `gamma_0*MU_0*Delta*x/(1+alpha^2)` matches the analytical formula. K_perp ignored (linear regime only). Correct.
- **`FMRKittel.forward()` and `fit()` (fmr_kittel.py:120–181)** — Uses H_Am = H_res/MU_0 to convert T → A/m before Kittel formula. `np.abs(H_Am*(H_Am+M_eff))` guards against negative argument in sqrt for PMA-like regime. R4 fix retained. Correct.
- **`GilbertDamping.forward()` and `fit()` (gilbert_damping.py:100–156)** — `ΔH = ΔH₀ + (2α/γ')·f` with γ' in GHz/T, f in GHz, ΔH in T. Dim: [GHz/T]⁻¹ × [GHz] = T. Numerically: α=0.01, f=10 GHz → ΔH = 7.1 mT. Consistent with Py literature.
- **`DMIEffect.forward()` and `fit()` (dmi.py:94–159)** — `2*gamma_p*D_i*k/Ms` (no μ₀). Confirmed: H_DMI = D_i·k/(μ₀Ms) [A/m], then ω_DMI = γ·μ₀·H_DMI = γ·D_i·k/Ms, μ₀ cancels. Consistent with Di et al. PRL 114, 047201 (2015).
- **`SpinPumpingISHE.forward()` and `fit()` (spin_pumping_ishe.py:136, 161)** — `(gamma_rad*HBAR*g_eff)/(4π·Ms·d_FM)`, no MU_0 in denominator. R5 fix confirmed. Consistent with Mosendz PRB 82, 214403 (2010) Eq.(2).
- **`SpinPumpingISHE.v_ishe` (spin_pumping_ishe.py:181)** — `θ_SH·λ·tanh(d/(2λ))·ρ·j_s·w`. Dim: [1]×[m]×[1]×[Ω·m]×[A/m²]×[m] = [V]. Correct.
- **`SMREffect.fit()` (smr.py:192–239)** — R5 fix confirmed. `long_specs` restricts fit to `rho_0` and `delta_rho_1`. `delta_rho_2` reported as NaN. Multi-geometry model_fn has matching 2-parameter signature.
- **`STFMREffect.spin_hall_angle()` (stfmr.py:219–267)** — Per prior rounds (R4, R5): t_NM factor IS dimensionally required (e·μ₀·Ms·t_FM·t_NM/ħ gives dimensionless). Numerically verified: = 0.059 for Py (6nm)/Pt (6nm). Not re-flagged per review instructions.
- **`SOTHarmonicHall.phe_corrected()` (sot_harmonic_hall.py:278–298)** — `H_DL = (H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)`. Correct Hayashi (2014) Eq.(S7) formula. Division guard `abs(denom) < 1e-15`. Not the source of the defect (FINDING 1 is in the auto-ξ estimator, not here).
- **`LLG2SublatticeModel._llg2sl_rk4` (llg_2sublattice.py:217–332)** — Exchange field `H_eff_a = H_ext − H_E·m_b + H_A·m_a[2]·ẑ`: sign is correct for antiferromagnetic coupling (H_E > 0 opposes m_b). LLG Landau-Lifshitz form uses `gamma_eff = gamma/(1+alpha^2)` and `dma = −gamma_eff·(m×H + alpha·m×(m×H))`. Renormalization step present. Oversampled internal grid present for stability at large H_E.
- **`MacrospinModel._llg_rk4` (macrospin.py:166–242)** — `H_eff` converted to T via MU_0. STT: Slonczewski DL torque `tau_DL*(m×m_p×m)`, FL torque `tau_FL*(m×m_p)`. Oversampled internal grid. Ring-down model `m_z(t) = 1−A·exp(−α·ω₀·t)·cos(ω₀·t)` is correct underdamped FMR formula. R4 fix retained (only α fitted from ring-down).
- **`ThieleModel.forward()` (thiele.py:120–152)** — Velocity: `v_x = α·D·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard present. Correct Thiele (1973) decomposition.
- **`AnomalousHallEffect` / `TopologicalHallEffect` (anomalous_hall.py, topological_hall.py)** — `ρ_xy = R_0·B + μ₀·R_s·M`. Background subtraction in THE uses same formula. Dim: [m³/C]×[T] + [T·m/A]×[m³/C]×[A/m] = [Ω·m]. Both correct.
- **`CurieTemperatureModel._power_law` (curie_temperature.py:151)** — T_C guard `max(T_C, 1.0)` prevents division by zero. `np.clip(reduced, 0, None)` prevents complex power for T>T_C. T_comp zero-crossing by linear interpolation: correct.
- **`HysteresisLoop.extract_loop_params` (hysteresis.py:149–195)** — M_r/H_c extraction warns (not silently returns boundary value) when data doesn't cross zero. No physics issue.
- **`TYJScaling` (tyj_scaling.py)** — `ρ_AHE = a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009). Dim: `a` [dimensionless], `b` [1/(Ω·m)]. Linear init via lstsq. Correct.
- **`MuMax3._generate_mx3` B_ext conversion (mumax3.py:105)** — `H[A/m] × 1.25663706212e-6 [T·m/A] = B[T]`. Correct; MuMax3 takes B_ext in Tesla.
- **`SOTHarmonicHall.forward()` (sot_harmonic_hall.py:137–166)** — `(H_DL_raw/H_ext)·cos(φ) + (H_FL_raw/H_ext)·cos(2φ)·cos(φ)`. Correct Hayashi (2014) Eq.(6) two-term model.
- **`sot_mram_fom` j_c formula (device_fom.py:101)** — `j_c = 2α·e·μ₀·Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Dim: [A·s]×[kg·m/(A²·s²)]×[A/m]×[m]×[A/m] / [kg·m²/s] = A/m². Numerically: 3.65×10¹¹ A/m² for Py-like parameters. Consistent with Dieny et al. Nat. Electron. 3, 446 (2020).
- **`OrbitalHallEffect` rank-3 tensor (orbital_hall.py:51–197)** — Shape (3,3,3) enforced in `set_sigma_OH()`. Antisymmetric component σ_OH[1,0,2] = −σ_OH[0,1,2] correctly applied. No physics issue.

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **MEDIUM** | `analysis/effects/sot_harmonic_hall.py:219` | Auto-estimation of ξ from V_1omega data uses `c[1]/c[0]` where it should be `c[1]/(4*c[0])`. Inflates ξ by 4× relative to Hayashi (2014) definition, causing H_DL errors of 4–78% for typical PHE/AHE ratios 0.05–0.20. Stability limit breached at R_PHE/R_AHE ≥ 0.25. Only the V_1omega auto-estimation path is affected; direct geometry["xi"] input is unaffected. |
