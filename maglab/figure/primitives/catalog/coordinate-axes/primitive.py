"""Coordinate axes annotation primitive (§12.4)."""

from __future__ import annotations

import html
from typing import Any


class CoordinateAxesPrimitive:
    """Coordinate axes annotation parametric primitive."""

    name: str = "coordinate-axes"
    category: str = "annotation"
    tags: list[str] = ["coordinate axes", "axes", "x", "y", "z", "coordinate system", "annotation", "arrow", "label", "vector"]
    description: str = (
        "Coordinate axes annotation primitive. Renders x, y, z axis arrows with "
        "user-defined labels. Supports 2D/3D projection mode selection."
    )
    parameters: list[dict[str, Any]] = [
        {"name": "length", "type": "float", "default": 40.0, "description": "Axis arrow length"},
        {"name": "label_x", "type": "str", "default": "x", "description": "x-axis label"},
        {"name": "label_y", "type": "str", "default": "y", "description": "y-axis label"},
        {"name": "label_z", "type": "str", "default": "z", "description": "z-axis label"},
        {"name": "show_z", "type": "bool", "default": True, "description": "Show z axis"},
        {"name": "color_x", "type": "str", "default": "#CC0000", "description": "x-axis color"},
        {"name": "color_y", "type": "str", "default": "#007700", "description": "y-axis color"},
        {"name": "color_z", "type": "str", "default": "#0055CC", "description": "z-axis color"},
    ]
    physics_convention: str = "Right-hand coordinate system. z is the out-of-plane direction. In 2D projection, z points upper-right."
    references: list[str] = []
    provenance: dict[str, Any] = {"source": "handwritten", "author": "MagLab P4"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        """Generate the coordinate axes SVG."""
        L = float(params.get("length", 40.0))
        lx = str(params.get("label_x", "x"))
        ly = str(params.get("label_y", "y"))
        lz = str(params.get("label_z", "z"))
        show_z = bool(params.get("show_z", True))
        # Escape color values for safe insertion into SVG attribute values.
        cx_col = html.escape(str(params.get("color_x", "#CC0000")), quote=True)
        cy_col = html.escape(str(params.get("color_y", "#007700")), quote=True)
        cz_col = html.escape(str(params.get("color_z", "#0055CC")), quote=True)

        ox, oy = 20.0, 20.0 + L
        size = L + 40

        defs = (
            f"<defs>"
            f'<marker id="axX" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6 Z" fill="{cx_col}"/></marker>'
            f'<marker id="axY" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6 Z" fill="{cy_col}"/></marker>'
            f'<marker id="axZ" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6 Z" fill="{cz_col}"/></marker>'
            f"</defs>"
        )

        parts: list[str] = [defs]

        # x axis →
        parts.append(
            f'<line x1="{ox:.1f}" y1="{oy:.1f}" x2="{ox + L - 3:.1f}" y2="{oy:.1f}" '
            f'stroke="{cx_col}" stroke-width="1.5" marker-end="url(#axX)"/>'
        )
        parts.append(
            f'<text x="{ox + L + 3:.1f}" y="{oy + 4:.1f}" '
            f'font-size="11" fill="{cx_col}" font-style="italic">{html.escape(lx)}</text>'
        )

        # y axis ↑
        parts.append(
            f'<line x1="{ox:.1f}" y1="{oy:.1f}" x2="{ox:.1f}" y2="{oy - L + 3:.1f}" '
            f'stroke="{cy_col}" stroke-width="1.5" marker-end="url(#axY)"/>'
        )
        parts.append(
            f'<text x="{ox - 4:.1f}" y="{oy - L - 4:.1f}" '
            f'font-size="11" fill="{cy_col}" font-style="italic" text-anchor="middle">{html.escape(ly)}</text>'
        )

        # z axis (3D projection: upper-right direction)
        if show_z:
            zx2 = ox + L * 0.6
            zy2 = oy - L * 0.45
            parts.append(
                f'<line x1="{ox:.1f}" y1="{oy:.1f}" '
                f'x2="{zx2 - 2:.1f}" y2="{zy2 + 2:.1f}" '
                f'stroke="{cz_col}" stroke-width="1.5" stroke-dasharray="4,2" '
                f'marker-end="url(#axZ)"/>'
            )
            parts.append(
                f'<text x="{zx2 + 3:.1f}" y="{zy2 - 3:.1f}" '
                f'font-size="11" fill="{cz_col}" font-style="italic">{html.escape(lz)}</text>'
            )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{size:.0f}" height="{size:.0f}" '
            f'viewBox="0 0 {size:.0f} {size:.0f}">\n' + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> CoordinateAxesPrimitive:
    return CoordinateAxesPrimitive()
