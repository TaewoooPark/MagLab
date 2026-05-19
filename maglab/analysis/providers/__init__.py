"""analysis/providers package — ModelProvider registration and registry.

Import all providers so that @register_provider decorators are executed.
"""

from __future__ import annotations

# Provider import order is alphabetical since there are no dependencies.
from maglab.analysis.providers.base import (  # noqa: F401
    ModelProvider,
    get_all_effects,
    get_effect,
    get_provider,
    list_providers,
    register_provider,
)

# Import each provider module → executes @register_provider
from maglab.analysis.providers.domain_walls_skyrmions import DWSkyrProvider  # noqa: F401
from maglab.analysis.providers.ferromagnetic_resonance import FMRProvider  # noqa: F401
from maglab.analysis.providers.magnetization_dynamics import MagDynProvider  # noqa: F401
from maglab.analysis.providers.magnetometry import MagnetometryProvider  # noqa: F401
from maglab.analysis.providers.magnetotransport import MagnetotransportProvider  # noqa: F401
from maglab.analysis.providers.spin_orbitronics import SpinOrbitronicsProvider  # noqa: F401
