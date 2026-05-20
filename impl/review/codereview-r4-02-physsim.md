# Code Review Round 4 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19
**Based on**: current code after Rounds 1–3 patches

---

## Round-3 Patch Verification

All five findings from Round 3 have been correctly applied:

| R3 Finding | Status |
|---|---|
| `llg.py:242` docstring formula wrong (factor-of-2, `(1-cos)` vs `cos`) | **FIXED** — docstring updated to `m_z(t) = 1 - A·exp(-α·ω₀·t)·cos(ω₀·t)` |
| `formulas.py:476` `afmr_frequency` crashes on negative args | **FIXED** — `if product < 0: return 0.0` guard added |
| `fmr_kittel.py:128` `forward()` NaN vs `fit()` abs mismatch | **FIXED** — `forward()` now uses `np.sqrt(np.abs(...))` matching `fit()` |
| `stfmr.py:255` `spin_hall_angle` crashes for PMA films | **FIXED** — `geom_arg < 0` guard with descriptive `ValueError` added |
| `llg.py:193` `forward()` `ZeroDivisionError` for zero-duration `t_span` | **FIXED** — `duration > 0` guard added, matches `MacrospinModel._llg_rk4` |

---

## Verdict

**ISSUES FOUND**

---

## Findings

### FINDING 1 — HIGH: `LLG2SublatticeModel._llg2sl_rk4` has no internal step-size control — numerically unstable for large exchange fields

**File / lines:** `maglab/analysis/effects/llg_2sublattice.py:268–288`

**Defect:**

`_llg2sl_rk4` integrates the coupled two-sublattice LLG using a fixed time step equal to the spacing of the user-supplied `t_arr`:

```python
for i in range(1, n_out):
    dt = t_arr[i] - t_arr[i - 1]
    k1a, k1b = _rhs(m_a, m_b)
    ...
```

There is no internal oversampled grid. For a typical AFM with exchange field `H_E ~ 10⁸–10⁹ A/m`, the exchange-driven precession frequency is:

```
omega_ex = gamma * mu_0 * H_E ~ 2.2 × 10¹³ – 2.2 × 10¹⁴ rad/s
T_precession ~ 30 – 300 fs
```

The default `t_eval = linspace(0, 1e-12, 200)` gives `dt = 5 fs`, yielding only 6 steps per precession period for `H_E = 10⁹ A/m`. RK4 requires **≥ 20–100 steps per period** for accuracy. The integration will produce numerically unstable trajectories.

This is a direct asymmetry with the two sibling integrators:
- `LLGModel.forward()` (`llg.py:180–195`): uses an oversampled internal grid (at least 10 steps per precession period)
- `MacrospinModel._llg_rk4` (`macrospin.py:199–214`): same internal oversampled grid with explicit guard

`_llg2sl_rk4` has neither guard.

**Quantified example:**

```
H_E = 1e9 A/m (NiO-class AFM)
omega_ex = 2.2e14 rad/s, T = 28 fs
default dt = 5 fs → 5.7 steps/period → RK4 is UNSTABLE
```

**Fix:** Mirror `MacrospinModel._llg_rk4`: build an internal oversampled grid with at least 10 steps per exchange precession period, then sample at the requested `t_arr` points.

```python
# At top of _llg2sl_rk4, add:
t_start, t_end = float(t_arr[0]), float(t_arr[-1])
omega_max = abs(GAMMA_E) * float(MU_0) * max(abs(H_E), abs(H_A), float(np.linalg.norm(H_ext)))
if omega_max > 0:
    max_step = min(
        (t_end - t_start) / 5.0 if t_end > t_start else 1e-12,
        2.0 * np.pi / omega_max / 10.0,
    )
else:
    max_step = (t_end - t_start) / 100.0 if t_end > t_start else 1e-12
n_internal = max(int((t_end - t_start) / max_step) + 1, 4 * n_out) if t_end > t_start else n_out
t_internal = np.linspace(t_start, t_end, n_internal + 1)
dt_int = t_internal[1] - t_internal[0] if n_internal > 0 else 0.0
# Then use t_internal in the loop with output sampling, same as LLGModel.forward()
```

---

### FINDING 2 — MEDIUM: `STFMREffect.spin_hall_angle` formula inconsistent with cited Liu 2011 reference and produces numerically implausible values

**File / lines:** `maglab/analysis/effects/stfmr.py:267`

**Defect:**

```python
return (S / A) * geom_factor * (e * mu_0 * Ms * t_FM * t_NM / hbar)
```

The docstring attributes this formula to Liu et al. PRL 106, 036601 (2011). However, Liu 2011 Eq. (3) does **not** contain `t_NM` (NM layer thickness):

> theta_SH = (S/A) × sqrt(1 + M_eff/H_FMR) × e × M_s × t_FM / (hbar × gamma × H_FMR)

The code's formula substitutes `mu_0 × Ms × t_NM` for `1/(gamma × H_FMR)`. These quantities have **different physical dimensions** (m vs. s) and cannot be equivalent:

```
mu_0 * Ms * t_NM ~ 1.25e-6 * 860e3 * 5e-9 = 5.4e-9 m
1/(gamma * H_FMR) ~ 1/(1.76e11 * 80e3) = 7.1e-17 s
```

Numerical cross-check with reference Pt(5nm)/Py(5nm) system:
- Literature: `xi_DL ~ 0.07–0.15` for Pt/Py
- Code result with `S/A = 2–5` (typical Pt, DL-dominant): `xi_DL ~ 0.28–0.70` (3–5× too large)
- Code result with `S/A = 0.1`: `xi_DL ~ 0.014` (a factor of 5–10 too small, requiring unphysical `S < A`)

The formula also mixes the meaning of `S/A`: in the code's fitting pipeline, `S` and `A` are in Volts (symmetric and antisymmetric Lorentzian amplitudes from the voltage fit), but the Liu formula requires `H_DL/H_ext` (a ratio of magnetic fields). These are not equivalent without additional normalization factors (`H_ext` and RF current) that the function does not accept.

The `fit()` method already silently catches this exception (`except (ValueError, ZeroDivisionError): fit_result.params["xi_DL"] = float("nan")`), meaning incorrect `xi_DL` propagates into `FitResult.params` without warning when the formula evaluates to a finite but wrong number.

**Fix:** Replace the formula with the correct Liu 2011 Eq. (3) expression and update the function signature to accept the required normalization parameters:

```python
@staticmethod
def spin_hall_angle(
    S: float,
    A: float,
    Ms: float,
    t_FM: float,
    t_NM: float,
    M_eff: float,
    H_res: float,
    gamma: float = 1.760859630e11,          # rad/(s·T)
    mu_0: float = 1.25663706212e-6,
    hbar: float = 1.054571817e-34,
    e: float = 1.602176634e-19,
) -> float:
    """
    Liu et al. PRL 106, 036601 (2011), Eq. (3):
    xi_DL = (S/A) * sqrt(1 + M_eff/H_res) * e * mu_0 * Ms * t_FM / (hbar * gamma * H_res)
    """
    if abs(A) < 1e-30:
        raise ValueError("A ≈ 0: cannot compute spin Hall angle.")
    if H_res <= 0:
        raise ValueError("H_res must be positive.")
    geom_arg = 1.0 + M_eff / H_res
    if geom_arg < 0.0:
        raise ValueError(...)
    geom_factor = math.sqrt(geom_arg)
    return (S / A) * geom_factor * (e * mu_0 * Ms * t_FM) / (hbar * gamma * H_res)
```

*(The `t_NM` parameter can be kept in the signature for backward compatibility but should not appear in the formula body.)*

---

### FINDING 3 — MEDIUM: `FMRKittel.forward()` out-of-plane mode returns negative frequency for `H_res < M_eff × μ₀` — inconsistent with `formulas.py`

**File / lines:** `maglab/analysis/effects/fmr_kittel.py:132–134`

**Defect:**

```python
else:
    # Out-of-plane: f = γ' · μ₀ · (H[A/m] − M_eff)
    H_Am = H_res / MU_0
    f = gamma_p * MU_0 * (H_Am - M_eff)
```

When `H_res < M_eff × MU_0` (i.e., the applied field is below the saturation field), `H_Am < M_eff` and the formula returns a negative frequency. FMR frequency is a positive definite quantity.

The equivalent function in `physics/formulas.py:403` correctly wraps the result in `abs()`:

```python
return (gamma / (2.0 * math.pi)) * abs(MU_0 * H_ext - MU_0 * Ms)
```

`fmr_kittel.py` does **not** apply `abs()`, breaking the invariant that `forward()` returns physical (non-negative) frequencies.

Concrete example:
```python
params = {"M_eff": 8e5, "gamma_ghz_t": 28.0}
geometry = {"H_res": np.array([0.01, 0.05, 0.1])}  # T, all below M_eff*mu_0 ≈ 1.0 T
FMRKittel(mode="out_of_plane").forward(params, geometry)
# → [-27.87, -26.75, -25.35] GHz  (negative — physically impossible)
```

The `fit()` method (`line 178`) has the same issue.

**Fix:** Apply `abs()` (or clip to zero with a warning) for the out-of-plane mode:

```python
f = gamma_p * MU_0 * abs(H_Am - M_eff)
```

This aligns with `formulas.py:403` and prevents non-physical negative frequencies from being returned to the caller.

---

### FINDING 4 — LOW: `LLGModel.fit()` includes `tau_DL` and `tau_FL` as free fit parameters but the model function does not depend on them

**File / lines:** `maglab/analysis/effects/llg.py:252–256`

**Defect:**

```python
def model_fn(x: np.ndarray, alpha: float, tau_DL: float, tau_FL: float) -> np.ndarray:
    mz_0 = float(mz[0]) if len(mz) > 0 else 0.8
    return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x) * np.cos(omega_0 * x)
```

`tau_DL` and `tau_FL` appear in the function signature and will be treated as free fit parameters by `run_fit()` / lmfit, but the model expression does not contain them. Consequently:

1. The residual is independent of `tau_DL` and `tau_FL`.
2. lmfit cannot compute partial derivatives with respect to these parameters.
3. The covariance matrix will be singular (or near-singular) for these columns.
4. `FitResult.uncertainties["tau_DL"]` and `uncertainties["tau_FL"]` will be `0.0` or `NaN`.
5. The `FitResult.params` will silently report `tau_DL = 0.0`, `tau_FL = 0.0` as "fitted" values, which is misleading — they are not determined by the data.

The analogous `MacrospinModel.fit()` time-series mode (`macrospin.py:343–348`) has the same issue: `tau_DL` and `tau_FL` appear in `model_fn_t`'s signature but not in the model body.

**Fix:** Either:
(a) Remove `tau_DL` and `tau_FL` from the `model_fn` signature and supply a reduced `param_specs` list (like `LLG2SublatticeModel.fit()` does with `afmr_specs`):
```python
llg_alpha_spec = [p for p in self.parameters if p.name == "alpha"]
def model_fn(x: np.ndarray, alpha: float) -> np.ndarray: ...
return run_fit(..., param_specs=llg_alpha_spec, ...)
```
(b) Add `tau_DL` and `tau_FL` to the model expression (proper STT ring-down model).

Option (a) is simpler and makes `FitResult` accurately reflect that only `alpha` is constrained by this measurement.

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **HIGH** | `effects/llg_2sublattice.py:268` | `_llg2sl_rk4` has no internal step-size control; numerically unstable for AFM exchange fields ≥ 10⁸ A/m (<10 steps/period with default t_arr) |
| 2 | **MEDIUM** | `effects/stfmr.py:267` | `spin_hall_angle` formula differs from Liu 2011 Eq.(3); includes spurious `t_NM` factor; produces ~3–5× wrong `xi_DL` for typical Pt/Py |
| 3 | **MEDIUM** | `effects/fmr_kittel.py:134` | `forward()` OOP returns negative frequency when `H_res < M_eff*μ₀`; `formulas.py` correctly uses `abs()` but `fmr_kittel.py` does not |
| 4 | **LOW** | `effects/llg.py:252` + `macrospin.py:344` | `tau_DL`, `tau_FL` are ghost parameters in the `fit()` model function — not identifiable from data, causing singular covariance and misleading `FitResult` |
