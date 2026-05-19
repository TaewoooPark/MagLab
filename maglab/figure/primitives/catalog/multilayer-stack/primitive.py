"""Multilayer thin film stack cross-section primitive (§12.4).

Parametric cross-section of magnetic heterostructures such as Ta/CoFeB/MgO.
"""

from __future__ import annotations

import html
from typing import Any

_DEFAULT_LAYERS: list[dict[str, Any]] = [
    {"name": "MgO", "thickness_nm": 2.0, "color": "#E8E8E8"},
    {"name": "CoFeB", "thickness_nm": 1.0, "color": "#C00"},
    {"name": "Ta", "thickness_nm": 5.0, "color": "#888"},
    {"name": "SiO₂", "thickness_nm": 100.0, "color": "#D4E8FF"},
]


class MultilayerStackPrimitive:
    """Multilayer thin film stack cross-section parametric primitive."""

    name: str = "multilayer-stack"
    category: str = "sample/thin film structure"
    tags: list[str] = [
        "multilayer",
        "stack",
        "cross-section",
        "thin film",
        "heterostructure",
        "interface",
        "magnetic",
        "Ta",
        "CoFeB",
        "MgO",
        "HM",
        "FM",
        "oxide",
    ]
    description: str = (
        "Multilayer thin film stack cross-section primitive. Renders heterostructures "
        "such as Ta/CoFeB/MgO with parametric layer composition. "
        "Layer thickness, material name, and color are specified as parameters."
    )
    parameters: list[dict[str, Any]] = [
        {
            "name": "layers",
            "type": "list",
            "default": _DEFAULT_LAYERS,
            "description": "Layer list: [{name, thickness_nm, color}]",
        },
        {"name": "width", "type": "float", "default": 120.0, "description": "Figure width"},
        {
            "name": "thickness_scale",
            "type": "float",
            "default": 20.0,
            "description": "SVG height scale per nm",
        },
        {"name": "show_labels", "type": "bool", "default": True, "description": "Show layer labels"},
        {
            "name": "show_thickness",
            "type": "bool",
            "default": True,
            "description": "Show thickness values",
        },
    ]
    physics_convention: str = "Layers are specified in growth order from substrate upward. Interfaces shown as solid lines."
    references: list[str] = [
        "doi:10.1038/nmat3522",
        "doi:10.1126/science.1188919",
    ]
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
        """Generate the stack cross-section SVG from parameters."""
        if backend == "tikz":
            return self._render_tikz(params)
        return self._render_svg(params)

    def _render_svg(self, params: dict[str, Any]) -> str:
        """SVG backend."""
        layers: list[dict[str, Any]] = params.get("layers", _DEFAULT_LAYERS)
        width = float(params.get("width", 120.0))
        ts = float(params.get("thickness_scale", 20.0))
        show_labels = bool(params.get("show_labels", True))
        show_thickness = bool(params.get("show_thickness", True))

        parts: list[str] = []
        # Stack from bottom upward (layers[0] = bottom)
        # Calculate total height first
        total_h = sum(float(lay.get("thickness_nm", 1.0)) * ts for lay in layers)
        total_h = max(total_h, 10.0)

        y = total_h  # current y position (starting from bottom)
        label_x = width + 5

        for lay in layers:
            name = str(lay.get("name", "?"))
            thick_nm = float(lay.get("thickness_nm", 1.0))
            color = str(lay.get("color", "#AAA"))
            h = thick_nm * ts
            y -= h

            # Layer rectangle — escape color for safe insertion into an attribute value.
            color_attr = html.escape(color, quote=True)
            parts.append(
                f'<rect x="0" y="{y:.1f}" width="{width:.1f}" height="{h:.1f}" '
                f'fill="{color_attr}" stroke="#333" stroke-width="0.5"/>'
            )

            # Labels
            if show_labels or show_thickness:
                label_parts: list[str] = []
                if show_labels:
                    label_parts.append(name)
                if show_thickness:
                    label_parts.append(f"({thick_nm:.0f} nm)")
                label_text = " ".join(label_parts)
                font_size = min(10.0, max(6.0, h * 0.6))
                parts.append(
                    f'<text x="{label_x:.1f}" y="{y + h / 2:.1f}" '
                    f'font-size="{font_size:.1f}" dominant-baseline="middle" '
                    f'fill="#222">{html.escape(label_text)}</text>'
                )

        # Substrate label
        parts.append(
            f'<text x="{width / 2:.1f}" y="{total_h + 12:.1f}" '
            f'font-size="9" text-anchor="middle" fill="#666">substrate</text>'
        )

        svg_w = label_x + 80
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{svg_w:.0f}" height="{total_h + 20:.0f}" '
            f'viewBox="0 0 {svg_w:.0f} {total_h + 20:.0f}">\n' + "\n".join(parts) + "\n</svg>"
        )

    def _render_tikz(self, params: dict[str, Any]) -> str:
        """TikZ backend."""
        layers: list[dict[str, Any]] = params.get("layers", _DEFAULT_LAYERS)
        width = float(params.get("width", 3.0)) / 40.0  # cm
        ts = 0.05  # cm/nm

        lines: list[str] = [r"\begin{tikzpicture}"]
        y = 0.0
        for lay in reversed(layers):
            name = str(lay.get("name", "?"))
            thick = float(lay.get("thickness_nm", 1.0)) * ts
            lines.append(
                rf"  \filldraw[fill=gray!30] (0,{y:.2f}) rectangle ({width:.2f},{y + thick:.2f});"
            )
            lines.append(rf"  \node[right] at ({width:.2f},{y + thick / 2:.2f}) {{\small {name}}};")
            y += thick
        lines.append(r"\end{tikzpicture}")
        return "\n".join(lines)


def get_primitive() -> MultilayerStackPrimitive:
    """Registry loader factory function."""
    return MultilayerStackPrimitive()
