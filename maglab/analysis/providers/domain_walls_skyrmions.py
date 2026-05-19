"""domain_walls_skyrmions ModelProvider.

Thiele·DMI(BLS).

Design basis: plan/04-analysis.md §11.1, impl/03-P2-analysis.md T-P2-31
"""

from __future__ import annotations

from maglab.analysis.effects.base import EffectModel
from maglab.analysis.effects.dmi import DMIEffect
from maglab.analysis.effects.thiele import ThieleModel
from maglab.analysis.providers.base import ModelProvider, register_provider


@register_provider
class DWSkyrProvider(ModelProvider):
    """Domain wall and skyrmion ModelProvider.

    Included effects:
    - Thiele skyrmion Hall angle (thiele)
    - DMI BLS (dmi)
    """

    @property
    def name(self) -> str:
        return "domain_walls_skyrmions"

    @property
    def description(self) -> str:
        return "Domain wall and skyrmion provider: Thiele equation (skyrmion Hall angle) and BLS DMI extraction."

    @property
    def effects(self) -> list[EffectModel]:
        return [
            ThieleModel(),
            DMIEffect(),
        ]
