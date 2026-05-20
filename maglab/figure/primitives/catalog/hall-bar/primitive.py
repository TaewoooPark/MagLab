"""Hall bar device geometry primitive (§12.4).

Standard Hall bar with current applied along x, Hall voltage along y, and magnetic field along z.
Includes two pairs of voltage contacts: longitudinal and Hall (transverse).
"""

from __future__ import annotations

import html
from typing import Any


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
        return self._render_svg(params)

    def _render_svg(self, params: dict[str, Any]) -> str:
        """SVG backend renderer."""
        # Extract parameters (apply defaults)
        W = float(params.get("width_um", 20.0))
        L = float(params.get("length_um", 100.0))
        cw = float(params.get("contact_width_um", 10.0))
        cl = float(params.get("contact_length_um", 8.0))
        color = str(params.get("color", "#4472C4"))
        show_arrows = bool(params.get("show_arrows", True))
        label = str(params.get("label", ""))

        # SVG scale: 1 μm = 2 px
        scale = 2.0
        sw, sl = W * scale, L * scale
        scw, scl = cw * scale, cl * scale

        # Hall bar body centered (primary direction x, width y)
        # Voltage contact positions: at 25%, 50%, 75%
        parts: list[str] = []

        # XML-safe color value for use in SVG attribute values.
        color_attr = html.escape(color, quote=True)

        # Main channel
        parts.append(
            f'<rect x="0" y="{sw:.1f}" width="{sl:.1f}" height="{sw:.1f}" '
            f'fill="{color_attr}" stroke="#000" stroke-width="1"/>'
        )

        # Current contacts (source/drain)
        parts.append(
            f'<rect x="-{scl:.1f}" y="{sw:.1f}" '
            f'width="{scl:.1f}" height="{sw:.1f}" '
            f'fill="{color_attr}" stroke="#000" stroke-width="1"/>'
        )
        parts.append(
            f'<rect x="{sl:.1f}" y="{sw:.1f}" '
            f'width="{scl:.1f}" height="{sw:.1f}" '
            f'fill="{color_attr}" stroke="#000" stroke-width="1"/>'
        )

        # Voltage contacts (Hall: top 2, longitudinal: bottom 2)
        x_hall1 = sl * 0.3
        x_hall2 = sl * 0.7
        x_long1 = sl * 0.25
        x_long2 = sl * 0.75

        for x_pos in [x_hall1, x_hall2]:
            parts.append(
                f'<rect x="{x_pos - scw / 2:.1f}" y="0" '
                f'width="{scw:.1f}" height="{sw:.1f}" '
                f'fill="{color_attr}" stroke="#000" stroke-width="1"/>'
            )

        for x_pos in [x_long1, x_long2]:
            parts.append(
                f'<rect x="{x_pos - scw / 2:.1f}" y="{sw * 2:.1f}" '
                f'width="{scw:.1f}" height="{sw:.1f}" '
                f'fill="{color_attr}" stroke="#000" stroke-width="1"/>'
            )

        # Arrows
        if show_arrows:
            arrow_y = sw * 1.5
            # Current arrow →
            parts.append(
                f'<line x1="{-scl:.1f}" y1="{arrow_y:.1f}" '
                f'x2="{-4:.1f}" y2="{arrow_y:.1f}" '
                f'stroke="#C00" stroke-width="2" '
                f'marker-end="url(#arr)"/>'
            )
            # Current label
            parts.append(
                f'<text x="{-scl / 2:.1f}" y="{arrow_y - 4:.1f}" '
                f'font-size="10" text-anchor="middle" fill="#C00">I</text>'
            )

        # Material label
        if label:
            parts.append(
                f'<text x="{sl / 2:.1f}" y="{sw * 1.5:.1f}" '
                f'font-size="9" text-anchor="middle" '
                f'dominant-baseline="middle" fill="#FFF">{html.escape(label)}</text>'
            )

        # Dimension text
        parts.append(
            f'<text x="{sl / 2:.1f}" y="{sw * 3.2:.1f}" '
            f'font-size="8" text-anchor="middle" fill="#444">'
            f"L={L:.0f}μm, W={W:.0f}μm</text>"
        )

        defs = (
            '<defs><marker id="arr" markerWidth="6" markerHeight="6" '
            'refX="5" refY="3" orient="auto">'
            '<path d="M0,0 L6,3 L0,6 Z" fill="#C00"/></marker></defs>'
        )

        total_h = sw * 3.5
        total_w = sl + scl * 2
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{total_w:.0f}" height="{total_h:.0f}" '
            f'viewBox="{-scl:.0f} 0 {total_w:.0f} {total_h:.0f}">\n'
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
