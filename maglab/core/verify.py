"""Verification loop — determinism-first four-layer verification & Evaluator-Optimizer (§5.7).

Verification order:
  1. Schema check — JSON structure, required fields, types, ranges (deterministic, no LLM)
  2. Domain sanity — physics.oracle for physical range/unit checks (deterministic)
  3. Trust signal — classify status/warnings → on partial: re-run or upgrade model
  4. LLM evaluator — only when layers 1–3 are insufficient, and only for qualitative judgement

★ LLM judge is forbidden for quantitative, citation, or fitting verification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from maglab.physics import oracle as physics_oracle

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verification result data structures
# ---------------------------------------------------------------------------


class VerifyStatus(StrEnum):
    """Pass/fail status for each verification layer."""

    PASSED = "passed"
    """All layers passed."""
    PARTIAL = "partial"
    """Some warnings — re-run or model upgrade recommended."""
    FAILED = "failed"
    """Verification failed — orchestrator re-planning required."""


@dataclass
class VerifyResult:
    """Final result of the verification loop.

    Attributes
    ----------
    status:
        PASSED / PARTIAL / FAILED
    schema_ok:
        Whether the schema layer passed.
    oracle_ok:
        Whether the oracle layer passed.
    trust_ok:
        Whether the trust signal layer passed.
    violations:
        List of violation messages found.
    warnings:
        List of warning messages (basis for partial status).
    llm_evaluation:
        LLM evaluator opinion (used only for qualitative items; None if not run).
    """

    status: VerifyStatus
    schema_ok: bool = True
    oracle_ok: bool = True
    trust_ok: bool = True
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    llm_evaluation: str | None = None


# ---------------------------------------------------------------------------
# Layer 1 — Schema check
# ---------------------------------------------------------------------------

# Required fields in sub-agent output
_REQUIRED_FIELDS = {"status"}
_VALID_STATUSES = {"success", "partial", "failed"}


def _check_schema(result: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check the JSON schema of a sub-agent result.

    Returns
    -------
    (ok, violations)
    """
    violations: list[str] = []
    for field_name in _REQUIRED_FIELDS:
        if field_name not in result:
            violations.append(f"Required field missing: '{field_name}'")

    status = result.get("status")
    if status is not None and status not in _VALID_STATUSES:
        violations.append(f"status='{status}' is invalid. Allowed values: {_VALID_STATUSES}")

    # The warnings field must be a list when present
    warnings_val = result.get("warnings")
    if warnings_val is not None and not isinstance(warnings_val, list):
        violations.append(
            f"warnings field must be a list. Actual type: {type(warnings_val).__name__}"
        )

    return len(violations) == 0, violations


# ---------------------------------------------------------------------------
# Layer 2 — oracle domain sanity
# ---------------------------------------------------------------------------

# Keys to extract from the result dict as physics parameters
_PHYSICS_PARAM_KEYS = {
    "alpha",
    "Ms",
    "M",
    "T",
    "velocity",
    "A",
    "K",
    "T_C",
    "l_ex",
}


def _extract_physics_params(result: dict[str, Any]) -> dict[str, Any]:
    """Extract physics parameters from the result that can be checked by oracle."""
    params: dict[str, Any] = {}
    for key in _PHYSICS_PARAM_KEYS:
        if key in result:
            val = result[key]
            if isinstance(val, (int, float)):
                params[key] = float(val)
    # Also search a nested 'result' dict
    inner = result.get("result")
    if isinstance(inner, dict):
        for key in _PHYSICS_PARAM_KEYS:
            if key in inner and key not in params:
                val = inner[key]
                if isinstance(val, (int, float)):
                    params[key] = float(val)
    return params


def _check_oracle(result: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check physics parameters via physics.oracle.

    Returns
    -------
    (ok, violations)
    """
    params = _extract_physics_params(result)
    if not params:
        return True, []

    oracle_result = physics_oracle.check(params)
    if oracle_result.ok:
        return True, []
    return False, [f"Physics range violation ({oracle_result.param}): {oracle_result.reason}"]


# ---------------------------------------------------------------------------
# Layer 3 — Trust signal
# ---------------------------------------------------------------------------


def _check_trust(result: dict[str, Any]) -> tuple[bool, bool, list[str]]:
    """Classify trust using status and warnings signals.

    Returns
    -------
    (ok, is_partial, warnings)
      ok=True means not failed.
      is_partial=True means partial (re-run recommended).
    """
    status = result.get("status", "success")
    agent_warnings: list[str] = result.get("warnings") or []

    if status == "failed":
        return (
            False,
            False,
            [f"Sub-agent returned status=failed. warnings: {agent_warnings}"],
        )
    if status == "partial":
        msgs = [
            f"Sub-agent status=partial (re-run or model upgrade recommended). warnings: {agent_warnings}"
        ]
        return True, True, msgs
    return True, False, []


# ---------------------------------------------------------------------------
# Integrated verifier
# ---------------------------------------------------------------------------


class Verifier:
    """Four-layer verifier for sub-agent results.

    Parameters
    ----------
    max_eval_iterations:
        Maximum iterations for the Evaluator-Optimizer loop (when LLM judge is included).
    allow_llm_judge:
        When True, LLM judge is allowed for qualitative items.
        ★ Always False for quantitative, citation, or fitting verification.
    llm_judge_fn:
        LLM evaluation function (text_to_eval: str) -> str.
        When None, the LLM judge is disabled.
    """

    def __init__(
        self,
        max_eval_iterations: int = 3,
        allow_llm_judge: bool = False,
        llm_judge_fn: Any = None,
    ) -> None:
        self._max_iterations = max_eval_iterations
        self._allow_llm_judge = allow_llm_judge
        self._llm_judge_fn = llm_judge_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        result: dict[str, Any],
        *,
        is_quantitative: bool = True,
        context_hint: str = "",
    ) -> VerifyResult:
        """Verify a sub-agent result through four layers.

        Parameters
        ----------
        result:
            Sub-agent return dictionary.
        is_quantitative:
            When True, the LLM judge is disabled (quantitative, citation, fitting).
        context_hint:
            Additional context hint passed to the LLM evaluator (qualitative only).

        Returns
        -------
        VerifyResult
        """
        all_violations: list[str] = []
        all_warnings: list[str] = []
        llm_eval_text: str | None = None

        # --- Layer 1: schema ---
        schema_ok, schema_violations = _check_schema(result)
        all_violations.extend(schema_violations)

        # --- Layer 2: oracle ---
        oracle_ok, oracle_violations = _check_oracle(result)
        all_violations.extend(oracle_violations)

        # --- Layer 3: trust ---
        trust_ok, is_partial, trust_warnings = _check_trust(result)
        if not trust_ok:
            all_violations.extend(trust_warnings)
        else:
            all_warnings.extend(trust_warnings)

        # Aggregate layers 1–3 results
        layers_failed = (not schema_ok) or (not oracle_ok) or (not trust_ok)

        if layers_failed:
            return VerifyResult(
                status=VerifyStatus.FAILED,
                schema_ok=schema_ok,
                oracle_ok=oracle_ok,
                trust_ok=trust_ok,
                violations=all_violations,
                warnings=all_warnings,
            )

        # --- Layer 4: LLM evaluator (qualitative only) ---
        if not is_quantitative and self._allow_llm_judge and self._llm_judge_fn is not None:
            llm_eval_text = self._run_llm_judge(result, context_hint)
            if llm_eval_text and "REJECT" in llm_eval_text.upper():
                all_warnings.append(f"LLM evaluator warning: {llm_eval_text}")
                is_partial = True

        if is_partial:
            return VerifyResult(
                status=VerifyStatus.PARTIAL,
                schema_ok=schema_ok,
                oracle_ok=oracle_ok,
                trust_ok=trust_ok,
                violations=all_violations,
                warnings=all_warnings,
                llm_evaluation=llm_eval_text,
            )

        return VerifyResult(
            status=VerifyStatus.PASSED,
            schema_ok=schema_ok,
            oracle_ok=oracle_ok,
            trust_ok=trust_ok,
            violations=all_violations,
            warnings=all_warnings,
            llm_evaluation=llm_eval_text,
        )

    def verify_loop(
        self,
        result: dict[str, Any],
        generator_fn: Any,
        *,
        is_quantitative: bool = True,
        context_hint: str = "",
    ) -> tuple[VerifyResult, dict[str, Any]]:
        """Evaluator-Optimizer loop: generator <-> verifier, with maximum iteration cap.

        Parameters
        ----------
        result:
            Initial sub-agent result.
        generator_fn:
            Re-generation function: (prev_result, violations) -> new_result dict.
            When None, only a single verification pass is performed.
        is_quantitative:
            Whether this is quantitative (blocks LLM judge).
        context_hint:
            LLM evaluator context.

        Returns
        -------
        (final VerifyResult, final result dict)
        """
        current = result
        for iteration in range(self._max_iterations):
            vr = self.verify(current, is_quantitative=is_quantitative, context_hint=context_hint)
            if vr.status == VerifyStatus.PASSED:
                return vr, current
            if vr.status == VerifyStatus.FAILED or generator_fn is None:
                return vr, current
            # PARTIAL: attempt re-generation
            log.debug(
                "verify_loop iteration %d: status=%s, warnings=%s",
                iteration + 1,
                vr.status,
                vr.warnings,
            )
            try:
                current = generator_fn(current, vr.violations + vr.warnings)
            except Exception as exc:  # noqa: BLE001
                log.warning("generator_fn error: %s", exc)
                return vr, current
        # Maximum iterations reached
        final = self.verify(current, is_quantitative=is_quantitative, context_hint=context_hint)
        return final, current

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_llm_judge(self, result: dict[str, Any], context_hint: str) -> str | None:
        """Invoke the LLM evaluator (qualitative only)."""
        try:
            text = json.dumps(result, ensure_ascii=False, indent=2)
            prompt = (
                f"Evaluate the following sub-agent result. Judge only qualitative aspects.\n"
                f"Context: {context_hint}\n\nResult:\n{text}\n\n"
                "Output 'ACCEPT' if the result is sound, or 'REJECT: <reason>' if there is an issue."
            )
            return self._llm_judge_fn(prompt)
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM judge invocation error: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def quick_verify(result: dict[str, Any]) -> VerifyResult:
    """Perform a fast three-layer verification without an LLM judge.

    Use this for quantitative result verification (LLM judge disabled).
    """
    return Verifier(allow_llm_judge=False).verify(result, is_quantitative=True)
