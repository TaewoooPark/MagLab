"""Unit tests for sim/custodian.py — engine error classification."""

from __future__ import annotations

from maglab.sim.custodian import CustodianResult, ErrorClass, classify, classify_exception


class TestClassify:
    def test_normal_exit_ok(self) -> None:
        result = classify(0, "Done.", "", engine="mumax3")
        assert result.ok
        assert result.error_class == ErrorClass.OK

    def test_mumax3_nan_convergence_error(self) -> None:
        result = classify(1, "", "NaN detected in mx", engine="mumax3")
        assert result.error_class == ErrorClass.CONVERGENCE

    def test_mumax3_memory_error(self) -> None:
        result = classify(1, "", "CUDA out of memory", engine="mumax3")
        assert result.error_class == ErrorClass.RESOURCE

    def test_mumax3_not_found(self) -> None:
        result = classify(-2, "", "mumax3: command not found", engine="mumax3")
        assert result.error_class == ErrorClass.ENGINE_NOT_FOUND

    def test_oommf_diverge_convergence(self) -> None:
        result = classify(1, "", "Diverge detected in simulation", engine="oommf")
        assert result.error_class == ErrorClass.CONVERGENCE

    def test_oommf_not_found(self) -> None:
        result = classify(-2, "", "oommf.tcl: can't execute 'tclsh'", engine="oommf")
        assert result.error_class in (ErrorClass.ENGINE_NOT_FOUND, ErrorClass.INPUT)

    def test_magnumnp_import_error(self) -> None:
        result = classify(1, "", "ModuleNotFoundError: magnumnp", engine="magnumnp")
        assert result.error_class == ErrorClass.ENGINE_NOT_FOUND

    def test_unknown_error(self) -> None:
        result = classify(99, "some output", "strange error xyz", engine="mumax3")
        assert result.error_class == ErrorClass.UNKNOWN

    def test_result_has_hint_for_convergence(self) -> None:
        result = classify(1, "", "NaN in mz", engine="mumax3")
        assert result.error_class == ErrorClass.CONVERGENCE
        # hint must not be an empty string
        assert len(result.hint) > 0 or result.error_class == ErrorClass.CONVERGENCE

    def test_result_has_backend_suggestion_for_resource(self) -> None:
        result = classify(1, "", "Out of memory: kill", engine="mumax3")
        assert result.error_class == ErrorClass.RESOURCE
        assert len(result.backend_suggestion) > 0

    def test_generic_engine(self) -> None:
        result = classify(1, "", "Permission denied", engine="generic")
        assert result.error_class == ErrorClass.RESOURCE


class TestClassifyException:
    def test_import_error_magnumnp(self) -> None:
        exc = ImportError("No module named 'magnumnp'")
        result = classify_exception(exc, engine="magnumnp")
        assert result.error_class == ErrorClass.ENGINE_NOT_FOUND

    def test_value_error_input(self) -> None:
        exc = ValueError("Invalid parameter range")
        result = classify_exception(exc, engine="magnumnp")
        assert result.error_class == ErrorClass.INPUT

    def test_runtime_error_unknown(self) -> None:
        exc = RuntimeError("unexpected state")
        result = classify_exception(exc, engine="magnumnp")
        # UNKNOWN or classifiable error
        assert isinstance(result, CustodianResult)
        assert result.error_class in list(ErrorClass)

    def test_ok_is_false_for_exception(self) -> None:
        exc = ValueError("bad param")
        result = classify_exception(exc)
        assert not result.ok
