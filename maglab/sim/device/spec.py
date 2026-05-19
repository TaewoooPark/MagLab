"""Device/transport scale ScaleSpec extension and input schema.

Design rationale: impl/04-P3-multiscale.md T-P3-14 · plan/03-physics-simulation.md §10.1.

Declares the input schema that receives ``micro_to_device`` handoff output.
Specifies ``Quantity`` types for critical current, switching time, and skyrmion Hall angle.

Placeholder for substantive implementation in P4 and beyond.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeviceSpec(BaseModel):
    """Device-scale simulation specification (placeholder).

    Inserted into ``MultiScaleSpec`` as
    ``ScaleSpec(scale="device", extra={"device_spec": DeviceSpec(...)})``.

    Attributes:
        Ms_Am: Saturation magnetization [A/m] (micromagnetic → device handoff output).
        A_Jm: Exchange stiffness [J/m].
        alpha: Gilbert damping constant.
        K_Jm3: Anisotropy constant [J/m³].
        D_Jm2: DMI coefficient [J/m²].
        j_c_Am2: Critical current density [A/m²] (estimated, micromagnetic → device handoff).
        t_sw_s: Switching time [s] (estimated).
        theta_SkH_rad: Skyrmion Hall angle [rad].
        extra: Free dictionary for additional parameters.
    """

    Ms_Am: float = Field(..., description="Saturation magnetization [A/m]", gt=0.0)
    A_Jm: float = Field(..., description="Exchange stiffness [J/m]", gt=0.0)
    alpha: float = Field(..., description="Gilbert damping constant", gt=0.0, le=1.0)
    K_Jm3: float = Field(default=0.0, description="Anisotropy constant [J/m³]")
    D_Jm2: float = Field(default=0.0, description="DMI coefficient [J/m²]")
    j_c_Am2: float | None = Field(default=None, description="Critical current density [A/m²]")
    t_sw_s: float | None = Field(default=None, description="Switching time [s]")
    theta_SkH_rad: float | None = Field(default=None, description="Skyrmion Hall angle [rad]")
    extra: dict[str, Any] = Field(default_factory=dict)


class DeviceResult(BaseModel):
    """Device-scale calculation result (placeholder).

    Attributes:
        device_spec: Input device specification.
        fom: Figure-of-merit dictionary (populated from P4 onwards).
        notes: Notes on calculation assumptions and sources.
    """

    device_spec: DeviceSpec
    fom: dict[str, float] = Field(default_factory=dict)
    notes: str = ""

    def summary(self) -> str:
        """Return a summary string."""
        fom_str = ", ".join(f"{k}={v:.4g}" for k, v in self.fom.items()) if self.fom else "not computed"
        return f"Device scale | FoM: {fom_str} | Notes: {self.notes[:80]}"
