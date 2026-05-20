"""tests/unit/test_material_builder.py — stack parsing, LayerData, and DataPoint unit tests (§14.5).

All network/API calls are mocked — zero real calls.
Includes validation that LLM-generated values are blocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maglab.physics.material_builder import (
    BuildResult,
    LayerSpec,
    _query_static,
    _raw_to_datapoints,
    build_material_stack,
    parse_stack,
    save_to_materials_yaml,
)
from maglab.provenance.datapoint import DataPoint, ProvenanceType

# ---------------------------------------------------------------------------
# LayerSpec
# ---------------------------------------------------------------------------


class TestLayerSpec:
    def test_basic(self):
        layer = LayerSpec(material="Ta", thickness_nm=5.0, order=0)
        assert layer.material == "Ta"
        assert layer.thickness_nm == pytest.approx(5.0)
        assert layer.order == 0

    def test_no_thickness(self):
        layer = LayerSpec(material="MgO", order=2)
        assert layer.thickness_nm is None


# ---------------------------------------------------------------------------
# parse_stack
# ---------------------------------------------------------------------------


class TestParseStack:
    def test_single_layer_with_thickness(self):
        layers = parse_stack("Ta(5)")
        assert len(layers) == 1
        assert layers[0].material == "Ta"
        assert layers[0].thickness_nm == pytest.approx(5.0)
        assert layers[0].order == 0

    def test_three_layer_stack(self):
        layers = parse_stack("Ta(5)/CoFeB(1)/MgO(2)")
        assert len(layers) == 3
        assert layers[0].material == "Ta"
        assert layers[1].material == "CoFeB"
        assert layers[2].material == "MgO"
        assert layers[0].thickness_nm == pytest.approx(5.0)
        assert layers[1].thickness_nm == pytest.approx(1.0)
        assert layers[2].thickness_nm == pytest.approx(2.0)

    def test_order_is_sequential(self):
        layers = parse_stack("A(1)/B(2)/C(3)")
        assert [lay.order for lay in layers] == [0, 1, 2]

    def test_layer_without_thickness(self):
        layers = parse_stack("Ta/CoFeB/MgO")
        assert all(lay.thickness_nm is None for lay in layers)
        assert len(layers) == 3

    def test_mixed_thickness(self):
        layers = parse_stack("Ta(5)/CoFeB/MgO(2)")
        assert layers[0].thickness_nm == pytest.approx(5.0)
        assert layers[1].thickness_nm is None
        assert layers[2].thickness_nm == pytest.approx(2.0)

    def test_alloy_material_name(self):
        layers = parse_stack("Ni80Fe20(5)")
        assert len(layers) == 1
        assert layers[0].material == "Ni80Fe20"

    def test_decimal_thickness(self):
        layers = parse_stack("Ta(0.5)")
        assert layers[0].thickness_nm == pytest.approx(0.5)

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_stack("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_stack("   ")

    def test_double_slash_raises(self):
        with pytest.raises(ValueError):
            parse_stack("Ta(5)//MgO(2)")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="parse failed"):
            parse_stack("Ta(5x)/CoFeB(1)")

    def test_complex_stack(self):
        # Formats like Pt(5)/[Co(0.5)/Pt(1)]x3 are not supported — simple slashes only
        layers = parse_stack("SiO2(300)/Ta(5)/CoFeB(1)/MgO(2)/Ta(3)")
        assert len(layers) == 5
        assert layers[0].material == "SiO2"

    def test_five_layer_variety(self):
        layers = parse_stack("Si(1)/SiO2(5)/Ta(3)/Py(10)/Al2O3(2)")
        assert len(layers) == 5
        materials = [lay.material for lay in layers]
        assert "Si" in materials
        assert "Py" in materials
        assert "Al2O3" in materials


# ---------------------------------------------------------------------------
# _raw_to_datapoints
# ---------------------------------------------------------------------------


class TestRawToDatapoints:
    def test_ms_am_converted_to_datapoint(self):
        raw = {"Ms_Am": 1.1e6, "alpha": 0.005, "doi": "10.1234/test"}
        points = _raw_to_datapoints(raw, "CoFeB")
        assert "Ms_Am" in points
        dp = points["Ms_Am"]
        assert isinstance(dp, DataPoint)
        assert dp.value == pytest.approx(1.1e6)
        assert dp.units == "A/m"
        assert dp.provenance_type == ProvenanceType.LITERATURE
        assert dp.source_ref == "10.1234/test"

    def test_alpha_datapoint(self):
        raw = {"alpha": 0.007, "doi": "10.9999/py"}
        points = _raw_to_datapoints(raw, "Py")
        assert "alpha" in points
        assert points["alpha"].units == "1"

    def test_missing_fields_not_included(self):
        raw = {"Ms_Am": 8.6e5}
        points = _raw_to_datapoints(raw, "Py")
        assert "Ms_Am" in points
        assert "alpha" not in points  # missing fields should not be included

    def test_source_ref_fallback_when_no_doi(self):
        raw = {"Ms_Am": 1.0e6}
        points = _raw_to_datapoints(raw, "TestMat")
        dp = points["Ms_Am"]
        assert "TestMat" in dp.source_ref  # fallback when no DOI is present

    def test_all_supported_properties(self):
        raw = {
            "Ms_Am": 1e6,
            "alpha": 0.01,
            "A_Jm": 1e-11,
            "K_Jm3": 5e4,
            "T_C_K": 1043.0,
            "density_g_cm3": 7.87,
            "g_factor": 2.09,
            "doi": "10.1234/all",
        }
        points = _raw_to_datapoints(raw, "Fe")
        assert len(points) == 7
        assert points["T_C_K"].units == "K"
        assert points["density_g_cm3"].units == "g/cm^3"


# ---------------------------------------------------------------------------
# _query_static
# ---------------------------------------------------------------------------


class TestQueryStatic:
    def test_ta_found(self):
        data = _query_static("ta")
        assert data is not None

    def test_case_insensitive(self):
        data = _query_static("TA")
        assert data is not None

    def test_py_permalloy(self):
        data = _query_static("Py")
        assert data is not None
        assert "Ms_Am" in data

    def test_unknown_material_returns_none(self):
        data = _query_static("Unobtanium123")
        assert data is None

    def test_mgo_has_doi(self):
        data = _query_static("MgO")
        assert data is not None
        assert "doi" in data
        assert data["doi"]


# ---------------------------------------------------------------------------
# build_material_stack (mocked sources)
# ---------------------------------------------------------------------------


class TestBuildMaterialStack:
    def test_basic_ta_cofeb_mgo_stack(self):
        """Ta(5)/CoFeB(1)/MgO(2) stack — looked up from static bundle."""
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("Ta(5)/CoFeB(1)/MgO(2)", use_mp=False)

        assert result.stack_str == "Ta(5)/CoFeB(1)/MgO(2)"
        assert len(result.layers) == 3

        # verify Ta layer
        ta_layer = result.layers[0]
        assert ta_layer.layer.material == "Ta"
        assert ta_layer.layer.thickness_nm == pytest.approx(5.0)
        assert ta_layer.source_info in ("static_bundle", "nemad_csv", "materials_project", "")

    def test_all_three_layers_parsed(self):
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("Ta(5)/CoFeB(1)/MgO(2)", use_mp=False)
        materials = [ld.layer.material for ld in result.layers]
        assert "Ta" in materials
        assert "CoFeB" in materials
        assert "MgO" in materials

    def test_datapoints_have_dois_when_available(self):
        """DataPoints that have a source should carry a DOI/source_ref."""
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("CoFeB(1)", use_mp=False)

        cofeb_layer = result.layers[0]
        for dp in cofeb_layer.datapoints.values():
            assert dp.source_ref, f"DataPoint missing source_ref: {dp}"

    def test_no_llm_generated_values(self):
        """build_material_stack must not include LLM-generated values (§3.3)."""
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("Ta(5)/CoFeB(1)/MgO(2)", use_mp=False)
        assert result.has_llm_generated_values() is False

    def test_unknown_material_generates_warning(self):
        """Materials with no data should produce a warning."""
        with (
            patch("maglab.physics.material_builder._query_nemad", return_value=None),
            patch("maglab.physics.material_builder._query_static", return_value=None),
            patch("maglab.physics.material_builder._query_materials_project", return_value=None),
        ):
            result = build_material_stack("Unobtanium(5)/CoFeB(1)", use_mp=True)

        # Unobtanium layer should have a warning
        unobt = next((ld for ld in result.layers if ld.layer.material == "Unobtanium"), None)
        assert unobt is not None
        assert len(unobt.warnings) > 0

    def test_materials_project_mock(self):
        """MP API mock — verify DataPoint creation on response."""
        mp_response = {
            "formula": "Ta",
            "density_g_cm3": 16.69,
            "doi": "10.1063/1.4812323",
            "source": "materials_project",
        }
        with (
            patch("maglab.physics.material_builder._query_nemad", return_value=None),
            patch("maglab.physics.material_builder._query_static", return_value=None),
            patch(
                "maglab.physics.material_builder._query_materials_project",
                return_value=mp_response,
            ),
        ):
            result = build_material_stack("Ta(5)", use_mp=True)

        ta = result.layers[0]
        assert ta.source_info == "materials_project"
        assert "density_g_cm3" in ta.datapoints

    def test_invalid_stack_raises_value_error(self):
        with pytest.raises(ValueError):
            build_material_stack("Ta(5)//CoFeB(1)")

    def test_all_datapoints_are_literature_type(self):
        """All DataPoints must be of LITERATURE type (DB lookup)."""
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("CoFeB(1)/Py(5)", use_mp=False)

        for layer_data in result.layers:
            for dp in layer_data.datapoints.values():
                assert dp.provenance_type == ProvenanceType.LITERATURE, (
                    f"{layer_data.layer.material} DataPoint is not LITERATURE type: {dp.provenance_type}"
                )

    def test_five_stack_parsing(self):
        """Verify accurate parsing of a 5-layer stack."""
        with (
            patch("maglab.physics.material_builder._query_nemad", return_value=None),
        ):
            result = build_material_stack("Si(1)/SiO2(5)/Ta(3)/Py(10)/Al2O3(2)", use_mp=False)
        assert len(result.layers) == 5

    def test_all_datapoints_values_are_floats(self):
        """DataPoint values must be float (no guessed string values)."""
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("Py(10)", use_mp=False)
        py_layer = result.layers[0]
        for name, dp in py_layer.datapoints.items():
            assert isinstance(dp.value, float), f"{name} value is not float"


# ---------------------------------------------------------------------------
# BuildResult
# ---------------------------------------------------------------------------


class TestBuildResult:
    def test_all_datapoints_dict(self):
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("CoFeB(1)/MgO(2)", use_mp=False)
        all_dp = result.all_datapoints()
        assert isinstance(all_dp, dict)
        assert "CoFeB" in all_dp or "MgO" in all_dp

    def test_has_llm_generated_values_always_false(self):
        result = BuildResult(stack_str="test")
        assert result.has_llm_generated_values() is False


# ---------------------------------------------------------------------------
# save_to_materials_yaml
# ---------------------------------------------------------------------------


class TestSaveToMaterialsYaml:
    def test_saves_yaml_file(self, tmp_path: Path):
        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("CoFeB(1)", use_mp=False)
        yaml_path = tmp_path / "test_materials.yaml"
        out = save_to_materials_yaml(result, yaml_path=yaml_path)
        assert out == yaml_path
        assert yaml_path.is_file()

    def test_yaml_contains_material(self, tmp_path: Path):
        import yaml  # type: ignore[import-untyped]

        with patch("maglab.physics.material_builder._query_nemad", return_value=None):
            result = build_material_stack("Py(10)", use_mp=False)
        yaml_path = tmp_path / "mat.yaml"
        save_to_materials_yaml(result, yaml_path=yaml_path)

        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        assert "materials" in data
        entries = data["materials"]
        assert any(e.get("id") == "Py" for e in entries)
