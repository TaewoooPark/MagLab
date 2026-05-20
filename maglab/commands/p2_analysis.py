"""P2 analysis CLI commands — fit, analyze, device.

Wires the real P2 analysis implementations to the CLI surface:
  - ``maglab fit --effect <name> <data>``  : effect-fitting registry
  - ``maglab analyze load|model|consistency|symmetry``  : analysis sub-app
  - ``maglab device fom <device-spec>``    : device figure-of-merit

Heavy optional dependencies (lmfit, numpy-heavy analysis stack) are imported
lazily inside command callbacks so that ``maglab --help`` works without the
[fit] / [analysis] extras installed.

Design basis: plan/04-analysis.md §11, plan/11-appendices.md Appendix A,
              impl/03-P2-analysis.md T-P2-08
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Typer apps
# ---------------------------------------------------------------------------

analyze_app = typer.Typer(
    name="analyze",
    help="[P2] Modeling and fitting analysis (load · model · consistency · symmetry).",
    no_args_is_help=True,
)

device_app = typer.Typer(
    name="device",
    help="[P2] Device figure-of-merit registry (maglab device fom <spec>).",
    no_args_is_help=True,
)

console = Console()

# ---------------------------------------------------------------------------
# Module-level singletons for typer.Argument / typer.Option defaults
# (satisfies ruff B008 — avoids function calls in argument defaults)
# ---------------------------------------------------------------------------

_FIT_EFFECT_OPT = typer.Option(
    ...,
    "--effect",
    "-e",
    help="Effect name (e.g. anomalous_hall, fmr_kittel, stfmr). "
    "Pass 'list' to see all registered effects.",
)
_FIT_DATA_ARG = typer.Argument(..., help="CSV data file path.")
_FIT_GEO_OPT = typer.Option(
    None,
    "--geometry",
    "-g",
    help="Measurement geometry JSON string (optional, effect-specific).",
)
_FIT_METHOD_OPT = typer.Option(
    "leastsq",
    "--method",
    "-m",
    help="lmfit minimisation method (leastsq · least_squares · nelder).",
)
_FIT_DISCOVER_OPT = typer.Option(
    False,
    "--discover",
    help=(
        "Run the deterministic bilevel inner loop: use the selected effect model form, "
        "multi-start initial values, and report AIC/BIC. No LLM proposes numbers."
    ),
)
_FIT_INIT_GRID_OPT = typer.Option(
    None,
    "--init-grid",
    help="JSON initial-value grid for --discover, e.g. '{\"R_H\":[-1e-10,0,1e-10]}'.",
)
_FIT_MAX_ATTEMPTS_OPT = typer.Option(
    10,
    "--max-attempts",
    help="Maximum deterministic inner-loop attempts for --discover.",
)
_FIT_X_COL_OPT = typer.Option(
    None,
    "--x-col",
    help="Independent-variable column for --discover. Defaults to the first required column.",
)
_FIT_Y_COL_OPT = typer.Option(
    None,
    "--y-col",
    help="Dependent-variable column for --discover. Defaults to the last required column.",
)
_FIT_REFS_OPT = typer.Option(False, "--refs", help="Print primary literature references.")

_LOAD_DATA_ARG = typer.Argument(..., help="CSV or HDF5 data file path.")
_LOAD_FMT_OPT = typer.Option("csv", "--format", "-f", help="File format (csv · hdf5).")
_LOAD_COLS_OPT = typer.Option(
    None,
    "--columns",
    "-c",
    help="Comma-separated column list to display (all if omitted).",
)

_MODEL_EFFECT_ARG = typer.Argument(
    None,
    help="Effect name to describe. Omit to list all models.",
)

_CONS_EFFECT_A_ARG = typer.Argument(..., help="First effect name (already fitted).")
_CONS_DATA_A_ARG = typer.Argument(..., help="CSV file for the first effect.")
_CONS_EFFECT_B_ARG = typer.Argument(..., help="Second effect name (already fitted).")
_CONS_DATA_B_ARG = typer.Argument(..., help="CSV file for the second effect.")
_CONS_CHI2_OPT = typer.Option(
    True,
    "--chi2/--no-chi2",
    help="Also check reduced chi² range for each fit.",
)

_SYM_GROUP_ARG = typer.Argument(
    ...,
    help="Magnetic point group label (e.g. m3m, 4/mmm, mm2, 2/m, -1, 6/mmm).",
)
_SYM_LIST_OPT = typer.Option(
    False,
    "--list",
    "-l",
    help="List all supported magnetic point groups instead.",
)

_DEV_DEVICE_ARG = typer.Argument(
    ...,
    help="Device type (sot-mram · stt-mram · racetrack). Pass 'list' to see all.",
)
_DEV_MS_OPT = typer.Option(None, "--Ms", help="Saturation magnetisation [A/m].")
_DEV_T_FM_OPT = typer.Option(None, "--t", "--t-fm", help="FM layer thickness [m].")
_DEV_KU_OPT = typer.Option(None, "--Ku", help="PMA anisotropy constant [J/m³].")
_DEV_ALPHA_OPT = typer.Option(None, "--alpha", help="Gilbert damping constant.")
_DEV_THETA_SH_OPT = typer.Option(None, "--theta-sh", help="Spin Hall angle θ_SH.")
_DEV_TEMP_OPT = typer.Option(None, "--T", "--temp", help="Temperature [K] (default 300).")
_DEV_DBIT_OPT = typer.Option(None, "--d-bit", help="Bit cell diameter [m].")
_DEV_P_OPT = typer.Option(None, "--P", help="Spin polarisation (STT-MRAM).")
_DEV_TMR_OPT = typer.Option(None, "--TMR", help="TMR ratio (STT-MRAM).")
_DEV_JDRIVE_OPT = typer.Option(None, "--j-drive", help="Drive current density (racetrack) [A/m²].")
_DEV_REFS_OPT = typer.Option(False, "--refs", help="Print primary literature references.")

# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
    """Attach P2 analysis commands to the root maglab app."""
    app.add_typer(analyze_app)
    app.add_typer(device_app)
    app.command("fit")(_make_fit_command())


def _make_fit_command():
    """Build a fresh Typer command so tests can register P2 on multiple apps."""

    def command(
        effect: Annotated[
            str,
            typer.Option(
                "--effect",
                "-e",
                help="Effect name (e.g. anomalous_hall, fmr_kittel, stfmr). "
                "Pass 'list' to see all registered effects.",
            ),
        ],
        data: Annotated[Path, typer.Argument(help="CSV data file path.")],
        geometry: Annotated[
            str | None,
            typer.Option(
                "--geometry",
                "-g",
                help="Measurement geometry JSON string (optional, effect-specific).",
            ),
        ] = None,
        method: Annotated[
            str,
            typer.Option(
                "--method",
                "-m",
                help="lmfit minimisation method (leastsq · least_squares · nelder).",
            ),
        ] = "leastsq",
        discover: Annotated[
            bool,
            typer.Option(
                "--discover",
                help=(
                    "Run the deterministic bilevel inner loop: use the selected effect model form, "
                    "multi-start initial values, and report AIC/BIC. No LLM proposes numbers."
                ),
            ),
        ] = False,
        init_grid_json: Annotated[
            str | None,
            typer.Option(
                "--init-grid",
                help="JSON initial-value grid for --discover, e.g. '{\"R_H\":[-1e-10,0,1e-10]}'.",
            ),
        ] = None,
        max_attempts: Annotated[
            int,
            typer.Option(
                "--max-attempts",
                help="Maximum deterministic inner-loop attempts for --discover.",
            ),
        ] = 10,
        x_col: Annotated[
            str | None,
            typer.Option(
                "--x-col",
                help="Independent-variable column for --discover. Defaults to the first required column.",
            ),
        ] = None,
        y_col: Annotated[
            str | None,
            typer.Option(
                "--y-col",
                help="Dependent-variable column for --discover. Defaults to the last required column.",
            ),
        ] = None,
        show_refs: Annotated[
            bool,
            typer.Option("--refs", help="Print primary literature references."),
        ] = False,
    ) -> None:
        fit_command(
            effect=effect,
            data=data,
            geometry=geometry,
            method=method,
            discover=discover,
            init_grid_json=init_grid_json,
            max_attempts=max_attempts,
            x_col=x_col,
            y_col=y_col,
            show_refs=show_refs,
        )

    command.__name__ = "fit_command"
    command.__doc__ = fit_command.__doc__
    return command


# ===========================================================================
# maglab fit
# ===========================================================================


def fit_command(
    effect: str,
    data: Path,
    geometry: str | None = None,
    method: str = "leastsq",
    discover: bool = False,
    init_grid_json: str | None = None,
    max_attempts: int = 10,
    x_col: str | None = None,
    y_col: str | None = None,
    show_refs: bool = False,
) -> None:
    """[P2] Fit a known effect model to experimental data.

    Examples:
        maglab fit --effect anomalous_hall data.csv
        maglab fit --effect fmr_kittel kittel.csv --method least_squares
        maglab fit --discover --effect ordinary_hall hall.csv --init-grid '{"R_H":[-1e-10,0,1e-10]}'
        maglab fit --effect list
    """
    # ---- special case: list all effects ----
    if effect.lower() in ("list", "ls", "--list"):
        _print_effect_list()
        return

    # ---- lazy imports ----
    try:
        from maglab.analysis.providers import get_all_effects, get_effect
    except ImportError as exc:
        console.print(f"[red]Required package not installed:[/] {exc}")
        console.print("  Install with: pip install 'maglab[analysis]'")
        raise typer.Exit(1) from exc

    # ---- resolve effect model ----
    try:
        model = get_effect(effect)
    except KeyError:
        all_effects = get_all_effects()
        console.print(f"[red]Unknown effect:[/] {effect!r}")
        console.print(f"  Registered effects: {', '.join(sorted(all_effects.keys()))}")
        raise typer.Exit(1) from None

    # ---- load data ----
    data_path = Path(data)
    if not data_path.is_file():
        console.print(f"[red]File not found:[/] {data_path}")
        raise typer.Exit(1)

    try:
        import pandas as pd  # type: ignore[import-untyped]
    except ImportError as exc:
        console.print(f"[red]pandas not installed:[/] {exc}")
        raise typer.Exit(1) from exc

    try:
        df = pd.read_csv(data_path)
    except Exception as exc:
        console.print(f"[red]Failed to read CSV:[/] {exc}")
        raise typer.Exit(1) from exc

    # ---- check required columns ----
    req_cols = list(model.measurement_config.required_columns)
    if req_cols:
        missing = [c for c in req_cols if c not in df.columns]
        if missing:
            console.print(f"[red]Missing required columns:[/] {missing}")
            console.print(f"  CSV columns: {list(df.columns)}")
            console.print(f"  Required by {effect}: {req_cols}")
            raise typer.Exit(1)

    # ---- build data dict ----
    try:
        data_dict = {col: df[col].to_numpy(dtype=float) for col in df.columns}
    except Exception as exc:
        console.print(f"[red]Data conversion error:[/] {exc}")
        raise typer.Exit(1) from exc

    # ---- parse geometry ----
    geo: dict | None = None
    if geometry:
        import json

        try:
            geo = json.loads(geometry)
        except json.JSONDecodeError as exc:
            console.print(f"[red]Geometry JSON parse error:[/] {exc}")
            raise typer.Exit(1) from exc

    if discover:
        _run_discover_fit(
            model=model,
            data_dict=data_dict,
            effect=effect,
            data_path=data_path,
            geometry=geo,
            init_grid_json=init_grid_json,
            max_attempts=max_attempts,
            method=method,
            x_col=x_col,
            y_col=y_col,
        )
        if show_refs:
            console.print("\n[bold]References:[/]")
            for ref in model.references:
                console.print(f"  • {ref}")
        return

    # ---- run fit ----
    from maglab.analysis.fit import FitConvergenceError

    with console.status(f"[dim]Fitting {effect} …[/]"):
        try:
            result = model.fit(data_dict, geometry=geo)
        except FitConvergenceError as exc:
            console.print(f"[red]Fit convergence failed:[/] {exc}")
            raise typer.Exit(1) from exc
        except Exception as exc:
            console.print(f"[red]Fit error:[/] {exc}")
            raise typer.Exit(1) from exc

    # ---- print results ----
    console.print(f"\n[bold cyan]FitResult[/] — effect=[bold]{effect}[/]  data={data_path.name}")
    console.print(f"  Convergence: {'[green]OK[/]' if result.success else '[red]FAILED[/]'}")
    if result.message:
        console.print(f"  Message: [dim]{result.message}[/]")
    console.print(f"  χ² = {result.chi2:.6g}   reduced χ² = {result.reduced_chi2:.4f}")

    # Parameter table
    if result.params:
        tbl = Table(title="Fitted Parameters", show_lines=False)
        tbl.add_column("Parameter", style="cyan")
        tbl.add_column("Value", justify="right")
        tbl.add_column("±1σ", justify="right")
        unit_map = {p.name: p.unit for p in model.parameters}
        for pname, pval in result.params.items():
            unc = result.uncertainties.get(pname, 0.0)
            unit = unit_map.get(pname, "")
            tbl.add_row(pname, f"{pval:.6g} {unit}", f"±{unc:.3g}")
        console.print(tbl)

    if result.provenance_id:
        console.print(f"  Provenance ID: [dim]{result.provenance_id}[/]")

    console.print(
        f"\n[dim]Geometry:[/] {model.measurement_config.geometry}"
        f"  (tensor rank={model.measurement_config.tensor_rank})"
    )

    if show_refs:
        console.print("\n[bold]References:[/]")
        for ref in model.references:
            console.print(f"  • {ref}")


def _run_discover_fit(
    *,
    model: object,
    data_dict: dict[str, object],
    effect: str,
    data_path: Path,
    geometry: dict | None,
    init_grid_json: str | None,
    max_attempts: int,
    method: str,
    x_col: str | None,
    y_col: str | None,
) -> None:
    """Run the deterministic inner loop for ``maglab fit --discover``."""
    import json

    import numpy as np

    from maglab.analysis.bilevel import CircuitBreakerError, discover_fit
    from maglab.analysis.fit import FitConvergenceError

    required_columns = list(model.measurement_config.required_columns)  # type: ignore[attr-defined]
    if len(required_columns) < 2 and (x_col is None or y_col is None):
        console.print(
            "[red]--discover needs an independent and dependent column.[/] "
            "Pass --x-col and --y-col for this effect."
        )
        raise typer.Exit(1)
    selected_x = x_col or required_columns[0]
    selected_y = y_col or required_columns[-1]
    if selected_x not in data_dict or selected_y not in data_dict:
        console.print(f"[red]Missing --discover columns:[/] x={selected_x!r}, y={selected_y!r}")
        console.print(f"  CSV columns: {list(data_dict)}")
        raise typer.Exit(1)

    init_grid = None
    if init_grid_json:
        try:
            parsed = json.loads(init_grid_json)
        except json.JSONDecodeError as exc:
            console.print(f"[red]--init-grid JSON parse error:[/] {exc}")
            raise typer.Exit(1) from exc
        try:
            init_grid = _normalize_init_grid(parsed)
        except typer.BadParameter as exc:
            console.print(f"[red]--init-grid invalid:[/] {exc}")
            raise typer.Exit(1) from exc

    base_geometry = dict(geometry or {})

    def model_fn(x_data: np.ndarray, **params: float) -> np.ndarray:
        local_geometry = {**base_geometry, selected_x: x_data}
        return model.forward(params, geometry=local_geometry)  # type: ignore[attr-defined]

    with console.status(f"[dim]Discovering deterministic inner fit for {effect} …[/]"):
        try:
            result = discover_fit(
                model_fn=model_fn,
                x_data=np.asarray(data_dict[selected_x], dtype=float),
                y_data=np.asarray(data_dict[selected_y], dtype=float),
                param_specs=model.parameters,  # type: ignore[attr-defined]
                init_grid=init_grid,
                max_attempts=max_attempts,
                method=method,
                model_description=f"{effect}:known_effect_form",
            )
        except CircuitBreakerError as exc:
            console.print(f"[red]Bilevel circuit breaker:[/] {exc}")
            raise typer.Exit(1) from exc
        except FitConvergenceError as exc:
            console.print(f"[red]Discover fit convergence failed:[/] {exc}")
            raise typer.Exit(1) from exc
        except Exception as exc:
            console.print(f"[red]Discover fit error:[/] {exc}")
            raise typer.Exit(1) from exc

    fit_result = result.fit_result
    console.print(
        f"\n[bold cyan]Bilevel Discover Fit[/] — effect=[bold]{effect}[/]  data={data_path.name}"
    )
    console.print(
        "  Mode: deterministic inner optimization over a known effect model form; "
        "no LLM-generated equation or numeric result was accepted."
    )
    console.print(f"  Columns: x={selected_x}  y={selected_y}")
    console.print(f"  Attempts: {result.n_iter}/{max_attempts}")
    console.print(f"  Convergence: {'[green]OK[/]' if result.converged else '[red]FAILED[/]'}")
    console.print(
        f"  χ² = {fit_result.chi2:.6g}   reduced χ² = {fit_result.reduced_chi2:.4f}   "
        f"AIC = {result.aic:.6g}   BIC = {result.bic:.6g}"
    )
    if fit_result.params:
        tbl = Table(title="Discovered Inner Parameters", show_lines=False)
        tbl.add_column("Parameter", style="cyan")
        tbl.add_column("Value", justify="right")
        tbl.add_column("±1σ", justify="right")
        unit_map = {p.name: p.unit for p in model.parameters}  # type: ignore[attr-defined]
        for pname, pval in fit_result.params.items():
            unc = fit_result.uncertainties.get(pname, 0.0)
            unit = unit_map.get(pname, "")
            tbl.add_row(pname, f"{pval:.6g} {unit}", f"±{unc:.3g}")
        console.print(tbl)
    if fit_result.provenance_id:
        console.print(f"  Provenance ID: [dim]{fit_result.provenance_id}[/]")


def _normalize_init_grid(parsed: object) -> dict[str, list[float]]:
    """Validate and normalize the ``--init-grid`` JSON payload."""
    if not isinstance(parsed, dict):
        raise typer.BadParameter("--init-grid must be a JSON object.")
    grid: dict[str, list[float]] = {}
    for key, values in parsed.items():
        if not isinstance(key, str) or not key:
            raise typer.BadParameter("--init-grid keys must be parameter names.")
        if not isinstance(values, list) or not values:
            raise typer.BadParameter(f"--init-grid value for {key!r} must be a non-empty list.")
        try:
            grid[key] = [float(value) for value in values]
        except (TypeError, ValueError) as exc:
            raise typer.BadParameter(f"--init-grid values for {key!r} must be numeric.") from exc
    return grid


# ---------------------------------------------------------------------------
# Helper: list all effects
# ---------------------------------------------------------------------------


def _print_effect_list() -> None:
    """Print all registered effects grouped by provider."""
    try:
        from maglab.analysis.providers.base import _PROVIDER_REGISTRY
    except ImportError as exc:
        console.print(f"[red]Import error:[/] {exc}")
        raise typer.Exit(1) from exc

    tbl = Table(title="Registered Effect Models", show_lines=False)
    tbl.add_column("Effect", style="cyan")
    tbl.add_column("Provider")
    tbl.add_column("Parameters")

    for provider_name, provider in sorted(_PROVIDER_REGISTRY.items()):
        for effect_model in provider.effects:
            params = ", ".join(p.name for p in effect_model.parameters)
            tbl.add_row(effect_model.name, provider_name, params[:60])
    console.print(tbl)


# ===========================================================================
# maglab analyze
# ===========================================================================


@analyze_app.command("load")
def analyze_load(
    data: Path = _LOAD_DATA_ARG,
    fmt: str = _LOAD_FMT_OPT,
    columns: str | None = _LOAD_COLS_OPT,
) -> None:
    """[P2] Load experimental data and display a provenance-tracked summary.

    Reads the file, creates DataPoint instances, and prints column statistics.
    Provenance type is set to MEASURED (raw data is never modified).
    """
    if not Path(data).is_file():
        console.print(f"[red]File not found:[/] {data}")
        raise typer.Exit(1)

    try:
        from maglab.analysis.io import load_csv, load_hdf5
    except ImportError as exc:
        console.print(f"[red]Import error:[/] {exc}")
        raise typer.Exit(1) from exc

    with console.status("[dim]Loading data …[/]"):
        try:
            if fmt.lower() == "hdf5":
                df, datapoints = load_hdf5(data)
            else:
                df, datapoints = load_csv(data)
        except Exception as exc:
            console.print(f"[red]Failed to load {data}:[/] {exc}")
            raise typer.Exit(1) from exc

    # Column filter
    display_cols = list(df.columns)
    if columns:
        requested = [c.strip() for c in columns.split(",") if c.strip()]
        missing = [c for c in requested if c not in df.columns]
        if missing:
            console.print(f"[yellow]Columns not found (skipped):[/] {missing}")
        display_cols = [c for c in requested if c in df.columns] or list(df.columns)

    console.print(
        f"\n[bold cyan]Data loaded:[/] {Path(data).name}  "
        f"({len(df)} rows × {len(df.columns)} columns)"
    )
    console.print(f"  DataPoints created: {len(datapoints)} (type=MEASURED, raw data unchanged)")

    # Statistics table
    tbl = Table(title="Column Summary", show_lines=False)
    tbl.add_column("Column", style="cyan")
    tbl.add_column("N", justify="right")
    tbl.add_column("Mean", justify="right")
    tbl.add_column("Std", justify="right")
    tbl.add_column("Min", justify="right")
    tbl.add_column("Max", justify="right")

    for col in display_cols:
        if col not in df.columns:
            continue
        try:
            arr = df[col].dropna().to_numpy(dtype=float)
            tbl.add_row(
                col,
                str(len(arr)),
                f"{arr.mean():.4g}" if len(arr) else "—",
                f"{arr.std():.4g}" if len(arr) else "—",
                f"{arr.min():.4g}" if len(arr) else "—",
                f"{arr.max():.4g}" if len(arr) else "—",
            )
        except (TypeError, ValueError):
            tbl.add_row(col, str(len(df[col])), "—", "—", "—", "—")

    console.print(tbl)


@analyze_app.command("model")
def analyze_model(
    effect: str | None = _MODEL_EFFECT_ARG,
) -> None:
    """[P2] Show effect model details (parameters, geometry, references).

    Without an argument: lists all registered effect models.
    With an effect name: prints full model specification.
    """
    try:
        from maglab.analysis.providers import get_all_effects, get_effect
    except ImportError as exc:
        console.print(f"[red]Import error:[/] {exc}")
        raise typer.Exit(1) from exc

    if effect is None:
        _print_effect_list()
        return

    try:
        model = get_effect(effect)
    except KeyError:
        all_effects = get_all_effects()
        console.print(f"[red]Unknown effect:[/] {effect!r}")
        console.print(f"  Registered: {', '.join(sorted(all_effects.keys()))}")
        raise typer.Exit(1) from None

    console.print(f"\n[bold cyan]{model.name}[/]  (subfield: {model.subfield})")
    console.print(f"  Geometry: {model.measurement_config.geometry}")
    console.print(f"  Tensor rank: {model.measurement_config.tensor_rank}")
    if model.measurement_config.required_columns:
        console.print(f"  Required columns: {', '.join(model.measurement_config.required_columns)}")
    if model.measurement_config.notes:
        console.print(f"  Notes: [dim]{model.measurement_config.notes}[/]")

    tbl = Table(title="Parameters", show_lines=False)
    tbl.add_column("Name", style="cyan")
    tbl.add_column("Unit")
    tbl.add_column("Lower bound", justify="right")
    tbl.add_column("Upper bound", justify="right")
    tbl.add_column("Description")
    for p in model.parameters:
        lb = f"{p.lower:.4g}" if p.lower is not None else "—"
        ub = f"{p.upper:.4g}" if p.upper is not None else "—"
        tbl.add_row(p.name, p.unit, lb, ub, p.description[:50])
    console.print(tbl)

    console.print("\n[bold]References:[/]")
    for ref in model.references:
        console.print(f"  • {ref}")


@analyze_app.command("consistency")
def analyze_consistency(
    effect_a: str = _CONS_EFFECT_A_ARG,
    data_a: Path = _CONS_DATA_A_ARG,
    effect_b: str = _CONS_EFFECT_B_ARG,
    data_b: Path = _CONS_DATA_B_ARG,
    chi2_check: bool = _CONS_CHI2_OPT,
) -> None:
    """[P2] Check physical consistency between two independent effect fits.

    Fits both effects to their respective data, then compares shared parameters.
    Inconsistencies trigger a D2 explain signal (printed to output).
    All checks are purely deterministic — no LLM judgment.
    """
    try:
        from maglab.analysis.consistency import check_consistency, check_reduced_chi2
        from maglab.analysis.providers import get_effect
    except ImportError as exc:
        console.print(f"[red]Import error:[/] {exc}")
        raise typer.Exit(1) from exc

    for path in (data_a, data_b):
        if not Path(path).is_file():
            console.print(f"[red]File not found:[/] {path}")
            raise typer.Exit(1)

    def _fit_effect(effect_name: str, data_path: Path) -> object:
        """Fit an effect to a CSV file and return FitResult."""
        import pandas as pd  # type: ignore[import-untyped]

        model = get_effect(effect_name)
        df = pd.read_csv(data_path)
        data_dict = {col: df[col].to_numpy(float) for col in df.columns}
        return model.fit(data_dict)

    from maglab.analysis.effects.base import FitResult
    from maglab.analysis.fit import FitConvergenceError

    try:
        with console.status(f"[dim]Fitting {effect_a} …[/]"):
            result_a = _fit_effect(effect_a, data_a)
        with console.status(f"[dim]Fitting {effect_b} …[/]"):
            result_b = _fit_effect(effect_b, data_b)
    except FitConvergenceError as exc:
        console.print(f"[red]Fit convergence failed:[/] {exc}")
        raise typer.Exit(1) from exc
    except KeyError as exc:
        console.print(f"[red]Unknown effect:[/] {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]Error during fitting:[/] {exc}")
        raise typer.Exit(1) from exc

    assert isinstance(result_a, FitResult)
    assert isinstance(result_b, FitResult)

    cresult = check_consistency(result_a, result_b)
    console.print(f"\n[bold cyan]Consistency Check[/]: {effect_a} vs {effect_b}")
    if cresult.ok:
        console.print("  [green]✓ Consistent[/] — no shared-parameter conflicts detected.")
    else:
        console.print("  [red]✗ Inconsistency detected[/]")
        for w in cresult.warnings:
            console.print(f"    [yellow]Warning:[/] {w}")
        if cresult.trigger_explain:
            console.print(
                "  [dim]→ Consider running 'maglab explain' to investigate the anomaly (D2).[/]"
            )

    if chi2_check:
        for eff_name, res in ((effect_a, result_a), (effect_b, result_b)):
            cr = check_reduced_chi2(res)
            status = "[green]OK[/]" if cr.ok else "[yellow]WARNING[/]"
            console.print(f"  reduced χ² ({eff_name}): {res.reduced_chi2:.4f}  [{status}]")
            for w in cr.warnings:
                console.print(f"    [dim]{w}[/]")


@analyze_app.command("symmetry")
def analyze_symmetry(
    point_group: str = _SYM_GROUP_ARG,
    list_groups: bool = _SYM_LIST_OPT,
) -> None:
    """[P2] Show allowed tensor components for a magnetic point group.

    Outputs AHE, AMR, PHE, and OHE (rank-3) allowed components.
    Useful for verifying which terms are symmetry-permitted before fitting.
    """
    try:
        from maglab.analysis.symmetry import (
            allowed_components,
            list_supported_groups,
        )
    except ImportError as exc:
        console.print(f"[red]Import error:[/] {exc}")
        raise typer.Exit(1) from exc

    if list_groups:
        groups = list_supported_groups()
        console.print("[bold]Supported magnetic point groups:[/]")
        for g in groups:
            console.print(f"  • {g}")
        return

    try:
        comp = allowed_components(point_group)
    except ValueError as exc:
        groups = list_supported_groups()
        console.print(f"[red]Unknown point group:[/] {point_group!r}")
        console.print(f"  Supported: {', '.join(groups)}")
        raise typer.Exit(1) from exc

    console.print(f"\n[bold cyan]Magnetic point group:[/] {comp.point_group}")
    if comp.notes:
        console.print(f"  [dim]{comp.notes}[/]")

    tbl = Table(title="Allowed Components", show_lines=False)
    tbl.add_column("Effect", style="cyan")
    tbl.add_column("Allowed")
    tbl.add_column("Components")

    hall_str = ", ".join(f"σ_{'xyz'[a]}{'xyz'[b]}" for a, b in comp.hall_components)
    tbl.add_row(
        "AHE (Hall conductivity)",
        "[green]Yes[/]" if comp.ahe_allowed else "[red]No[/]",
        hall_str or "—",
    )
    tbl.add_row(
        "AMR (cos²θ)",
        "[green]Yes[/]" if comp.amr_allowed else "[red]No[/]",
        "Δρ·cos²θ" if comp.amr_allowed else "forbidden",
    )
    tbl.add_row(
        "PHE (sin2φ)",
        "[green]Yes[/]" if comp.phe_allowed else "[red]No[/]",
        "(Δρ/2)·sin2φ" if comp.phe_allowed else "forbidden",
    )
    ohe_str = ", ".join(
        f"σ^{'xyz'[c]}_{{'xyz'[a]}}{'xyz'[b]}" for a, b, c in comp.ohe_components[:6]
    )
    if len(comp.ohe_components) > 6:
        ohe_str += f" … (+{len(comp.ohe_components) - 6} more)"
    tbl.add_row(
        "OHE (rank-3 tensor)",
        "[green]Yes[/]" if comp.ohe_components else "[red]No[/]",
        ohe_str or "none",
    )

    console.print(tbl)


# ===========================================================================
# maglab device
# ===========================================================================


@device_app.command("fom")
def device_fom(
    device: str = _DEV_DEVICE_ARG,
    ms: float | None = _DEV_MS_OPT,
    t_fm: float | None = _DEV_T_FM_OPT,
    k_u: float | None = _DEV_KU_OPT,
    alpha: float | None = _DEV_ALPHA_OPT,
    theta_sh: float | None = _DEV_THETA_SH_OPT,
    temp: float | None = _DEV_TEMP_OPT,
    d_bit: float | None = _DEV_DBIT_OPT,
    p_spin: float | None = _DEV_P_OPT,
    tmr: float | None = _DEV_TMR_OPT,
    j_drive: float | None = _DEV_JDRIVE_OPT,
    show_refs: bool = _DEV_REFS_OPT,
) -> None:
    """[P2] Compute device figures-of-merit (FoM) for a spintronic device.

    Examples:
        maglab device fom sot-mram --Ms 8e5 --t 2e-9 --Ku 4e5
        maglab device fom stt-mram --Ms 8e5 --t 2e-9 --Ku 4e5 --P 0.6
        maglab device fom racetrack --alpha 0.01
        maglab device fom list
    """
    try:
        from maglab.analysis.device_fom import compute_fom, list_devices
    except ImportError as exc:
        console.print(f"[red]Import error:[/] {exc}")
        raise typer.Exit(1) from exc

    if device.lower() in ("list", "ls", "--list"):
        console.print("[bold]Registered device types:[/]")
        for dev in list_devices():
            console.print(f"  • {dev}")
        return

    # Collect user-supplied kwargs (only non-None values)
    kwargs: dict[str, float] = {}
    _optmap: list[tuple[str, float | None]] = [
        ("Ms", ms),
        ("t_FM", t_fm),
        ("K_u", k_u),
        ("alpha", alpha),
        ("theta_SH", theta_sh),
        ("T", temp),
        ("d_bit", d_bit),
        ("P", p_spin),
        ("TMR", tmr),
        ("j_drive", j_drive),
    ]
    for key, val in _optmap:
        if val is not None:
            kwargs[key] = val

    try:
        result = compute_fom(device, **kwargs)
    except KeyError:
        console.print(f"[red]Unknown device:[/] {device!r}")
        console.print(f"  Registered: {', '.join(list_devices())}")
        raise typer.Exit(1) from None
    except Exception as exc:
        console.print(f"[red]FoM computation error:[/] {exc}")
        raise typer.Exit(1) from exc

    # Print inputs
    console.print(f"\n[bold cyan]Device FoM:[/] {result.device}")
    inp_parts = [f"{k}={v:.3g}" for k, v in result.inputs.items()]
    console.print(f"  Inputs: {', '.join(inp_parts)}")

    # FoM table
    tbl = Table(title=f"{result.device.upper()} — Figure of Merit", show_lines=False)
    tbl.add_column("FoM", style="cyan")
    tbl.add_column("Value", justify="right")
    tbl.add_column("Unit")
    tbl.add_column("Formula")
    tbl.add_column("vs Target", justify="right")

    for row in result.table():
        ratio_str = ""
        if "current/target" in row and row["current/target"] is not None:
            ratio = row["current/target"]
            color = "green" if ratio >= 1.0 else "yellow"
            ratio_str = f"[{color}]{ratio:.2f}×[/{color}]"
        tbl.add_row(
            row["FoM"],
            f"{row['value']:.4g}" if row["value"] is not None else "—",
            row.get("unit", ""),
            row.get("formula", ""),
            ratio_str,
        )

    console.print(tbl)

    if result.target_comparison:
        console.print("  [dim]Target column: ratio = computed / IRDS 2023 target.[/]")

    if show_refs:
        console.print("\n[bold]References:[/]")
        for ref in result.references:
            console.print(f"  • {ref}")
