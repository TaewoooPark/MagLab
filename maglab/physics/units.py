"""Magnetic unit conversion table.

Provides CGS <-> SI unit conversion functions used in magnetics experiments and theory.
All conversions are invertible (round-trip) and deterministic.

Unit system summary:
  Magnetic field H : Oe (CGS-Gaussian) <-> A/m (SI) <-> T (μ₀H basis)
  Magnetization M  : emu/cm³ (CGS)     <-> A/m (SI)
  Energy density   : erg/cm³            <-> J/m³
  Energy/length    : erg/cm (DW energy) <-> J/m
  Exchange energy  : meV                <-> K  (J_ij exchange parameter)
  DMI              : mJ/m²              <-> meV/Å²
  Magnetic aniso.  : erg/cm³            <-> J/m³  (same as energy density)

Conversion factor sources:
  1 Oe = (1000/4π) A/m  ≈ 79.5775 A/m   [Jackson, Classical Electrodynamics 3ed front cover]
  1 emu/cm³ = 1000 A/m                  [SI/Gaussian definition]
  1 erg/cm³ = 0.1 J/m³                  [SI/CGS energy conversion]
  1 erg/cm  = 1e-3 J/m                  [SI/CGS energy/length]
  1 meV     = e * 1e-3 J                [elementary charge definition]
  1 K       = k_B * 1 J                 [Boltzmann constant definition]

Design principle (PLAN §9): Implemented directly without pint dependency. Purely deterministic.
"""

from __future__ import annotations

import math

from maglab.physics.constants import E_CHARGE, K_B, MU_0

# ---------------------------------------------------------------------------
# Internal factors (intermediate constants used by conversion routines)
# ---------------------------------------------------------------------------

# 1 Oe -> A/m : 1/(4π × 10⁻³)  =  1000/(4π)
_OE_TO_AM: float = 1000.0 / (4.0 * math.pi)  # ≈ 79.5775 A/m

# 1 emu/cm³ -> A/m
_EMU_CM3_TO_AM: float = 1000.0  # A/m per emu/cm³

# 1 erg/cm³ -> J/m³
_ERG_CM3_TO_JM3: float = 0.1  # J/m³ per erg/cm³

# 1 erg/cm -> J/m
_ERG_CM_TO_JM: float = 1e-3  # J/m per erg/cm

# 1 meV -> J
_MEV_TO_J: float = E_CHARGE * 1e-3  # ≈ 1.60218e-22 J

# 1 K -> J  (k_B basis)
_K_TO_J: float = K_B  # ≈ 1.38065e-23 J


# ===========================================================================
# Magnetic field H
# ===========================================================================


def oe_to_am(h_oe: float) -> float:
    """Convert magnetic field from Oersted (Oe) to A/m.

    Conversion factor: 1 Oe = 1000/(4π) A/m ≈ 79.5775 A/m.

    Args:
        h_oe: Magnetic field [Oe].

    Returns:
        Magnetic field [A/m].
    """
    return h_oe * _OE_TO_AM


def am_to_oe(h_am: float) -> float:
    """Convert magnetic field from A/m to Oersted (Oe).

    Args:
        h_am: Magnetic field [A/m].

    Returns:
        Magnetic field [Oe].
    """
    return h_am / _OE_TO_AM


def am_to_tesla(h_am: float) -> float:
    """Convert magnetic field H from A/m to μ₀H (in Tesla).

    Note: This is μ₀H, not B (magnetic flux density).
    μ₀H = μ₀ × H, and B = μ₀H only in vacuum.

    Args:
        h_am: Magnetic field [A/m].

    Returns:
        μ₀H [T].
    """
    return MU_0 * h_am


def tesla_to_am(mu0h_t: float) -> float:
    """Convert μ₀H (T) to magnetic field H [A/m].

    Args:
        mu0h_t: μ₀H [T].

    Returns:
        Magnetic field H [A/m].
    """
    return mu0h_t / MU_0


def oe_to_tesla(h_oe: float) -> float:
    """Convert magnetic field from Oe to μ₀H (T).

    Args:
        h_oe: Magnetic field [Oe].

    Returns:
        μ₀H [T].
    """
    return am_to_tesla(oe_to_am(h_oe))


def tesla_to_oe(mu0h_t: float) -> float:
    """Convert μ₀H (T) to Oersted (Oe).

    Args:
        mu0h_t: μ₀H [T].

    Returns:
        Magnetic field H [Oe].
    """
    return am_to_oe(tesla_to_am(mu0h_t))


# ===========================================================================
# Magnetization M
# ===========================================================================


def emu_cm3_to_am(m_emu: float) -> float:
    """Convert magnetization from emu/cm³ to A/m.

    Conversion factor: 1 emu/cm³ = 1000 A/m.

    Args:
        m_emu: Magnetization [emu/cm³].

    Returns:
        Magnetization [A/m].
    """
    return m_emu * _EMU_CM3_TO_AM


def am_to_emu_cm3(m_am: float) -> float:
    """Convert magnetization from A/m to emu/cm³.

    Args:
        m_am: Magnetization [A/m].

    Returns:
        Magnetization [emu/cm³].
    """
    return m_am / _EMU_CM3_TO_AM


# ===========================================================================
# Energy density (anisotropy constant K, exchange energy density, etc.)
# ===========================================================================


def erg_cm3_to_jm3(e_erg: float) -> float:
    """Convert energy density from erg/cm³ to J/m³.

    Conversion factor: 1 erg/cm³ = 0.1 J/m³.

    Args:
        e_erg: Energy density [erg/cm³].

    Returns:
        Energy density [J/m³].
    """
    return e_erg * _ERG_CM3_TO_JM3


def jm3_to_erg_cm3(e_jm3: float) -> float:
    """Convert energy density from J/m³ to erg/cm³.

    Args:
        e_jm3: Energy density [J/m³].

    Returns:
        Energy density [erg/cm³].
    """
    return e_jm3 / _ERG_CM3_TO_JM3


# ===========================================================================
# Energy/length (domain wall energy σ)
# ===========================================================================


def erg_cm_to_jm(sigma_erg: float) -> float:
    """Convert energy/length from erg/cm to J/m.

    Conversion factor: 1 erg/cm = 1e-3 J/m.

    Args:
        sigma_erg: Energy/length [erg/cm].

    Returns:
        Energy/length [J/m].
    """
    return sigma_erg * _ERG_CM_TO_JM


def jm_to_erg_cm(sigma_jm: float) -> float:
    """Convert energy/length from J/m to erg/cm.

    Args:
        sigma_jm: Energy/length [J/m].

    Returns:
        Energy/length [erg/cm].
    """
    return sigma_jm / _ERG_CM_TO_JM


# ===========================================================================
# Exchange energy J_ij : meV <-> K
# ===========================================================================


def mev_to_kelvin(e_mev: float) -> float:
    """Convert exchange energy from meV to K (J_ij parameter).

    Conversion: T_K = E_meV × (e × 10^-3) / k_B.

    Args:
        e_mev: Energy [meV].

    Returns:
        Equivalent temperature [K].
    """
    return e_mev * _MEV_TO_J / _K_TO_J


def kelvin_to_mev(t_k: float) -> float:
    """Convert equivalent temperature (K) to meV energy (J_ij parameter).

    Args:
        t_k: Equivalent temperature [K].

    Returns:
        Energy [meV].
    """
    return t_k * _K_TO_J / _MEV_TO_J


# ===========================================================================
# DMI energy : mJ/m² <-> meV/Å²
# ===========================================================================

# 1 Å² = 1e-20 m² -> 1 meV/Å² = 1e-3 eV / 1e-20 m² = 1e-3 × e / 1e-20 J/m²
_MEV_A2_TO_MJM2: float = (_MEV_TO_J / 1e-20) * 1e3  # meV/Å² -> mJ/m²
# Simplified: 1 meV/Å² = e × 1e-3 / 1e-20 × 1e3 mJ/m² = e × 1e10 × 1e-3 mJ/m²
# = 1.60218e-22 / 1e-20 × 1e3 mJ/m² = 1.60218 × 1e3 × 1e-3 mJ/m² = 1.60218 mJ/m²


def mev_a2_to_mjm2(d_mev: float) -> float:
    """Convert DMI coefficient from meV/Å² to mJ/m².

    Args:
        d_mev: DMI coefficient [meV/Å²].

    Returns:
        DMI coefficient [mJ/m²].
    """
    return d_mev * _MEV_A2_TO_MJM2


def mjm2_to_mev_a2(d_mjm2: float) -> float:
    """Convert DMI coefficient from mJ/m² to meV/Å².

    Args:
        d_mjm2: DMI coefficient [mJ/m²].

    Returns:
        DMI coefficient [meV/Å²].
    """
    return d_mjm2 / _MEV_A2_TO_MJM2


# ===========================================================================
# Exchange stiffness A : erg/cm <-> J/m  (also handled by erg_cm_to_jm, alias provided)
# ===========================================================================


def exchange_erg_cm_to_jm(a_erg: float) -> float:
    """Convert exchange stiffness from erg/cm to J/m.

    A [J/m] = A [erg/cm] × 10^-3.

    Args:
        a_erg: Exchange stiffness [erg/cm].

    Returns:
        Exchange stiffness [J/m].
    """
    return erg_cm_to_jm(a_erg)


def exchange_jm_to_erg_cm(a_jm: float) -> float:
    """Convert exchange stiffness from J/m to erg/cm.

    Args:
        a_jm: Exchange stiffness [J/m].

    Returns:
        Exchange stiffness [erg/cm].
    """
    return jm_to_erg_cm(a_jm)


# ===========================================================================
# CGS <-> SI conversion factor dictionary (for reference)
# ===========================================================================

CGS_SI_FACTORS: dict[str, tuple[float, str, str]] = {
    # name : (SI = CGS × factor, CGS unit, SI unit)
    "H_field": (_OE_TO_AM, "Oe", "A/m"),
    "M_magnetization": (_EMU_CM3_TO_AM, "emu/cm³", "A/m"),
    "energy_density": (_ERG_CM3_TO_JM3, "erg/cm³", "J/m³"),
    "energy_per_length": (_ERG_CM_TO_JM, "erg/cm", "J/m"),
    "exchange_stiffness": (_ERG_CM_TO_JM, "erg/cm", "J/m"),
}
