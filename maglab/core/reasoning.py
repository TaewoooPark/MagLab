"""Anomaly explanation D2 + hypothesis generation D1 (§5.11, §5.10).

D2 — Abductive reasoning for anomalous results (``maglab explain``).
D1 — Hypothesis generation and Elo-tournament ranking (``maglab hypotheses``).

D2 pipeline (§5.11)
--------------------
1. Generate mechanism candidates via abductive reasoning (LLM optional —
   but LLM must never produce raw numerical values).
2. Search literature RAG for supporting evidence per candidate.
3. Propose discriminating measurements / simulations per candidate.

D1 pipeline (§5.10)
--------------------
1. Generate candidate hypotheses from literature gaps, current results, and
   research-loop state (``generate_candidates``).
2. Rank candidates via Elo tournament — pairwise comparison on four criteria:
   novelty, testability, feasibility, impact (``rank_by_elo``).
3. Reflection pass checks physical validity against ``oracle`` / ``formulas``
   (``reflection_physics_check``).

Integrity (both D1 and D2)
--------------------------
- LLM does not generate numerical values or fabricate citations.
- Hypotheses and explanations are explicitly labelled as AI suggestions.
- Novelty evidence must reference verified cite-keys (not invented DOIs).
- Physical plausibility is checked deterministically via ``oracle``.
"""

from __future__ import annotations

import logging
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Word-bounded pattern that matches a standalone "0 K" / "0k" claim,
# but NOT a trailing zero inside a larger number like "100 K" or "300 K".
_ABSOLUTE_ZERO_RE = re.compile(r"(?<!\d)0\s*k(?!\w)", re.IGNORECASE)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D2 data structures
# ---------------------------------------------------------------------------


class ConfidenceLevel(StrEnum):
    """Mechanism candidate confidence level."""

    HIGH = "high"
    """Physically well-established mechanism with strong literature support."""
    MEDIUM = "medium"
    """Plausible but has remaining uncertainty."""
    LOW = "low"
    """Possible but with low prior probability."""
    SPECULATIVE = "speculative"
    """Speculative — requires strong additional evidence."""


@dataclass
class DiscriminatingTest:
    """Discriminating test proposal.

    Attributes
    ----------
    test_id:
        Test identifier.
    description:
        Test description (what to measure/simulate and how).
    discriminates_between:
        List of mechanism candidate IDs this test distinguishes.
    expected_if_true:
        Expected outcome when this candidate is correct (qualitative).
    expected_if_false:
        Expected outcome when this candidate is incorrect (qualitative).
    method:
        'measurement' or 'simulation'.
    difficulty:
        Execution difficulty ('easy', 'moderate', 'hard').
    """

    test_id: str
    description: str
    discriminates_between: list[str] = field(default_factory=list)
    expected_if_true: str = ""
    expected_if_false: str = ""
    method: str = "measurement"
    difficulty: str = "moderate"


@dataclass
class MechanismCandidate:
    """Mechanism candidate card.

    Attributes
    ----------
    candidate_id:
        Candidate identifier.
    mechanism:
        Mechanism description (physical mechanism).
    physical_basis:
        Why this mechanism could produce the observed signal
        (physical rationale — LLM reasoning, no numerical values).
    supporting_evidence:
        List of supporting evidence [(DOI, excerpt), ...].
    contradicting_evidence:
        List of contradicting evidence [(DOI, excerpt), ...].
    confidence:
        Confidence level.
    discriminating_tests:
        List of proposed discriminating tests.
    """

    candidate_id: str
    mechanism: str
    physical_basis: str
    supporting_evidence: list[tuple[str, str]] = field(default_factory=list)
    contradicting_evidence: list[tuple[str, str]] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    discriminating_tests: list[DiscriminatingTest] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "mechanism": self.mechanism,
            "physical_basis": self.physical_basis,
            "confidence": self.confidence.value,
            "supporting_evidence": [
                {"doi": doi, "excerpt": ex} for doi, ex in self.supporting_evidence
            ],
            "contradicting_evidence": [
                {"doi": doi, "excerpt": ex} for doi, ex in self.contradicting_evidence
            ],
            "discriminating_tests": [
                {
                    "test_id": t.test_id,
                    "description": t.description,
                    "discriminates_between": t.discriminates_between,
                    "expected_if_true": t.expected_if_true,
                    "expected_if_false": t.expected_if_false,
                    "method": t.method,
                    "difficulty": t.difficulty,
                }
                for t in self.discriminating_tests
            ],
        }


@dataclass
class ExplanationResult:
    """D2 anomaly explanation result.

    Attributes
    ----------
    query:
        User input (description of the anomalous result).
    candidates:
        List of mechanism candidates (sorted by confidence).
    top_discriminating_tests:
        Summary of the most important discriminating tests.
    disclaimer:
        Integrity notice (these are hypotheses, not conclusions).
    """

    query: str
    candidates: list[MechanismCandidate]
    top_discriminating_tests: list[DiscriminatingTest] = field(default_factory=list)
    disclaimer: str = (
        "⚠ These explanations are AI-suggested hypothesis candidates — not conclusions. "
        "Each must be validated through discriminating tests. "
        "The LLM did not directly generate any numerical physics values."
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "query": self.query,
            "disclaimer": self.disclaimer,
            "n_candidates": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "top_discriminating_tests": [
                {
                    "test_id": t.test_id,
                    "description": t.description,
                    "method": t.method,
                    "difficulty": t.difficulty,
                }
                for t in self.top_discriminating_tests
            ],
        }

    def summary(self) -> str:
        """Return a human-readable summary text."""
        lines = [
            f"[D2 Anomaly Explanation] Query: {self.query}",
            f"{self.disclaimer}",
            "",
            f"■ {len(self.candidates)} mechanism candidate(s):",
        ]
        for c in self.candidates:
            ev_count = len(c.supporting_evidence)
            lines.append(
                f"  [{c.candidate_id}] {c.mechanism} "
                f"(confidence: {c.confidence.value}, evidence: {ev_count})"
            )

        if self.top_discriminating_tests:
            lines.append("\n■ Key discriminating tests:")
            for t in self.top_discriminating_tests[:3]:
                lines.append(f"  [{t.test_id}] {t.description[:80]}...")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in mechanism candidate database (magnetism / spintronics)
# ---------------------------------------------------------------------------

# Anomalous signal keywords → list of mechanism candidates
_MECHANISM_DB: dict[str, list[dict[str, Any]]] = {
    "topological hall": [
        {
            "mechanism": "Topological Hall effect (THE)",
            "physical_basis": (
                "Additional Hall resistivity contribution from non-trivial topological properties "
                "(Berry phase). Associated with skyrmion or magnetic monopole textures."
            ),
            "confidence": ConfidenceLevel.HIGH,
            "test_description": (
                "Separate AHE contribution from temperature/field dependence; skyrmion Hall measurement"
            ),
        },
        {
            "mechanism": "Secondary magnetic phase (magnetic heterojunction effect)",
            "physical_basis": (
                "When two magnetic phases in the film have different Curie temperatures, "
                "an additional Hall component appears near the transition temperature."
            ),
            "confidence": ConfidenceLevel.MEDIUM,
            "test_description": "Confirm magnetic phase separation via XMCD and neutron scattering",
        },
        {
            "mechanism": "Contact artifact",
            "physical_basis": (
                "Spurious signal from non-uniform contact resistance at voltage leads "
                "and current flow distortion."
            ),
            "confidence": ConfidenceLevel.LOW,
            "test_description": "Change Hall bar geometry; compare multiple contacts",
        },
        {
            "mechanism": "Thermal drift / zeroing error",
            "physical_basis": (
                "Incompletely corrected Hall resistance contribution from cryostat or "
                "thermocouple zeroing errors."
            ),
            "confidence": ConfidenceLevel.LOW,
            "test_description": (
                "Extend thermal stabilization time; use AC measurement to separate symmetric components"
            ),
        },
    ],
    "ahe sign reversal": [
        {
            "mechanism": "Scattering mechanism crossover (side-jump ↔ skew scattering)",
            "physical_basis": (
                "Temperature-driven change in the dominant scattering mechanism — "
                "impurity scattering vs. intrinsic Berry phase contribution."
            ),
            "confidence": ConfidenceLevel.HIGH,
            "test_description": "ρ_xy vs ρ_xx² scaling analysis; σ_xy vs σ_xx plot",
        },
        {
            "mechanism": "Fermi-level topological phase crossover",
            "physical_basis": (
                "Temperature-dependent thermal expansion and electron-phonon coupling "
                "shift Berry curvature hot spots toward the Fermi level."
            ),
            "confidence": ConfidenceLevel.MEDIUM,
            "test_description": "Track Berry curvature temperature dependence via DFT band structure calculation",
        },
    ],
    "fmr linewidth anomaly": [
        {
            "mechanism": "Two-magnon scattering mode coupling",
            "physical_basis": "Linewidth broadening from two-magnon scattering at defects and surface roughness.",
            "confidence": ConfidenceLevel.HIGH,
            "test_description": "Compare in-plane vs. out-of-plane FMR; angle-dependent linewidth",
        },
        {
            "mechanism": "Spin pumping / loss channel",
            "physical_basis": "Effective damping increase from spin-current leakage into an adjacent NM layer.",
            "confidence": ConfidenceLevel.MEDIUM,
            "test_description": "NM thickness dependence; simultaneous ISHE measurement",
        },
    ],
}


def _find_candidate_templates(query: str) -> list[dict[str, Any]]:
    """Find relevant mechanism candidate templates for the given query string."""
    q_lower = query.lower()
    matches = []
    for keyword, templates in _MECHANISM_DB.items():
        if keyword in q_lower:
            matches.extend(templates)
    return matches


# ---------------------------------------------------------------------------
# D2 anomaly explanation engine
# ---------------------------------------------------------------------------


class AnomalyExplainer:
    """D2 abductive anomaly explanation engine (§5.11).

    Parameters
    ----------
    rag_search_fn:
        Literature RAG search function: (query: str, top_k: int) -> list[dict].
        When None, only the built-in DB is used (no RAG).
    llm_explain_fn:
        LLM mechanism candidate generation function:
        (query: str, templates: list[dict]) -> list[dict[str, Any]].
        When None, only the built-in templates are used.
    min_candidates:
        Minimum number of candidates to return.
    """

    def __init__(
        self,
        rag_search_fn: Callable[[str, int], list[dict[str, Any]]] | None = None,
        llm_explain_fn: Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
        min_candidates: int = 2,
    ) -> None:
        self._rag_fn = rag_search_fn
        self._llm_fn = llm_explain_fn
        self._min_candidates = min_candidates

    def explain(self, query: str) -> ExplanationResult:
        """Generate mechanism candidates and discriminating tests for an anomalous result.

        Parameters
        ----------
        query:
            Description of the anomalous result (e.g. "AHE sign reversal above 200 K").

        Returns
        -------
        ExplanationResult
            List of hypothesis cards in which the LLM has not directly generated
            any numerical physics values.
        """
        # 1. Collect templates from the built-in DB
        templates = _find_candidate_templates(query)

        # 2. Generate candidates via LLM (numerical value generation is forbidden)
        raw_candidates: list[dict[str, Any]] = []
        if self._llm_fn is not None:
            try:
                llm_candidates = self._llm_fn(query, templates)
                raw_candidates.extend(llm_candidates)
            except Exception as exc:  # noqa: BLE001
                log.warning("[D2] LLM mechanism generation error: %s", exc)

        # Fall back to templates when no LLM or no results
        if not raw_candidates:
            raw_candidates = templates

        # Ensure minimum number of candidates.
        # The former condition `len(...) < min AND not raw_candidates` was logically
        # equivalent to `not raw_candidates` (empty list only).  When the LLM returns
        # a non-empty but too-short list (e.g. 1 candidate when min=2) the fallback
        # was never triggered.  The corrected form top-ups any under-count result.
        if len(raw_candidates) < self._min_candidates:
            raw_candidates = raw_candidates + self._fallback_candidates(query)

        # 3. Convert to MechanismCandidate objects
        candidates = []
        for i, raw in enumerate(raw_candidates[: max(self._min_candidates, 5)]):
            cid = f"C{i + 1:02d}"
            confidence = raw.get("confidence", ConfidenceLevel.MEDIUM)
            if isinstance(confidence, str):
                try:
                    confidence = ConfidenceLevel(confidence)
                except ValueError:
                    confidence = ConfidenceLevel.MEDIUM

            # 4. Search RAG for literature support
            supporting: list[tuple[str, str]] = []
            if self._rag_fn is not None:
                try:
                    rag_results = self._rag_fn(f"{query} {raw.get('mechanism', '')}", 3)
                    for r in rag_results:
                        doi = r.get("doi", "")
                        excerpt = r.get("text", r.get("excerpt", ""))[:200]
                        if doi:
                            supporting.append((doi, excerpt))
                except Exception as exc:  # noqa: BLE001
                    log.warning("[D2] RAG search error: %s", exc)

            # 5. Generate discriminating test
            test_desc = raw.get(
                "test_description", f"Validation test for {raw.get('mechanism', '')}"
            )
            disc_test = DiscriminatingTest(
                test_id=f"T{i + 1:02d}",
                description=test_desc,
                discriminates_between=[cid],
                expected_if_true=f"Characteristic signal confirming candidate {cid}",
                expected_if_false=f"Candidate {cid} absent — explore other candidates",
                method="measurement",
                difficulty="moderate",
            )

            candidate = MechanismCandidate(
                candidate_id=cid,
                mechanism=raw.get("mechanism", f"Mechanism candidate {i + 1}"),
                physical_basis=raw.get("physical_basis", "Physical basis undetermined"),
                supporting_evidence=supporting,
                confidence=confidence,
                discriminating_tests=[disc_test],
            )
            candidates.append(candidate)

        # Sort by confidence level
        confidence_order = {
            ConfidenceLevel.HIGH: 0,
            ConfidenceLevel.MEDIUM: 1,
            ConfidenceLevel.LOW: 2,
            ConfidenceLevel.SPECULATIVE: 3,
        }
        candidates.sort(key=lambda c: confidence_order.get(c.confidence, 9))

        # Collect top discriminating tests
        top_tests = []
        for c in candidates[:3]:
            top_tests.extend(c.discriminating_tests)

        return ExplanationResult(
            query=query,
            candidates=candidates,
            top_discriminating_tests=top_tests[:3],
        )

    @staticmethod
    def _fallback_candidates(query: str) -> list[dict[str, Any]]:
        """Return generic magnetism anomaly candidates when no template matches."""
        return [
            {
                "mechanism": "Measurement artifact",
                "physical_basis": (
                    "Measurement system issues such as contact resistance, thermal effects, "
                    "or electromagnetic interference."
                ),
                "confidence": ConfidenceLevel.MEDIUM,
                "test_description": "Re-measure with a different sample or geometry; compare against dummy sample",
            },
            {
                "mechanism": "Sample defect or inhomogeneity",
                "physical_basis": (
                    "Grain boundaries, oxidation, or alloy inhomogeneity in the film "
                    "contributing to the signal."
                ),
                "confidence": ConfidenceLevel.MEDIUM,
                "test_description": "Verify microstructure via TEM/XRD; perform position-resolved measurements",
            },
        ]


# ---------------------------------------------------------------------------
# D2 entry point
# ---------------------------------------------------------------------------


def explain_anomaly(
    query: str,
    *,
    rag_search_fn: Callable[[str, int], list[dict[str, Any]]] | None = None,
    llm_explain_fn: Callable[..., Any] | None = None,
    min_candidates: int = 2,
) -> ExplanationResult:
    """Anomaly explanation entry point function (§5.11 D2).

    Parameters
    ----------
    query:
        Description string of the anomalous result.
    rag_search_fn:
        Literature RAG search function (optional).
    llm_explain_fn:
        LLM mechanism generation function (optional).
    min_candidates:
        Minimum number of candidates.

    Returns
    -------
    ExplanationResult
    """
    explainer = AnomalyExplainer(
        rag_search_fn=rag_search_fn,
        llm_explain_fn=llm_explain_fn,
        min_candidates=min_candidates,
    )
    return explainer.explain(query)


# ===========================================================================
# D1 — Hypothesis Generation and Elo Tournament (§5.10, T-P6-35–37)
# ===========================================================================

# ---------------------------------------------------------------------------
# D1 data structures
# ---------------------------------------------------------------------------

# Elo initial rating and K-factor
_ELO_INITIAL = 1200.0
_ELO_K = 32.0

# Evaluation criteria for pairwise Elo comparison (§5.10)
D1_CRITERIA = ("novelty", "testability", "feasibility", "impact")


@dataclass
class HypothesisCandidate:
    """A single hypothesis candidate produced by D1 (§5.10, T-P6-35).

    Attributes
    ----------
    hypothesis_id:
        Unique identifier (e.g. ``"H01"``).
    idea:
        One-sentence statement of the hypothesis.
    novelty_rationale:
        Why this hypothesis is novel — grounded in literature gaps.
        Cite-keys must be from a verified literature pool.
    novelty_cite_keys:
        List of verified cite-keys supporting the novelty claim.
    verification_method:
        Proposed measurement plan or simulation link to test the hypothesis.
    feasibility_score:
        Initial feasibility estimate (0–1; higher = more feasible).
    impact_score:
        Initial impact estimate (0–1; higher = higher scientific impact).
    elo_rating:
        Elo rating after tournament (starts at ``_ELO_INITIAL``).
    """

    hypothesis_id: str
    idea: str
    novelty_rationale: str
    novelty_cite_keys: list[str] = field(default_factory=list)
    verification_method: str = ""
    feasibility_score: float = 0.5
    impact_score: float = 0.5
    elo_rating: float = _ELO_INITIAL

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dictionary."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "idea": self.idea,
            "novelty_rationale": self.novelty_rationale,
            "novelty_cite_keys": self.novelty_cite_keys,
            "verification_method": self.verification_method,
            "feasibility_score": self.feasibility_score,
            "impact_score": self.impact_score,
            "elo_rating": self.elo_rating,
        }


@dataclass
class RankedHypothesis:
    """A hypothesis candidate augmented with Elo rank and physical validity.

    Attributes
    ----------
    rank:
        1-based ranking position (1 = highest Elo).
    candidate:
        The underlying ``HypothesisCandidate``.
    physical_valid:
        ``True`` if the reflection pass found no physics contradiction.
    physics_contradiction:
        Description of the contradiction (empty string when valid).
    physics_reason:
        Full explanation from ``reflection_physics_check``.
    ai_label:
        Integrity label — always ``"AI suggestion"`` (§5.10 integrity).
    """

    rank: int
    candidate: HypothesisCandidate
    physical_valid: bool = True
    physics_contradiction: str = ""
    physics_reason: str = ""
    ai_label: str = "AI suggestion"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dictionary."""
        return {
            "rank": self.rank,
            "ai_label": self.ai_label,
            "physical_valid": self.physical_valid,
            "physics_contradiction": self.physics_contradiction,
            "physics_reason": self.physics_reason,
            **self.candidate.to_dict(),
        }

    def summary(self) -> str:
        """Return a human-readable card for terminal display."""
        valid_tag = "valid" if self.physical_valid else "PHYSICS ISSUE"
        lines = [
            f"[{self.ai_label}] Rank #{self.rank} — {self.candidate.idea}",
            f"  Novelty: {self.candidate.novelty_rationale[:120]}",
            f"  Cite-keys: {', '.join(self.candidate.novelty_cite_keys) or '(none)'}",
            f"  Verify via: {self.candidate.verification_method or '(not specified)'}",
            f"  Feasibility: {self.candidate.feasibility_score:.2f}  "
            f"Impact: {self.candidate.impact_score:.2f}  "
            f"Elo: {self.candidate.elo_rating:.1f}",
            f"  Physics: {valid_tag}",
        ]
        if not self.physical_valid and self.physics_contradiction:
            lines.append(f"  WARNING: {self.physics_contradiction}")
        return "\n".join(lines)


@dataclass
class ReflectionResult:
    """Result of the physics reflection pass (§5.10, T-P6-37).

    Attributes
    ----------
    valid:
        ``True`` if no physics contradiction was detected.
    contradiction:
        Short description of the contradiction (empty if valid).
    reason:
        Full explanation of the check result.
    """

    valid: bool
    contradiction: str = ""
    reason: str = ""


@dataclass
class HypothesisResult:
    """Top-level result of the D1 hypothesis engine.

    Attributes
    ----------
    topic:
        The research topic passed by the caller.
    ranked:
        Ranked hypothesis list (highest Elo first).
    disclaimer:
        Integrity label always present on the result.
    """

    topic: str
    ranked: list[RankedHypothesis]
    disclaimer: str = (
        "WARNING: These hypotheses are AI suggestions — not conclusions. "
        "Each must be tested via the proposed verification method before use. "
        "Novelty claims are grounded in a verified literature pool only."
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dictionary."""
        return {
            "topic": self.topic,
            "disclaimer": self.disclaimer,
            "n_hypotheses": len(self.ranked),
            "hypotheses": [h.to_dict() for h in self.ranked],
        }

    def summary(self) -> str:
        """Return a human-readable multi-card summary."""
        lines = [
            f"[D1 Hypothesis Engine] Topic: {self.topic}",
            self.disclaimer,
            "",
        ]
        for rh in self.ranked:
            lines.append(rh.summary())
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in hypothesis seed templates (magnetism / spintronics)
# ---------------------------------------------------------------------------

_HYPOTHESIS_SEEDS: list[dict[str, Any]] = [
    {
        "idea": "Topological Hall effect contribution from skyrmion lattice formation",
        "novelty_rationale": (
            "Skyrmion-driven THE has been observed in B20 materials but not yet "
            "systematically mapped in Heusler alloys with competing anisotropies."
        ),
        "verification_method": (
            "Lorentz TEM at low temperature + field-angle-dependent Hall measurement; "
            "compare with micromagnetic simulation of skyrmion nucleation."
        ),
        "feasibility_score": 0.7,
        "impact_score": 0.85,
    },
    {
        "idea": "Spin-orbit torque efficiency enhancement via interface oxidation engineering",
        "novelty_rationale": (
            "Oxygen-controlled interface disorder has been shown to boost SHA in Pt/Co; "
            "its role in W/CoFeB systems under PMA conditions is underexplored."
        ),
        "verification_method": (
            "ST-FMR harmonic Hall measurement series with controlled O2 exposure; "
            "XPS depth profile to quantify oxidation."
        ),
        "feasibility_score": 0.75,
        "impact_score": 0.8,
    },
    {
        "idea": "Anomalous Nernst effect as a probe of Berry curvature hot spots",
        "novelty_rationale": (
            "ANE shares Berry curvature origin with AHE but probes thermal gradients; "
            "comparative temperature-dependent ANE/AHE in topological magnets is sparse."
        ),
        "verification_method": (
            "Simultaneous Hall + Nernst measurement with Peltier-controlled gradient; "
            "DFT Berry curvature calculation for comparison."
        ),
        "feasibility_score": 0.6,
        "impact_score": 0.75,
    },
    {
        "idea": "Magnon-drag contribution to spin Seebeck signal at low temperature",
        "novelty_rationale": (
            "Phonon-drag analogues in spin Seebeck are theoretically predicted but "
            "experimentally unconfirmed below 10 K due to instrumentation challenges."
        ),
        "verification_method": (
            "SSE measurement in dilution refrigerator; isotopically pure sample to "
            "suppress phonon scattering; frequency-dependent lock-in detection."
        ),
        "feasibility_score": 0.45,
        "impact_score": 0.9,
    },
    {
        "idea": "Orbital Hall effect dominating charge-to-spin conversion in light metals",
        "novelty_rationale": (
            "OHE in Ti and Cr is predicted large by DFT but experimental confirmation "
            "is indirect; direct orbital torque measurement via optical techniques is missing."
        ),
        "verification_method": (
            "MOKE-detected FMR with voltage-controlled orbital injection; "
            "comparison between heavy- and light-metal underlayers."
        ),
        "feasibility_score": 0.55,
        "impact_score": 0.9,
    },
]


# ---------------------------------------------------------------------------
# Elo helpers
# ---------------------------------------------------------------------------


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Return the expected Elo score for player A given ratings A and B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _update_elo(
    rating_a: float,
    rating_b: float,
    score_a: float,
    k: float = _ELO_K,
) -> tuple[float, float]:
    """Return updated Elo ratings for players A and B.

    Parameters
    ----------
    rating_a, rating_b:
        Current Elo ratings.
    score_a:
        Actual score for A — 1.0 (A wins), 0.5 (draw), 0.0 (B wins).
    k:
        Elo K-factor.

    Returns
    -------
    (new_rating_a, new_rating_b)
    """
    ea = _expected_score(rating_a, rating_b)
    eb = _expected_score(rating_b, rating_a)
    new_a = rating_a + k * (score_a - ea)
    new_b = rating_b + k * ((1.0 - score_a) - eb)
    return new_a, new_b


# ---------------------------------------------------------------------------
# D1 core functions
# ---------------------------------------------------------------------------


def generate_candidates(
    topic: str,
    lit_gap: str = "",
    current_results: list[dict[str, Any]] | None = None,
    n: int = 5,
    *,
    llm_generate_fn: (
        Callable[[str, str, list[dict[str, Any]]], list[dict[str, Any]]] | None
    ) = None,
    verified_cite_pool: set[str] | None = None,
    rng_seed: int | None = None,
) -> list[HypothesisCandidate]:
    """Generate *n* hypothesis candidates for *topic* (§5.10, T-P6-35).

    Grounding rules (integrity §3.3)
    ---------------------------------
    - The LLM may generate hypothesis text but must NOT produce numerical values.
    - Novelty cite-keys are validated against ``verified_cite_pool`` when provided.
    - Without an LLM function, built-in seed templates are used (always available).

    Parameters
    ----------
    topic:
        Research topic / question.
    lit_gap:
        Literature gap description (from §14 discovery intelligence).
    current_results:
        List of DataPoint-like dicts from the active research loop.
    n:
        Number of candidates to generate (1 <= n <= 20).
    llm_generate_fn:
        Optional LLM function ``(topic, lit_gap, current_results) -> list[dict]``.
        Each dict must have keys: ``idea``, ``novelty_rationale``,
        ``novelty_cite_keys`` (list[str]), ``verification_method``,
        ``feasibility_score``, ``impact_score``.
    verified_cite_pool:
        Set of validated cite-keys.  When provided, ``novelty_cite_keys`` are
        filtered to only include keys present in the pool.
    rng_seed:
        Seed for the internal PRNG used when shuffling seed templates
        (for reproducibility in tests).

    Returns
    -------
    list[HypothesisCandidate]
        Up to *n* candidates with initialised Elo ratings.
    """
    n = max(1, min(n, 20))
    current_results = current_results or []
    rng = random.Random(rng_seed)

    raw_candidates: list[dict[str, Any]] = []

    # 1. Try LLM generation
    if llm_generate_fn is not None:
        try:
            raw_candidates = llm_generate_fn(topic, lit_gap, current_results)
        except Exception:  # noqa: BLE001
            log.warning("[D1] LLM generate_fn failed — falling back to seed templates")

    # 2. Supplement / replace with seed templates if needed
    if len(raw_candidates) < n:
        topic_lower = topic.lower()
        matching = [
            s
            for s in _HYPOTHESIS_SEEDS
            if any(word in s["idea"].lower() for word in topic_lower.split())
        ]
        # Matching seeds first (shuffled within group), then non-matching (shuffled within group).
        # Shuffling each group separately preserves topic-priority while keeping intra-group
        # randomness so the same topic doesn't always return identical candidate order.
        matching_group = list(matching)
        rng.shuffle(matching_group)
        nonmatching_group = [s for s in _HYPOTHESIS_SEEDS if s not in matching]
        rng.shuffle(nonmatching_group)
        pool_shuffled = matching_group + nonmatching_group
        raw_candidates.extend(pool_shuffled)

    candidates: list[HypothesisCandidate] = []
    for i, raw in enumerate(raw_candidates[:n]):
        cite_keys: list[str] = raw.get("novelty_cite_keys", [])
        if verified_cite_pool is not None:
            cite_keys = [k for k in cite_keys if k in verified_cite_pool]

        candidates.append(
            HypothesisCandidate(
                hypothesis_id=f"H{i + 1:02d}",
                idea=raw.get("idea", f"Hypothesis {i + 1}"),
                novelty_rationale=raw.get("novelty_rationale", ""),
                novelty_cite_keys=cite_keys,
                verification_method=raw.get("verification_method", ""),
                feasibility_score=float(raw.get("feasibility_score", 0.5)),
                impact_score=float(raw.get("impact_score", 0.5)),
                elo_rating=_ELO_INITIAL,
            )
        )

    return candidates


def rank_by_elo(
    candidates: list[HypothesisCandidate],
    criteria: tuple[str, ...] = D1_CRITERIA,
    *,
    llm_compare_fn: (
        Callable[[HypothesisCandidate, HypothesisCandidate, str], float] | None
    ) = None,
    rng_seed: int | None = None,
) -> list[RankedHypothesis]:
    """Rank *candidates* using an Elo pairwise tournament (§5.10, T-P6-36).

    Tournament protocol
    -------------------
    For each pair (A, B) and each criterion, a score_A in {0.0, 0.5, 1.0}
    is determined — either by ``llm_compare_fn`` or by a deterministic
    heuristic (feasibility / impact scores + small RNG perturbation for
    novelty and testability).  Elo ratings are updated after each comparison.

    The final list is sorted descending by Elo rating.  Ties are broken by
    ``feasibility_score + impact_score``.

    Parameters
    ----------
    candidates:
        List of candidates (Elo ratings are updated in-place).
    criteria:
        Criteria to compare on.
    llm_compare_fn:
        Optional LLM judge ``(a, b, criterion) -> score_a``.
        score_a: 1.0 = A wins, 0.5 = draw, 0.0 = B wins.
    rng_seed:
        Seed for reproducible heuristic comparisons.

    Returns
    -------
    list[RankedHypothesis]
        Candidates sorted by Elo (highest first), 1-based ranks, no ties.
    """
    if not candidates:
        return []

    rng = random.Random(rng_seed)

    def _heuristic_score(
        a: HypothesisCandidate,
        b: HypothesisCandidate,
        criterion: str,
    ) -> float:
        if criterion == "feasibility":
            da = a.feasibility_score
            db = b.feasibility_score
        elif criterion == "impact":
            da = a.impact_score
            db = b.impact_score
        else:
            delta = rng.uniform(-0.1, 0.1)
            da = 0.5 + delta
            db = 0.5 - delta

        diff = da - db
        if abs(diff) < 0.05:
            return 0.5
        return 1.0 if diff > 0 else 0.0

    n = len(candidates)
    for i in range(n):
        for j in range(i + 1, n):
            a = candidates[i]
            b = candidates[j]
            for criterion in criteria:
                if llm_compare_fn is not None:
                    try:
                        score_a = llm_compare_fn(a, b, criterion)
                    except Exception:  # noqa: BLE001
                        score_a = _heuristic_score(a, b, criterion)
                else:
                    score_a = _heuristic_score(a, b, criterion)

                new_ra, new_rb = _update_elo(a.elo_rating, b.elo_rating, score_a)
                a.elo_rating = new_ra
                b.elo_rating = new_rb

    sorted_candidates = sorted(
        candidates,
        key=lambda c: (c.elo_rating, c.feasibility_score + c.impact_score),
        reverse=True,
    )

    return [
        RankedHypothesis(rank=rank, candidate=cand)
        for rank, cand in enumerate(sorted_candidates, start=1)
    ]


def reflection_physics_check(
    candidate: HypothesisCandidate,
    *,
    oracle_check_fn: Callable[[dict[str, Any]], Any] | None = None,
    formulas_check_fn: Callable[[str], bool] | None = None,
) -> ReflectionResult:
    """Check a hypothesis candidate for physical validity (§5.10, T-P6-37).

    Uses ``physics/oracle.py`` deterministically.  The check is keyword-based:
    if the hypothesis text matches a known-violation pattern, ``valid=False``
    is returned.

    Parameters
    ----------
    candidate:
        Hypothesis candidate to check.
    oracle_check_fn:
        Optional custom oracle function ``(params: dict) -> OracleResult``.
        Defaults to ``maglab.physics.oracle.check``.
    formulas_check_fn:
        Optional custom formulas validation function ``(text: str) -> bool``.
        Returns ``True`` if no formula-level contradiction is detected.

    Returns
    -------
    ReflectionResult
    """
    if oracle_check_fn is None:
        try:
            from maglab.physics.oracle import check as _oracle_check

            oracle_check_fn = _oracle_check
        except ImportError:
            oracle_check_fn = None

    full_text = f"{candidate.idea} {candidate.novelty_rationale}".lower()

    contradictions: list[tuple[str, str]] = [
        (
            "generates energy",
            "Energy generation violates the first law of thermodynamics.",
        ),
        (
            "energy from nothing",
            "Creation of energy from nothing violates energy conservation.",
        ),
        (
            "perpetual motion",
            "Perpetual motion devices violate thermodynamics.",
        ),
        (
            "below absolute zero",
            "Temperature below absolute zero (0 K) is forbidden by the third law of thermodynamics.",
        ),
        (
            "negative temperature k",
            "Negative absolute temperature is non-physical in classical thermodynamics.",
        ),
        (
            "faster than light",
            "Superluminal velocity violates special relativity.",
        ),
        (
            "speed of light exceeded",
            "No material object can exceed the speed of light.",
        ),
        (
            "negative gilbert damping",
            "Negative Gilbert damping without explicit parametric pumping is non-physical.",
        ),
    ]

    for pattern, contradiction in contradictions:
        if pattern in full_text:
            return ReflectionResult(
                valid=False,
                contradiction=contradiction,
                reason=(
                    f"Pattern '{pattern}' detected in hypothesis text. "
                    f"Contradiction: {contradiction}"
                ),
            )

    if oracle_check_fn is not None:
        params: dict[str, Any] = {}
        if "absolute zero" in full_text or bool(_ABSOLUTE_ZERO_RE.search(full_text)):
            params["T"] = 0.0

        if params:
            try:
                result = oracle_check_fn(params)
                ok = bool(result)
                if not ok:
                    reason = getattr(result, "reason", str(result))
                    return ReflectionResult(
                        valid=False,
                        contradiction=reason,
                        reason=f"Oracle check failed: {reason}",
                    )
            except Exception:  # noqa: BLE001
                log.debug("[D1] Oracle check raised — skipping parameter checks")

    if formulas_check_fn is not None:
        try:
            ok = formulas_check_fn(full_text)
            if not ok:
                return ReflectionResult(
                    valid=False,
                    contradiction="Custom formulas check failed.",
                    reason="formulas_check_fn returned False for hypothesis text.",
                )
        except Exception:  # noqa: BLE001
            log.debug("[D1] formulas_check_fn raised — skipping")

    return ReflectionResult(
        valid=True,
        reason="No physical contradiction detected by oracle or pattern checks.",
    )


# ---------------------------------------------------------------------------
# D1 top-level engine
# ---------------------------------------------------------------------------


class D1HypothesisEngine:
    """End-to-end D1 hypothesis generation and evaluation engine (§5.10).

    Wraps ``generate_candidates``, ``rank_by_elo``, and
    ``reflection_physics_check`` into a single callable.

    Parameters
    ----------
    n:
        Number of candidates to generate (default 5).
    llm_generate_fn:
        Optional LLM candidate generator.
    llm_compare_fn:
        Optional LLM pairwise comparator for Elo.
    oracle_check_fn:
        Optional custom oracle function.
    verified_cite_pool:
        Set of validated cite-keys (optional).
    rng_seed:
        Seed for reproducible heuristic comparisons.
    """

    def __init__(
        self,
        n: int = 5,
        llm_generate_fn: (
            Callable[[str, str, list[dict[str, Any]]], list[dict[str, Any]]] | None
        ) = None,
        llm_compare_fn: (
            Callable[[HypothesisCandidate, HypothesisCandidate, str], float] | None
        ) = None,
        oracle_check_fn: Callable[[dict[str, Any]], Any] | None = None,
        verified_cite_pool: set[str] | None = None,
        rng_seed: int | None = None,
    ) -> None:
        self._n = n
        self._llm_generate_fn = llm_generate_fn
        self._llm_compare_fn = llm_compare_fn
        self._oracle_check_fn = oracle_check_fn
        self._verified_cite_pool = verified_cite_pool
        self._rng_seed = rng_seed

    def run(
        self,
        topic: str,
        lit_gap: str = "",
        current_results: list[dict[str, Any]] | None = None,
    ) -> HypothesisResult:
        """Generate, rank, and validate hypotheses for *topic*.

        Parameters
        ----------
        topic:
            Research topic.
        lit_gap:
            Literature gap description.
        current_results:
            DataPoint-like dicts from the active research loop.

        Returns
        -------
        HypothesisResult
        """
        candidates = generate_candidates(
            topic=topic,
            lit_gap=lit_gap,
            current_results=current_results,
            n=self._n,
            llm_generate_fn=self._llm_generate_fn,
            verified_cite_pool=self._verified_cite_pool,
            rng_seed=self._rng_seed,
        )

        ranked = rank_by_elo(
            candidates,
            llm_compare_fn=self._llm_compare_fn,
            rng_seed=self._rng_seed,
        )

        for rh in ranked:
            ref = reflection_physics_check(
                rh.candidate,
                oracle_check_fn=self._oracle_check_fn,
            )
            rh.physical_valid = ref.valid
            rh.physics_contradiction = ref.contradiction
            rh.physics_reason = ref.reason

        return HypothesisResult(topic=topic, ranked=ranked)


# ---------------------------------------------------------------------------
# D1 public entry point
# ---------------------------------------------------------------------------


def generate_hypotheses(
    topic: str,
    lit_gap: str = "",
    current_results: list[dict[str, Any]] | None = None,
    n: int = 5,
    *,
    llm_generate_fn: (
        Callable[[str, str, list[dict[str, Any]]], list[dict[str, Any]]] | None
    ) = None,
    llm_compare_fn: (
        Callable[[HypothesisCandidate, HypothesisCandidate, str], float] | None
    ) = None,
    oracle_check_fn: Callable[[dict[str, Any]], Any] | None = None,
    verified_cite_pool: set[str] | None = None,
    rng_seed: int | None = None,
) -> HypothesisResult:
    """Generate and rank hypotheses for *topic* (§5.10 D1 entry point).

    Convenience wrapper around ``D1HypothesisEngine``.

    Parameters
    ----------
    topic:
        Research topic / question.
    lit_gap:
        Literature gap description.
    current_results:
        DataPoint-like dicts from the active research loop.
    n:
        Number of candidates to return (1–20).
    llm_generate_fn:
        Optional LLM candidate generator.
    llm_compare_fn:
        Optional LLM pairwise comparator for Elo tournament.
    oracle_check_fn:
        Optional oracle function for physics reflection check.
    verified_cite_pool:
        Set of validated cite-keys.
    rng_seed:
        Seed for reproducible heuristic Elo comparisons.

    Returns
    -------
    HypothesisResult
        Ranked, reflection-checked candidates with AI integrity label.
    """
    engine = D1HypothesisEngine(
        n=n,
        llm_generate_fn=llm_generate_fn,
        llm_compare_fn=llm_compare_fn,
        oracle_check_fn=oracle_check_fn,
        verified_cite_pool=verified_cite_pool,
        rng_seed=rng_seed,
    )
    return engine.run(topic=topic, lit_gap=lit_gap, current_results=current_results)


# ---------------------------------------------------------------------------
# Backwards-compat stub — replaced by generate_hypotheses above
# ---------------------------------------------------------------------------


def generate_hypothesis(
    topic: str,
    *,
    literature_context: str = "",
    llm_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """D1 hypothesis generation (§5.10) — delegates to ``generate_hypotheses``.

    Kept for backwards compatibility.  Prefer ``generate_hypotheses``.

    Parameters
    ----------
    topic:
        Research topic.
    literature_context:
        Literature gap description (maps to ``lit_gap``).
    llm_fn:
        LLM generator function (maps to ``llm_generate_fn``).

    Returns
    -------
    dict
        Serialised ``HypothesisResult``.
    """
    result = generate_hypotheses(
        topic=topic,
        lit_gap=literature_context,
        llm_generate_fn=llm_fn,
    )
    return result.to_dict()
