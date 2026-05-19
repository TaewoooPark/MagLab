"""analysis package — modeling and fitting engine providers.

Main entry points:
    from maglab.analysis import providers, effects
    from maglab.analysis.providers import get_effect, list_providers
    from maglab.analysis.fit import run_fit, FitConvergenceError
"""

from __future__ import annotations

from maglab.analysis import effects, providers  # noqa: F401
from maglab.analysis.fit import FitConvergenceError, run_fit, run_fit_multi  # noqa: F401
