"""Active learning and multi-fidelity measurement optimization (§13.7).

Theorist↔experimentalist separation:
  - theorist: fits an effect model to current data → estimates model uncertainty
  - experimentalist: selects the next measurement point by information gain (Bayesian optimization)

Multi-fidelity ladder: DFT (low cost) → atomistic (medium) → experiment (high cost).
Fidelity is chosen by information gain per unit cost.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from maglab.lab.planning.state import StandardState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Information gain computation
# ---------------------------------------------------------------------------


def _compute_variance_reduction(
    conditions: np.ndarray,
    candidate: np.ndarray,
    sigma: float = 0.1,
) -> float:
    """Estimate the Gaussian process variance reduction at a candidate measurement point.

    Simplified RBF-kernel version: the farther the candidate from existing points,
    the higher the information gain.

    Parameters
    ----------
    conditions:
        Array of existing measurement conditions (n_points × n_dims).
    candidate:
        Candidate measurement point array (n_dims,).
    sigma:
        Kernel length scale.

    Returns
    -------
    float
        Estimated information gain (higher is more informative).
    """
    if conditions.shape[0] == 0:
        return 1.0

    # RBF kernel: k(x, x') = exp(-||x-x'||² / (2σ²))
    dists_sq = np.sum((conditions - candidate) ** 2, axis=1)
    similarities = np.exp(-dists_sq / (2 * sigma**2))
    # Information gain ≈ 1 - max_similarity (higher when most dissimilar to existing points)
    max_sim = float(np.max(similarities))
    return 1.0 - max_sim


def _compute_model_disagreement(
    models: list[Callable[[np.ndarray], np.ndarray]],
    candidate: np.ndarray,
) -> float:
    """Compute the prediction variance among multiple models at a candidate point.

    Parameters
    ----------
    models:
        List of prediction functions (each (n_dims,) → scalar).
    candidate:
        Candidate measurement point.

    Returns
    -------
    float
        Prediction variance across models.
    """
    if not models:
        return 0.0
    preds = []
    for model_fn in models:
        try:
            pred = float(model_fn(candidate))
            preds.append(pred)
        except Exception:  # noqa: BLE001
            pass
    if len(preds) < 2:
        return 0.0
    mean_pred = sum(preds) / len(preds)
    variance = sum((p - mean_pred) ** 2 for p in preds) / len(preds)
    return variance


# ---------------------------------------------------------------------------
# Multi-fidelity ladder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrecisionLevel:
    """Single fidelity level.

    Attributes
    ----------
    name:
        Level name ('low', 'medium', 'high').
    cost:
        Relative cost unit.
    information_factor:
        Information quality multiplier (higher is better).
    description:
        Description.
    """

    name: str
    cost: float
    information_factor: float
    description: str = ""


PRECISION_LADDER: list[PrecisionLevel] = [
    PrecisionLevel(
        name="low",
        cost=1.0,
        information_factor=0.5,
        description="DFT/theory calculation (low cost, intermediate accuracy)",
    ),
    PrecisionLevel(
        name="medium",
        cost=5.0,
        information_factor=0.8,
        description="Atomistic simulation (medium cost and accuracy)",
    ),
    PrecisionLevel(
        name="high",
        cost=20.0,
        information_factor=1.0,
        description="Experimental measurement (high cost, highest accuracy)",
    ),
]


def select_precision(
    information_gain: float,
    budget_remaining: float,
    *,
    precision_ladder: list[PrecisionLevel] | None = None,
) -> PrecisionLevel:
    """Select the optimal fidelity level by information gain per unit cost.

    Parameters
    ----------
    information_gain:
        Estimated information gain at the candidate point (0–1).
    budget_remaining:
        Remaining cost budget.
    precision_ladder:
        Fidelity ladder (uses PRECISION_LADDER by default when None).

    Returns
    -------
    PrecisionLevel
        Selected fidelity level.
    """
    ladder = precision_ladder or PRECISION_LADDER

    # Select optimal fidelity by information gain relative to budget:
    # Budget slack (budget_remaining / level.cost) determines preference for
    # higher information_factor when budget is comfortable.
    affordable = [lvl for lvl in ladder if lvl.cost <= budget_remaining]
    if not affordable:
        return ladder[0]  # If none are affordable, choose cheapest

    best = affordable[0]
    best_score = -1.0

    for level in affordable:
        # Budget slack: higher slack makes expensive options more attractive
        budget_slack = min(5.0, budget_remaining / max(level.cost, 1e-9))
        # Score: information_factor weighted by information gain and budget slack
        score = information_gain * level.information_factor * (1.0 + budget_slack)
        if score > best_score:
            best_score = score
            best = level

    return best


# ---------------------------------------------------------------------------
# Theorist — fit current data
# ---------------------------------------------------------------------------


class Theorist:
    """Fits an effect model to current measurement data to estimate uncertainty (§13.7).

    Parameters
    ----------
    target_key:
        Observation key to fit.
    fit_fn:
        Fitting function: (conditions: np.ndarray, observations: np.ndarray)
        → dict[str, float].
        Falls back to linear regression when None.
    """

    def __init__(
        self,
        target_key: str = "signal",
        fit_fn: Callable[[np.ndarray, np.ndarray], dict[str, float]] | None = None,
    ) -> None:
        self._target_key = target_key
        self._fit_fn = fit_fn
        self._last_params: dict[str, float] = {}
        self._last_uncertainty: dict[str, float] = {}

    def fit(self, state: StandardState) -> dict[str, float]:
        """Fit a model to the current state data.

        Parameters
        ----------
        state:
            Shared StandardState.

        Returns
        -------
        dict[str, float]
            Fitted parameter dictionary.
        """
        conditions = state.conditions_array()
        observations = state.observations_array(self._target_key)

        # Remove NaN values
        valid = ~np.isnan(observations)
        if valid.sum() < 2:
            return {}

        cond_valid = conditions[valid]
        obs_valid = observations[valid]

        if self._fit_fn is not None:
            try:
                params = self._fit_fn(cond_valid, obs_valid)
            except Exception as exc:  # noqa: BLE001
                log.warning("[Theorist] Fitting error: %s", exc)
                params = {}
        else:
            params = self._simple_linear_fit(cond_valid, obs_valid)

        self._last_params = params

        # Simple uncertainty estimate (data variance based)
        if len(obs_valid) > 1:
            residuals = obs_valid - np.mean(obs_valid)
            uncertainty_scale = float(np.std(residuals))
            self._last_uncertainty = dict.fromkeys(params, uncertainty_scale)

        state.current_best_model = params
        state.model_uncertainty = self._last_uncertainty
        return params

    @staticmethod
    def _simple_linear_fit(
        conditions: np.ndarray,
        observations: np.ndarray,
    ) -> dict[str, float]:
        """Simple linear regression fallback."""
        if conditions.shape[1] == 0:
            return {"intercept": float(np.mean(observations))}
        # Linear regression on the first condition variable
        x = conditions[:, 0]
        if np.std(x) < 1e-9:
            return {"intercept": float(np.mean(observations))}
        slope = float(np.cov(x, observations)[0, 1] / np.var(x))
        intercept = float(np.mean(observations) - slope * np.mean(x))
        return {"slope": slope, "intercept": intercept}


# ---------------------------------------------------------------------------
# Experimentalist — select next measurement point
# ---------------------------------------------------------------------------


@dataclass
class NextPointSuggestion:
    """Next measurement point suggestion.

    Attributes
    ----------
    conditions:
        Suggested measurement conditions.
    information_gain:
        Estimated information gain (0–1).
    precision:
        Recommended fidelity level.
    rationale:
        Reason for the selection.
    """

    conditions: dict[str, float]
    information_gain: float
    precision: PrecisionLevel
    rationale: str


class Experimentalist:
    """Selects the next measurement point by information gain criterion (§13.7).

    Parameters
    ----------
    search_grid_points:
        Candidate point search grid size.
    budget_remaining:
        Remaining cost budget.
    """

    def __init__(
        self,
        search_grid_points: int = 50,
        budget_remaining: float = 100.0,
    ) -> None:
        self._grid_points = search_grid_points
        self._budget = budget_remaining

    def suggest_next(
        self,
        state: StandardState,
        *,
        models: list[Callable[[np.ndarray], np.ndarray]] | None = None,
    ) -> NextPointSuggestion:
        """Suggest the next measurement point.

        Parameters
        ----------
        state:
            Shared StandardState.
        models:
            List of current model prediction functions (for model disagreement).

        Returns
        -------
        NextPointSuggestion
        """
        if not state.feasible_region:
            return NextPointSuggestion(
                conditions={},
                information_gain=0.0,
                precision=PRECISION_LADDER[-1],
                rationale="No measurement points — feasible region undefined. Initial exploration required.",
            )

        conditions_arr = state.conditions_array()
        param_names = sorted(state.feasible_region.keys())

        # Generate candidate point grid
        candidate_list = self._generate_candidates(state.feasible_region, param_names)

        # Compute information gain
        best_cand: dict[str, float] = {}
        best_gain = -1.0

        for candidate_dict in candidate_list:
            candidate_vec = np.array([candidate_dict[p] for p in param_names])

            # Variance reduction (distance from existing points)
            var_reduction = _compute_variance_reduction(conditions_arr, candidate_vec)

            # Model disagreement
            disagreement = 0.0
            if models:
                disagreement = _compute_model_disagreement(models, candidate_vec)

            gain = 0.6 * var_reduction + 0.4 * min(1.0, disagreement)

            if gain > best_gain:
                best_gain = gain
                best_cand = candidate_dict

        precision = select_precision(best_gain, self._budget)

        return NextPointSuggestion(
            conditions=best_cand,
            information_gain=round(best_gain, 4),
            precision=precision,
            rationale=(
                f"Information gain {best_gain:.3f} — under-explored region relative to "
                f"{len(state.measured_points)} existing points. "
                f"Recommended fidelity: {precision.name} ({precision.description})."
            ),
        )

    def _generate_candidates(
        self,
        feasible_region: dict[str, tuple[float, float]],
        param_names: list[str],
    ) -> list[dict[str, float]]:
        """Generate candidate points within the feasible region."""
        try:
            from scipy.stats.qmc import LatinHypercube, scale

            sampler = LatinHypercube(d=len(param_names), seed=0)
            samples = sampler.random(n=self._grid_points)
            lo = [feasible_region[p][0] for p in param_names]
            hi = [feasible_region[p][1] for p in param_names]
            scaled = scale(samples, lo, hi)
            return [
                {param_names[j]: float(row[j]) for j in range(len(param_names))} for row in scaled
            ]
        except ImportError:
            pass

        # Fallback: uniform grid
        candidates = []
        for i in range(self._grid_points):
            t = i / max(self._grid_points - 1, 1)
            pt = {
                p: feasible_region[p][0] + t * (feasible_region[p][1] - feasible_region[p][0])
                for p in param_names
            }
            candidates.append(pt)
        return candidates


# ---------------------------------------------------------------------------
# Active learning loop (theorist↔experimentalist)
# ---------------------------------------------------------------------------


@dataclass
class ActiveLearningResult:
    """Active learning loop result.

    Attributes
    ----------
    state:
        Final StandardState.
    suggestions:
        List of measurement point suggestions per round.
    n_rounds:
        Number of rounds executed.
    final_model:
        Final fitted model parameters.
    """

    state: StandardState
    suggestions: list[NextPointSuggestion]
    n_rounds: int
    final_model: dict[str, float]


def run_active_learning(
    state: StandardState,
    *,
    target_key: str = "signal",
    fit_fn: Callable[[np.ndarray, np.ndarray], dict[str, float]] | None = None,
    n_rounds: int = 5,
    budget_per_round: float = 20.0,
    search_grid_points: int = 50,
) -> ActiveLearningResult:
    """Run the active learning loop (§13.7).

    Parameters
    ----------
    state:
        Initial StandardState (including existing measurement points).
    target_key:
        Observation key to fit.
    fit_fn:
        Fitting function.
    n_rounds:
        Number of active learning rounds.
    budget_per_round:
        Cost budget per round.
    search_grid_points:
        Candidate point grid size.

    Returns
    -------
    ActiveLearningResult
    """
    theorist = Theorist(target_key=target_key, fit_fn=fit_fn)
    experimentalist = Experimentalist(
        search_grid_points=search_grid_points,
        budget_remaining=budget_per_round,
    )

    suggestions: list[NextPointSuggestion] = []

    for round_i in range(n_rounds):
        log.info("[Active learning] Round %d/%d", round_i + 1, n_rounds)

        # Theorist: fit current data
        theorist.fit(state)

        # Experimentalist: select next measurement point
        suggestion = experimentalist.suggest_next(state)
        suggestions.append(suggestion)

        log.info(
            "[Active learning] Suggestion conditions=%s, information_gain=%.3f, fidelity=%s",
            suggestion.conditions,
            suggestion.information_gain,
            suggestion.precision.name,
        )

        # Actual measurement simulation (test/dummy: in real use, a human/instrument measures
        # and adds results via state.add_point() after this pause)

    return ActiveLearningResult(
        state=state,
        suggestions=suggestions,
        n_rounds=n_rounds,
        final_model=state.current_best_model,
    )
