# Code Review Round 3 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19
**Based on**: current code after Round 1 and Round 2 patches

---

## Verdict

**ISSUES FOUND**

---

## Round-2 Patch Verification

All six findings from Round 2 have been correctly applied:

| R2 Finding | Status |
|---|---|
| `formulas.py` `dw_velocity_below_walker` used `1/alpha` instead of `1/(1+alpha²)` | **FIXED** — `gamma * delta * MU_0 * H / (1.0 + alpha**2)` |
| `macrospin.py` `fit()` time-series model was purely exponential (no cosine) | **FIXED** — `exp(-alpha*omega_0*x) * np.cos(omega_0*x)` |
| `dw_1d.py` docstrings stated wrong Walker field (missing `/2`) | **FIXED** — both docstrings corrected to `H_W = α·K_⊥ / (2·μ₀·M_s)` |
| `llg.py` `forward()` did not store initial condition at `t_eval[0]` | **FIXED** — initial condition stored before loop |
| `formulas.py` `skyrmion_hall_angle` raised `ZeroDivisionError` for `alpha=0` | **FIXED** — `math.atan2(G, alpha*D_norm)` used |
| `macrospin.py` `_llg_rk4` had no step-size control | **FIXED** — oversampled internal grid added |

---

## Findings

### FINDING 1 — MEDIUM: `LLGModel.fit()` docstring formula contradicts the implementation

**File / lines:** `maglab/analysis/effects/llg.py:242–243`

**Defect:**

The `fit()` docstring states:

```
Uses the approximation m_z(t) = 1 - A·exp(-αω₀t/2)·(1-cos(ω₀t)).
```

The actual implementation at line 255 is:

```python
return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x) * np.cos(omega_0 * x)
```

Two errors in the docstring:
1. **Extra `/2` in exponent**: the docstring says `exp(-αω₀t/2)` but the code correctly uses `exp(-αω₀t)` (the ring-down time constant for the LLG equation is `1/(αω₀)`, not `2/(αω₀)`).
2. **Wrong envelope function**: the docstring says `(1-cos(...))` but the code correctly uses `cos(...)`.

Numerical confirmation: at `t=0`, the docstring formula gives `mz(0) = 1 - A*(1-cos(0)) = 1 - 0 = 1.0` regardless of `mz_0`, violating the initial condition. The code correctly gives `mz(0) = 1 - (1-mz_0)*1*1 = mz_0`. The code is physically correct; the docstring is wrong in two ways.

This directly contradicts the code that was specifically fixed in Round 1 (`LLGModel.fit` oscillatory ring-down). The docstring was not updated to match the correction.

**Fix:** Update the docstring at line 242–243 to:

```python
# Oscillatory ring-down: mz(t) = 1 - A·exp(-α·ω₀·t)·cos(ω₀·t)
# Time constant 1/(α·ω₀); valid in the underdamped limit α ≪ 1.
```

---

### FINDING 2 — MEDIUM: `afmr_frequency()` crashes with `ValueError` for negative field arguments; crash propagates through `LLG2SublatticeModel.fit()`

**File / lines:** `maglab/physics/formulas.py:476` and `maglab/analysis/effects/llg_2sublattice.py:350`

**Defect:**

`afmr_frequency` at line 476:

```python
return (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(2.0 * H_E * H_A)
```

`math.sqrt` raises `ValueError` for negative arguments. If `H_E < 0` or `H_A < 0`, the function crashes:

```
>>> math.sqrt(-1.0)
ValueError: math domain error
```

This crash propagates through `LLG2SublatticeModel.fit()` at line 350–351, where the residual function calls `afmr_frequency` inside a list comprehension:

```python
def model_fn(x: np.ndarray, H_E: float) -> np.ndarray:
    return np.array([afmr_frequency(H_E, float(ha), gamma) for ha in x])
```

The critical issue is that `run_fit()` uses `method="leastsq"` (Levenberg-Marquardt), which does **not** enforce parameter bounds. Even though `H_E` has `lower=0.0` in its `ParamSpec`, the optimizer can and does propose negative values during the Jacobian computation (finite-difference steps near the boundary). The resulting `ValueError` is unhandled and propagates up to the caller.

**Verify:**

```python
import math
math.sqrt(2.0 * (-1.0) * 1e5)  # → ValueError: expected a nonneg input
```

**Fix:** Guard against negative arguments in `afmr_frequency`:

```python
product = 2.0 * H_E * H_A
if product < 0.0:
    return 0.0  # unphysical but numerically safe for optimizer
return (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(product)
```

Alternatively, change `method="leastsq"` to `method="least_squares"` in `run_fit()`, which enforces bounds, but this would affect all fits globally.

---

### FINDING 3 — MEDIUM: `FMRKittel.forward()` uses `sqrt` without `abs`, while `FMRKittel.fit()` uses `sqrt(abs(...))` — the two methods implement different mathematical models

**File / lines:** `maglab/analysis/effects/fmr_kittel.py:128` and `:174`

**Defect:**

`forward()` at line 128 (in-plane mode):

```python
f = gamma_p * MU_0 * np.sqrt(H_Am * (H_Am + M_eff))
```

`fit()` model function at line 174:

```python
return gamma_ghz_t * MU_0 * np.sqrt(np.abs(H_Am * (H_Am + M_eff)))
```

When `M_eff < 0` and `|M_eff| > H_Am` (e.g., a PMA film with large `K_u` such that `M_eff = Ms - 2K_u/(μ₀Ms) < 0`), the inner product `H_Am * (H_Am + M_eff)` is negative. The consequences are:

- `forward()` returns `NaN` silently (numpy `sqrt` of negative gives `NaN` with a RuntimeWarning, not an exception).
- `fit()` model function returns a finite real number via `sqrt(abs(...))`.

This means `fit()` can converge to parameters where `M_eff < -H_Am`, but calling `forward()` with those fitted parameters gives all-NaN output. The model returned by fit cannot be used to make predictions via the public `forward()` API — a broken invariant.

**Numerical demonstration:**

```python
M_eff = -3e6 A/m, H_res = [0.1, 0.2, 0.3] T
fit()     → f = [16.98, 23.68, 28.59] GHz  (real, abs taken)
forward() → f = [nan, nan, nan]              (NaN, no abs)
```

**Fix:** Align the two implementations. For in-plane mode, `H_Am * (H_Am + M_eff) < 0` means the operating point is below the FMR threshold — raise a descriptive error or return 0. Update `forward()` at line 128:

```python
inner = H_Am * (H_Am + M_eff)
if np.any(inner < 0):
    raise ValueError(
        f"FMR in-plane: H_Am*(H_Am+M_eff) < 0. "
        "Check that M_eff > 0 for in-plane geometry, or use 'out_of_plane' mode."
    )
f = gamma_p * MU_0 * np.sqrt(inner)
```

Also update `fit()` model to match: either drop the `np.abs` (and let it propagate NaN, forcing the optimizer away from non-physical regions), or clip with a warning.

---

### FINDING 4 — MEDIUM: `STFMREffect.spin_hall_angle()` crashes with `ValueError` for PMA films (M_eff < 0)

**File / lines:** `maglab/analysis/effects/stfmr.py:255`

**Defect:**

```python
geom_factor = math.sqrt(1.0 + M_eff / H_res) if H_res > 0 else 1.0
```

When `M_eff < 0` (perpendicular magnetic anisotropy) and `|M_eff| > H_res`, the argument `1 + M_eff/H_res` is negative. `math.sqrt` raises `ValueError`:

```
math.sqrt(-49.0)  → ValueError: math domain error
```

This is a real crash path in routine experimental use. The code's own references include Garello et al. Nat. Nano. 8, 587 (2013), which studies `Ta/CoFeB/MgO` bilayers — a PMA material with `M_eff < 0` by design. The formula `√(1 + M_eff/H_res)` from Liu et al. PRL 106, 036601 (2011) is derived for in-plane magnetized samples; for PMA films the geometry factor takes a different form. The code does not document this restriction or enforce it.

**Quantified example:**

```python
M_eff = -5e5 A/m  # CoFeB/MgO with strong PMA
H_res = 1e4 A/m   # typical in-plane ST-FMR resonance
# 1 + M_eff/H_res = 1 + (-50) = -49 → crash
```

**Fix:** Guard against negative argument and raise a descriptive error that explains the physics:

```python
geom_arg = 1.0 + M_eff / H_res if H_res > 0 else 1.0
if geom_arg < 0.0:
    raise ValueError(
        f"spin_hall_angle: 1 + M_eff/H_res = {geom_arg:.3f} < 0. "
        "The Liu et al. (2011) geometry factor applies to in-plane magnetized samples "
        "(M_eff > 0). For PMA samples (M_eff < 0), use the out-of-plane geometry formula."
    )
geom_factor = math.sqrt(geom_arg)
```

This converts the silent crash into an actionable error message for the user.

---

### FINDING 5 — LOW: `LLGModel.forward()` raises `ZeroDivisionError` for degenerate `t_span` (t₀ = t₁)

**File / lines:** `maglab/analysis/effects/llg.py:193–195`

**Defect:**

When `t_span[0] == t_span[1]` (degenerate zero-duration interval):

```python
# H_mag > 0 branch:
max_step = min(
    (t_span[1] - t_span[0]) / 5.0,  # = 0.0
    2.0 * np.pi / omega_max / 10.0,
)
# max_step = 0.0
n_steps = max(int((t_span[1] - t_span[0]) / max_step) + 1, 4 * n_out)
#                   ↑ ZeroDivisionError: 0.0 / 0.0
```

Both the `H_mag > 0` and `H_mag == 0` code paths crash with `ZeroDivisionError`.

`MacrospinModel._llg_rk4` (fixed in Round 2) correctly guards this case:

```python
max_step = min(
    (t_end - t_start) / 5.0 if t_end > t_start else 1e-12,  # ← guard
    ...
)
```

`LLGModel.forward()` does not have this guard, creating an asymmetry between two sibling integrators.

**Fix:** Mirror `MacrospinModel._llg_rk4`'s guard:

```python
duration = t_span[1] - t_span[0]
if H_mag > 0:
    omega_max = gamma_0 * float(MU_0) * H_mag
    max_step = min(
        duration / 5.0 if duration > 0 else 1e-12,   # ← add this guard
        2.0 * np.pi / omega_max / 10.0,
    )
else:
    max_step = duration / 100.0 if duration > 0 else 1e-12   # ← add guard
```

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **MEDIUM** | `effects/llg.py:242` | `fit()` docstring formula wrong in two ways (factor-of-2 in exponent, `(1-cos)` vs `cos`); code is correct, docstring contradicts it |
| 2 | **MEDIUM** | `physics/formulas.py:476` + `effects/llg_2sublattice.py:350` | `afmr_frequency` crashes with `ValueError` for negative arguments; `leastsq` optimizer can probe negative `H_E` values regardless of `lower=0` bound |
| 3 | **MEDIUM** | `effects/fmr_kittel.py:128` vs `:174` | `forward()` returns NaN silently; `fit()` model uses `sqrt(abs(...))` — different mathematical models, so fitted parameters cannot be used with `forward()` |
| 4 | **MEDIUM** | `effects/stfmr.py:255` | `spin_hall_angle()` crashes with `ValueError` for PMA films (`M_eff < 0`, `|M_eff| > H_res`); the exact material class cited in the code's references |
| 5 | LOW | `effects/llg.py:193` | `forward()` raises `ZeroDivisionError` for `t_span[0] == t_span[1]`; `MacrospinModel._llg_rk4` guards this correctly but `LLGModel.forward()` does not |
