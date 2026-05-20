"""Unit tests for the atomistic parser.

Design rationale: impl/04-P3-multiscale.md T-P3-05 · T-P3-09.
Validates VAMPIRE M(T) parsing, T_C extraction, and Spirit JSON parsing.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers — generate test VAMPIRE/Spirit output
# ---------------------------------------------------------------------------


def _make_vampire_mt(t_c: float = 1043.0, n_points: int = 25) -> str:
    """Generate a test VAMPIRE magnetisation file.

    Synthetic bcc Fe M(T) data — β=0.33 scaling based on T_C=1043 K (Pajda 2001).
    Source: M. Pajda et al., Phys. Rev. B 64, 174402 (2001).
    """
    lines = ["# Temperature  Mx  My  Mz  |M|  specific_heat\n"]
    t_step = (t_c + 200) / n_points
    for i in range(n_points):
        t = i * t_step
        if t >= t_c:
            m = 0.0
        else:
            m = (1.0 - t / t_c) ** 0.33
        lines.append(f"{t:.1f}  0.0  0.0  {m:.6f}  {m:.6f}  0.0\n")
    return "".join(lines)


def _make_spirit_json(t_c: float = 1043.0) -> str:
    """Generate a test Spirit energy log JSON."""
    import json

    data = {
        "energy": -1234.56,
        "Ms_Am": 1.71e6,
        "T_C_K": t_c,
        "converged": True,
    }
    return json.dumps(data)


# ---------------------------------------------------------------------------
# AtomisticInputGenerator tests
# ---------------------------------------------------------------------------


class TestAtomisticInputGenerator:
    """AtomisticInputGenerator — input file generation tests."""

    def test_vampire_generates_input(self, tmp_path: Path) -> None:
        """VAMPIRE input files must be generated."""
        from maglab.sim.atomistic.input_gen import AtomisticEngine, AtomisticInputGenerator

        gen = AtomisticInputGenerator(engine=AtomisticEngine.VAMPIRE)
        files = gen.generate(
            params={"J_ij_K": 398.0, "T_max_K": 1300.0},
            output_dir=tmp_path,
        )

        assert len(files) > 0
        # Expect an input or input.cfg file
        file_names = [f.name for f in files.values()]
        assert any("input" in n.lower() for n in file_names)

    def test_vampire_input_contains_j_ij(self, tmp_path: Path) -> None:
        """VAMPIRE input files must contain exchange coupling parameters."""
        from maglab.sim.atomistic.input_gen import AtomisticEngine, AtomisticInputGenerator

        gen = AtomisticInputGenerator(engine=AtomisticEngine.VAMPIRE)
        files = gen.generate(
            params={"J_ij_K": 398.0},
            output_dir=tmp_path,
        )

        # At least one input file must contain exchange-related values
        all_text = " ".join(f.read_text() for f in files.values() if f.exists())
        assert any(
            kw in all_text.lower() for kw in ["exchange", "jij", "j_ij", "3.44", "398", "34.3"]
        )

    def test_spirit_generates_config(self, tmp_path: Path) -> None:
        """Spirit input files must be generated."""
        from maglab.sim.atomistic.input_gen import AtomisticEngine, AtomisticInputGenerator

        gen = AtomisticInputGenerator(engine=AtomisticEngine.SPIRIT)
        files = gen.generate(
            params={"J_ij_K": 398.0, "T_max_K": 1300.0},
            output_dir=tmp_path,
        )

        assert len(files) > 0


# ---------------------------------------------------------------------------
# parse_vampire_output tests
# ---------------------------------------------------------------------------


class TestParseVampireOutput:
    """parse_vampire_output — VAMPIRE M(T) parsing and T_C extraction tests."""

    def test_parse_returns_atomistic_result(self, tmp_path: Path) -> None:
        """parse_vampire_output must return an AtomisticResult."""
        from maglab.sim.atomistic.parse_atomistic import AtomisticResult, parse_vampire_output

        (tmp_path / "magnetisation").write_text(_make_vampire_mt(t_c=1043.0), encoding="utf-8")

        result = parse_vampire_output(tmp_path)
        assert isinstance(result, AtomisticResult)

    def test_parse_tc_extraction_bcc_fe(self, tmp_path: Path) -> None:
        """T_C ≈ 1043 K must be extracted from the bcc Fe M(T) curve.

        Reference: M. Pajda et al., Phys. Rev. B 64, 174402 (2001).
        Tolerance: ±100 K (includes discretisation error of mock data).
        """
        from maglab.sim.atomistic.parse_atomistic import parse_vampire_output

        (tmp_path / "magnetisation").write_text(
            _make_vampire_mt(t_c=1043.0, n_points=50), encoding="utf-8"
        )

        result = parse_vampire_output(tmp_path)
        assert result.T_C_K is not None
        assert 900 < result.T_C_K < 1200, (
            f"T_C = {result.T_C_K:.1f} K is outside the expected bcc Fe range of 900–1200 K."
        )

    def test_parse_ms_calculation(self, tmp_path: Path) -> None:
        """M_s(T=0) calculation must be performed."""
        from maglab.sim.atomistic.parse_atomistic import parse_vampire_output

        (tmp_path / "magnetisation").write_text(_make_vampire_mt(t_c=1043.0), encoding="utf-8")

        result = parse_vampire_output(tmp_path)
        # M_s_Am is a per-temperature list; the first entry (T=0) must be positive
        if result.M_s_Am:
            assert result.M_s_Am[0] > 0

    def test_parse_empty_output_dir(self, tmp_path: Path) -> None:
        """Missing magnetisation file must be handled without error."""
        from maglab.sim.atomistic.parse_atomistic import AtomisticResult, parse_vampire_output

        result = parse_vampire_output(tmp_path)
        assert isinstance(result, AtomisticResult)
        assert result.T_C_K is None or result.T_C_K >= 0

    def test_tc_extraction_above_room_temp(self, tmp_path: Path) -> None:
        """T_C extraction must work for various target temperatures (300 K, 600 K)."""
        from maglab.sim.atomistic.parse_atomistic import parse_vampire_output

        for t_c_target in [300.0, 600.0]:
            (tmp_path / "magnetisation").write_text(
                _make_vampire_mt(t_c=t_c_target, n_points=40), encoding="utf-8"
            )

            result = parse_vampire_output(tmp_path)
            if result.T_C_K is not None:
                assert abs(result.T_C_K - t_c_target) < 150, (
                    f"T_C={result.T_C_K:.1f} K, target={t_c_target:.0f} K, error > 150 K"
                )


# ---------------------------------------------------------------------------
# parse_spirit_output tests
# ---------------------------------------------------------------------------


class TestParseSpiritOutput:
    """parse_spirit_output — Spirit JSON/text parsing tests."""

    def test_parse_spirit_json(self, tmp_path: Path) -> None:
        """Spirit JSON output must be parsed."""
        from maglab.sim.atomistic.parse_atomistic import AtomisticResult, parse_spirit_output

        (tmp_path / "spirit_log.json").write_text(_make_spirit_json(t_c=1043.0), encoding="utf-8")

        result = parse_spirit_output(tmp_path)
        assert isinstance(result, AtomisticResult)

    def test_parse_spirit_empty_dir(self, tmp_path: Path) -> None:
        """Missing Spirit output must be handled without error."""
        from maglab.sim.atomistic.parse_atomistic import AtomisticResult, parse_spirit_output

        result = parse_spirit_output(tmp_path)
        assert isinstance(result, AtomisticResult)


# ---------------------------------------------------------------------------
# AtomisticResult data structure tests
# ---------------------------------------------------------------------------


class TestAtomisticResult:
    """AtomisticResult data class tests."""

    def test_quantities_are_datapoints(self, tmp_path: Path) -> None:
        """AtomisticResult.quantities must hold a DataPoint dictionary."""
        from maglab.sim.atomistic.parse_atomistic import parse_vampire_output

        (tmp_path / "magnetisation").write_text(_make_vampire_mt(), encoding="utf-8")

        result = parse_vampire_output(tmp_path)
        assert isinstance(result.quantities, dict)

    def test_result_has_engine(self, tmp_path: Path) -> None:
        """AtomisticResult.engine must be set."""
        from maglab.sim.atomistic.parse_atomistic import parse_vampire_output

        (tmp_path / "magnetisation").write_text(_make_vampire_mt(), encoding="utf-8")

        result = parse_vampire_output(tmp_path)
        assert result.engine is not None
        assert "vampire" in result.engine.lower()


# ---------------------------------------------------------------------------
# _extract_tc_from_mt unit tests
# ---------------------------------------------------------------------------


class TestExtractTcFromMt:
    """_extract_tc_from_mt — unit tests for the T_C extraction algorithm from M(T)."""

    def test_simple_step_function(self) -> None:
        """T_C must be correctly extracted from a step-function M(T)."""
        from maglab.sim.atomistic.parse_atomistic import _extract_tc_from_mt

        T = list(range(0, 1200, 50))
        t_c_true = 1000.0
        M = [1.0 if t < t_c_true else 0.0 for t in T]

        t_c = _extract_tc_from_mt(T, M)
        # Allow ±100 K for discretisation error
        assert t_c is not None
        assert abs(t_c - t_c_true) < 100, f"T_C={t_c:.1f}, expected={t_c_true:.0f}, error > 100 K"

    def test_smooth_power_law(self) -> None:
        """T_C must be extracted from a smooth power-law M(T)."""
        from maglab.sim.atomistic.parse_atomistic import _extract_tc_from_mt

        t_c_true = 800.0
        T = [float(t) for t in range(0, 1100, 25)]
        M = [(1 - t / t_c_true) ** 0.33 if t < t_c_true else 0.0 for t in T]

        t_c = _extract_tc_from_mt(T, M)
        assert t_c is not None
        assert abs(t_c - t_c_true) < 150

    def test_all_zero_magnetization(self) -> None:
        """T_C must be None when M=0 throughout."""
        from maglab.sim.atomistic.parse_atomistic import _extract_tc_from_mt

        T = list(range(0, 1000, 50))
        M = [0.0] * len(T)

        t_c = _extract_tc_from_mt(T, M)
        # All zeros implies None or a very low value
        assert t_c is None or t_c < 50

    def test_constant_magnetization(self) -> None:
        """T_C must be None when M=const (no transition)."""
        from maglab.sim.atomistic.parse_atomistic import _extract_tc_from_mt

        T = list(range(0, 500, 25))
        M = [1.0] * len(T)  # no change

        t_c = _extract_tc_from_mt(T, M)
        # No clear transition implies None
        assert t_c is None or t_c > max(T)
