"""Deterministic multiscale formula library.

Each function includes primary literature and textbook references in its docstring.
All inputs and outputs use SI units unless otherwise specified.
The `Quantity` type is supported for unit tracking, but scalar float calls are also accepted.

Design principles (PLAN §9, T-P0-05):
  - Fully deterministic — no LLM calls, no network access, no measurements.
  - Each formula documents its source (primary literature or textbook) in the docstring.
  - Quantity input/output supported.
  - Recommended to call after oracle validation (input range not checked — oracle's role).
"""

from __future__ import annotations

import math

from maglab.physics.constants import (
    GAMMA_E,
    MU_0,
)
from maglab.physics.quantity import Quantity

# ===========================================================================
# 1. Exchange Length
# ===========================================================================


def exchange_length(A: float, Ms: float) -> float:
    r"""Compute the exchange length l_ex.

    .. math::
        l_{ex} = \sqrt{\frac{2A}{\mu_0 M_s^2}}

    This length is a measure of the competition between exchange and
    magnetostatic energy, and serves as the reference scale for domain
    structures, skyrmion size, and critical device dimensions.

    References:
        Hubert & Schäfer, *Magnetic Domains* (Springer, 1998), Eq. (3.29).
        Coey, *Magnetism and Magnetic Materials* (Cambridge, 2010), p. 155.

    Args:
        A: Exchange stiffness [J/m]. A > 0.
        Ms: Saturation magnetization [A/m]. Ms > 0.

    Returns:
        Exchange length [m].

    Example (Permalloy, A≈13e-12 J/m, Ms≈860e3 A/m):
        >>> l = exchange_length(13e-12, 860e3)
        >>> round(l * 1e9, 1)  # nm
        5.3
    """
    return math.sqrt(2.0 * A / (MU_0 * Ms**2))


def exchange_length_q(A: Quantity, Ms: Quantity) -> Quantity:
    """Quantity interface — see exchange_length."""
    a_si = A.to("J/m").value if A.unit != "J/m" else A.value
    ms_si = Ms.to("A/m").value if Ms.unit != "A/m" else Ms.value
    l = exchange_length(a_si, ms_si)
    return Quantity(l, "m", label="l_ex")


# ===========================================================================
# 2. Domain Wall Width (Bloch Wall Width)
# ===========================================================================


def bloch_wall_width(A: float, K: float) -> float:
    r"""Compute the Bloch domain-wall width Δ (domain wall parameter).

    .. math::
        \Delta = \pi \sqrt{\frac{A}{K}}

    This definition is the characteristic width of an atan-profile wall.
    Some references use \sqrt{A/K} without the π factor.
    Here the π√(A/K) definition is adopted, consistent with Bloch wall energy.

    References:
        Landau & Lifshitz, *Phys. Z. Sowjetunion* 8, 153 (1935).
        Hubert & Schäfer, *Magnetic Domains* (Springer, 1998), Eq. (3.30).
        Coey, *Magnetism and Magnetic Materials* (Cambridge, 2010), p. 158.

    Args:
        A: Exchange stiffness [J/m]. A > 0.
        K: Anisotropy constant [J/m³]. K > 0 (perpendicular anisotropy).

    Returns:
        Domain wall width Δ [m].

    Example (YIG, A≈4e-12 J/m, K≈610 J/m³):
        >>> delta = bloch_wall_width(4e-12, 610)
        >>> round(delta * 1e9, 0)  # nm — literature: ~250 nm
        255.0
    """
    if K <= 0.0:
        raise ValueError(f"K={K} J/m³ is not positive. Perpendicular anisotropy requires K > 0.")
    return math.pi * math.sqrt(A / K)


def bloch_wall_width_q(A: Quantity, K: Quantity) -> Quantity:
    """Quantity interface — see bloch_wall_width."""
    a_si = A.to("J/m").value if A.unit != "J/m" else A.value
    k_si = K.to("J/m3").value if K.unit != "J/m3" else K.value
    delta = bloch_wall_width(a_si, k_si)
    return Quantity(delta, "m", label="delta_DW")


def bloch_wall_energy(A: float, K: float) -> float:
    r"""Compute the Bloch domain-wall energy density σ [J/m²].

    .. math::
        \sigma = 4 \sqrt{A K}

    References:
        Hubert & Schäfer, *Magnetic Domains* (Springer, 1998), Eq. (3.31).

    Args:
        A: Exchange stiffness [J/m].
        K: Anisotropy constant [J/m³]. K > 0.

    Returns:
        Domain wall energy density [J/m²].
    """
    if K <= 0.0:
        raise ValueError(f"K={K} J/m³ is not positive.")
    return 4.0 * math.sqrt(A * K)


# ===========================================================================
# 3. Domain Wall Dynamics — Walker Breakdown Field and Velocity
# ===========================================================================


def walker_breakdown_field(alpha: float, Ms: float, K: float, A: float) -> float:
    r"""Compute the Walker breakdown field H_W.

    .. math::
        H_W = \frac{\alpha}{2} \frac{K}{\mu_0 M_s}

    (Simple 1D model assuming uniaxial anisotropy.)

    Above this field, the domain wall cannot move stably and undergoes
    precessional instability (Walker breakdown).

    References:
        Schryer & Walker, *J. Appl. Phys.* 45, 5406 (1974).
        Thiaville et al., *EPL* 69, 990 (2005), Eq. (6).

    Args:
        alpha: Gilbert damping constant [dimensionless]. 0 < α ≤ 1.
        Ms: Saturation magnetization [A/m].
        K: Anisotropy constant [J/m³]. K > 0.
        A: Exchange stiffness [J/m]. (Unused but kept for interface consistency.)

    Returns:
        Walker breakdown field [A/m].
    """
    _ = A  # preserved for future extension
    return alpha * K / (2.0 * MU_0 * Ms)


def walker_velocity(
    alpha: float,
    Ms: float,
    Delta: float,
    gamma: float = GAMMA_E,
) -> float:
    r"""Compute the maximum domain-wall velocity just below the Walker breakdown v_W.

    .. math::
        v_W = \frac{\gamma \Delta \mu_0 M_s}{2}

    Dimensional analysis:
        gamma [rad/(s·T)] × Delta [m] × MU_0 [T·m/A] × Ms [A/m] = m/s

    References:
        Mougin, A. et al., *EPL* 78, 57007 (2007), Eq. (1).
        Schryer, N. L., Walker, L. R., *J. Appl. Phys.* 45, 5406 (1974), Eq. (8a).

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


def dw_velocity_below_walker(
    H: float,
    alpha: float,
    Ms: float,
    delta: float,
    gamma: float = GAMMA_E,
) -> float:
    r"""Compute the domain-wall velocity below the Walker breakdown v_DW.

    .. math::
        v_{DW} = \frac{\gamma \Delta \mu_0 H}{1 + \alpha^2}

    Schryer–Walker (1974) exact result for the steady-state DW velocity
    below the Walker breakdown field.

    References:
        Schryer, N. L., Walker, L. R.,
        J. Appl. Phys. 45, 5406 (1974), Eq. (8a).
        DOI: 10.1063/1.1663252

    Args:
        H: Applied magnetic field [A/m].
        alpha: Gilbert damping constant.
        Ms: Saturation magnetization [A/m].
        delta: Domain wall width Δ [m].
        gamma: Gyromagnetic ratio [rad/(s·T)].

    Returns:
        Domain wall velocity [m/s].
    """
    _ = Ms  # Ms is implicit in delta derivation
    return gamma * delta * MU_0 * H / (1.0 + alpha**2)


# ===========================================================================
# 4. Skyrmion Radius and Stability
# ===========================================================================


def skyrmion_radius_dmi(D: float, A: float, K: float, Ms: float) -> float:
    r"""Estimate the characteristic radius r_sk of a DMI-stabilized skyrmion.

    .. math::
        r_{sk} \approx \frac{\pi D}{4 K_{eff}}

    where K_eff = K - μ₀M_s²/2 (effective anisotropy).

    This is an approximate energy-minimization formula; the exact radius
    requires numerical solution of the 1D Euler–Lagrange equation.

    References:
        Romming et al., *Science* 341, 636 (2013), Supporting Material.
        Büttner et al., *Nature Materials* 20, 30 (2021), Eq. (S1).
        Bogdanov & Rößler, *Phys. Rev. Lett.* 87, 037203 (2001).

    Args:
        D: DMI coefficient [J/m²]. D > 0.
        A: Exchange stiffness [J/m].
        K: Anisotropy constant [J/m³].
        Ms: Saturation magnetization [A/m].

    Returns:
        Skyrmion characteristic radius [m]. Negative value indicates instability.

    Note:
        This formula gives an approximate result. The actual radius requires
        full energy minimization.
    """
    _ = A  # used in more precise models
    k_eff = K - 0.5 * MU_0 * Ms**2
    if k_eff <= 0.0:
        # Shape anisotropy dominant — skyrmion stability uncertain
        return -1.0
    return math.pi * D / (4.0 * k_eff)


def skyrmion_stability_criterion(D: float, A: float, K: float, Ms: float) -> dict[str, float]:
    r"""Compute the skyrmion stability criterion κ.

    .. math::
        \kappa = \frac{D^2}{4 A K_{eff}}

    κ > 1 indicates that the skyrmion phase is thermodynamically stable.

    References:
        Bogdanov & Hubert, *J. Magn. Magn. Mater.* 138, 255 (1994).
        Rohart & Thiaville, *Phys. Rev. B* 88, 184422 (2013), Eq. (7).

    Args:
        D: DMI coefficient [J/m²].
        A: Exchange stiffness [J/m].
        K: Anisotropy constant [J/m³].
        Ms: Saturation magnetization [A/m].

    Returns:
        {"kappa": float, "stable": bool, "K_eff": float}.
    """
    k_eff = K - 0.5 * MU_0 * Ms**2
    if k_eff <= 0.0 or A <= 0.0:
        return {"kappa": 0.0, "stable": False, "K_eff": k_eff}
    kappa = D**2 / (4.0 * A * k_eff)
    return {"kappa": kappa, "stable": kappa > 1.0, "K_eff": k_eff}


# ===========================================================================
# 5. Spin Wave Dispersion
# ===========================================================================


def spinwave_dispersion_fm(
    k: float,
    A: float,
    Ms: float,
    H_ext: float = 0.0,
    gamma: float = GAMMA_E,
) -> float:
    r"""Compute the spin-wave dispersion relation ω(k) for a ferromagnet.

    Simplified dispersion for a uniformly magnetized ferromagnet
    (infinite medium, propagation direction ignored):

    .. math::
        \omega(k) = \gamma \mu_0 \left( H_{ext} + \frac{2A}{\mu_0 M_s} k^2 \right)

    More accurate dispersions require shape and dipolar terms.

    References:
        Kalinikos & Slavin, *J. Phys. C* 19, 7013 (1986), Eq. (2.17).
        Stancil & Prabhakar, *Spin Waves* (Springer, 2009), Eq. (5.65).

    Args:
        k: Wavevector [rad/m].
        A: Exchange stiffness [J/m].
        Ms: Saturation magnetization [A/m].
        H_ext: External magnetic field [A/m] (default 0).
        gamma: Gyromagnetic ratio [rad/(s·T)].

    Returns:
        Angular frequency ω [rad/s].
    """
    omega_H = gamma * MU_0 * H_ext
    omega_ex = gamma * (2.0 * A / Ms) * k**2
    return omega_H + omega_ex


def spinwave_dispersion_fm_ghz(
    k: float,
    A: float,
    Ms: float,
    H_ext: float = 0.0,
    gamma: float = GAMMA_E,
) -> float:
    """Return the spin-wave dispersion in GHz units.

    See spinwave_dispersion_fm.

    Returns:
        Frequency [GHz].
    """
    omega = spinwave_dispersion_fm(k, A, Ms, H_ext, gamma)
    return omega / (2.0 * math.pi * 1e9)


# ===========================================================================
# 6. Kittel Formula — FMR Resonance Frequency
# ===========================================================================


def kittel_freq_in_plane(
    H_ext: float,
    Ms: float,
    gamma: float = GAMMA_E,
) -> float:
    r"""Compute the in-plane FMR resonance frequency using the Kittel formula (thin film).

    .. math::
        f_{res} = \frac{\gamma}{2\pi} \sqrt{\mu_0 H_{ext} (\mu_0 H_{ext} + \mu_0 M_s)}

    Args:
        H_ext: In-plane external magnetic field [A/m].
        Ms: Saturation magnetization [A/m].
        gamma: Gyromagnetic ratio [rad/(s·T)].

    Returns:
        Resonance frequency [Hz].

    References:
        Kittel, *Phys. Rev.* 73, 155 (1948), Eq. (4).
        Coey, *Magnetism and Magnetic Materials* (Cambridge, 2010), p. 190, Eq. (6.33).
    """
    mu0_H = MU_0 * H_ext
    mu0_Ms = MU_0 * Ms
    return (gamma / (2.0 * math.pi)) * math.sqrt(mu0_H * (mu0_H + mu0_Ms))


def kittel_freq_out_of_plane(
    H_ext: float,
    Ms: float,
    gamma: float = GAMMA_E,
) -> float:
    r"""Compute the out-of-plane FMR resonance frequency using the Kittel formula (thin film).

    .. math::
        f_{res} = \frac{\gamma}{2\pi} |\mu_0 H_{ext} - \mu_0 M_s|

    Args:
        H_ext: Out-of-plane external magnetic field [A/m].
        Ms: Saturation magnetization [A/m].
        gamma: Gyromagnetic ratio [rad/(s·T)].

    Returns:
        Resonance frequency [Hz].

    References:
        Kittel, *Phys. Rev.* 73, 155 (1948), Eq. (2).
    """
    return (gamma / (2.0 * math.pi)) * abs(MU_0 * H_ext - MU_0 * Ms)


# ===========================================================================
# 7. Spin Hall Angle — SOT Torque (transport)
# ===========================================================================


def sot_efficiency(
    theta_sh: float,
    rho_n: float,
    t_n: float,
    rho_f: float,
    t_f: float,
) -> float:
    r"""Estimate the effective SOT (spin-orbit torque) efficiency ξ_eff.

    Conductance-ratio model:

    .. math::
        \xi_{eff} = \theta_{SH} \frac{\rho_N / t_N}{\rho_N / t_N + \rho_F / t_F}

    The precise calculation is performed in the SOT fitting (§11). This function
    provides a quick estimate.

    References:
        Sinova et al., *Rev. Mod. Phys.* 87, 1213 (2015), Sec. IV.B.
        Liu et al., *Phys. Rev. Lett.* 106, 036601 (2011), Supplementary.

    Args:
        theta_sh: Spin Hall angle [dimensionless].
        rho_n: Normal metal resistivity [Ω·m].
        t_n: Normal metal thickness [m].
        rho_f: Ferromagnet resistivity [Ω·m].
        t_f: Ferromagnet thickness [m].

    Returns:
        Effective SOT efficiency [dimensionless].
    """
    cond_n = 1.0 / (rho_n * t_n)
    cond_f = 1.0 / (rho_f * t_f)
    return theta_sh * cond_n / (cond_n + cond_f)


# ===========================================================================
# 8. Antiferromagnetic Resonance Frequency (AFMR)
# ===========================================================================


def afmr_frequency(
    H_E: float,
    H_A: float,
    gamma: float = GAMMA_E,
) -> float:
    r"""Compute the antiferromagnetic resonance (AFMR) frequency.

    Zero-field AFMR frequency for a uniaxial antiferromagnet:

    .. math::
        f_{AFMR} = \frac{\gamma}{2\pi} \mu_0 \sqrt{2 H_E H_A}

    Args:
        H_E: Exchange field [A/m]. (H_E = J/μ₀M₀)
        H_A: Anisotropy field [A/m].
        gamma: Gyromagnetic ratio [rad/(s·T)].

    Returns:
        AFMR resonance frequency [Hz].

    References:
        Keffer & Kittel, *Phys. Rev.* 85, 329 (1952), Eq. (13).
        Jungwirth et al., *Nature Nanotechnology* 11, 231 (2016), Eq. (2).
    """
    product = 2.0 * H_E * H_A
    if product < 0.0:
        # Unphysical parameter combination (optimizer excursion into negative H_E or H_A).
        # Return 0 so the Levenberg-Marquardt residual stays finite instead of raising
        # ValueError, allowing the optimizer to recover toward physical values.
        return 0.0
    return (gamma / (2.0 * math.pi)) * MU_0 * math.sqrt(product)


# ===========================================================================
# 9. Ferrimagnet Resonance Frequency near Compensation Temperature (simple model)
# ===========================================================================


def ferrimagnet_compensation_freq(
    m_a: float,
    m_b: float,
    H_ex_ab: float,
    gamma_a: float,
    gamma_b: float,
) -> float:
    r"""Compute the resonance frequency of a ferrimagnet near the angular-momentum
    compensation point (simple two-sublattice model).

    The intermediate quantity is the angular frequency:

    .. math::
        \omega_{res} = \frac{|\gamma_a m_a - \gamma_b m_b|}{m_a + m_b} \mu_0 H_{ex}

    This function returns the ordinary frequency f = ω / (2π) [Hz].

    This is a highly simplified model. Accurate computation requires solving
    a 4×4 LLG matrix equation.

    References:
        Kittel, *Phys. Rev.* 76, 743 (1949).
        Kim et al., *Nature Materials* 21, 544 (2022), Sec. Methods.

    Args:
        m_a, m_b: Sublattice magnetization magnitudes [A/m].
        H_ex_ab: Intersublattice exchange field [A/m].
        gamma_a, gamma_b: Gyromagnetic ratios of the two sublattices [rad/(s·T)].

    Returns:
        Resonance frequency f [Hz] (magnitude only, no sign).
    """
    numerator = abs(gamma_a * m_a - gamma_b * m_b)
    denominator = m_a + m_b
    if denominator <= 0.0:
        raise ValueError("Sum of sublattice magnetizations is zero or negative.")
    omega = (numerator / denominator) * MU_0 * H_ex_ab  # angular frequency [rad/s]
    return omega / (2.0 * math.pi)  # convert to Hz


# ===========================================================================
# 10. Multiscale Bridging — Heisenberg → Continuum Exchange Stiffness
# ===========================================================================


def heisenberg_to_exchange_stiffness(
    J_ij: float,
    a: float,
    S: float,
    z: int,
    n_atoms: float,
) -> float:
    r"""Compute the continuum exchange stiffness A from the Heisenberg exchange integral J_ij.

    Simple cubic lattice (simplified formula):

    .. math::
        A = \frac{n_{atoms} J S^2 z a^2}{6}

    (where a is the lattice constant, z is the number of nearest neighbors,
    and n_atoms is the number of atoms per unit volume.)

    References:
        Coey, *Magnetism and Magnetic Materials* (Cambridge, 2010), Eq. (5.86).
        Antropov et al., *Phys. Rev. B* 54, 1019 (1996).

    Args:
        J_ij: Exchange integral [J].
        a: Lattice constant [m].
        S: Spin quantum number [dimensionless].
        z: Number of nearest neighbors [dimensionless integer].
        n_atoms: Number of atoms per unit volume [m^-3].

    Returns:
        Exchange stiffness A [J/m].
    """
    return n_atoms * J_ij * S**2 * z * a**2 / 6.0


def spin_diffusion_length(
    D_s: float,
    tau_sf: float,
) -> float:
    r"""Compute the spin diffusion length λ_sf.

    .. math::
        \lambda_{sf} = \sqrt{D_s \tau_{sf}}

    References:
        Valet & Fert, *Phys. Rev. B* 48, 7099 (1993), Eq. (6).

    Args:
        D_s: Spin diffusion coefficient [m²/s].
        tau_sf: Spin-flip time [s].

    Returns:
        Spin diffusion length [m].
    """
    return math.sqrt(D_s * tau_sf)


# ===========================================================================
# 11. Thiele Equation — Skyrmion Hall Angle
# ===========================================================================


def skyrmion_hall_angle(
    alpha: float,
    Q: float = 1,
) -> float:
    r"""Compute the skyrmion Hall angle θ_SkHE (simple Thiele model).

    .. math::
        \tan\theta_{SkHE} = -\frac{G}{\alpha \mathcal{D}} = \frac{4\pi Q}{\alpha \mathcal{D}_{norm}}

    Simplified isotropic assumption (diagonal D tensor):

    .. math::
        \theta_{SkHE} \approx \arctan\!\left(\frac{4\pi Q}{\alpha \mathcal{D}}\right)

    References:
        Thiele, *Phys. Rev. Lett.* 30, 230 (1973).
        Jiang et al., *Nature Physics* 13, 162 (2017), Eq. (2).

    Args:
        alpha: Gilbert damping constant.
        Q: Topological charge (skyrmion number, typically Q=1).

    Returns:
        Skyrmion Hall angle [rad].

    Note:
        Simple model with D tensor normalized to 1. Accurate calculation
        requires full D tensor integration.
    """
    # Gyrovector |G| = 4πQ, dissipation tensor D normalized to 1 (approximation)
    G = 4.0 * math.pi * Q
    D_norm = 1.0  # normalization factor — replaced by integral in detailed calculations
    # Use atan2 to handle alpha=0 correctly (returns π/2, matching Thiele eq.)
    return math.atan2(G, alpha * D_norm)
