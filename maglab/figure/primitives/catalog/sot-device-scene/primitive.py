"""Nature-style SOT device schematic scene (§12.4).

This primitive intentionally avoids "presentation graphics" tricks.  Nature's
figure guide asks for editable vector artwork, standard fonts, compact panel
layout, 5-7 pt labels, black annotation text, and no decorative shadows or
patterns.  The scene is therefore generated as clean SVG with an optional HTML
wrapper for browser-first preview/export workflows.
"""

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
    {"name": "Si/SiO₂", "role": "substrate", "thickness_nm": 500.0, "color": "#d7e8f7"},
    {"name": "Pt", "role": "heavy_metal", "thickness_nm": 5.0, "color": "#8a8f95"},
    {"name": "CoFeB", "role": "ferromagnet", "thickness_nm": 1.1, "color": "#d55e00"},
    {"name": "MgO", "role": "oxide", "thickness_nm": 2.0, "color": "#f2f2f2"},
    {"name": "Ta cap", "role": "cap", "thickness_nm": 2.0, "color": "#6f767d"},
]

_INK = "#111111"
_MUTED = "#5c5c5c"
_BLUE = "#4b78b8"
_BLUE_LIGHT = "#d8e6f8"
_CONTACT = "#b7c7db"
_WIRE = "#2f2f2f"


class SotDeviceScenePrimitive:
    """Composite SOT stack-to-Hall-bar schematic.

    The drawing is layout-first: the outer canvas is split into named panel
    regions and all graphical elements are attached to semantic frames/anchors.
    This is closer to browser/SVG figure authoring than to ad-hoc primitive
    placement, while staying fully editable as vector artwork.
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
        "Nature",
        "SVG",
    ]
    description: str = (
        "Nature-style editable SVG schematic connecting a multilayer SOT stack "
        "to a patterned Hall bar transport geometry."
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
            "default": "SOT stack",
            "description": "External label for the Hall bar channel",
        },
        {
            "name": "width_mm",
            "type": "float",
            "default": 183.0,
            "description": "Physical SVG width in millimetres; 183 mm is Nature double-column.",
        },
        {
            "name": "height_mm",
            "type": "float",
            "default": 62.0,
            "description": "Physical SVG height in millimetres.",
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
        {
            "name": "show_readout_inset",
            "type": "bool",
            "default": True,
            "description": "Show a qualitative editable Hall-readout inset panel",
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
        """Generate the composite SOT device scene."""
        if backend == "tikz":
            return self._render_tikz(params)
        if backend == "html":
            return self._render_html(params, style_key=style)
        return self._render_svg(params, style_key=style)

    def _canvas_size(self, params: dict[str, Any]) -> tuple[float, float]:
        """Return physical canvas size in millimetres."""
        canvas_params = {
            "width_mm": params.get("width_mm", params.get("width", 183.0)),
            "height_mm": params.get("height_mm", params.get("height", 62.0)),
        }
        width = positive_float(canvas_params, "width_mm", 183.0, minimum=89.0, maximum=183.0)
        height = positive_float(canvas_params, "height_mm", 62.0, minimum=48.0, maximum=170.0)
        return width, height

    def _render_svg(self, params: dict[str, Any], *, style_key: str = "nature") -> str:
        """SVG renderer."""
        style = schematic_style(style_key)
        width, height = self._canvas_size(params)
        device_label = str(params.get("device_label", "SOT stack"))
        show_process_arrow = bool(params.get("show_process_arrow", True))
        show_axes = bool(params.get("show_axes", True))
        show_voltage = bool(params.get("show_voltage", True))
        show_field = bool(params.get("show_field", True))
        show_readout_inset = bool(params.get("show_readout_inset", True))
        layers = _coerce_layers(params.get("layers", _DEFAULT_LAYERS), style=style)

        margin = 5.0
        gutter = 6.0
        panel_h = height - margin * 2.0
        if show_readout_inset:
            panel_a = SchematicFrame(margin, margin, 59.0, panel_h)
            panel_b = SchematicFrame(panel_a.x + panel_a.width + gutter, margin, 62.0, panel_h)
            panel_c: SchematicFrame | None = SchematicFrame(
                panel_b.x + panel_b.width + gutter,
                margin,
                width - (panel_b.x + panel_b.width + gutter) - margin,
                panel_h,
            )
        else:
            panel_w = (width - margin * 2.0 - gutter) / 2.0
            panel_a = SchematicFrame(margin, margin, panel_w, panel_h)
            panel_b = SchematicFrame(margin + panel_w + gutter, margin, panel_w, panel_h)
            panel_c = None

        stack_frame = panel_a.inset(7.0, 17.0, 17.0, 15.5)
        device_frame = panel_b.inset(9.0, 19.0, 7.0, 14.0)
        axis_origin = panel_b.point(0.80, 0.87)

        parts: list[str] = [
            tag(
                "rect", {"x": 0, "y": 0, "width": fmt(width), "height": fmt(height), "fill": "#fff"}
            ),
            _panel_label(panel_a, "a"),
            _panel_label(panel_b, "b"),
            _panel_label(panel_c, "c") if panel_c is not None else "",
            _panel_title(panel_a, "Layer stack"),
            _panel_title(panel_b, "Patterned device"),
            _panel_title(panel_c, "Readout") if panel_c is not None else "",
        ]
        parts.extend(_draw_stack(layers, style=style, frame=stack_frame, panel=panel_a))
        if show_process_arrow:
            parts.extend(
                _draw_process_arrow(
                    style=style,
                    start=panel_a.point(0.82, 0.55),
                    end=panel_b.point(0.10, 0.55),
                    label="",
                )
            )
        parts.extend(
            _draw_hall_bar(
                style=style,
                frame=device_frame,
                panel=panel_b,
                label=device_label,
                show_voltage=show_voltage,
                show_field=show_field,
            )
        )
        if show_axes:
            parts.extend(_draw_axes(style=style, ox=axis_origin[0], oy=axis_origin[1], length=8.5))
        if panel_c is not None:
            parts.extend(
                _draw_process_arrow(
                    style=style,
                    start=panel_b.point(0.87, 0.55),
                    end=panel_c.point(0.13, 0.55),
                    label="",
                )
            )
            parts.extend(_draw_readout_inset(style=style, panel=panel_c))

        defs = (
            "<defs>"
            "<style><![CDATA["
            ".maglab-nature-figure text{font-family:Arial,Helvetica,sans-serif;fill:#111;}"
            ".maglab-panel-label{font-size:2.85px;font-weight:700;}"
            ".maglab-panel-title{font-size:2.35px;font-weight:700;}"
            ".maglab-label{font-size:2.05px;}"
            ".maglab-small{font-size:1.75px;}"
            ".maglab-keyline{stroke:#111;stroke-width:.28;fill:none;vector-effect:non-scaling-stroke;}"
            ".maglab-thin{stroke:#555;stroke-width:.20;fill:none;vector-effect:non-scaling-stroke;}"
            ".maglab-shape{stroke:#111;stroke-width:.28;vector-effect:non-scaling-stroke;}"
            "]]></style>"
            '<marker id="sotArrow" markerWidth="5" markerHeight="5" refX="4.6" refY="2.5" '
            'orient="auto" markerUnits="strokeWidth">'
            f'<path d="M0,0 L5,2.5 L0,5 Z" fill="{_INK}"/></marker>'
            "</defs>"
        )
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{fmt(width)}mm" height="{fmt(height)}mm" '
            f'viewBox="0 0 {fmt(width)} {fmt(height)}" '
            'class="maglab-nature-figure" role="img" '
            'aria-label="Spin-orbit torque stack and Hall bar readout schematic">\n'
            f"{defs}\n" + "\n".join(parts) + "\n</svg>"
        )

    def _render_html(self, params: dict[str, Any], *, style_key: str = "nature") -> str:
        """Return a browser-previewable HTML document with the editable SVG inline."""
        svg = self._render_svg(params, style_key=style_key)
        width, height = self._canvas_size(params)
        return (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>MagLab SOT device schematic</title>\n"
            "<style>\n"
            "  html,body{margin:0;background:#fff;}\n"
            "  body{display:flex;align-items:flex-start;justify-content:center;padding:8mm;}\n"
            f"  .figure-sheet{{width:{fmt(width)}mm;height:{fmt(height)}mm;}}\n"
            "  svg{display:block;width:100%;height:100%;}\n"
            "</style>\n"
            "</head>\n"
            '<body><main class="figure-sheet">\n'
            f"{svg}\n"
            "</main></body>\n"
            "</html>\n"
        )

    def _render_tikz(self, params: dict[str, Any]) -> str:
        """TikZ fallback placeholder."""
        return (
            r"\begin{tikzpicture}" + "\n"
            r"  \node[draw, rounded corners] {SOT stack $\rightarrow$ Hall bar};" + "\n"
            r"\end{tikzpicture}"
        )


def _panel_label(frame: SchematicFrame, label: str) -> str:
    """Draw a Nature-style lowercase panel label."""
    return tag(
        "text",
        {
            "class": "maglab-panel-label",
            "x": fmt(frame.x),
            "y": fmt(frame.y + 4.2),
        },
        text(label),
    )


def _panel_title(frame: SchematicFrame, title: str) -> str:
    """Draw a compact panel title."""
    return tag(
        "text",
        {
            "class": "maglab-panel-title",
            "x": fmt(frame.x + 7.0),
            "y": fmt(frame.y + 4.2),
        },
        text(title),
    )


def _draw_stack(
    layers: list[dict[str, Any]],
    *,
    style: Any,
    frame: SchematicFrame,
    panel: SchematicFrame,
) -> list[str]:
    """Draw a bounded multilayer stack with external labels and growth axis."""
    heights = _bounded_heights(
        [float(layer["thickness_nm"]) for layer in layers], height=frame.height
    )
    parts: list[str] = []
    current_y = frame.y + frame.height
    label_x = frame.x + frame.width + 8.0
    label_targets: list[float] = []
    boxes: list[tuple[dict[str, Any], float, float]] = []

    for layer, h in zip(layers, heights, strict=True):
        current_y -= h
        boxes.append((layer, current_y, h))
        parts.append(
            tag(
                "rect",
                {
                    "class": "maglab-sot-stack-layer maglab-shape",
                    "x": fmt(frame.x),
                    "y": fmt(current_y),
                    "width": fmt(frame.width),
                    "height": fmt(h),
                    "fill": layer["color"],
                },
            )
        )
        label_targets.append(current_y + h / 2.0)

    label_positions = _spread(
        label_targets,
        min_gap=3.8,
        lower=frame.y + 2.0,
        upper=frame.y + frame.height - 2.0,
    )
    for (layer, layer_y, h), label_y in zip(boxes, label_positions, strict=True):
        mid_y = layer_y + h / 2.0
        parts.append(
            tag(
                "path",
                {
                    "class": "maglab-sot-stack-callout maglab-thin",
                    "d": (
                        f"M {fmt(frame.x + frame.width)} {fmt(mid_y)} "
                        f"L {fmt(label_x - 2.2)} {fmt(label_y)}"
                    ),
                },
            )
        )
        parts.append(
            tag(
                "text",
                {
                    "class": "maglab-sot-stack-label maglab-label",
                    "x": fmt(label_x),
                    "y": fmt(label_y + 0.8),
                },
                text(f"{layer['name']} ({layer['thickness_nm']:.3g} nm)"),
            )
        )

    axis_x = panel.x + 3.2
    axis_y1 = frame.y + frame.height
    axis_y2 = frame.y + 2.0
    parts.append(
        tag(
            "line",
            {
                "class": "maglab-keyline",
                "x1": fmt(axis_x),
                "y1": fmt(axis_y1),
                "x2": fmt(axis_x),
                "y2": fmt(axis_y2),
                "marker_end": "url(#sotArrow)",
            },
        )
    )
    parts.append(
        tag(
            "text",
            {
                "class": "maglab-small",
                "x": fmt(axis_x - 1.5),
                "y": fmt(axis_y2 - 1.4),
                "text_anchor": "end",
            },
            "z",
        )
    )
    parts.append(
        tag(
            "text",
            {"class": "maglab-small", "x": fmt(frame.x), "y": fmt(frame.y + frame.height + 5.5)},
            "heights compressed",
        )
    )
    return parts


def _draw_process_arrow(
    *,
    style: Any,
    start: tuple[float, float],
    end: tuple[float, float],
    label: str,
) -> list[str]:
    """Draw a restrained process arrow between the two panels."""
    x1, y1 = start
    x2, y2 = end
    cx1 = x1 + (x2 - x1) * 0.42
    cx2 = x1 + (x2 - x1) * 0.58
    parts = [
        tag(
            "path",
            {
                "class": "maglab-sot-process-arrow maglab-keyline",
                "d": f"M {fmt(x1)} {fmt(y1)} C {fmt(cx1)} {fmt(y1 - 4)} "
                f"{fmt(cx2)} {fmt(y2 - 4)} {fmt(x2)} {fmt(y2)}",
                "marker_end": "url(#sotArrow)",
            },
        ),
    ]
    if label:
        parts.append(
            tag(
                "text",
                {
                    "class": "maglab-small",
                    "x": fmt((x1 + x2) / 2.0),
                    "y": fmt(y1 - 7.0),
                    "text_anchor": "middle",
                },
                text(label),
            )
        )
    return parts


def _draw_hall_bar(
    *,
    style: Any,
    frame: SchematicFrame,
    panel: SchematicFrame,
    label: str,
    show_voltage: bool,
    show_field: bool,
) -> list[str]:
    """Draw a Nature-style Hall bar with black annotation text and keylines."""
    channel = frame.inset(7.0, frame.height * 0.39, 7.0, frame.height * 0.39)
    channel_h = channel.height
    contact_w = 5.4
    voltage_w = 6.1
    voltage_h = 13.8
    parts: list[str] = []

    # Device body and contacts.
    device_rects = [
        (channel.x, channel.y, channel.width, channel.height, _BLUE, "maglab-sot-hall-channel"),
        (
            channel.x - contact_w,
            channel.y,
            contact_w,
            channel_h,
            _BLUE_LIGHT,
            "maglab-sot-current-contact",
        ),
        (
            channel.x + channel.width,
            channel.y,
            contact_w,
            channel_h,
            _BLUE_LIGHT,
            "maglab-sot-current-contact",
        ),
        (
            channel.x + channel.width * 0.20,
            channel.y - voltage_h,
            voltage_w,
            voltage_h,
            _CONTACT,
            "maglab-sot-voltage-contact",
        ),
        (
            channel.x + channel.width * 0.62,
            channel.y - voltage_h,
            voltage_w,
            voltage_h,
            _CONTACT,
            "maglab-sot-voltage-contact",
        ),
        (
            channel.x + channel.width * 0.19,
            channel.y + channel_h,
            voltage_w,
            voltage_h,
            _CONTACT,
            "maglab-sot-voltage-contact",
        ),
        (
            channel.x + channel.width * 0.62,
            channel.y + channel_h,
            voltage_w,
            voltage_h,
            _CONTACT,
            "maglab-sot-voltage-contact",
        ),
    ]
    for rect_x, rect_y, rect_w, rect_h, fill, klass in device_rects:
        parts.append(
            tag(
                "rect",
                {
                    "class": f"{klass} maglab-shape",
                    "x": fmt(rect_x),
                    "y": fmt(rect_y),
                    "width": fmt(rect_w),
                    "height": fmt(rect_h),
                    "fill": fill,
                },
            )
        )

    center_y = channel.y + channel_h / 2.0
    parts.append(
        tag(
            "line",
            {
                "class": "maglab-sot-current-arrow maglab-keyline",
                "x1": fmt(channel.x - contact_w * 0.65),
                "y1": fmt(center_y),
                "x2": fmt(channel.x + channel.width * 0.34),
                "y2": fmt(center_y),
                "marker_end": "url(#sotArrow)",
            },
        )
    )
    parts.append(
        tag(
            "text",
            {
                "class": "maglab-label",
                "x": fmt(channel.x + channel.width * 0.19),
                "y": fmt(center_y - 2.2),
                "text_anchor": "middle",
            },
            _subscript("I", "x"),
        )
    )

    # External channel label with keyline instead of text on a coloured object.
    label_x = channel.x + channel.width * 0.52
    label_y = channel.y + channel_h + 19.5
    parts.append(
        tag(
            "path",
            {
                "class": "maglab-thin",
                "d": f"M {fmt(channel.x + channel.width * 0.52)} {fmt(channel.y + channel_h)} "
                f"L {fmt(label_x)} {fmt(label_y - 4.0)}",
            },
        )
    )
    parts.append(
        tag(
            "text",
            {
                "class": "maglab-label",
                "x": fmt(label_x),
                "y": fmt(label_y),
                "text_anchor": "middle",
            },
            text(label),
        )
    )

    if show_voltage:
        vx = channel.x + channel.width * 0.255
        parts.append(
            tag(
                "line",
                {
                    "class": "maglab-sot-voltage-arrow maglab-keyline",
                    "x1": fmt(vx),
                    "y1": fmt(channel.y - 1.0),
                    "x2": fmt(vx),
                    "y2": fmt(channel.y - voltage_h + 3.0),
                    "marker_end": "url(#sotArrow)",
                },
            )
        )
        parts.append(
            tag(
                "text",
                {
                    "class": "maglab-label",
                    "x": fmt(vx + 3.6),
                    "y": fmt(channel.y - voltage_h + 3.8),
                },
                _subscript("V", "H"),
            )
        )

    if show_field:
        fx = min(channel.x + channel.width + 10.0, panel.x + panel.width - 12.0)
        fy = channel.y - 7.5
        parts.append(
            tag(
                "circle",
                {
                    "class": "maglab-sot-field-dot maglab-keyline",
                    "cx": fmt(fx),
                    "cy": fmt(fy),
                    "r": fmt(4.6),
                },
            )
        )
        parts.append(tag("circle", {"cx": fmt(fx), "cy": fmt(fy), "r": fmt(0.9), "fill": _INK}))
        parts.append(
            tag(
                "text",
                {
                    "class": "maglab-label",
                    "x": fmt(panel.x + panel.width - 1.5),
                    "y": fmt(fy + 1.4),
                    "text_anchor": "end",
                },
                _subscript("H", "z"),
            )
        )

    # Scale bar: editable line + text, not flattened into the device.
    scale_x = panel.x + panel.width - 27.0
    scale_y = panel.y + panel.height - 7.0
    parts.append(
        tag(
            "line",
            {
                "class": "maglab-keyline",
                "x1": fmt(scale_x),
                "y1": fmt(scale_y),
                "x2": fmt(scale_x + 15.0),
                "y2": fmt(scale_y),
            },
        )
    )
    parts.append(
        tag(
            "text",
            {
                "class": "maglab-small",
                "x": fmt(scale_x + 7.5),
                "y": fmt(scale_y - 2.0),
                "text_anchor": "middle",
            },
            "10 μm",
        )
    )
    return parts


def _draw_readout_inset(*, style: Any, panel: SchematicFrame) -> list[str]:
    """Draw a qualitative, editable Hall readout inset panel."""
    plot = panel.inset(7.0, 18.0, 3.5, 9.5)
    x0 = plot.x
    y0 = plot.y + plot.height
    x1 = plot.x + plot.width
    y1 = plot.y
    curve_d = (
        f"M {fmt(x0 + 2.0)} {fmt(y0 - plot.height * 0.28)} "
        f"C {fmt(x0 + plot.width * 0.28)} {fmt(y1 + plot.height * 0.10)} "
        f"{fmt(x0 + plot.width * 0.52)} {fmt(y0 - plot.height * 0.12)} "
        f"{fmt(x0 + plot.width * 0.73)} {fmt(y0 - plot.height * 0.52)} "
        f"S {fmt(x1 - 3.0)} {fmt(y1 + plot.height * 0.35)} "
        f"{fmt(x1 - 1.5)} {fmt(y1 + plot.height * 0.18)}"
    )
    return [
        tag(
            "line",
            {
                "class": "maglab-keyline",
                "x1": fmt(x0),
                "y1": fmt(y0),
                "x2": fmt(x1),
                "y2": fmt(y0),
                "marker_end": "url(#sotArrow)",
            },
        ),
        tag(
            "line",
            {
                "class": "maglab-keyline",
                "x1": fmt(x0),
                "y1": fmt(y0),
                "x2": fmt(x0),
                "y2": fmt(y1),
                "marker_end": "url(#sotArrow)",
            },
        ),
        tag(
            "path",
            {
                "class": "maglab-sot-readout-curve",
                "d": curve_d,
                "fill": "none",
                "stroke": _BLUE,
                "stroke_width": ".42",
                "vector_effect": "non-scaling-stroke",
            },
        ),
        tag(
            "text",
            {
                "class": "maglab-small",
                "x": fmt(x0 - 1.8),
                "y": fmt(y1 + 2.0),
                "text_anchor": "end",
            },
            _subscript("V", "H"),
        ),
        tag(
            "text",
            {
                "class": "maglab-small",
                "x": fmt(x1 - 0.5),
                "y": fmt(y0 + 4.0),
                "text_anchor": "end",
            },
            _subscript("H", "z"),
        ),
        tag(
            "text",
            {
                "class": "maglab-label",
                "x": fmt(panel.x + 7.0),
                "y": fmt(panel.y + panel.height - 2.5),
            },
            "qualitative response",
        ),
    ]


def _draw_axes(*, style: Any, ox: float, oy: float, length: float) -> list[str]:
    """Draw compact coordinate axes."""
    return [
        tag(
            "line",
            {
                "class": "maglab-sot-axis maglab-keyline",
                "x1": fmt(ox),
                "y1": fmt(oy),
                "x2": fmt(ox + length),
                "y2": fmt(oy),
                "marker_end": "url(#sotArrow)",
            },
        ),
        tag(
            "line",
            {
                "class": "maglab-sot-axis maglab-keyline",
                "x1": fmt(ox),
                "y1": fmt(oy),
                "x2": fmt(ox),
                "y2": fmt(oy - length),
                "marker_end": "url(#sotArrow)",
            },
        ),
        tag(
            "text",
            {
                "class": "maglab-small",
                "x": fmt(ox + length + 2.2),
                "y": fmt(oy + 1.2),
            },
            "x",
        ),
        tag(
            "text",
            {
                "class": "maglab-small",
                "x": fmt(ox - 1.2),
                "y": fmt(oy - length - 1.4),
                "text_anchor": "end",
            },
            "y",
        ),
    ]


def _subscript(symbol: str, sub: str) -> str:
    """Return editable SVG text with a subscript tspan."""
    return f'{text(symbol)}<tspan baseline-shift="sub" font-size="1.45px">{text(sub)}</tspan>'


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
    min_height = 2.5
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
        "heavy_metal": "#8a8f95",
        "ferromagnet": "#d55e00",
        "oxide": "#f2f2f2",
        "substrate": "#d7e8f7",
        "cap": "#6f767d",
    }.get(role, "#b6b6b6")


def get_primitive() -> SotDeviceScenePrimitive:
    """Registry loader factory function."""
    return SotDeviceScenePrimitive()
