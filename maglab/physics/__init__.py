"""MagLab physics core package.

Deterministic magnetism and spintronics physics computation modules.
No LLM calls or network access — purely deterministic.

Submodules:
    constants : CODATA 2022 physical constants
    units     : magnetic unit conversions (CGS <-> SI)
    quantity  : lightweight Quantity type
    oracle    : sanity oracle (range, dimensional, and conservation-law checks)
    formulas  : deterministic multiscale formula library
    materials : curated material database
"""

from __future__ import annotations
