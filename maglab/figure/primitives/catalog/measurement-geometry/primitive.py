"""Measurement geometry vector diagram primitive (§12.4)."""

from __future__ import annotations

import math
from typing import Any


class MeasurementGeometryPrimitive:
    """Measurement geometry vector diagram parametric primitive."""

    name: str = "measurement-geometry"
    category: str = "measurement geometry"
    tags: list[str] = [
        "measurement",
        "geometry",
        "current",
        "magnetic field",
        "voltage",
        "vector",
        "angle",
        "direction",
        "arrow",
        "MOKE",
        "FMR",
        "transport",
    ]
    description: str = (
        "Measurement geometry vector diagram. Standard measurement geometry schematic "
        "showing current (I), magnetic field (H), and voltage (V) direction arrows "
        "along with rotation angle (θ, φ) definitions."
    )
    parameters: list[dict[str, Any]] = [
        {
            "name": "angle_theta_deg",
            "type": "float",
            "default": 0.0,
            "description": "In-plane magnetic field angle θ (degrees)",
        },
        {
            "name": "show_current",
            "type": "bool",
            "default": True,
            "description": "Show current arrow",
        },
        {
            "name": "show_field",
            "type": "bool",
            "default": True,
            "description": "Show field arrow",
        },
        {
            "name": "show_voltage",
            "type": "bool",
            "default": True,
            "description": "Show voltage arrow",
        },
        {
            "name": "size",
            "type": "float",
            "default": 100.0,
            "description": "Diagram size (SVG units)",
        },
    ]
    physics_convention: str = (
        "Right-hand coordinate system. x=current, y=Hall voltage, z=out-of-plane. θ is the in-plane angle, φ is the out-of-plane angle."
    )
    references: list[str] = ["doi:10.1103/PhysRevB.89.144425"]
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
        """Generate the measurement geometry SVG."""
        return self._render_svg(params)

    def _render_svg(self, params: dict[str, Any]) -> str:
        """SVG renderer."""
        theta = float(params.get("angle_theta_deg", 0.0))
        show_current = bool(params.get("show_current", True))
        show_field = bool(params.get("show_field", True))
        show_voltage = bool(params.get("show_voltage", True))
        size = float(params.get("size", 100.0))

        cx, cy = size / 2, size / 2
        r = size * 0.35

        parts: list[str] = []

        # Reference circle
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="none" stroke="#DDD" stroke-width="0.5" stroke-dasharray="4,2"/>'
        )

        defs_content = (
            '<marker id="arrowR" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">'
            '<path d="M0,0 L8,3 L0,6 Z" fill="#C00"/></marker>'
            '<marker id="arrowB" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">'
            '<path d="M0,0 L8,3 L0,6 Z" fill="#0055CC"/></marker>'
            '<marker id="arrowG" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">'
            '<path d="M0,0 L8,3 L0,6 Z" fill="#007700"/></marker>'
        )

        # Current arrow (x direction →)
        if show_current:
            x2 = cx + r
            parts.append(
                f'<line x1="{cx - r:.1f}" y1="{cy:.1f}" '
                f'x2="{x2 - 4:.1f}" y1="{cy:.1f}" '
                f'stroke="#C00" stroke-width="2" marker-end="url(#arrowR)"/>'
            )
            parts.append(
                f'<text x="{x2 + 3:.1f}" y="{cy + 4:.1f}" '
                f'font-size="11" fill="#C00" font-style="italic">I</text>'
            )

        # Magnetic field arrow (along θ)
        if show_field:
            rad = math.radians(theta)
            hx = cx + r * math.cos(rad)
            hy = cy - r * math.sin(rad)
            parts.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" '
                f'x2="{hx - 4 * math.cos(rad):.1f}" '
                f'y2="{hy + 4 * math.sin(rad):.1f}" '
                f'stroke="#0055CC" stroke-width="2" marker-end="url(#arrowB)"/>'
            )
            label_x = cx + (r + 10) * math.cos(rad)
            label_y = cy - (r + 10) * math.sin(rad)
            parts.append(
                f'<text x="{label_x:.1f}" y="{label_y + 4:.1f}" '
                f'font-size="11" fill="#0055CC" font-style="italic">H</text>'
            )

        # Hall voltage arrow (y direction ↑)
        if show_voltage:
            parts.append(
                f'<line x1="{cx:.1f}" y1="{cy + r:.1f}" '
                f'x2="{cx:.1f}" y2="{cy - r + 4:.1f}" '
                f'stroke="#007700" stroke-width="2" marker-end="url(#arrowG)"/>'
            )
            parts.append(
                f'<text x="{cx + 3:.1f}" y="{cy - r - 2:.1f}" '
                f'font-size="11" fill="#007700" font-style="italic">V_H</text>'
            )

        # Angle label θ
        if show_field and theta != 0.0:
            parts.append(
                f'<text x="{cx + 12:.1f}" y="{cy - 5:.1f}" '
                f'font-size="10" fill="#666">θ={theta:.0f}°</text>'
            )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{size:.0f}" height="{size:.0f}" '
            f'viewBox="0 0 {size:.0f} {size:.0f}">\n'
            f"<defs>{defs_content}</defs>\n" + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> MeasurementGeometryPrimitive:
    """Registry loader factory function."""
    return MeasurementGeometryPrimitive()
