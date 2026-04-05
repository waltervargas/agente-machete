"""LLM Provider Protocol and adapters.

CT mapping:
  - LLMProvider Protocol = typeclass (PEP 544 structural subtyping)
  - Each adapter is an *algebra* for that typeclass
  - @impure_safe wraps side-effecting calls into IOResult
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from returns.io import IOFailure, IOResult, IOSuccess, impure_safe

from machete.types import (
    AgentError,
    LLMError,
    LLMMessage,
    LLMResponse,
    Role,
    ToolCall,
)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol (typeclass) for LLM providers.

    Any object with a `complete` method matching this signature
    satisfies the protocol — no inheritance needed.
    """

    def complete(
        self,
        messages: Sequence[LLMMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        *,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> IOResult[LLMResponse, AgentError]: ...


# ---------------------------------------------------------------------------
# MockProvider — for testing and local dev without API keys
# ---------------------------------------------------------------------------

class MockProvider:
    """Deterministic mock provider for testing.

    Can be configured with canned responses or a response function.
    """

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        response_fn: Any | None = None,
    ) -> None:
        self._responses = list(responses) if responses else []
        self._response_fn = response_fn
        self._call_count = 0

    def complete(
        self,
        messages: Sequence[LLMMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        *,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> IOResult[LLMResponse, AgentError]:
        self._call_count += 1

        if self._response_fn:
            try:
                return IOSuccess(self._response_fn(messages, tools))
            except Exception as e:
                return IOFailure(LLMError(message=str(e), provider="mock"))

        if self._responses:
            return IOSuccess(self._responses.pop(0))

        # Default: return a simple text response
        return IOSuccess(
            LLMResponse(
                message=LLMMessage(
                    role=Role.ASSISTANT,
                    content="Mock response",
                ),
                model="mock",
                stop_reason="end_turn",
            )
        )

    @property
    def call_count(self) -> int:
        return self._call_count


# ---------------------------------------------------------------------------
# AnthropicProvider — wraps the Anthropic SDK
# ---------------------------------------------------------------------------

class AnthropicProvider:
    """Anthropic Claude adapter.

    Requires: pip install agente-machete[anthropic]
    """

    def __init__(self, api_key: str | None = None) -> None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: "
                "pip install agente-machete[anthropic]"
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        messages: Sequence[LLMMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        *,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> IOResult[LLMResponse, AgentError]:
        @impure_safe
        def _call() -> LLMResponse:
            # Convert to Anthropic message format
            system_msg = ""
            api_messages = []
            for msg in messages:
                if msg.role == Role.SYSTEM:
                    system_msg = msg.content
                elif msg.role == Role.TOOL:
                    api_messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }],
                    })
                elif msg.role == Role.ASSISTANT and msg.tool_calls:
                    content: list[dict[str, Any]] = []
                    if msg.content:
                        content.append({"type": "text", "text": msg.content})
                    for tc in msg.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                    api_messages.append({"role": "assistant", "content": content})
                else:
                    api_messages.append({
                        "role": msg.role.value,
                        "content": msg.content,
                    })

            # Build API kwargs
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": api_messages,
            }
            if system_msg:
                kwargs["system"] = system_msg
            if temperature > 0:
                kwargs["temperature"] = temperature

            # Convert tools to Anthropic format
            if tools:
                anthropic_tools = []
                for t in tools:
                    fn = t.get("function", {})
                    anthropic_tools.append({
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    })
                kwargs["tools"] = anthropic_tools

            response = self._client.messages.create(**kwargs)

            # Parse response
            content_text = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    content_text = block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input,  # type: ignore[arg-type]
                        )
                    )

            return LLMResponse(
                message=LLMMessage(
                    role=Role.ASSISTANT,
                    content=content_text,
                    tool_calls=tool_calls,
                ),
                model=response.model,
                stop_reason=response.stop_reason,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )

        result = _call()
        return result.alt(  # type: ignore[return-value]
            lambda exc: LLMError(message=str(exc), provider="anthropic")
        )


# ---------------------------------------------------------------------------
# OpenAIProvider — wraps the OpenAI SDK
# ---------------------------------------------------------------------------

class OpenAIProvider:
    """OpenAI adapter.

    Requires: pip install agente-machete[openai]
    """

    def __init__(self, api_key: str | None = None) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package required. Install with: "
                "pip install agente-machete[openai]"
            )
        self._client = openai.OpenAI(api_key=api_key)

    def complete(
        self,
        messages: Sequence[LLMMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        *,
        model: str = "gpt-4o",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> IOResult[LLMResponse, AgentError]:
        @impure_safe
        def _call() -> LLMResponse:
            api_messages = []
            for msg in messages:
                m: dict[str, Any] = {
                    "role": msg.role.value,
                    "content": msg.content,
                }
                if msg.tool_call_id:
                    m["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    m["name"] = msg.name
                api_messages.append(m)

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools

            response = self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg_out = choice.message

            tool_calls = []
            if msg_out.tool_calls:
                import json

                for tc in msg_out.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=json.loads(tc.function.arguments),
                        )
                    )

            return LLMResponse(
                message=LLMMessage(
                    role=Role.ASSISTANT,
                    content=msg_out.content or "",
                    tool_calls=tool_calls,
                ),
                model=response.model,
                stop_reason=choice.finish_reason,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            )

        result = _call()
        return result.alt(  # type: ignore[return-value]
            lambda exc: LLMError(message=str(exc), provider="openai")
        )
