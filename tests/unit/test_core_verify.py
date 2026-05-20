"""verify.py unit tests — LLM mock, deterministic."""

from __future__ import annotations

from maglab.core.verify import (
    Verifier,
    VerifyStatus,
    _check_oracle,
    _check_schema,
    _check_trust,
    quick_verify,
)

# ---------------------------------------------------------------------------
# Layer 1 — Schema check
# ---------------------------------------------------------------------------


class TestSchemaCheck:
    def test_valid_success(self) -> None:
        ok, violations = _check_schema({"status": "success"})
        assert ok
        assert violations == []

    def test_missing_status(self) -> None:
        ok, violations = _check_schema({})
        assert not ok
        assert any("status" in v for v in violations)

    def test_invalid_status_value(self) -> None:
        ok, violations = _check_schema({"status": "unknown_value"})
        assert not ok

    def test_warnings_not_list(self) -> None:
        ok, violations = _check_schema({"status": "success", "warnings": "bad"})
        assert not ok
        assert any("warnings" in v for v in violations)

    def test_warnings_as_list(self) -> None:
        ok, violations = _check_schema({"status": "success", "warnings": ["w1"]})
        assert ok

    def test_partial_status(self) -> None:
        ok, violations = _check_schema({"status": "partial"})
        assert ok

    def test_failed_status(self) -> None:
        ok, violations = _check_schema({"status": "failed"})
        assert ok


# ---------------------------------------------------------------------------
# Layer 2 — oracle check
# ---------------------------------------------------------------------------


class TestOracleCheck:
    def test_no_physics_params(self) -> None:
        ok, violations = _check_oracle({"status": "success", "text": "hello"})
        assert ok
        assert violations == []

    def test_valid_alpha(self) -> None:
        ok, violations = _check_oracle({"status": "success", "alpha": 0.01})
        assert ok

    def test_invalid_alpha(self) -> None:
        ok, violations = _check_oracle({"status": "success", "alpha": 5.0})
        assert not ok
        assert violations

    def test_valid_temperature(self) -> None:
        ok, violations = _check_oracle({"T": 300.0})
        assert ok

    def test_invalid_temperature(self) -> None:
        ok, violations = _check_oracle({"T": -10.0})
        assert not ok

    def test_inner_result_dict(self) -> None:
        """Extract parameters from nested 'result' dict."""
        ok, violations = _check_oracle({"status": "success", "result": {"alpha": 5.0}})
        assert not ok

    def test_invalid_Ms(self) -> None:
        ok, violations = _check_oracle({"Ms": -1.0})
        assert not ok

    def test_valid_Ms(self) -> None:
        ok, violations = _check_oracle({"Ms": 8e5})
        assert ok


# ---------------------------------------------------------------------------
# Layer 3 — Trust signal
# ---------------------------------------------------------------------------


class TestTrustCheck:
    def test_success_no_warnings(self) -> None:
        ok, is_partial, msgs = _check_trust({"status": "success"})
        assert ok
        assert not is_partial

    def test_partial_status(self) -> None:
        ok, is_partial, msgs = _check_trust({"status": "partial"})
        assert ok
        assert is_partial
        assert msgs

    def test_failed_status(self) -> None:
        ok, is_partial, msgs = _check_trust({"status": "failed"})
        assert not ok
        assert msgs

    def test_with_agent_warnings(self) -> None:
        ok, is_partial, msgs = _check_trust({"status": "partial", "warnings": ["w1", "w2"]})
        assert ok
        assert is_partial
        # warnings must be reflected in the messages
        combined = " ".join(msgs)
        assert "w1" in combined or "partial" in combined


# ---------------------------------------------------------------------------
# Integrated Verifier
# ---------------------------------------------------------------------------


class TestVerifier:
    def test_passed(self) -> None:
        v = Verifier(allow_llm_judge=False)
        result = v.verify({"status": "success"})
        assert result.status == VerifyStatus.PASSED
        assert result.schema_ok
        assert result.oracle_ok
        assert result.trust_ok
        assert result.violations == []

    def test_schema_fail(self) -> None:
        v = Verifier(allow_llm_judge=False)
        result = v.verify({})
        assert result.status == VerifyStatus.FAILED
        assert not result.schema_ok

    def test_oracle_fail(self) -> None:
        v = Verifier(allow_llm_judge=False)
        result = v.verify({"status": "success", "alpha": 999.0})
        assert result.status == VerifyStatus.FAILED
        assert not result.oracle_ok

    def test_trust_partial(self) -> None:
        v = Verifier(allow_llm_judge=False)
        result = v.verify({"status": "partial"})
        assert result.status == VerifyStatus.PARTIAL
        assert result.trust_ok

    def test_trust_failed(self) -> None:
        v = Verifier(allow_llm_judge=False)
        result = v.verify({"status": "failed"})
        assert result.status == VerifyStatus.FAILED
        assert not result.trust_ok

    def test_llm_judge_disabled_for_quantitative(self) -> None:
        """Verify LLM judge is disabled for quantitative results."""
        judge_called = []

        def fake_judge(prompt: str) -> str:
            judge_called.append(prompt)
            return "ACCEPT"

        v = Verifier(allow_llm_judge=True, llm_judge_fn=fake_judge)
        # LLM judge must not be called when is_quantitative=True
        result = v.verify({"status": "success"}, is_quantitative=True)
        assert result.status == VerifyStatus.PASSED
        assert judge_called == []

    def test_llm_judge_for_qualitative(self) -> None:
        """Verify LLM judge is called for qualitative results."""
        judge_called = []

        def fake_judge(prompt: str) -> str:
            judge_called.append(prompt)
            return "ACCEPT"

        v = Verifier(allow_llm_judge=True, llm_judge_fn=fake_judge)
        result = v.verify({"status": "success"}, is_quantitative=False)
        assert result.status == VerifyStatus.PASSED
        assert len(judge_called) == 1

    def test_llm_judge_reject(self) -> None:
        """LLM judge REJECT → PARTIAL."""

        def fake_reject(prompt: str) -> str:
            return "REJECT: quality insufficient"

        v = Verifier(allow_llm_judge=True, llm_judge_fn=fake_reject)
        result = v.verify({"status": "success"}, is_quantitative=False)
        assert result.status == VerifyStatus.PARTIAL
        assert result.llm_evaluation is not None

    def test_no_llm_judge_fn(self) -> None:
        """LLM judge must not run when llm_judge_fn=None."""
        v = Verifier(allow_llm_judge=True, llm_judge_fn=None)
        result = v.verify({"status": "success"}, is_quantitative=False)
        assert result.status == VerifyStatus.PASSED
        assert result.llm_evaluation is None


# ---------------------------------------------------------------------------
# Evaluator-Optimizer loop
# ---------------------------------------------------------------------------


class TestVerifyLoop:
    def test_passes_on_first_try(self) -> None:
        v = Verifier(max_eval_iterations=3, allow_llm_judge=False)
        result = {"status": "success"}
        vr, final = v.verify_loop(result, generator_fn=None)
        assert vr.status == VerifyStatus.PASSED
        assert final == result

    def test_generator_called_on_partial(self) -> None:
        """generator is called on partial result."""
        calls = []

        def gen(prev: dict, violations: list) -> dict:
            calls.append(violations)
            return {"status": "success"}

        v = Verifier(max_eval_iterations=3, allow_llm_judge=False)
        initial = {"status": "partial"}
        vr, final = v.verify_loop(initial, generator_fn=gen)
        assert len(calls) >= 1
        assert final.get("status") == "success"

    def test_max_iterations_respected(self) -> None:
        """Maximum iteration count is respected."""
        calls = []

        def gen(prev: dict, violations: list) -> dict:
            calls.append(True)
            return {"status": "partial"}  # keep returning partial

        v = Verifier(max_eval_iterations=2, allow_llm_judge=False)
        vr, final = v.verify_loop({"status": "partial"}, generator_fn=gen)
        # calls must not exceed max_eval_iterations
        assert len(calls) <= 2

    def test_failed_stops_immediately(self) -> None:
        """FAILED result stops the loop immediately."""
        calls = []

        def gen(prev: dict, violations: list) -> dict:
            calls.append(True)
            return {"status": "success"}

        v = Verifier(max_eval_iterations=3, allow_llm_judge=False)
        vr, _ = v.verify_loop({"status": "failed"}, generator_fn=gen)
        assert vr.status == VerifyStatus.FAILED
        assert calls == []

    def test_no_generator(self) -> None:
        """Single verification pass when generator_fn=None."""
        v = Verifier(max_eval_iterations=3, allow_llm_judge=False)
        vr, final = v.verify_loop({"status": "partial"}, generator_fn=None)
        assert vr.status == VerifyStatus.PARTIAL


# ---------------------------------------------------------------------------
# quick_verify convenience function
# ---------------------------------------------------------------------------


class TestQuickVerify:
    def test_passes(self) -> None:
        result = quick_verify({"status": "success"})
        assert result.status == VerifyStatus.PASSED

    def test_fails_missing_status(self) -> None:
        result = quick_verify({"data": "x"})
        assert result.status == VerifyStatus.FAILED

    def test_oracle_applied(self) -> None:
        result = quick_verify({"status": "success", "T": -100.0})
        assert result.status == VerifyStatus.FAILED
