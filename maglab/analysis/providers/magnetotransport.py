"""magnetotransport ModelProvider.

Ordinary Hall·AHE·TYJ scaling·PHE·THE·AMR·SMR·GMR/TMR.

Design basis: plan/04-analysis.md §11.1, impl/03-P2-analysis.md T-P2-09
"""

from __future__ import annotations

from maglab.analysis.effects.amr import AMREffect
from maglab.analysis.effects.anomalous_hall import AnomalousHallEffect
from maglab.analysis.effects.base import EffectModel
from maglab.analysis.effects.gmr_tmr import GMRTMREffect
from maglab.analysis.effects.ordinary_hall import OrdinaryHallEffect
from maglab.analysis.effects.planar_hall import PlanarHallEffect
from maglab.analysis.effects.smr import SMREffect
from maglab.analysis.effects.topological_hall import TopologicalHallEffect
from maglab.analysis.effects.tyj_scaling import TYJScaling
from maglab.analysis.effects.usmr import USMREffect
from maglab.analysis.providers.base import ModelProvider, register_provider


@register_provider
class MagnetotransportProvider(ModelProvider):
    """Magnetotransport effect ModelProvider.

    Included effects:
    - Ordinary Hall (ordinary_hall)
    - Anomalous Hall AHE (anomalous_hall)
    - TYJ scaling (tyj_scaling)
    - Planar Hall PHE (planar_hall)
    - Topological Hall THE (topological_hall)
    - AMR (amr)
    - SMR (smr)
    - GMR/TMR (gmr_tmr)
    - USMR (usmr)
    """

    @property
    def name(self) -> str:
        return "magnetotransport"

    @property
    def description(self) -> str:
        return (
            "Magnetotransport effect provider: ordinary Hall, AHE, TYJ scaling, "
            "PHE, THE, AMR, SMR, GMR/TMR, USMR."
        )

    @property
    def effects(self) -> list[EffectModel]:
        return [
            OrdinaryHallEffect(),
            AnomalousHallEffect(),
            TYJScaling(),
            PlanarHallEffect(),
            TopologicalHallEffect(),
            AMREffect(),
            SMREffect(),
            GMRTMREffect(),
            USMREffect(),
        ]
