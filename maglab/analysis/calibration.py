"""Calibration registry, systematic correction pipeline, and GUM uncertainty budget.

Measurements are not fit directly; they pass through calibration and systematic
corrections before uncertainty propagation.

Design basis: plan/04-analysis.md §11.6, impl/03-P2-analysis.md T-P2-33
Sources: JCGM 100:2008 (GUM), ISO/IEC Guide 98-3.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from maglab.core.atomic import atomic_write_text

# ---------------------------------------------------------------------------
# Calibration registry
# ---------------------------------------------------------------------------


@dataclass
class CalibrationEntry:
    """Single calibration factor entry.

    Attributes:
        id: Unique calibration entry ID.
        instrument: Instrument identifier (e.g., "Keithley_2400_SN123").
        channel: Channel identifier (optional).
        factor: Calibration factor (measured × factor = corrected).
        offset: Calibration offset (corrected = measured × factor + offset).
        uncertainty: Calibration uncertainty (1σ).
        valid_from: Calibration validity start (UTC ISO 8601).
        valid_until: Calibration validity end (UTC ISO 8601, None=indefinite).
        notes: Calibration conditions/notes.
    """

    instrument: str
    channel: str = ""
    factor: float = 1.0
    offset: float = 0.0
    uncertainty: float = 0.0
    valid_from: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    valid_until: str | None = None
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def is_valid(self, at: datetime | None = None) -> bool:
        """Check whether the calibration is valid at the specified time."""
        check_time = at or datetime.now(UTC)
        valid_from_dt = datetime.fromisoformat(self.valid_from)
        if check_time < valid_from_dt:
            return False
        if self.valid_until is not None:
            valid_until_dt = datetime.fromisoformat(self.valid_until)
            if check_time > valid_until_dt:
                return False
        return True

    def apply(self, value: np.ndarray | float) -> np.ndarray | float:
        """Apply calibration factor: corrected = value × factor + offset."""
        return np.asarray(value) * self.factor + self.offset

    def unapply(self, corrected: np.ndarray | float) -> np.ndarray | float:
        """Inverse-apply calibration: raw = (corrected - offset) / factor."""
        if self.factor == 0.0:
            raise ValueError("Calibration factor = 0: cannot inverse-apply.")
        return (np.asarray(corrected) - self.offset) / self.factor


class CalibrationRegistry:
    """Registry for storing and querying calibration factors by instrument and channel.

    File storage: JSON (in-memory → file serialization/restoration).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._entries: list[CalibrationEntry] = []
        self._path = Path(path) if path else None
        if self._path and self._path.exists():
            self._load()

    def add(self, entry: CalibrationEntry) -> str:
        """Register a calibration entry. Returns the entry ID."""
        self._entries.append(entry)
        if self._path:
            self._save()
        return entry.id

    def get(
        self,
        instrument: str,
        channel: str = "",
        at: datetime | None = None,
    ) -> CalibrationEntry | None:
        """Return the most recent valid calibration entry (None if not found)."""
        check_time = at or datetime.now(UTC)
        matches = [
            e
            for e in self._entries
            if e.instrument == instrument and e.channel == channel and e.is_valid(check_time)
        ]
        if not matches:
            return None
        # Most recent valid_from
        return sorted(matches, key=lambda e: e.valid_from, reverse=True)[0]

    def check_expired(
        self,
        instrument: str,
        channel: str = "",
    ) -> bool:
        """Check if calibration has expired. Returns True if expired or not registered."""
        entry = self.get(instrument, channel)
        return entry is None

    def list_all(self) -> list[CalibrationEntry]:
        """Return the list of all calibration entries."""
        return list(self._entries)

    def _save(self) -> None:
        """Save to JSON file."""
        assert self._path is not None
        data = [
            {
                "id": e.id,
                "instrument": e.instrument,
                "channel": e.channel,
                "factor": e.factor,
                "offset": e.offset,
                "uncertainty": e.uncertainty,
                "valid_from": e.valid_from,
                "valid_until": e.valid_until,
                "notes": e.notes,
            }
            for e in self._entries
        ]
        # Atomic: _load() runs from __init__ with no error handling, so a
        # truncated calibration file makes every command that opens the store
        # die on a raw JSONDecodeError — after silently losing the factors and
        # offsets that measurements are corrected with.
        atomic_write_text(self._path, json.dumps(data, indent=2))

    def _load(self) -> None:
        """Restore from JSON file."""
        assert self._path is not None
        data = json.loads(self._path.read_text())
        for d in data:
            entry = CalibrationEntry(
                instrument=d["instrument"],
                channel=d.get("channel", ""),
                factor=d.get("factor", 1.0),
                offset=d.get("offset", 0.0),
                uncertainty=d.get("uncertainty", 0.0),
                valid_from=d.get("valid_from", datetime.now(UTC).isoformat()),
                valid_until=d.get("valid_until"),
                notes=d.get("notes", ""),
                id=d.get("id", str(uuid.uuid4())),
            )
            self._entries.append(entry)


# ---------------------------------------------------------------------------
# Systematic correction pipeline
# ---------------------------------------------------------------------------


@dataclass
class CorrectionStep:
    """Single declarative correction step.

    Attributes:
        name: Correction step name (e.g., "background_subtraction").
        fn: Correction function (ndarray → ndarray).
        inv_fn: Inverse function (for reversibility verification, optional).
        uncertainty: Additional uncertainty contribution from this correction (absolute).
        description: Correction description.
    """

    name: str
    fn: Callable[[np.ndarray], np.ndarray]
    inv_fn: Callable[[np.ndarray], np.ndarray] | None = None
    uncertainty: float = 0.0
    description: str = ""


class CorrectionPipeline:
    """Declarative systematic correction pipeline.

    Each correction step is reversible and traceable, recorded in provenance.
    Applied to raw data before fitting.
    """

    def __init__(self) -> None:
        self._steps: list[CorrectionStep] = []

    def add_step(self, step: CorrectionStep) -> None:
        """Add a correction step to the pipeline."""
        self._steps.append(step)

    def apply(self, data: np.ndarray) -> tuple[np.ndarray, list[str]]:
        """Apply all correction steps in order.

        Args:
            data: Raw data array.

        Returns:
            (corrected, step_log) tuple.
            corrected: Corrected data.
            step_log: List of applied step names.
        """
        corrected = data.copy()
        log: list[str] = []
        for step in self._steps:
            corrected = step.fn(corrected)
            log.append(step.name)
        return corrected, log

    def unapply(self, corrected: np.ndarray) -> np.ndarray:
        """Inverse-apply in reverse order to recover raw data.

        Steps without an inverse function are treated as identity.

        Args:
            corrected: Corrected data.

        Returns:
            Recovered raw data.
        """
        raw = corrected.copy()
        for step in reversed(self._steps):
            if step.inv_fn is not None:
                raw = step.inv_fn(raw)
        return raw

    def total_uncertainty(self) -> float:
        """GUM: return the quadrature combination of all correction step uncertainties."""
        return float(np.sqrt(sum(s.uncertainty**2 for s in self._steps)))

    @staticmethod
    def background_subtraction(background: np.ndarray) -> CorrectionPipeline:
        """Convenience factory to create a background subtraction pipeline."""
        pipeline = CorrectionPipeline()
        _bg = background.copy()
        pipeline.add_step(
            CorrectionStep(
                name="background_subtraction",
                fn=lambda x: x - _bg,
                inv_fn=lambda x: x + _bg,
                uncertainty=float(np.std(background)),
                description="Subtract measured background signal",
            )
        )
        return pipeline

    @staticmethod
    def offset_removal() -> CorrectionPipeline:
        """DC offset removal pipeline."""
        pipeline = CorrectionPipeline()
        pipeline.add_step(
            CorrectionStep(
                name="offset_removal",
                fn=lambda x: x - float(x.mean()),
                inv_fn=None,  # Cannot invert without knowing the original mean
                uncertainty=0.0,
                description="Remove DC offset (subtract mean)",
            )
        )
        return pipeline

    @staticmethod
    def hall_antisymmetrize() -> CorrectionPipeline:
        """Hall data antisymmetrization: ρ_H = (ρ_xy(+H) - ρ_xy(-H))/2."""
        pipeline = CorrectionPipeline()

        def antisymm(x: np.ndarray) -> np.ndarray:
            n = len(x)
            if n % 2 != 0:
                return x  # Return as-is for odd length
            half = n // 2
            return (x[:half] - x[half:][::-1]) / 2.0

        pipeline.add_step(
            CorrectionStep(
                name="hall_antisymmetrize",
                fn=antisymm,
                inv_fn=None,
                uncertainty=0.0,
                description="Hall resistivity antisymmetrization (ρ_H = [ρ(+H)-ρ(-H)]/2)",
            )
        )
        return pipeline


# ---------------------------------------------------------------------------
# GUM uncertainty budget
# ---------------------------------------------------------------------------


@dataclass
class UncertaintyComponent:
    """Single component of a GUM uncertainty budget."""

    name: str
    value: float  # 1σ absolute uncertainty
    source: str = ""  # source of uncertainty


@dataclass
class UncertaintyBudget:
    """GUM uncertainty budget (full analysis chain).

    σ_total² = σ_measurement² + σ_calibration² + σ_fit²

    Source: JCGM 100:2008 (GUM). ISO/IEC Guide 98-3.
    """

    components: list[UncertaintyComponent] = field(default_factory=list)

    def add(self, name: str, value: float, source: str = "") -> None:
        """Add an uncertainty component."""
        self.components.append(UncertaintyComponent(name=name, value=value, source=source))

    def total(self) -> float:
        """GUM combined uncertainty: σ_total = sqrt(Σ σ_i²)."""
        return float(np.sqrt(sum(c.value**2 for c in self.components)))

    def relative_total(self, reference: float) -> float:
        """Relative uncertainty: σ_total / |reference|."""
        if abs(reference) < 1e-30:
            return float("inf")
        return self.total() / abs(reference)

    def table(self) -> list[dict[str, Any]]:
        """Return the error budget table as a list of dictionaries."""
        rows = []
        total = self.total()
        for c in self.components:
            rows.append(
                {
                    "name": c.name,
                    "value": c.value,
                    "source": c.source,
                    "fraction": (c.value / total) ** 2 if total > 0 else 0.0,
                }
            )
        rows.append(
            {
                "name": "TOTAL (combined)",
                "value": total,
                "source": "GUM quadrature combination",
                "fraction": 1.0,
            }
        )
        return rows


def build_uncertainty_budget(
    sigma_measurement: float,
    sigma_calibration: float,
    sigma_fit: float,
) -> UncertaintyBudget:
    """Build a GUM budget from the three major uncertainty components of the analysis chain.

    Args:
        sigma_measurement: Measurement uncertainty (1σ).
        sigma_calibration: Calibration uncertainty (1σ).
        sigma_fit: Fitting uncertainty (lmfit stderr, 1σ).

    Returns:
        UncertaintyBudget.
    """
    budget = UncertaintyBudget()
    budget.add("measurement", sigma_measurement, "measurement noise and repeatability")
    budget.add("calibration", sigma_calibration, "calibration factor uncertainty")
    budget.add("fitting", sigma_fit, "lmfit parameter standard deviation")
    return budget
