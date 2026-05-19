---
name: multilayer-stack
category: sample/thin film structure
tags: [multilayer, stack, cross-section, thin film, heterostructure, interface, magnetic, Ta, CoFeB, MgO, HM, FM, oxide]
description: Multilayer thin film stack cross-section primitive. Renders heterostructures such as Ta/CoFeB/MgO with parametric layer configuration. Layer thickness, material name, and color are specified as parameters.
journal_styles: [nature, aps, ieee, elsevier]
physics_convention: Layers are specified in growth order from substrate upward. Interfaces are shown as solid lines.
references: [doi:10.1038/nmat3522, doi:10.1126/science.1188919]
---

# Multilayer stack cross-section primitive

Parametric thin film stack cross-section. Specifying Ta(5)/CoFeB(1)/MgO(2) stacks layers from bottom to top.

## Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| layers | list | see default | Layer list: [{name, thickness_nm, color}] |
| width | float | 120.0 | Figure width (SVG units) |
| thickness_scale | float | 20.0 | SVG height scale per nm |
| show_labels | bool | true | Show layer labels |
| show_thickness | bool | true | Show thickness values |
