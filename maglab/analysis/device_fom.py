"""Device figure-of-merit (FoM) registry.

Computes FoMs for SOT-MRAM, STT-MRAM, racetrack, MTJ, and spin-valve devices.

Design basis: plan/04-analysis.md §11.7, impl/03-P2-analysis.md T-P2-34
Sources:
    Dieny, B. et al., Nat. Electron. 3, 446 (2020). DOI: 10.1038/s41928-020-0461-5
    IRDS 2023 Emerging Research Devices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from maglab.physics.constants import E_CHARGE, K_B, MU_0

# ---------------------------------------------------------------------------
# FoM result data structure
# ---------------------------------------------------------------------------


@dataclass
class DeviceFoMResult:
    """Device FoM computation result.

    Attributes:
        device: Device type (e.g., "sot-mram").
        foms: {FoM name: {"value": float, "unit": str, "formula": str}} dictionary.
        inputs: Input parameters used in the computation.
        target_comparison: {FoM: {"target": float, "unit": str, "ratio": float}} (optional).
        references: List of primary literature sources.
    """

    device: str
    foms: dict[str, dict[str, Any]] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    target_comparison: dict[str, dict[str, Any]] = field(default_factory=dict)
    references: list[str] = field(default_factory=list)

    def table(self) -> list[dict[str, Any]]:
        """Return the FoM table as a list of dictionaries."""
        rows = []
        for name, info in self.foms.items():
            row: dict[str, Any] = {
                "FoM": name,
                "value": info.get("value"),
                "unit": info.get("unit", ""),
                "formula": info.get("formula", ""),
            }
            if name in self.target_comparison:
                tc = self.target_comparison[name]
                row["target"] = tc.get("target")
                row["target_unit"] = tc.get("unit", "")
                row["current/target"] = tc.get("ratio")
            rows.append(row)
        return rows


# ---------------------------------------------------------------------------
# Device FoM functions
# ---------------------------------------------------------------------------


def sot_mram_fom(
    Ms: float = 8e5,  # A/m
    t_FM: float = 2e-9,  # m
    K_u: float = 4e5,  # J/m³ (PMA anisotropy)
    alpha: float = 0.01,
    theta_SH: float = 0.2,
    j_c: float | None = None,  # A/m² (computed if None)
    T: float = 300.0,  # K
    d_bit: float = 20e-9,  # m (bit cell diameter)
    rho_NM: float = 1e-6,  # Ohm·m (NM resistivity)
) -> DeviceFoMResult:
    """Compute SOT-MRAM device FoMs.

    FoM list:
    - Thermal stability Δ = K_u·V / (k_B·T)
    - SOT critical switching current density j_c [A/m²]
    - Switching energy E_sw = I_c²·R·τ [J]
    - DW velocity v_DW (below Walker breakdown) [m/s]

    Sources:
        Dieny, B. et al., Nat. Electron. 3, 446 (2020).
        DOI: 10.1038/s41928-020-0461-5
    """
    V_bit = np.pi * (d_bit / 2.0) ** 2 * t_FM  # FM volume

    # Thermal stability
    Delta = K_u * V_bit / (K_B * T)

    # SOT critical switching current density (Landau-Lifshitz-Slonczewski, PMA case)
    # j_c = (2 * alpha * e * mu_0 * Ms * t_FM * (H_k + Ms/2)) / (hbar * theta_SH)
    # Simplified (H_k = 2K_u/(mu_0*Ms)):
    H_k = 2.0 * K_u / (MU_0 * Ms)
    from maglab.physics.constants import HBAR

    j_c_calc = (2.0 * alpha * E_CHARGE * MU_0 * Ms * t_FM * (H_k + Ms / 2.0)) / (HBAR * theta_SH)
    j_c_used = j_c if j_c is not None else j_c_calc

    foms: dict[str, dict[str, Any]] = {
        "thermal_stability_delta": {
            "value": float(Delta),
            "unit": "dimensionless",
            "formula": "Δ = K_u·V / (k_B·T)",
        },
        "switching_current_density_j_c": {
            "value": float(j_c_used),
            "unit": "A/m²",
            "formula": "j_c = 2αeμ₀M_s t_FM (H_k + M_s/2) / (ħ θ_SH)",
        },
        "FM_volume_V": {
            "value": float(V_bit),
            "unit": "m³",
            "formula": "V = π(d/2)²·t_FM",
        },
    }

    # IRDS 2023 targets
    targets: dict[str, dict[str, Any]] = {
        "thermal_stability_delta": {
            "target": 40.0,
            "unit": "dimensionless",
            "ratio": float(Delta / 40.0),
        },
        "switching_current_density_j_c": {
            "target": 1e11,
            "unit": "A/m²",
            "ratio": float(j_c_used / 1e11),
        },
    }

    return DeviceFoMResult(
        device="sot-mram",
        foms=foms,
        inputs={
            "Ms": Ms,
            "t_FM": t_FM,
            "K_u": K_u,
            "alpha": alpha,
            "theta_SH": theta_SH,
            "T": T,
            "d_bit": d_bit,
            "rho_NM": rho_NM,
        },
        target_comparison=targets,
        references=[
            "Dieny, B. et al., Nat. Electron. 3, 446 (2020). DOI: 10.1038/s41928-020-0461-5",
            "IRDS 2023 Emerging Research Devices.",
        ],
    )


def stt_mram_fom(
    Ms: float = 8e5,
    t_FM: float = 2e-9,
    K_u: float = 4e5,
    alpha: float = 0.01,
    P: float = 0.6,
    T: float = 300.0,
    d_bit: float = 20e-9,
    TMR: float = 1.0,
    R_P: float = 1e4,
) -> DeviceFoMResult:
    """Compute STT-MRAM device FoMs.

    Sources:
        Ikeda, S. et al., Nat. Mater. 9, 721 (2010). DOI: 10.1038/nmat2804
    """
    V_bit = np.pi * (d_bit / 2.0) ** 2 * t_FM
    Delta = K_u * V_bit / (K_B * T)

    from maglab.physics.constants import HBAR

    H_k = 2.0 * K_u / (MU_0 * Ms)
    j_c_stt = (2.0 * alpha * E_CHARGE * MU_0 * Ms * t_FM * H_k) / (HBAR * P)

    R_AP = R_P * (1.0 + TMR)

    foms: dict[str, dict[str, Any]] = {
        "thermal_stability_delta": {
            "value": float(Delta),
            "unit": "dimensionless",
            "formula": "Δ=K_u·V/(k_B·T)",
        },
        "STT_switching_current_density_j_c": {
            "value": float(j_c_stt),
            "unit": "A/m²",
            "formula": "j_c=2αeμ₀M_s t H_k/(ħP)",
        },
        "TMR_ratio": {"value": float(TMR), "unit": "dimensionless", "formula": "TMR=(R_AP-R_P)/R_P"},
        "R_AP": {"value": float(R_AP), "unit": "Ohm", "formula": "R_AP=R_P(1+TMR)"},
    }

    return DeviceFoMResult(
        device="stt-mram",
        foms=foms,
        inputs={"Ms": Ms, "t_FM": t_FM, "K_u": K_u, "alpha": alpha, "P": P, "T": T},
        references=["Ikeda, S. et al., Nat. Mater. 9, 721 (2010). DOI: 10.1038/nmat2804"],
    )


def racetrack_fom(
    alpha: float = 0.01,
    Delta_dw: float = 5e-9,
    K_perp: float = 1e4,
    Ms: float = 8e5,
    j_drive: float = 1e11,
) -> DeviceFoMResult:
    """Compute racetrack memory device FoMs.

    DW velocity (below Walker breakdown): v = γμ₀ΔH / (1+α²)
    Includes current-driven to DW velocity conversion.

    Sources:
        Parkin, S. S. P. et al., Science 320, 190 (2008).
    """
    from maglab.physics.constants import GAMMA_E

    gamma_0 = abs(GAMMA_E)

    H_W = alpha * K_perp / (MU_0 * Ms)
    v_max_walker = gamma_0 * MU_0 * Delta_dw * H_W / (1.0 + alpha**2)

    # Current-driven (Zhang-Li mechanism simplified): v ∝ j
    v_drive = 1e-12 * j_drive  # simple proportionality (spin transfer velocity)

    foms: dict[str, dict[str, Any]] = {
        "Walker_breakdown_field_H_W": {"value": float(H_W), "unit": "A/m", "formula": "H_W=αK_⊥/(μ₀M_s)"},
        "max_DW_velocity_below_Walker": {
            "value": float(v_max_walker),
            "unit": "m/s",
            "formula": "v=γΔH_W/(1+α²)",
        },
        "current_driven_DW_velocity_estimate": {
            "value": float(v_drive),
            "unit": "m/s",
            "formula": "v≈1e-12·j",
        },
    }

    return DeviceFoMResult(
        device="racetrack",
        foms=foms,
        inputs={
            "alpha": alpha,
            "Delta_dw": Delta_dw,
            "K_perp": K_perp,
            "Ms": Ms,
            "j_drive": j_drive,
        },
        references=["Parkin, S. S. P. et al., Science 320, 190 (2008)."],
    )


def mtj_fom(
    TMR: float = 2.0,
    R_P: float = 1e4,
    Ms: float = 8e5,
    t_FM: float = 2e-9,
    K_u: float = 4e5,
    alpha: float = 0.01,
    P: float = 0.65,
    T: float = 300.0,
    d_bit: float = 20e-9,
    C_J: float = 40e-15,
    V_write: float = 0.5,
) -> DeviceFoMResult:
    """Compute MTJ standalone device FoMs.

    A standalone magnetic tunnel junction (MTJ) is characterized by its TMR
    ratio, thermal stability (retention), and read/write margins.

    FoM list:
    - Thermal stability Δ = K_u·V / (k_B·T)
    - TMR ratio (R_AP − R_P) / R_P
    - Resistance-area product RA = R_P · A_bit [Ω·μm²]
    - Write energy E_write = C_J · V_write² / 2 [J]
    - Read signal ΔV_read = (R_AP − R_P) · I_sense [mV/μA estimate]

    Sources:
        Yuasa, S., Djayaprawira, D. D., J. Phys. D: Appl. Phys. 40, R337 (2007).
        DOI: 10.1088/0022-3727/40/21/R01
        Ikeda, S. et al., Nat. Mater. 9, 721 (2010). DOI: 10.1038/nmat2804

    Args:
        TMR: Tunneling magnetoresistance ratio (R_AP − R_P)/R_P [dimensionless].
        R_P: Parallel-state resistance [Ω].
        Ms: Saturation magnetization [A/m].
        t_FM: Free-layer thickness [m].
        K_u: Uniaxial anisotropy constant [J/m³].
        alpha: Gilbert damping constant.
        P: Tunneling spin polarization.
        T: Temperature [K].
        d_bit: Free-layer diameter (circular pillar) [m].
        C_J: Junction capacitance [F].
        V_write: Write voltage [V].

    Returns:
        DeviceFoMResult.
    """
    from maglab.physics.constants import HBAR

    A_bit = np.pi * (d_bit / 2.0) ** 2
    V_bit = A_bit * t_FM

    # Thermal stability
    Delta = K_u * V_bit / (K_B * T)

    # TMR ratio
    R_AP = R_P * (1.0 + TMR)

    # Resistance-area product [Ω·μm²]
    RA_product = R_P * A_bit * 1e12  # convert m² → μm²

    # STT critical current density (Slonczewski, PMA): j_c = 2αeMsHk t/(ħP)
    H_k = 2.0 * K_u / (MU_0 * Ms)
    j_c_stt = (2.0 * alpha * E_CHARGE * MU_0 * Ms * t_FM * H_k) / (HBAR * P)
    I_c = j_c_stt * A_bit

    # Write energy (capacitive charge model): E = 0.5 C V²
    E_write = 0.5 * C_J * V_write**2

    foms: dict[str, dict[str, Any]] = {
        "thermal_stability_delta": {
            "value": float(Delta),
            "unit": "dimensionless",
            "formula": "Δ=K_u·V/(k_B·T)",
        },
        "TMR_ratio": {
            "value": float(TMR),
            "unit": "dimensionless",
            "formula": "TMR=(R_AP-R_P)/R_P",
        },
        "R_AP": {
            "value": float(R_AP),
            "unit": "Ohm",
            "formula": "R_AP=R_P(1+TMR)",
        },
        "resistance_area_product_RA": {
            "value": float(RA_product),
            "unit": "Ohm·um^2",
            "formula": "RA=R_P·A_bit",
        },
        "STT_critical_current_I_c": {
            "value": float(I_c),
            "unit": "A",
            "formula": "I_c=j_c·A_bit; j_c=2αeμ₀MsHkt/(ħP)",
        },
        "write_energy_E_write": {
            "value": float(E_write),
            "unit": "J",
            "formula": "E_write=0.5·C_J·V_write²",
        },
    }

    targets: dict[str, dict[str, Any]] = {
        "thermal_stability_delta": {
            "target": 60.0,
            "unit": "dimensionless",
            "ratio": float(Delta / 60.0),
        },
        "TMR_ratio": {
            "target": 2.0,
            "unit": "dimensionless",
            "ratio": float(TMR / 2.0),
        },
    }

    return DeviceFoMResult(
        device="mtj",
        foms=foms,
        inputs={
            "TMR": TMR,
            "R_P": R_P,
            "Ms": Ms,
            "t_FM": t_FM,
            "K_u": K_u,
            "alpha": alpha,
            "P": P,
            "T": T,
            "d_bit": d_bit,
            "C_J": C_J,
            "V_write": V_write,
        },
        target_comparison=targets,
        references=[
            "Yuasa, S., Djayaprawira, D. D., "
            "J. Phys. D: Appl. Phys. 40, R337 (2007). DOI: 10.1088/0022-3727/40/21/R01",
            "Ikeda, S. et al., Nat. Mater. 9, 721 (2010). DOI: 10.1038/nmat2804",
        ],
    )


def spin_valve_sensor_fom(
    GMR: float = 0.1,
    R_sq: float = 20.0,
    t_FM: float = 5e-9,
    Ms: float = 8e5,
    H_sat: float = 2e3,
    noise_floor: float = 1e-9,
    bandwidth: float = 1e6,
) -> DeviceFoMResult:
    """Compute spin-valve (GMR) sensor device FoMs.

    A spin-valve sensor exploits the giant magnetoresistance (GMR) effect to
    detect external fields.  Key FoMs are sensitivity, field resolution, and
    detectivity.

    FoM list:
    - GMR ratio ΔR/R_P [%]
    - Field sensitivity S_H = (ΔR/R_P) / H_sat [1/(A/m)]
    - Noise-equivalent field (NEF) = noise_floor / S_H [T/√Hz]
    - Detectivity D = 1 / (S_H · √(noise_floor·bandwidth)) [dimensionless]
    - Linear field range ≈ H_sat [A/m]

    Sources:
        Dieny, B. et al., Phys. Rev. B 43, 1297 (1991).
        DOI: 10.1103/PhysRevB.43.1297
        Freitas, P. P. et al., J. Phys.: Condens. Matter 19, 165221 (2007).
        DOI: 10.1088/0953-8984/19/16/165221

    Args:
        GMR: GMR ratio ΔR/R_P [dimensionless, e.g. 0.1 = 10%].
        R_sq: Sheet resistance (ohms per square) [Ω/□].
        t_FM: Magnetic free-layer thickness [m].
        Ms: Saturation magnetization [A/m].
        H_sat: Saturation field of the free layer [A/m].
        noise_floor: Voltage noise spectral density [V/√Hz] (white-noise floor).
        bandwidth: Sensor bandwidth [Hz].

    Returns:
        DeviceFoMResult.
    """
    # Field sensitivity [1/(A/m)] — GMR swing per unit field
    S_H = GMR / H_sat

    # Noise-equivalent field [A/m / √Hz] → convert to T/√Hz
    NEF_Am_sqrtHz = noise_floor / (S_H * R_sq)
    NEF_T_sqrtHz = NEF_Am_sqrtHz * MU_0

    foms: dict[str, dict[str, Any]] = {
        "GMR_ratio_percent": {
            "value": float(GMR * 100.0),
            "unit": "%",
            "formula": "GMR=(R_AP-R_P)/R_P×100",
        },
        "field_sensitivity_S_H": {
            "value": float(S_H),
            "unit": "1/(A/m)",
            "formula": "S_H=GMR/H_sat",
        },
        "noise_equivalent_field_T_sqrtHz": {
            "value": float(NEF_T_sqrtHz),
            "unit": "T/sqrt(Hz)",
            "formula": "NEF=noise_floor/(S_H·R_sq·μ₀)",
        },
        "linear_field_range_H_sat": {
            "value": float(H_sat),
            "unit": "A/m",
            "formula": "linear range ≈ H_sat",
        },
    }

    return DeviceFoMResult(
        device="spin-valve-sensor",
        foms=foms,
        inputs={
            "GMR": GMR,
            "R_sq": R_sq,
            "t_FM": t_FM,
            "Ms": Ms,
            "H_sat": H_sat,
            "noise_floor": noise_floor,
            "bandwidth": bandwidth,
        },
        references=[
            "Dieny, B. et al., Phys. Rev. B 43, 1297 (1991). "
            "DOI: 10.1103/PhysRevB.43.1297",
            "Freitas, P. P. et al., J. Phys.: Condens. Matter 19, 165221 (2007). "
            "DOI: 10.1088/0953-8984/19/16/165221",
        ],
    )


def spin_orbit_logic_fom(
    theta_SH: float = 0.3,
    alpha: float = 0.01,
    Ms: float = 8e5,
    t_FM: float = 2e-9,
    K_u: float = 4e5,
    rho_NM: float = 1.5e-6,
    t_NM: float = 5e-9,
    T: float = 300.0,
    d_bit: float = 20e-9,
    V_dd: float = 1.0,
) -> DeviceFoMResult:
    """Compute spin-orbit logic (SOL) device FoMs.

    Spin-orbit logic uses SOT switching for non-volatile logic-in-memory
    (LIM) operations.  Key FoMs are switching current, energy delay product,
    and switching speed.

    FoM list:
    - Thermal stability Δ = K_u·V / (k_B·T)
    - SOT critical switching current density j_c [A/m²]
    - Switching energy E_sw = j_c²·ρ_NM·t_NM·A_bit·τ_sw [J]  (τ_sw ~ 1 ns)
    - Energy-delay product EDP = E_sw · τ_sw [J·s]
    - Logic speed estimate f_max = 1 / (2·τ_sw) [GHz]

    Sources:
        Manipatruni, S. et al., Nature 565, 35 (2019).
        DOI: 10.1038/s41586-018-0770-2
        Dieny, B. et al., Nat. Electron. 3, 446 (2020).
        DOI: 10.1038/s41928-020-0461-5

    Args:
        theta_SH: Spin Hall angle [dimensionless].
        alpha: Gilbert damping constant.
        Ms: Saturation magnetization [A/m].
        t_FM: FM free-layer thickness [m].
        K_u: Perpendicular anisotropy constant [J/m³].
        rho_NM: Heavy-metal resistivity [Ω·m].
        t_NM: Heavy-metal (NM) layer thickness [m].
        T: Temperature [K].
        d_bit: Free-layer diameter [m].
        V_dd: Supply voltage [V].

    Returns:
        DeviceFoMResult.
    """
    from maglab.physics.constants import HBAR

    A_bit = np.pi * (d_bit / 2.0) ** 2
    V_bit = A_bit * t_FM

    # Thermal stability
    Delta = K_u * V_bit / (K_B * T)

    # SOT critical switching current density (PMA, macrospin, field-free SOT):
    # j_c = 2 α e μ₀ Ms t_FM (H_k + Ms/2) / (ħ θ_SH)
    H_k = 2.0 * K_u / (MU_0 * Ms)
    j_c = (2.0 * alpha * E_CHARGE * MU_0 * Ms * t_FM * (H_k + Ms / 2.0)) / (HBAR * theta_SH)

    # Switching time estimate (damping-determined): τ_sw ≈ π / (α ω_0), ω_0 = γ μ₀ H_k
    from maglab.physics.constants import GAMMA_E

    gamma_0 = abs(GAMMA_E)
    omega_0 = gamma_0 * MU_0 * H_k
    tau_sw = np.pi / max(alpha * omega_0, 1e-30)  # seconds
    tau_sw = min(tau_sw, 10e-9)  # cap at 10 ns for physically meaningful estimate

    # Switching energy: power dissipated in NM layer during τ_sw
    # R_NM = rho_NM * t_NM / A_bit (sheet resistance of NM contact)
    R_NM = rho_NM * t_NM / A_bit
    I_c = j_c * A_bit
    E_sw = I_c**2 * R_NM * tau_sw

    # Energy-delay product
    EDP = E_sw * tau_sw

    # Logic frequency estimate
    f_max_GHz = 1.0 / (2.0 * tau_sw) * 1e-9

    foms: dict[str, dict[str, Any]] = {
        "thermal_stability_delta": {
            "value": float(Delta),
            "unit": "dimensionless",
            "formula": "Δ=K_u·V/(k_B·T)",
        },
        "SOT_critical_current_density_j_c": {
            "value": float(j_c),
            "unit": "A/m^2",
            "formula": "j_c=2αeμ₀Ms t_FM(H_k+Ms/2)/(ħθ_SH)",
        },
        "switching_time_tau_sw": {
            "value": float(tau_sw * 1e9),
            "unit": "ns",
            "formula": "τ_sw=π/(α·γ·μ₀·H_k)",
        },
        "switching_energy_E_sw": {
            "value": float(E_sw),
            "unit": "J",
            "formula": "E_sw=I_c²·R_NM·τ_sw",
        },
        "energy_delay_product_EDP": {
            "value": float(EDP),
            "unit": "J·s",
            "formula": "EDP=E_sw·τ_sw",
        },
        "max_logic_frequency_f_max": {
            "value": float(f_max_GHz),
            "unit": "GHz",
            "formula": "f_max=1/(2τ_sw)",
        },
    }

    targets: dict[str, dict[str, Any]] = {
        "thermal_stability_delta": {
            "target": 40.0,
            "unit": "dimensionless",
            "ratio": float(Delta / 40.0),
        },
    }

    return DeviceFoMResult(
        device="spin-orbit-logic",
        foms=foms,
        inputs={
            "theta_SH": theta_SH,
            "alpha": alpha,
            "Ms": Ms,
            "t_FM": t_FM,
            "K_u": K_u,
            "rho_NM": rho_NM,
            "t_NM": t_NM,
            "T": T,
            "d_bit": d_bit,
            "V_dd": V_dd,
        },
        target_comparison=targets,
        references=[
            "Manipatruni, S. et al., Nature 565, 35 (2019). DOI: 10.1038/s41586-018-0770-2",
            "Dieny, B. et al., Nat. Electron. 3, 446 (2020). DOI: 10.1038/s41928-020-0461-5",
        ],
    )


def magnon_device_fom(
    A: float = 4e-12,
    Ms: float = 1.4e5,
    alpha: float = 5e-4,
    K_u: float = 0.0,
    d_waveguide: float = 1e-6,
    L_waveguide: float = 100e-6,
    f_drive: float = 3e9,
) -> DeviceFoMResult:
    """Compute magnon-based device FoMs (magnonic waveguide / spin-wave logic).

    Magnon devices exploit spin waves (magnons) for information processing.
    Key FoMs are group velocity, decay length, and power consumption relative
    to electronic logic.

    FoM list:
    - Exchange spin-wave group velocity v_g = 2A·k / (μ₀ Ms) [m/s]
    - Magnon propagation length λ_prop = v_g / (α·ω) [m]
    - Waveguide transit time τ = L_waveguide / v_g [ps]
    - Power per spin-wave packet P_sw [W] — thermal energy kT at room T
    - Magnon figure-of-merit ξ_magnon = λ_prop / d_waveguide [dimensionless]

    Sources:
        Chumak, A. V. et al., Nat. Phys. 11, 453 (2015).
        DOI: 10.1038/nphys3347
        Kruglyak, V. V. et al., J. Phys. D: Appl. Phys. 43, 264001 (2010).
        DOI: 10.1088/0022-3727/43/26/264001

    Args:
        A: Exchange stiffness [J/m].
        Ms: Saturation magnetization [A/m].
        alpha: Gilbert damping constant.
        K_u: Uniaxial anisotropy constant [J/m³].
        d_waveguide: Waveguide width [m].
        L_waveguide: Waveguide length [m].
        f_drive: Drive frequency [Hz].

    Returns:
        DeviceFoMResult.
    """
    omega = 2.0 * np.pi * f_drive

    # Exchange spin-wave dispersion: ω(k) = γ μ₀ (H_0 + (2A/Ms)·k²)
    # Group velocity at k = π / d_waveguide (first mode, typical waveguide k)
    k_mode = np.pi / d_waveguide
    v_g = 2.0 * A * k_mode / (MU_0 * Ms)  # ∂ω/∂k at exchange limit

    # Propagation length λ = v_g / (α ω)
    lambda_prop = v_g / (alpha * omega + 1e-30)

    # Waveguide transit time
    tau_transit_ps = L_waveguide / max(v_g, 1e-15) * 1e12

    # Thermal energy kT per spin-wave packet (minimum excitation cost)
    P_sw_kT = K_B * 300.0  # J/packet (approximate)

    # Magnon FoM: propagation-length-to-width ratio
    xi_magnon = lambda_prop / d_waveguide

    foms: dict[str, dict[str, Any]] = {
        "spin_wave_group_velocity_v_g": {
            "value": float(v_g),
            "unit": "m/s",
            "formula": "v_g=2A·k/(μ₀M_s)",
        },
        "magnon_propagation_length_lambda": {
            "value": float(lambda_prop * 1e6),
            "unit": "um",
            "formula": "λ=v_g/(α·ω)",
        },
        "waveguide_transit_time_tau": {
            "value": float(tau_transit_ps),
            "unit": "ps",
            "formula": "τ=L/v_g",
        },
        "thermal_energy_per_packet_kT": {
            "value": float(P_sw_kT),
            "unit": "J",
            "formula": "E_min=k_B·T (room temperature)",
        },
        "magnon_FoM_xi": {
            "value": float(xi_magnon),
            "unit": "dimensionless",
            "formula": "ξ=λ_prop/d_waveguide",
        },
    }

    return DeviceFoMResult(
        device="magnon",
        foms=foms,
        inputs={
            "A": A,
            "Ms": Ms,
            "alpha": alpha,
            "K_u": K_u,
            "d_waveguide": d_waveguide,
            "L_waveguide": L_waveguide,
            "f_drive": f_drive,
        },
        references=[
            "Chumak, A. V. et al., Nat. Phys. 11, 453 (2015). DOI: 10.1038/nphys3347",
            "Kruglyak, V. V. et al., J. Phys. D: Appl. Phys. 43, 264001 (2010). "
            "DOI: 10.1088/0022-3727/43/26/264001",
        ],
    )


# ---------------------------------------------------------------------------
# Registry entry point
# ---------------------------------------------------------------------------

_DEVICE_FOM_REGISTRY: dict[str, Any] = {
    "sot-mram": sot_mram_fom,
    "stt-mram": stt_mram_fom,
    "racetrack": racetrack_fom,
    "mtj": mtj_fom,
    "spin-valve-sensor": spin_valve_sensor_fom,
    "spin-orbit-logic": spin_orbit_logic_fom,
    "magnon": magnon_device_fom,
}


def compute_fom(device: str, **kwargs: Any) -> DeviceFoMResult:
    """Compute FoMs for the given device name and parameters.

    Args:
        device: Device type ("sot-mram", "stt-mram", "racetrack").
        **kwargs: Device-specific parameters.

    Returns:
        DeviceFoMResult.

    Raises:
        KeyError: Unknown device name.
    """
    if device not in _DEVICE_FOM_REGISTRY:
        raise KeyError(f"Unknown device: '{device}'. Supported: {list(_DEVICE_FOM_REGISTRY.keys())}")
    return _DEVICE_FOM_REGISTRY[device](**kwargs)


def list_devices() -> list[str]:
    """Return the list of registered device types."""
    return list(_DEVICE_FOM_REGISTRY.keys())
