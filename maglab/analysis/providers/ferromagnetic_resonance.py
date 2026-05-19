"""ferromagnetic_resonance ModelProvider.

FMR Kittel·Gilbert damping.

Design basis: plan/04-analysis.md §11.1, impl/03-P2-analysis.md T-P2-23
"""

from __future__ import annotations

from maglab.analysis.effects.base import EffectModel
from maglab.analysis.effects.fmr_kittel import FMRKittel
from maglab.analysis.effects.gilbert_damping import GilbertDamping
from maglab.analysis.providers.base import ModelProvider, register_provider


@register_provider
class FMRProvider(ModelProvider):
    """Ferromagnetic resonance ModelProvider.

    Included effects:
    - FMR Kittel dispersion relation (fmr_kittel)
    - Gilbert damping (gilbert_damping)
    """

    @property
    def name(self) -> str:
        return "ferromagnetic_resonance"

    @property
    def description(self) -> str:
        return "Ferromagnetic resonance effect provider: Kittel dispersion relation and Gilbert damping linewidth fitting."

    @property
    def effects(self) -> list[EffectModel]:
        return [
            FMRKittel(mode="in_plane"),
            GilbertDamping(),
        ]
