"""magnetometry ModelProvider.

Hysteresis loop analysis and Curie/compensation temperature fitting.

Design basis: plan/04-analysis.md §11.1, impl/03-P2-analysis.md T-P2-30
"""

from __future__ import annotations

from maglab.analysis.effects.base import EffectModel
from maglab.analysis.effects.curie_temperature import CurieTemperatureModel
from maglab.analysis.effects.hysteresis import HysteresisLoop
from maglab.analysis.providers.base import ModelProvider, register_provider


@register_provider
class MagnetometryProvider(ModelProvider):
    """Magnetometry measurement ModelProvider.

    Included effects:
    - Hysteresis loop (hysteresis)
    - Curie/compensation temperature fitting from M(T) data (curie_temperature)
    """

    @property
    def name(self) -> str:
        return "magnetometry"

    @property
    def description(self) -> str:
        return (
            "Magnetometry (VSM·SQUID) measurement provider: "
            "hysteresis loop analysis (M_s·M_r·H_c extraction), "
            "Curie/compensation temperature from M(T) critical-exponent fit."
        )

    @property
    def effects(self) -> list[EffectModel]:
        return [
            HysteresisLoop(),
            CurieTemperatureModel(),
        ]
