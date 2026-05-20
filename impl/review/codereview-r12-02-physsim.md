# Code Review Round 12 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-20
**Based on**: current code after Rounds 1–11 patches

---

## Verdict

**ISSUES FOUND** — 1 finding, severity LOW.

One genuine defect was found: the `SpinPumpingISHE` class in `spin_pumping_ishe.py` carries a factually incorrect physics formula in two docstrings (class-level and `forward()` method). Both docstrings write `Δα = (γħg↑↓)/(4π·μ₀·M_s·d_FM)` — i.e., with `μ₀` in the denominator — while the code correctly implements the formula **without** `μ₀`, consistent with the primary literature (Tserkovnyak et al. PRL 88, 117601 (2002); Mosendz et al. PRB 82, 214403 (2010)). The computed results are physically correct; only the user-facing documentation is wrong. One inline comment within the same function correctly states "no μ₀ in denominator", creating an internal contradiction. The R11 review inadvertently reproduced the wrong docstring formula in its non-findings table without noticing that the code differed.

An independent fresh re-audit of all other files in the domain confirmed no additional genuine defects.

---

## Findings

### Finding 1 — LOW

**Location**: `maglab/analysis/effects/spin_pumping_ishe.py` lines 36, 109–112

**Defect**: The class-level docstring (line 36) and the `forward()` method docstring (lines 109–112) both state the formula for the spin-pumping linewidth enhancement as:

```
Δα = (γ ħ g↑↓) / (4π μ₀ M_s d_FM)    ← docstrings (WRONG)
```

The code at line 136 correctly implements:

```python
prefactor = (gamma_rad * HBAR * g_eff) / (4.0 * np.pi * Ms * d_FM)  # no μ₀
```

**Dimensional analysis**:

- Code formula (no μ₀): `[rad/(s·T)] × [J·s] × [m⁻²] / ([A/m] × [m])`. With `T = kg/(A·s²)` and `J = kg·m²/s²`: numerator → `[rad·A]`; denominator → `[A]`; ratio → `[rad]` = dimensionless. ✓
- Docstring formula (with μ₀): inserting `[T·m/A]` into the denominator gives `[rad·A] / ([T·m/A]·[A]) = [rad·A²/(T·m·A)] = [rad·A/(kg·m/s²·m)] = [rad·A·s²/(kg·m²)]` ≠ dimensionless. ✗ — dimensionally inconsistent.

**Numerical check**: For Py(5 nm)/Pt at `g_eff = 2.1×10¹⁹ m⁻²`, `Ms = 860 kA/m`, `d_FM = 5 nm`:
- Code result: `Δα ≈ 7.2×10⁻³` — matches literature (Py/Pt: 3×10⁻³ to 10⁻²). ✓
- Docstring formula (with μ₀): `Δα ≈ 5700` — unphysical by four orders of magnitude. ✗

**Literature**: Tserkovnyak, Brataas, Bauer, *Phys. Rev. Lett.* 88, 117601 (2002), Eq. (3):
```
Δα = (g_s μ_B / (4π M_s t_F)) · Re[g_mix]
   = (γ ħ / (4π M_s t_F)) · Re[g_mix]     [no μ₀]
```
Mosendz et al., *Phys. Rev. B* 82, 214403 (2010), Eq. (2) is consistent with this form in SI units without μ₀.

The formula WITH μ₀ arises only when γ is interpreted as the Landé g-factor form γ_0 = μ₀·γ (the "spectroscopic" convention used in CGS-adjacent notation), which is NOT the convention used in this codebase (GAMMA_E = 1.7609×10¹¹ rad/(s·T) is the standard SI gyromagnetic ratio; multiplying by μ₀ would double-count).

**Impact**: Code behavior is correct — all numerical results produced by `forward()` and `fit()` are physically accurate. However, any user reading the class or method docstring to understand or reproduce the formula externally would obtain wrong numbers. The internal contradiction (docstring says μ₀; inline comment at lines 134–135 says "no μ₀") is also confusing.

**Fix**: Remove `μ₀` from the docstring formula in both locations.

```python
# Line 36 (class docstring) — change:
#   Δα = (γ ħ g↑↓) / (4π μ₀ M_s d_FM)
# to:
    Δα = (γ ħ g↑↓) / (4π M_s d_FM)

# Lines 109–112 (forward() docstring) — change:
#   Compute Δα(d_NM) = γħg↑↓ / (4πμ₀M_s·d_FM) · tanh(d_NM / (2λ_sf)).
#   Δα(d_NM) = (γħg↑↓)/(4π·μ₀·M_s·d_FM) · tanh(d_NM / (2λ_sf))
# to:
    Compute Δα(d_NM) = γħg↑↓ / (4π M_s·d_FM) · tanh(d_NM / (2λ_sf)).
    Δα(d_NM) = (γħg↑↓)/(4π·M_s·d_FM) · tanh(d_NM / (2λ_sf))
```

Reference: Tserkovnyak, Brataas, Bauer, *Phys. Rev. Lett.* 88, 117601 (2002), Eq. (3).

---

## Non-Findings

Investigated and dismissed (no genuine defect found). All formulas independently re-verified in this round.

- **`exchange_length` (`formulas.py:55`)** — `√(2A/(μ₀Ms²))`. Permalloy: 5.3 nm (literature 5.3 nm). ✓
- **`bloch_wall_width` (`formulas.py:100`)** — `π√(A/K)`. YIG: 255 nm. Factor of π correct per Hubert & Schäfer (1998). ✓
- **`bloch_wall_energy` (`formulas.py:127`)** — `4√(AK)`. K ≤ 0 guard present. ✓
- **`walker_breakdown_field` (`formulas.py:162`)** — `α·K/(2·μ₀·Ms)`. Factor of 2 confirmed Schryer-Walker (1974). ✓
- **`walker_velocity` (`formulas.py:193`)** — `γ·Δ·μ₀·Ms/2`. Dimensional analysis: `[rad/(s·T)]·[m]·[T·m/A]·[A/m] = [m/s]`. ✓
- **`dw_velocity_below_walker` (`formulas.py:227`)** — `γ·δ·μ₀·H/(1+α²)`. ✓
- **`skyrmion_radius_dmi` (`formulas.py:269`)** — `πD/(4K_eff)`, K_eff > 0 guard. ✓
- **`skyrmion_stability_criterion` (`formulas.py:296`)** — `D²/(4AK_eff)`. Guards for K_eff ≤ 0 and A ≤ 0. ✓
- **`spinwave_dispersion_fm` exchange term (`formulas.py:337`)** — `ω_ex = γ·(2A/Ms)·k²`. No μ₀ required because exchange effective field `H_ex = 2Ak²/μ₀Ms` multiplied by `γμ₀` gives `γ·2A·k²/Ms`. Dimensional analysis: `[rad/(s·T)]·[J/m]/[A/m]·[1/m²] = [rad/s]`. ✓
- **`kittel_freq_in_plane` (`formulas.py:388`)** — Numerically verified: 9.63 GHz at H = 0.1 T, Ms = 860 kA/m. ✓
- **`kittel_freq_out_of_plane` (`formulas.py:412`)** — `abs()` guard for H < M_eff. ✓
- **`afmr_frequency` (`formulas.py:491`)** — `(γ/2π)·μ₀·√(2·H_E·H_A)`. Dimensional check: `[rad/(s·T)]·[T·m/A]·[A/m] = [rad/s]`. MnF₂ numerical check: 273 GHz vs. literature 262 GHz (4%). ✓
- **`ferrimagnet_compensation_freq` (`formulas.py:531`)** — `(|γ_a m_a − γ_b m_b|/(m_a+m_b))·μ₀·H_ex`. Dimensional analysis passes. ✓
- **`sot_efficiency` (`formulas.py:451`)** — Conductance-ratio model; dimensionless result. ✓
- **`heisenberg_to_exchange_stiffness` (`formulas.py:575`)** — `n·J·S²·z·a²/6`. Dimensional check: `[m⁻³]·[J]·[m²] = [J/m]`. ✓
- **`spin_diffusion_length` (`formulas.py:597`)** — `√(D_s·τ_sf)`. `[m²/s·s]^½ = [m]`. ✓
- **`skyrmion_hall_angle` (`formulas.py:638`)** — `atan2(4πQ, α·D)`. Handles α = 0 correctly. Thiele (1973). ✓
- **`GilbertDamping.forward()` (`gilbert_damping.py:114`)** — `ΔH = ΔH₀ + (2α/γ')·f`. Units: `[T] + [1/(GHz/T)]·[GHz] = [T]`. Slope for Py: 0.714 mT/GHz. ✓
- **`FMRKittel.forward()` in-plane (`fmr_kittel.py:130`)** — H_res [T] converted to [A/m] via H/μ₀ before Kittel formula; correct unit chain. ✓
- **`SpinPumpingISHE.forward()` CODE (`spin_pumping_ishe.py:136`)** — Code is correct (no μ₀); gives Δα ≈ 7.2×10⁻³ for Py/Pt. Docstring is wrong (see Finding 1). ✓ (code) / ✗ (docstring)
- **`SpinPumpingISHE.v_ishe()` (`spin_pumping_ishe.py:204`)** — `θ_SH·λ_sf·tanh(d/(2λ_sf))·ρ_NM·j_s·w`. Dimensional: `[1]·[m]·[1]·[Ω·m]·[A/m²]·[m] = [V]`. ✓
- **`STFMREffect.spin_hall_angle()` t_NM factor (`stfmr.py:267`)** — Per rounds R4–R7 consensus and standing instruction: t_NM is dimensionally required. Not re-flagged. ✓
- **`GMRTMREffect.forward()` and `fit()` (`gmr_tmr.py:149,179`)** — R10 fix confirmed: amplitude is P1·P2 per Slonczewski (1989). ✓
- **`TopologicalHallEffect.forward()` and `extract_the()` (`topological_hall.py:113,177`)** — `ρ_xy − R_0·B − μ₀·R_s·M`. Nagaosa et al. RMP 82, 1539 (2010). Dimensional: R_0·B = [m³/C]·[T] = [Ω·m]; μ₀·R_s·M = [Ω·m]. ✓
- **`SOTHarmonicHall.fit()` ξ extraction (`sot_harmonic_hall.py:222`)** — `c[1]/(4·c[0])`. R7 fix retained: 1ω regression gives c[0] = R_AHE/2; ξ = c[1]/(4c[0]). ✓
- **`SOTHarmonicHall.phe_corrected()` (`sot_harmonic_hall.py:296`)** — `(H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)`. Denominator guard present. ✓
- **`AMREffect.forward()` (`amr.py:117`)** — `ρ_⊥ + Δρ·cos²θ`. McGuire & Potter (1975). ✓
- **`AnomalousHallEffect.forward()` (`anomalous_hall.py:115`)** — `R_0·B + μ₀·R_s·M`. Nagaosa et al. (2010) SI convention. ✓
- **`OrdinaryHallEffect.carrier_density()` (`ordinary_hall.py:135`)** — `1/(|R_H|·e)`. `[m⁻³]`. ✓
- **`TYJScaling.forward()` (`tyj_scaling.py:114`)** — `a·ρ_xx + b·ρ_xx²`. Tian, Ye, Jin PRL 103, 087206 (2009). ✓
- **`ThieleModel.forward()` (`thiele.py:147–149`)** — `v_x = αD·F/(α²D²+G²)`, `v_y = G·F/(α²D²+G²)`. Denominator guard present. Thiele (1973). ✓
- **`PlanarHallEffect.forward()` (`planar_hall.py:101`)** — `(Δρ/2)·sin(2φ)`. Taskin & Ando (2011). ✓
- **`USMREffect.forward()` (`usmr.py:177,179`)** — `ε·j₀·sin(φ) + offset` and `ε·j + offset`. Avci et al. (2015). ✓
- **`OrbitalHallEffect.forward()` (`orbital_hall.py:146`)** — Simplified approximate model, clearly labeled. ✓
- **`CurieTemperatureModel._power_law()` (`curie_temperature.py:166–169`)** — T_C bounded at 1 K; `np.clip(reduced, 0, None)` prevents complex power. ✓
- **`LLGModel._llg_rhs` (`llg.py:120–128`)** — H_eff [A/m] multiplied by μ₀ before cross product; `γ_eff = γ/(1+α²)`; STT torques correct. ✓
- **`LLGModel.precession_frequency()` (`llg.py:299`)** — `γ₀·μ₀·H_eff/(2π)·1e-9` [GHz]. Dimensional check passes. ✓
- **`LLG2SublatticeModel._llg2sl_rk4` exchange field sign (`llg_2sublattice.py:254–261`)** — `H_eff_a = H_ext − H_E·m_b + H_A·m_a[2]·ẑ`. AFM ground state check (m_a = +ẑ, m_b = −ẑ): `H_eff_a = (H_E+H_A)·ẑ` (stabilises m_a = +ẑ ✓). Keffer-Kittel (1952). ✓
- **`MacrospinModel.sw_switching_field()` (`macrospin.py:159–164`)** — `H_k/[(cos²θ)^(2/3) + (sin²θ)^(2/3)]^(3/2)`. Stoner-Wohlfarth (1948) astroid. Denominator guard present. ✓
- **`DW1DModel.walker_field()` (`dw_1d.py:126`)** — `α·K_⊥/(2·μ₀·Ms)`. Factor of 2 correct per Schryer-Walker (1974). ✓
- **`DW1DModel.dw_velocity_below_walker()` (`dw_1d.py:142`)** — `γ₀·Δ·μ₀·H/(1+α²)`. ✓
- **`SMREffect.fit()` delta_rho_2 → NaN (`smr.py:238`)** — NaN for parameter not identifiable from longitudinal data alone. R5 fix retained. ✓
- **`DMIEffect.forward()` (`dmi.py:118`)** — `2·γ_p·D_i·k/M_s`. No μ₀ in denominator. Confirmed against Di et al. PRL 114, 047201 (2015). ✓
- **`sot_mram_fom` j_c formula (`device_fom.py:101`)** — `2αeμ₀Ms·t_FM·(H_k+Ms/2)/(ħ·θ_SH)`. Dimensional: `[A/m²]`. ✓
- **`stt_mram_fom` j_c formula (`device_fom.py:179`)** — Same structure without Ms/2 demagnetization correction (PMA geometry). ✓
- **`racetrack_fom` Walker breakdown field (`device_fom.py:229`)** — `α·K_⊥/(2·μ₀·Ms)`. Factor-of-2 fix retained. ✓
- **`racetrack_fom` current-driven DW velocity (`device_fom.py:233`)** — `v≈1e-12·j`. Clearly labeled placeholder. ✓
- **`spin_valve_sensor_fom` NEF formula (`device_fom.py:455–456,472`)** — `NEF = noise_floor/(S_H·R_sq)` [A/(m·√Hz)], then `NEF_T = NEF·μ₀` [T/√Hz]. R9 fix retained. ✓
- **`spin_orbit_logic_fom` switching time (`device_fom.py:566`)** — `τ_sw = π/(α·γ·μ₀·H_k)`. Macrospin estimate. ✓
- **`magnon_device_fom` v_g formula (`device_fom.py:702`)** — `4·γ·A·k/Ms`. Dimensional: `[m/s]`. YIG defaults: v_g = 63.2 m/s. ✓
- **`magnon_device_fom` lambda_prop (`device_fom.py:705`)** — `v_g/(α·ω)`. Standard spin-wave amplitude 1/e decay length. ✓
- **`MuMax3._generate_mx3` B_ext conversion (`mumax3.py:105`)** — `H[A/m] × 1.25663706212e-6 = B[T]`. MuMax3 requires `B_ext` in Tesla. μ₀ value correct. ✓
- **`OOMMFGenerateMIF2` (`oommf.py:53,124`)** — `_mu_0 = 1.25663706212e-6` for H→B conversion; `gamma_G = 1.760859630e11 rad/(s·T)` (= GAMMA_E). Both correct. ✓
- **`CalibrationEntry.apply/unapply` (`calibration.py:65–73`)** — `corrected = value × factor + offset`. Zero-factor guard in `unapply`. ✓
- **`GUM UncertaintyBudget.total()` (`calibration.py:327`)** — `√(Σσᵢ²)`. JCGM 100:2008 ✓.
- **`GAMMA_E` value (`constants.py:68`)** — 1.760859630×10¹¹ rad/(s·T). CODATA 2022. ✓
- **`MU_0` value (`constants.py:26`)** — 1.25663706212×10⁻⁶ H/m. CODATA 2022. ✓
- **`HBAR` value (`constants.py:32`)** — 1.054571817×10⁻³⁴ J·s (exact). CODATA 2022. ✓
- **`E_CHARGE` value (`constants.py:44`)** — 1.602176634×10⁻¹⁹ C (exact). CODATA 2022. ✓
- **Spin Hall angle in the STFMR effect** — t_NM factor is dimensionally required per Liu et al. PRL 106, 036601 (2011). Not re-flagged (standing instruction R4–R7). ✓

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | LOW | `spin_pumping_ishe.py:36,109–112` | Docstrings write `μ₀` in Δα formula denominator; code correctly omits it |
