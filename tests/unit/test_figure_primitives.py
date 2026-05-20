"""tests/unit/test_figure_primitives.py — Primitive contract and registry interface tests.

Validation items (§20):
- The ``Primitive`` protocol passes type checks.
- ``PrimitiveRegistry.search()`` and ``load()`` interface signatures are confirmed.
- Verified via a dummy implementation that P4 can implement this interface without breaking it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import pytest

from maglab.figure.primitives.spec import Category, Primitive, PrimitiveRegistry, default_registry

# ---------------------------------------------------------------------------
# Dummy Primitive implementation (for protocol compliance verification)
# ---------------------------------------------------------------------------


class DummyPrimitive:
    """Dummy Primitive protocol implementation — stub for a real P4 primitive."""

    name: str = "dummy-hall-bar"
    category: str = "device geometry"
    tags: list[str] = ["Hall", "bar", "measurement", "geometry"]
    description: str = "Hall bar device geometry dummy primitive (for testing)."
    parameters: list[dict[str, Any]] = [
        {
            "name": "width_um",
            "type": "float",
            "default": 20.0,
            "description": "Hall bar width (μm).",
        },
        {
            "name": "length_um",
            "type": "float",
            "default": 100.0,
            "description": "Hall bar length (μm).",
        },
    ]
    physics_convention: str = "Current along x, Hall voltage along y, magnetic field along z."
    references: list[str] = ["doi:10.1103/PhysRevLett.88.117601"]
    provenance: dict[str, Any] = {"source": "handwritten", "author": "test"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(
        self,
        params: dict[str, Any],
        backend: str = "svg",
        style: str = "nature",
    ) -> str:
        w = params.get("width_um", self.parameters[0]["default"])
        length = params.get("length_um", self.parameters[1]["default"])
        return f'<rect width="{w}" height="{length}" />'


# ---------------------------------------------------------------------------
# Primitive protocol type checks
# ---------------------------------------------------------------------------


class TestPrimitiveProtocol:
    def test_dummy_satisfies_primitive_protocol(self):
        """DummyPrimitive satisfies the Primitive protocol."""
        dummy = DummyPrimitive()
        # runtime_checkable protocol isinstance check
        assert isinstance(dummy, Primitive), (
            "DummyPrimitive does not satisfy the Primitive protocol."
        )

    def test_primitive_required_attributes_present(self):
        """All required attributes of the Primitive protocol are present."""
        dummy = DummyPrimitive()
        required = [
            "name",
            "category",
            "tags",
            "description",
            "parameters",
            "physics_convention",
            "references",
            "provenance",
            "preview",
            "journal_styles",
        ]
        for attr in required:
            assert hasattr(dummy, attr), f"Missing Primitive attribute '{attr}'."

    def test_render_returns_string(self):
        """render() returns a string."""
        dummy = DummyPrimitive()
        result = dummy.render({"width_um": 30.0})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_backends(self):
        """render() accepts various backend arguments."""
        dummy = DummyPrimitive()
        for backend in ["svg", "tikz", "py"]:
            result = dummy.render({}, backend=backend)
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# PrimitiveRegistry interface
# ---------------------------------------------------------------------------


class TestPrimitiveRegistry:
    def test_empty_registry(self):
        """An empty registry returns [] from list_all()."""
        reg = PrimitiveRegistry()
        assert reg.list_all() == []
        assert len(reg) == 0

    def test_register_and_load(self):
        """After register(), load() returns the same object."""
        reg = PrimitiveRegistry()
        dummy = DummyPrimitive()
        reg.register(dummy)
        loaded = reg.load(dummy.name)
        assert loaded is dummy

    def test_load_unknown_raises(self):
        """load() with an unknown name raises KeyError."""
        reg = PrimitiveRegistry()
        with pytest.raises(KeyError, match="registry"):
            reg.load("nonexistent")

    def test_list_all_after_register(self):
        """After register(), the item appears in list_all()."""
        reg = PrimitiveRegistry()
        dummy = DummyPrimitive()
        reg.register(dummy)
        items = reg.list_all()
        assert len(items) == 1
        assert items[0]["name"] == dummy.name

    def test_search_by_keyword(self):
        """search() finds primitives by keyword."""
        reg = PrimitiveRegistry()
        dummy = DummyPrimitive()
        reg.register(dummy)
        results = reg.search("Hall bar")
        assert len(results) >= 1
        assert any(r["name"] == dummy.name for r in results)

    def test_search_no_match(self):
        """A search with no match returns an empty list."""
        reg = PrimitiveRegistry()
        dummy = DummyPrimitive()
        reg.register(dummy)
        results = reg.search("skyrmion topological hopfion xyzzy")
        assert results == []

    def test_search_by_category(self):
        """Searching by category keyword works."""
        reg = PrimitiveRegistry()
        dummy = DummyPrimitive()
        reg.register(dummy)
        results = reg.search("device geometry")
        assert len(results) >= 1

    def test_index_includes_required_keys(self):
        """Index entries include name, category, tags, description."""
        reg = PrimitiveRegistry()
        reg.register(DummyPrimitive())
        item = reg.list_all()[0]
        for key in ["name", "category", "tags", "description", "journal_styles"]:
            assert key in item, f"Index entry missing '{key}'."

    def test_len(self):
        """len(registry) returns the number of registered primitives."""
        reg = PrimitiveRegistry()
        assert len(reg) == 0
        reg.register(DummyPrimitive())
        assert len(reg) == 1

    def test_default_registry_is_instance(self):
        """default_registry is a PrimitiveRegistry instance."""
        assert isinstance(default_registry, PrimitiveRegistry)

    def test_multiple_register(self):
        """Multiple primitives can be registered."""
        reg = PrimitiveRegistry()
        for i in range(5):
            d = DummyPrimitive()
            object.__setattr__(d, "name", f"dummy-{i}")
            d.name = f"dummy-{i}"
            reg.register(d)
        assert len(reg) == 5


# ---------------------------------------------------------------------------
# Interface signature verification (P4 implementability without breaking)
# ---------------------------------------------------------------------------


class TestInterfaceSignatures:
    def test_search_signature(self):
        """search(query: str) -> list[dict] signature is maintained."""
        reg = PrimitiveRegistry()
        result = reg.search("test")
        assert isinstance(result, list)

    def test_load_signature(self):
        """load(name: str) -> Primitive signature is maintained."""
        reg = PrimitiveRegistry()
        reg.register(DummyPrimitive())
        primitive = reg.load("dummy-hall-bar")
        assert isinstance(primitive, Primitive)

    def test_list_all_signature(self):
        """list_all() -> list[dict] signature is maintained."""
        reg = PrimitiveRegistry()
        result = reg.list_all()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Category enum (FIX 5)
# ---------------------------------------------------------------------------


class TestCategoryEnum:
    """Category StrEnum coverage (plan §12.4-②, T-P4-18)."""

    def test_category_is_str_enum(self):
        """Category must be importable and be a StrEnum subclass."""
        from enum import StrEnum

        assert issubclass(Category, StrEnum)

    def test_category_has_ten_entries(self):
        """Category must have exactly 10 taxonomy families."""
        assert len(Category) == 10, (
            f"Expected 10 Category entries; got {len(Category)}: {list(Category)}"
        )

    def test_category_values_are_strings(self):
        """All Category values must be non-empty strings."""
        for cat in Category:
            assert isinstance(cat, str)
            assert len(cat) > 0

    def test_category_equals_string(self):
        """StrEnum members compare equal to their string values (backward-compat)."""
        assert Category.DEVICE_GEOMETRY == "device geometry"
        assert Category.SPIN_TEXTURE == "spin/magnetic texture"
        assert Category.ANNOTATION == "annotation"
        assert Category.DYNAMICS == "dynamics"

    def test_catalog_categories_covered_by_enum(self):
        """All free-form category strings used in the catalog are covered by Category values."""
        from maglab.figure.primitives import default_registry

        catalog_categories = {item["category"] for item in default_registry.list_all()}
        enum_values = {cat.value for cat in Category}
        uncovered = catalog_categories - enum_values
        assert not uncovered, (
            f"Catalog categories not in Category enum: {uncovered}. "
            "Add them or map to an existing entry."
        )


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 4, domain 01/02)
# ---------------------------------------------------------------------------


class TestR4Finding1SvgLineAttributes:
    """R4-F1 / R4-F2 (MEDIUM): Every SVG <line> element in catalog primitives must
    have exactly one y1 attribute and exactly one y2 attribute.

    Previously, HallBarPrimitive and MeasurementGeometryPrimitive both wrote
    `y1=` twice (and omitted `y2=`), causing the current-arrow line to
    degenerate to a zero-height invisible element.
    """

    @staticmethod
    def _count_attr(tag: str, attr: str) -> int:
        """Count occurrences of ``attr=`` inside a single SVG tag string."""
        import re

        return len(re.findall(rf"\b{re.escape(attr)}=", tag))

    def _extract_line_tags(self, svg: str) -> list[str]:
        """Return all <line …/> tag strings from an SVG document."""
        import re

        return re.findall(r"<line\b[^>]*/>", svg, re.DOTALL)

    def test_hall_bar_current_arrow_has_y1_and_y2(self) -> None:
        """HallBarPrimitive current-arrow <line> must have exactly one y1 and one y2."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("hall-bar")  # type: ignore[assignment]
        svg = prim.render({"show_arrows": True}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        assert line_tags, "No <line> elements found in hall-bar SVG."
        for tag in line_tags:
            y1_count = self._count_attr(tag, "y1")
            y2_count = self._count_attr(tag, "y2")
            assert y1_count == 1, (
                f"hall-bar <line> has {y1_count} y1 attribute(s) (expected 1): {tag!r}"
            )
            assert y2_count == 1, (
                f"hall-bar <line> has {y2_count} y2 attribute(s) (expected 1): {tag!r}"
            )

    def test_measurement_geometry_current_arrow_has_y1_and_y2(self) -> None:
        """MeasurementGeometryPrimitive current-arrow <line> must have exactly one y1 and one y2."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("measurement-geometry")  # type: ignore[assignment]

        svg = prim.render(
            {"show_current": True, "show_field": False, "show_voltage": False}, backend="svg"
        )
        line_tags = self._extract_line_tags(svg)
        assert line_tags, "No <line> elements found in measurement-geometry SVG."
        for tag in line_tags:
            y1_count = self._count_attr(tag, "y1")
            y2_count = self._count_attr(tag, "y2")
            assert y1_count == 1, (
                f"measurement-geometry <line> has {y1_count} y1 attribute(s) (expected 1): {tag!r}"
            )
            assert y2_count == 1, (
                f"measurement-geometry <line> has {y2_count} y2 attribute(s) (expected 1): {tag!r}"
            )

    def test_all_catalog_svg_lines_have_distinct_y1_y2(self) -> None:
        """All <line> elements across the entire catalog must have exactly one y1 and one y2."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        for entry in reg.list_all():
            prim = reg.load(entry["name"])  # type: ignore[assignment]
            svg = prim.render({}, backend="svg")
            line_tags = self._extract_line_tags(svg)
            for tag in line_tags:
                y1_count = self._count_attr(tag, "y1")
                y2_count = self._count_attr(tag, "y2")
                assert y1_count == 1, (
                    f"Primitive {entry['name']!r}: <line> has {y1_count} y1 attr(s): {tag!r}"
                )
                assert y2_count == 1, (
                    f"Primitive {entry['name']!r}: <line> has {y2_count} y2 attr(s): {tag!r}"
                )


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 6, domain 03)
# ---------------------------------------------------------------------------


class TestR6Finding1SvgTextXmlEscaping:
    """R6-F1 (LOW): User-controlled strings inserted into SVG <text> node content
    must be XML-escaped so that characters like ``<``, ``>``, and ``&`` do not
    produce malformed XML that cairosvg/lxml rejects.

    The three affected primitives are: multilayer-stack, hall-bar, coordinate-axes.
    """

    _SPECIAL = "CoFeB<10nm> & Fe₂O₃"

    def _assert_valid_xml(self, svg: str, primitive_name: str) -> None:
        """Parse svg as XML; raise AssertionError if it is malformed."""
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(
                f"Primitive {primitive_name!r} produced malformed XML when given special "
                f"characters: {exc}"
            ) from exc

    def test_multilayer_stack_escapes_layer_name(self) -> None:
        """multilayer-stack layer names containing <, >, & must produce valid XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("multilayer-stack")  # type: ignore[assignment]
        params = {
            "layers": [
                {"name": self._SPECIAL, "thickness_nm": 2.0, "color": "#C00"},
            ],
            "show_labels": True,
            "show_thickness": False,
        }
        svg = prim.render(params, backend="svg")
        self._assert_valid_xml(svg, "multilayer-stack")
        # Entity-encoded form must appear in the output
        assert "&lt;" in svg, "Expected '&lt;' in escaped multilayer-stack SVG"
        assert "&amp;" in svg, "Expected '&amp;' in escaped multilayer-stack SVG"

    def test_hall_bar_escapes_label(self) -> None:
        """hall-bar label containing <, >, & must produce valid XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("hall-bar")  # type: ignore[assignment]
        params = {"label": self._SPECIAL}
        svg = prim.render(params, backend="svg")
        self._assert_valid_xml(svg, "hall-bar")
        assert "&lt;" in svg, "Expected '&lt;' in escaped hall-bar SVG"
        assert "&amp;" in svg, "Expected '&amp;' in escaped hall-bar SVG"

    def test_coordinate_axes_escapes_labels(self) -> None:
        """coordinate-axes label_x/y/z containing <, >, & must produce valid XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("coordinate-axes")  # type: ignore[assignment]
        params = {
            "label_x": "H<sub>eff</sub>",
            "label_y": "M & H",
            "label_z": "B>0",
            "show_z": True,
        }
        svg = prim.render(params, backend="svg")
        self._assert_valid_xml(svg, "coordinate-axes")
        assert "&lt;" in svg, "Expected '&lt;' in escaped coordinate-axes SVG"
        assert "&amp;" in svg, "Expected '&amp;' in escaped coordinate-axes SVG"
        assert "&gt;" in svg, "Expected '&gt;' in escaped coordinate-axes SVG"


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 7, domain 03)
# ---------------------------------------------------------------------------


class TestR7Finding1SvgColorAttrEscaping:
    """R7-F1 (LOW): User-controlled color parameters inserted into SVG attribute
    values must be XML-escaped so that characters like ``<``, ``>``, ``&``, and
    ``"`` do not produce malformed XML that cairosvg/lxml rejects.

    Affected primitives: hall-bar, multilayer-stack, bloch-domain-wall,
    mtj-pillar, coordinate-axes.
    """

    # A color string containing all four dangerous characters.
    _BAD_COLOR = 'red<bad>&"evil"'

    def _assert_valid_xml(self, svg: str, primitive_name: str) -> None:
        """Parse svg as XML; raise AssertionError if it is malformed."""
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(
                f"Primitive {primitive_name!r} produced malformed XML when given a "
                f"color param containing '<', '>', '&', '\"': {exc}"
            ) from exc

    def test_hall_bar_color_attr_escaped(self) -> None:
        """hall-bar color param with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("hall-bar")  # type: ignore[assignment]
        svg = prim.render({"color": self._BAD_COLOR}, backend="svg")
        self._assert_valid_xml(svg, "hall-bar")

    def test_multilayer_stack_color_attr_escaped(self) -> None:
        """multilayer-stack layer color with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("multilayer-stack")  # type: ignore[assignment]
        params = {
            "layers": [
                {"name": "CoFeB", "thickness_nm": 2.0, "color": self._BAD_COLOR},
            ]
        }
        svg = prim.render(params, backend="svg")
        self._assert_valid_xml(svg, "multilayer-stack")

    def test_bloch_domain_wall_color_up_attr_escaped(self) -> None:
        """bloch-domain-wall color_up with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg = prim.render({"color_up": self._BAD_COLOR, "show_domains": True}, backend="svg")
        self._assert_valid_xml(svg, "bloch-domain-wall (color_up)")

    def test_bloch_domain_wall_color_down_attr_escaped(self) -> None:
        """bloch-domain-wall color_down with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg = prim.render({"color_down": self._BAD_COLOR, "show_domains": True}, backend="svg")
        self._assert_valid_xml(svg, "bloch-domain-wall (color_down)")

    def test_mtj_pillar_fixed_color_attr_escaped(self) -> None:
        """mtj-pillar fixed_color with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("mtj-pillar")  # type: ignore[assignment]
        svg = prim.render({"fixed_color": self._BAD_COLOR}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (fixed_color)")

    def test_mtj_pillar_free_color_attr_escaped(self) -> None:
        """mtj-pillar free_color with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("mtj-pillar")  # type: ignore[assignment]
        svg = prim.render({"free_color": self._BAD_COLOR}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (free_color)")

    def test_mtj_pillar_barrier_color_attr_escaped(self) -> None:
        """mtj-pillar barrier_color with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("mtj-pillar")  # type: ignore[assignment]
        svg = prim.render({"barrier_color": self._BAD_COLOR}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (barrier_color)")

    def test_coordinate_axes_color_x_attr_escaped(self) -> None:
        """coordinate-axes color_x with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("coordinate-axes")  # type: ignore[assignment]
        svg = prim.render({"color_x": self._BAD_COLOR}, backend="svg")
        self._assert_valid_xml(svg, "coordinate-axes (color_x)")

    def test_coordinate_axes_color_y_attr_escaped(self) -> None:
        """coordinate-axes color_y with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("coordinate-axes")  # type: ignore[assignment]
        svg = prim.render({"color_y": self._BAD_COLOR}, backend="svg")
        self._assert_valid_xml(svg, "coordinate-axes (color_y)")

    def test_coordinate_axes_color_z_attr_escaped(self) -> None:
        """coordinate-axes color_z with '<', '>', '&', '\"' must produce well-formed XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("coordinate-axes")  # type: ignore[assignment]
        svg = prim.render({"color_z": self._BAD_COLOR, "show_z": True}, backend="svg")
        self._assert_valid_xml(svg, "coordinate-axes (color_z)")


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 11, domain 03)
# ---------------------------------------------------------------------------


class TestR11ZeroDivisionGuards:
    """R11-F1/F2/F3 (LOW): Primitives must not raise ZeroDivisionError when a
    user-controlled divisor parameter is 0; they must instead clamp to a sane
    minimum and produce parseable SVG XML.
    """

    @staticmethod
    def _assert_valid_xml(svg: str, label: str) -> None:
        """Raise AssertionError if *svg* is not well-formed XML."""
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(f"{label!r}: render output is not valid XML: {exc}") from exc

    # ------------------------------------------------------------------
    # F1 — neel-domain-wall: wall_width=0
    # ------------------------------------------------------------------

    def test_neel_wall_width_zero_no_raise(self) -> None:
        """neel-domain-wall with wall_width=0 must not raise ZeroDivisionError."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("neel-domain-wall")  # type: ignore[assignment]
        svg = prim.render({"wall_width": 0}, backend="svg")
        assert isinstance(svg, str) and len(svg) > 0

    def test_neel_wall_width_zero_produces_valid_xml(self) -> None:
        """neel-domain-wall with wall_width=0 must produce parseable SVG XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("neel-domain-wall")  # type: ignore[assignment]
        svg = prim.render({"wall_width": 0}, backend="svg")
        self._assert_valid_xml(svg, "neel-domain-wall (wall_width=0)")

    def test_neel_wall_width_positive_unchanged(self) -> None:
        """neel-domain-wall with a valid positive wall_width renders identically
        before and after the clamp guard (clamp must be a no-op for positive inputs)."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("neel-domain-wall")  # type: ignore[assignment]
        svg_default = prim.render({}, backend="svg")
        svg_explicit = prim.render({"wall_width": 120.0}, backend="svg")
        assert svg_default == svg_explicit, (
            "neel-domain-wall default render changed after R11 guard — regression."
        )
        self._assert_valid_xml(svg_default, "neel-domain-wall (wall_width=120.0)")

    # ------------------------------------------------------------------
    # F2 — bloch-domain-wall: wall_width=0
    # ------------------------------------------------------------------

    def test_bloch_wall_width_zero_no_raise(self) -> None:
        """bloch-domain-wall with wall_width=0 must not raise ZeroDivisionError."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg = prim.render({"wall_width": 0}, backend="svg")
        assert isinstance(svg, str) and len(svg) > 0

    def test_bloch_wall_width_zero_produces_valid_xml(self) -> None:
        """bloch-domain-wall with wall_width=0 must produce parseable SVG XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg = prim.render({"wall_width": 0}, backend="svg")
        self._assert_valid_xml(svg, "bloch-domain-wall (wall_width=0)")

    def test_bloch_wall_width_positive_unchanged(self) -> None:
        """bloch-domain-wall with a valid positive wall_width renders identically
        before and after the clamp guard (clamp must be a no-op for positive inputs)."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg_default = prim.render({}, backend="svg")
        svg_explicit = prim.render({"wall_width": 120.0}, backend="svg")
        assert svg_default == svg_explicit, (
            "bloch-domain-wall default render changed after R11 guard — regression."
        )
        self._assert_valid_xml(svg_default, "bloch-domain-wall (wall_width=120.0)")

    # ------------------------------------------------------------------
    # F3 — spin-texture-colorwheel: n_sectors=0
    # ------------------------------------------------------------------

    def test_colorwheel_n_sectors_zero_no_raise(self) -> None:
        """spin-texture-colorwheel with n_sectors=0 must not raise ZeroDivisionError."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("spin-texture-colorwheel")  # type: ignore[assignment]
        svg = prim.render({"n_sectors": 0}, backend="svg")
        assert isinstance(svg, str) and len(svg) > 0

    def test_colorwheel_n_sectors_zero_produces_valid_xml(self) -> None:
        """spin-texture-colorwheel with n_sectors=0 must produce parseable SVG XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("spin-texture-colorwheel")  # type: ignore[assignment]
        svg = prim.render({"n_sectors": 0}, backend="svg")
        self._assert_valid_xml(svg, "spin-texture-colorwheel (n_sectors=0)")

    def test_colorwheel_n_sectors_positive_unchanged(self) -> None:
        """spin-texture-colorwheel with a valid positive n_sectors renders identically
        before and after the clamp guard (clamp must be a no-op for positive inputs)."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("spin-texture-colorwheel")  # type: ignore[assignment]
        svg_default = prim.render({}, backend="svg")
        svg_explicit = prim.render({"n_sectors": 36}, backend="svg")
        assert svg_default == svg_explicit, (
            "spin-texture-colorwheel default render changed after R11 guard — regression."
        )
        self._assert_valid_xml(svg_default, "spin-texture-colorwheel (n_sectors=36)")


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 12, domain 03)
# ---------------------------------------------------------------------------


class TestR12Finding1BlochArrowheadColor:
    """R12-F1 (LOW): BlochDomainWallPrimitive arrowhead color must not be stuck at black.

    The marker path uses ``fill="currentColor"``, which resolves to the CSS ``color``
    property of the referencing element. When ``color=`` is absent, SVG renderers
    default to black, so all arrowhead tips render black regardless of the computed
    blend color while the line shafts show the correct physics-encoded color.

    Fix: every ``<line>`` element that references the ``#arrBloch`` marker must carry
    ``color="{arr_color}"`` so that ``currentColor`` in the marker resolves correctly.
    """

    @staticmethod
    def _assert_valid_xml(svg: str, label: str) -> None:
        """Raise AssertionError if *svg* is not well-formed XML."""
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(f"{label!r}: render output is not valid XML: {exc}") from exc

    @staticmethod
    def _extract_line_tags(svg: str) -> list[str]:
        """Return all ``<line …/>`` tag strings from an SVG document."""
        import re

        return re.findall(r"<line\b[^>]*/>", svg, re.DOTALL)

    def test_bloch_line_elements_have_color_attribute(self) -> None:
        """Every <line> element in bloch-domain-wall SVG must carry a color= attribute
        so that currentColor inside the #arrBloch marker resolves to the blend color."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg = prim.render({}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        # The primitive always emits at least one spin arrow, so there must be lines.
        assert line_tags, "No <line> elements found in bloch-domain-wall SVG."
        for tag in line_tags:
            # Only check lines that reference the #arrBloch marker (spin arrows).
            if "arrBloch" not in tag:
                continue
            assert 'color="' in tag, (
                f"bloch-domain-wall <line> referencing #arrBloch is missing color= attribute "
                f"(currentColor will default to black): {tag!r}"
            )

    def test_bloch_svg_is_valid_xml(self) -> None:
        """bloch-domain-wall render output must be parseable XML."""
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg = prim.render({}, backend="svg")
        self._assert_valid_xml(svg, "bloch-domain-wall (default params)")

    def test_bloch_arrowhead_color_is_not_black_for_non_black_blend(self) -> None:
        """When the physics-computed blend color is non-black, the color= attribute on
        <line> elements must NOT be ``rgb(0,0,0)`` (pure black).

        With default params (color_up blue, color_down red) the wall spins sweep
        through blue↔red: no arrow should ever encode to pure black (0,0,0)."""
        import re

        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        prim = reg.load("bloch-domain-wall")  # type: ignore[assignment]
        svg = prim.render(
            {
                "n_spins": 9,
                "wall_width": 120.0,
                "chirality": 1,
                "color_up": "#0055CC",
                "color_down": "#CC0000",
            },
            backend="svg",
        )
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrBloch" in t]
        assert arrow_lines, "No #arrBloch <line> elements found — cannot assert non-black color."
        for tag in arrow_lines:
            # Extract color= attribute value.
            m = re.search(r'color="([^"]*)"', tag)
            assert m is not None, f"<line> referencing #arrBloch has no color= attribute: {tag!r}"
            color_val = m.group(1)
            assert color_val != "rgb(0,0,0)", (
                f"<line> color= is pure black 'rgb(0,0,0)' — arrowhead will be invisible: {tag!r}"
            )
            assert color_val != "#000000", (
                f"<line> color= is pure black '#000000' — arrowhead will be invisible: {tag!r}"
            )
            assert color_val != "black", (
                f"<line> color= is 'black' — arrowhead will be invisible: {tag!r}"
            )


# ---------------------------------------------------------------------------
# Regression tests — code-review findings (round 13, domain 03)
# ---------------------------------------------------------------------------


class TestR13Finding1MTJPillarVerticalArrow:
    """R13-F1 (LOW): MTJPillarPrimitive.arrow_svg() must implement the ``"up"``
    and ``"down"`` magnetization direction branches.

    Previously the function returned ``""`` for any direction other than
    ``"right"`` or ``"left"``, so PMA (perpendicular-magnetic-anisotropy)
    MTJ geometries silently rendered without any magnetization indicator.

    Fix verification:
    - Rendering with ``free_direction="up"`` or ``"down"`` must produce a
      non-empty ``<line>`` element inside valid XML.
    - Existing ``"right"`` / ``"left"`` behavior must be unchanged.
    """

    @staticmethod
    def _assert_valid_xml(svg: str, label: str) -> None:
        """Raise AssertionError if *svg* is not well-formed XML."""
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:
            raise AssertionError(f"{label!r}: render output is not valid XML: {exc}") from exc

    @staticmethod
    def _extract_line_tags(svg: str) -> list[str]:
        """Return all ``<line …/>`` tag strings from an SVG document."""
        import re

        return re.findall(r"<line\b[^>]*/>", svg, re.DOTALL)

    def _load_mtj(self):  # type: ignore[return]
        from maglab.figure.primitives.registry import make_default_registry

        reg = make_default_registry()
        return reg.load("mtj-pillar")  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # "up" direction
    # ------------------------------------------------------------------

    def test_free_direction_up_produces_line_element(self) -> None:
        """free_direction='up' must produce at least one <line> element (non-empty arrow)."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "up"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        assert line_tags, (
            "mtj-pillar with free_direction='up' produced no <line> elements — "
            "arrow_svg() returned empty string for 'up' direction."
        )

    def test_free_direction_up_arrow_references_marker(self) -> None:
        """free_direction='up' arrow <line> must reference the #arrMTJ marker."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "up"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, (
            "mtj-pillar with free_direction='up': no <line> referencing #arrMTJ found."
        )

    def test_free_direction_up_produces_valid_xml(self) -> None:
        """free_direction='up' must produce parseable SVG XML."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "up"}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (free_direction='up')")

    def test_free_direction_up_line_is_vertical(self) -> None:
        """free_direction='up' must include at least one vertical #arrMTJ <line> (x1 == x2).

        The render also contains the fixed-layer arrow (default "right", horizontal), so
        we assert that *at least one* #arrMTJ line is vertical rather than requiring all.
        """
        import re

        prim = self._load_mtj()
        svg = prim.render({"free_direction": "up"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, "No #arrMTJ <line> elements found for 'up' direction."
        vertical = [
            t
            for t in arrow_lines
            if (
                (m1 := re.search(r'\bx1="([^"]*)"', t))
                and (m2 := re.search(r'\bx2="([^"]*)"', t))
                and m1.group(1) == m2.group(1)
            )
        ]
        assert vertical, (
            f"'up' direction: no vertical (x1==x2) #arrMTJ <line> found among: {arrow_lines}"
        )

    def test_free_direction_up_arrowhead_points_upward(self) -> None:
        """The vertical 'up' arrow tip must have y2 < y1 (SVG up = decreasing y)."""
        import re

        prim = self._load_mtj()
        svg = prim.render({"free_direction": "up"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, "No #arrMTJ <line> elements found for 'up' direction."
        # Inspect only vertical lines (the free-layer "up" arrow).
        vertical = [
            t
            for t in arrow_lines
            if (
                (m1 := re.search(r'\bx1="([^"]*)"', t))
                and (m2 := re.search(r'\bx2="([^"]*)"', t))
                and m1.group(1) == m2.group(1)
            )
        ]
        assert vertical, "'up' direction: no vertical arrow line found — cannot check orientation."
        for tag in vertical:
            y1_m = re.search(r'\by1="([^"]*)"', tag)
            y2_m = re.search(r'\by2="([^"]*)"', tag)
            assert y1_m and y2_m
            y1 = float(y1_m.group(1))
            y2 = float(y2_m.group(1))
            assert y2 < y1, (
                f"'up' arrow <line> tip (y2={y2}) is not above tail (y1={y1}) "
                f"— arrowhead points the wrong way: {tag!r}"
            )

    # ------------------------------------------------------------------
    # "down" direction
    # ------------------------------------------------------------------

    def test_free_direction_down_produces_line_element(self) -> None:
        """free_direction='down' must produce at least one <line> element (non-empty arrow)."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "down"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        assert line_tags, (
            "mtj-pillar with free_direction='down' produced no <line> elements — "
            "arrow_svg() returned empty string for 'down' direction."
        )

    def test_free_direction_down_arrow_references_marker(self) -> None:
        """free_direction='down' arrow <line> must reference the #arrMTJ marker."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "down"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, (
            "mtj-pillar with free_direction='down': no <line> referencing #arrMTJ found."
        )

    def test_free_direction_down_produces_valid_xml(self) -> None:
        """free_direction='down' must produce parseable SVG XML."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "down"}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (free_direction='down')")

    def test_free_direction_down_line_is_vertical(self) -> None:
        """free_direction='down' must include at least one vertical #arrMTJ <line> (x1 == x2).

        The render also contains the fixed-layer arrow (default "right", horizontal), so
        we assert that *at least one* #arrMTJ line is vertical rather than requiring all.
        """
        import re

        prim = self._load_mtj()
        svg = prim.render({"free_direction": "down"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, "No #arrMTJ <line> elements found for 'down' direction."
        vertical = [
            t
            for t in arrow_lines
            if (
                (m1 := re.search(r'\bx1="([^"]*)"', t))
                and (m2 := re.search(r'\bx2="([^"]*)"', t))
                and m1.group(1) == m2.group(1)
            )
        ]
        assert vertical, (
            f"'down' direction: no vertical (x1==x2) #arrMTJ <line> found among: {arrow_lines}"
        )

    def test_free_direction_down_arrowhead_points_downward(self) -> None:
        """The vertical 'down' arrow tip must have y2 > y1 (SVG down = increasing y)."""
        import re

        prim = self._load_mtj()
        svg = prim.render({"free_direction": "down"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, "No #arrMTJ <line> elements found for 'down' direction."
        # Inspect only vertical lines (the free-layer "down" arrow).
        vertical = [
            t
            for t in arrow_lines
            if (
                (m1 := re.search(r'\bx1="([^"]*)"', t))
                and (m2 := re.search(r'\bx2="([^"]*)"', t))
                and m1.group(1) == m2.group(1)
            )
        ]
        assert vertical, (
            "'down' direction: no vertical arrow line found — cannot check orientation."
        )
        for tag in vertical:
            y1_m = re.search(r'\by1="([^"]*)"', tag)
            y2_m = re.search(r'\by2="([^"]*)"', tag)
            assert y1_m and y2_m
            y1 = float(y1_m.group(1))
            y2 = float(y2_m.group(1))
            assert y2 > y1, (
                f"'down' arrow <line> tip (y2={y2}) is not below tail (y1={y1}) "
                f"— arrowhead points the wrong way: {tag!r}"
            )

    # ------------------------------------------------------------------
    # Existing "right" / "left" directions are unchanged
    # ------------------------------------------------------------------

    def test_free_direction_right_still_produces_horizontal_arrow(self) -> None:
        """free_direction='right' (existing behaviour) must still produce at least one
        horizontal #arrMTJ <line> (y1 == y2)."""
        import re

        prim = self._load_mtj()
        svg = prim.render({"free_direction": "right"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, "No #arrMTJ <line> elements found for 'right' direction."
        horizontal = [
            t
            for t in arrow_lines
            if (
                (m1 := re.search(r'\by1="([^"]*)"', t))
                and (m2 := re.search(r'\by2="([^"]*)"', t))
                and m1.group(1) == m2.group(1)
            )
        ]
        assert horizontal, (
            f"'right' direction: no horizontal (y1==y2) #arrMTJ <line> found among: {arrow_lines}"
        )

    def test_free_direction_left_still_produces_horizontal_arrow(self) -> None:
        """free_direction='left' (existing behaviour) must still produce at least one
        horizontal #arrMTJ <line> (y1 == y2)."""
        import re

        prim = self._load_mtj()
        svg = prim.render({"free_direction": "left"}, backend="svg")
        line_tags = self._extract_line_tags(svg)
        arrow_lines = [t for t in line_tags if "arrMTJ" in t]
        assert arrow_lines, "No #arrMTJ <line> elements found for 'left' direction."
        horizontal = [
            t
            for t in arrow_lines
            if (
                (m1 := re.search(r'\by1="([^"]*)"', t))
                and (m2 := re.search(r'\by2="([^"]*)"', t))
                and m1.group(1) == m2.group(1)
            )
        ]
        assert horizontal, (
            f"'left' direction: no horizontal (y1==y2) #arrMTJ <line> found among: {arrow_lines}"
        )

    def test_both_layers_up_produces_valid_xml(self) -> None:
        """PMA geometry with both layers pointing up must produce valid XML."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "up", "fixed_direction": "up"}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (both layers up)")

    def test_both_layers_down_produces_valid_xml(self) -> None:
        """PMA geometry with both layers pointing down must produce valid XML."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "down", "fixed_direction": "down"}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (both layers down)")

    def test_antiparallel_pma_produces_valid_xml(self) -> None:
        """PMA antiparallel state (free=up, fixed=down) must produce valid XML."""
        prim = self._load_mtj()
        svg = prim.render({"free_direction": "up", "fixed_direction": "down"}, backend="svg")
        self._assert_valid_xml(svg, "mtj-pillar (free=up, fixed=down)")
