"""spin_orbitronics ModelProvider.

SOT harmonic Hall·ST-FMR·spin pumping/ISHE·orbital Hall (OHE).

Design basis: plan/04-analysis.md §11.1, impl/03-P2-analysis.md T-P2-18
"""

from __future__ import annotations

from maglab.analysis.effects.base import EffectModel
from maglab.analysis.effects.orbital_hall import OrbitalHallEffect
from maglab.analysis.effects.sot_harmonic_hall import SOTHarmonicHall
from maglab.analysis.effects.spin_pumping_ishe import SpinPumpingISHE
from maglab.analysis.effects.stfmr import STFMREffect
from maglab.analysis.providers.base import ModelProvider, register_provider


@register_provider
class SpinOrbitronicsProvider(ModelProvider):
    """Spintronics/spin-orbit effect ModelProvider.

    Included effects:
    - SOT harmonic Hall (sot_harmonic_hall)
    - ST-FMR (stfmr)
    - Spin pumping/ISHE (spin_pumping_ishe)
    - Orbital Hall OHE (orbital_hall)
    """

    @property
    def name(self) -> str:
        return "spin_orbitronics"

    @property
    def description(self) -> str:
        return (
            "Spin-orbit interaction effect provider: "
            "SOT harmonic Hall, ST-FMR, spin pumping/ISHE, orbital Hall (OHE, rank-3 tensor)."
        )

    @property
    def effects(self) -> list[EffectModel]:
        return [
            SOTHarmonicHall(),
            STFMREffect(),
            SpinPumpingISHE(),
            OrbitalHallEffect(),
        ]
