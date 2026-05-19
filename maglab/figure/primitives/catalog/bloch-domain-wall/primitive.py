"""Bloch-type domain wall spin texture primitive (§12.4)."""

from __future__ import annotations

import html
import math
from typing import Any


class BlochDomainWallPrimitive:
    """Bloch-type domain wall spin texture parametric primitive."""

    name: str = "bloch-domain-wall"
    category: str = "spin/magnetic texture"
    tags: list[str] = [
        "domain wall",
        "DW",
        "Bloch",
        "spin",
        "texture",
        "magnetization",
        "reversal",
        "chirality",
        "DW",
    ]
    description: str = (
        "Bloch-type domain wall spin texture primitive. Represents the spin rotation "
        "of a Bloch wall using wall thickness, magnetization color, and arrows. "
        "Convention: wall normal along x, spins rotate in the y-z plane."
    )
    parameters: list[dict[str, Any]] = [
        {"name": "n_spins", "type": "int", "default": 9, "description": "Number of arrows"},
        {
            "name": "wall_width",
            "type": "float",
            "default": 120.0,
            "description": "Wall width (SVG units)",
        },
        {
            "name": "chirality",
            "type": "int",
            "default": 1,
            "description": "Chirality: +1 (left-handed) / -1 (right-handed)",
        },
        {
            "name": "color_up",
            "type": "str",
            "default": "#0055CC",
            "description": "Spin-up color (blue)",
        },
        {
            "name": "color_down",
            "type": "str",
            "default": "#CC0000",
            "description": "Spin-down color (red)",
        },
        {
            "name": "show_domains",
            "type": "bool",
            "default": True,
            "description": "Show domain background",
        },
    ]
    physics_convention: str = (
        "Bloch wall convention. Wall propagation direction x, spins rotate in the y-z plane. Chirality ±1."
    )
    references: list[str] = ["doi:10.1103/PhysRevB.84.094410"]
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
        """Generate the Bloch domain wall SVG."""
        return self._render_svg(params)

    def _render_svg(self, params: dict[str, Any]) -> str:
        """SVG renderer."""
        n = int(params.get("n_spins", 9))
        # R11-F2: clamp wall_width to a positive minimum so division never raises
        wall_width = max(1.0, float(params.get("wall_width", 120.0)))
        chirality = int(params.get("chirality", 1))
        color_up = str(params.get("color_up", "#0055CC"))
        color_down = str(params.get("color_down", "#CC0000"))
        show_domains = bool(params.get("show_domains", True))

        total_w = wall_width + 60
        total_h = 80.0
        cx = total_w / 2
        cy = total_h / 2

        parts: list[str] = []

        # XML-safe color values for use in SVG attribute values.
        color_up_attr = html.escape(color_up, quote=True)
        color_down_attr = html.escape(color_down, quote=True)

        # Domain background
        if show_domains:
            parts.append(
                f'<rect x="0" y="0" width="{total_w / 2:.1f}" height="{total_h:.1f}" '
                f'fill="{color_up_attr}" opacity="0.15"/>'
            )
            parts.append(
                f'<rect x="{total_w / 2:.1f}" y="0" width="{total_w / 2:.1f}" '
                f'height="{total_h:.1f}" fill="{color_down_attr}" opacity="0.15"/>'
            )

        # Wall center marker
        parts.append(
            f'<line x1="{cx:.1f}" y1="5" x2="{cx:.1f}" y2="{total_h - 5:.1f}" '
            f'stroke="#999" stroke-width="0.5" stroke-dasharray="3,2"/>'
        )

        # Spin arrows (distributed along x; spins rotate about the z axis)
        arrow_len = 18.0
        xs = [total_w * (i + 0.5) / n for i in range(n)]

        for _i, x in enumerate(xs):
            # Bloch wall: spin angle phi = atan2(x - cx) from 0→π
            t = (x - (total_w * 0.5 - wall_width / 2)) / wall_width
            t = max(0.0, min(1.0, t))
            phi = chirality * math.pi * t  # 0→π (Bloch rotation)

            # Arrow direction (rotation in y-z plane → 2D projection)
            sz = math.cos(phi)  # z component (out-of-plane)
            sy = math.sin(phi)  # y component (in-plane, along wall)

            # Color: interpolate blue↔red via z component
            blend = (sz + 1.0) / 2.0
            r_c = int(0 * blend + 204 * (1 - blend))
            g_c = int(85 * blend + 0 * (1 - blend))
            b_c = int(204 * blend + 0 * (1 - blend))
            arr_color = f"rgb({r_c},{g_c},{b_c})"

            # Arrow (centered on cy; sy projected onto x component)
            dx = sy * arrow_len * 0.5
            dz = sz * arrow_len * 0.7
            x1 = x - dx
            y1 = cy + dz * 0.5
            x2 = x + dx - dx * 0.1
            y2 = cy - dz * 0.5

            parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
                f'x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{arr_color}" stroke-width="1.5" '
                f'marker-end="url(#arrBloch)" color="{arr_color}"/>'
            )

        defs = (
            '<defs><marker id="arrBloch" markerWidth="6" markerHeight="6" '
            'refX="5" refY="3" orient="auto">'
            '<path d="M0,0 L6,3 L0,6 Z" fill="currentColor"/>'
            "</marker></defs>"
        )

        # Labels
        parts.append(
            f'<text x="10" y="{total_h + 12:.1f}" font-size="9" fill="{color_up_attr}">↑</text>'
        )
        parts.append(
            f'<text x="{total_w - 15:.1f}" y="{total_h + 12:.1f}" '
            f'font-size="9" fill="{color_down_attr}">↓</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{total_h + 12:.1f}" '
            f'font-size="8" text-anchor="middle" fill="#666">Bloch DW</text>'
        )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{total_w:.0f}" height="{total_h + 15:.0f}" '
            f'viewBox="0 0 {total_w:.0f} {total_h + 15:.0f}">\n'
            f"{defs}\n" + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> BlochDomainWallPrimitive:
    """Registry loader factory function."""
    return BlochDomainWallPrimitive()
