"""Atomistic-scale simulation — VAMPIRE·Spirit input generation and result parsing.

Target for P3 implementation. Falls back to the mock backend when solver binaries are not installed.
"""

from __future__ import annotations

from maglab.sim.atomistic.input_gen import AtomisticEngine, AtomisticInputGenerator
from maglab.sim.atomistic.parse_atomistic import (
    AtomisticResult,
    parse_spirit_output,
    parse_vampire_output,
)

__all__ = [
    "AtomisticInputGenerator",
    "AtomisticEngine",
    "parse_vampire_output",
    "parse_spirit_output",
    "AtomisticResult",
]
