"""Agent execution context — the Reader monad pattern.

The context carries all dependencies an agent step needs (LLM provider,
tools, config, message history) without global state or DI frameworks.

CT mapping:
  - AgentContext ≈ Reader monad environment
  - tool_session  ≈ bracket / resource algebra (acquire-use-release)
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generator
from uuid import uuid4

from machete.types import AgentConfig, LLMMessage, MacheteMeta, ToolSpec

if TYPE_CHECKING:
    from machete.llm.protocol import LLMProvider


@dataclass
class AgentContext:
    """Immutable-ish execution environment threaded through every step.

    This is the Reader monad's environment — instead of using
    RequiresContext directly (which adds syntactic overhead), we pass
    this explicitly. Same semantics, more Pythonic.
    """

    config: AgentConfig
    provider: LLMProvider
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    messages: list[LLMMessage] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_messages(self, messages: list[LLMMessage]) -> AgentContext:
        """Return a new context with updated messages (persistent data structure style)."""
        return AgentContext(
            config=self.config,
            provider=self.provider,
            tools=self.tools,
            messages=messages,
            run_id=self.run_id,
            metadata=self.metadata,
        )

    def append_message(self, message: LLMMessage) -> AgentContext:
        """Return a new context with one message appended."""
        return self.with_messages([*self.messages, message])

    def get_tool(self, name: str) -> ToolSpec | None:
        return self.tools.get(name)


@contextmanager
def tool_session(ctx: AgentContext) -> Generator[AgentContext, None, None]:
    """Bracket pattern for tool lifecycle — acquire/use/release.

    This is the resource algebra: ensures tools are properly initialized
    before use and cleaned up after, even on error.

    Usage::

        with tool_session(ctx) as session_ctx:
            result = run_pipeline(session_ctx)
    """
    # Acquire: initialize tools that need setup
    for tool in ctx.tools.values():
        if hasattr(tool, "__machete_init__"):
            tool.__machete_init__()  # type: ignore[union-attr]

    try:
        yield ctx
    finally:
        # Release: cleanup tools
        for tool in ctx.tools.values():
            if hasattr(tool, "__machete_cleanup__"):
                tool.__machete_cleanup__()  # type: ignore[union-attr]


def build_context(
    meta: MacheteMeta,
    provider: LLMProvider,
    input_message: str = "",
) -> AgentContext:
    """Build an AgentContext from decorator metadata + a provider."""
    tools_dict = {}
    for t in meta.tools:
        if hasattr(t, "tool_name"):
            tools_dict[t.tool_name] = t

    messages: list[LLMMessage] = []
    if meta.config and meta.config.system_prompt:
        messages.append(LLMMessage(role="system", content=meta.config.system_prompt))  # type: ignore[arg-type]
    if input_message:
        messages.append(LLMMessage(role="user", content=input_message))  # type: ignore[arg-type]

    return AgentContext(
        config=meta.config or AgentConfig(name=meta.name),
        provider=provider,
        tools=tools_dict,
        messages=messages,
    )
