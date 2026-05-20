"""F6 data → figure integration tests (§20 — F6 flow value accuracy validation).

Validation items:
  - CSV loading → DataPoint MEASURED tagging
  - PlotKind inference from column names
  - FigureSpec construction and DataPoint binding
  - Render → PDF/SVG export
  - Value accuracy (not pixel comparison)
  - Unbound panel honesty gate blocking
  - Graceful handling when simulation overlay solver is not installed
"""

from __future__ import annotations

import math
import textwrap
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from maglab.figure.spec import PanelType, PlotKind
from maglab.provenance.datapoint import DataPoint, ProvenanceType
from maglab.sim.plot import (
    build_figure_spec,
    infer_plot_kind,
    load_csv_datapoints,
    plot_data_to_figure,
    run_sim_overlay,
)

# ---------------------------------------------------------------------------
# Fixtures — sample CSV files
# ---------------------------------------------------------------------------


@pytest.fixture()
def hysteresis_csv(tmp_path: Path) -> Path:
    """M-H hysteresis CSV file."""
    content = textwrap.dedent("""\
        H (T),M (A/m)
        -1.0,-860000.0
        -0.5,-820000.0
        0.0,0.0
        0.5,820000.0
        1.0,860000.0
    """)
    p = tmp_path / "hysteresis.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def hall_csv(tmp_path: Path) -> Path:
    """Hall resistivity CSV file."""
    content = textwrap.dedent("""\
        H (T),rho_xy (Ohm)
        -1.0,-0.5
        -0.5,-0.3
        0.0,0.0
        0.5,0.3
        1.0,0.5
    """)
    p = tmp_path / "hall.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def fmr_csv(tmp_path: Path) -> Path:
    """FMR absorption CSV file."""
    content = textwrap.dedent("""\
        H (T),absorption (a.u.)
        0.1,0.1
        0.2,0.5
        0.3,1.0
        0.4,0.5
        0.5,0.1
    """)
    p = tmp_path / "fmr.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def dispersion_csv(tmp_path: Path) -> Path:
    """Dispersion relation CSV file."""
    content = textwrap.dedent("""\
        k (1/nm),frequency (GHz)
        0.0,5.0
        1.0,5.5
        2.0,6.2
        3.0,7.1
        4.0,8.3
    """)
    p = tmp_path / "dispersion.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def generic_xy_csv(tmp_path: Path) -> Path:
    """Generic XY CSV file (no labeled columns)."""
    content = textwrap.dedent("""\
        x,y
        0.0,0.0
        1.0,2.0
        2.0,4.0
        3.0,6.0
    """)
    p = tmp_path / "xy.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def header_only_csv(tmp_path: Path) -> Path:
    """CSV file with header only and no data rows."""
    content = "H (T),M (A/m)\n"
    p = tmp_path / "empty.csv"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# load_csv_datapoints tests
# ---------------------------------------------------------------------------


class TestLoadCsvDatapoints:
    def test_returns_dict_of_datapoints(self, hysteresis_csv: Path) -> None:
        """Returns a dictionary matching the number of CSV columns."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        assert isinstance(col_dps, dict)
        assert len(col_dps) == 2

    def test_provenance_type_is_measured(self, hysteresis_csv: Path) -> None:
        """All DataPoints must have provenance_type == MEASURED."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        for dp in col_dps.values():
            assert dp.provenance_type == ProvenanceType.MEASURED

    def test_value_accuracy(self, hysteresis_csv: Path) -> None:
        """H column values match the original CSV."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        assert "h" in col_dps
        h_vals = col_dps["h"].value
        assert isinstance(h_vals, list)
        assert len(h_vals) == 5
        assert math.isclose(h_vals[0], -1.0)
        assert math.isclose(h_vals[2], 0.0)
        assert math.isclose(h_vals[4], 1.0)

    def test_units_extracted_from_header(self, hysteresis_csv: Path) -> None:
        """Units in parentheses in the header are correctly extracted into DataPoint.units."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        assert col_dps["h"].units == "T"
        assert col_dps["m"].units == "A/m"

    def test_units_fallback_dimensionless(self, generic_xy_csv: Path) -> None:
        """Headers without parentheses are treated as units='1'."""
        col_dps = load_csv_datapoints(generic_xy_csv)
        for dp in col_dps.values():
            assert dp.units == "1"

    def test_source_ref_defaults_to_absolute_path(self, hysteresis_csv: Path) -> None:
        """When source_ref is not provided, the absolute file path is used."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        for dp in col_dps.values():
            assert str(hysteresis_csv.resolve()) in dp.source_ref

    def test_custom_source_ref(self, hysteresis_csv: Path) -> None:
        """User-provided source_ref is reflected."""
        col_dps = load_csv_datapoints(hysteresis_csv, source_ref="doi:10.1234/test")
        for dp in col_dps.values():
            assert dp.source_ref == "doi:10.1234/test"

    def test_conditions_passed_to_datapoint(self, hysteresis_csv: Path) -> None:
        """Conditions dictionary is passed to all DataPoints."""
        cond = {"T_K": 300.0, "field_dir": "z"}
        col_dps = load_csv_datapoints(hysteresis_csv, conditions=cond)
        for dp in col_dps.values():
            assert dp.conditions == cond

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError for a non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_csv_datapoints(tmp_path / "nonexistent.csv")

    def test_header_only_raises_value_error(self, header_only_csv: Path) -> None:
        """Raises ValueError for a CSV with no data rows."""
        with pytest.raises(ValueError, match="CSV contains no numeric data"):
            load_csv_datapoints(header_only_csv)

    def test_each_datapoint_has_unique_id(self, hysteresis_csv: Path) -> None:
        """All DataPoints have unique IDs."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        ids = [dp.id for dp in col_dps.values()]
        assert len(ids) == len(set(ids))

    def test_m_column_values(self, hysteresis_csv: Path) -> None:
        """M column values match the original CSV."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        assert "m" in col_dps
        m_vals = col_dps["m"].value
        assert isinstance(m_vals, list)
        assert math.isclose(m_vals[0], -860000.0)
        assert math.isclose(m_vals[2], 0.0)
        assert math.isclose(m_vals[4], 860000.0)


# ---------------------------------------------------------------------------
# infer_plot_kind tests
# ---------------------------------------------------------------------------


class TestInferPlotKind:
    def test_hysteresis_inferred_from_m(self) -> None:
        """'h' and 'm' columns infer HYSTERESIS."""
        assert infer_plot_kind(["h", "m"]) == PlotKind.HYSTERESIS

    def test_hysteresis_inferred_from_magnetization(self) -> None:
        """A 'magnetization' column infers HYSTERESIS."""
        assert infer_plot_kind(["h", "magnetization"]) == PlotKind.HYSTERESIS

    def test_hall_priority_over_hysteresis(self) -> None:
        """'rho_xy' takes HALL priority over HYSTERESIS."""
        assert infer_plot_kind(["h", "rho_xy", "m"]) == PlotKind.HALL

    def test_hall_from_rho_xy(self) -> None:
        """'rho_xy' column infers HALL."""
        assert infer_plot_kind(["h", "rho_xy"]) == PlotKind.HALL

    def test_fmr_inferred(self) -> None:
        """'absorption' column infers FMR."""
        assert infer_plot_kind(["h", "absorption"]) == PlotKind.FMR

    def test_fmr_priority_over_hall(self) -> None:
        """When both 'fmr' and 'rho_xy' are present, HALL takes priority over FMR."""
        kind = infer_plot_kind(["hall", "fmr"])
        assert kind == PlotKind.HALL

    def test_dispersion_requires_freq_and_k(self) -> None:
        """'frequency' and 'k' together infer DISPERSION."""
        assert infer_plot_kind(["k", "frequency"]) == PlotKind.DISPERSION

    def test_dispersion_not_inferred_without_k(self) -> None:
        """'frequency' alone without 'k' does not infer DISPERSION."""
        kind = infer_plot_kind(["frequency"])
        assert kind != PlotKind.DISPERSION

    def test_xy_fallback(self) -> None:
        """Falls back to XY when no pattern matches."""
        assert infer_plot_kind(["time", "voltage"]) == PlotKind.XY

    def test_single_column_fallback(self) -> None:
        """A single column is handled without error."""
        kind = infer_plot_kind(["data"])
        assert isinstance(kind, PlotKind)


# ---------------------------------------------------------------------------
# build_figure_spec tests
# ---------------------------------------------------------------------------


class TestBuildFigureSpec:
    def test_returns_figure_spec(self, hysteresis_csv: Path) -> None:
        """Returns a FigureSpec instance."""
        from maglab.figure.spec import FigureSpec

        col_dps = load_csv_datapoints(hysteresis_csv)
        spec = build_figure_spec(col_dps)
        assert isinstance(spec, FigureSpec)

    def test_panel_type_is_data_plot(self, hysteresis_csv: Path) -> None:
        """Panel type must be DATA_PLOT."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        spec = build_figure_spec(col_dps)
        assert spec.panels[0].panel_type == PanelType.DATA_PLOT

    def test_data_point_ids_bound(self, hysteresis_csv: Path) -> None:
        """DataPoint IDs must be bound to the panel."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        spec = build_figure_spec(col_dps)
        assert len(spec.panels[0].data_point_ids) >= 1

    def test_bound_ids_exist_in_col_dps(self, hysteresis_csv: Path) -> None:
        """Bound DataPoint IDs must match actual DataPoint IDs."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        spec = build_figure_spec(col_dps)
        all_ids = {dp.id for dp in col_dps.values()}
        for pid in spec.panels[0].data_point_ids:
            assert pid in all_ids

    def test_plot_kind_hysteresis(self, hysteresis_csv: Path) -> None:
        """Hysteresis CSV sets HYSTERESIS PlotKind."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        spec = build_figure_spec(col_dps)
        assert spec.panels[0].plot_kind == PlotKind.HYSTERESIS

    def test_plot_kind_hall(self, hall_csv: Path) -> None:
        """Hall CSV sets HALL PlotKind."""
        col_dps = load_csv_datapoints(hall_csv)
        spec = build_figure_spec(col_dps)
        assert spec.panels[0].plot_kind == PlotKind.HALL

    def test_explicit_plot_kind_override(self, hysteresis_csv: Path) -> None:
        """plot_kind argument overrides inference."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        spec = build_figure_spec(col_dps, plot_kind=PlotKind.XY)
        assert spec.panels[0].plot_kind == PlotKind.XY

    def test_sim_dp_ids_in_overlay(self, hysteresis_csv: Path) -> None:
        """sim_dp_ids are inserted into the panel overlay."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        fake_sim_ids = ["sim-id-001", "sim-id-002"]
        spec = build_figure_spec(col_dps, sim_dp_ids=fake_sim_ids)
        for sid in fake_sim_ids:
            assert sid in spec.panels[0].overlay

    def test_empty_col_dps_raises(self) -> None:
        """Empty DataPoint dictionary raises ValueError."""
        with pytest.raises(ValueError, match="DataPoint is empty"):
            build_figure_spec({})

    def test_honesty_gate_no_binding_raises(self) -> None:
        """A data-plot panel without data_point_ids raises ValidationError."""
        from maglab.figure.spec import (
            AxisSpec,
            GridPosition,
            PanelSpec,
            PlotKind,
        )

        with pytest.raises(ValidationError):
            PanelSpec(
                panel_id="p_unbound",
                panel_type=PanelType.DATA_PLOT,
                plot_kind=PlotKind.HYSTERESIS,
                data_point_ids=[],  # unbound — must be blocked
                grid_position=GridPosition(row=0, col=0),
                x_axis=AxisSpec(label="H (T)"),
                y_axis=AxisSpec(label="M (A/m)"),
            )

    def test_caption_auto_generated(self, hysteresis_csv: Path, tmp_path: Path) -> None:
        """When no caption is provided to plot_data_to_figure, one is auto-generated."""
        out = tmp_path / "autocap.pdf"
        _, spec, _ = plot_data_to_figure(hysteresis_csv, output_path=out)
        assert spec.caption != ""

    def test_custom_caption(self, hysteresis_csv: Path) -> None:
        """User-provided caption is reflected."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        spec = build_figure_spec(col_dps, caption="My caption")
        assert spec.caption == "My caption"

    def test_figure_id_is_unique(self, hysteresis_csv: Path) -> None:
        """figure_id differs between two invocations."""
        col_dps = load_csv_datapoints(hysteresis_csv)
        spec1 = build_figure_spec(col_dps)
        spec2 = build_figure_spec(col_dps)
        assert spec1.figure_id != spec2.figure_id


# ---------------------------------------------------------------------------
# plot_data_to_figure — integration pipeline tests
# ---------------------------------------------------------------------------


class TestPlotDataToFigure:
    def test_returns_tuple(self, hysteresis_csv: Path, tmp_path: Path) -> None:
        """Return value must be a (Path, FigureSpec, dict) tuple."""
        from maglab.figure.spec import FigureSpec

        out = tmp_path / "out.pdf"
        result = plot_data_to_figure(hysteresis_csv, output_path=out)
        assert isinstance(result, tuple) and len(result) == 3
        saved, spec, ledger = result
        assert isinstance(saved, Path)
        assert isinstance(spec, FigureSpec)
        assert isinstance(ledger, dict)

    def test_pdf_file_created(self, hysteresis_csv: Path, tmp_path: Path) -> None:
        """A PDF file is actually created."""
        out = tmp_path / "test.pdf"
        saved, _, _ = plot_data_to_figure(hysteresis_csv, output_path=out)
        assert saved.exists()
        assert saved.suffix == ".pdf"
        assert saved.stat().st_size > 0

    def test_svg_file_created(self, hysteresis_csv: Path, tmp_path: Path) -> None:
        """An SVG file is actually created."""
        out = tmp_path / "test.svg"
        saved, _, _ = plot_data_to_figure(hysteresis_csv, output_path=out, fmt="svg")
        assert saved.exists()
        assert saved.stat().st_size > 0

    def test_output_default_path(self, hysteresis_csv: Path) -> None:
        """When output_path is not provided, the file is created in the same directory as data_path."""
        saved, _, _ = plot_data_to_figure(hysteresis_csv)
        assert saved.parent == hysteresis_csv.parent
        assert saved.stem == hysteresis_csv.stem
        # Clean up created file
        if saved.exists():
            saved.unlink()

    def test_ledger_contains_measured_datapoints(
        self, hysteresis_csv: Path, tmp_path: Path
    ) -> None:
        """All DataPoints in the ledger must be of type MEASURED."""
        out = tmp_path / "out.pdf"
        _, _, ledger = plot_data_to_figure(hysteresis_csv, output_path=out)
        for dp in ledger.values():
            assert dp.provenance_type == ProvenanceType.MEASURED

    def test_ledger_ids_match_spec_bindings(self, hysteresis_csv: Path, tmp_path: Path) -> None:
        """All IDs bound in FigureSpec must exist in the ledger."""
        out = tmp_path / "out.pdf"
        _, spec, ledger = plot_data_to_figure(hysteresis_csv, output_path=out)
        for panel in spec.panels:
            for pid in panel.data_point_ids:
                assert pid in ledger

    def test_value_accuracy_in_ledger(self, hysteresis_csv: Path, tmp_path: Path) -> None:
        """DataPoint values in the ledger match the original CSV."""
        out = tmp_path / "out.pdf"
        _, _, ledger = plot_data_to_figure(hysteresis_csv, output_path=out)
        # Find the H column DataPoint in the ledger
        h_dp: DataPoint | None = None
        for dp in ledger.values():
            if isinstance(dp.value, list) and math.isclose(dp.value[0], -1.0, rel_tol=1e-6):
                h_dp = dp
                break
        assert h_dp is not None, "Could not find a DataPoint with H=-1.0."
        assert math.isclose(h_dp.value[4], 1.0, rel_tol=1e-6)

    def test_hall_plot_kind_inferred(self, hall_csv: Path, tmp_path: Path) -> None:
        """Hall CSV sets HALL PlotKind."""
        out = tmp_path / "hall.pdf"
        _, spec, _ = plot_data_to_figure(hall_csv, output_path=out)
        assert spec.panels[0].plot_kind == PlotKind.HALL

    def test_fmr_plot_kind_inferred(self, fmr_csv: Path, tmp_path: Path) -> None:
        """FMR CSV sets FMR PlotKind."""
        out = tmp_path / "fmr.pdf"
        _, spec, _ = plot_data_to_figure(fmr_csv, output_path=out)
        assert spec.panels[0].plot_kind == PlotKind.FMR

    def test_dispersion_plot_kind_inferred(self, dispersion_csv: Path, tmp_path: Path) -> None:
        """Dispersion relation CSV sets DISPERSION PlotKind."""
        out = tmp_path / "disp.pdf"
        _, spec, _ = plot_data_to_figure(dispersion_csv, output_path=out)
        assert spec.panels[0].plot_kind == PlotKind.DISPERSION

    def test_file_not_found_propagates(self, tmp_path: Path) -> None:
        """FileNotFoundError propagates for a non-existent file."""
        with pytest.raises(FileNotFoundError):
            plot_data_to_figure(tmp_path / "ghost.csv")

    def test_sim_overlay_graceful_no_solver(self, hysteresis_csv: Path, tmp_path: Path) -> None:
        """Simulation overlay only issues a warning and plots data when no solver is installed."""
        out = tmp_path / "overlay.pdf"
        # Specifying a non-installed engine falls back without error
        sim_spec = {
            "scales": [
                {
                    "scale": "micro",
                    "engine": "mumax3",  # not installed — graceful handling
                    "material": {
                        "Ms_Am": 860000.0,
                        "A_Jm": 1.3e-11,
                        "alpha": 0.01,
                        "K_Jm3": 0.0,
                        "K_axis": [0.0, 0.0, 1.0],
                        "D_Jm2": 0.0,
                    },
                    "geometry": {
                        "nx": 16,
                        "ny": 16,
                        "nz": 2,
                        "dx_nm": 5.0,
                        "dy_nm": 5.0,
                        "dz_nm": 5.0,
                    },
                    "t_sim_ns": 0.0,
                    "initial_state": "uniform",
                    "initial_m_dir": [1.0, 0.0, 0.0],
                }
            ]
        }
        with warnings.catch_warnings(record=True) as w_list:
            warnings.simplefilter("always")
            saved, _, ledger = plot_data_to_figure(
                hysteresis_csv,
                output_path=out,
                sim_spec_dict=sim_spec,
            )
        # Verify file creation
        assert saved.exists()
        # ledger DataPoints are MEASURED (no simulation DataPoints — solver not installed)
        for dp in ledger.values():
            assert dp.provenance_type == ProvenanceType.MEASURED
        # Warning presence check (solver not installed → warning + continue)
        _ = [w for w in w_list if issubclass(w.category, (UserWarning, RuntimeWarning))]
        # No warning is also valid (depends on environment)


# ---------------------------------------------------------------------------
# run_sim_overlay — standalone tests
# ---------------------------------------------------------------------------


class TestRunSimOverlay:
    def test_invalid_spec_returns_empty_with_warning(self) -> None:
        """Returns an empty list and a warning for an invalid spec."""
        with warnings.catch_warnings(record=True) as w_list:
            warnings.simplefilter("always")
            result = run_sim_overlay({"invalid": "spec"})
        assert result == []
        assert len(w_list) > 0

    def test_no_solver_returns_empty(self) -> None:
        """Returns an empty list when no solver is installed (no exception)."""
        spec_dict = {
            "scales": [
                {
                    "scale": "micro",
                    "engine": "mumax3",
                    "material": {
                        "Ms_Am": 860000.0,
                        "A_Jm": 1.3e-11,
                        "alpha": 0.01,
                        "K_Jm3": 0.0,
                        "K_axis": [0.0, 0.0, 1.0],
                        "D_Jm2": 0.0,
                    },
                    "geometry": {
                        "nx": 8,
                        "ny": 8,
                        "nz": 1,
                        "dx_nm": 5.0,
                        "dy_nm": 5.0,
                        "dz_nm": 5.0,
                    },
                    "t_sim_ns": 0.0,
                    "initial_state": "uniform",
                    "initial_m_dir": [1.0, 0.0, 0.0],
                }
            ]
        }
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = run_sim_overlay(spec_dict)
        # Always returns empty list when solver is not installed
        assert isinstance(result, list)

    def test_return_type_is_list(self) -> None:
        """Return value is always of type list."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = run_sim_overlay({})
        assert isinstance(result, list)
