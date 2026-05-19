---
name: physics-oracle
description: Use when validating the dimensional, range, and conservation-law plausibility of magnetic physics quantities, or when performing deterministic physics formula calculations and unit conversions. Gilbert damping 0≤α≤1 check, M≤M_s, exchange length and domain wall width calculations, Oe↔A/m↔T·emu/cm³↔A/m·J_ij meV↔K conversions.
license: MIT
metadata:
  phase: P0
  subfield: magnetism
---

# physics-oracle

Deterministic validation and calculation skill for magnetism & spintronics physics quantities.

## When to use

- When a physical quantity may be invalid — Gilbert damping > 1, negative temperature, M > M_s, etc.
- When a magnetic unit conversion is needed — Oe↔A/m↔T, emu/cm³↔A/m, J_ij meV↔K, DMI mJ/m²↔meV.
- Deterministic formula calculations — exchange length, domain wall width, skyrmion radius, etc.

## Procedure

1. Confirm the type and units of the quantity to validate or calculate — do not guess.
2. Use the `physics_check` tool to verify dimensions, ranges, and conservation laws.
3. Use `physics_compute` for calculations and `convert_units` for unit conversions.
4. **Do not fabricate numbers** — report only the values returned by the tools.

## Integrity

This skill calls only deterministic tools. LLM-estimated values are never used as results — consistent
with MagLab's verifiable orchestrator principle (§3).
