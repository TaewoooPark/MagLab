"""F6 data→simulation→figure integrated pipeline (§10.3).

Design rationale: plan/03-physics-simulation.md §10.3 · impl/02-P1-figure-sim.md T-P1-18.

Core logic for ``maglab sim plot <data>`` CLI:
  1. Load experimental data (CSV etc.) → tag as DataPoints (ProvenanceType.MEASURED).
  2. Infer experiment type (PlotKind) from column names.
  3. Build FigureSpec → render with DataPlotRenderer.
  4. Optional simulation overlay: SimSpec → validate → run → parse → tag as
     simulation DataPoints (ProvenanceType.SIMULATED) → insert into FigureSpec overlay field.

Verifiable orchestrator principles (§3):
  - Figure data is bound to DataPoints.
  - Simulation results use ProvenanceType.SIMULATED.
  - LLM-free deterministic path.
  - No raster generative image model calls.

Graceful handling when external solvers (OOMMF/MuMax3) are not installed
(plots data only without simulation).
"""

from __future__ import annotations

import contextlib
import csv
import uuid
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

from maglab.figure.compose import FigureComposer
from maglab.figure.export import FigureExporter
from maglab.figure.spec import (
    AxisSpec,
    ColumnWidth,
    FigureSpec,
    GridLayout,
    GridPosition,
    JournalTarget,
    PanelSpec,
    PanelType,
    PlotKind,
)
from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# Exported public symbols
# ---------------------------------------------------------------------------

__all__ = [
    "load_csv_datapoints",
    "infer_plot_kind",
    "build_figure_spec",
    "render_data_figure",
    "run_sim_overlay",
    "plot_data_to_figure",
]


# ---------------------------------------------------------------------------
# CSV loading — DataPoint tagging
# ---------------------------------------------------------------------------


def load_csv_datapoints(
    path: str | Path,
    source_ref: str = "",
    conditions: dict[str, Any] | None = None,
) -> dict[str, DataPoint]:
    """Load per-column DataPoints from a CSV file and return as a dictionary.

    Each column becomes one DataPoint (value=list[float]).
    Units are extracted from parenthetical notation in the header
    (e.g. ``"H (T)"``); missing units default to ``"1"``.

    Parameters:
        path: CSV file path.
        source_ref: Source reference. Uses the absolute file path if empty.
        conditions: DataPoint conditions dictionary (temperature, external field, etc.).

    Returns:
        Dictionary of ``{base column name: DataPoint}``.

    Raises:
        FileNotFoundError: When the file does not exist.
        ValueError: When the CSV has only a header and no data.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    if not source_ref:
        source_ref = str(path.resolve())

    cond = conditions or {}

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"Cannot read CSV header: {path}")

        raw_cols: dict[str, list[float]] = {h: [] for h in reader.fieldnames}
        for row in reader:
            for header in reader.fieldnames:
                val_str = row.get(header, "").strip()
                with contextlib.suppress(ValueError):
                    raw_cols[header].append(float(val_str))

    if all(len(v) == 0 for v in raw_cols.values()):
        raise ValueError(f"CSV contains no numeric data: {path}")

    result: dict[str, DataPoint] = {}
    for header, values in raw_cols.items():
        if not values:
            continue
        col_name, units = _parse_header(header)
        dp = DataPoint(
            value=values,
            units=units,
            provenance_type=ProvenanceType.MEASURED,
            source_ref=source_ref,
            conditions=cond,
        )
        result[col_name] = dp

    return result


def _parse_header(header: str) -> tuple[str, str]:
    """Split name and units from a header in the form ``"H (T)"``.

    Returns:
        (normalized column name, unit).
    """
    header = header.strip()
    if "(" in header and header.endswith(")"):
        name_part, unit_part = header.rsplit("(", 1)
        col_name = name_part.strip().lower().replace(" ", "_")
        units = unit_part.rstrip(")").strip() or "1"
    else:
        col_name = header.strip().lower().replace(" ", "_")
        units = "1"
    return col_name, units


# ---------------------------------------------------------------------------
# Experiment type inference
# ---------------------------------------------------------------------------


def infer_plot_kind(col_names: list[str]) -> PlotKind:
    """Infer the experiment type (PlotKind) from a set of column names.

    Inference priority:
      1. ``hall``/``rho_xy``/``ρ_xy`` → HALL.
      2. ``fmr``/``fmr_signal``/``absorption`` → FMR.
      3. ``dispersion``/``omega``/``frequency`` together with ``k``/``wavevector`` → DISPERSION.
      4. ``m``/``mx``/``my``/``mz``/``magnetization``/``hysteresis`` → HYSTERESIS.
      5. Otherwise → XY.

    Parameters:
        col_names: List of normalized column names.

    Returns:
        PlotKind.
    """
    names = {n.lower() for n in col_names}

    # Hall
    if any(k in names for k in ("hall", "rho_xy", "ρ_xy", "rxy", "anomalous_hall")):
        return PlotKind.HALL

    # FMR
    if any(k in names for k in ("fmr", "fmr_signal", "absorption", "derivative_absorption")):
        return PlotKind.FMR

    # Dispersion
    has_freq = any(k in names for k in ("omega", "frequency", "freq", "dispersion"))
    has_k = any(k in names for k in ("k", "wavevector", "k_vector", "k_nm"))
    if has_freq and has_k:
        return PlotKind.DISPERSION

    # Hysteresis
    if any(
        k in names for k in ("m", "mx", "my", "mz", "magnetization", "hysteresis", "normalized_m")
    ):
        return PlotKind.HYSTERESIS

    return PlotKind.XY


# ---------------------------------------------------------------------------
# FigureSpec construction
# ---------------------------------------------------------------------------


def build_figure_spec(
    col_dps: dict[str, DataPoint],
    plot_kind: PlotKind | None = None,
    journal: JournalTarget = JournalTarget.NATURE,
    column_width: ColumnWidth = ColumnWidth.SINGLE,
    caption: str = "",
    sim_dp_ids: list[str] | None = None,
) -> FigureSpec:
    """Build a single-panel FigureSpec from a DataPoint dictionary.

    Automatically selects x/y columns and inserts overlay (simulation) DataPoint IDs.
    DataPoints must be bound; PanelSpec blocks unbound panels.

    Parameters:
        col_dps: Dictionary of ``{column name: DataPoint}``.
        plot_kind: Plot type. Inferred from col_dps if None.
        journal: Journal target.
        column_width: Single or double column.
        caption: Figure caption.
        sim_dp_ids: List of simulation overlay DataPoint IDs.

    Returns:
        FigureSpec.
    """
    col_names = list(col_dps.keys())
    if not col_names:
        raise ValueError("DataPoint is empty. Load data from CSV first.")

    kind = plot_kind or infer_plot_kind(col_names)

    # x/y column selection
    x_col, y_col = _select_xy_cols(col_names, kind)

    x_dp = col_dps.get(x_col)
    y_dp = col_dps.get(y_col)

    if x_dp is None or y_dp is None:
        # Fall back to first two columns when x column is missing
        first, second = (col_names + [col_names[0]])[:2]
        x_dp = col_dps[first]
        y_dp = col_dps.get(second, x_dp)
        x_col, y_col = first, second

    dp_ids = [x_dp.id, y_dp.id]

    x_label = _axis_label(x_col, x_dp.units)
    y_label = _axis_label(y_col, y_dp.units)

    panel = PanelSpec(
        panel_id="p1",
        panel_type=PanelType.DATA_PLOT,
        plot_kind=kind,
        data_point_ids=dp_ids,
        grid_position=GridPosition(row=0, col=0),
        x_axis=AxisSpec(label=x_label),
        y_axis=AxisSpec(label=y_label),
        overlay=sim_dp_ids or [],
    )

    return FigureSpec(
        figure_id=str(uuid.uuid4()),
        journal=journal,
        column_width=column_width,
        panels=[panel],
        layout=GridLayout(nrows=1, ncols=1),
        caption=caption,
    )


def _select_xy_cols(col_names: list[str], kind: PlotKind) -> tuple[str, str]:
    """Select x/y columns according to plot type."""
    names = list(col_names)
    if len(names) == 1:
        return names[0], names[0]

    # Preferred x column names per plot type
    x_candidates: dict[PlotKind, list[str]] = {
        PlotKind.HYSTERESIS: ["h", "b", "field", "mu0h", "h_t"],
        PlotKind.HALL: ["h", "b", "field", "mu0h", "h_t"],
        PlotKind.FMR: ["h", "field", "h_res"],
        PlotKind.DISPERSION: ["k", "wavevector", "k_vector", "k_nm"],
        PlotKind.XY: [],
    }
    y_candidates: dict[PlotKind, list[str]] = {
        PlotKind.HYSTERESIS: ["m", "mx", "my", "mz", "magnetization", "normalized_m"],
        PlotKind.HALL: ["hall", "rho_xy", "ρ_xy", "rxy"],
        PlotKind.FMR: ["fmr", "fmr_signal", "absorption", "derivative_absorption"],
        PlotKind.DISPERSION: ["omega", "frequency", "freq"],
        PlotKind.XY: [],
    }

    x_col = _pick(names, x_candidates.get(kind, []))
    y_col = _pick([n for n in names if n != x_col], y_candidates.get(kind, []))

    if x_col is None:
        x_col = names[0]
    if y_col is None:
        remaining = [n for n in names if n != x_col]
        y_col = remaining[0] if remaining else x_col

    return x_col, y_col


def _pick(candidates: list[str], preferred: list[str]) -> str | None:
    """Find and return the first item from the preferred list that exists in candidates."""
    for pref in preferred:
        for c in candidates:
            if pref in c or c in pref:
                return c
    return None


def _axis_label(col_name: str, units: str) -> str:
    """Generate an axis label from column name and units."""
    if units and units != "1":
        return f"{col_name} ({units})"
    return col_name


# ---------------------------------------------------------------------------
# Data figure rendering
# ---------------------------------------------------------------------------


def render_data_figure(
    spec: FigureSpec,
    ledger: dict[str, DataPoint],
    output_path: str | Path,
    fmt: str = "pdf",
    journal: JournalTarget = JournalTarget.NATURE,
) -> Path:
    """Render and export a vector figure from a FigureSpec and DataPoint ledger.

    Parameters:
        spec: FigureSpec IR.
        ledger: DataPoint ID → DataPoint lookup dictionary.
        output_path: Output file path.
        fmt: Export format ('pdf'/'svg'/'eps').
        journal: Journal target (for StyleProfile selection).

    Returns:
        Path to the saved file.
    """
    composer = FigureComposer()
    exporter = FigureExporter()

    fig = composer.compose(spec, ledger)
    out = exporter.export(fig, output_path, fmt=fmt)  # type: ignore[arg-type]

    import matplotlib.pyplot as plt

    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Simulation overlay (optional)
# ---------------------------------------------------------------------------


def run_sim_overlay(
    spec_dict: dict[str, Any],
) -> list[DataPoint]:
    """Run a simulation from a SimSpec dictionary and return the resulting DataPoint list.

    Returns an empty list with only a warning when external solvers are not installed
    (graceful degradation).

    Parameters:
        spec_dict: MultiScaleSpec serialized dictionary.

    Returns:
        List of simulation-result DataPoints (ProvenanceType.SIMULATED).
    """
    try:
        from maglab.sim.spec import MultiScaleSpec
        from maglab.sim.validate import validate
    except ImportError:
        warnings.warn("Cannot load sim module. Skipping simulation overlay.", stacklevel=2)
        return []

    try:
        multi_spec = MultiScaleSpec.model_validate(spec_dict)
    except Exception as exc:
        warnings.warn(
            f"SimSpec validation failed: {exc}. Skipping simulation overlay.", stacklevel=2
        )
        return []

    try:
        validate(multi_spec)
    except Exception as exc:
        warnings.warn(
            f"SimSpec static validation failed: {exc}. Skipping simulation overlay.",
            stacklevel=2,
        )
        return []

    # Attempt backend execution
    scale_spec = multi_spec.single_scale_spec()
    engine = scale_spec.engine

    try:
        return _run_backend(scale_spec, engine)
    except Exception as exc:
        warnings.warn(
            f"Simulation run failed (engine={engine}): {exc}. Skipping simulation overlay.",
            stacklevel=2,
        )
        return []


def _run_backend(scale_spec: Any, engine: str) -> list[DataPoint]:
    """Run a single ScaleSpec against a backend and return the DataPoint list."""
    from maglab.sim.spec import ScaleType

    if scale_spec.scale != ScaleType.micro:
        warnings.warn(
            f"scale={scale_spec.scale} does not support simulation overlay in P1.",
            stacklevel=3,
        )
        return []

    # Auto-select engine
    if engine == "auto":
        engine = _detect_available_engine()

    if engine == "magnumnp":
        return _run_magnumnp(scale_spec)
    elif engine == "oommf":
        return _run_oommf(scale_spec)
    elif engine == "mumax3":
        return _run_mumax3(scale_spec)
    else:
        warnings.warn(f"Unknown engine: {engine}. Skipping simulation overlay.", stacklevel=3)
        return []


def _detect_available_engine() -> str:
    """Auto-detect an installed micromagnetic solver engine."""
    import shutil

    if shutil.which("mumax3"):
        return "mumax3"
    if shutil.which("oommf") or shutil.which("tclsh"):
        return "oommf"
    try:
        import magnumnp  # type: ignore[import-untyped]  # noqa: F401

        return "magnumnp"
    except ImportError:
        pass
    raise RuntimeError(
        "No micromagnetic solver available (MuMax3·OOMMF·magnum.np). "
        "Plotting data only without a simulation overlay."
    )


def _run_magnumnp(scale_spec: Any) -> list[DataPoint]:
    """Run a simulation with magnum.np and return the DataPoint list."""
    try:
        from maglab.sim.micro.magnumnp import run as mnp_run
    except ImportError as exc:
        raise RuntimeError(f"Failed to import magnum.np wrapper: {exc}") from exc

    job_result = mnp_run(scale_spec)
    return _extract_sim_datapoints(job_result)


def _run_oommf(scale_spec: Any) -> list[DataPoint]:
    """Run a simulation with OOMMF and return the DataPoint list."""
    try:
        from maglab.sim.micro.oommf import run as oommf_run
    except ImportError as exc:
        raise RuntimeError(f"Failed to import OOMMF wrapper: {exc}") from exc

    job_result = oommf_run(scale_spec)
    return _extract_sim_datapoints(job_result)


def _run_mumax3(scale_spec: Any) -> list[DataPoint]:
    """Run a simulation with MuMax3 and return the DataPoint list."""
    try:
        from maglab.sim.micro.mumax3 import run as mumax_run
    except ImportError as exc:
        raise RuntimeError(f"Failed to import MuMax3 wrapper: {exc}") from exc

    job_result = mumax_run(scale_spec)
    return _extract_sim_datapoints(job_result)


def _extract_sim_datapoints(job_result: Any) -> list[DataPoint]:
    """Flatten a JobResult into a DataPoint list."""
    dps: list[DataPoint] = []
    for qty_dps in job_result.quantities.values():
        dps.extend(qty_dps)
    return dps


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


def plot_data_to_figure(
    data_path: str | Path,
    output_path: str | Path | None = None,
    journal: JournalTarget = JournalTarget.NATURE,
    column_width: ColumnWidth = ColumnWidth.SINGLE,
    fmt: str = "pdf",
    sim_spec_dict: dict[str, Any] | None = None,
    caption: str = "",
    source_ref: str = "",
    conditions: dict[str, Any] | None = None,
) -> tuple[Path, FigureSpec, dict[str, DataPoint]]:
    """F6 integrated pipeline: load data → build FigureSpec → render → export vector figure.

    This is the core logic of the ``maglab sim plot <data>`` CLI.

    Parameters:
        data_path: CSV experimental data file path.
        output_path: Output file path. Defaults to data_path with a .pdf extension if None.
        journal: Journal target.
        column_width: Single or double column.
        fmt: Export format ('pdf'·'svg'·'eps').
        sim_spec_dict: MultiScaleSpec serialized dictionary for simulation overlay. Data-only if None.
        caption: Figure caption. Auto-generated if empty.
        source_ref: Data source reference.
        conditions: DataPoint conditions dictionary.

    Returns:
        (saved file path, FigureSpec, DataPoint ledger dictionary).

    Raises:
        FileNotFoundError: When data_path does not exist.
        ValueError: When the CSV contains no numeric data.
    """
    data_path = Path(data_path)

    # 1. Load experimental data → tag as DataPoints
    col_dps = load_csv_datapoints(data_path, source_ref=source_ref, conditions=conditions)

    # Build DataPoint ledger (ID → DataPoint)
    ledger: dict[str, DataPoint] = {dp.id: dp for dp in col_dps.values()}

    # 2. Infer experiment type
    plot_kind = infer_plot_kind(list(col_dps.keys()))

    # 3. Optional simulation overlay
    sim_dp_ids: list[str] = []
    if sim_spec_dict is not None:
        sim_dps = run_sim_overlay(sim_spec_dict)
        for sdp in sim_dps:
            ledger[sdp.id] = sdp
            sim_dp_ids.append(sdp.id)

    # 4. Auto-generate caption
    if not caption:
        badge = "MEAS"
        sim_badge = f" + SIM({len(sim_dp_ids)} DataPoint)" if sim_dp_ids else ""
        caption = (
            f"[{badge}]{sim_badge} "
            f"Data source: {source_ref or str(data_path)} | "
            f"Journal: {journal.value} | Format: {fmt}"
        )

    # 5. Build FigureSpec
    spec = build_figure_spec(
        col_dps=col_dps,
        plot_kind=plot_kind,
        journal=journal,
        column_width=column_width,
        caption=caption,
        sim_dp_ids=sim_dp_ids,
    )

    # 6. Output path
    if output_path is None:
        output_path = data_path.with_suffix(f".{fmt}")
    output_path = Path(output_path)

    # 7. Render → export
    saved_path = render_data_figure(
        spec=spec,
        ledger=ledger,
        output_path=output_path,
        fmt=fmt,
        journal=journal,
    )

    return saved_path, spec, ledger
