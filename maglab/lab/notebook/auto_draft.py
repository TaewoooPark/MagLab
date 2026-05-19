"""ELN auto-draft generation — automatic entry draft after analysis/fitting is complete (§13.5).

After analysis and fitting complete, automatically generates an ELNEntry as a draft
(is_draft=True).  The researcher edits and confirms it, then sets is_draft=False.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from maglab.lab.notebook.entry import (
    _TEMPLATES,
    ELNEntry,
    ELNNotebook,
    MeasurementType,
)

log = logging.getLogger(__name__)


def draft_from_fit_result(
    notebook: ELNNotebook,
    fit_result: dict[str, Any],
    *,
    sample: str = "",
    instrument: str = "",
    effect_name: str = "",
    datapoint_ids: list[str] | None = None,
    provenance_entity_ids: list[str] | None = None,
) -> ELNEntry:
    """Generate an automatic ELN entry draft from a fitting result.

    Parameters
    ----------
    notebook:
        ELNNotebook instance to store the entry in.
    fit_result:
        Dictionary returned by EffectModel.fit() or a similar function.
        Expected keys: params, chi2, r2, message, effect_name.
    sample:
        Sample ID.
    instrument:
        Instrument used.
    effect_name:
        Name of the effect model used for analysis.
    datapoint_ids:
        List of DataPoint IDs to link.
    provenance_entity_ids:
        List of provenance entity IDs to link.

    Returns
    -------
    ELNEntry
        Automatically generated draft entry with is_draft=True.
    """
    eff = fit_result.get("effect_name", effect_name) or "unspecified effect"
    params = fit_result.get("params", {})
    chi2 = fit_result.get("chi2", "N/A")
    r2 = fit_result.get("r2", "N/A")
    message = fit_result.get("message", "")

    # Parameter table
    param_lines = []
    for k, v in params.items() if isinstance(params, dict) else {}.items():
        param_lines.append(f"- {k}: {v}")
    params_block = "\n".join(param_lines) if param_lines else "- (no parameters)"

    dp_refs = "\n".join(f"- {dp}" for dp in (datapoint_ids or [])) or "- (none)"

    body = f"""\
## Auto-Draft — {eff} Fitting Result

> **Note**: This entry is an automatic draft. Please review and edit the content,
> then set is_draft to false when confirmed.

### Analysis Summary
- Effect model: {eff}
- χ²: {chi2}
- R²: {r2}
{f"- Message: {message}" if message else ""}

### Fitting Parameters
{params_block}

### DataPoint Links
{dp_refs}

### Researcher Notes (write here directly)

"""

    title = f"[Auto-Draft] {eff} Fitting — {date.today().isoformat()}"
    tags = ["auto-draft", "fitting"]
    if eff:
        tags.append(eff.replace(" ", "_"))

    mtype = _infer_measurement_type(eff)
    # Build the entry with the correct title before any write so the entry is
    # persisted exactly once with the right title.  Prepend the measurement-type
    # template the same way create_entry() would, keeping body content identical.
    entry = ELNEntry(
        date=date.today(),
        title=title,
        sample=sample,
        instrument=instrument,
        measurement_type=mtype,
        tags=tags,
        datapoint_ids=datapoint_ids or [],
        body=_TEMPLATES.get(mtype, "") + "\n" + body,
        provenance_entity_ids=provenance_entity_ids or [],
        is_draft=True,
    )
    notebook.save_entry(entry)

    log.info("[ELN auto-draft] Entry created: entry_id=%s", entry.entry_id)
    return entry


def _infer_measurement_type(effect_name: str) -> MeasurementType:
    """Infer measurement type from effect name."""
    name_lower = effect_name.lower()
    if any(k in name_lower for k in ["fmr", "damping", "kittel"]):
        return MeasurementType.FMR
    if any(k in name_lower for k in ["hall", "transport", "smr", "sot", "amr"]):
        return MeasurementType.MAGNETOTRANSPORT
    if "moke" in name_lower:
        return MeasurementType.MOKE
    if any(k in name_lower for k in ["vsm", "hysteresis", "magnetization"]):
        return MeasurementType.VSM
    return MeasurementType.GENERAL
