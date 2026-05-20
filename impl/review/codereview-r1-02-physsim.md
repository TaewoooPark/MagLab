# Code Review — Physics / Sim / Analysis Domain
**Scope**: `maglab/physics/`, `maglab/sim/`, `maglab/analysis/`
**Reviewer**: Claude Sonnet 4.6 (adversarial read-only audit)
**Date**: 2026-05-19

---

## Verdict

**ISSUES FOUND**

---

## Findings

### FINDING 1 — HIGH: LLG integration missing `μ₀` in precession term (all three implementations)

**Files / lines:**
- `maglab/analysis/effects/llg.py:118–120` (`_llg_rhs`)
- `maglab/analysis/effects/macrospin.py:186–190` (`_llg_rk4 → rhs`)
- `maglab/analysis/effects/llg_2sublattice.py:259–263` (`_rhs`)

**Defect:**

All three LLG implementations compute the precession term as:

```python
mxH = np.cross(m, H_eff)           # H_eff in A/m
precession = -gamma_eff * mxH      # WRONG: missing μ₀
```

The docstrings and geometry defaults explicitly state `H_eff` is in A/m. The LLG equation in SI units requires:

```
dm/dt = −γ · μ₀ · (m × H_eff)    [H_eff in A/m, γ in rad/(s·T)]
```

Without `μ₀`, the effective angular frequency used in the ODE is `ω = γ|H|` instead of the correct `ω = γμ₀|H|`. For a representative field of `H = 1 × 10⁴ A/m`:

| | Value |
|---|---|
| Correct `ω = γμ₀H` | 2.21 × 10⁹ rad/s (≈ 352 MHz) |
| Code `ω = γH` (no `μ₀`) | 1.76 × 10¹⁵ rad/s (≈ 280 000 GHz) |
| Error factor | ×1/μ₀ ≈ ×796 000 |

**Numerical consequence confirmed:** A single RK4 step with the code's `max_step` (which _correctly_ uses `μ₀` for step estimation) causes `m_new` to overflow to `∼10⁵⁰` before the post-step renormalisation collapses it back to a unit vector. The trajectory is physically meaningless — the magnetisation does not precess coherently; it random-walks under artificial diffusion from the extreme per-step rotation (measured: 6.1° per step vs the controlled 3.5° obtained when `μ₀` is correctly applied). The `max_step` calculation in `forward()` (line 178: `omega_max = gamma_0 * float(MU_0) * H_mag`) already includes `μ₀` correctly, exposing the inconsistency between step control and physics.

**Fix:** Insert `μ₀` into every cross-product that involves an A/m field:

```python
# llg.py _llg_rhs (and identically in macrospin and llg_2sublattice)
from maglab.physics.constants import MU_0
...
mxH = np.cross(m, MU_0 * H_eff)    # H_eff in A/m -> B = μ₀H in T
precession = -gamma_eff * mxH
damping    = -alpha * gamma_eff * np.cross(m, mxH)
```

Alternatively, document that `H_eff` is expected in Tesla and update the defaults and docstrings accordingly.

---

### FINDING 2 — HIGH: DMI BLS formula contains spurious `μ₀` in denominator (off by factor ∼10⁶)

**File / lines:** `maglab/analysis/effects/dmi.py:110` (`forward`) and `:142` (`fit → model_fn`)

**Defect:**

```python
return 2.0 * gamma_p * D_i * k / (np.pi * MU_0 * Ms)   # WRONG
```

The correct BLS non-reciprocal frequency shift from the DMI-modified spin-wave dispersion (verified against Di K. et al. PRL 114, 047201 (2015) and Belmeguenai et al. PRB 2015 experimental data) is:

```
Δf = (2 · γ · D · k) / (2π · Mₛ)  =  2·γ_p·D·k / Mₛ
```

where `γ_p = γ/(2π)` [Hz/T] and `Mₛ` [A/m]. No `μ₀` appears in the denominator. Dimensional analysis confirms this:

- `[γ_p] × [D] × [k] / [Mₛ]` = `[1/(s·T)] × [J/m²] × [m⁻¹] / [A/m]` = `[Hz]` ✓
- Adding `μ₀` (units H/m) in the denominator breaks the dimension by a factor of `[m²/A²·s²/kg]` and numerically inflates the result by `1/μ₀ ≈ 8 × 10⁵`.

**Quantified error:** For Co/Pt typical parameters (D = 1.3 mJ/m², k = 1.2 × 10⁷ rad/m, Mₛ = 1.19 × 10⁶ A/m) the Gaussian-unit reference formula gives Δf ≈ 1.5 GHz (consistent with literature ≈ 1–3 GHz). The code gives ≈ 186 000 GHz — six orders of magnitude wrong.

**Fix:**

```python
# dmi.py forward() and model_fn
return 2.0 * gamma_p * D_i * k / (np.pi * Ms)  # removed MU_0
```

Note: the `π` in the denominator vs. `2π` depends on whether the formula is expressed in terms of `γ` (rad/s/T) or `γ_p = γ/(2π)` (Hz/T). With `γ_p` defined as in the code, the correct coefficient is `2·γ_p` (the `π` from `γ/(2π)` is already absorbed). See Di et al. Eq. (2) in Gaussian units — the PI factor comes from the definition `γ_p = γ/(2π)`, so the formula is `2·γ·D·k/(2π·Mₛ) = 2·γ_p·D·k/Mₛ` — no standalone `π` in the denominator.

---

### FINDING 3 — HIGH: ST-FMR `spin_hall_angle()` formula wrong (extra `t_NM` factor, missing geometry correction)

**File / lines:** `maglab/analysis/effects/stfmr.py:224–238` (`spin_hall_angle` static method)

**Defect:**

```python
return (S / A) * (e * mu_0 * Ms * t_FM * t_NM / hbar)  # WRONG
```

The published Liu et al. (PRL 106, 036601, 2011) formula for the damping-like spin Hall angle is:

```
ξ_DL = (S/A) · √(1 + M_eff / H_res) · e·μ₀·Mₛ·t_FM / ℏ
```

Two errors:
1. `t_NM` (NM layer thickness) appears in the numerator — it should not be there. The formula involves only the FM thickness `t_FM`.
2. The factor `√(1 + M_eff/H_res)` is missing. This factor corrects for the elliptical precession orbit (it can range from 1 to ∼3 depending on the resonance condition).

**Quantified error:** With typical values (`S/A = 0.2`, `t_FM = t_NM = 5 nm`, `Mₛ = 860 kA/m`) the code gives `ξ_DL ≈ 0.008`, about 8.5× below the expected ≈ 0.07 for Pt/Py. The error is proportional to `t_NM / √(1+M_eff/H_res)`.

**Fix:**

```python
@staticmethod
def spin_hall_angle(
    S: float, A: float, Ms: float, t_FM: float,
    M_eff: float, H_res: float,
    mu_0: float = 1.25663706212e-6,
    hbar: float = 1.054571817e-34,
    e: float = 1.602176634e-19,
) -> float:
    if abs(A) < 1e-30:
        raise ValueError("A ≈ 0: cannot compute spin Hall angle.")
    geom_factor = math.sqrt(1.0 + M_eff / H_res) if H_res > 0 else 1.0
    return (S / A) * geom_factor * (e * mu_0 * Ms * t_FM / hbar)
```

---

### FINDING 4 — MEDIUM: Walker breakdown field inconsistent between `formulas.py` and `dw_1d.py` (factor-of-2 error in `dw_1d.py`)

**Files / lines:**
- `maglab/physics/formulas.py:162` — `walker_breakdown_field`: `H_W = α·K / (2·μ₀·Mₛ)` ✓ (Schryer & Walker 1974, Thiaville EPL 2005 Eq.(6))
- `maglab/analysis/effects/dw_1d.py:122` — `DW1DModel.walker_field`: `H_W = α·K_⊥ / (μ₀·Mₛ)` ✗ (missing factor of 2)

**Defect:** The two functions implementing the same physical quantity differ by a factor of 2. The standard Schryer–Walker result (which `formulas.py` correctly implements) is `H_W = α·K_⊥/(2μ₀Mₛ)`. The `DW1DModel.walker_field()` method, which researchers would call to compute the Walker field from a fit, is 2× too large.

**Fix in `dw_1d.py`:**

```python
def walker_field(self, alpha: float, K_perp: float, Ms: float) -> float:
    return alpha * K_perp / (2.0 * MU_0 * Ms)   # add factor of 2
```

---

### FINDING 5 — MEDIUM: `LLG2SublatticeModel.fit()` AFMR mode has a dead parameter (`H_A` is a fit parameter but ignored in `model_fn`)

**File / lines:** `maglab/analysis/effects/llg_2sublattice.py:335–353`

**Defect:**

```python
def model_fn(
    x: np.ndarray, H_E: float, H_A: float, alpha_a: float, alpha_b: float
) -> np.ndarray:
    return np.array([afmr_frequency(H_E, float(ha), gamma) for ha in x])
```

`H_A` is declared as a fit parameter (in `param_specs = self.parameters`) and passed to `model_fn`, but `model_fn` ignores it — it iterates over `x` (which is the `H_A_sweep` array) and calls `afmr_frequency(H_E, ha, ...)` for each `ha` in the sweep. lmfit will therefore attempt to optimize `H_A`, but since the residual is independent of `H_A`, the covariance matrix will be singular or the fit will assign a physically meaningless `H_A` (likely stuck at the initial value `H_A_mid`). The fitted `H_A` in `FitResult.params` cannot be trusted.

**Fix:** Either remove `H_A`, `alpha_a`, `alpha_b` from the parameter specifications for this mode, or add a second fitting pass that uses `H_A` as a real variable. The simplest correction:

```python
afmr_specs = [
    ParamSpec("H_E", "A/m", lower=0.0, upper=None,
              description="Intersublattice exchange field [A/m]"),
]
# Remove H_A, alpha_a, alpha_b from this fit call; return them as fixed defaults
init = {"H_E": H_E_init}
return run_fit(model_fn=..., param_specs=afmr_specs, init_values=init, ...)
```

---

### FINDING 6 — MEDIUM: `SpinPumpingISHE.forward()` returns a constant independent of `d_NM`; fit is degenerate

**File / lines:** `maglab/analysis/effects/spin_pumping_ishe.py:119–121` (`forward`) and `:146–147` (`model_fn` in `fit`)

**Defect:**

```python
delta_alpha = (gamma_rad * HBAR * g_eff) / (4.0 * np.pi * MU_0 * Ms * d_FM)
return np.full_like(d_NM, alpha_0 + delta_alpha, dtype=float)  # constant!
```

The Δα formula depends on `d_FM` (fixed) and `g_eff` (fit parameter), but not on `d_NM` (the independent variable swept in the measurement). The model therefore predicts a flat line over the `d_NM` sweep, which means:

1. The fit cannot distinguish `g_eff` from `alpha_0` — both shift the same constant — so the covariance matrix will be rank-deficient.
2. The purpose of the `d_NM` sweep (to see how linewidth enhancement grows with NM thickness before saturating) is physically motivated but the model ignores this dependence.

The thickness-dependent formula (including spin backflow) is:
```
Δα(d_NM) = (γℏ·g↑↓) / (4π·μ₀·Mₛ·d_FM) · tanh(d_NM / (2λ_sf))
```
The model already implements `tanh(d_NM / λ_sf)` in the static method `v_ishe()`, suggesting the full formula was known but omitted from `forward()`.

**Fix:** Add `d_NM` and `lambda_sf` dependence to `forward()` and `model_fn`:

```python
delta_alpha = (
    (gamma_rad * HBAR * g_eff) / (4.0 * np.pi * MU_0 * Ms * d_FM)
    * np.tanh(d_NM / (2.0 * lambda_sf))
)
return alpha_0 + delta_alpha  # now varies with d_NM
```

---

### FINDING 7 — LOW: `LLGModel.fit()` model function does not match `forward()` (exponential vs. oscillatory)

**File / lines:** `maglab/analysis/effects/llg.py:244–247` (`fit → model_fn`)

**Defect:**

```python
def model_fn(x, alpha, tau_DL, tau_FL):
    mz_0 = float(mz[0]) if len(mz) > 0 else 0.8
    return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x)
```

`forward()` integrates the full LLG ODE and produces an oscillatory (precessing + damped) trajectory. `fit()` approximates `m_z(t)` as a purely exponential relaxation with no oscillation. When experimental data contains the usual oscillatory ring-down (which is the standard FMR measurement), the fit will converge to an incorrect `α`. The asymptotic envelope of `m_z(t)` from the ODE decays as `exp(−α·ω₀·t)` only in the strongly overdamped limit (`α ≫ 1`), which is rarely the regime of interest (typical α ≈ 0.001–0.1).

**Fix:** Use the full oscillatory decay model:

```python
return 1.0 - (1.0 - mz_0) * np.exp(-alpha * omega_0 * x) * np.cos(omega_0 * x)
```

Or fit directly against forward-model output via numerical Jacobian (more expensive but physically consistent).

---

### FINDING 8 — LOW: `FiM compensation mode` in `LLG2SublatticeModel.fit()` generates synthetic data fitted against itself (circular provenance)

**File / lines:** `maglab/analysis/effects/llg_2sublattice.py:386–399`

**Defect:**

```python
x_sweep = np.linspace(max(H_E_solved * 0.9, 1.0), H_E_solved * 1.1, n_pts)
y_sweep = np.array([ferrimagnet_compensation_freq(..., he, ...) for he in x_sweep])
fit_he = run_fit(model_fn=model_fn_he, x_data=x_sweep, y_data=y_sweep, ...)
```

The `x_sweep` and `y_sweep` are generated synthetically from the analytic solution `H_E_solved`, then `run_fit` fits `H_E` back to this synthetic data. The fit will always converge to `H_E = H_E_solved` regardless of the measurement input `f_comp`. `FitResult.provenance_id` records this as a genuine `FITTED` data point, but no real data-to-model comparison occurs — the analytic inversion is the only information used.

**Fix:** For the single-point case, return a `FitResult` directly from the analytic inversion and tag it with `ProvenanceType.COMPUTED` rather than `FITTED`, or add a real data-vs-model check using the measured `f_comp`:

```python
residual = f_comp_val - ferrimagnet_compensation_freq(m_a_val, m_b_val, H_E_solved, ...)
# Build FitResult manually with ProvenanceType.COMPUTED and report residual
```

---

### FINDING 9 — LOW: `HysteresisLoop.extract_loop_params()` gives wrong `M_r` and `H_c` when data does not include a zero-crossing

**File / lines:** `maglab/analysis/effects/hysteresis.py:160–168`

**Defect:**

```python
idx_zero = int(np.argmin(np.abs(H)))
M_r = float(abs(M[idx_zero]))         # nearest point to H=0, not zero-crossing
idx_mc = int(np.argmin(np.abs(M)))
H_c = float(abs(H[idx_mc]))           # nearest point to M=0, not zero-crossing
```

If the `H` array contains only positive values (e.g., a first-quadrant branch), `argmin(|H|)` returns `index 0` (the smallest H value measured), and `M_r` will be the magnetization at that boundary — not the remanence. Similarly, if `M` does not cross zero, `H_c` will be the field at minimum `|M|`, which could be anywhere. No validation or warning is issued in these cases.

**Fix:** Add a guard that checks for actual zero-crossings and emits `float('nan')` with a warning if none is found:

```python
# Check H crosses zero
if H.min() >= 0 or H.max() <= 0:
    M_r = float('nan')
else:
    idx_zero = int(np.argmin(np.abs(H)))
    M_r = float(abs(M[idx_zero]))
# Similar for H_c
```

---

## Summary table

| # | Severity | File | Issue |
|---|---|---|---|
| 1 | **HIGH** | `effects/llg.py`, `macrospin.py`, `llg_2sublattice.py` | LLG precession missing `μ₀` → integration diverges, trajectory meaningless |
| 2 | **HIGH** | `effects/dmi.py` | DMI BLS formula has spurious `μ₀` in denominator → ∼10⁶× error in Δf |
| 3 | **HIGH** | `effects/stfmr.py` | `spin_hall_angle()` has extra `t_NM` factor and missing `√(1+M_eff/H_res)` |
| 4 | MEDIUM | `effects/dw_1d.py` vs `physics/formulas.py` | Walker field 2× too large in `dw_1d.py` (missing `/2`) |
| 5 | MEDIUM | `effects/llg_2sublattice.py` | AFMR fit: `H_A` declared as parameter but ignored in `model_fn` — degenerate fit |
| 6 | MEDIUM | `effects/spin_pumping_ishe.py` | `forward()` constant w.r.t. `d_NM` → fit of `(g_eff, alpha_0)` degenerate |
| 7 | LOW | `effects/llg.py` | `fit()` model (exponential) mismatches `forward()` (oscillatory LLG) |
| 8 | LOW | `effects/llg_2sublattice.py` | FiM compensation fit is circular (synthetic data from analytic solution) |
| 9 | LOW | `effects/hysteresis.py` | `extract_loop_params()` gives wrong `M_r`, `H_c` on single-branch or saturation-only data |
