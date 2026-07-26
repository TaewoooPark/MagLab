"""Data load/save — CSV/HDF5 ↔ DataPoint[].

Reads CSV (pandas) or HDF5 and returns DataPoint[], and writes fitting
result DataPoints to files. Raw data is never modified (only MEASURED type is loaded).

Design basis: plan/04-analysis.md §11, impl/03-P2-analysis.md T-P2-04
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from maglab.core.atomic import atomic_write_text
from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# CSV load
# ---------------------------------------------------------------------------


def load_csv(
    path: str | Path,
    column_map: dict[str, str] | None = None,
    source_ref: str = "",
    conditions: dict[str, Any] | None = None,
    units_map: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[DataPoint]]:
    """Read a CSV file and return a DataFrame and DataPoint[].

    Args:
        path: CSV file path.
        column_map: {original column: standard column} renaming map (optional).
        source_ref: Data source reference (file path, experiment ID, etc.).
        conditions: Measurement conditions dictionary (temperature, external field, etc.).
        units_map: {column: unit string} (optional). Defaults to 'dimensionless'.

    Returns:
        (DataFrame, DataPoint list) tuple.
        The DataFrame is the original data (unchanged).
        Each column's entire array is returned as a single DataPoint
        (not one DataPoint per row×column).
    """
    file_path = Path(path)
    df = pd.read_csv(file_path)

    if column_map:
        df = df.rename(columns=column_map)

    _source = source_ref or str(file_path)
    _cond = conditions or {}
    _units = units_map or {}

    datapoints: list[DataPoint] = []
    for col in df.columns:
        unit = _units.get(col, "dimensionless")
        try:
            values = df[col].dropna().tolist()
            dp = DataPoint(
                value=values if len(values) != 1 else values[0],
                units=unit,
                provenance_type=ProvenanceType.MEASURED,
                source_ref=_source,
                conditions={**_cond, "column": col},
            )
            datapoints.append(dp)
        except Exception:
            pass  # Skip columns that cannot be converted to numeric

    return df, datapoints


# ---------------------------------------------------------------------------
# HDF5 load
# ---------------------------------------------------------------------------


def load_hdf5(
    path: str | Path,
    key: str = "data",
    source_ref: str = "",
    conditions: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, list[DataPoint]]:
    """Read an HDF5 file and return a DataFrame and DataPoint[].

    Args:
        path: HDF5 file path.
        key: HDF5 key (default "data").
        source_ref: Source reference.
        conditions: Measurement conditions.

    Returns:
        (DataFrame, DataPoint list) tuple.
    """
    file_path = Path(path)
    df = pd.read_hdf(str(file_path), key=key)
    _source = source_ref or str(file_path)
    _cond = conditions or {}

    datapoints: list[DataPoint] = []
    for col in df.columns:
        try:
            values = df[col].dropna().tolist()
            dp = DataPoint(
                value=values if len(values) != 1 else values[0],
                units="dimensionless",
                provenance_type=ProvenanceType.MEASURED,
                source_ref=_source,
                conditions={**_cond, "column": col},
            )
            datapoints.append(dp)
        except Exception:
            pass

    return df, datapoints


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_csv(
    df: pd.DataFrame,
    path: str | Path,
    fit_datapoints: list[DataPoint] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save a DataFrame as CSV and record fitting DataPoints to a sidecar JSON.

    Raw data immutability principle: no columns are added to the original df.
    Fitting results are saved separately to {basename}_fit_provenance.json.

    Args:
        df: DataFrame to save.
        path: Save path.
        fit_datapoints: List of fitting result DataPoints (optional).
        metadata: Additional metadata (optional).
    """
    file_path = Path(path)
    df.to_csv(file_path, index=False)

    if fit_datapoints or metadata:
        prov_path = file_path.with_name(file_path.stem + "_fit_provenance.json")
        prov_data: dict[str, Any] = {
            "source_csv": str(file_path),
            "metadata": metadata or {},
            "fit_datapoints": [dp.to_dict() for dp in (fit_datapoints or [])],
        }
        atomic_write_text(prov_path, json.dumps(prov_data, indent=2, default=str))


def load_fit_provenance(path: str | Path) -> list[DataPoint]:
    """Restore a list of fitting DataPoints from the sidecar fit_provenance.json."""
    prov_path = Path(path)
    if not prov_path.exists():
        return []
    data = json.loads(prov_path.read_text(encoding="utf-8"))
    dps = []
    for d in data.get("fit_datapoints", []):
        with contextlib.suppress(Exception):
            dps.append(DataPoint.from_dict(d))
    return dps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def dataframe_to_arrays(
    df: pd.DataFrame,
    columns: list[str],
) -> dict[str, np.ndarray]:
    """Extract specified columns from a DataFrame as a numpy array dictionary.

    Args:
        df: Source DataFrame.
        columns: List of column names to extract.

    Returns:
        {column: np.ndarray} dictionary.

    Raises:
        KeyError: When required columns are missing.
    """
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise KeyError(
            f"Required columns not found: {missing}. Available columns: {list(df.columns)}"
        )
    return {col: df[col].to_numpy(dtype=float) for col in columns}
