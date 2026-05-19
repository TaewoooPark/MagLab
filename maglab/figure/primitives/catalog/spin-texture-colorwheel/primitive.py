"""Magnetization azimuthal color wheel legend primitive (§12.4)."""

from __future__ import annotations

import math
from typing import Any


def _hsl_to_hex(h: float, s: float = 1.0, lightness: float = 0.5) -> str:
    """Convert HSL to HEX color (h in 0–360)."""
    h = h % 360
    c = (1 - abs(2 * lightness - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = lightness - c / 2

    if h < 60:
        r, g, b = c, x, 0.0
    elif h < 120:
        r, g, b = x, c, 0.0
    elif h < 180:
        r, g, b = 0.0, c, x
    elif h < 240:
        r, g, b = 0.0, x, c
    elif h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x

    ri, gi, bi = int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)
    return f"#{ri:02X}{gi:02X}{bi:02X}"


class SpinTextureColorwheelPrimitive:
    """Magnetization azimuthal HSL color wheel legend primitive."""

    name: str = "spin-texture-colorwheel"
    category: str = "spin/magnetic texture"
    tags: list[str] = [
        "colorwheel",
        "color wheel",
        "magnetization",
        "color",
        "spin",
        "HSL",
        "azimuthal",
        "micromagnetic",
    ]
    description: str = (
        "Magnetization azimuthal color wheel legend primitive. "
        "Standard color wheel legend representing in-plane magnetization direction via HSL color."
    )
    parameters: list[dict[str, Any]] = [
        {"name": "radius", "type": "float", "default": 30.0, "description": "Color wheel radius"},
        {"name": "n_sectors", "type": "int", "default": 36, "description": "Number of sectors"},
        {"name": "show_labels", "type": "bool", "default": True, "description": "Direction labels"},
    ]
    physics_convention: str = (
        "HSL color wheel — 0°=+x(red), 90°=+y(green), 180°=-x(cyan), 270°=-y(blue). "
        "Standard micromagnetic visualization convention."
    )
    references: list[str] = ["doi:10.1063/1.4870957"]
    provenance: dict[str, Any] = {"source": "handwritten", "author": "MagLab P4"}
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        """Generate the color wheel SVG."""
        radius = float(params.get("radius", 30.0))
        # R11-F3: clamp n_sectors to a positive minimum so division never raises
        n = max(1, int(params.get("n_sectors", 36)))
        show_labels = bool(params.get("show_labels", True))

        size = radius * 2 + 30
        cx = cy = size / 2

        parts: list[str] = []

        # Build color wheel using pie sectors
        sector_angle = 360.0 / n
        for i in range(n):
            angle_start = i * sector_angle - 90  # 0° = +y (top)
            angle_end = angle_start + sector_angle + 0.5  # slight overlap

            a1 = math.radians(angle_start)
            a2 = math.radians(angle_end)

            x1 = cx + radius * math.cos(a1)
            y1 = cy + radius * math.sin(a1)
            x2 = cx + radius * math.cos(a2)
            y2 = cy + radius * math.sin(a2)

            # HSL: use angle_start + 90 as hue (0°=+x→hue=0)
            hue = (angle_start + 90) % 360
            color = _hsl_to_hex(hue)

            large = 1 if sector_angle > 180 else 0
            path_d = (
                f"M {cx:.1f} {cy:.1f} "
                f"L {x1:.1f} {y1:.1f} "
                f"A {radius:.1f} {radius:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} Z"
            )
            parts.append(f'<path d="{path_d}" fill="{color}"/>')

        # White center circle (hole)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius * 0.35:.1f}" fill="white"/>')
        # Outer border
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" '
            f'fill="none" stroke="#666" stroke-width="0.5"/>'
        )

        if show_labels:
            offset = radius + 10
            for angle_deg, label in [(0, "+x"), (90, "+y"), (180, "-x"), (270, "-y")]:
                rad = math.radians(angle_deg - 90)
                lx = cx + offset * math.cos(rad)
                ly = cy + offset * math.sin(rad)
                parts.append(
                    f'<text x="{lx:.1f}" y="{ly + 3:.1f}" '
                    f'font-size="7" text-anchor="middle" fill="#444">{label}</text>'
                )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{size:.0f}" height="{size:.0f}" '
            f'viewBox="0 0 {size:.0f} {size:.0f}">\n' + "\n".join(parts) + "\n</svg>"
        )


def get_primitive() -> SpinTextureColorwheelPrimitive:
    return SpinTextureColorwheelPrimitive()
