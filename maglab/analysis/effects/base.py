"""EffectModel interface and auxiliary type definitions.

Defines the abstract base class (ABC) and auxiliary types (ParamSpec, MeasurementConfig,
FitResult) for all effect models. Each concrete effect model must implement this interface.

Design basis: plan/04-analysis.md §11.2, impl/03-P2-analysis.md T-P2-03
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Auxiliary types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    """Fitting parameter specification.

    Attributes:
        name: Parameter name (e.g., "R_0", "alpha").
        unit: SI unit string (e.g., "Ohm/T", "dimensionless").
        lower: Physical lower bound (None = unconstrained).
        upper: Physical upper bound (None = unconstrained).
        description: Parameter description.
    """

    name: str
    unit: str
    lower: float | None = None
    upper: float | None = None
    description: str = ""


@dataclass(frozen=True)
class MeasurementConfig:
    """Measurement geometry and tensor structure specification.

    Attributes:
        geometry: Measurement geometry description (e.g., "Hall bar, I∥x, B∥z, V_y").
        tensor_rank: Effect tensor rank (AHE=2, OHE=3, etc.).
        required_columns: List of required column names in data files.
        notes: Additional measurement notes.
    """

    geometry: str
    tensor_rank: int = 2
    required_columns: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


@dataclass
class FitResult:
    """Fitting result data structure.

    Attributes:
        params: Dictionary of fitted parameter name → value.
        uncertainties: Parameter name → 1σ uncertainty.
        chi2: Sum of squared residuals (chi-squared).
        reduced_chi2: Reduced chi-squared (chi2 / (N - P)).
        covariance: Parameter covariance matrix.
        provenance_id: DataPoint ID where the fitting result is stored.
        message: Fitting convergence message.
        success: Whether fitting converged.
        effect_name: Name of the effect model used for fitting.
        raw_result: lmfit MinimizerResult object (for post-processing, optional).
    """

    params: dict[str, float]
    uncertainties: dict[str, float]
    chi2: float
    reduced_chi2: float
    covariance: np.ndarray
    provenance_id: str = ""
    message: str = ""
    success: bool = True
    effect_name: str = ""
    raw_result: Any = None


# ---------------------------------------------------------------------------
# EffectModel ABC
# ---------------------------------------------------------------------------


class EffectModel(ABC):
    """Abstract base class for effect fitting models.

    A unit that holds the exact fitting format for each magnetism/spintronics effect.
    `forward()` generates a signal from known parameters, and `fit()` recovers
    parameters from data.

    Subclasses must implement all abstract properties/methods.

    Design basis: plan/04-analysis.md §11.2
    """

    # ------------------------------------------------------------------
    # Meta properties (defined as class variables in subclasses)
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Effect model identifier (e.g., "anomalous_hall")."""
        ...

    @property
    @abstractmethod
    def subfield(self) -> str:
        """Domain (e.g., "magnetotransport", "spin_orbitronics")."""
        ...

    @property
    @abstractmethod
    def references(self) -> list[str]:
        """List of primary literature sources (author-journal-year format)."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> list[ParamSpec]:
        """List of fitting parameter specifications."""
        ...

    @property
    @abstractmethod
    def measurement_config(self) -> MeasurementConfig:
        """Measurement geometry and tensor structure specification."""
        ...

    @property
    @abstractmethod
    def symmetry_constraints(self) -> dict[str, Any]:
        """Magnetic point group allowed component constraints (populated by symmetry.py).

        Keys: parameter names, values: allowed status or fixed value.
        """
        ...

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    @abstractmethod
    def forward(
        self,
        params: dict[str, float],
        geometry: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Compute signal from known parameters (forward model).

        Args:
            params: Parameter name → value dictionary.
            geometry: Additional measurement geometry information (input data coordinate system, etc.).

        Returns:
            Computed signal array.
        """
        ...

    @abstractmethod
    def fit(
        self,
        data: dict[str, np.ndarray],
        geometry: dict[str, Any] | None = None,
    ) -> FitResult:
        """Recover parameters from data (inverse fitting).

        Args:
            data: Column name → array dictionary. See measurement_config.required_columns.
            geometry: Additional measurement geometry information.

        Returns:
            FitResult instance.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def param_names(self) -> list[str]:
        """Return the list of parameter names."""
        return [p.name for p in self.parameters]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' subfield='{self.subfield}'>"
