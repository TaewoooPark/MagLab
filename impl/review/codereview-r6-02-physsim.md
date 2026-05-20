# Code Review Round 6 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19
**Based on**: current code after Rounds 1–5 patches

---

## Verdict

**ISSUES FOUND** — 1 finding, severity HIGH.

---

## R5 Fix Verification

All three R5 fixes are correctly in place:

| R5 Finding | Status |
|---|---|
| `ferrimagnet_compensation_freq` returns ω (rad/s) not Hz; FiM inversion missing 2π | **FIXED** — `formulas.py:526–527` now computes `omega` then `return omega / (2.0 * math.pi)`. `llg_2sublattice.py:435–437` uses `2.0 * math.pi * f_comp_val * (m_a_val + m_b_val) / (denom_gamma * MU_0)`. Residual check at line 447 confirms algebraic consistency. |
| `SpinPumpingISHE` spurious `MU_0` in Δα prefactor | **FIXED** — both `forward()` (line 136) and `fit()` (line 161) now use `(gamma_rad * HBAR * g_eff) / (4.0 * np.pi * Ms * d_FM)` and `(gamma_rad * HBAR) / (4.0 * np.pi * Ms * d_FM)` respectively — `MU_0` absent from both. Comments at lines 134–135 and 160 explicitly cite Mosendz PRB 82, 214403 (2010). |
| `SMR.fit()` ghost `delta_rho_2` in model-function signatures | **FIXED** — `long_specs` (line 192) restricts the fit to `rho_0` and `delta_rho_1` only. Both `model_fn_single` and `multi_model_fn` have matching 2-parameter signatures (lines 199, 219). `delta_rho_2` is appended as `float("nan")` with `float("nan")` uncertainty at lines 238–239. |

---

## Findings

### FINDING 1 — HIGH: `walker_velocity` in `formulas.py` is missing `Delta` (DW width) and returns angular frequency, not velocity

**File / line:** `maglab/physics/formulas.py:184`

**Defect:**

```python
def walker_velocity(alpha: float, Ms: float, gamma: float = GAMMA_E) -> float:
    ...
    return gamma * MU_0 * Ms / 2.0
```

The claimed reference (Mougin et al., *EPL* 78, 57007 (2007), Eq. (1)) gives:

```
v_W = γ · Δ · μ₀ · M_s / 2
```

where Δ is the domain-wall width [m]. The code omits Δ entirely, and the function signature does not accept it as a parameter.

**Dimensional analysis:**

```
gamma [rad/(s·T)]  ×  MU_0 [T·m/A]  ×  Ms [A/m]
= [rad/(s·T)] × [T] = rad/s
```

The result has units **rad/s** (angular frequency), not **m/s** (velocity). The docstring incorrectly declares `Returns: Walker velocity [m/s]`.

The correct formula:

```
gamma [rad/(s·T)]  ×  Delta [m]  ×  MU_0 [T·m/A]  ×  Ms [A/m]
= [rad/(s·T)] × [m] × [T·m/A] × [A/m]
= [rad · m/s] = m/s   (rad is dimensionless in SI)
```

**Quantified error:**

For Permalloy (γ = 1.76×10¹¹ rad/(s·T), μ₀ = 1.26×10⁻⁶ H/m, M_s = 860 kA/m, Δ ≈ 10–200 nm):

| Quantity | Correct (with Δ=100 nm) | Code (missing Δ) |
|---|---|---|
| v_W | ~950 m/s | 9.52×10¹⁰ rad/s = 317× speed of light |
| Error factor | — | 1/Δ ≈ 10⁷ m⁻¹ |

**Upstream impact:**

`walker_velocity` is defined only in `maglab/physics/formulas.py` and is not called from anywhere in the `maglab/analysis/` or `maglab/sim/` sub-trees (confirmed by grep). Impact is therefore confined to any external consumer of `formulas.walker_velocity`. The sister function `dw_velocity_below_walker` in the same file correctly includes Δ at line 218, and `DW1DModel.dw_velocity_below_walker` (line 142 of `dw_1d.py`) is also correct. There is no cascading error inside the analysis/sim domain.

**Reference:**

Mougin, A. et al., *EPL* 78, 57007 (2007), Eq. (1):
```
v_max = γ · Δ_DW · μ₀ · M_s / 2
```
Schryer, N.L., Walker, L.R., *J. Appl. Phys.* 45, 5406 (1974), Eq. (8a):
```
v_DW = γ · Δ · μ₀ · H / (1 + α²)   [below Walker, linear regime]
```

**Concrete fix:**

```python
def walker_velocity(alpha: float, Ms: float, Delta: float, gamma: float = GAMMA_E) -> float:
    r"""Compute the maximum domain-wall velocity just below the Walker breakdown v_W.

    .. math::
        v_W = \frac{\gamma \mu_0 M_s \Delta}{2}

    References:
        Mougin et al., *EPL* 78, 57007 (2007), Eq. (1).

    Args:
        alpha: Gilbert damping constant [dimensionless].
        Ms: Saturation magnetization [A/m].
        Delta: Domain-wall width parameter Δ [m].
        gamma: Gyromagnetic ratio [rad/(s·T)] (default: electron γ).

    Returns:
        Walker velocity [m/s].
    """
    _ = alpha
    return gamma * Delta * MU_0 * Ms / 2.0
```

---

## Non-Findings

Investigated and dismissed (no genuine defect found):

- **`spinwave_dispersion_fm` (formulas.py:327–329)** — `omega = gamma*mu_0*H + gamma*(2A/Ms)*k^2` is correct; mu_0 cancels algebraically in the exchange term (Kalinikos–Slavin 1986, Eq. 2.17). Confirmed numerically for Py at k=10⁸ m⁻¹ → 8.82 GHz.
- **`DMIEffect.forward()` / `fit()` (dmi.py:118, 150)** — formula `delta_f = 2*gamma_p*D_i*k/Ms` (no mu_0) is dimensionally correct: gamma_p [Hz/T] × D_i [J/m²] × k [m⁻¹] / Ms [A/m] = Hz. Confirmed via derivation: H_eff_DMI = D_i·k/(mu_0·Ms) [A/m], then omega_DMI = gamma·mu_0·H_eff_DMI = gamma·D_i·k/Ms [rad/s], and mu_0 cancels.
- **`GilbertDamping.forward()` / `fit()` (gilbert_damping.py:114, 149)** — `dH = dH_0 + (2*alpha/gamma_p)*f` with gamma_p in GHz/T, f in GHz, dH in T. Dimensional check: [1/(GHz/T)]×[GHz] = T. Numerically: α=0.01, f=10 GHz → ΔH = 7.1 mT (consistent with Py literature).
- **`AFMRfrequency` / `ferrimagnet_compensation_freq` (formulas.py:482, 527)** — both formulae verified dimensionally and numerically (R5 fix confirmed).
- **`DW1DModel.dw_velocity_below_walker` (dw_1d.py:142)** — correctly includes Delta: `gamma_0 * Delta * MU_0 * H / (1+alpha**2)`. No issue.
- **`MacrospinModel` ring-down model (macrospin.py:364)** — `m_z(t) = 1 - A·exp(-α·ω₀·t)·cos(ω₀·t)` is the correct underdamped FMR precession formula. No issue.
- **`BlochWallWidth` / `bloch_wall_energy` (formulas.py:100, 129)** — `pi*sqrt(A/K)` and `4*sqrt(A*K)` match Hubert–Schäfer (1998) Eqs. (3.30–3.31). Numerically verified for YIG.
- **`spin_hall_angle` (stfmr.py:267)** — previously confirmed correct in Rounds R4, R5 (Liu et al. PRL 106, 036601 (2011) t_NM factor is dimensionally required). Not re-flagged per review instructions.
- **`SMREffect._m_y` geometry factors (smr.py)** — α/β/γ geometries correctly implement m_y = cos(α), sin(β), 0 per Chen et al. PRB 87, 144411 (2013).
- **`FMRKittel.forward()` OOP mode (fmr_kittel.py:137)** — `np.abs(H_Am - M_eff)` correctly prevents negative frequency (R4 fix retained).
- **`heisenberg_to_exchange_stiffness` (formulas.py:566)** — matches Coey (2010) Eq. (5.86): A = n·J·S²·z·a²/6. Numerically: 19.6 pJ/m for fcc Fe — physically reasonable.
- **`MuMax3._generate_mx3` B_ext conversion (mumax3.py:105)** — `H[A/m] × 1.25663706212e-6 [T·m/A] = B[T]` is correct; MuMax3 takes B_ext in Tesla.
- **`SOTHarmonicHall.phe_corrected` (sot_harmonic_hall.py:296)** — PHE correction formula `H_DL = (H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)` matches Hayashi et al. PRB 89, 144425 (2014) Eq. (S7).
- **`TYJScaling` (tyj_scaling.py)** — `rho_AHE = a*rho_xx + b*rho_xx^2` matches Tian, Ye, Jin PRL 103, 087206 (2009) exactly.
- **`LLG2SublatticeModel` AFMR fit (llg_2sublattice.py:394)** — `afmr_frequency` called correctly per H_A_sweep; only H_E is fitted; non-identifiable params reported as defaults (R4 ghost-param pattern applied).
- **`CurieTemperatureModel._power_law` (curie_temperature.py:166)** — power-law M(T)=M_0·(1−T/T_C)^β with T_C_safe=max(T_C,1) guards division by zero. Zero-crossing interpolation for T_comp is linear and correct.
- **`HysteresisLoop.extract_loop_params` (hysteresis.py:149–195)** — M_r/H_c extraction uses argmin(|H|) and argmin(|M|) respectively; warns (not silently returns boundary) when data doesn't straddle zero. No physics issue.

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **HIGH** | `physics/formulas.py:184` | `walker_velocity` returns `gamma*MU_0*Ms/2` [rad/s] not [m/s]; missing `Delta` (DW width) parameter; off by ~10⁻⁸ m and dimensionally wrong. Not called from analysis/sim domain — no cascading error inside scope. |
