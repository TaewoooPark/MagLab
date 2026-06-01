"""Multilayer thin film stack cross-section primitive (§12.4).

Parametric cross-section of magnetic heterostructures such as Ta/CoFeB/MgO.
"""

from __future__ import annotations

import math
from typing import Any

from maglab.figure.primitives.svg import (
    color_value,
    fmt,
    positive_float,
    schematic_style,
    tag,
    text,
)

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
        {
            "name": "scale_mode",
            "type": "str",
            "default": "bounded",
            "description": "Thickness scaling: bounded, sqrt, or linear",
        },
        {
            "name": "label_mode",
            "type": "str",
            "default": "auto",
            "description": "Label placement: auto, callout, or inside",
        },
        {
            "name": "show_labels",
            "type": "bool",
            "default": True,
            "description": "Show layer labels",
        },
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
        return self._render_svg(params, style_key=style)

    def _render_svg(self, params: dict[str, Any], *, style_key: str = "nature") -> str:
        """SVG backend."""
        style = schematic_style(style_key)
        layers = _coerce_layers(params.get("layers", _DEFAULT_LAYERS), style=style)
        width = positive_float(params, "width", 120.0, minimum=40.0, maximum=500.0)
        ts = positive_float(params, "thickness_scale", 20.0, minimum=0.5, maximum=100.0)
        min_layer_height = positive_float(
            params, "min_layer_height", 7.0, minimum=2.0, maximum=40.0
        )
        scale_mode = str(params.get("scale_mode", "bounded")).lower()
        label_mode = str(params.get("label_mode", "auto")).lower()
        show_labels = bool(params.get("show_labels", True))
        show_thickness = bool(params.get("show_thickness", True))

        heights = _layer_heights(
            [float(lay["thickness_nm"]) for lay in layers],
            thickness_scale=ts,
            mode=scale_mode,
            min_layer_height=min_layer_height,
        )
        total_h = sum(heights)
        label_x = width + 24.0
        right_margin = 142.0 if (show_labels or show_thickness) else 10.0
        svg_w = width + right_margin
        svg_h = total_h + 24.0

        parts: list[str] = [
            tag(
                "rect",
                {
                    "x": 0,
                    "y": 0,
                    "width": fmt(width),
                    "height": fmt(total_h),
                    "fill": "#ffffff",
                    "stroke": "none",
                },
            )
        ]

        y = total_h
        layer_boxes: list[tuple[dict[str, Any], float, float]] = []

        for lay, h in zip(layers, heights, strict=True):
            y -= h
            layer_boxes.append((lay, y, h))
            parts.append(
                tag(
                    "rect",
                    {
                        "class": "maglab-layer",
                        "x": fmt(0),
                        "y": fmt(y),
                        "width": fmt(width),
                        "height": fmt(h),
                        "fill": lay["color"],
                        "stroke": "#333333",
                        "stroke_width": fmt(style.stroke_width),
                    },
                )
            )

        label_positions = _resolve_label_positions(
            [(y + h / 2.0) for _, y, h in layer_boxes],
            min_gap=style.label_gap,
            lower=style.label_size,
            upper=max(style.label_size, total_h - style.label_size),
        )

        for (lay, y, h), label_y in zip(layer_boxes, label_positions, strict=True):
            layer_label = _layer_label(lay, show_labels=show_labels, show_thickness=show_thickness)
            if not layer_label:
                continue

            can_place_inside = label_mode == "inside" or (
                label_mode == "auto" and h >= style.label_size * 1.8 and len(layer_label) <= 12
            )
            if can_place_inside:
                parts.append(
                    tag(
                        "text",
                        {
                            "class": "maglab-layer-label",
                            "x": fmt(width / 2.0),
                            "y": fmt(y + h / 2.0),
                            "font_family": style.font_family,
                            "font_size": fmt(style.small_label_size),
                            "text_anchor": "middle",
                            "dominant_baseline": "middle",
                            "fill": _label_fill(lay["color"]),
                        },
                        text(layer_label),
                    )
                )
            else:
                mid_y = y + h / 2.0
                parts.append(
                    tag(
                        "path",
                        {
                            "class": "maglab-layer-callout",
                            "d": (
                                f"M {fmt(width)} {fmt(mid_y)} L {fmt(label_x - 7)} {fmt(label_y)}"
                            ),
                            "fill": "none",
                            "stroke": "#555555",
                            "stroke_width": fmt(style.callout_width),
                        },
                    )
                )
                parts.append(
                    tag(
                        "text",
                        {
                            "class": "maglab-layer-label",
                            "x": fmt(label_x),
                            "y": fmt(label_y),
                            "font_family": style.font_family,
                            "font_size": fmt(style.label_size),
                            "dominant_baseline": "middle",
                            "fill": "#222222",
                        },
                        text(layer_label),
                    )
                )

        # A small growth-direction cue makes the stack convention explicit.
        parts.append(
            tag(
                "path",
                {
                    "class": "maglab-growth-arrow",
                    "d": f"M {fmt(width + 7)} {fmt(total_h)} L {fmt(width + 7)} {fmt(4)}",
                    "fill": "none",
                    "stroke": "#777777",
                    "stroke_width": fmt(style.axis_width),
                    "marker_end": "url(#growthArrow)",
                },
            )
        )
        defs = (
            '<defs><marker id="growthArrow" markerWidth="6" markerHeight="6" '
            'refX="5" refY="3" orient="auto">'
            '<path d="M0,0 L6,3 L0,6 Z" fill="#777777"/></marker></defs>'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{fmt(svg_w)}" height="{fmt(svg_h)}" '
            f'viewBox="0 0 {fmt(svg_w)} {fmt(svg_h)}">\n'
            f"{defs}\n" + "\n".join(parts) + "\n</svg>"
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


def _coerce_layers(raw_layers: object, *, style: Any) -> list[dict[str, Any]]:
    """Normalize layer dictionaries and infer role colors."""
    if not isinstance(raw_layers, list) or not raw_layers:
        raw_layers = _DEFAULT_LAYERS
    result: list[dict[str, Any]] = []
    for raw in raw_layers:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "?"))
        role = str(raw.get("role", _infer_role(name))).lower()
        try:
            thickness = float(raw.get("thickness_nm", 1.0))
        except (TypeError, ValueError):
            thickness = 1.0
        thickness = max(0.05, thickness)
        fallback = style.color(role, _role_fallback(role))
        result.append(
            {
                "name": name,
                "role": role,
                "thickness_nm": thickness,
                "color": color_value(raw.get("color", fallback), fallback),
            }
        )
    return result or _coerce_layers(_DEFAULT_LAYERS, style=style)


def _infer_role(name: str) -> str:
    """Infer a visual role from common spintronic stack material names."""
    lower = name.lower()
    if any(token in lower for token in ("cofe", "co", "fe", "ni", "fm")):
        return "ferromagnet"
    if any(token in lower for token in ("mgo", "alox", "oxide", "sio", "sio2", "sio₂")):
        return "oxide" if "substrate" not in lower else "substrate"
    if any(token in lower for token in ("pt", "ta", "w", "hm", "heavy")):
        return "heavy_metal"
    if "cap" in lower:
        return "cap"
    if "substrate" in lower or lower.startswith("si"):
        return "substrate"
    return "neutral"


def _role_fallback(role: str) -> str:
    """Fallback color for a material role."""
    return {
        "heavy_metal": "#8f969e",
        "ferromagnet": "#c43c39",
        "oxide": "#eeeeee",
        "substrate": "#d9e8f6",
        "cap": "#7f858b",
    }.get(role, "#aaaaaa")


def _layer_heights(
    thicknesses: list[float],
    *,
    thickness_scale: float,
    mode: str,
    min_layer_height: float,
) -> list[float]:
    """Map physical thicknesses to legible SVG layer heights."""
    if mode == "linear":
        return [max(min_layer_height, t * thickness_scale) for t in thicknesses]

    raw = [math.sqrt(t) if mode in {"bounded", "sqrt"} else t for t in thicknesses]
    target_total = min(190.0, max(72.0, sum(thicknesses) * thickness_scale))
    total_raw = sum(raw) or 1.0
    heights = [max(min_layer_height, target_total * value / total_raw) for value in raw]
    overflow = sum(heights) - target_total
    if overflow <= 0:
        return heights
    flexible = [i for i, h in enumerate(heights) if h > min_layer_height]
    if not flexible:
        return heights
    per = overflow / len(flexible)
    for i in flexible:
        heights[i] = max(min_layer_height, heights[i] - per)
    return heights


def _layer_label(layer: dict[str, Any], *, show_labels: bool, show_thickness: bool) -> str:
    """Build a compact label string."""
    parts: list[str] = []
    if show_labels:
        parts.append(str(layer["name"]))
    if show_thickness:
        parts.append(f"({layer['thickness_nm']:.3g} nm)")
    return " ".join(parts)


def _resolve_label_positions(
    preferred: list[float],
    *,
    min_gap: float,
    lower: float,
    upper: float,
) -> list[float]:
    """Resolve vertically stacked callout labels without overlap."""
    if not preferred:
        return []
    order = sorted(range(len(preferred)), key=preferred.__getitem__)
    placed = preferred[:]
    last = lower - min_gap
    for idx in order:
        placed[idx] = max(preferred[idx], last + min_gap)
        last = placed[idx]
    excess = max(0.0, last - upper)
    if excess:
        for idx in order:
            placed[idx] -= excess
    return placed


def _label_fill(color: str) -> str:
    """Choose text color for internal labels."""
    value = color.lstrip("#")
    if len(value) not in {3, 6, 8}:
        return "#222222"
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    try:
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return "#222222"
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#ffffff" if luminance < 120 else "#222222"
