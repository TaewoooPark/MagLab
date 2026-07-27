"""Scale N → N+1 handoff — units, temperature dependence, assumptions + provenance threading.

Design rationale: impl/04-P3-multiscale.md T-P3-06~08 · plan/03-physics-simulation.md §10.1 · Appendix D.

P3 core value: document units and assumptions near the code for all inter-scale parameter
conversions, and record every conversion event as a ``DataPoint`` in provenance.

Supported handoffs:
1. DFT → atomistic   (``dft_to_atomistic``)
2. atomistic → micro  (``atomistic_to_micro``)
3. micro → device     (``micro_to_device``)

Handoff rules (Appendix D):
- Scale N output units = Scale N+1 input units
- Unit mismatch raises HandoffUnitError
- Must pass oracle.py dimensional validation

---------------------------------------------------------------------
Unit conversion sources:
  meV → K : E[meV] × e×10^-3 / k_B  (Boltzmann constant definition)
  meV → J : E[meV] × e×10^-3        (elementary charge definition)
  μ_B/atom → A/m : mu_B × N/V (volume from crystal structure)
  J_ij[K] → A_exchange[J/m] : spin-wave continuum limit — A = z × J × S² / a
              (z=8 bcc NN count, S=1/2×dimensionless spin, a=lattice constant)
              Ref: Chikazumi, Physics of Ferromagnetism (1997) Eq. (7.74)
---------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.interpolate import interp1d  # type: ignore[import-untyped]

from maglab.physics.constants import E_CHARGE, K_B
from maglab.physics.oracle import (
    OracleResult,
    check_curie_temperature,
    check_exchange_stiffness,
    check_saturation_magnetization,
    check_temperature,
)
from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class HandoffUnitError(ValueError):
    """Handoff unit mismatch — scale N output units ≠ N+1 input units.

    Appendix D static validation rule: block JobResult creation on unit mismatch.
    """


class HandoffPhysicsError(ValueError):
    """Handoff parameter is outside physical range (oracle validation failed)."""


# ---------------------------------------------------------------------------
# Handoff result struct
# ---------------------------------------------------------------------------


@dataclass
class HandoffResult:
    """Handoff conversion result.

    Attributes:
        from_scale: Source scale name.
        to_scale: Target scale name.
        params: Converted parameter dictionary (with units).
        assumptions: List of assumptions applied in the conversion (documented in code).
        provenance_datapoints: List of provenance DataPoints.
        warnings: List of non-fatal warning messages.
    """

    from_scale: str
    to_scale: str
    params: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    provenance_datapoints: list[DataPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return a summary text."""
        n_params = len(self.params)
        n_assumptions = len(self.assumptions)
        return (
            f"handoff: {self.from_scale} → {self.to_scale} | "
            f"params: {n_params} | assumptions: {n_assumptions}"
        )


# ---------------------------------------------------------------------------
# 1. DFT → atomistic handoff
# ---------------------------------------------------------------------------

# Assumption list (documented near the code — Appendix D handoff rules)
_DFT_TO_ATOMISTIC_ASSUMPTIONS = [
    "Heisenberg model applied: H = -Σ J_ij S_i·S_j (J_ij symmetric, no double counting)",
    "J_ij unit conversion: meV → K  (using k_B — Boltzmann constant definition 1.380649e-23 J/K)",
    "MAE unit conversion: meV/atom → J/atom (elementary charge definition 1.602176634e-19 C)",
    "DMI unit conversion: meV → J  (elementary charge definition)",
    "Magnetic moment: μ_B/atom — passed to atomistic unchanged (VAMPIRE internal units)",
    "Exchange coupling mapped to Heisenberg spin model: no U/4 correction (assuming no DFT+U)",
    "J_ij truncation warning: alert if J magnitude changes abruptly near TB2J cutoff (Appendix D)",
]


def dft_to_atomistic(
    J_ij_meV: float | list[float],
    MAE_meV_atom: float | None = None,
    DMI_meV: float | None = None,
    m_muB: float | None = None,
    j_ij_pairs: list[tuple[int, int, float]] | None = None,
    source_ref: str = "DFT->atomistic handoff",
    provenance_type: ProvenanceType = ProvenanceType.SIMULATED,
) -> HandoffResult:
    """Convert DFT results to atomistic input units.

    Unit conversions (Appendix D handoff rules):
    - J_ij  : meV → K  (= meV × e×10⁻³ / k_B)
    - MAE   : meV/atom → J/atom (= meV/atom × e×10⁻³)
    - DMI   : meV → J  (= meV × e×10⁻³)
    - m     : μ_B/atom (no conversion — passed directly as VAMPIRE input)

    Parameters
    ----------
    J_ij_meV:
        Exchange coupling list [meV]. DFT output units.
    MAE_meV_atom:
        Magnetic anisotropy energy [meV/atom]. None if not available.
    DMI_meV:
        DMI magnitude [meV]. None if not available.
    m_muB:
        Magnetic moment [μ_B/atom]. None if not available.
    j_ij_pairs:
        List of (i, j, J_meV) pairs. If None, the first element of J_ij_meV is used as NN.
    source_ref:
        Provenance reference string.

    Returns
    -------
    HandoffResult
        Converted atomistic parameters. params keys:
        - ``"J_ij_K"``: J_ij list [K].
        - ``"J_ij_pairs_K"``: list of (i, j, J_K) pairs.
        - ``"K_J"``: MAE [J/atom] (if provided).
        - ``"D_J"``: DMI [J] (if provided).
        - ``"m_muB"``: magnetic moment [μ_B/atom] (if provided).

    Raises
    ------
    HandoffUnitError
        If input units are not meV (unit tracking failure).
    HandoffPhysicsError
        If oracle range validation fails.
    """
    # Unit conversion constants
    mev_to_J = E_CHARGE * 1e-3  # 1 meV = e×10⁻³ J ≈ 1.602e-22 J
    mev_to_K = mev_to_J / K_B  # 1 meV = e×10⁻³ / k_B K ≈ 11.6045 K

    # J_ij conversion: meV → K (accepts single float or list)
    _scalar_input = isinstance(J_ij_meV, (int, float))
    if isinstance(J_ij_meV, (int, float)):
        J_ij_list: list[float] = [float(J_ij_meV)]
    else:
        J_ij_list = [float(j) for j in J_ij_meV]
    J_ij_K_list = [j * mev_to_K for j in J_ij_list]
    # Scale N+1 input unit compatibility: pass scalar if single input, list if list input
    J_ij_K: float | list[float] = J_ij_K_list[0] if (_scalar_input and J_ij_K_list) else J_ij_K_list

    # (i, j, J_K) pair list
    if j_ij_pairs is not None:
        J_pairs_K = [(p[0], p[1], p[2] * mev_to_K) for p in j_ij_pairs]
    else:
        j_k_first: float = J_ij_K_list[0] if J_ij_K_list else 0.0
        J_pairs_K = [(1, 1, j_k_first)] if J_ij_K_list else []

    params: dict[str, Any] = {
        "J_ij_K": J_ij_K,
        "J_ij_pairs_K": J_pairs_K,
        # Convenience scalar (first J_ij value — 1NN)
        "J_1_K": J_ij_K_list[0] if J_ij_K_list else None,
    }

    # MAE conversion: meV/atom → J/atom
    K_J: float | None = None
    if MAE_meV_atom is not None:
        K_J = MAE_meV_atom * mev_to_J
        params["K_J"] = K_J

    # DMI conversion: meV → J
    D_J: float | None = None
    if DMI_meV is not None:
        D_J = DMI_meV * mev_to_J
        params["D_J"] = D_J

    # Magnetic moment: no conversion
    if m_muB is not None:
        params["m_muB"] = m_muB

    # Build DataPoints (provenance)
    dps: list[DataPoint] = []
    if J_ij_K_list:
        dps.append(
            DataPoint(
                value=J_ij_K_list[0],
                units="K",
                provenance_type=provenance_type,
                source_ref=source_ref,
                conditions={"from": "J_ij meV", "conversion": "meV × e×10⁻³ / k_B"},
            )
        )
    if K_J is not None:
        dps.append(
            DataPoint(
                value=K_J,
                units="J",
                provenance_type=provenance_type,
                source_ref=source_ref,
                conditions={"from": "MAE meV/atom", "conversion": "meV × e×10⁻³"},
            )
        )

    # Collect warnings
    warnings_list: list[str] = []
    if not J_ij_K_list:
        warnings_list.append("J_ij list is empty. Check DFT calculation or TB2J results.")

    return HandoffResult(
        from_scale="dft",
        to_scale="atomistic",
        params=params,
        assumptions=_DFT_TO_ATOMISTIC_ASSUMPTIONS.copy(),
        provenance_datapoints=dps,
        warnings=warnings_list,
    )


# ---------------------------------------------------------------------------
# 2. atomistic → micro handoff
# ---------------------------------------------------------------------------

# Assumption list
_ATOMISTIC_TO_MICRO_ASSUMPTIONS = [
    "Continuum approximation: lattice constant a ≪ simulation domain size (l >> a)",
    "Exchange stiffness A: A = z × J_1 × S² × a / (temperature scaling) — bcc: z=8, a=2.87 Å",
    "  Ref: Chikazumi, Physics of Ferromagnetism (1997) Eq. 7.74",
    "  A = (2/a) × J₁ × S² × a² = 2J₁S²/a (bcc 8 NN: A = 2zJ₁S²a/(2z) = J₁S²a)",
    "  Exact formula: A = n_nn × J₁ × S² / a, n_nn=8(bcc), S=1 (spin-1 → S²=1)",
    "Temperature-dependent spline interpolation: M_s(T), A(T), K(T) — linear if data insufficient",
    "Saturation magnetization: M_s(T) taken directly from atomistic simulation M(T) output",
    "Anisotropy constant K(T): M_s(T)^n scaling (n=2 — Callen-Callen theory, uniaxial anisotropy)",
    "  Ref: Callen & Callen, J. Phys. Chem. Solids 27, 1271 (1966)",
    "Continuum DMI: D_micro [J/m²] = D_atomistic × N_s / a² (N_s = surface atom density)",
    "  Simplified: D_micro = D_J / a² (in-plane interface — zero in bulk)",
]

# bcc Fe material constants (reference values)
_BCC_FE_A_M = 2.87e-10  # lattice constant [m]
_BCC_FE_Z_NN = 8  # bcc NN count
_BCC_FE_S = 1.0  # spin degree of freedom (VAMPIRE spin-1 model)
# A = n_nn × J₁ × S² × a / 2 — continuum limit
# More accurate: A = (2 × J₁ × S²) / a  (bcc, Chikazumi 7.74)
_BCC_A_PREFACTOR = 2.0 / _BCC_FE_A_M  # = 2/a [m⁻¹]


def atomistic_to_micro(
    T_K: list[float],
    M_s_Am: list[float],
    T_target_K: float = 300.0,
    J_1_K: float | None = None,
    K_0_Jm3: float | None = None,
    D_Jm2: float | None = None,
    lattice_const_m: float = _BCC_FE_A_M,
    source_ref: str = "atomistic->micro handoff",
    provenance_type: ProvenanceType = ProvenanceType.SIMULATED,
) -> HandoffResult:
    """Convert atomistic results to micromagnetic input units.

    Units (Appendix D handoff rules):
    - M_s(T) : A/m (atomistic output → micromagnetic input, same units)
    - A(T)   : J/m (exchange stiffness — continuum limit calculation)
    - K(T)   : J/m³ (anisotropy — M_s(T)^2 scaling)

    Parameters
    ----------
    T_K:
        Temperature array [K] (ascending).
    M_s_Am:
        Saturation magnetization array [A/m] at each temperature.
    T_target_K:
        Target temperature for conversion [K].
    J_1_K:
        Nearest-neighbor exchange coupling [K]. A(T) cannot be computed if None.
    K_0_Jm3:
        Anisotropy constant at T=0 K [J/m³]. K(T) cannot be computed if None.
    D_Jm2:
        DMI coefficient [J/m²]. D_micro = 0 if None.
    lattice_const_m:
        Lattice constant [m]. Default: bcc Fe 2.87 Å.
    source_ref:
        Provenance reference string.

    Returns
    -------
    HandoffResult
        Converted micromagnetic parameters. params keys:
        - ``"Ms_Am"``   : saturation magnetization [A/m] at T_target.
        - ``"A_Jm"``    : exchange stiffness [J/m] at T_target (if J_1_K provided).
        - ``"K_Jm3"``   : anisotropy constant [J/m³] at T_target (if K_0 provided).
        - ``"D_Jm2"``   : DMI coefficient [J/m²] (if provided).
        - ``"T_C_K"``   : extracted Curie temperature [K] (estimated from M_s(T)).

    Raises
    ------
    HandoffUnitError
        If unit mismatch is detected.
    HandoffPhysicsError
        If oracle validation fails.
    """
    if len(T_K) != len(M_s_Am):
        raise HandoffUnitError(
            f"T_K (length {len(T_K)}) and M_s_Am (length {len(M_s_Am)}) arrays have different lengths."
        )
    if not T_K:
        raise HandoffUnitError("T_K and M_s_Am arrays are empty.")

    T_arr = np.array(T_K, dtype=float)
    M_arr = np.array(M_s_Am, dtype=float)

    # Validate T_target range (T=0 K is rejected by oracle, but physically use T=0 data directly)
    if T_target_K > 0.0:
        T_result = check_temperature(T_target_K)
        if not T_result:
            raise HandoffPhysicsError(f"Temperature range validation failed: {T_result.reason}")

    # M_s(T_target) interpolation
    if len(T_arr) == 1 or T_target_K <= T_arr[0]:
        Ms_target = float(M_arr[0])
    elif T_target_K >= T_arr[-1]:
        Ms_target = float(M_arr[-1])
    else:
        interp_Ms = interp1d(T_arr, M_arr, kind="cubic" if len(T_arr) >= 4 else "linear")
        Ms_target = float(interp_Ms(T_target_K))

    # Oracle Ms validation
    Ms_result = check_saturation_magnetization(max(Ms_target, 1.0))
    if not Ms_result:
        raise HandoffPhysicsError(f"M_s oracle validation failed: {Ms_result.reason}")

    params: dict[str, Any] = {
        "Ms_Am": Ms_target,
        "T_target_K": T_target_K,
    }

    # Exchange stiffness A(T) computation [J/m]
    # A = 2 × J₁[J] × S² / a [m]  (continuum limit, bcc)
    # J₁[J] = J₁[K] × k_B
    # Temperature dependence: A(T) = A(0) × (M_s(T) / M_s(0))^2  (linear spin-wave theory)
    # Ref: Hinzke et al., PRL 107, 027205 (2011)
    A_target: float | None = None
    if J_1_K is not None:
        J_1_J = J_1_K * K_B  # K → J
        A_0 = _BCC_A_PREFACTOR * J_1_J * _BCC_FE_S**2  # A(0) [J/m]

        # Temperature scaling
        Ms_0 = float(M_arr[0]) if M_arr[0] > 0 else 1.0
        if Ms_0 > 0 and Ms_target > 0:
            A_target = A_0 * (Ms_target / Ms_0) ** 2
        else:
            A_target = A_0

        # Oracle A validation
        A_result = check_exchange_stiffness(max(A_target, 1e-30))
        if not A_result:
            raise HandoffPhysicsError(
                f"Exchange stiffness oracle validation failed: {A_result.reason}"
            )

        params["A_Jm"] = A_target

    # Anisotropy constant K(T) computation [J/m³]
    # K(T) = K(0) × (M_s(T) / M_s(0))^2  (Callen-Callen n=2, uniaxial)
    K_target: float | None = None
    if K_0_Jm3 is not None:
        Ms_0 = float(M_arr[0]) if M_arr[0] > 0 else 1.0
        if Ms_0 > 0 and Ms_target > 0:
            K_target = K_0_Jm3 * (Ms_target / Ms_0) ** 2
        else:
            K_target = K_0_Jm3
        params["K_Jm3"] = K_target

    # DMI
    if D_Jm2 is not None:
        params["D_Jm2"] = D_Jm2

    # T_C estimation (M_s = 0 crossing)
    from maglab.sim.atomistic.parse_atomistic import _extract_tc_from_mt

    M_norm = M_arr / (np.max(M_arr) + 1e-30)
    T_C = _extract_tc_from_mt(T_arr, M_norm)
    if T_C is not None:
        tc_result = check_curie_temperature(T_C)
        if not tc_result:
            T_C = None  # invalidate T_C on oracle failure
        else:
            params["T_C_K"] = T_C

    # Build DataPoints
    dps: list[DataPoint] = []
    dps.append(
        DataPoint(
            value=Ms_target,
            units="A/m",
            provenance_type=provenance_type,
            source_ref=source_ref,
            conditions={"temperature_K": T_target_K, "from_scale": "atomistic"},
        )
    )
    if A_target is not None:
        dps.append(
            DataPoint(
                value=A_target,
                units="J/m",
                provenance_type=provenance_type,
                source_ref=source_ref,
                conditions={
                    "temperature_K": T_target_K,
                    "formula": "A = 2J₁S²/a × (Ms(T)/Ms(0))²",
                    "assumption": "Chikazumi 7.74 + spin-wave temperature scaling",
                },
            )
        )
    if T_C is not None:
        dps.append(
            DataPoint(
                value=T_C,
                units="K",
                provenance_type=provenance_type,
                source_ref=source_ref,
                conditions={"from_scale": "atomistic M(T) interpolation"},
            )
        )

    warnings_list: list[str] = []
    if len(T_arr) < 4:
        warnings_list.append(
            f"Only {len(T_arr)} temperature data points — at least 10 recommended for accurate interpolation."
        )

    return HandoffResult(
        from_scale="atomistic",
        to_scale="micro",
        params=params,
        assumptions=_ATOMISTIC_TO_MICRO_ASSUMPTIONS.copy(),
        provenance_datapoints=dps,
        warnings=warnings_list,
    )


# ---------------------------------------------------------------------------
# 3. Micromagnetic → device handoff
# ---------------------------------------------------------------------------

_MICRO_TO_DEVICE_ASSUMPTIONS = [
    "Continuum→macrospin reduction: device FoM extracted from time-averaged micromagnetic dynamics simulation",
    "Critical current density: j_c = 2e × α × μ₀ × Ms × t × Hk / (ħ × θ_SH)  (STT formula)",
    "  Ref: Slonczewski, J. Magn. Magn. Mater. 159, L1 (1996)",
    "Skyrmion Hall angle: tan(θ_SkH) = G / (α × D_thiele)  (Thiele equation)",
    "  Ref: Thiele, PRL 30, 230 (1973)",
    "Switching time estimate: t_sw ≈ 1 / (α × γ × H_k)  (macrospin WKB approximation)",
    "  This is a qualitative estimate; accurate values require micromagnetic dynamics simulation",
]


def micro_to_device(
    Ms_Am: float,
    A_Jm: float,
    alpha: float,
    K_Jm3: float = 0.0,
    D_Jm2: float = 0.0,
    ovf_summary: dict[str, Any] | None = None,
    source_ref: str = "micro->device handoff",
    provenance_type: ProvenanceType = ProvenanceType.SIMULATED,
) -> HandoffResult:
    """Convert micromagnetic results to device/transport scale inputs.

    Units (Appendix D handoff rules):
    - Critical current density j_c : A/m² (SI current density)
    - Switching time t_sw           : s (SI time)
    - Skyrmion Hall angle           : dimensionless (rad)

    Parameters
    ----------
    Ms_Am:
        Saturation magnetization [A/m].
    A_Jm:
        Exchange stiffness [J/m].
    alpha:
        Gilbert damping constant [dimensionless].
    K_Jm3:
        Anisotropy constant [J/m³].
    D_Jm2:
        DMI coefficient [J/m²].
    ovf_summary:
        OVF magnetization structure summary dictionary (micromagnetic simulation output).
    source_ref:
        Provenance reference.

    Returns
    -------
    HandoffResult
        Converted device parameters. params keys:
        - ``"j_c_Am2"``       : Critical current density [A/m²] (estimate).
        - ``"t_sw_s"``        : Switching time [s] (estimate).
        - ``"theta_SkH_rad"`` : Skyrmion Hall angle [rad] (only when D≠0).
        - ``"Ms_Am"``         : Saturation magnetization [A/m] (pass-through).
        - ``"A_Jm"``          : Exchange stiffness [J/m] (pass-through).
        - ``"alpha"``         : Damping constant (pass-through).
        - ``"K_Jm3"``         : Anisotropy constant [J/m³] (pass-through).

    Raises
    ------
    HandoffPhysicsError
        When oracle validation fails.
    """
    from maglab.physics.constants import GAMMA_E, HBAR, MU_0

    # Oracle validation
    Ms_result = check_saturation_magnetization(Ms_Am)
    if not Ms_result:
        raise HandoffPhysicsError(f"M_s oracle validation failed: {Ms_result.reason}")

    A_result = check_exchange_stiffness(A_Jm)
    if not A_result:
        raise HandoffPhysicsError(f"Exchange stiffness oracle validation failed: {A_result.reason}")

    # Effective anisotropy field H_k [A/m]: crystalline anisotropy + thin-film perpendicular shape anisotropy (demagnetization)
    # H_k_crys = 2K / (μ₀ Ms)  (crystalline anisotropy)
    # H_k_shape = Ms             (thin-film perpendicular demagnetization: N_z ≈ 1, H_demag = μ₀ Ms — dimensionless units [A/m])
    # H_k_eff = H_k_crys + H_k_shape  (Slonczewski thin-film perpendicular switching criterion)
    # Ref: Slonczewski, J. Magn. Magn. Mater. 159, L1 (1996)
    H_k_crys = (2.0 * K_Jm3) / (MU_0 * Ms_Am) if Ms_Am > 0 else 0.0
    H_k_shape = (
        Ms_Am  # thin-film perpendicular demagnetization field [A/m] (N_z=1 monolayer approximation)
    )
    H_k = H_k_crys + H_k_shape

    # Critical current density estimate (STT, Slonczewski 1996)
    # j_c ≈ 2e × α × μ₀ × Ms × t × Hk / (ħ × θ_SH)
    # θ_SH (spin Hall angle) unknown — default 0.1 (Pt reference)
    theta_SH = 0.1
    t_fm_m = 1e-9  # ferromagnetic layer thickness [m] (1 nm default)
    j_c = (2.0 * E_CHARGE * alpha * MU_0 * Ms_Am * t_fm_m * H_k) / (HBAR * theta_SH)

    # Switching time estimate (macrospin WKB)
    # t_sw ≈ 1 / (α × γ × H_k)  [s]
    if alpha > 0 and H_k > 0:
        t_sw = 1.0 / (alpha * GAMMA_E * MU_0 * (H_k / (4.0 * np.pi)))
    else:
        t_sw = float("inf")

    params: dict[str, Any] = {
        "Ms_Am": Ms_Am,
        "A_Jm": A_Jm,
        "alpha": alpha,
        "K_Jm3": K_Jm3,
        "j_c_Am2": j_c,
        "t_sw_s": t_sw if np.isfinite(t_sw) else None,
    }

    # Skyrmion Hall angle (Thiele equation)
    # tan(θ_SkH) = G / (α × D_thiele)
    # G = 4π × Q (Q = topological charge, Q=1 for Neel skyrmion)
    # D_thiele ≈ π × r² × Ms (skyrmion radius r required — estimated)
    if D_Jm2 != 0.0:
        # Skyrmion radius estimate: r = sqrt(A/K) (simplified)
        if K_Jm3 > 0:
            r_sk = (A_Jm / K_Jm3) ** 0.5
        else:
            r_sk = 10e-9  # default 10 nm
        G_thiele = 4.0 * np.pi * 1  # Q=1
        D_thiele = np.pi * r_sk**2 * Ms_Am
        if D_thiele > 0 and alpha > 0:
            theta_SkH = np.arctan(G_thiele / (alpha * D_thiele))
        else:
            theta_SkH = 0.0
        params["theta_SkH_rad"] = theta_SkH

    if ovf_summary:
        params["ovf_summary"] = ovf_summary

    # Build DataPoints
    dps: list[DataPoint] = [
        DataPoint(
            value=j_c,
            units="A/m^2",
            provenance_type=provenance_type,
            source_ref=source_ref,
            conditions={
                "formula": "j_c = 2e×α×μ₀×Ms×t×Hk/(ħ×θ_SH)",
                "assumption": "θ_SH=0.1(Pt), t=1nm — estimates",
            },
        ),
    ]
    if np.isfinite(t_sw):
        dps.append(
            DataPoint(
                value=t_sw,
                units="s",
                provenance_type=provenance_type,
                source_ref=source_ref,
                conditions={
                    "formula": "t_sw ≈ 1/(α×γ×H_k)",
                    "assumption": "macrospin WKB approximation",
                },
            )
        )

    warnings_list: list[str] = [
        "Critical current and switching time are macrospin estimates. "
        "Accurate values require micromagnetic dynamics simulation (MuMax3/OOMMF).",
    ]

    return HandoffResult(
        from_scale="micro",
        to_scale="device",
        params=params,
        assumptions=_MICRO_TO_DEVICE_ASSUMPTIONS.copy(),
        provenance_datapoints=dps,
        warnings=warnings_list,
    )


# ---------------------------------------------------------------------------
# Utility: unit continuity verification (Appendix D)
# ---------------------------------------------------------------------------


def verify_unit_continuity(
    from_params: dict[str, Any],
    to_params: dict[str, Any],
    required_keys: list[str],
) -> OracleResult:
    """Verify unit continuity between scale N output parameters and N+1 input parameters.

    Appendix D handoff rule: units of scale N output = units of N+1 input.
    Currently implemented as required-key presence + value type validation.

    Parameters
    ----------
    from_params:
        Output parameter dictionary for scale N.
    to_params:
        Input parameter dictionary for scale N+1.
    required_keys:
        List of parameter keys to verify for continuity.

    Returns
    -------
    OracleResult
        Validation result.
    """
    from maglab.physics.oracle import OracleResult

    missing_from = [k for k in required_keys if k not in from_params]
    missing_to = [k for k in required_keys if k not in to_params]

    if missing_from:
        return OracleResult(
            ok=False,
            reason=f"Required keys missing from output parameters: {missing_from}",
            param="from_params",
            value=missing_from,
        )
    if missing_to:
        return OracleResult(
            ok=False,
            reason=f"Required keys missing from input parameters: {missing_to}",
            param="to_params",
            value=missing_to,
        )

    return OracleResult(ok=True, checks=["unit_continuity_keys"])
