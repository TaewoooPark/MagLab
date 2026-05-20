"""tests/unit/test_reasoning_d1.py — D1 hypothesis generation unit tests (§5.10)."""

from __future__ import annotations

from typing import Any

import pytest

from maglab.core.reasoning import (
    _ELO_INITIAL,
    D1HypothesisEngine,
    HypothesisCandidate,
    HypothesisResult,
    _expected_score,
    _update_elo,
    generate_candidates,
    generate_hypotheses,
    generate_hypothesis,
    rank_by_elo,
    reflection_physics_check,
)

# ---------------------------------------------------------------------------
# Elo helper tests
# ---------------------------------------------------------------------------


class TestEloHelpers:
    def test_expected_score_equal_ratings(self) -> None:
        """Equal ratings yield 0.5 expected score."""
        score = _expected_score(1200.0, 1200.0)
        assert abs(score - 0.5) < 1e-9

    def test_expected_score_higher_rating_wins(self) -> None:
        """Higher rating yields expected score > 0.5."""
        score = _expected_score(1400.0, 1200.0)
        assert score > 0.5

    def test_update_elo_winner_gains(self) -> None:
        """The winner gains rating points."""
        ra, rb = _update_elo(1200.0, 1200.0, score_a=1.0)
        assert ra > 1200.0
        assert rb < 1200.0

    def test_update_elo_loser_loses(self) -> None:
        """The loser loses rating points."""
        ra, rb = _update_elo(1200.0, 1200.0, score_a=0.0)
        assert ra < 1200.0
        assert rb > 1200.0

    def test_update_elo_draw_small_change(self) -> None:
        """A draw between equal players produces tiny changes."""
        ra, rb = _update_elo(1200.0, 1200.0, score_a=0.5)
        assert abs(ra - 1200.0) < 1.0
        assert abs(rb - 1200.0) < 1.0

    def test_update_elo_sum_conserved(self) -> None:
        """The sum of ratings is conserved after an update."""
        ra, rb = _update_elo(1200.0, 1400.0, score_a=1.0)
        assert abs((ra + rb) - (1200.0 + 1400.0)) < 1e-6


# ---------------------------------------------------------------------------
# generate_candidates
# ---------------------------------------------------------------------------


class TestGenerateCandidates:
    def test_returns_requested_n(self) -> None:
        candidates = generate_candidates("spin Hall effect", n=3, rng_seed=0)
        assert len(candidates) == 3

    def test_returns_at_least_one(self) -> None:
        candidates = generate_candidates("any topic", n=1)
        assert len(candidates) >= 1

    def test_n_clamped_to_20(self) -> None:
        candidates = generate_candidates("topic", n=999)
        assert len(candidates) <= 20

    def test_candidate_ids_unique(self) -> None:
        candidates = generate_candidates("AHE", n=5, rng_seed=42)
        ids = [c.hypothesis_id for c in candidates]
        assert len(set(ids)) == len(ids)

    def test_initial_elo_is_default(self) -> None:
        candidates = generate_candidates("FMR", n=3, rng_seed=0)
        for c in candidates:
            assert c.elo_rating == _ELO_INITIAL

    def test_idea_not_empty(self) -> None:
        candidates = generate_candidates("magnetic anisotropy", n=4, rng_seed=1)
        for c in candidates:
            assert c.idea.strip() != ""

    def test_verified_cite_pool_filters_keys(self) -> None:
        """cite-keys not in the verified pool must be removed."""
        pool: set[str] = {"valid_key_1", "valid_key_2"}

        def _llm_fn(topic: str, gap: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [
                {
                    "idea": "Test hypothesis",
                    "novelty_rationale": "Novel idea",
                    "novelty_cite_keys": ["valid_key_1", "INVALID_KEY"],
                    "verification_method": "Measure it",
                    "feasibility_score": 0.7,
                    "impact_score": 0.8,
                }
            ]

        candidates = generate_candidates(
            "topic", n=1, llm_generate_fn=_llm_fn, verified_cite_pool=pool
        )
        assert len(candidates) == 1
        assert "INVALID_KEY" not in candidates[0].novelty_cite_keys
        assert "valid_key_1" in candidates[0].novelty_cite_keys

    def test_llm_fn_failure_falls_back_to_seeds(self) -> None:
        """If the LLM function raises, seeds are used instead."""

        def _bad_llm(topic: str, gap: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
            raise RuntimeError("LLM unavailable")

        candidates = generate_candidates("skyrmion", n=3, llm_generate_fn=_bad_llm)
        assert len(candidates) >= 1


# ---------------------------------------------------------------------------
# rank_by_elo
# ---------------------------------------------------------------------------


class TestRankByElo:
    def _make_candidates(self, n: int = 4) -> list[HypothesisCandidate]:
        return generate_candidates("test topic", n=n, rng_seed=42)

    def test_returns_same_count(self) -> None:
        candidates = self._make_candidates(4)
        ranked = rank_by_elo(candidates, rng_seed=0)
        assert len(ranked) == 4

    def test_ranks_are_one_based(self) -> None:
        candidates = self._make_candidates(3)
        ranked = rank_by_elo(candidates, rng_seed=0)
        assert [r.rank for r in ranked] == [1, 2, 3]

    def test_elo_ratings_differ(self) -> None:
        """After the tournament, candidates should have different Elo ratings."""
        candidates = self._make_candidates(5)
        # Give them distinct feasibility/impact to force different outcomes
        for i, c in enumerate(candidates):
            c.feasibility_score = (i + 1) * 0.1
            c.impact_score = (i + 1) * 0.1
        ranked = rank_by_elo(candidates, rng_seed=7)
        elos = [r.candidate.elo_rating for r in ranked]
        assert len(set(elos)) > 1  # not all identical

    def test_sorted_descending_elo(self) -> None:
        candidates = self._make_candidates(5)
        ranked = rank_by_elo(candidates, rng_seed=3)
        elos = [r.candidate.elo_rating for r in ranked]
        assert elos == sorted(elos, reverse=True)

    def test_empty_returns_empty(self) -> None:
        assert rank_by_elo([]) == []

    def test_single_candidate_rank_one(self) -> None:
        candidates = self._make_candidates(1)
        ranked = rank_by_elo(candidates, rng_seed=0)
        assert len(ranked) == 1
        assert ranked[0].rank == 1

    def test_ai_label_present(self) -> None:
        candidates = self._make_candidates(2)
        ranked = rank_by_elo(candidates, rng_seed=0)
        for rh in ranked:
            assert rh.ai_label == "AI suggestion"

    def test_llm_compare_fn_used(self) -> None:
        """When llm_compare_fn is provided it should influence the outcome."""
        candidates = self._make_candidates(3)
        # Always give candidate A a perfect score — rank order should be A > B > C
        # We just check it doesn't raise.
        calls: list[str] = []

        def _compare(a: HypothesisCandidate, b: HypothesisCandidate, criterion: str) -> float:
            calls.append(criterion)
            return 1.0  # A always wins

        ranked = rank_by_elo(candidates, llm_compare_fn=_compare, rng_seed=0)
        assert len(calls) > 0
        assert len(ranked) == 3


# ---------------------------------------------------------------------------
# reflection_physics_check
# ---------------------------------------------------------------------------


class TestReflectionPhysicsCheck:
    def _make_candidate(self, idea: str, rationale: str = "") -> HypothesisCandidate:
        return HypothesisCandidate(
            hypothesis_id="H01",
            idea=idea,
            novelty_rationale=rationale,
        )

    def test_valid_hypothesis_passes(self) -> None:
        c = self._make_candidate("Spin Hall effect enhancement via interface engineering")
        result = reflection_physics_check(c)
        assert result.valid is True
        assert result.contradiction == ""

    def test_perpetual_motion_rejected(self) -> None:
        c = self._make_candidate("A perpetual motion device based on spin currents")
        result = reflection_physics_check(c)
        assert result.valid is False
        assert result.contradiction != ""

    def test_faster_than_light_rejected(self) -> None:
        c = self._make_candidate(
            "Domain wall propagation faster than light enables new logic gates"
        )
        result = reflection_physics_check(c)
        assert result.valid is False

    def test_negative_damping_rejected(self) -> None:
        c = self._make_candidate("Negative gilbert damping for zero-loss propagation")
        result = reflection_physics_check(c)
        assert result.valid is False

    def test_generates_energy_rejected(self) -> None:
        c = self._make_candidate("This material generates energy spontaneously")
        result = reflection_physics_check(c)
        assert result.valid is False

    def test_custom_oracle_called(self) -> None:
        """Custom oracle_check_fn should be invoked."""
        called: list[dict] = []

        class _FakeOracleResult:
            ok = True

            def __bool__(self) -> bool:
                return True

        def _oracle(params: dict) -> _FakeOracleResult:
            called.append(params)
            return _FakeOracleResult()

        c = self._make_candidate("Some hypothesis mentioning absolute zero temperature")
        reflection_physics_check(c, oracle_check_fn=_oracle)
        # oracle should have been called because "absolute zero" is in the text
        assert len(called) > 0

    def test_custom_formulas_check_fn_failure(self) -> None:
        c = self._make_candidate("Novel hypothesis")

        def _bad_check(text: str) -> bool:
            return False

        result = reflection_physics_check(c, formulas_check_fn=_bad_check)
        assert result.valid is False

    def test_result_has_reason(self) -> None:
        c = self._make_candidate("Normal hypothesis about AHE")
        result = reflection_physics_check(c)
        assert result.reason != ""


# ---------------------------------------------------------------------------
# D1HypothesisEngine
# ---------------------------------------------------------------------------


class TestD1HypothesisEngine:
    def test_run_returns_hypothesis_result(self) -> None:
        engine = D1HypothesisEngine(n=3, rng_seed=42)
        result = engine.run("anomalous Hall effect")
        assert isinstance(result, HypothesisResult)

    def test_result_has_ranked_list(self) -> None:
        engine = D1HypothesisEngine(n=4, rng_seed=0)
        result = engine.run("spin Seebeck effect")
        assert len(result.ranked) == 4

    def test_each_ranked_has_physical_valid(self) -> None:
        engine = D1HypothesisEngine(n=3, rng_seed=1)
        result = engine.run("skyrmion Hall effect")
        for rh in result.ranked:
            assert isinstance(rh.physical_valid, bool)

    def test_disclaimer_present(self) -> None:
        engine = D1HypothesisEngine(n=2, rng_seed=0)
        result = engine.run("FMR linewidth")
        assert "AI suggestion" in result.disclaimer or "AI suggestions" in result.disclaimer

    def test_to_dict_structure(self) -> None:
        engine = D1HypothesisEngine(n=2, rng_seed=0)
        result = engine.run("test topic")
        d = result.to_dict()
        assert "topic" in d
        assert "hypotheses" in d
        assert "disclaimer" in d
        assert "n_hypotheses" in d

    def test_summary_text(self) -> None:
        engine = D1HypothesisEngine(n=2, rng_seed=0)
        result = engine.run("orbital Hall")
        text = result.summary()
        assert "D1 Hypothesis Engine" in text
        assert "AI suggestion" in text


# ---------------------------------------------------------------------------
# generate_hypotheses (public entry point)
# ---------------------------------------------------------------------------


class TestGenerateHypotheses:
    def test_basic_call(self) -> None:
        result = generate_hypotheses("spin-orbit torque", n=3, rng_seed=0)
        assert isinstance(result, HypothesisResult)
        assert len(result.ranked) == 3

    def test_returns_sorted_by_elo(self) -> None:
        result = generate_hypotheses("AHE", n=5, rng_seed=7)
        elos = [rh.candidate.elo_rating for rh in result.ranked]
        assert elos == sorted(elos, reverse=True)

    def test_each_hypothesis_has_id(self) -> None:
        result = generate_hypotheses("magnon", n=4, rng_seed=0)
        ids = [rh.candidate.hypothesis_id for rh in result.ranked]
        assert all(hid.startswith("H") for hid in ids)

    def test_with_verified_cite_pool(self) -> None:
        pool: set[str] = {"cite_key_A"}

        def _llm_fn(topic: str, gap: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [
                {
                    "idea": "Test idea",
                    "novelty_rationale": "Novel",
                    "novelty_cite_keys": ["cite_key_A", "INVALID"],
                    "verification_method": "Measure",
                    "feasibility_score": 0.6,
                    "impact_score": 0.7,
                }
            ]

        result = generate_hypotheses("test", n=1, llm_generate_fn=_llm_fn, verified_cite_pool=pool)
        assert "INVALID" not in result.ranked[0].candidate.novelty_cite_keys


# ---------------------------------------------------------------------------
# generate_hypothesis (backwards-compat)
# ---------------------------------------------------------------------------


class TestGenerateHypothesisCompat:
    def test_returns_dict(self) -> None:
        result = generate_hypothesis("spin Hall effect")
        assert isinstance(result, dict)
        assert "hypotheses" in result
        assert "topic" in result

    def test_no_longer_raises_not_implemented(self) -> None:
        """The stub was replaced — it must not raise NotImplementedError."""
        try:
            generate_hypothesis("magnetic skyrmion")
        except NotImplementedError:
            pytest.fail("generate_hypothesis raised NotImplementedError")


# ---------------------------------------------------------------------------
# REGRESSION — Finding 2 (R3): reflection_physics_check must NOT false-positive
# on temperatures like 100 K, 300 K, 10 K because of the "0 k" substring match.
#
# Before the fix, "0 k" in full_text matched any temperature whose digit string
# ends in "0" followed by a space and "k" (e.g. "30[0 k]" in "300 K").
# The bug set params["T"] = 0.0, causing the oracle to reject the hypothesis
# as non-physical (T <= 0).
#
# After the fix, only an isolated "0 K" token (word-bounded) or the explicit
# phrase "absolute zero" triggers the oracle T=0 check.
# ---------------------------------------------------------------------------


class TestReflectionPhysicsCheckTemperatureRegression:
    """R3/F2 — Valid temperatures ending in 0 (100 K, 300 K, 10 K) must not be
    false-flagged as T=0 by reflection_physics_check."""

    def _make_candidate(self, idea: str, rationale: str = "") -> HypothesisCandidate:
        return HypothesisCandidate(
            hypothesis_id="H_REG",
            idea=idea,
            novelty_rationale=rationale,
        )

    @pytest.mark.parametrize(
        "temperature_text",
        [
            "Topological Hall effect in YBa2Cu3O7 at 300 K shows anomalous transition",
            "Spin transport measurement at 100 K below the Curie temperature",
            "Magnon-drag at 10 K in dilution refrigerator experiment",
            "AHE sign reversal at 200 K near the magnetic phase boundary",
            "FMR linewidth anomaly observed at 400 K during field sweep",
            "Skyrmion lattice stabilised at 20 K in thin film geometry",
        ],
    )
    def test_valid_temperature_not_rejected(self, temperature_text: str) -> None:
        """Hypothesis mentioning a temperature like 300 K must not be rejected as T=0."""
        oracle_called_with: list[dict] = []

        class _FakeOracleResult:
            ok = False  # would reject if called with T=0

            def __bool__(self) -> bool:
                return False

        def _strict_oracle(params: dict) -> _FakeOracleResult:
            oracle_called_with.append(dict(params))
            return _FakeOracleResult()

        c = self._make_candidate(temperature_text)
        result = reflection_physics_check(c, oracle_check_fn=_strict_oracle)

        # If the oracle was called with T=0.0 it means the bug fired
        t_zero_calls = [p for p in oracle_called_with if p.get("T") == 0.0]
        assert t_zero_calls == [], (
            f"False-positive: oracle called with T=0.0 for text '{temperature_text}'. "
            f"The '0 k' substring check incorrectly matched a digit inside a larger number."
        )
        assert result.valid is True, (
            f"reflection_physics_check incorrectly rejected a valid hypothesis: "
            f"'{temperature_text}' → valid={result.valid}, contradiction={result.contradiction!r}"
        )

    def test_genuine_absolute_zero_is_still_rejected(self) -> None:
        """A hypothesis explicitly claiming absolute zero must still be rejected."""
        c = self._make_candidate(
            "Spin transport at absolute zero temperature without any thermal noise"
        )
        oracle_called_with: list[dict] = []

        class _ZeroRejectOracle:
            def __bool__(self) -> bool:
                return False

            reason = "Temperature must be > 0 K"

        def _oracle(params: dict) -> _ZeroRejectOracle:
            oracle_called_with.append(dict(params))
            return _ZeroRejectOracle()

        result = reflection_physics_check(c, oracle_check_fn=_oracle)
        t_zero_calls = [p for p in oracle_called_with if p.get("T") == 0.0]
        assert t_zero_calls != [], (
            "'absolute zero' in text must still trigger the oracle T=0.0 check."
        )
        assert result.valid is False

    def test_explicit_0_k_token_still_triggers_oracle(self) -> None:
        """A hypothesis stating '0 K' as a standalone token must trigger the check."""
        # "operates at 0 K" — the "0" is a standalone number, not trailing digits
        c = self._make_candidate("Spintronic device operates at 0 K with perfect coherence")
        oracle_called_with: list[dict] = []

        class _ZeroRejectOracle:
            def __bool__(self) -> bool:
                return False

            reason = "Temperature must be > 0 K"

        def _oracle(params: dict) -> _ZeroRejectOracle:
            oracle_called_with.append(dict(params))
            return _ZeroRejectOracle()

        result = reflection_physics_check(c, oracle_check_fn=_oracle)
        t_zero_calls = [p for p in oracle_called_with if p.get("T") == 0.0]
        assert t_zero_calls != [], (
            "A standalone '0 K' token must still trigger the oracle T=0.0 check."
        )
        assert result.valid is False


# ---------------------------------------------------------------------------
# REGRESSION — R6/F1: generate_candidates matching-seed priority
#
# Before the fix, rng.shuffle(pool_shuffled) destroyed the intended ordering
# (matching seeds first), so topic-matched seeds had no higher probability of
# being selected when the slice n < len(matching).  After the fix, each group
# is shuffled separately: matching-group first, non-matching-group after.
# ---------------------------------------------------------------------------


class TestGenerateCandidatesMatchingPriority:
    """R6/F1 — Matching seeds must appear before non-matching seeds in the pool.

    Strategy: inject a fake pool (via monkeypatching) where a strict subset of
    seeds match the query topic word, then request n candidates smaller than
    the number of matching seeds.  Every returned candidate must come from the
    matching group, not from the non-matching group.
    """

    def test_matching_seeds_have_priority_when_n_less_than_matching(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When n < len(matching), all returned candidates must be from the matching group."""
        import maglab.core.reasoning as _reasoning_mod

        # Build a controlled fake seed pool:
        #   - 3 seeds whose idea contains the word "skyrmion" (matching)
        #   - 2 seeds whose idea contains only "magnon" (non-matching for "skyrmion" query)
        matching_ideas = [
            "skyrmion Hall effect in chiral magnets",
            "skyrmion nucleation via spin-orbit coupling",
            "skyrmion lattice dynamics probed by neutrons",
        ]
        nonmatching_ideas = [
            "magnon-drag in ferrimagnets at low temperature",
            "magnon Seebeck coefficient in Heusler alloys",
        ]

        fake_seeds: list[dict[str, Any]] = [
            {
                "idea": idea,
                "novelty_rationale": "test",
                "novelty_cite_keys": [],
                "verification_method": "test",
                "feasibility_score": 0.5,
                "impact_score": 0.5,
            }
            for idea in matching_ideas + nonmatching_ideas
        ]

        monkeypatch.setattr(_reasoning_mod, "_HYPOTHESIS_SEEDS", fake_seeds)

        # Request n=2, which is less than the 3 matching seeds — all results must
        # come from the matching group.
        n = 2
        candidates = generate_candidates("skyrmion", n=n, rng_seed=0)

        assert len(candidates) == n, f"Expected {n} candidates, got {len(candidates)}"

        returned_ideas = {c.idea for c in candidates}
        matching_ideas_set = set(matching_ideas)
        nonmatching_ideas_set = set(nonmatching_ideas)

        for idea in returned_ideas:
            assert idea in matching_ideas_set, (
                f"Candidate idea {idea!r} is from the non-matching group; "
                "topic-priority shuffle is broken — matching seeds must come first."
            )
        assert returned_ideas.isdisjoint(nonmatching_ideas_set), (
            "Non-matching seed ideas must not appear when n < len(matching). "
            "The per-group shuffle must preserve the matching-first ordering."
        )

    def test_matching_seeds_exhausted_falls_through_to_nonmatching(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When n > len(matching), non-matching seeds fill the remainder."""
        import maglab.core.reasoning as _reasoning_mod

        matching_ideas = ["skyrmion Hall effect in chiral magnets"]
        nonmatching_ideas = [
            "magnon-drag at low temperature",
            "orbital Hall effect in light metals",
            "spin Seebeck in Heusler alloys",
        ]

        fake_seeds: list[dict[str, Any]] = [
            {
                "idea": idea,
                "novelty_rationale": "test",
                "novelty_cite_keys": [],
                "verification_method": "test",
                "feasibility_score": 0.5,
                "impact_score": 0.5,
            }
            for idea in matching_ideas + nonmatching_ideas
        ]

        monkeypatch.setattr(_reasoning_mod, "_HYPOTHESIS_SEEDS", fake_seeds)

        # Request more candidates than matching seeds — matching must appear first.
        candidates = generate_candidates("skyrmion", n=4, rng_seed=42)

        assert len(candidates) == 4
        # The first candidate must be the single matching seed.
        assert candidates[0].idea == matching_ideas[0], (
            f"First candidate should be the matching seed, got {candidates[0].idea!r}"
        )
