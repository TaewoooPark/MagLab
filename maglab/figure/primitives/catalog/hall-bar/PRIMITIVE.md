---
name: hall-bar
category: device geometry
tags: [Hall, bar, measurement, geometry, current, voltage, transport]
description: Hall bar device geometry primitive. Standard Hall bar shape including current injection and Hall/longitudinal voltage measurement contacts. Convention: current along x, Hall voltage along y, magnetic field along z.
journal_styles: [nature, aps, ieee, elsevier]
physics_convention: Current along x, Hall voltage along y, magnetic field along z (right-hand coordinate system). Follows Néel convention.
references: [doi:10.1103/PhysRevLett.88.117601]
---

# Hall bar primitive

Parametric Hall bar device geometry. Includes current contacts (source/drain) and voltage contacts (Hall/longitudinal).

## Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| width_um | float | 20.0 | Hall bar width (μm) |
| length_um | float | 100.0 | Hall bar length (μm) |
| contact_width_um | float | 10.0 | Voltage contact width (μm) |
| contact_length_um | float | 8.0 | Voltage contact length (μm) |
| color | str | "#4472C4" | Fill color (default: blue) |
| show_arrows | bool | true | Show current/voltage arrows |
| label | str | "" | Material label |
