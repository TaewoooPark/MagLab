"""DataPoint — the fundamental data structure for all numerical results.

Research integrity principle (§3.3·§17): every numerical value must be wrapped
in a ``DataPoint`` with a mandatory provenance type (``provenance_type``),
units (``units``), and source reference (``source_ref``).  Bare ``float``
values appearing in reports or text are blocked by ``HonestyGate``.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ProvenanceType(StrEnum):
    """Classification of a numerical value's origin.

    - SIMULATED : value produced by a deterministic simulator (MuMax3, VAMPIRE, etc.).
    - MEASURED  : value obtained from experimental apparatus.
    - THEORY    : value computed from a closed-form theoretical expression.
    - LITERATURE: value taken from the literature or a database (DOI/URL reference required).
    - FITTED    : parameter from an effect-fitting model (lmfit, scipy.curve_fit, etc.).
    """

    SIMULATED = "SIMULATED"
    MEASURED = "MEASURED"
    THEORY = "THEORY"
    LITERATURE = "LITERATURE"
    FITTED = "FITTED"


# Badge label mapping — the UI layer (report/) adds colour; this module provides labels only.
BADGE_LABEL: dict[ProvenanceType, str] = {
    ProvenanceType.SIMULATED: "SIM",
    ProvenanceType.MEASURED: "MEAS",
    ProvenanceType.THEORY: "PRED",
    ProvenanceType.LITERATURE: "LIT",
    ProvenanceType.FITTED: "FIT",
}

# Minimum allowed pattern for unit strings (rejects empty strings and whitespace-only strings).
_UNITS_RE = re.compile(r"\S")


class DataPoint(BaseModel):
    """Complete description of a single measurement, calculation, or literature value (§17).

    Every numerical value must be a ``DataPoint`` instance.  Bare ``float``
    values used directly in reports are blocked by ``HonestyGate``.

    Parameters
    ----------
    id:
        Unique identifier for the DataPoint (UUID4, auto-generated).
    value:
        The numerical value.  Either a ``float`` or a ``list[float]``
        (spectrum / array data).
    units:
        SI or domain unit string.  Use ``"1"`` or ``"dimensionless"`` for
        dimensionless quantities.
    uncertainty:
        Standard uncertainty (1σ).  ``None`` if not available.
    provenance_type:
        Origin classification (``ProvenanceType`` enum).  **Required** —
        construction is rejected if omitted.
    source_ref:
        Source reference: DOI, URL, file path, job ID, formula identifier, etc.
    timestamp:
        UTC ISO 8601.  Set automatically at construction time.
    conditions:
        Free-form dictionary of measurement/calculation conditions
        (temperature, applied field, simulation parameters, etc.).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    value: float | list[float]
    units: str
    uncertainty: float | None = None
    provenance_type: ProvenanceType
    source_ref: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    conditions: dict[str, Any] = Field(default_factory=dict)

    # DataPoint is immutable — create a new instance to change a value.
    # datetime is serialised to ISO 8601 automatically by pydantic v2 in
    # mode="json", so json_encoders is not needed.
    model_config = {"frozen": True}

    @field_validator("units")
    @classmethod
    def _units_not_blank(cls, v: str) -> str:
        """Reject blank or whitespace-only unit strings."""
        if not _UNITS_RE.search(v):
            raise ValueError(
                "units must not be blank or whitespace-only. "
                "Use '1' or 'dimensionless' for dimensionless quantities."
            )
        return v

    @field_validator("uncertainty")
    @classmethod
    def _uncertainty_non_negative(cls, v: float | None) -> float | None:
        """Uncertainty must not be negative."""
        if v is not None and v < 0:
            raise ValueError(f"uncertainty must be >= 0. Got: {v}")
        return v

    @model_validator(mode="after")
    def _literature_requires_source_ref(self) -> DataPoint:
        """LITERATURE type DataPoints must provide a ``source_ref`` (DOI, URL, etc.)."""
        if self.provenance_type is ProvenanceType.LITERATURE and not self.source_ref.strip():
            raise ValueError("LITERATURE DataPoints require a source_ref (DOI/URL).")
        return self

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    @property
    def badge(self) -> str:
        """Provenance badge label (e.g. '[SIM]', '[MEAS]')."""
        return f"[{BADGE_LABEL[self.provenance_type]}]"

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serialisable dictionary."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataPoint:
        """Reconstruct a ``DataPoint`` from a dictionary."""
        return cls.model_validate(data)

    def scalar(self) -> float:
        """Return ``value`` as a ``float`` when it is a scalar.

        Raises
        ------
        TypeError
            If ``value`` is a list.
        """
        if isinstance(self.value, list):
            raise TypeError("This DataPoint's value is an array. Access .value directly.")
        return float(self.value)
