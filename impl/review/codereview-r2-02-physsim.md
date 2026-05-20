# Code Review Round 2 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19
**Based on**: current code after Round 1 patches

---

## Verdict

**ISSUES FOUND**

---

## Round-1 Patch Verification

All three HIGH defects from Round 1 have been correctly applied:

| R1 Finding | Status |
|---|---|
| LLG missing μ₀ in precession (`llg.py`, `macrospin.py`, `llg_2sublattice.py`) | **FIXED** — `MU_0 * H_eff` in all three |
| DMI BLS formula spurious μ₀ in denominator (`dmi.py`) | **FIXED** — formula now `2*gamma_p*D_i*k/Ms`, no μ₀ |
| ST-FMR `spin_hall_angle()` missing √(1+M_eff/H_res) (`stfmr.py`) | **FIXED** — `geom_factor = sqrt(1+M_eff/H_res)` added |
| Walker field factor-of-2 in `dw_1d.py` | **FIXED** — `alpha*K_perp/(2*MU_0*Ms)` |
| AFMR fit degenerate H_A parameter (`llg_2sublattice.py`) | **FIXED** — `H_A` removed from AFMR fit param_specs |
| SpinPumping forward() constant vs d_NM | **FIXED** — `tanh(d_NM/(2*lambda_sf))` factor added |
| LLG fit model purely exponential | **FIXED** — oscillatory `exp(-alpha*omega_0*t)*cos(omega_0*t)` |
| FiM compensation circular synthetic fit | **FIXED** — analytic inversion returns `FitResult` directly |
| Hysteresis `extract_loop_params()` no zero-crossing guard | **FIXED** — NaN + warning emitted |

**Clarification on ST-FMR `t_NM` (R1 Finding 3):** The R1 review claimed `t_NM` should be removed. This was incorrect. Dimensional analysis confirms that `e*mu_0*Ms*t_FM/hbar` has units `[1/m]`, not dimensionless; only `e*mu_0*Ms*t_FM*t_NM/hbar` yields a dimensionless xi_DL. The patched code retains `t_NM` and is dimensionally correct. The formula matches the standard experimental convention (Garello et al. Nat. Nano 2013, Pai et al. APL 2012).

---

## Findings

### FINDING 1 — MEDIUM: `formulas.py` `dw_velocity_below_walker` wrong denominator (100× error)

**File / line:** `maglab/physics/formulas.py:214–216`

**Defect:**

```python
# Code (WRONG):
return (gamma * delta / alpha) * MU_0 * H
```

The Schryer–Walker (1974) result for domain-wall velocity below the Walker breakdown is:

```
v = γ·Δ·μ₀·H / (1 + α²)
```

The code uses `1/alpha` instead of `1/(1+alpha²)`. This is not the large-alpha limit (`1/alpha²`) nor the small-alpha limit (`1/(1+alpha²) ≈ 1`); it is a physically incorrect formula that overestimates velocity by a factor of `(1+alpha²)/alpha ≈ 1/alpha` for small alpha.

**Quantified error:**

| alpha | Code (1/α) | Correct (1/(1+α²)) | Ratio |
|---|---|---|---|
| 0.001 | 1000× relative | 1.0× | **1000×** |
| 0.01 | 100× | 1.0× | **100×** |
| 0.1 | 10.1× | ~1.0× | **10×** |

For Permalloy (alpha=0.01, Δ=30 nm, H=10 kA/m): code gives 6638 m/s vs correct 66 m/s. Typical Walker DW velocities for Py are 10–100 m/s.

The companion function `dw_1d.py:dw_velocity_below_walker()` uses the correct `1/(1+alpha²)` formula, creating a 100× discrepancy between the two functions that claim to compute the same quantity.

**Fix:**

```python
# formulas.py line 214
return gamma * delta * MU_0 * H / (1.0 + alpha**2)
```

Also update the docstring formula from `v_DW = (γΔ/α)·μ₀·H` to `v_DW = (γΔ·μ₀·H)/(1+α²)` and correct the reference annotation — the Schryer–Walker (1974) JAP 45, 5406 Eq. (8a) is the authoritative source.

---

### FINDING 2 — MEDIUM: `MacrospinModel.fit()` time-series model is purely exponential (not oscillatory), giving ~14,000% error in α

**File / lines:** `maglab/analysis/effects/macrospin.py:313–314`

**Defect:**

```python
def model_fn_t(x, H_k, alpha, tau_DL, tau_FL):
    mz_0 = float(mz[0]) if len(mz) > 0 else 0.8
    return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x)  # WRONG: no cosine
```

`LLGModel.forward()` integrates the full oscillatory LLG ODE. Real FMR precession produces oscillatory ring-down `m_z(t) ≈ 1 − A·exp(−α·ω₀·t)·cos(ω₀·t)`. The macrospin time-series `model_fn_t` fits a purely exponential decay instead.

When this exponential model is applied to oscillatory FMR data, `curve_fit` drives alpha toward the overdamped limit (alpha ≈ 1.47 in a numerical test where true alpha = 0.01), an error of ~14,559%. This makes the macrospin time-series fit physically meaningless for any underdamped system (α ≪ 1), which is the regime of interest (typical α ∈ [0.001, 0.1]).

Compare: `LLGModel.fit()` (the analogous fitting function) correctly uses the oscillatory model `1 − (1−mz_0)·exp(−α·ω₀·t)·cos(ω₀·t)`, which was fixed in Round 1. The macrospin equivalent was not similarly updated.

**Fix:**

```python
def model_fn_t(x, H_k, alpha, tau_DL, tau_FL):
    mz_0 = float(mz[0]) if len(mz) > 0 else 0.8
    return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x) * np.cos(omega_0 * x)
```

---

### FINDING 3 — MEDIUM: `dw_1d.py` module/class docstring states wrong Walker field formula (missing factor of 2)

**File / lines:** `maglab/analysis/effects/dw_1d.py:4` and `:39`

**Defect:**

The module-level docstring (line 4) states:

```
Walker breakdown field: H_W = α·K_⊥/M_s.
```

The class-level docstring (line 39) states:

```
Walker breakdown field: H_W = α·K_⊥ / (μ₀·M_s)
```

Both are incorrect: they are missing both the `μ₀` factor (module line 4) and the factor of 2 (both). The correct formula implemented in `walker_field()` at line 126 is:

```python
return alpha * K_perp / (2.0 * MU_0 * Ms)   # ← CORRECT implementation
```

Researchers reading the class docstring will compute a Walker field that is **2× too large** (and the module docstring is off by `μ₀`). This is a documentation bug, but because the docstring is the first thing users read when deciding parameters, it is consequential enough to rate MEDIUM.

**Fix:** Update both docstrings to `H_W = α·K_⊥ / (2·μ₀·M_s)`.

---

### FINDING 4 — LOW: `LLGModel.forward()` does not store initial condition `m_0` at `t_eval[0] = t_span[0]`

**File / lines:** `maglab/analysis/effects/llg.py:199–221`

**Defect:**

The output-collection loop:

```python
for i, t_i in enumerate(t_internal[:-1]):
    # RK4 step: m_curr advances from t_i to t_next
    ...
    t_next = t_internal[i + 1]
    while out_idx < n_out and t_arr[out_idx] <= t_next + 1e-15:
        result[out_idx] = m_curr   # m_curr is at t_next, not t_i
        out_idx += 1
```

When `t_eval[0] = t_span[0]` (the default), the first output point is captured after the first RK4 step, i.e., it stores `m(t_span[0] + dt)` rather than `m_0`. The initial condition is never written to `result`.

`MacrospinModel._llg_rk4` (line 184) correctly handles this by initializing `result[0] = m_curr` before the loop. The LLG model does not.

For typical parameters (10 GHz, n_steps = 4×n_out), the timing error is `dt_internal ≈ T_period/40 ≈ 70 ps`, producing a ~1.4° phase error at the first output point. For high fields (H > 10⁵ A/m) this is larger.

**Fix:** Insert `result[0] = m_0.copy()` and begin output collection at `out_idx = 1` if `t_arr[0] == t_span[0]`, or adopt `MacrospinModel`'s pattern of pre-initializing `result[0]` and starting the integration loop from index 1.

---

### FINDING 5 — LOW: `formulas.py` `skyrmion_hall_angle` raises `ZeroDivisionError` for `alpha = 0`

**File / lines:** `maglab/physics/formulas.py:615`

**Defect:**

```python
def skyrmion_hall_angle(alpha: float, Q: float = 1) -> float:
    G = 4.0 * math.pi * Q
    D_norm = 1.0
    return math.atan(G / (alpha * D_norm))   # ZeroDivisionError for alpha=0
```

`math.atan(x)` is not called; `G / (alpha * D_norm)` raises `ZeroDivisionError` before `atan` is reached when `alpha = 0`.

The `ThieleModel.skyrmion_hall_angle()` in `thiele.py:115–118` correctly handles this with `math.atan2(G_z, alpha * D)`, which returns `π/2` for zero denominator.

**Fix:**

```python
return math.atan2(G, alpha * D_norm)   # handles alpha=0 correctly → returns π/2
```

---

### FINDING 6 — LOW: `MacrospinModel._llg_rk4` has no step-size control; `LLGModel.forward()` does

**File / lines:** `maglab/analysis/effects/macrospin.py:166–209`

**Defect:**

`LLGModel.forward()` (lines 178–186) correctly computes `max_step = 2π/(ω_max·10)` to ensure at least 10 integration steps per precession period, using `omega_max = gamma_0 * MU_0 * H_mag`. `MacrospinModel._llg_rk4` uses `t_arr` directly as integration time points, with no step-size safety check.

For `H_eff = 1×10⁵ A/m`: precession period = 284 ps. With default `n_pts=200` over 1 ns, `dt = 5 ps = T/57`. This is marginally adequate.

For `H_eff = 1×10⁶ A/m` (applied at or above the anisotropy field of hard magnets): period = 28.4 ps, `dt = 5 ps = T/5.7`. Below the Nyquist criterion — the RK4 step is underresolved and the trajectory will be inaccurate or diverge.

**Fix:** Enforce `max_step` in `_llg_rk4` as done in `LLGModel.forward()`, or use `n_pts` to auto-compute a safe step count.

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **MEDIUM** | `physics/formulas.py:214` | `dw_velocity_below_walker` uses `1/alpha` instead of `1/(1+alpha²)` → 100× error at α=0.01 |
| 2 | **MEDIUM** | `effects/macrospin.py:313` | `fit()` time-series model exponential (no cosine) → ~14 000% error in extracted α |
| 3 | **MEDIUM** | `effects/dw_1d.py:4,39` | Module and class docstrings both state wrong Walker field formula (missing `/2`) |
| 4 | LOW | `effects/llg.py:199` | `forward()` does not store initial condition `m_0` at `t_eval[0]` |
| 5 | LOW | `physics/formulas.py:615` | `skyrmion_hall_angle` `ZeroDivisionError` for `alpha=0` |
| 6 | LOW | `effects/macrospin.py:166` | `_llg_rk4` has no step-size control; may undersample at high H fields |
