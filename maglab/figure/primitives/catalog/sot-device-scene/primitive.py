"""Publication-style SOT device schematic scene (§12.4)."""

from __future__ import annotations

import math
from typing import Any

from maglab.figure.primitives.svg import (
    SchematicFrame,
    color_value,
    fmt,
    positive_float,
    schematic_style,
    tag,
    text,
)

_DEFAULT_LAYERS: list[dict[str, Any]] = [
    {"name": "Si/SiO2", "role": "substrate", "thickness_nm": 500.0, "color": "#d9e8f6"},
    {"name": "Pt", "role": "heavy_metal", "thickness_nm": 5.0, "color": "#8f969e"},
    {"name": "CoFeB", "role": "ferromagnet", "thickness_nm": 1.1, "color": "#c43c39"},
    {"name": "MgO", "role": "oxide", "thickness_nm": 2.0, "color": "#eeeeee"},
    {"name": "Ta cap", "role": "cap", "thickness_nm": 2.0, "color": "#7f858b"},
]


class SotDeviceScenePrimitive:
    """Composite SOT stack-to-Hall-bar schematic.

    This primitive follows a layout-first drawing strategy: the scene has named
    regions for the cross-section, process arrow, device top view, and coordinate
    axes.  Shapes are then attached to semantic anchors inside those regions.
    """

    name: str = "sot-device-scene"
    category: str = "concept/process"
    tags: list[str] = [
        "SOT",
        "spin-orbit torque",
        "Hall bar",
        "multilayer",
        "stack",
        "measurement",
        "device",
        "spintronics",
    ]
    description: str = (
        "Publication-style SOT device scene connecting a multilayer cross-section "
        "to a patterned Hall bar transport geometry with measurement annotations."
    )
    parameters: list[dict[str, Any]] = [
        {
            "name": "layers",
            "type": "list",
            "default": _DEFAULT_LAYERS,
            "description": "Layer list: [{name, role, thickness_nm, color}]",
        },
        {
            "name": "device_label",
            "type": "str",
            "default": "HM/FM/Oxide",
            "description": "Label shown on the Hall bar channel",
        },
        {
            "name": "show_process_arrow",
            "type": "bool",
            "default": True,
            "description": "Show stack-to-device process arrow",
        },
        {
            "name": "show_axes",
            "type": "bool",
            "default": True,
            "description": "Show compact coordinate axes",
        },
        {
            "name": "show_voltage",
            "type": "bool",
            "default": True,
            "description": "Show Hall-voltage annotation",
        },
        {
            "name": "show_field",
            "type": "bool",
            "default": True,
            "description": "Show out-of-plane field marker",
        },
    ]
    physics_convention: str = (
        "Layers are shown in growth order from substrate upward. Hall bar: current along "
        "x, Hall voltage along y, out-of-plane field along z."
    )
    references: list[str] = [
        "doi:10.1038/nmat3522",
        "doi:10.1126/science.1188919",
        "doi:10.1103/PhysRevLett.88.117601",
    ]
    provenance: dict[str, Any] = {
        "source": "handwritten",
        "author": "MagLab P4",
        "physics_verified": True,
    }
    preview: str | None = None
    journal_styles: list[str] = ["nature", "aps", "ieee", "elsevier"]

    def render(self, params: dict[str, Any], backend: str = "svg", style: str = "nature") -> str:
        """Generate the composite SOT device scene SVG."""
        if backend == "tikz":
            return self._render_tikz(params)
        return self._render_svg(params, style_key=style)

    def _render_svg(self, params: dict[str, Any], *, style_key: str = "nature") -> str:
        """SVG renderer."""
        style = schematic_style(style_key)
        width = positive_float(params, "width", 520.0, minimum=360.0, maximum=900.0)
        height = positive_float(params, "height", 210.0, minimum=180.0, maximum=600.0)
        device_label = str(params.get("device_label", "HM/FM/Oxide"))
        show_process_arrow = bool(params.get("show_process_arrow", True))
        show_axes = bool(params.get("show_axes", True))
        show_voltage = bool(params.get("show_voltage", True))
        show_field = bool(params.get("show_field", True))
        layers = _coerce_layers(params.get("layers", _DEFAULT_LAYERS), style=style)
        stack_frame = SchematicFrame(36.0, 56.0, 142.0, 120.0)
        device_frame = SchematicFrame(294.0, 66.0, 174.0, 116.0)
        axis_origin = device_frame.point(0.85, 1.07)

        parts: list[str] = [
            tag(
                "rect", {"x": 0, "y": 0, "width": fmt(width), "height": fmt(height), "fill": "#fff"}
            )
        ]
        parts.extend(_draw_stack(layers, style=style, frame=stack_frame))
        if show_process_arrow:
            arrow_start = stack_frame.point(1.18, 0.58)
            arrow_end = device_frame.point(-0.13, 0.52)
            parts.extend(
                _draw_process_arrow(
                    style=style,
                    x1=arrow_start[0],
                    y=arrow_start[1],
                    x2=arrow_end[0],
                )
            )
        parts.extend(
            _draw_hall_bar(
                style=style,
                frame=device_frame,
                label=device_label,
                show_voltage=show_voltage,
                show_field=show_field,
            )
        )
        if show_axes:
            parts.extend(_draw_axes(style=style, ox=axis_origin[0], oy=axis_origin[1], length=30.0))

        defs = (
            "<defs>"
            '<marker id="sotArrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
            '<path d="M0,0 L7,3.5 L0,7 Z" fill="#555555"/></marker>'
            '<marker id="sotCurrentArrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
            f'<path d="M0,0 L7,3.5 L0,7 Z" fill="{style.color("current", "#c43c39")}"/></marker>'
            '<marker id="sotVoltageArrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
            f'<path d="M0,0 L7,3.5 L0,7 Z" fill="{style.color("voltage", "#237a4b")}"/></marker>'
            "</defs>"
        )
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{fmt(width)}" height="{fmt(height)}" '
            f'viewBox="0 0 {fmt(width)} {fmt(height)}">\n'
            f"{defs}\n" + "\n".join(parts) + "\n</svg>"
        )

    def _render_tikz(self, params: dict[str, Any]) -> str:
        """TikZ fallback placeholder."""
        return (
            r"\begin{tikzpicture}" + "\n"
            r"  \node[draw, rounded corners] {SOT stack $\rightarrow$ Hall bar};" + "\n"
            r"\end{tikzpicture}"
        )


def _draw_stack(
    layers: list[dict[str, Any]],
    *,
    style: Any,
    frame: SchematicFrame,
) -> list[str]:
    """Draw a bounded multilayer stack with external callout labels."""
    x, y, width, height = frame.x, frame.y, frame.width, frame.height
    heights = _bounded_heights([float(layer["thickness_nm"]) for layer in layers], height=height)
    parts: list[str] = []
    current_y = y + height
    label_x = x + width + 22.0
    label_targets: list[float] = []
    boxes: list[tuple[dict[str, Any], float, float]] = []

    for layer, h in zip(layers, heights, strict=True):
        current_y -= h
        boxes.append((layer, current_y, h))
        parts.append(
            tag(
                "rect",
                {
                    "class": "maglab-sot-stack-layer",
                    "x": fmt(x),
                    "y": fmt(current_y),
                    "width": fmt(width),
                    "height": fmt(h),
                    "fill": layer["color"],
                    "stroke": "#2f3437",
                    "stroke_width": fmt(style.stroke_width),
                },
            )
        )
        label_targets.append(current_y + h / 2.0)

    label_positions = _spread(label_targets, min_gap=13.5, lower=y + 8.0, upper=y + height - 8.0)
    for (layer, layer_y, h), label_y in zip(boxes, label_positions, strict=True):
        mid_y = layer_y + h / 2.0
        parts.append(
            tag(
                "path",
                {
                    "class": "maglab-sot-stack-callout",
                    "d": f"M {fmt(x + width)} {fmt(mid_y)} L {fmt(label_x - 8)} {fmt(label_y)}",
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
                    "class": "maglab-sot-stack-label",
                    "x": fmt(label_x),
                    "y": fmt(label_y),
                    "font_family": style.font_family,
                    "font_size": fmt(style.small_label_size),
                    "dominant_baseline": "middle",
                    "fill": "#202020",
                },
                text(f"{layer['name']} ({layer['thickness_nm']:.3g} nm)"),
            )
        )

    parts.append(
        tag(
            "text",
            {
                "x": fmt(x),
                "y": fmt(y - 13),
                "font_family": style.font_family,
                "font_size": fmt(style.label_size),
                "font_weight": "600",
                "fill": "#202020",
            },
            "heterostructure",
        )
    )
    return parts


def _draw_process_arrow(*, style: Any, x1: float, y: float, x2: float) -> list[str]:
    """Draw a clean process arrow between stack and device."""
    return [
        tag(
            "path",
            {
                "class": "maglab-sot-process-arrow",
                "d": f"M {fmt(x1)} {fmt(y)} C {fmt(x1 + 18)} {fmt(y - 16)} "
                f"{fmt(x2 - 18)} {fmt(y - 16)} {fmt(x2)} {fmt(y)}",
                "fill": "none",
                "stroke": "#555555",
                "stroke_width": fmt(style.axis_width),
                "marker_end": "url(#sotArrow)",
            },
        ),
    ]


def _draw_hall_bar(
    *,
    style: Any,
    frame: SchematicFrame,
    label: str,
    show_voltage: bool,
    show_field: bool,
) -> list[str]:
    """Draw a top-view Hall bar with transport annotations."""
    x, y, width, height = frame.x, frame.y, frame.width, frame.height
    channel_h = height * 0.32
    channel_y = y + height * 0.36
    contact_w = width * 0.13
    voltage_w = width * 0.13
    voltage_h = height * 0.38
    x_left = x
    x_right = x + width
    channel_x = x + contact_w
    channel_w = width - 2 * contact_w
    color = "#4978c7"
    parts: list[str] = []

    parts.append(
        tag(
            "text",
            {
                "x": fmt(x),
                "y": fmt(y - 13),
                "font_family": style.font_family,
                "font_size": fmt(style.label_size),
                "font_weight": "600",
                "fill": "#202020",
            },
            "transport geometry",
        )
    )
    for rect_x, rect_y, rect_w, rect_h, klass in [
        (channel_x, channel_y, channel_w, channel_h, "maglab-sot-hall-channel"),
        (x_left, channel_y, contact_w, channel_h, "maglab-sot-current-contact"),
        (x_right - contact_w, channel_y, contact_w, channel_h, "maglab-sot-current-contact"),
        (x + width * 0.30, y, voltage_w, voltage_h, "maglab-sot-voltage-contact"),
        (x + width * 0.60, y, voltage_w, voltage_h, "maglab-sot-voltage-contact"),
        (
            x + width * 0.22,
            channel_y + channel_h,
            voltage_w,
            voltage_h,
            "maglab-sot-voltage-contact",
        ),
        (
            x + width * 0.63,
            channel_y + channel_h,
            voltage_w,
            voltage_h,
            "maglab-sot-voltage-contact",
        ),
    ]:
        parts.append(
            tag(
                "rect",
                {
                    "class": klass,
                    "x": fmt(rect_x),
                    "y": fmt(rect_y),
                    "width": fmt(rect_w),
                    "height": fmt(rect_h),
                    "fill": color,
                    "stroke": "#1f2530",
                    "stroke_width": fmt(style.stroke_width),
                },
            )
        )

    center_y = channel_y + channel_h / 2.0
    parts.append(
        tag(
            "line",
            {
                "class": "maglab-sot-current-arrow",
                "x1": fmt(x + 8),
                "y1": fmt(center_y),
                "x2": fmt(x + 52),
                "y2": fmt(center_y),
                "stroke": style.color("current", "#c43c39"),
                "stroke_width": fmt(style.arrow_width),
                "marker_end": "url(#sotCurrentArrow)",
            },
        )
    )
    parts.append(
        tag(
            "text",
            {
                "x": fmt(x + 27),
                "y": fmt(center_y - 9),
                "font_family": style.font_family,
                "font_size": fmt(style.small_label_size),
                "font_style": "italic",
                "text_anchor": "middle",
                "fill": style.color("current", "#c43c39"),
            },
            "I_x",
        )
    )
    parts.append(
        tag(
            "text",
            {
                "x": fmt(x + width / 2),
                "y": fmt(center_y + 3),
                "font_family": style.font_family,
                "font_size": fmt(style.small_label_size),
                "font_weight": "600",
                "text_anchor": "middle",
                "dominant_baseline": "middle",
                "fill": "#ffffff",
            },
            text(label),
        )
    )

    if show_voltage:
        vx = x + width * 0.365
        parts.append(
            tag(
                "line",
                {
                    "class": "maglab-sot-voltage-arrow",
                    "x1": fmt(vx),
                    "y1": fmt(channel_y + 4),
                    "x2": fmt(vx),
                    "y2": fmt(y + 12),
                    "stroke": style.color("voltage", "#237a4b"),
                    "stroke_width": fmt(style.axis_width),
                    "marker_end": "url(#sotVoltageArrow)",
                },
            )
        )
        parts.append(
            tag(
                "text",
                {
                    "x": fmt(vx + 9),
                    "y": fmt(y + 13),
                    "font_family": style.font_family,
                    "font_size": fmt(style.small_label_size),
                    "font_style": "italic",
                    "fill": style.color("voltage", "#237a4b"),
                },
                "V_H",
            )
        )

    if show_field:
        fx = x + width * 0.82
        fy = y + height * 0.17
        parts.append(
            tag(
                "circle",
                {
                    "class": "maglab-sot-field-dot",
                    "cx": fmt(fx),
                    "cy": fmt(fy),
                    "r": fmt(10),
                    "fill": "none",
                    "stroke": style.color("field", "#275dad"),
                    "stroke_width": fmt(style.axis_width),
                },
            )
        )
        parts.append(
            tag(
                "circle",
                {
                    "cx": fmt(fx),
                    "cy": fmt(fy),
                    "r": fmt(2.2),
                    "fill": style.color("field", "#275dad"),
                },
            )
        )
        parts.append(
            tag(
                "text",
                {
                    "x": fmt(fx + 14),
                    "y": fmt(fy + 4),
                    "font_family": style.font_family,
                    "font_size": fmt(style.small_label_size),
                    "font_style": "italic",
                    "fill": style.color("field", "#275dad"),
                },
                "H_z",
            )
        )
    return parts


def _draw_axes(*, style: Any, ox: float, oy: float, length: float) -> list[str]:
    """Draw compact coordinate axes."""
    return [
        tag(
            "line",
            {
                "class": "maglab-sot-axis",
                "x1": fmt(ox),
                "y1": fmt(oy),
                "x2": fmt(ox + length),
                "y2": fmt(oy),
                "stroke": "#333333",
                "stroke_width": fmt(style.callout_width),
                "marker_end": "url(#sotArrow)",
            },
        ),
        tag(
            "line",
            {
                "class": "maglab-sot-axis",
                "x1": fmt(ox),
                "y1": fmt(oy),
                "x2": fmt(ox),
                "y2": fmt(oy - length),
                "stroke": "#333333",
                "stroke_width": fmt(style.callout_width),
                "marker_end": "url(#sotArrow)",
            },
        ),
        tag(
            "text",
            {
                "x": fmt(ox + length + 5),
                "y": fmt(oy + 3),
                "font_family": style.font_family,
                "font_size": fmt(style.small_label_size),
                "fill": "#333333",
            },
            "x",
        ),
        tag(
            "text",
            {
                "x": fmt(ox - 3),
                "y": fmt(oy - length - 6),
                "font_family": style.font_family,
                "font_size": fmt(style.small_label_size),
                "text_anchor": "end",
                "fill": "#333333",
            },
            "y",
        ),
    ]


def _coerce_layers(raw_layers: object, *, style: Any) -> list[dict[str, Any]]:
    """Normalize layer dictionaries."""
    if not isinstance(raw_layers, list) or not raw_layers:
        raw_layers = _DEFAULT_LAYERS
    layers: list[dict[str, Any]] = []
    for raw in raw_layers:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "?"))
        role = str(raw.get("role", _infer_role(name))).lower()
        try:
            thickness = float(raw.get("thickness_nm", 1.0))
        except (TypeError, ValueError):
            thickness = 1.0
        fallback = style.color(role, _role_color(role))
        layers.append(
            {
                "name": name,
                "role": role,
                "thickness_nm": max(0.05, thickness),
                "color": color_value(raw.get("color", fallback), fallback),
            }
        )
    return layers or _coerce_layers(_DEFAULT_LAYERS, style=style)


def _bounded_heights(thicknesses: list[float], *, height: float) -> list[float]:
    """Compress large physical thickness contrast into legible layer heights."""
    weights = [math.sqrt(max(t, 0.05)) for t in thicknesses]
    total = sum(weights) or 1.0
    min_height = 6.5
    heights = [max(min_height, height * w / total) for w in weights]
    overflow = sum(heights) - height
    if overflow <= 0:
        return heights
    flexible = [i for i, h in enumerate(heights) if h > min_height]
    if not flexible:
        return heights
    for idx in flexible:
        heights[idx] = max(min_height, heights[idx] - overflow / len(flexible))
    return heights


def _spread(values: list[float], *, min_gap: float, lower: float, upper: float) -> list[float]:
    """Spread labels vertically while keeping their preferred order."""
    order = sorted(range(len(values)), key=values.__getitem__)
    placed = values[:]
    last = lower - min_gap
    for idx in order:
        placed[idx] = max(values[idx], last + min_gap)
        last = placed[idx]
    excess = max(0.0, last - upper)
    if excess:
        for idx in order:
            placed[idx] -= excess
    return placed


def _infer_role(name: str) -> str:
    """Infer common spintronics material roles."""
    lower = name.lower()
    if "substrate" in lower or lower.startswith("si"):
        return "substrate"
    if any(token in lower for token in ("cofe", "co", "fe", "ni", "fm")):
        return "ferromagnet"
    if any(token in lower for token in ("mgo", "oxide", "sio2", "sio₂")):
        return "oxide"
    if "cap" in lower:
        return "cap"
    if any(token in lower for token in ("pt", "ta", " w", "hm", "heavy")):
        return "heavy_metal"
    return "neutral"


def _role_color(role: str) -> str:
    """Fallback palette by layer role."""
    return {
        "heavy_metal": "#8f969e",
        "ferromagnet": "#c43c39",
        "oxide": "#eeeeee",
        "substrate": "#d9e8f6",
        "cap": "#7f858b",
    }.get(role, "#aaaaaa")


def get_primitive() -> SotDeviceScenePrimitive:
    """Registry loader factory function."""
    return SotDeviceScenePrimitive()
