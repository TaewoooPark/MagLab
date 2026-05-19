"""Active learning shared state — StandardState (§13.7).

Measurement conditions, collected data, and current best model state
shared between the theorist and experimentalist roles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class MeasurementPoint:
    """Single measurement point.

    Attributes
    ----------
    conditions:
        Dictionary of measurement conditions (e.g. {"B": 0.5, "T": 300}).
    observations:
        Dictionary of observed values (e.g. {"Rxy": 0.01}).
    precision_level:
        Fidelity level ('low'=DFT, 'medium'=atomistic, 'high'=experiment).
    cost:
        Relative measurement cost unit.
    """

    conditions: dict[str, float]
    observations: dict[str, float]
    precision_level: str = "high"
    cost: float = 1.0


@dataclass
class StandardState:
    """Shared theorist↔experimentalist state (§13.7).

    Attributes
    ----------
    goal:
        Research goal.
    measured_points:
        List of measurement points collected so far.
    current_best_model:
        Current best model parameter dictionary.
    model_uncertainty:
        Model parameter uncertainty (variance).
    feasible_region:
        Feasible condition region (learned constraints).
    metadata:
        Additional metadata.
    """

    goal: str = ""
    measured_points: list[MeasurementPoint] = field(default_factory=list)
    current_best_model: dict[str, float] = field(default_factory=dict)
    model_uncertainty: dict[str, float] = field(default_factory=dict)
    feasible_region: dict[str, tuple[float, float]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_point(self, point: MeasurementPoint) -> None:
        """Add a measurement point and update the feasible region."""
        self.measured_points.append(point)
        self._update_feasible_region(point)

    def _update_feasible_region(self, point: MeasurementPoint) -> None:
        """Incrementally learn the feasible condition range."""
        for param, value in point.conditions.items():
            if param not in self.feasible_region:
                self.feasible_region[param] = (value, value)
            else:
                lo, hi = self.feasible_region[param]
                self.feasible_region[param] = (min(lo, value), max(hi, value))

    def conditions_array(self) -> np.ndarray:
        """Return measurement conditions as a NumPy array."""
        if not self.measured_points:
            return np.empty((0, 0))
        keys = sorted(self.measured_points[0].conditions.keys())
        rows = [[p.conditions.get(k, 0.0) for k in keys] for p in self.measured_points]
        return np.array(rows, dtype=float)

    def observations_array(self, target_key: str) -> np.ndarray:
        """Return a specific observation as a NumPy array."""
        return np.array(
            [p.observations.get(target_key, float("nan")) for p in self.measured_points],
            dtype=float,
        )
