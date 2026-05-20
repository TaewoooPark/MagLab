"""LLG precession / damping vector diagram primitive (§12.4)."""

from __future__ import annotations

import math
from typing import Any


class LLGPrecessionPrimitive:
    """LLG precession Bloch sphere diagram parametric primitive."""

    name: str = "llg-precession"
    category: str = "dynamics"
    tags: list[str] = [
        "LLG",
        "precession",
        "damping",
        "Bloch sphere",
        "torque",
        "dynamics",
        "magnetization",
    ]
    description: str = (
        "LLG precession / damping vector diagram (Bloch sphere). Renders Heff, "
        "precession arrows, and a damping spiral path on the Bloch sphere."
    )
    parameters: list[dict[str, Any]] = [
        {"name": "radius", "type": "float", "default": 50.0, "description": "Bloch sphere radius"},
        {
            "name": "theta_deg",
            "type": "float",
            "default": 45.0,
            "description": "Precession polar angle θ (degrees)",
        },
        {
            "name": "show_damping",
            "type": "bool",
            "default": True,
            "description": "Show damping spiral",
        },
        {"name": "show_heff", "type": "bool", "default": True, "description": "Show Heff arrow"},
    ]
    physics_convention: str = (
        "LLG equation. dM/dt = -γ(M×Heff) + α/Ms(M×dM/dt). Counter-clockwise precession."
    )
    references: list[str] = ["doi:10.1103/PhysRevB.72.014463"]
    provenance: dict[str, Any] = {"source": "handwritten", "author": "MagLab P4"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        """Generate the LLG Bloch sphere SVG."""
        radius = float(params.get("radius", 50.0))
        theta_deg = float(params.get("theta_deg", 45.0))
        show_damping = bool(params.get("show_damping", True))
        show_heff = bool(params.get("show_heff", True))

        size = radius * 2 + 40
        cx = cy = size / 2

        parts: list[str] = []

        # Bloch sphere
        parts.append(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{radius:.1f}" ry="{radius:.1f}" '
            f'fill="#F8F8FF" stroke="#888" stroke-width="0.8"/>'
        )
        # Equator dashed line
        parts.append(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{radius:.1f}" ry="{radius * 0.25:.1f}" '
            f'fill="none" stroke="#CCC" stroke-width="0.5" stroke-dasharray="3,2"/>'
        )

        # z axis
        parts.append(
            f'<line x1="{cx:.1f}" y1="{cy + radius:.1f}" '
            f'x2="{cx:.1f}" y2="{cy - radius - 8:.1f}" '
            f'stroke="#666" stroke-width="0.8"/>'
        )
        parts.append(
            f'<text x="{cx + 4:.1f}" y="{cy - radius - 10:.1f}" '
            f'font-size="10" fill="#666" font-style="italic">z (Heff)</text>'
        )

        # Magnetization vector M (along θ)
        theta = math.radians(theta_deg)
        mx = cx + radius * math.sin(theta) * 0.8
        my = cy - radius * math.cos(theta) * 0.8

        defs = (
            "<defs>"
            '<marker id="arrM" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
            '<path d="M0,0 L7,3.5 L0,7 Z" fill="#0055CC"/></marker>'
            '<marker id="arrH" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
            '<path d="M0,0 L7,3.5 L0,7 Z" fill="#CC0000"/></marker>'
            "</defs>"
        )
        parts.insert(0, defs)

        parts.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" '
            f'x2="{mx - 3:.1f}" y2="{my + 2:.1f}" '
            f'stroke="#0055CC" stroke-width="2" marker-end="url(#arrM)"/>'
        )
        parts.append(
            f'<text x="{mx + 4:.1f}" y="{my:.1f}" '
            f'font-size="11" fill="#0055CC" font-style="italic">M</text>'
        )

        # Heff arrow (along z)
        if show_heff:
            parts.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" '
                f'x2="{cx:.1f}" y2="{cy - radius * 0.7:.1f}" '
                f'stroke="#CC0000" stroke-width="1.5" stroke-dasharray="4,2" '
                f'marker-end="url(#arrH)"/>'
            )

        # Precession path (ellipse)
        prec_ry = radius * math.sin(theta) * 0.25
        prec_rx = radius * math.sin(theta)
        prec_cy = cy - radius * math.cos(theta)
        if prec_rx > 2:
            parts.append(
                f'<ellipse cx="{cx:.1f}" cy="{prec_cy:.1f}" '
                f'rx="{prec_rx:.1f}" ry="{prec_ry:.1f}" '
                f'fill="none" stroke="#0055CC" stroke-width="0.8" '
                f'stroke-dasharray="5,3" opacity="0.6"/>'
            )

        # Damping spiral (simplified: converging arrow)
        if show_damping and prec_rx > 2:
            damp_x = cx + prec_rx * 0.6
            damp_y = prec_cy + prec_ry * 0.3
            parts.append(
                f'<text x="{damp_x:.1f}" y="{damp_y:.1f}" '
                f'font-size="8" fill="#666" font-style="italic">α</text>'
            )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{size:.0f}" height="{size:.0f}" '
            f'viewBox="0 0 {size:.0f} {size:.0f}">\n' + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> LLGPrecessionPrimitive:
    return LLGPrecessionPrimitive()
