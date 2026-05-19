"""Measurement planning and DOE — physics-aware measurement campaign planner (§13.6).

Uses the effect registry's measurement_config in *reverse*:
  "I want physical quantity X" → required measurement·geometry mapping

DOE: proposes full/partial factorial and Latin hypercube designs.
Entry point: `maglab lab plan "<goal>"`.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Measurement step data structures
# ---------------------------------------------------------------------------


@dataclass
class SweepSpec:
    """Parameter sweep specification.

    Attributes
    ----------
    parameter:
        Sweep parameter name (e.g. "B_applied", "temperature").
    unit:
        Unit string.
    start:
        Start value.
    stop:
        Stop value.
    steps:
        Number of steps.
    """

    parameter: str
    unit: str
    start: float
    stop: float
    steps: int = 10

    @property
    def step_size(self) -> float:
        """Step size."""
        return (self.stop - self.start) / max(self.steps - 1, 1)


@dataclass
class MeasurementStep:
    """Single measurement step.

    Attributes
    ----------
    step_id:
        Step identifier.
    target_quantity:
        Physical quantity to measure (e.g. "spin Hall angle", "damping constant α").
    effect_model:
        Effect model name to use (e.g. "sot_harmonic_hall").
    geometry:
        Measurement geometry description (from MeasurementConfig.geometry).
    instrument_hint:
        Recommended instrument hint.
    sweeps:
        List of sweep parameter specifications.
    expected_signal:
        Description of expected signal.
    prerequisites:
        List of prerequisite conditions.
    estimated_hours:
        Estimated time required (hours).
    required_columns:
        List of required data columns.
    notes:
        Additional notes.
    """

    step_id: str
    target_quantity: str
    effect_model: str
    geometry: str
    instrument_hint: str = ""
    sweeps: list[SweepSpec] = field(default_factory=list)
    expected_signal: str = ""
    prerequisites: list[str] = field(default_factory=list)
    estimated_hours: float = 2.0
    required_columns: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "step_id": self.step_id,
            "target_quantity": self.target_quantity,
            "effect_model": self.effect_model,
            "geometry": self.geometry,
            "instrument_hint": self.instrument_hint,
            "sweeps": [
                {
                    "parameter": s.parameter,
                    "unit": s.unit,
                    "start": s.start,
                    "stop": s.stop,
                    "steps": s.steps,
                }
                for s in self.sweeps
            ],
            "expected_signal": self.expected_signal,
            "prerequisites": self.prerequisites,
            "estimated_hours": self.estimated_hours,
            "required_columns": self.required_columns,
            "notes": self.notes,
        }


@dataclass
class MeasurementPlan:
    """Measurement campaign plan.

    Attributes
    ----------
    goal:
        Research goal.
    steps:
        List of measurement steps.
    doe_design:
        DOE design metadata.
    total_estimated_hours:
        Total estimated time.
    checklist_yaml:
        Living checklist YAML string.
    """

    goal: str
    steps: list[MeasurementStep] = field(default_factory=list)
    doe_design: dict[str, Any] = field(default_factory=dict)
    total_estimated_hours: float = 0.0
    checklist_yaml: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "goal": self.goal,
            "total_estimated_hours": self.total_estimated_hours,
            "steps": [s.to_dict() for s in self.steps],
            "doe_design": self.doe_design,
        }

    def to_checklist_yaml(self) -> str:
        """Generate an editable living checklist YAML."""
        lines = [
            f"# Measurement plan — {self.goal}",
            f"# Total estimated time: {self.total_estimated_hours:.1f} hours",
            "",
            "steps:",
        ]
        for step in self.steps:
            lines.append(f"  - id: {step.step_id}")
            lines.append(f"    target: {step.target_quantity}")
            lines.append(f"    effect: {step.effect_model}")
            lines.append(f'    geometry: "{step.geometry}"')
            lines.append(f'    instrument: "{step.instrument_hint}"')
            lines.append(f"    estimated_hours: {step.estimated_hours}")
            lines.append("    done: false")
            lines.append('    notes: ""')
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Physical quantity → effect model mapping (measurement_config reverse lookup)
# ---------------------------------------------------------------------------

# Physical quantity keywords → (effect model name, priority)
_QUANTITY_TO_EFFECT: dict[str, list[tuple[str, int]]] = {
    "spin hall angle": [("sot_harmonic_hall", 1), ("stfmr", 2)],
    "sha": [("sot_harmonic_hall", 1), ("stfmr", 2)],
    "sot efficiency": [("sot_harmonic_hall", 1), ("stfmr", 2)],
    "damping": [("fmr_kittel", 1), ("stfmr", 2)],
    "gilbert damping": [("fmr_kittel", 1), ("stfmr", 2)],
    "alpha": [("fmr_kittel", 1), ("gilbert_damping", 2)],
    "magnetization": [("hysteresis", 1), ("vsm", 1)],
    "saturation magnetization": [("hysteresis", 1)],
    "ms": [("hysteresis", 1)],
    "anomalous hall": [("anomalous_hall", 1)],
    "ahe": [("anomalous_hall", 1)],
    "hall": [("anomalous_hall", 1), ("ordinary_hall", 2)],
    "smr": [("smr", 1)],
    "spin mixing conductance": [("smr", 1), ("spin_pumping_ishe", 2)],
    "dmi": [("dmi", 1)],
    "domain wall": [("dw_1d", 1)],
    "fmr": [("fmr_kittel", 1)],
    "resonance frequency": [("fmr_kittel", 1)],
    "anisotropy": [("fmr_kittel", 1), ("hysteresis", 2)],
}

# Effect name → default instrument hint
_EFFECT_INSTRUMENT: dict[str, str] = {
    "sot_harmonic_hall": "Lock-in amplifier (2ω, Hall bar)",
    "stfmr": "RF generator + Lock-in amplifier (ST-FMR)",
    "fmr_kittel": "VNA or Cavity FMR",
    "gilbert_damping": "VNA FMR (broadband)",
    "anomalous_hall": "Hall bar, 4-terminal measurement",
    "ordinary_hall": "Hall bar, high magnetic field",
    "hysteresis": "VSM or MOKE",
    "smr": "Hall bar (SMR geometry)",
    "dmi": "BLS or Domain wall chirality",
    "dw_1d": "MOKE microscope or Hall bar",
    "spin_pumping_ishe": "FMR + ISHE measurement",
}


def _find_effects_for_goal(goal: str) -> list[tuple[str, int]]:
    """Find relevant effect models from the goal string (measurement_config reverse lookup)."""
    goal_lower = goal.lower()
    matches: dict[str, int] = {}

    for keyword, effects in _QUANTITY_TO_EFFECT.items():
        if keyword in goal_lower:
            for effect_name, priority in effects:
                if effect_name not in matches or matches[effect_name] > priority:
                    matches[effect_name] = priority

    # Sort by priority
    return sorted(matches.items(), key=lambda x: x[1])


def _get_measurement_config_from_effect(effect_name: str) -> dict[str, Any]:
    """Retrieve MeasurementConfig information from an effect model.

    Attempts to load from the actual analysis registry, falls back to defaults
    on failure.
    """
    try:
        # EFFECT_REGISTRY will be added during P2/P3 integration (using fallback for now)
        import maglab.analysis.effects as _effects_mod  # noqa: PLC0415

        registry = getattr(_effects_mod, "EFFECT_REGISTRY", None)
        if registry is not None:
            model = registry.get(effect_name)
            if model:
                mc = model.measurement_config
                return {
                    "geometry": mc.geometry,
                    "required_columns": list(mc.required_columns),
                    "notes": mc.notes,
                }
    except Exception:  # noqa: BLE001
        pass

    # Default fallback
    return {
        "geometry": f"{effect_name} default geometry",
        "required_columns": ["B_applied", "signal"],
        "notes": "",
    }


# ---------------------------------------------------------------------------
# Measurement campaign planner
# ---------------------------------------------------------------------------


class MeasurementPlanner:
    """Physics-aware measurement campaign planner (§13.6).

    Parameters
    ----------
    default_sweep_steps:
        Default number of sweep steps.
    default_hours_per_step:
        Default estimated time per step (hours).
    """

    def __init__(
        self,
        default_sweep_steps: int = 20,
        default_hours_per_step: float = 2.0,
    ) -> None:
        self._sweep_steps = default_sweep_steps
        self._hours_per_step = default_hours_per_step

    def plan(
        self,
        goal: str,
        *,
        parameters: dict[str, tuple[float, float]] | None = None,
        doe_type: str = "latin_hypercube",
        n_doe_points: int = 10,
    ) -> MeasurementPlan:
        """Generate a measurement campaign plan from a research goal.

        Parameters
        ----------
        goal:
            Research goal (e.g. "SOT efficiency CoFeB/Pt").
        parameters:
            Parameter range dictionary for multi-parameter DOE
            {parameter_name: (min, max)}.
        doe_type:
            DOE type ('full_factorial', 'partial_factorial', 'latin_hypercube').
        n_doe_points:
            Number of Latin hypercube points.

        Returns
        -------
        MeasurementPlan
        """
        effects = _find_effects_for_goal(goal)

        if not effects:
            log.warning("No relevant effect models found for goal '%s'.", goal)
            effects = [("general_measurement", 1)]

        steps = []
        for i, (effect_name, _) in enumerate(effects):
            mc_info = _get_measurement_config_from_effect(effect_name)
            instrument = _EFFECT_INSTRUMENT.get(effect_name, "unspecified instrument")

            sweeps = self._default_sweeps(effect_name)
            step = MeasurementStep(
                step_id=f"step_{i + 1:02d}_{effect_name}",
                target_quantity=goal,
                effect_model=effect_name,
                geometry=mc_info.get("geometry", ""),
                instrument_hint=instrument,
                sweeps=sweeps,
                expected_signal=f"{effect_name} signal",
                prerequisites=[f"step_{i:02d}_{effects[i - 1][0]}"] if i > 0 else [],
                estimated_hours=self._hours_per_step,
                required_columns=mc_info.get("required_columns", []),
                notes=mc_info.get("notes", ""),
            )
            steps.append(step)

        # DOE design
        doe_design: dict[str, Any] = {}
        if parameters and len(parameters) > 1:
            doe_design = self._build_doe(parameters, doe_type, n_doe_points)

        total_hours = sum(s.estimated_hours for s in steps)
        plan = MeasurementPlan(
            goal=goal,
            steps=steps,
            doe_design=doe_design,
            total_estimated_hours=total_hours,
        )
        plan.checklist_yaml = plan.to_checklist_yaml()
        return plan

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_sweeps(self, effect_name: str) -> list[SweepSpec]:
        """Return default sweep specifications for an effect model."""
        default_map: dict[str, list[SweepSpec]] = {
            "sot_harmonic_hall": [
                SweepSpec("B_applied", "mT", -500, 500, self._sweep_steps),
                SweepSpec("I_ac", "mA", 1, 10, 5),
            ],
            "stfmr": [
                SweepSpec("frequency", "GHz", 4, 20, self._sweep_steps),
                SweepSpec("B_applied", "mT", 0, 500, self._sweep_steps),
            ],
            "fmr_kittel": [
                SweepSpec("frequency", "GHz", 1, 20, self._sweep_steps),
                SweepSpec("B_applied", "mT", 0, 1000, self._sweep_steps),
            ],
            "anomalous_hall": [
                SweepSpec("B_applied", "T", -2, 2, self._sweep_steps),
            ],
            "hysteresis": [
                SweepSpec("B_applied", "T", -2, 2, self._sweep_steps * 2),
            ],
        }
        return default_map.get(
            effect_name,
            [SweepSpec("B_applied", "mT", -500, 500, self._sweep_steps)],
        )

    @staticmethod
    def _build_doe(
        parameters: dict[str, tuple[float, float]],
        doe_type: str,
        n_points: int,
    ) -> dict[str, Any]:
        """Generate a DOE design.

        Parameters
        ----------
        parameters:
            {parameter_name: (min, max)} dictionary.
        doe_type:
            'full_factorial', 'partial_factorial', 'latin_hypercube'.
        n_points:
            Number of Latin hypercube points.

        Returns
        -------
        dict[str, Any]
            DOE design metadata.
        """
        param_names = list(parameters.keys())
        n_params = len(param_names)

        if doe_type == "full_factorial":
            levels_per_param = max(2, int(n_points ** (1 / n_params)))
            grids = []
            for _pname, (lo, hi) in parameters.items():
                step = (hi - lo) / (levels_per_param - 1) if levels_per_param > 1 else 0
                grids.append([round(lo + step * i, 6) for i in range(levels_per_param)])
            design_points = list(itertools.product(*grids))
            return {
                "type": "full_factorial",
                "n_params": n_params,
                "levels_per_param": levels_per_param,
                "n_runs": len(design_points),
                "param_names": param_names,
                "design_points": design_points[:20],  # top 20 only
                "note": f"Full factorial {levels_per_param}^{n_params}={len(design_points)} runs",
            }

        elif doe_type == "latin_hypercube":
            try:
                from scipy.stats.qmc import LatinHypercube, scale

                sampler = LatinHypercube(d=n_params, seed=42)
                sample = sampler.random(n=n_points)
                lo_bounds = [v[0] for v in parameters.values()]
                hi_bounds = [v[1] for v in parameters.values()]
                scaled = scale(sample, lo_bounds, hi_bounds)
                lh_points: list[dict[str, float]] = [
                    {param_names[j]: round(row[j], 6) for j in range(n_params)} for row in scaled
                ]
                return {
                    "type": "latin_hypercube",
                    "n_params": n_params,
                    "n_runs": n_points,
                    "param_names": param_names,
                    "design_points": lh_points,
                    "note": f"Latin hypercube {n_points} runs (scipy.stats.qmc)",
                }
            except ImportError:
                # Simple grid fallback when scipy is absent
                pass

        # Fallback: simple uniform grid
        simple_points = []
        for i in range(min(n_points, 5)):
            t = i / max(n_points - 1, 1)
            pt = {pname: round(lo + t * (hi - lo), 6) for pname, (lo, hi) in parameters.items()}
            simple_points.append(pt)

        return {
            "type": "simple_grid",
            "n_params": n_params,
            "n_runs": len(simple_points),
            "param_names": param_names,
            "design_points": simple_points,
            "note": "Simple uniform grid (scipy not installed fallback)",
        }
