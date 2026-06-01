"""Hall bar device geometry primitive (§12.4).

Standard Hall bar with current applied along x, Hall voltage along y, and magnetic field along z.
Includes two pairs of voltage contacts: longitudinal and Hall (transverse).
"""

from __future__ import annotations

from typing import Any

from maglab.figure.primitives.svg import (
    color_value,
    fmt,
    positive_float,
    schematic_style,
    tag,
    text,
)


class HallBarPrimitive:
    """Hall bar device geometry parametric SVG primitive."""

    name: str = "hall-bar"
    category: str = "device geometry"
    tags: list[str] = ["Hall", "bar", "measurement", "geometry", "current", "voltage", "transport"]
    description: str = (
        "Hall bar device geometry primitive. Includes current source, Hall voltage, "
        "and longitudinal voltage measurement contacts. "
        "Convention: current direction (x), Hall voltage (y), magnetic field (z)."
    )
    parameters: list[dict[str, Any]] = [
        {
            "name": "width_um",
            "type": "float",
            "default": 20.0,
            "description": "Hall bar width (μm)",
        },
        {
            "name": "length_um",
            "type": "float",
            "default": 100.0,
            "description": "Hall bar length (μm)",
        },
        {
            "name": "contact_width_um",
            "type": "float",
            "default": 10.0,
            "description": "Voltage contact width (μm)",
        },
        {
            "name": "contact_length_um",
            "type": "float",
            "default": 8.0,
            "description": "Voltage contact length (μm)",
        },
        {
            "name": "color",
            "type": "str",
            "default": "#4472C4",
            "description": "Fill color (default: blue)",
        },
        {
            "name": "show_arrows",
            "type": "bool",
            "default": True,
            "description": "Show current/voltage arrows",
        },
        {
            "name": "show_voltage",
            "type": "bool",
            "default": True,
            "description": "Show Hall and longitudinal voltage contacts/arrows",
        },
        {
            "name": "show_field",
            "type": "bool",
            "default": True,
            "description": "Show out-of-plane field marker",
        },
        {"name": "label", "type": "str", "default": "", "description": "Material label"},
    ]
    physics_convention: str = "Current along x, Hall voltage along y, magnetic field along z (right-hand coordinate system). Follows Néel convention."
    references: list[str] = ["doi:10.1103/PhysRevLett.88.117601"]
    provenance: dict[str, Any] = {
        "source": "handwritten",
        "author": "MagLab P4",
        "physics_verified": True,
    }
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(
        self,
        params: dict[str, Any],
        backend: str = "svg",
        style: str = "nature",
    ) -> str:
        """Generate the Hall bar SVG from parameters."""
        if backend == "tikz":
            return self._render_tikz(params)
        return self._render_svg(params, style_key=style)

    def _render_svg(self, params: dict[str, Any], *, style_key: str = "nature") -> str:
        """SVG backend renderer."""
        style = schematic_style(style_key)
        # Extract parameters (apply defaults)
        W = positive_float(params, "width_um", 20.0, minimum=2.0, maximum=500.0)
        L = positive_float(params, "length_um", 100.0, minimum=10.0, maximum=2000.0)
        cw = positive_float(params, "contact_width_um", 10.0, minimum=1.0, maximum=200.0)
        cl = positive_float(params, "contact_length_um", 8.0, minimum=1.0, maximum=200.0)
        color = color_value(params.get("color", "#4472C4"), "#4472C4")
        show_arrows = bool(params.get("show_arrows", True))
        show_voltage = bool(params.get("show_voltage", True))
        show_field = bool(params.get("show_field", True))
        label = str(params.get("label", ""))

        # SVG scale: 1 μm = 2 px
        scale = 2.0
        sw, sl = W * scale, L * scale
        scw, scl = cw * scale, cl * scale

        # Hall bar body centered (primary direction x, width y)
        # Voltage contact positions: at 25%, 50%, 75%
        parts: list[str] = []

        # Main channel
        parts.append(
            tag(
                "rect",
                {
                    "class": "maglab-hall-channel",
                    "x": 0,
                    "y": fmt(sw),
                    "width": fmt(sl),
                    "height": fmt(sw),
                    "fill": color,
                    "stroke": "#000000",
                    "stroke_width": fmt(style.stroke_width),
                },
            )
        )

        # Current contacts (source/drain)
        parts.append(
            tag(
                "rect",
                {
                    "class": "maglab-hall-current-contact",
                    "x": fmt(-scl),
                    "y": fmt(sw),
                    "width": fmt(scl),
                    "height": fmt(sw),
                    "fill": color,
                    "stroke": "#000000",
                    "stroke_width": fmt(style.stroke_width),
                },
            )
        )
        parts.append(
            tag(
                "rect",
                {
                    "class": "maglab-hall-current-contact",
                    "x": fmt(sl),
                    "y": fmt(sw),
                    "width": fmt(scl),
                    "height": fmt(sw),
                    "fill": color,
                    "stroke": "#000000",
                    "stroke_width": fmt(style.stroke_width),
                },
            )
        )

        # Voltage contacts (Hall: top 2, longitudinal: bottom 2)
        x_hall1 = sl * 0.3
        x_hall2 = sl * 0.7
        x_long1 = sl * 0.25
        x_long2 = sl * 0.75

        for x_pos in [x_hall1, x_hall2]:
            parts.append(
                tag(
                    "rect",
                    {
                        "class": "maglab-hall-voltage-contact",
                        "x": fmt(x_pos - scw / 2),
                        "y": 0,
                        "width": fmt(scw),
                        "height": fmt(sw),
                        "fill": color,
                        "stroke": "#000000",
                        "stroke_width": fmt(style.stroke_width),
                    },
                )
            )

        for x_pos in [x_long1, x_long2]:
            parts.append(
                tag(
                    "rect",
                    {
                        "class": "maglab-hall-voltage-contact",
                        "x": fmt(x_pos - scw / 2),
                        "y": fmt(sw * 2),
                        "width": fmt(scw),
                        "height": fmt(sw),
                        "fill": color,
                        "stroke": "#000000",
                        "stroke_width": fmt(style.stroke_width),
                    },
                )
            )

        # Arrows
        if show_arrows:
            arrow_y = sw * 1.5
            # Current arrow →
            parts.append(
                tag(
                    "line",
                    {
                        "class": "maglab-current-arrow",
                        "x1": fmt(-scl),
                        "y1": fmt(arrow_y),
                        "x2": fmt(-4),
                        "y2": fmt(arrow_y),
                        "stroke": style.color("current", "#C00"),
                        "stroke_width": fmt(style.arrow_width),
                        "marker_end": "url(#hbCurrentArrow)",
                    },
                )
            )
            # Current label
            parts.append(
                tag(
                    "text",
                    {
                        "x": fmt(-scl / 2),
                        "y": fmt(arrow_y - 4),
                        "font_family": style.font_family,
                        "font_size": fmt(style.label_size),
                        "text_anchor": "middle",
                        "fill": style.color("current", "#C00"),
                        "font_style": "italic",
                    },
                    "I",
                )
            )

        if show_voltage:
            for x_pos, label_text, y1, y2 in [
                (x_hall1, "V_H", sw * 0.82, sw * 0.18),
                (x_long2, "V_xx", sw * 2.18, sw * 2.82),
            ]:
                parts.append(
                    tag(
                        "line",
                        {
                            "class": "maglab-voltage-arrow",
                            "x1": fmt(x_pos),
                            "y1": fmt(y1),
                            "x2": fmt(x_pos),
                            "y2": fmt(y2),
                            "stroke": style.color("voltage", "#007700"),
                            "stroke_width": fmt(style.axis_width),
                            "marker_end": "url(#hbVoltageArrow)",
                        },
                    )
                )
                parts.append(
                    tag(
                        "text",
                        {
                            "x": fmt(x_pos + 5),
                            "y": fmt(y2),
                            "font_family": style.font_family,
                            "font_size": fmt(style.small_label_size),
                            "fill": style.color("voltage", "#007700"),
                            "font_style": "italic",
                        },
                        text(label_text),
                    )
                )

        if show_field:
            field_x = sl * 0.88
            field_y = sw * 0.35
            parts.append(
                tag(
                    "circle",
                    {
                        "class": "maglab-field-out-of-plane",
                        "cx": fmt(field_x),
                        "cy": fmt(field_y),
                        "r": fmt(5.5),
                        "fill": "none",
                        "stroke": style.color("field", "#0055CC"),
                        "stroke_width": fmt(style.axis_width),
                    },
                )
            )
            parts.append(
                tag(
                    "circle",
                    {
                        "cx": fmt(field_x),
                        "cy": fmt(field_y),
                        "r": fmt(1.5),
                        "fill": style.color("field", "#0055CC"),
                    },
                )
            )
            parts.append(
                tag(
                    "text",
                    {
                        "x": fmt(field_x + 8),
                        "y": fmt(field_y + 3),
                        "font_family": style.font_family,
                        "font_size": fmt(style.small_label_size),
                        "fill": style.color("field", "#0055CC"),
                        "font_style": "italic",
                    },
                    "H_z",
                )
            )

        # Material label
        if label:
            parts.append(
                tag(
                    "text",
                    {
                        "x": fmt(sl / 2),
                        "y": fmt(sw * 1.5),
                        "font_family": style.font_family,
                        "font_size": fmt(style.small_label_size),
                        "text_anchor": "middle",
                        "dominant_baseline": "middle",
                        "fill": "#ffffff",
                    },
                    text(label),
                )
            )

        # Dimension text
        parts.append(
            tag(
                "text",
                {
                    "x": fmt(sl / 2),
                    "y": fmt(sw * 3.25),
                    "font_family": style.font_family,
                    "font_size": fmt(style.small_label_size),
                    "text_anchor": "middle",
                    "fill": "#444444",
                },
                text(f"L={L:.0f} um, W={W:.0f} um"),
            )
        )

        defs = (
            '<defs><marker id="hbCurrentArrow" markerWidth="6" markerHeight="6" '
            'refX="5" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6 Z" fill="{style.color("current", "#C00")}"/></marker>'
            '<marker id="hbVoltageArrow" markerWidth="6" markerHeight="6" '
            'refX="5" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6 Z" fill="{style.color("voltage", "#007700")}"/></marker>'
            "</defs>"
        )

        total_h = sw * 3.5
        total_w = sl + scl * 2
        pad = 18.0
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{total_w + 2 * pad:.0f}" height="{total_h + 2 * pad:.0f}" '
            f'viewBox="{-scl - pad:.0f} {-pad:.0f} '
            f'{total_w + 2 * pad:.0f} {total_h + 2 * pad:.0f}">\n'
            f"{defs}\n" + "\n".join(parts) + "\n</svg>"
        )

    def _render_tikz(self, params: dict[str, Any]) -> str:
        """TikZ backend renderer (for LaTeX integration)."""
        W = float(params.get("width_um", 20.0)) / 10.0  # cm
        L = float(params.get("length_um", 100.0)) / 10.0
        color = str(params.get("color", "blue!60"))
        return (
            r"\begin{tikzpicture}" + "\n"
            rf"  \filldraw[fill={color}, draw=black] "
            rf"(0,0) rectangle ({L},{W});"
            "\n"
            "  \\draw[->] (-1,"
            + f"{W / 2:.1f}"
            + ") -- (0,"
            + f"{W / 2:.1f}"
            + ") node[right] {$I$};"
            "\n"
            r"\end{tikzpicture}"
        )


def get_primitive() -> HallBarPrimitive:
    """Factory function called by the registry loader."""
    return HallBarPrimitive()
