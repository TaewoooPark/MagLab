"""magnetization_dynamics ModelProvider.

LLG (+STT/SOT)·Macrospin·1D DW (q-Φ)·Thiele·2-sublattice LLG.

Design basis: plan/04-analysis.md §11.1, impl/03-P2-analysis.md T-P2-26
"""

from __future__ import annotations

from maglab.analysis.effects.base import EffectModel
from maglab.analysis.effects.dw_1d import DW1DModel
from maglab.analysis.effects.llg import LLGModel
from maglab.analysis.effects.llg_2sublattice import LLG2SublatticeModel
from maglab.analysis.effects.macrospin import MacrospinModel
from maglab.analysis.effects.thiele import ThieleModel
from maglab.analysis.providers.base import ModelProvider, register_provider


@register_provider
class MagDynProvider(ModelProvider):
    """Magnetization dynamics ModelProvider.

    Included effects:
    - LLG +STT/SOT (llg)
    - Macrospin Stoner-Wohlfarth + STT/SOT (macrospin)
    - 1D DW q-Φ model (dw_1d)
    - Thiele skyrmion dynamics (thiele)
    - Two-sublattice LLG for AFM/FiM (llg_2sublattice)
    """

    @property
    def name(self) -> str:
        return "magnetization_dynamics"

    @property
    def description(self) -> str:
        return (
            "Magnetization dynamics provider: LLG (+STT·SOT), macrospin (Stoner-Wohlfarth), "
            "1D DW (q-Φ), Thiele skyrmion equation, two-sublattice LLG (AFM/FiM)."
        )

    @property
    def effects(self) -> list[EffectModel]:
        return [
            LLGModel(),
            MacrospinModel(),
            DW1DModel(),
            ThieleModel(),
            LLG2SublatticeModel(),
        ]
