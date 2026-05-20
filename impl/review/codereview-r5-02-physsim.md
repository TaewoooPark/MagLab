# Code Review Round 5 — Physics / Sim / Analysis Domain

**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19
**Based on**: current code after Rounds 1–4 patches

---

## Round-4 Patch Verification

All four findings from Round 4 have been correctly applied:

| R4 Finding | Status |
|---|---|
| `llg_2sublattice.py:268` no internal step-size control | **FIXED** — oversampled internal grid (≥10 steps per exchange period) now implemented at lines 278–295 |
| `stfmr.py:267` spin_hall_angle formula — confirmed correct in R1–R3 and re-examined | **CONFIRMED** — formula retained; R4 re-examination did not add new patches |
| `fmr_kittel.py:134` OOP mode negative frequency | **FIXED** — `np.abs(H_Am - M_eff)` now used in both `forward()` and `fit()` `model_fn` |
| `llg.py:252` + `macrospin.py:344` ghost `tau_DL`/`tau_FL` parameters | **FIXED** — both models now use a reduced `alpha_spec` and a single-parameter `model_fn`; ghost params reported as fixed defaults post-fit |

---

## Verdict

**ISSUES FOUND**

---

## Findings

### FINDING 1 — HIGH: `ferrimagnet_compensation_freq` returns ω (rad/s) but docstring claims Hz; FiM inversion in `LLG2SublatticeModel.fit()` is off by factor 2π

**Files / lines:**
- `maglab/physics/formulas.py:516,522`
- `maglab/analysis/effects/llg_2sublattice.py:432,441–442`

**Defect:**

`ferrimagnet_compensation_freq` computes:

```python
return (numerator / denominator) * MU_0 * H_ex_ab
```

where `numerator = |γ_a m_a − γ_b m_b|` (units: rad/(s·T) × A/m = rad·A/(s·T·m)).

Dimensional analysis:
```
[rad/(s·T)] × [A/m]   ×   [T·m/A]   ×   [A/m]   =   rad/s
   (gamma*m)                (mu_0)       (H_ex)
```

The function returns **angular frequency ω [rad/s]**, not frequency f [Hz]. The docstring at line 516 states `Returns: Resonance frequency [Hz]`, which is incorrect.

`LLG2SublatticeModel.fit()` FiM compensation mode (line 432) inverts this formula assuming the input `f_comp` is in Hz:

```python
H_E_solved = f_comp_val * (m_a + m_b) / (denom_gamma * MU_0)
```

The correct inversion (from `omega = 2π·f`) should be:

```python
H_E_solved = f_comp_val * 2.0 * math.pi * (m_a + m_b) / (denom_gamma * MU_0)
```

**Quantified error:**
- Algebraic cancellation at line 441–442 makes `residual = |f_comp - f_model| ≈ 0` always, silently masking the wrong `H_E_solved`.
- For a typical FiM (GdFe at 500 GHz compensation frequency): `H_E_solved` is too small by factor `2π ≈ 6.28`.

```
True H_E = 1.0 × 10⁸ A/m
Code H_E = 1.0 × 10⁸ / (2π) ≈ 1.59 × 10⁷ A/m
chi2 reported = 0 (false — algebraic identity, not convergence)
```

**Fix:**

1. In `formulas.py:522`, either rename the return to reflect angular frequency and update docstring, or divide by `2π` before returning:
   ```python
   return (numerator / denominator) * MU_0 * H_ex_ab / (2.0 * math.pi)
   ```
2. In `llg_2sublattice.py:432`, add the missing `2π`:
   ```python
   H_E_solved = f_comp_val * 2.0 * math.pi * (m_a + m_b) / (denom_gamma * MU_0)
   ```
   Both changes must be made together for consistency.

---

### FINDING 2 — HIGH: `SpinPumpingISHE.forward()` and `fit()` have spurious `MU_0` in the Δα denominator — `g↑↓` is wrong by factor ≈ 8×10⁵

**File / lines:** `maglab/analysis/effects/spin_pumping_ishe.py:134,158`

**Defect:**

`forward()` at line 134:
```python
prefactor = (gamma_rad * HBAR * g_eff) / (4.0 * np.pi * MU_0 * Ms * d_FM)
```

`fit()` model function at line 158:
```python
prefactor = (gamma_rad * HBAR) / (4.0 * np.pi * MU_0 * Ms * d_FM)
```

The Mosendz et al. (PRB 82, 214403, 2010), Eq. (2) formula for the spin-pumping Gilbert damping enhancement is:

```
Δα = (g·μ_B · g↑↓) / (4π · M_s · d_FM)
   = (γ_e · ħ · g↑↓) / (4π · M_s · d_FM)
```

where `g·μ_B = γ_e·ħ` and there is **no μ₀ in the denominator**.

The code's inclusion of `MU_0 = 1.257×10⁻⁶` H/m in the denominator makes the prefactor `1/MU_0 ≈ 7.96×10⁵` times too large.

**Dimensional analysis of the correct formula:**
```
[rad/(s·T)] × [J·s] × [m⁻²]   /   [A/m]   ×   [m]
=  rad·J/(T·m²·s⁻¹)  /  A    =  dimensionless  ✓
```

The μ₀ factor has units T·m/A; including it breaks dimensional homogeneity and multiplies Δα by `1/μ₀ ≈ 8×10⁵`.

**Quantified error:**

For Pt(5nm)/Py(5nm) with `g↑↓_true = 5×10¹⁹ m⁻²`, `Ms = 860 kA/m`, `d_FM = 5 nm`:

| Quantity | Correct formula | Code formula |
|---|---|---|
| `prefactor` | `8.59×10⁻³` | `6.84×10³` |
| `Δα` at saturation | `~0.009` | `~6840` (unphysical) |
| `g↑↓` from fit | `5.00×10¹⁹ m⁻²` | `6.28×10¹³ m⁻²` (off by μ₀) |

**Self-consistency note:** `forward()` and `fit()` use the same wrong prefactor, so model predictions are internally consistent — fitting converges. However, the extracted `g↑↓` is off by factor `μ₀ ≈ 1.26×10⁻⁶`, i.e., a ~6 orders of magnitude error in the physical quantity.

**Fix:** Remove `MU_0` from the denominator in both `forward()` and `fit()`:

```python
# forward() line 134:
prefactor = (gamma_rad * HBAR * g_eff) / (4.0 * np.pi * Ms * d_FM)

# fit() line 158:
prefactor = (gamma_rad * HBAR) / (4.0 * np.pi * Ms * d_FM)
```

---

### FINDING 3 — MEDIUM: `SMR.fit()` — `delta_rho_2` is a ghost parameter in both `model_fn_single` and `multi_model_fn`; singular covariance and misleading `FitResult`

**File / lines:** `maglab/analysis/effects/smr.py:191–215`

**Defect:**

`SMR.fit()` fits from `rho_long` data only (Hall data `rho_hall` is present in `data` but never used in the residual). Both fitting branches define a `model_fn` that does not include `delta_rho_2`:

```python
# Single-geometry fallback (line 191–194):
def model_fn_single(x, rho_0, delta_rho_1, delta_rho_2):
    _m = self._m_y(x, geom_key)
    return rho_0 + delta_rho_1 * (1.0 - _m**2)   # delta_rho_2 unused

# Multi-dataset (line 211–215):
def multi_model_fn(x, geom_str, rho_0, delta_rho_1, delta_rho_2):
    m_y = self._m_y(x, geom_str)
    return rho_0 + delta_rho_1 * (1.0 - m_y**2)  # delta_rho_2 unused
```

In both cases `delta_rho_2` is passed to `run_fit` / `run_fit_multi` via `self.parameters` (which includes it), but the residual is independent of it. Consequently:
1. The Jacobian column for `delta_rho_2` is identically zero.
2. lmfit cannot compute `stderr` for `delta_rho_2`; it will be `0.0` or `NaN`.
3. The covariance matrix is singular for the `delta_rho_2` row/column.
4. `FitResult.params["delta_rho_2"]` reports the initial guess value, not a fitted value.

`delta_rho_2 = Δρ₂` (the SMR Hall coefficient) is a key physical quantity used to extract `θ_SH`. Returning it as a ghost value from `FitResult` without warning is misleading.

This is the same pattern as R4 Finding 4 (LLG `tau_DL`/`tau_FL` ghost parameters), which was patched for `llg.py` and `macrospin.py` but missed in `smr.py`.

**Fix:**

Option (a) — fit `delta_rho_2` from `rho_hall` in a separate pass, or add `rho_hall` data to the multi-dataset residual.

Option (b) — restrict the `fit()` `param_specs` to `[rho_0, delta_rho_1]` (matching only what `rho_long` can determine), add `delta_rho_2` post-fit with `0.0` uncertainty:

```python
long_specs = [p for p in self.parameters if p.name in ("rho_0", "delta_rho_1")]
# fit with long_specs only
fit_result.params.setdefault("delta_rho_2", float("nan"))
fit_result.uncertainties.setdefault("delta_rho_2", float("nan"))
```

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **HIGH** | `physics/formulas.py:522` + `effects/llg_2sublattice.py:432` | `ferrimagnet_compensation_freq` returns rad/s not Hz; FiM inversion missing `2π` → `H_E` off by factor 6.28, masked by chi2=0 |
| 2 | **HIGH** | `effects/spin_pumping_ishe.py:134,158` | Spurious `MU_0` in Δα denominator (Mosendz 2010 formula has no μ₀); fitted `g↑↓` off by factor μ₀ ≈ 1.26×10⁻⁶ (~6 orders of magnitude) |
| 3 | **MEDIUM** | `effects/smr.py:191,211` | `delta_rho_2` ghost parameter in `model_fn_single` and `multi_model_fn`; singular covariance, misleading `FitResult.params["delta_rho_2"]` |
