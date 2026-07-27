"""MagLab — magnetism & spintronics research lifecycle copilot.

Verifiable orchestrator: the LLM handles reasoning, planning, and tool calls only;
numbers, citations, and figure data come from deterministic tools, and every output
carries a provenance record.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version


def _version_from_source_tree() -> str:
    """Read the version straight from pyproject.toml when nothing is installed.

    A hard-coded fallback is the drift this indirection exists to prevent: it sat
    at "0.0.3" through two releases, so an uninstalled source tree reported a
    version that had not been current for a long time.
    """
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with pyproject.open("rb") as fh:
            version = tomllib.load(fh)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0+unknown"
    return str(version)


try:
    # Single source of truth: the installed package metadata (pyproject.toml).
    __version__ = _pkg_version("maglab")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = _version_from_source_tree()
