"""Bloch-type skyrmion spin texture primitive (§12.4)."""

from __future__ import annotations

import math
from typing import Any


class BlochSkyrmionPrimitive:
    """Bloch-type skyrmion parametric primitive."""

    name: str = "skyrmion-bloch"
    category: str = "spin/magnetic texture"
    tags: list[str] = [
        "skyrmion",
        "Bloch",
        "topology",
        "magnetization",
        "texture",
        "vortex",
        "helical",
    ]
    description: str = (
        "Bloch-type skyrmion spin texture primitive. Renders a circularly symmetric Bloch skyrmion "
        "as an array of arrows. Topological charge Q=-1. HSL color wheel representation available."
    )
    parameters: list[dict[str, Any]] = [
        {"name": "radius", "type": "float", "default": 50.0, "description": "Skyrmion radius"},
        {"name": "n_rings", "type": "int", "default": 3, "description": "Number of radial rings"},
        {"name": "n_per_ring", "type": "int", "default": 8, "description": "Arrows per ring"},
        {
            "name": "skyrmion_number",
            "type": "int",
            "default": -1,
            "description": "Skyrmion number (-1)",
        },
    ]
    physics_convention: str = "Bloch skyrmion. Spins rotate tangentially. Topological charge Q=-1."
    references: list[str] = ["doi:10.1038/nnano.2013.29"]
    provenance: dict[str, Any] = {"source": "handwritten", "author": "MagLab P4"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        """Generate the Bloch skyrmion SVG."""
        radius = float(params.get("radius", 50.0))
        n_rings = int(params.get("n_rings", 3))
        n_per_ring = int(params.get("n_per_ring", 8))
        skn = int(params.get("skyrmion_number", -1))

        size = radius * 2 + 20
        cx = cy = size / 2
        arrow_len = radius * 0.22

        parts: list[str] = []

        # Background circle
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" '
            f'fill="#F0F4FF" stroke="#888" stroke-width="0.5"/>'
        )

        defs = (
            '<defs><marker id="arrSkym" markerWidth="5" markerHeight="5" '
            'refX="4" refY="2.5" orient="auto">'
            '<path d="M0,0 L5,2.5 L0,5 Z" fill="inherit"/>'
            "</marker></defs>"
        )

        # Core spin (downward = skyrmion core)
        sz_core = -1.0 * skn
        core_color = "#CC0000" if sz_core < 0 else "#0055CC"
        arr_cy = cy + arrow_len * 0.5 if sz_core < 0 else cy - arrow_len * 0.5
        parts.append(
            f'<line x1="{cx:.1f}" y1="{cy - arrow_len * 0.4:.1f}" '
            f'x2="{cx:.1f}" y2="{arr_cy:.1f}" '
            f'stroke="{core_color}" stroke-width="2" '
            f'marker-end="url(#arrSkym)" color="{core_color}"/>'
        )

        # Ring spins
        for ring_i in range(1, n_rings + 1):
            r_frac = ring_i / n_rings
            r_pos = radius * r_frac
            # sz varies with distance (core→edge: -1→+1)
            sz = -1.0 * skn * math.cos(math.pi * r_frac)
            blend = (sz + 1.0) / 2.0
            r_c = int(0 * blend + 204 * (1 - blend))
            g_c = int(85 * blend)
            b_c = int(204 * blend)

            for j in range(n_per_ring):
                phi = 2 * math.pi * j / n_per_ring
                x = cx + r_pos * math.cos(phi)
                y = cy + r_pos * math.sin(phi)

                # Bloch: arrow direction = tangential
                tang_phi = phi + math.pi / 2  # tangent
                dx = math.cos(tang_phi) * arrow_len * 0.5
                dy = math.sin(tang_phi) * arrow_len * 0.5

                arr_color = f"rgb({r_c},{g_c},{b_c})"
                parts.append(
                    f'<line x1="{x - dx:.1f}" y1="{y - dy:.1f}" '
                    f'x2="{x + dx * 0.7:.1f}" y2="{y + dy * 0.7:.1f}" '
                    f'stroke="{arr_color}" stroke-width="1.2" '
                    f'marker-end="url(#arrSkym)" color="{arr_color}"/>'
                )

        parts.append(
            f'<text x="{cx:.1f}" y="{size - 2:.1f}" '
            f'font-size="8" text-anchor="middle" fill="#666">'
            f"Bloch skyrmion (Q={skn})</text>"
        )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{size:.0f}" height="{size:.0f}" '
            f'viewBox="0 0 {size:.0f} {size:.0f}">\n'
            f"{defs}\n" + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> BlochSkyrmionPrimitive:
    return BlochSkyrmionPrimitive()
