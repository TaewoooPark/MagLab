"""MagLab — magnetism & spintronics research lifecycle copilot.

Verifiable orchestrator: the LLM handles reasoning, planning, and tool calls only;
numbers, citations, and figure data come from deterministic tools, and every output
carries a provenance record.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    # Single source of truth: the installed package metadata (pyproject.toml).
    __version__ = _pkg_version("maglab")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.3"
