"""CODATA 2022 physical constants for magnetism and spintronics.

Source: CODATA 2022 recommended values of the fundamental physical constants.
     https://physics.nist.gov/cuu/Constants/index.html
     NIST SP 961 (2023 edition).

Design principle (PLAN §3.1): This module contains only pure static named constants.
No runtime computation, no external dependencies. Unit strings follow SI notation.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Magnetism-related CODATA 2022 constants
# ---------------------------------------------------------------------------

# Bohr magneton μ_B  [J/T]
# CODATA 2022: 9.274 010 0657e-24 J/T
MU_B: float = 9.2740100657e-24
MU_B_UNIT: str = "J/T"

# Vacuum permeability μ_0  [N/A² = T·m/A = H/m]
# Defined value (not a measurement after the 2019 SI redefinition, but CODATA 2022 recommended):
# μ_0 = 1.25663706212e-6  H/m
# CODATA 2022: 1.25663706212e-6 N A^{-2}
MU_0: float = 1.25663706212e-6
MU_0_UNIT: str = "N/A^2"  # = H/m = T·m/A

# Reduced Planck constant ħ  [J·s]
# CODATA 2022: 1.054 571 817e-34 J·s  (exact value)
HBAR: float = 1.054571817e-34
HBAR_UNIT: str = "J*s"

# Planck constant h  [J·s]
# CODATA 2022: 6.626 070 15e-34 J·s  (exact value)
H_PLANCK: float = 6.62607015e-34
H_PLANCK_UNIT: str = "J*s"

# Boltzmann constant k_B  [J/K]
# CODATA 2022: 1.380 649e-23 J/K  (exact value)
K_B: float = 1.380649e-23
K_B_UNIT: str = "J/K"

# Elementary charge e  [C]
# CODATA 2022: 1.602 176 634e-19 C  (exact value)
E_CHARGE: float = 1.602176634e-19
E_CHARGE_UNIT: str = "C"

# Electron mass m_e  [kg]
# CODATA 2022: 9.109 383 7139e-31 kg
M_E: float = 9.1093837139e-31
M_E_UNIT: str = "kg"

# Electron g-factor g_e  [dimensionless]
# CODATA 2022: -2.002 319 304 3137  (sign included; spin magnetic moment relation)
# Note: typically |g_e| ≈ 2.0023 is used. Here the full signed value is stored.
G_E: float = -2.0023193043137
G_E_UNIT: str = "dimensionless"

# Avogadro constant N_A  [mol^-1]
# CODATA 2022: 6.022 140 76e23 mol^{-1}  (exact value)
N_A: float = 6.02214076e23
N_A_UNIT: str = "mol^-1"

# Electron gyromagnetic ratio γ_e  [rad/(s·T)]
# γ_e = |g_e| * μ_B / ħ = |g_e| * e / (2 m_e)
# CODATA 2022: 1.760 859 630e11 rad s^{-1} T^{-1}
GAMMA_E: float = 1.760859630e11
GAMMA_E_UNIT: str = "rad/(s*T)"

# Speed of light c  [m/s]  — used in oracle velocity limit checks
# CODATA 2022: 299 792 458 m/s  (exact value)
C_LIGHT: float = 2.99792458e8
C_LIGHT_UNIT: str = "m/s"

# ---------------------------------------------------------------------------
# Convenience aliases (composite constants frequently used in magnetics calculations)
# ---------------------------------------------------------------------------

# 4π × 10^-7  H/m  —  a conversion factor that appears often in CGS<->SI
# Note: not identical to μ_0 (differs at the decimal level).
#       CODATA 2022 μ_0 = 4π × 10^-7 × (1 + O(α²)), but
#       for calculations use the CODATA 2022 recommended value MU_0.
FOUR_PI_1E7: float = 4.0 * 3.141592653589793e0 * 1e-7  # ≈ 1.2566370614e-6 H/m
FOUR_PI_1E7_UNIT: str = "H/m"
