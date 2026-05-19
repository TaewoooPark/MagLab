"""CPU-only fallback backend router.

Design rationale: impl/02-P1-figure-sim.md T-P1-02.

CPU-only fallback router. Auto-detects available solvers and routes by priority:
  1. magnum.np (Python-native, always available)
  2. OOMMF (CPU-only, if found on PATH)
  3. MuMax3 CPU mode (if found on PATH)

Operates without a GPU in the Mac development environment (§10.2).
"""

from __future__ import annotations

from maglab.sim.backends.local import check_binary


class CPUBackendRouter:
    """Auto-detects and routes to available CPU backends.

    Priority: magnumnp > oommf > mumax3 (CPU mode).
    """

    @staticmethod
    def available_engines() -> list[str]:
        """Return a list of CPU engines available in the current environment.

        Returns:
            List of available engine names in priority order.
        """
        engines: list[str] = []

        # magnum.np: verify by attempting a Python package import
        try:
            import magnumnp  # noqa: F401

            engines.append("magnumnp")
        except ImportError:
            pass

        # OOMMF: detect tclsh + oommf
        if check_binary("oommf") or (check_binary("tclsh") and check_binary("oommf.tcl")):
            engines.append("oommf")

        # MuMax3: detect binary
        if check_binary("mumax3"):
            engines.append("mumax3")

        return engines

    @staticmethod
    def best_engine(preferred: str = "auto") -> str:
        """Select and return the best available CPU engine.

        Parameters:
            preferred: Preferred engine ("auto"|"magnumnp"|"oommf"|"mumax3").
                       When "auto", the highest-priority available engine is chosen.

        Returns:
            Name of the selected engine. Returns "none" if no engine is available.
        """
        available = CPUBackendRouter.available_engines()

        if not available:
            return "none"

        if preferred == "auto":
            return available[0]

        if preferred in available:
            return preferred

        # preferred engine not installed — fall back to the highest-priority available engine
        return available[0]

    @staticmethod
    def is_available() -> bool:
        """Return True if at least one CPU engine is available."""
        return len(CPUBackendRouter.available_engines()) > 0
