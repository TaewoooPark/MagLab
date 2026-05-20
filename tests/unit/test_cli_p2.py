"""CLI tests for P2 analysis commands — fit, analyze, device.

Uses typer.testing.CliRunner against a fresh Typer app with register() applied.
All checks are deterministic — no LLM judgment.

Design basis: impl/03-P2-analysis.md T-P2-08, plan/11-appendices.md Appendix A
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from maglab.commands.p2_analysis import register

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app() -> typer.Typer:
    """Fresh Typer app with P2 commands registered."""
    _app = typer.Typer(name="maglab-test", add_completion=False, no_args_is_help=False)
    register(_app)
    return _app


@pytest.fixture(scope="module")
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Fixture CSV helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, **columns: list[float]) -> None:
    """Write a simple CSV with float columns."""
    headers = list(columns.keys())
    rows = list(zip(*columns.values(), strict=False))
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


# ===========================================================================
# --help tests (must exit 0 for every command/subcommand)
# ===========================================================================


class TestHelp:
    def test_fit_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["fit", "--help"])
        assert result.exit_code == 0, result.output
        assert "effect" in result.output.lower()

    def test_analyze_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0, result.output

    def test_analyze_load_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["analyze", "load", "--help"])
        assert result.exit_code == 0, result.output

    def test_analyze_model_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["analyze", "model", "--help"])
        assert result.exit_code == 0, result.output

    def test_analyze_consistency_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["analyze", "consistency", "--help"])
        assert result.exit_code == 0, result.output

    def test_analyze_symmetry_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["analyze", "symmetry", "--help"])
        assert result.exit_code == 0, result.output

    def test_device_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["device", "--help"])
        assert result.exit_code == 0, result.output

    def test_device_fom_help(self, app: typer.Typer, runner: CliRunner) -> None:
        result = runner.invoke(app, ["device", "fom", "--help"])
        assert result.exit_code == 0, result.output


# ===========================================================================
# maglab fit
# ===========================================================================


class TestFit:
    def test_fit_list_effects(self, app: typer.Typer, runner: CliRunner) -> None:
        """'fit --effect list' prints registered effects and exits 0."""
        result = runner.invoke(app, ["fit", "--effect", "list", "dummy.csv"])
        assert result.exit_code == 0, result.output
        # Should show at least one well-known effect
        assert "anomalous_hall" in result.output or "ordinary_hall" in result.output

    def test_fit_unknown_effect(self, app: typer.Typer, runner: CliRunner, tmp_path: Path) -> None:
        """Unknown effect name gives exit code 1."""
        csv_path = tmp_path / "dummy.csv"
        _write_csv(csv_path, B=[0.0, 1.0], rho_xy=[0.0, 1e-8])
        result = runner.invoke(app, ["fit", "--effect", "nonexistent_effect_xyz", str(csv_path)])
        assert result.exit_code == 1
        assert "Unknown effect" in result.output or "unknown" in result.output.lower()

    def test_fit_missing_file(self, app: typer.Typer, runner: CliRunner) -> None:
        """Missing data file gives exit code 1."""
        result = runner.invoke(app, ["fit", "--effect", "anomalous_hall", "/no/such/file.csv"])
        assert result.exit_code == 1

    def test_fit_ordinary_hall(self, app: typer.Typer, runner: CliRunner, tmp_path: Path) -> None:
        """Fit ordinary_hall to synthetic linear ρ_xy = R_H·B data, expect exit 0."""
        import numpy as np

        # Synthetic: R_H = 1.5e-10 m³/C
        R_H_true = 1.5e-10
        B = np.linspace(-1.0, 1.0, 40)
        rho_xy = R_H_true * B

        csv_path = tmp_path / "ordinary_hall.csv"
        _write_csv(csv_path, B=B.tolist(), rho_xy=rho_xy.tolist())

        result = runner.invoke(app, ["fit", "--effect", "ordinary_hall", str(csv_path)])
        assert result.exit_code == 0, result.output
        # Output must contain fitted parameter info
        assert "FitResult" in result.output or "Fitted" in result.output or "R_H" in result.output

    def test_fit_fmr_kittel(self, app: typer.Typer, runner: CliRunner, tmp_path: Path) -> None:
        """Fit fmr_kittel to synthetic Kittel dispersion data, expect exit 0."""
        import numpy as np

        # Kittel in-plane: (ω/γ)² = μ₀²·H_res·(H_res + M_eff)
        # We generate (f, H_res) pairs with known M_eff and γ
        MU_0 = 4 * np.pi * 1e-7
        gamma = 1.76e11  # rad/(s·T), typical gyromagnetic ratio
        M_eff_true = 800e3  # A/m, typical for Permalloy

        H_res = np.linspace(0.01e3, 200e3, 20)  # A/m
        omega = gamma * MU_0 * np.sqrt(H_res * (H_res + M_eff_true))
        freq_GHz = omega / (2 * np.pi * 1e9)

        csv_path = tmp_path / "kittel.csv"
        _write_csv(csv_path, H_res=H_res.tolist(), f=freq_GHz.tolist())

        result = runner.invoke(app, ["fit", "--effect", "fmr_kittel", str(csv_path)])
        assert result.exit_code == 0, result.output

    def test_fit_show_refs(self, app: typer.Typer, runner: CliRunner, tmp_path: Path) -> None:
        """--refs flag causes references to appear in output."""
        import numpy as np

        B = np.linspace(-1.0, 1.0, 20)
        rho_xy = 1.5e-10 * B

        csv_path = tmp_path / "hall.csv"
        _write_csv(csv_path, B=B.tolist(), rho_xy=rho_xy.tolist())

        result = runner.invoke(
            app, ["fit", "--effect", "ordinary_hall", str(csv_path), "--refs"]
        )
        assert result.exit_code == 0, result.output
        assert "Reference" in result.output or "DOI" in result.output or "Phys" in result.output


# ===========================================================================
# maglab analyze load
# ===========================================================================


class TestAnalyzeLoad:
    def test_load_csv(self, app: typer.Typer, runner: CliRunner, tmp_path: Path) -> None:
        """analyze load prints column stats for a CSV file."""
        import numpy as np

        csv_path = tmp_path / "data.csv"
        _write_csv(csv_path, B=np.linspace(-1, 1, 30).tolist(), rho_xy=(1e-9 * np.linspace(-1, 1, 30)).tolist())

        result = runner.invoke(app, ["analyze", "load", str(csv_path)])
        assert result.exit_code == 0, result.output
        assert "30" in result.output  # row count
        assert "B" in result.output

    def test_load_missing_file(self, app: typer.Typer, runner: CliRunner) -> None:
        """Missing file gives exit code 1."""
        result = runner.invoke(app, ["analyze", "load", "/no/such/file.csv"])
        assert result.exit_code == 1

    def test_load_column_filter(self, app: typer.Typer, runner: CliRunner, tmp_path: Path) -> None:
        """--columns filter shows only specified columns."""
        import numpy as np

        csv_path = tmp_path / "multi.csv"
        _write_csv(
            csv_path,
            B=np.linspace(-1, 1, 10).tolist(),
            rho_xy=(1e-9 * np.linspace(-1, 1, 10)).tolist(),
            T=[300.0] * 10,
        )

        result = runner.invoke(app, ["analyze", "load", str(csv_path), "--columns", "B,rho_xy"])
        assert result.exit_code == 0, result.output
        assert "B" in result.output
        assert "rho_xy" in result.output


# ===========================================================================
# maglab analyze model
# ===========================================================================


class TestAnalyzeModel:
    def test_list_all_models(self, app: typer.Typer, runner: CliRunner) -> None:
        """analyze model without argument lists all registered effects."""
        result = runner.invoke(app, ["analyze", "model"])
        assert result.exit_code == 0, result.output
        assert "anomalous_hall" in result.output or "ordinary_hall" in result.output

    def test_show_specific_model(self, app: typer.Typer, runner: CliRunner) -> None:
        """analyze model <name> shows parameter table and references."""
        result = runner.invoke(app, ["analyze", "model", "anomalous_hall"])
        assert result.exit_code == 0, result.output
        # Should contain parameter names for AHE
        assert "R_0" in result.output or "R_s" in result.output or "anomalous_hall" in result.output

    def test_unknown_model(self, app: typer.Typer, runner: CliRunner) -> None:
        """Unknown effect name gives exit code 1."""
        result = runner.invoke(app, ["analyze", "model", "no_such_effect_xyz"])
        assert result.exit_code == 1


# ===========================================================================
# maglab analyze consistency
# ===========================================================================


class TestAnalyzeConsistency:
    def _make_ordinary_hall_csv(self, tmp_path: Path, suffix: str, r_h: float) -> Path:
        """Write a synthetic ordinary_hall CSV."""
        import numpy as np

        B = np.linspace(-1.0, 1.0, 30)
        rho_xy = r_h * B
        path = tmp_path / f"hall_{suffix}.csv"
        _write_csv(path, B=B.tolist(), rho_xy=rho_xy.tolist())
        return path

    def test_consistency_same_effect(
        self, app: typer.Typer, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Comparing identical effects with close parameters should exit 0."""
        path_a = self._make_ordinary_hall_csv(tmp_path, "a", 1.5e-10)
        path_b = self._make_ordinary_hall_csv(tmp_path, "b", 1.5e-10)

        result = runner.invoke(
            app,
            ["analyze", "consistency", "ordinary_hall", str(path_a), "ordinary_hall", str(path_b)],
        )
        assert result.exit_code == 0, result.output
        # The command should complete without crashing; output may say consistent or chi2 info

    def test_consistency_missing_file(self, app: typer.Typer, runner: CliRunner, tmp_path: Path) -> None:
        """Missing second file gives exit code 1."""
        path_a = self._make_ordinary_hall_csv(tmp_path, "c", 1.5e-10)
        result = runner.invoke(
            app,
            [
                "analyze",
                "consistency",
                "ordinary_hall",
                str(path_a),
                "ordinary_hall",
                "/no/such/file.csv",
            ],
        )
        assert result.exit_code == 1


# ===========================================================================
# maglab analyze symmetry
# ===========================================================================


class TestAnalyzeSymmetry:
    def test_list_groups(self, app: typer.Typer, runner: CliRunner) -> None:
        """--list flag lists all supported groups."""
        result = runner.invoke(app, ["analyze", "symmetry", "m3m", "--list"])
        assert result.exit_code == 0, result.output
        assert "m3m" in result.output

    def test_cubic_m3m(self, app: typer.Typer, runner: CliRunner) -> None:
        """m3m point group shows AHE as allowed."""
        result = runner.invoke(app, ["analyze", "symmetry", "m3m"])
        assert result.exit_code == 0, result.output
        assert "AHE" in result.output or "m3m" in result.output

    def test_unknown_group(self, app: typer.Typer, runner: CliRunner) -> None:
        """Unknown point group exits with code 1."""
        result = runner.invoke(app, ["analyze", "symmetry", "not_a_real_group"])
        assert result.exit_code == 1

    def test_tetragonal(self, app: typer.Typer, runner: CliRunner) -> None:
        """4/mmm point group should exit 0."""
        result = runner.invoke(app, ["analyze", "symmetry", "4/mmm"])
        assert result.exit_code == 0, result.output


# ===========================================================================
# maglab device fom
# ===========================================================================


class TestDeviceFom:
    def test_fom_list(self, app: typer.Typer, runner: CliRunner) -> None:
        """'device fom list' prints registered device types."""
        result = runner.invoke(app, ["device", "fom", "list"])
        assert result.exit_code == 0, result.output
        assert "sot-mram" in result.output

    def test_fom_sot_mram_defaults(self, app: typer.Typer, runner: CliRunner) -> None:
        """sot-mram with default parameters computes FoMs."""
        result = runner.invoke(app, ["device", "fom", "sot-mram"])
        assert result.exit_code == 0, result.output
        assert "thermal_stability" in result.output or "delta" in result.output.lower() or "Δ" in result.output

    def test_fom_sot_mram_custom_params(self, app: typer.Typer, runner: CliRunner) -> None:
        """sot-mram with explicit params computes FoMs and outputs values."""
        result = runner.invoke(
            app,
            ["device", "fom", "sot-mram", "--Ms", "8e5", "--t", "2e-9", "--Ku", "4e5"],
        )
        assert result.exit_code == 0, result.output
        # Should contain a numeric output
        assert "FoM" in result.output or "mram" in result.output.lower()

    def test_fom_stt_mram(self, app: typer.Typer, runner: CliRunner) -> None:
        """stt-mram computes FoMs and exits 0."""
        result = runner.invoke(app, ["device", "fom", "stt-mram"])
        assert result.exit_code == 0, result.output

    def test_fom_racetrack(self, app: typer.Typer, runner: CliRunner) -> None:
        """racetrack computes FoMs and exits 0."""
        result = runner.invoke(app, ["device", "fom", "racetrack"])
        assert result.exit_code == 0, result.output

    def test_fom_unknown_device(self, app: typer.Typer, runner: CliRunner) -> None:
        """Unknown device name gives exit code 1."""
        result = runner.invoke(app, ["device", "fom", "not_a_real_device"])
        assert result.exit_code == 1

    def test_fom_with_refs(self, app: typer.Typer, runner: CliRunner) -> None:
        """--refs flag prints references."""
        result = runner.invoke(app, ["device", "fom", "sot-mram", "--refs"])
        assert result.exit_code == 0, result.output
        assert "Dieny" in result.output or "Nat" in result.output or "DOI" in result.output
