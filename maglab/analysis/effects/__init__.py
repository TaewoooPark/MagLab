"""analysis/effects package — EffectModel base class and all effect models.

Auxiliary types (ParamSpec, MeasurementConfig, FitResult) are also re-exported from this package.
"""

from __future__ import annotations

from maglab.analysis.effects.amr import AMREffect  # noqa: F401
from maglab.analysis.effects.anomalous_hall import AnomalousHallEffect  # noqa: F401
from maglab.analysis.effects.base import (  # noqa: F401
    EffectModel,
    FitResult,
    MeasurementConfig,
    ParamSpec,
)
from maglab.analysis.effects.dmi import DMIEffect  # noqa: F401
from maglab.analysis.effects.dw_1d import DW1DModel  # noqa: F401
from maglab.analysis.effects.fmr_kittel import FMRKittel  # noqa: F401
from maglab.analysis.effects.gilbert_damping import GilbertDamping  # noqa: F401
from maglab.analysis.effects.gmr_tmr import GMRTMREffect  # noqa: F401
from maglab.analysis.effects.hysteresis import HysteresisLoop  # noqa: F401
from maglab.analysis.effects.llg import LLGModel  # noqa: F401
from maglab.analysis.effects.orbital_hall import OrbitalHallEffect  # noqa: F401
from maglab.analysis.effects.ordinary_hall import OrdinaryHallEffect  # noqa: F401
from maglab.analysis.effects.planar_hall import PlanarHallEffect  # noqa: F401
from maglab.analysis.effects.smr import SMREffect  # noqa: F401
from maglab.analysis.effects.sot_harmonic_hall import SOTHarmonicHall  # noqa: F401
from maglab.analysis.effects.spin_pumping_ishe import SpinPumpingISHE  # noqa: F401
from maglab.analysis.effects.stfmr import STFMREffect  # noqa: F401
from maglab.analysis.effects.thiele import ThieleModel  # noqa: F401
from maglab.analysis.effects.topological_hall import TopologicalHallEffect  # noqa: F401
from maglab.analysis.effects.tyj_scaling import TYJScaling  # noqa: F401
