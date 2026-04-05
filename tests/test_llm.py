"""Tests for LLM protocol and mock provider."""

from returns.io import IOSuccess

from machete.llm.protocol import LLMProvider, MockProvider
from machete.types import LLMMessage, LLMResponse, Role


class TestMockProvider:
    def test_satisfies_protocol(self) -> None:
        provider = MockProvider()
        assert isinstance(provider, LLMProvider)

    def test_default_response(self) -> None:
        provider = MockProvider()
        result = provider.complete([LLMMessage(role=Role.USER, content="hi")])
        assert isinstance(result, IOSuccess)

    def test_custom_responses(self) -> None:
        responses = [
            LLMResponse(
                message=LLMMessage(role=Role.ASSISTANT, content="first"),
                model="mock",
            ),
            LLMResponse(
                message=LLMMessage(role=Role.ASSISTANT, content="second"),
                model="mock",
            ),
        ]
        provider = MockProvider(responses=responses)

        r1 = provider.complete([LLMMessage(role=Role.USER, content="a")])
        r2 = provider.complete([LLMMessage(role=Role.USER, content="b")])

        assert isinstance(r1, IOSuccess)
        assert isinstance(r2, IOSuccess)
        assert provider.call_count == 2

    def test_response_function(self) -> None:
        def echo(messages, tools):
            last = messages[-1].content if messages else "empty"
            return LLMResponse(
                message=LLMMessage(role=Role.ASSISTANT, content=f"echo: {last}"),
                model="mock",
            )

        provider = MockProvider(response_fn=echo)
        result = provider.complete([LLMMessage(role=Role.USER, content="hello")])
        assert isinstance(result, IOSuccess)
