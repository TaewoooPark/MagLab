"""DFT-scale simulation — VASP·QE·FLEUR input generation and result parsing.

Target for P3 implementation. Falls back to the mock backend when solver binaries are not installed.
"""

from __future__ import annotations

from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator
from maglab.sim.dft.parse_dft import DFTResult, parse_dft_output
from maglab.sim.dft.tb2j import TB2JResult, parse_tb2j_output

__all__ = [
    "DFTInputGenerator",
    "DFTEngine",
    "DFTCalcType",
    "parse_dft_output",
    "DFTResult",
    "parse_tb2j_output",
    "TB2JResult",
]
