"""Néel-type domain wall spin texture primitive (§12.4)."""

from __future__ import annotations

import math
from typing import Any


class NeelDomainWallPrimitive:
    """Néel-type domain wall parametric primitive."""

    name: str = "neel-domain-wall"
    category: str = "spin/magnetic texture"
    tags: list[str] = [
        "domain wall",
        "DW",
        "Neel",
        "Néel",
        "spin",
        "texture",
        "SOT",
        "DMI",
        "chiral",
    ]
    description: str = (
        "Néel-type domain wall spin texture primitive. Parametrically renders the Néel wall "
        "observed in SOT/DMI systems. Spins rotate in the wall propagation direction x."
    )
    parameters: list[dict[str, Any]] = [
        {"name": "n_spins", "type": "int", "default": 9, "description": "Number of arrows"},
        {"name": "wall_width", "type": "float", "default": 120.0, "description": "Wall width"},
        {"name": "chirality", "type": "int", "default": 1, "description": "DMI chirality ±1"},
    ]
    physics_convention: str = "Néel wall. Spins rotate in the x-z plane. DMI chirality."
    references: list[str] = ["doi:10.1038/ncomms3944"]
    provenance: dict[str, Any] = {"source": "handwritten", "author": "MagLab P4"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        """Generate the Néel wall SVG."""
        n = int(params.get("n_spins", 9))
        # R11-F1: clamp wall_width to a positive minimum so division never raises
        wall_width = max(1.0, float(params.get("wall_width", 120.0)))
        chirality = int(params.get("chirality", 1))

        total_w = wall_width + 60
        total_h = 80.0
        cx = total_w / 2

        parts: list[str] = []
        parts.append(
            f'<rect x="0" y="0" width="{total_w / 2:.1f}" height="{total_h:.1f}" '
            f'fill="#0055CC" opacity="0.15"/>'
        )
        parts.append(
            f'<rect x="{total_w / 2:.1f}" y="0" width="{total_w / 2:.1f}" '
            f'height="{total_h:.1f}" fill="#CC0000" opacity="0.15"/>'
        )

        arrow_len = 20.0
        cy = total_h / 2
        xs = [total_w * (i + 0.5) / n for i in range(n)]

        defs = (
            '<defs><marker id="arrNeel" markerWidth="6" markerHeight="6" '
            'refX="5" refY="3" orient="auto">'
            '<path d="M0,0 L6,3 L0,6 Z" fill="inherit"/>'
            "</marker></defs>"
        )

        for _i, x in enumerate(xs):
            t = (x - (total_w * 0.5 - wall_width / 2)) / wall_width
            t = max(0.0, min(1.0, t))
            phi = chirality * math.pi * t

            # Néel: spins rotate in x-z plane → x component is in-plane
            sx = math.sin(phi)  # in-plane x component
            sz = math.cos(phi)  # out-of-plane z component

            blend = (sz + 1.0) / 2.0
            r_c = int(0 * blend + 204 * (1 - blend))
            g_c = int(85 * blend)
            b_c = int(204 * blend)
            arr_color = f"rgb({r_c},{g_c},{b_c})"

            dx = sx * arrow_len * 0.5
            dz = sz * arrow_len * 0.5
            parts.append(
                f'<line x1="{x - dx:.1f}" y1="{cy + dz:.1f}" '
                f'x2="{x + dx * 0.85:.1f}" y2="{cy - dz * 0.85:.1f}" '
                f'stroke="{arr_color}" stroke-width="1.5" '
                f'marker-end="url(#arrNeel)" color="{arr_color}"/>'
            )

        parts.append(
            f'<text x="{cx:.1f}" y="{total_h + 12:.1f}" '
            f'font-size="8" text-anchor="middle" fill="#666">Néel DW</text>'
        )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{total_w:.0f}" height="{total_h + 15:.0f}" '
            f'viewBox="0 0 {total_w:.0f} {total_h + 15:.0f}">\n'
            f"{defs}\n" + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> NeelDomainWallPrimitive:
    return NeelDomainWallPrimitive()
