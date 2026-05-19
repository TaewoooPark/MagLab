"""Provenance Ledger — high-level recording API (§17).

Provides a high-level interface tailored to the research workflow on top of the
low-level PROV triple API of ``ProvenanceStore``.

- Registers DataPoints as Entities and links their lineage.
- Builds lineage chains (A → B → C) with a single call.
- Queries Entities by ID or condition.
- Deterministic — no LLM calls.
"""

from __future__ import annotations

import uuid
from typing import Any

from .datapoint import DataPoint, ProvenanceType
from .store import ProvenanceStore


class ProvenanceLedger:
    """High-level provenance recording API centred on DataPoints.

    Parameters
    ----------
    store:
        ``ProvenanceStore`` instance.  Injected externally (dependency
        injection).  If ``None``, an in-memory store is created automatically.
    """

    def __init__(self, store: ProvenanceStore | None = None) -> None:
        self._store: ProvenanceStore = store if store is not None else ProvenanceStore()
        # DataPoint ID → DataPoint cache (for in-memory lookups)
        self._cache: dict[str, DataPoint] = {}

    @property
    def store(self) -> ProvenanceStore:
        """Direct access to the underlying ``ProvenanceStore``."""
        return self._store

    # ------------------------------------------------------------------
    # DataPoint registration
    # ------------------------------------------------------------------

    def record_datapoint(
        self,
        dp: DataPoint,
        derived_from_ids: list[str] | None = None,
        activity_description: str = "",
    ) -> str:
        """Register a DataPoint as an Entity in the PROV document and cache it.

        Parameters
        ----------
        dp:
            The ``DataPoint`` to register.
        derived_from_ids:
            List of predecessor DataPoint IDs from which this DataPoint was derived.
        activity_description:
            Description of the activity that produced this DataPoint
            (e.g. 'exchange length calculation').

        Returns
        -------
        str
            The ``id`` of the DataPoint.
        """
        # 1) Register Entity
        self._store.add_entity(
            dp.id,
            attributes={
                "provenance_type": dp.provenance_type.value,
                "units": dp.units,
                "source_ref": dp.source_ref,
                "timestamp": dp.timestamp.isoformat(),
            },
        )

        # 2) Register generation Activity and link it
        if activity_description or derived_from_ids:
            act_id = f"act-{uuid.uuid4().hex[:8]}"
            self._store.add_activity(
                act_id,
                start_time=dp.timestamp,
                attributes={"description": activity_description or "DataPoint creation"},
            )
            self._store.was_generated_by(dp.id, act_id, time=dp.timestamp)

        # 3) Attribution
        self._store.was_attributed_to(dp.id)

        # 4) Derivation relationships
        if derived_from_ids:
            for parent_id in derived_from_ids:
                self._store.was_derived_from(dp.id, parent_id)

        # 5) In-memory cache
        self._cache[dp.id] = dp
        return dp.id

    # ------------------------------------------------------------------
    # LLM call recording (delegated)
    # ------------------------------------------------------------------

    def record_llm_call(
        self,
        model: str,
        prompt_summary: str,
        result_datapoint_id: str | None = None,
    ) -> str:
        """Record an LLM call as a first-class Activity.

        Returns
        -------
        str
            The local ID of the created Activity.
        """
        qn = self._store.record_llm_call(model, prompt_summary, result_datapoint_id)
        return str(qn)

    # ------------------------------------------------------------------
    # Lineage chain construction
    # ------------------------------------------------------------------

    def chain(self, *datapoints: DataPoint, activity_description: str = "") -> list[str]:
        """Register a sequence of DataPoints as a linear derivation chain.

        ``chain(a, b, c)`` → b is derived from a; c is derived from b.

        Parameters
        ----------
        *datapoints:
            DataPoints to link in order.
        activity_description:
            Activity description applied to the entire chain.

        Returns
        -------
        list[str]
            List of registered DataPoint IDs.
        """
        ids: list[str] = []
        for idx, dp in enumerate(datapoints):
            parent_ids = [ids[-1]] if idx > 0 else None
            self.record_datapoint(
                dp, derived_from_ids=parent_ids, activity_description=activity_description
            )
            ids.append(dp.id)
        return ids

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, dp_id: str) -> DataPoint | None:
        """Look up a DataPoint by ID (in-memory cache first)."""
        return self._cache.get(dp_id)

    def query_by_type(self, ptype: ProvenanceType) -> list[DataPoint]:
        """Filter DataPoints by ``provenance_type``."""
        return [dp for dp in self._cache.values() if dp.provenance_type is ptype]

    def query_by_units(self, units: str) -> list[DataPoint]:
        """Return DataPoints whose unit string matches exactly."""
        return [dp for dp in self._cache.values() if dp.units == units]

    def all_ids(self) -> list[str]:
        """Return the full list of registered DataPoint IDs."""
        return list(self._cache.keys())

    def lineage(self, dp_id: str) -> list[dict[str, Any]]:
        """Return the PROV lineage records for a DataPoint."""
        return self._store.get_entity_lineage(dp_id)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_json(self) -> dict[str, Any]:
        """Export the current PROV document as a JSON dictionary."""
        return self._store.export_json()

    def export_json_str(self) -> str:
        """Export the current PROV document as a JSON string."""
        return self._store.export_json_str()
