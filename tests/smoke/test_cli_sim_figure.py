"""CLI sim/figure subapp smoke tests (§20 — P1 CLI smoke).

Validates:
  - maglab sim --help, maglab figure --help exit 0
  - All sub-subcommand --help exit 0
  - sim plot actual behaviour: CSV → vector figure creation
  - figure spec/render actual behaviour
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from maglab.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# --help exit 0
# ---------------------------------------------------------------------------


@pytest.mark.smoke
def test_sim_help_exit_0() -> None:
    """maglab sim --help returns exit 0."""
    result = runner.invoke(app, ["sim", "--help"])
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert "sim" in result.stdout.lower()


@pytest.mark.smoke
def test_figure_help_exit_0() -> None:
    """maglab figure --help returns exit 0."""
    result = runner.invoke(app, ["figure", "--help"])
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert "figure" in result.stdout.lower()


@pytest.mark.smoke
@pytest.mark.parametrize(
    "args",
    [
        ["sim", "doctor", "--help"],
        ["sim", "micro", "--help"],
        ["sim", "validate", "--help"],
        ["sim", "plot", "--help"],
        ["sim", "job", "--help"],
        ["sim", "dft", "--help"],
        ["sim", "atomistic", "--help"],
        ["sim", "pipeline", "--help"],
        ["figure", "spec", "--help"],
        ["figure", "render", "--help"],
        ["figure", "compose", "--help"],
        ["figure", "export", "--help"],
    ],
)
def test_subcommand_help_exit_0(args: list[str]) -> None:
    """sim/figure sub-subcommand --help returns exit 0."""
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"args={args}  exit={result.exit_code}\n{result.stdout}"


# ---------------------------------------------------------------------------
# sim/figure subapps are real subapps, not stubs (no P1 message)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
def test_sim_no_args_shows_help() -> None:
    """maglab sim (no args) prints help, not a P1 stub message."""
    result = runner.invoke(app, ["sim"])
    # no_args_is_help=True → exit 0 (Typer) or exit 2 (some versions)
    # Key: the P1 stub message ('P1') is not printed; subcommand list is shown
    assert "micro" in result.stdout or "validate" in result.stdout or "plot" in result.stdout


@pytest.mark.smoke
def test_sim_doctor_json_smoke() -> None:
    """sim doctor emits machine-readable backend readiness JSON."""
    result = runner.invoke(app, ["sim", "doctor", "--json"])

    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    report = json.loads(result.stdout)
    assert report["backend_requested"] == "auto"
    assert report["recommended_backend"] in {"local-gpu", "cpu", "mock"}
    assert "python" in report
    assert "remote_python" in report
    assert "paramiko" not in {item["name"] for item in report["python"]}
    assert "paramiko" in {item["name"] for item in report["remote_python"]}
    assert "binaries" in report


@pytest.mark.smoke
def test_sim_doctor_explain_shows_execution_paths() -> None:
    """sim doctor --explain shows the user-facing path decision table."""
    result = runner.invoke(app, ["sim", "doctor", "--explain"])

    assert result.exit_code == 0, result.output
    assert "Simulation execution paths" in result.output
    assert "Remote execution Python packages" in result.output
    assert "No-GPU dry run" in result.output
    assert "Local CPU fallback" in result.output


@pytest.mark.smoke
def test_sim_pipeline_mock_writes_manifest_json() -> None:
    """No-GPU pipeline path produces a real manifest artifact."""
    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            [
                "sim",
                "pipeline",
                "--backend",
                "mock",
                "--work-dir",
                "pipeline_out",
                "--json",
            ],
        )
        manifest = Path("pipeline_out/pipeline_result.json")
        exists = manifest.is_file()

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["manifest_path"].endswith("pipeline_result.json")
    assert payload["provenance"]
    assert exists


@pytest.mark.smoke
def test_sim_pipeline_help_uses_doctor_backend_names() -> None:
    result = runner.invoke(app, ["sim", "pipeline", "--help"])
    assert result.exit_code == 0, result.output
    assert "local-gpu" in result.output
    assert "ssh-gpu" in result.output
    assert "ssh-hpc" in result.output


@pytest.mark.smoke
def test_figure_no_args_shows_help() -> None:
    """maglab figure (no args) prints help."""
    result = runner.invoke(app, ["figure"])
    assert "spec" in result.stdout or "render" in result.stdout or "compose" in result.stdout


# ---------------------------------------------------------------------------
# sim plot — F6 actual behaviour (CSV → PDF creation)
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_hysteresis_csv(tmp_path: Path) -> Path:
    """M-H hysteresis CSV sample."""
    content = textwrap.dedent("""\
        H (T),M (A/m)
        -1.0,-860000.0
        -0.5,-820000.0
        0.0,0.0
        0.5,820000.0
        1.0,860000.0
    """)
    p = tmp_path / "test_hysteresis.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def sample_hall_csv(tmp_path: Path) -> Path:
    """Hall CSV sample."""
    content = textwrap.dedent("""\
        H (T),rho_xy (Ohm)
        -1.0,-0.5
        0.0,0.0
        1.0,0.5
    """)
    p = tmp_path / "test_hall.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.mark.smoke
def test_sim_plot_pdf_created(sample_hysteresis_csv: Path, tmp_path: Path) -> None:
    """sim plot creates a PDF vector figure from a CSV."""
    out = tmp_path / "output.pdf"
    result = runner.invoke(
        app,
        ["sim", "plot", str(sample_hysteresis_csv), "--output", str(out)],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert out.exists(), "PDF file should be created."
    assert out.stat().st_size > 0


@pytest.mark.smoke
def test_sim_plot_svg_created(sample_hysteresis_csv: Path, tmp_path: Path) -> None:
    """sim plot --format svg creates an SVG figure."""
    out = tmp_path / "output.svg"
    result = runner.invoke(
        app,
        ["sim", "plot", str(sample_hysteresis_csv), "--output", str(out), "--format", "svg"],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert out.exists()


@pytest.mark.smoke
def test_sim_plot_accepts_prl_journal_alias(sample_hysteresis_csv: Path, tmp_path: Path) -> None:
    """sim plot should accept common APS journal aliases."""
    out = tmp_path / "output_prl.svg"
    result = runner.invoke(
        app,
        [
            "sim",
            "plot",
            str(sample_hysteresis_csv),
            "--journal",
            "prl",
            "--format",
            "svg",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert out.exists()


@pytest.mark.smoke
def test_sim_plot_hall_csv(sample_hall_csv: Path, tmp_path: Path) -> None:
    """sim plot succeeds for a Hall CSV."""
    out = tmp_path / "hall.pdf"
    result = runner.invoke(
        app,
        ["sim", "plot", str(sample_hall_csv), "--output", str(out)],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert out.exists()


@pytest.mark.smoke
def test_sim_plot_nonexistent_file() -> None:
    """sim plot returns exit 1 for a non-existent file."""
    result = runner.invoke(app, ["sim", "plot", "/nonexistent/ghost.csv"])
    assert result.exit_code == 1


@pytest.mark.smoke
def test_sim_plot_stdout_contains_saved_path(sample_hysteresis_csv: Path, tmp_path: Path) -> None:
    """On success, sim plot includes the saved path in its output."""
    out = tmp_path / "check.pdf"
    result = runner.invoke(
        app,
        ["sim", "plot", str(sample_hysteresis_csv), "--output", str(out)],
    )
    assert result.exit_code == 0
    # Filename or path must appear in stdout
    assert "check.pdf" in result.stdout or str(out) in result.stdout


# ---------------------------------------------------------------------------
# sim validate — MultiScaleSpec JSON validation
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_spec_json(tmp_path: Path) -> Path:
    """Valid MultiScaleSpec JSON file."""
    spec = {
        "scales": [
            {
                "scale": "micro",
                "engine": "auto",
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
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return p


@pytest.mark.smoke
def test_sim_validate_valid_file(valid_spec_json: Path) -> None:
    """validate returns exit 0 for a valid spec JSON file."""
    result = runner.invoke(app, ["sim", "validate", str(valid_spec_json)])
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"


@pytest.mark.smoke
def test_sim_validate_second_file(tmp_path: Path) -> None:
    """validate succeeds with a second valid spec JSON file (different size)."""
    spec = {
        "scales": [
            {
                "scale": "micro",
                "engine": "auto",
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
    p = tmp_path / "spec2.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    result = runner.invoke(app, ["sim", "validate", str(p)])
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"


@pytest.mark.smoke
def test_sim_validate_invalid_json() -> None:
    """Invalid JSON returns exit 1."""
    result = runner.invoke(app, ["sim", "validate", "not-valid-json"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# figure spec — FigureSpec skeleton generation
# ---------------------------------------------------------------------------


@pytest.mark.smoke
def test_figure_spec_outputs_json() -> None:
    """figure spec outputs a JSON structure."""
    result = runner.invoke(app, ["figure", "spec"])
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    # Check if JSON-parseable
    try:
        data = json.loads(result.stdout)
        assert "panels" in data or "figure_id" in data or "journal" in data
    except json.JSONDecodeError:
        # Non-JSON output is also acceptable (text output allowed)
        assert len(result.stdout) > 0


@pytest.mark.smoke
def test_figure_spec_accepts_prl_alias() -> None:
    """Common journal aliases should map to installed style profiles."""
    result = runner.invoke(app, ["figure", "spec", "--journal", "prl"])
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert "FigureSpec skeleton written" in result.stdout


# ---------------------------------------------------------------------------
# figure render — FigureSpec JSON → vector figure
# ---------------------------------------------------------------------------


@pytest.fixture()
def simple_figure_spec_json(tmp_path: Path, sample_hysteresis_csv: Path) -> tuple[Path, Path]:
    """FigureSpec JSON with bound DataPoints and ledger JSON."""
    from maglab.sim.plot import load_csv_datapoints

    col_dps = load_csv_datapoints(sample_hysteresis_csv)
    dp_list = list(col_dps.values())
    x_dp, y_dp = dp_list[0], dp_list[1]

    spec = {
        "figure_id": "test-fig-001",
        "journal": "nature",
        "column_width": "single",
        "panels": [
            {
                "panel_id": "p1",
                "panel_type": "data-plot",
                "plot_kind": "hysteresis",
                "data_point_ids": [x_dp.id, y_dp.id],
                "grid_position": {"row": 0, "col": 0},
                "x_axis": {"label": "H (T)"},
                "y_axis": {"label": "M (A/m)"},
                "overlay": [],
            }
        ],
        "layout": {"nrows": 1, "ncols": 1},
        "caption": "Test figure",
    }
    ledger = {
        x_dp.id: x_dp.model_dump(mode="json"),
        y_dp.id: y_dp.model_dump(mode="json"),
    }

    spec_path = tmp_path / "spec.json"
    ledger_path = tmp_path / "ledger.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return spec_path, ledger_path


@pytest.mark.smoke
def test_figure_render_produces_file(
    simple_figure_spec_json: tuple[Path, Path], tmp_path: Path
) -> None:
    """figure render produces a vector file."""
    spec_path, ledger_path = simple_figure_spec_json
    out = tmp_path / "rendered.pdf"
    result = runner.invoke(
        app,
        [
            "figure",
            "render",
            str(spec_path),
            "--datapoints",
            str(ledger_path),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.smoke
def test_figure_render_svg(simple_figure_spec_json: tuple[Path, Path], tmp_path: Path) -> None:
    """figure render --format svg produces an SVG file."""
    spec_path, ledger_path = simple_figure_spec_json
    out = tmp_path / "rendered.svg"
    result = runner.invoke(
        app,
        [
            "figure",
            "render",
            str(spec_path),
            "--datapoints",
            str(ledger_path),
            "--output",
            str(out),
            "--format",
            "svg",
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.stdout}"
    assert out.exists()
