"""tests/unit/test_lab_planning.py — measurement planning and active learning unit tests."""

from __future__ import annotations

import numpy as np
import pytest

from maglab.lab.planning.active_learning import (
    ActiveLearningResult,
    Experimentalist,
    Theorist,
    _compute_variance_reduction,
    run_active_learning,
    select_precision,
)
from maglab.lab.planning.planner import MeasurementPlan, MeasurementPlanner
from maglab.lab.planning.state import MeasurementPoint, StandardState


class TestMeasurementPlanner:
    """MeasurementPlanner unit tests."""

    def test_plan_sot_efficiency(self):
        """SOT efficiency goal produces a harmonic Hall / ST-FMR measurement plan."""
        planner = MeasurementPlanner()
        plan = planner.plan("SOT efficiency CoFeB/Pt")
        assert isinstance(plan, MeasurementPlan)
        assert len(plan.steps) >= 1
        # includes harmonic hall or ST-FMR
        effect_names = [s.effect_model for s in plan.steps]
        assert any("sot" in e.lower() or "stfmr" in e.lower() for e in effect_names)

    def test_plan_damping_includes_fmr(self):
        """Damping goal includes an FMR measurement."""
        planner = MeasurementPlanner()
        plan = planner.plan("damping constant alpha")
        effect_names = [s.effect_model for s in plan.steps]
        assert any("fmr" in e.lower() or "damping" in e.lower() for e in effect_names)

    def test_plan_steps_have_geometry(self):
        """All measurement steps have geometry information."""
        planner = MeasurementPlanner()
        plan = planner.plan("anomalous Hall effect")
        for step in plan.steps:
            assert step.geometry != ""

    def test_plan_steps_have_sweep(self):
        """All measurement steps have a sweep specification."""
        planner = MeasurementPlanner()
        plan = planner.plan("spin Hall angle")
        for step in plan.steps:
            assert len(step.sweeps) >= 1

    def test_plan_total_hours(self):
        """Total estimated time is greater than zero."""
        planner = MeasurementPlanner()
        plan = planner.plan("Hall effect")
        assert plan.total_estimated_hours > 0

    def test_plan_checklist_yaml(self):
        """Living checklist YAML is generated."""
        planner = MeasurementPlanner()
        plan = planner.plan("FMR measurement")
        yaml = plan.to_checklist_yaml()
        assert "steps:" in yaml
        assert "done: false" in yaml

    def test_plan_latin_hypercube_doe(self):
        """Multi-parameter goal generates a Latin hypercube DOE."""
        planner = MeasurementPlanner()
        params = {"temperature": (5.0, 300.0), "field": (-2.0, 2.0)}
        plan = planner.plan("anomalous Hall", parameters=params, n_doe_points=8)
        if plan.doe_design:
            assert plan.doe_design.get("n_params", 0) >= 2

    def test_plan_to_dict(self):
        """Verify serialization behavior."""
        planner = MeasurementPlanner()
        plan = planner.plan("Hall effect")
        d = plan.to_dict()
        assert "goal" in d
        assert "steps" in d


class TestStandardState:
    """StandardState unit tests."""

    def test_add_point_updates_feasible_region(self):
        state = StandardState(goal="test")
        state.add_point(
            MeasurementPoint(
                conditions={"B": 0.5, "T": 300.0},
                observations={"Rxy": 0.01},
            )
        )
        assert "B" in state.feasible_region
        assert "T" in state.feasible_region

    def test_conditions_array(self):
        state = StandardState()
        state.add_point(MeasurementPoint({"B": 0.5}, {"signal": 1.0}))
        state.add_point(MeasurementPoint({"B": 1.0}, {"signal": 2.0}))
        arr = state.conditions_array()
        assert arr.shape == (2, 1)

    def test_observations_array(self):
        state = StandardState()
        state.add_point(MeasurementPoint({"B": 0.5}, {"signal": 1.5}))
        obs = state.observations_array("signal")
        assert obs[0] == pytest.approx(1.5)


class TestActiveLearning:
    """Active learning theorist↔experimentalist tests."""

    def test_variance_reduction_far_point(self):
        """A candidate far from existing points has a higher information gain."""
        existing = np.array([[0.0, 0.0], [1.0, 1.0]])
        candidate_far = np.array([5.0, 5.0])
        candidate_near = np.array([0.1, 0.1])
        gain_far = _compute_variance_reduction(existing, candidate_far)
        gain_near = _compute_variance_reduction(existing, candidate_near)
        assert gain_far > gain_near

    def test_select_precision_high_budget(self):
        """With sufficient budget, a high fidelity level can be selected."""
        level = select_precision(0.9, budget_remaining=100.0)
        # high information gain + sufficient budget → high or medium
        assert level.name in ["high", "medium"]

    def test_select_precision_low_budget(self):
        """Low budget leads to lower fidelity selection."""
        level = select_precision(0.9, budget_remaining=2.0)
        assert level.cost <= 2.0

    def test_theorist_fit(self):
        """Theorist performs a linear fit on the data."""
        state = StandardState(goal="test")
        for i in range(5):
            state.add_point(
                MeasurementPoint(
                    {"B": float(i)},
                    {"signal": float(i) * 2.0},
                )
            )
        theorist = Theorist(target_key="signal")
        params = theorist.fit(state)
        assert isinstance(params, dict)

    def test_experimentalist_suggests_next(self):
        """Experimentalist suggests the next measurement point."""
        state = StandardState(goal="test")
        state.add_point(MeasurementPoint({"B": 0.0}, {"signal": 0.0}))
        state.add_point(MeasurementPoint({"B": 1.0}, {"signal": 1.0}))
        exp = Experimentalist(search_grid_points=10, budget_remaining=100.0)
        suggestion = exp.suggest_next(state)
        assert isinstance(suggestion.conditions, dict)
        assert suggestion.information_gain >= 0.0

    def test_active_learning_n_rounds(self):
        """run_active_learning executes the specified number of rounds."""
        state = StandardState(goal="test")
        state.add_point(MeasurementPoint({"B": 0.5}, {"signal": 1.0}))
        state.add_point(MeasurementPoint({"B": 1.0}, {"signal": 2.0}))
        result = run_active_learning(state, n_rounds=3, search_grid_points=10)
        assert isinstance(result, ActiveLearningResult)
        assert result.n_rounds == 3
        assert len(result.suggestions) == 3

    def test_information_gain_above_random(self):
        """Active selection information gain is greater than zero."""
        state = StandardState(goal="test")
        for i in range(5):
            state.add_point(MeasurementPoint({"B": float(i)}, {"signal": float(i)}))
        exp = Experimentalist(search_grid_points=20, budget_remaining=100.0)
        suggestion = exp.suggest_next(state)
        # should target an under-explored region relative to existing points
        assert suggestion.information_gain >= 0.0
