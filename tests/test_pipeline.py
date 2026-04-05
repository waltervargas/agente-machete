"""Tests for the pipeline engine — the agentic loop."""

from returns.io import IOSuccess

from machete.context import AgentContext
from machete.decorators import agent, tool
from machete.llm.protocol import MockProvider
from machete.pipeline import AgentPipeline, get_last_response
from machete.types import (
    AgentConfig,
    LLMMessage,
    LLMResponse,
    Role,
    ToolCall,
)


def _make_ctx(
    provider: MockProvider,
    tools: dict | None = None,
    input_text: str = "hello",
) -> AgentContext:
    return AgentContext(
        config=AgentConfig(name="test"),
        provider=provider,
        tools=tools or {},
        messages=[LLMMessage(role=Role.USER, content=input_text)],
    )


class TestAgentPipeline:
    def test_simple_response(self) -> None:
        """Agent returns a text response with no tool calls."""
        provider = MockProvider(
            responses=[
                LLMResponse(
                    message=LLMMessage(role=Role.ASSISTANT, content="Hello back!"),
                    model="mock",
                    stop_reason="end_turn",
                ),
            ]
        )
        ctx = _make_ctx(provider)
        pipeline = AgentPipeline()
        result = pipeline.run(ctx)

        assert isinstance(result, IOSuccess)

    def test_tool_call_loop(self) -> None:
        """Agent calls a tool, gets result, then responds."""
        provider = MockProvider(
            responses=[
                # First: LLM requests tool call
                LLMResponse(
                    message=LLMMessage(
                        role=Role.ASSISTANT,
                        content="",
                        tool_calls=[ToolCall(id="tc1", name="add", arguments={"a": 2, "b": 3})],
                    ),
                    model="mock",
                    stop_reason="tool_use",
                ),
                # Second: LLM gives final answer after tool result
                LLMResponse(
                    message=LLMMessage(role=Role.ASSISTANT, content="The answer is 5."),
                    model="mock",
                    stop_reason="end_turn",
                ),
            ]
        )

        @tool(name="add", description="Add numbers")
        def add(a: int, b: int) -> int:
            return a + b

        ctx = _make_ctx(provider, tools={"add": add}, input_text="What is 2+3?")
        pipeline = AgentPipeline()
        result = pipeline.run(ctx)

        assert isinstance(result, IOSuccess)
        inner_ctx = result.unwrap()._inner_value  # type: ignore[union-attr]
        assert get_last_response(inner_ctx) == "The answer is 5."

    def test_tool_error_reported_to_llm(self) -> None:
        """When a tool raises, the error is sent back to the LLM (not pipeline failure)."""
        provider = MockProvider(
            responses=[
                LLMResponse(
                    message=LLMMessage(
                        role=Role.ASSISTANT,
                        content="",
                        tool_calls=[ToolCall(id="tc1", name="broken", arguments={})],
                    ),
                    model="mock",
                    stop_reason="tool_use",
                ),
                LLMResponse(
                    message=LLMMessage(role=Role.ASSISTANT, content="Sorry, the tool failed."),
                    model="mock",
                    stop_reason="end_turn",
                ),
            ]
        )

        @tool(name="broken", description="Always fails")
        def broken() -> str:
            raise RuntimeError("kaboom")

        ctx = _make_ctx(provider, tools={"broken": broken})
        pipeline = AgentPipeline()
        result = pipeline.run(ctx)

        # Pipeline should succeed — error is handled gracefully
        assert isinstance(result, IOSuccess)

    def test_max_iterations_respected(self) -> None:
        """Pipeline stops after max_iterations even if LLM keeps requesting tools."""

        # Provider always requests tools
        def always_tool_call(messages, tools):
            return LLMResponse(
                message=LLMMessage(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[ToolCall(id="tc", name="noop", arguments={})],
                ),
                model="mock",
                stop_reason="tool_use",
            )

        provider = MockProvider(response_fn=always_tool_call)

        @tool(name="noop", description="Does nothing")
        def noop() -> str:
            return "ok"

        ctx = AgentContext(
            config=AgentConfig(name="test", max_iterations=3),
            provider=provider,
            tools={"noop": noop},
            messages=[LLMMessage(role=Role.USER, content="loop forever")],
        )

        pipeline = AgentPipeline()
        result = pipeline.run(ctx)
        # Should terminate without error
        assert isinstance(result, IOSuccess)
        assert provider.call_count == 3


class TestRunFromAgent:
    def test_run_from_decorated_agent(self) -> None:
        @tool(name="greet", description="Greet someone")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        @agent(name="greeter", tools=[greet], system_prompt="Be friendly.")
        def greeter(q: str) -> str: ...

        provider = MockProvider(
            responses=[
                LLMResponse(
                    message=LLMMessage(role=Role.ASSISTANT, content="Hi there!"),
                    model="mock",
                    stop_reason="end_turn",
                ),
            ]
        )

        pipeline = AgentPipeline()
        result = pipeline.run_from_agent(greeter, provider, "Hello")
        assert isinstance(result, IOSuccess)
