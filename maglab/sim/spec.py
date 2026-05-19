"""Multiscale simulation IR (engine-agnostic) — MultiScaleSpec.

Design rationale: PLAN §10.2 · impl/02-P1-figure-sim.md T-P1-01.

``MultiScaleSpec`` is a declarative IR composed of a list of scales
(``ScaleSpec[]``) and a list of inter-scale handoffs (``Handoff[]``).
It is not bound to any engine (MuMax3·OOMMF·magnum.np); a single-scale
job is represented as a ``scales`` list with one element.

P3 extension readiness: ``scale`` includes ``"dft"``·``"atomistic"``·``"device"``
from the start so that P3 can insert new entries without breaking this IR.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Scale enumeration
# ---------------------------------------------------------------------------


class ScaleType(StrEnum):
    """Supported physical scales.

    - micro     : Micromagnetic simulation (MuMax3·OOMMF·magnum.np) — P1 implemented.
    - atomistic : Atomistic simulation (VAMPIRE·Spirit) — P3 reserved.
    - dft       : DFT first-principles (VASP·QE·FLEUR) — P3 reserved.
    - device    : Device/transport simulation — P3 reserved.
    """

    micro = "micro"
    atomistic = "atomistic"
    dft = "dft"
    device = "device"


# ---------------------------------------------------------------------------
# Micromagnetic material parameters
# ---------------------------------------------------------------------------


class MicroMagMaterial(BaseModel):
    """Material parameters for micromagnetic simulation.

    Attributes:
        Ms_Am: Saturation magnetization [A/m]. Required.
        A_Jm: Exchange stiffness [J/m]. Required.
        alpha: Gilbert damping constant [dimensionless]. Required, > 0.
        K_Jm3: Anisotropy constant [J/m³]. Optional (0 if absent).
        K_axis: Anisotropy axis unit vector [x, y, z]. Default [0, 0, 1].
        D_Jm2: DMI coefficient [J/m²]. Optional (0 if absent).
        material_id: Material DB ID (reference only). Optional.
    """

    Ms_Am: float = Field(..., description="Saturation magnetization [A/m]", gt=0.0)
    A_Jm: float = Field(..., description="Exchange stiffness [J/m]", gt=0.0)
    alpha: float = Field(..., description="Gilbert damping constant", gt=0.0, le=1.0)
    K_Jm3: float = Field(default=0.0, description="Anisotropy constant [J/m³]")
    K_axis: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 1.0], description="Anisotropy axis unit vector"
    )
    D_Jm2: float = Field(default=0.0, description="DMI coefficient [J/m²]")
    material_id: str | None = Field(default=None, description="Material DB ID")

    @model_validator(mode="after")
    def _validate_k_axis(self) -> MicroMagMaterial:
        """Verify that the anisotropy axis is a 3-dimensional vector."""
        if len(self.K_axis) != 3:
            raise ValueError(f"K_axis must be a 3-dimensional vector. Got: {self.K_axis}")
        return self


# ---------------------------------------------------------------------------
# Micromagnetic geometry parameters
# ---------------------------------------------------------------------------


class MicroMagGeometry(BaseModel):
    """Geometry (mesh) parameters for micromagnetic simulation.

    Attributes:
        nx, ny, nz: Number of grid cells in each direction. Each ≥ 1.
        dx_nm, dy_nm, dz_nm: Cell size [nm]. Each > 0.
        pbc_x, pbc_y, pbc_z: Periodic boundary condition flags.
    """

    nx: int = Field(..., ge=1, description="Number of grid cells in x")
    ny: int = Field(..., ge=1, description="Number of grid cells in y")
    nz: int = Field(..., ge=1, description="Number of grid cells in z")
    dx_nm: float = Field(..., gt=0.0, description="Cell size in x [nm]")
    dy_nm: float = Field(..., gt=0.0, description="Cell size in y [nm]")
    dz_nm: float = Field(..., gt=0.0, description="Cell size in z [nm]")
    pbc_x: bool = Field(default=False)
    pbc_y: bool = Field(default=False)
    pbc_z: bool = Field(default=False)

    @property
    def cell_size_m(self) -> tuple[float, float, float]:
        """Return cell size in SI units [m]."""
        return (self.dx_nm * 1e-9, self.dy_nm * 1e-9, self.dz_nm * 1e-9)

    @property
    def total_volume_m3(self) -> float:
        """Return total simulation domain volume [m³]."""
        dx, dy, dz = self.cell_size_m
        return self.nx * self.ny * self.nz * dx * dy * dz


# ---------------------------------------------------------------------------
# External field sweep specification
# ---------------------------------------------------------------------------


class FieldSweep(BaseModel):
    """External magnetic field sweep specification.

    Attributes:
        H_start_Am: Initial field vector [A/m] (x, y, z).
        H_end_Am: Final field vector [A/m] (x, y, z).
        n_steps: Number of steps.
    """

    H_start_Am: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    H_end_Am: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    n_steps: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Single-scale simulation specification (ScaleSpec)
# ---------------------------------------------------------------------------


class ScaleSpec(BaseModel):
    """Single-scale simulation specification.

    The backend corresponding to the physical ``scale`` interprets the parameters.
    In P1 only ``scale="micro"`` is implemented.

    Attributes:
        scale: Physical scale (ScaleType enum).
        engine: Preferred solver engine ("magnumnp"|"oommf"|"mumax3"|"auto").
        label: Human-readable label for this scale stage.
        material: Micromagnetic material parameters (required when scale="micro").
        geometry: Micromagnetic geometry parameters (required when scale="micro").
        field_sweep: External field sweep specification. Optional.
        t_sim_ns: Simulation time [ns]. Used when scale="micro".
        dt_ns: Time step [ns]. None lets the solver choose automatically.
        initial_state: Initial magnetization state name ("uniform_x"|"uniform_z"|"random").
        initial_m_dir: Initial magnetization direction vector (uniform mode). Default [1, 0, 0].
        extra: Engine-specific additional parameters (free dictionary).
    """

    scale: ScaleType
    engine: str = Field(default="auto", description="Solver engine selection")
    label: str = Field(default="", description="Stage label")

    # micro scale parameters
    material: MicroMagMaterial | None = Field(default=None)
    geometry: MicroMagGeometry | None = Field(default=None)
    field_sweep: FieldSweep | None = Field(default=None)

    # Dynamics
    t_sim_ns: float = Field(default=0.0, ge=0.0, description="Simulation time [ns]")
    dt_ns: float | None = Field(default=None, description="Time step [ns]")
    initial_state: str = Field(default="uniform_x", description="Initial magnetization state")
    initial_m_dir: list[float] = Field(default_factory=lambda: [1.0, 0.0, 0.0])

    # Extension
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_micro_params(self) -> ScaleSpec:
        """Verify that material and geometry are provided when scale='micro'."""
        if self.scale == ScaleType.micro:
            if self.material is None:
                raise ValueError("ScaleSpec with scale='micro' requires the material parameter.")
            if self.geometry is None:
                raise ValueError("ScaleSpec with scale='micro' requires the geometry parameter.")
        return self


# ---------------------------------------------------------------------------
# Inter-scale handoff
# ---------------------------------------------------------------------------


class Handoff(BaseModel):
    """Scale N → N+1 handoff specification.

    P3 implements the DFT→atomistic and atomistic→micromagnetic handoffs.
    In P1 this structure is included in the IR but no active handoffs exist.

    Attributes:
        from_scale: Source scale.
        to_scale: Target scale.
        mapping: Handoff mapping parameter dictionary (e.g. {"J_ij_to_A": true}).
        notes: Units, assumptions, and source reference notes.
    """

    from_scale: ScaleType
    to_scale: ScaleType
    mapping: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


# ---------------------------------------------------------------------------
# Multiscale IR
# ---------------------------------------------------------------------------


class MultiScaleSpec(BaseModel):
    """Multiscale simulation IR (engine-agnostic).

    A single-scale job is represented as a ``scales`` list with one element.
    For P3 extension, add a new Handoff to ``handoffs`` and insert a new
    ScaleSpec into ``scales`` — this IR itself is not broken.

    Attributes:
        name: Simulation identification name.
        description: Description of the simulation purpose.
        scales: List of ScaleSpec. Order is execution order.
        handoffs: List of inter-scale handoffs. Empty for single-scale simulations.
        provenance_ref: Reference to the DataPoint/job ID that generated this spec.
    """

    name: str = Field(default="sim", description="Simulation name")
    description: str = Field(default="", description="Purpose description")
    scales: list[ScaleSpec] = Field(default_factory=list)
    handoffs: list[Handoff] = Field(default_factory=list)
    provenance_ref: str = Field(default="", description="Generation source reference")

    @model_validator(mode="after")
    def _validate_scales_nonempty(self) -> MultiScaleSpec:
        """MultiScaleSpec must contain at least one ScaleSpec."""
        if not self.scales:
            raise ValueError("MultiScaleSpec must contain at least one ScaleSpec.")
        return self

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def single_scale_spec(self) -> ScaleSpec:
        """Return the ScaleSpec for a single-scale simulation.

        Raises:
            ValueError: If there are two or more scales.
        """
        if len(self.scales) != 1:
            raise ValueError(f"Not a single-scale spec (number of scales: {len(self.scales)}).")
        return self.scales[0]

    def is_single_scale(self) -> bool:
        """Return whether this is a single-scale simulation."""
        return len(self.scales) == 1

    def scales_of_type(self, scale_type: ScaleType) -> list[ScaleSpec]:
        """Return the list of ScaleSpecs matching the given scale type."""
        return [s for s in self.scales if s.scale == scale_type]
