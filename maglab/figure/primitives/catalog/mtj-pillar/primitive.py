"""Magnetic tunnel junction (MTJ) pillar cross-section primitive (§12.4)."""

from __future__ import annotations

import html
from typing import Any


class MTJPillarPrimitive:
    """MTJ pillar cross-section parametric primitive."""

    name: str = "mtj-pillar"
    category: str = "device geometry"
    tags: list[str] = [
        "MTJ",
        "magnetic tunnel junction",
        "pillar",
        "device",
        "spin valve",
        "FM",
        "ferromagnet",
        "tunnel",
        "barrier",
        "MgO",
    ]
    description: str = (
        "Magnetic tunnel junction (MTJ) pillar cross-section primitive. "
        "Cross-section diagram of an MTJ device composed of pinned layer / tunnel barrier / free layer."
    )
    parameters: list[dict[str, Any]] = [
        {"name": "width", "type": "float", "default": 60.0, "description": "Pillar width"},
        {
            "name": "free_color",
            "type": "str",
            "default": "#4472C4",
            "description": "Free layer color",
        },
        {
            "name": "fixed_color",
            "type": "str",
            "default": "#C00020",
            "description": "Fixed layer color",
        },
        {
            "name": "barrier_color",
            "type": "str",
            "default": "#E8E8E8",
            "description": "Barrier color (MgO)",
        },
        {
            "name": "free_direction",
            "type": "str",
            "default": "right",
            "description": "Free layer magnetization direction (left/right/up/down)",
        },
        {
            "name": "fixed_direction",
            "type": "str",
            "default": "right",
            "description": "Fixed layer magnetization direction",
        },
    ]
    physics_convention: str = (
        "Bottom = pinned layer (fixed), middle = MgO barrier, top = free layer. Magnetization arrows shown."
    )
    references: list[str] = ["doi:10.1103/PhysRevLett.84.3149"]
    provenance: dict[str, Any] = {"source": "handwritten", "author": "MagLab P4"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        """Generate the MTJ pillar SVG."""
        width = float(params.get("width", 60.0))
        # Escape color values for safe insertion into SVG attribute values.
        free_color = html.escape(str(params.get("free_color", "#4472C4")), quote=True)
        fixed_color = html.escape(str(params.get("fixed_color", "#C00020")), quote=True)
        barrier_color = html.escape(str(params.get("barrier_color", "#E8E8E8")), quote=True)
        free_dir = str(params.get("free_direction", "right"))
        fixed_dir = str(params.get("fixed_direction", "right"))

        h_layer = 20.0
        h_barrier = 8.0
        total_h = h_layer * 2 + h_barrier + 30
        total_w = width + 80

        cx = width / 2

        def arrow_svg(direction: str, ax: float, ay: float, color: str, label: str) -> str:
            """Directional arrow SVG.

            Renders a magnetization arrow for the given direction.  The marker
            ``#arrMTJ`` uses ``orient="auto"``, so the arrowhead automatically
            rotates to face the direction of the line vector.

            Parameters
            ----------
            direction:
                One of ``"right"``, ``"left"``, ``"up"``, or ``"down"``.
                Any other value is silently ignored (returns ``""``).
            ax, ay:
                Centre coordinates of the layer rectangle.
            color:
                SVG color string (already escaped).
            label:
                Optional text label appended after the arrowhead (used only
                for the ``"right"`` branch that shows the layer label).
            """
            if direction == "right":
                return (
                    f'<line x1="{ax - 12:.1f}" y1="{ay:.1f}" '
                    f'x2="{ax + 8:.1f}" y2="{ay:.1f}" '
                    f'stroke="{color}" stroke-width="2" '
                    f'marker-end="url(#arrMTJ)"/>'
                    f'<text x="{ax + 12:.1f}" y="{ay + 4:.1f}" '
                    f'font-size="9" fill="{color}">{label}</text>'
                )
            if direction == "left":
                return (
                    f'<line x1="{ax + 12:.1f}" y1="{ay:.1f}" '
                    f'x2="{ax - 8:.1f}" y2="{ay:.1f}" '
                    f'stroke="{color}" stroke-width="2" '
                    f'marker-end="url(#arrMTJ)"/>'
                )
            if direction == "up":
                # Arrow points upward: line goes from below the centre to above.
                # The marker orient="auto" rotates the arrowhead to face the tip
                # (the x2,y2 end), which is the smaller y value (SVG y increases
                # downward), i.e. the visual top of the layer.
                return (
                    f'<line x1="{ax:.1f}" y1="{ay + 12:.1f}" '
                    f'x2="{ax:.1f}" y2="{ay - 8:.1f}" '
                    f'stroke="{color}" stroke-width="2" '
                    f'marker-end="url(#arrMTJ)"/>'
                )
            if direction == "down":
                # Arrow points downward: line goes from above the centre to below.
                # The tip (x2,y2) is at the larger y value (visual bottom).
                return (
                    f'<line x1="{ax:.1f}" y1="{ay - 12:.1f}" '
                    f'x2="{ax:.1f}" y2="{ay + 8:.1f}" '
                    f'stroke="{color}" stroke-width="2" '
                    f'marker-end="url(#arrMTJ)"/>'
                )
            return ""

        defs = (
            '<defs><marker id="arrMTJ" markerWidth="6" markerHeight="6" '
            'refX="5" refY="3" orient="auto">'
            '<path d="M0,0 L6,3 L0,6 Z" fill="inherit"/></marker></defs>'
        )

        parts: list[str] = [defs]

        # Fixed layer (bottom)
        y_fixed = total_h - h_layer - 10
        parts.append(
            f'<rect x="0" y="{y_fixed:.1f}" width="{width:.1f}" height="{h_layer:.1f}" '
            f'fill="{fixed_color}" stroke="#333" stroke-width="0.8"/>'
        )
        parts.append(
            f'<text x="{width + 5:.1f}" y="{y_fixed + h_layer / 2 + 4:.1f}" '
            f'font-size="9" fill="{fixed_color}">Fixed (FM)</text>'
        )
        parts.append(arrow_svg(fixed_dir, cx, y_fixed + h_layer / 2, fixed_color, ""))

        # MgO barrier
        y_barrier = y_fixed - h_barrier
        parts.append(
            f'<rect x="0" y="{y_barrier:.1f}" width="{width:.1f}" height="{h_barrier:.1f}" '
            f'fill="{barrier_color}" stroke="#333" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{width + 5:.1f}" y="{y_barrier + h_barrier / 2 + 3:.1f}" '
            f'font-size="8" fill="#666">MgO</text>'
        )

        # Free layer (top)
        y_free = y_barrier - h_layer
        parts.append(
            f'<rect x="0" y="{y_free:.1f}" width="{width:.1f}" height="{h_layer:.1f}" '
            f'fill="{free_color}" stroke="#333" stroke-width="0.8"/>'
        )
        parts.append(
            f'<text x="{width + 5:.1f}" y="{y_free + h_layer / 2 + 4:.1f}" '
            f'font-size="9" fill="{free_color}">Free (FM)</text>'
        )
        parts.append(arrow_svg(free_dir, cx, y_free + h_layer / 2, free_color, ""))

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{total_w:.0f}" height="{total_h:.0f}" '
            f'viewBox="0 0 {total_w:.0f} {total_h:.0f}">\n' + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> MTJPillarPrimitive:
    return MTJPillarPrimitive()
