---
name: sot-device-scene
category: concept/process
tags: [SOT, spin-orbit torque, Hall bar, multilayer, stack, measurement, device, schematic, spintronics]
description: Publication-style SOT device scene connecting a multilayer cross-section to a patterned Hall bar transport geometry with measurement annotations.
journal_styles: [nature, aps, ieee, elsevier]
physics_convention: Layers are shown in growth order from substrate upward. The Hall bar uses current along x, Hall voltage along y, and out-of-plane field along z.
references: [doi:10.1038/nmat3522, doi:10.1126/science.1188919, doi:10.1103/PhysRevLett.88.117601]
---

# SOT device scene primitive

Composite publication-style schematic for a spin-orbit-torque heterostructure:
multilayer stack cross-section, process arrow, patterned Hall bar, current /
Hall-voltage annotations, and out-of-plane field marker.

## Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| layers | list | see default | Layer list: [{name, role, thickness_nm, color}] |
| device_label | str | "HM/FM/Oxide" | Label shown on the Hall bar channel |
| show_process_arrow | bool | true | Show stack-to-device process arrow |
| show_axes | bool | true | Show compact coordinate axes |
| show_voltage | bool | true | Show Hall-voltage annotation |
| show_field | bool | true | Show out-of-plane field marker |
