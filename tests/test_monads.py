"""Tests for the monadic layer."""

from returns.io import IOSuccess, IOFailure

from machete.monads import AgentResult, failure, flow_steps, safe_step, success
from machete.types import PipelineError


class TestSuccessFailure:
    def test_success_wraps_value(self) -> None:
        r = success(42)
        assert isinstance(r, IOSuccess)

    def test_failure_wraps_error(self) -> None:
        err = PipelineError(message="boom")
        r = failure(err)
        assert isinstance(r, IOFailure)


class TestSafeStep:
    def test_wraps_pure_function(self) -> None:
        @safe_step("double")
        def double(x: int) -> int:
            return x * 2

        result = double(5)
        assert isinstance(result, IOSuccess)

    def test_captures_exception_as_failure(self) -> None:
        @safe_step("explode")
        def explode() -> str:
            raise ValueError("kaboom")

        result = explode()
        assert isinstance(result, IOFailure)


class TestFlowSteps:
    def test_composes_successful_steps(self) -> None:
        def add_one(x: int) -> AgentResult[int]:
            return success(x + 1)

        def double(x: int) -> AgentResult[int]:
            return success(x * 2)

        result = flow_steps(success(5), add_one, double)
        assert isinstance(result, IOSuccess)

    def test_short_circuits_on_failure(self) -> None:
        def add_one(x: int) -> AgentResult[int]:
            return success(x + 1)

        def fail(_: int) -> AgentResult[int]:
            return failure(PipelineError(message="stopped"))

        def should_not_run(x: int) -> AgentResult[int]:
            raise AssertionError("This should not be called")

        result = flow_steps(success(5), add_one, fail, should_not_run)
        assert isinstance(result, IOFailure)
