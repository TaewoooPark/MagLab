"""tests/unit/test_figure_schematic.py — Schematic renderer and SVG→PDF tests.

Validation items (§20):
- SchematicRenderer.render_panel(): returns valid SVG XML.
- Combining 2 or more primitives works correctly.
- SVG → PDF conversion (cairosvg fallback path).
- Empty registry returns empty SVG (no error).
- Provenance comment is included.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from maglab.figure.primitives.spec import PrimitiveRegistry
from maglab.figure.renderers.schematic import (
    SchematicRenderer,
    _build_placement_plan,
    _extract_svg_body,
    assemble_svg,
    svg_to_pdf,
)
from maglab.figure.spec import PanelSpec, PanelType

# ---------------------------------------------------------------------------
# Dummy primitives (for testing)
# ---------------------------------------------------------------------------


class _DummyPrimitive:
    """Dummy Primitive for testing."""

    name: str = "dummy-prim"
    category: str = "test"
    tags: list[str] = ["test", "dummy"]
    description: str = "Dummy primitive for testing."
    parameters: list[dict[str, Any]] = [
        {"name": "width", "type": "float", "default": 50.0, "description": "Width"},
    ]
    physics_convention: str = "For testing."
    references: list[str] = []
    provenance: dict[str, Any] = {"source": "test"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        w = float(params.get("width", 50.0))
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="40">'
            f'<rect width="{w}" height="40" fill="#AAA"/>'
            f"</svg>"
        )


class _DummyPrimitive2:
    """Second dummy primitive for testing."""

    name: str = "dummy-prim-2"
    category: str = "test"
    tags: list[str] = ["test", "second"]
    description: str = "Second dummy primitive for testing."
    parameters: list[dict[str, Any]] = []
    physics_convention: str = "For testing."
    references: list[str] = []
    provenance: dict[str, Any] = {"source": "test"}
    preview: str | None = None
    journal_styles: list[str] = ["nature"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="40"><circle cx="30" cy="20" r="20" fill="#CCC"/></svg>'


def _make_registry(*primitives: Any) -> PrimitiveRegistry:
    """Create a registry populated with dummy primitives."""
    reg = PrimitiveRegistry()
    for p in primitives:
        reg.register(p)
    return reg


def _make_schematic_panel(panel_id: str = "p1", query: str = "test dummy") -> PanelSpec:
    """Create a schematic panel spec for testing."""
    return PanelSpec(
        panel_id=panel_id,
        panel_type=PanelType.SCHEMATIC,
        extra={"query": query},
    )


# ---------------------------------------------------------------------------
# SVG helper function tests
# ---------------------------------------------------------------------------


class TestSvgHelpers:
    def test_extract_svg_body_full_doc(self) -> None:
        """Extract body from a complete SVG document."""
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
        body = _extract_svg_body(svg)
        assert "<rect" in body
        assert "<svg" not in body

    def test_extract_svg_body_no_tag(self) -> None:
        """Without SVG tag, the original text is returned."""
        raw = "<rect width='10' height='10'/>"
        body = _extract_svg_body(raw)
        assert "<rect" in body

    def test_build_placement_plan_single(self) -> None:
        """Placement plan for a single primitive."""
        dummy = _DummyPrimitive()
        plan = _build_placement_plan([(dummy, {})], canvas_width=200.0, canvas_height=150.0)
        assert len(plan) == 1
        _, _, x, y = plan[0]
        assert x >= 0
        assert y >= 0

    def test_build_placement_plan_multiple(self) -> None:
        """Multiple primitives are placed left to right."""
        dummy1 = _DummyPrimitive()
        dummy2 = _DummyPrimitive2()
        plan = _build_placement_plan(
            [(dummy1, {}), (dummy2, {})], canvas_width=200.0, canvas_height=150.0
        )
        assert len(plan) == 2
        x1 = plan[0][2]
        x2 = plan[1][2]
        assert x2 > x1

    def test_build_placement_plan_empty(self) -> None:
        """Empty input returns an empty plan."""
        plan = _build_placement_plan([], canvas_width=200.0, canvas_height=150.0)
        assert plan == []


class TestAssembleSvg:
    def test_assemble_single_primitive(self) -> None:
        """Assemble SVG with a single primitive."""
        dummy = _DummyPrimitive()
        svg = assemble_svg([(dummy, {"width": 30.0})], width_mm=89.0, height_mm=60.0)
        assert "<?xml" in svg
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_assemble_multiple_primitives(self) -> None:
        """Assembled SVG with two primitives."""
        d1 = _DummyPrimitive()
        d2 = _DummyPrimitive2()
        svg = assemble_svg([(d1, {}), (d2, {})], width_mm=89.0, height_mm=60.0)
        assert "<g transform=" in svg

    def test_assemble_provenance_comment(self) -> None:
        """Provenance comment is included."""
        d = _DummyPrimitive()
        svg = assemble_svg([(d, {})], provenance="test-panel")
        assert "test-panel" in svg

    def test_assemble_empty(self) -> None:
        """Empty primitive list returns header and footer only."""
        svg = assemble_svg([], width_mm=89.0, height_mm=60.0)
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_assemble_valid_xml(self) -> None:
        """Assembled SVG is valid XML."""
        import xml.etree.ElementTree as ET

        d = _DummyPrimitive()
        svg = assemble_svg([(d, {})], width_mm=89.0, height_mm=60.0)
        # Check that XML parsing succeeds
        try:
            ET.fromstring(svg)
            xml_ok = True
        except ET.ParseError:
            xml_ok = False
        assert xml_ok, f"SVG is not valid XML:\n{svg[:300]}"


# ---------------------------------------------------------------------------
# SchematicRenderer tests
# ---------------------------------------------------------------------------


class TestSchematicRenderer:
    def test_render_panel_returns_svg_string(self) -> None:
        """render_panel() returns an SVG string."""
        reg = _make_registry(_DummyPrimitive())
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel(query="test")
        svg = renderer.render_panel(panel)
        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_render_panel_empty_registry(self) -> None:
        """Empty registry returns empty SVG (no error)."""
        reg = PrimitiveRegistry()
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel(query="nonexistent")
        svg = renderer.render_panel(panel)
        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_render_panel_two_primitives_combined(self) -> None:
        """Two primitives are combined (when query matches)."""
        d1 = _DummyPrimitive()
        d2 = _DummyPrimitive2()
        reg = _make_registry(d1, d2)
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel(query="test")
        svg = renderer.render_panel(panel)
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_render_panel_provenance_comment(self) -> None:
        """SVG includes a provenance comment."""
        reg = _make_registry(_DummyPrimitive())
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel(panel_id="test_panel", query="test")
        svg = renderer.render_panel(panel)
        assert "test_panel" in svg or "MagLab" in svg

    def test_render_to_file_svg(self, tmp_path: Path) -> None:
        """Export to SVG file."""
        reg = _make_registry(_DummyPrimitive())
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel()
        out = tmp_path / "output.svg"
        result_path = renderer.render_to_file(panel, out, fmt="svg")
        assert result_path.is_file()
        content = result_path.read_text(encoding="utf-8")
        assert "<svg" in content

    def test_render_to_file_invalid_format(self, tmp_path: Path) -> None:
        """Unsupported format raises ValueError."""
        reg = _make_registry(_DummyPrimitive())
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel()
        with pytest.raises(ValueError, match="format"):
            renderer.render_to_file(panel, tmp_path / "out.xyz", fmt="xyz")

    def test_render_panel_with_llm_layout_fn(self) -> None:
        """LLM layout function is called when present."""
        d = _DummyPrimitive()
        reg = _make_registry(d)

        called = [False]

        def mock_layout_fn(query: str, candidates: list[dict]) -> list[tuple[str, dict]]:
            called[0] = True
            return [("dummy-prim", {"width": 40.0})]

        renderer = SchematicRenderer(registry=reg, llm_layout_fn=mock_layout_fn)
        panel = _make_schematic_panel(query="test")
        svg = renderer.render_panel(panel)
        assert called[0] is True
        assert "<svg" in svg

    def test_render_panel_llm_layout_fallback_on_error(self) -> None:
        """Fallback is used when the LLM layout function raises an error."""
        d = _DummyPrimitive()
        reg = _make_registry(d)

        def bad_layout_fn(query: str, candidates: list[dict]) -> list[tuple[str, dict]]:
            raise RuntimeError("LLM error")

        renderer = SchematicRenderer(registry=reg, llm_layout_fn=bad_layout_fn)
        panel = _make_schematic_panel(query="test")
        # Returns fallback SVG without error
        svg = renderer.render_panel(panel)
        assert "<svg" in svg


# ---------------------------------------------------------------------------
# SVG → PDF conversion tests
# ---------------------------------------------------------------------------


def _mock_cairosvg(output_path_kwarg: str) -> Any:
    """Create a cairosvg module mock (for environments without libcairo)."""
    import types

    def _fake_svg2pdf(**kwargs: Any) -> None:
        write_to = kwargs.get(output_path_kwarg, "")
        if write_to:
            Path(str(write_to)).write_bytes(b"%PDF-1.4 fake")

    mock_module = types.ModuleType("cairosvg")
    mock_module.svg2pdf = _fake_svg2pdf  # type: ignore[attr-defined]
    return mock_module


class TestSvgToPdf:
    def test_svg_to_pdf_cairosvg_fallback(self, tmp_path: Path) -> None:
        """Convert SVG → PDF using cairosvg fallback."""
        svg_path = tmp_path / "test.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
            '<rect width="100" height="100" fill="blue"/>'
            "</svg>",
            encoding="utf-8",
        )
        pdf_path = tmp_path / "output.pdf"

        import sys

        mock_cairosvg = _mock_cairosvg("write_to")
        # Assume Inkscape is absent to test cairosvg fallback
        with (
            patch("maglab.figure.renderers.schematic._find_inkscape", return_value=None),
            patch.dict(sys.modules, {"cairosvg": mock_cairosvg}),
        ):
            result = svg_to_pdf(svg_path, pdf_path)

        assert result == pdf_path
        assert pdf_path.is_file()
        assert pdf_path.stat().st_size > 0

    def test_svg_to_pdf_output_dir_created(self, tmp_path: Path) -> None:
        """Missing output directory is created automatically."""
        svg_path = tmp_path / "test.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50">'
            '<rect width="50" height="50" fill="red"/>'
            "</svg>",
            encoding="utf-8",
        )
        pdf_path = tmp_path / "subdir" / "nested" / "output.pdf"

        import sys

        mock_cairosvg = _mock_cairosvg("write_to")
        with (
            patch("maglab.figure.renderers.schematic._find_inkscape", return_value=None),
            patch.dict(sys.modules, {"cairosvg": mock_cairosvg}),
        ):
            result = svg_to_pdf(svg_path, pdf_path)

        assert pdf_path.parent.is_dir()
        assert result.is_file()

    def test_render_to_file_pdf(self, tmp_path: Path) -> None:
        """renderer.render_to_file(fmt='pdf') works correctly."""
        import sys

        reg = _make_registry(_DummyPrimitive())
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel()
        out = tmp_path / "output.pdf"

        mock_cairosvg = _mock_cairosvg("write_to")
        with (
            patch("maglab.figure.renderers.schematic._find_inkscape", return_value=None),
            patch.dict(sys.modules, {"cairosvg": mock_cairosvg}),
        ):
            result_path = renderer.render_to_file(panel, out, fmt="pdf")

        assert result_path.is_file()
        assert result_path.suffix == ".pdf"


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 3)
# ---------------------------------------------------------------------------


class TestR3Finding2DefaultRegistryWiring:
    """R3-F2 (HIGH): SchematicRenderer() with no explicit registry must use the
    populated CatalogRegistry, not the empty P1 stub PrimitiveRegistry().

    Previously, SchematicRenderer.__init__ defaulted to
    ``spec.default_registry`` which is ``PrimitiveRegistry()`` — always empty.
    Now it must default to ``make_default_registry()`` (CatalogRegistry).
    """

    def test_default_renderer_registry_is_nonempty(self):
        """SchematicRenderer() with no args must have a non-empty registry."""
        renderer = SchematicRenderer()
        assert len(renderer._registry) > 0, (
            "SchematicRenderer default registry is empty — CatalogRegistry not wired in."
        )

    def test_default_renderer_registry_is_catalog_type(self):
        """SchematicRenderer() default registry must be a CatalogRegistry instance."""
        from maglab.figure.primitives.registry import CatalogRegistry

        renderer = SchematicRenderer()
        assert isinstance(renderer._registry, CatalogRegistry), (
            f"Expected CatalogRegistry, got {type(renderer._registry).__name__}"
        )

    def test_default_renderer_can_search_catalog_primitives(self):
        """SchematicRenderer() default registry must return results for a catalog query."""
        renderer = SchematicRenderer()
        # The catalog has 10 primitives; any keyword that appears in any name/tag
        # should return at least one result.
        results = renderer._registry.search("hall")
        assert len(results) > 0, (
            "Default registry search('hall') returned no results — catalog primitives unreachable."
        )

    def test_explicit_registry_overrides_default(self):
        """Passing an explicit registry must override the catalog default."""
        empty_reg = PrimitiveRegistry()
        renderer = SchematicRenderer(registry=empty_reg)
        assert len(renderer._registry) == 0, (
            "Explicit empty registry was not used — default catalog overrode it."
        )


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 5)
# ---------------------------------------------------------------------------


class TestR5Finding2PanelIdSanitization:
    """R5-F2 (LOW): panel_id containing '-->' must produce well-formed SVG XML.

    A raw panel_id like 'test-->foo' would place '-->' inside an XML comment,
    violating the XML spec and causing cairosvg/lxml to raise XMLSyntaxError.
    The fix replaces '--' with '__' before inserting into the comment.
    """

    def test_assemble_svg_double_dash_sanitized(self) -> None:
        """assemble_svg() with provenance containing '--' must yield valid XML."""
        import xml.etree.ElementTree as ET

        d = _DummyPrimitive()
        # Provenance string that would break XML comments if unsanitized
        svg = assemble_svg(
            [(d, {})],
            provenance="panel_id=test-->foo<!--bar",
        )
        # Must not contain raw '-->' sequence inside the comment body
        # (the closing '-->' that ends the comment tag is OK)
        # The comment should use '__' instead of '--'
        assert "panel_id=test__>foo<!__bar" in svg or "__>" in svg
        # Most importantly, the document must be parseable as valid XML
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(
                f"SVG is not valid XML after sanitization: {exc}\n{svg[:400]}"
            ) from exc

    def test_empty_svg_double_dash_sanitized(self) -> None:
        """_empty_svg() with panel_id containing '--' must yield valid XML."""
        import xml.etree.ElementTree as ET

        reg = PrimitiveRegistry()
        renderer = SchematicRenderer(registry=reg)
        # _empty_svg is called directly (it is a public-enough helper)
        svg = renderer._empty_svg("bad--panel-->id", width_mm=89.0, height_mm=60.0)
        assert "<!--" in svg  # comment is still present
        # Raw '--' inside comment body must be replaced
        # Strip the closing tag marker to check just the comment content
        comment_content = svg.split("<!--")[1].split("-->")[0]
        assert "--" not in comment_content, (
            f"Comment content still contains '--': {comment_content!r}"
        )
        # Document must be valid XML
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(f"Empty SVG is not valid XML: {exc}\n{svg}") from exc

    def test_render_panel_with_dangerous_panel_id_produces_valid_xml(self) -> None:
        """render_panel() with a panel_id containing '-->' must return valid XML."""
        import xml.etree.ElementTree as ET

        reg = PrimitiveRegistry()  # empty — forces _empty_svg path
        renderer = SchematicRenderer(registry=reg)
        panel = _make_schematic_panel(panel_id="test--><script>alert(1)</script><!--")
        svg = renderer.render_panel(panel)
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(
                f"render_panel() produced invalid XML for dangerous panel_id: {exc}\n{svg[:400]}"
            ) from exc
