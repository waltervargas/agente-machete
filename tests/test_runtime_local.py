"""Tests for the local runtime."""

import pytest
from machete.decorators import agent, tool
from machete.llm.protocol import MockProvider
from machete.runtime.local import run, run_result
from machete.types import LLMMessage, LLMResponse, Role, ToolCall
from returns.io import IOSuccess


@tool(name="add", description="Add two numbers")
def _add(a: int, b: int) -> int:
    return a + b


@agent(name="calc", tools=[_add], system_prompt="You are a calculator.")
def _calc(question: str) -> str:
    ...


class TestRun:
    def test_simple_run(self) -> None:
        provider = MockProvider(responses=[
            LLMResponse(
                message=LLMMessage(role=Role.ASSISTANT, content="42"),
                model="mock",
            ),
        ])
        result = run(_calc, "What is the answer?", provider=provider)
        assert result == "42"

    def test_run_with_mock_default(self) -> None:
        # Should use MockProvider by default and not crash
        result = run(_calc, "hello")
        assert isinstance(result, str)

    def test_run_raises_on_non_agent(self) -> None:
        def not_an_agent(q: str) -> str:
            return q

        with pytest.raises(ValueError, match="not an @agent"):
            run(not_an_agent, "hi")

    def test_run_with_tool_call(self) -> None:
        provider = MockProvider(responses=[
            LLMResponse(
                message=LLMMessage(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[ToolCall(id="tc1", name="add", arguments={"a": 2, "b": 3})],
                ),
                model="mock",
                stop_reason="tool_use",
            ),
            LLMResponse(
                message=LLMMessage(role=Role.ASSISTANT, content="5"),
                model="mock",
                stop_reason="end_turn",
            ),
        ])
        result = run(_calc, "2+3", provider=provider)
        assert result == "5"


class TestRunResult:
    def test_returns_agent_result(self) -> None:
        provider = MockProvider()
        result = run_result(_calc, "hello", provider=provider)
        assert isinstance(result, IOSuccess)
