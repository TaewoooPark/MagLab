"""Honest report builder — structured reports with provenance (§17).

Assembles DataPoints together with their provenance and lineage information
into a structured report.  **No visual styling (colours, badge styles)** —
only classification, structure, and text logic are handled here.
Colour and Rich styling are the responsibility of the UI layer in
``maglab/ui/render.py``.

Deterministic — no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..provenance.datapoint import DataPoint, ProvenanceType
from .honesty_gate import HonestyViolation, Violation, run_gate

# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------


@dataclass
class ReportEntry:
    """A report entry for a single DataPoint."""

    dp: DataPoint
    label: str = ""  # user-defined label (e.g. "saturation magnetisation")
    notes: str = ""  # additional notes

    @property
    def badge(self) -> str:
        """Provenance badge label (e.g. [SIM], [MEAS])."""
        return self.dp.badge

    def to_line(self) -> str:
        """Serialise to a single text line."""
        name = self.label or f"dp:{self.dp.id[:8]}"
        val = self.dp.value
        unc = f" ± {self.dp.uncertainty}" if self.dp.uncertainty is not None else ""
        ref = f" | ref: {self.dp.source_ref}" if self.dp.source_ref else ""
        cond = f" | cond: {self.dp.conditions}" if self.dp.conditions else ""
        return f"{self.badge} {name} = {val} {self.dp.units}{unc}{ref}{cond}"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a dictionary."""
        return {
            "badge": self.badge,
            "label": self.label,
            "id": self.dp.id,
            "value": self.dp.value,
            "units": self.dp.units,
            "uncertainty": self.dp.uncertainty,
            "provenance_type": self.dp.provenance_type.value,
            "source_ref": self.dp.source_ref,
            "timestamp": self.dp.timestamp.isoformat(),
            "conditions": self.dp.conditions,
            "notes": self.notes,
        }


@dataclass
class Report:
    """Structured report — a set of DataPoint entries with metadata.

    Parameters
    ----------
    title:
        Report title.
    entries:
        List of ``ReportEntry`` objects.
    narrative:
        Natural-language narrative (supplementary text that does not directly
        contain DataPoints).
    violations:
        Honesty Gate violation list (collected before passing the gate).
    metadata:
        Additional metadata dictionary.
    """

    title: str
    entries: list[ReportEntry] = field(default_factory=list)
    narrative: str = ""
    violations: list[Violation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed_gate(self) -> bool:
        """Whether the Honesty Gate was passed."""
        return len(self.violations) == 0

    def to_text(self) -> str:
        """Serialise to a human-readable text report."""
        lines: list[str] = []
        lines.append(f"{'=' * 60}")
        lines.append(f"Report: {self.title}")
        lines.append(f"{'=' * 60}")

        if self.entries:
            lines.append("")
            lines.append("▶ Data")
            for entry in self.entries:
                lines.append(f"  {entry.to_line()}")

        if self.narrative:
            lines.append("")
            lines.append("▶ Narrative")
            lines.append(f"  {self.narrative}")

        if self.metadata:
            lines.append("")
            lines.append("▶ Metadata")
            for k, v in self.metadata.items():
                lines.append(f"  {k}: {v}")

        if self.violations:
            lines.append("")
            lines.append("▶ Integrity violations")
            for v in self.violations:
                lines.append(f"  ✗ {v}")

        lines.append(f"{'=' * 60}")
        status = "PASSED" if self.passed_gate else f"BLOCKED ({len(self.violations)} violation(s))"
        lines.append(f"Integrity gate: {status}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a dictionary (JSON-serialisable)."""
        return {
            "title": self.title,
            "passed_gate": self.passed_gate,
            "entries": [e.to_dict() for e in self.entries],
            "narrative": self.narrative,
            "violations": [str(v) for v in self.violations],
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


class ReportBuilder:
    """Step-by-step builder for an honest report.

    Example usage::

        builder = ReportBuilder("Domain wall analysis results")
        builder.add(dp_sim, label="Domain wall width")
        builder.add(dp_lit, label="Literature reference", notes="Bloch, 1932")
        report = builder.build(run_honesty_gate=True)
        print(report.to_text())
    """

    def __init__(self, title: str) -> None:
        self._title = title
        self._entries: list[ReportEntry] = []
        self._narrative: str = ""
        self._metadata: dict[str, Any] = {}

    def add(
        self,
        dp: DataPoint,
        label: str = "",
        notes: str = "",
    ) -> ReportBuilder:
        """Add a DataPoint to the report."""
        self._entries.append(ReportEntry(dp=dp, label=label, notes=notes))
        return self

    def add_many(
        self,
        datapoints: list[DataPoint],
        labels: list[str] | None = None,
    ) -> ReportBuilder:
        """Add a list of DataPoints in bulk."""
        for idx, dp in enumerate(datapoints):
            label = labels[idx] if labels and idx < len(labels) else ""
            self.add(dp, label=label)
        return self

    def narrative(self, text: str) -> ReportBuilder:
        """Set the natural-language narrative section."""
        self._narrative = text
        return self

    def meta(self, key: str, value: Any) -> ReportBuilder:
        """Add a metadata key-value pair."""
        self._metadata[key] = value
        return self

    def build(
        self,
        run_honesty_gate: bool = True,
        raise_on_violation: bool = False,
        vault_ids: set[str] | None = None,
        verified_citations: set[str] | None = None,
    ) -> Report:
        """Build the report.

        Parameters
        ----------
        run_honesty_gate:
            If True, run the Honesty Gate and collect violations in
            ``Report.violations``.
        raise_on_violation:
            If True, raise ``HonestyViolation`` on any violation.
            Only effective when ``run_honesty_gate=True``.
        vault_ids:
            DataPoint ID vault (for out-of-vault reference checks).
        verified_citations:
            Set of verified citations.

        Returns
        -------
        Report
            The structured report.
        """
        violations: list[Violation] = []

        if run_honesty_gate and (self._narrative or self._entries):
            # Use registered DataPoint IDs as known_dp_ids
            known_ids: set[str] = {e.dp.id for e in self._entries}
            combined_text = self._narrative

            # Run Honesty Gate on the narrative text
            if combined_text.strip():
                try:
                    run_gate(
                        combined_text,
                        known_dp_ids=known_ids,
                        vault_ids=vault_ids,
                        verified_citations=verified_citations,
                        raise_on_violation=raise_on_violation,
                    )
                except HonestyViolation as exc:
                    violations.extend(exc.violations)

        return Report(
            title=self._title,
            entries=list(self._entries),
            narrative=self._narrative,
            violations=violations,
            metadata=dict(self._metadata),
        )


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def build_report(
    title: str,
    datapoints: list[DataPoint],
    labels: list[str] | None = None,
    narrative: str = "",
    run_honesty_gate: bool = True,
    raise_on_violation: bool = False,
    vault_ids: set[str] | None = None,
    verified_citations: set[str] | None = None,
) -> Report:
    """Build a report from a list of DataPoints in a single call.

    Parameters
    ----------
    title:
        Report title.
    datapoints:
        DataPoints to include.
    labels:
        Labels corresponding to each DataPoint (abbreviated ID used if absent).
    narrative:
        Natural-language narrative.
    run_honesty_gate:
        If True, run the Honesty Gate.
    raise_on_violation:
        If True, raise on violation.
    vault_ids:
        DataPoint vault set.
    verified_citations:
        Set of verified citations.
    """
    builder = ReportBuilder(title)
    builder.add_many(datapoints, labels=labels)
    if narrative:
        builder.narrative(narrative)
    return builder.build(
        run_honesty_gate=run_honesty_gate,
        raise_on_violation=raise_on_violation,
        vault_ids=vault_ids,
        verified_citations=verified_citations,
    )


def group_by_type(datapoints: list[DataPoint]) -> dict[ProvenanceType, list[DataPoint]]:
    """Group DataPoints by ``ProvenanceType``."""
    result: dict[ProvenanceType, list[DataPoint]] = {pt: [] for pt in ProvenanceType}
    for dp in datapoints:
        result[dp.provenance_type].append(dp)
    return result


def summarize_datapoints(datapoints: list[DataPoint]) -> dict[str, Any]:
    """Return summary statistics for a list of DataPoints.

    Only scalar DataPoints are aggregated.
    """
    by_type = group_by_type(datapoints)
    total = len(datapoints)
    scalar_dps = [dp for dp in datapoints if not isinstance(dp.value, list)]

    summary: dict[str, Any] = {
        "total": total,
        "by_type": {pt.value: len(lst) for pt, lst in by_type.items()},
        "scalar_count": len(scalar_dps),
        "array_count": total - len(scalar_dps),
    }

    if scalar_dps:
        import numpy as np

        values = [dp.scalar() for dp in scalar_dps]
        summary["scalar_stats"] = {
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        }

    return summary
