"""Local runtime — execute agents in-process, Jupyter-friendly.

No cloud dependencies needed. This is the default runtime for
development, testing, and notebook usage.
"""

from __future__ import annotations

import asyncio
from typing import Any

from returns.io import IOFailure, IOSuccess

from machete.context import AgentContext
from machete.decorators import get_meta
from machete.llm.protocol import LLMProvider, MockProvider
from machete.monads import AgentResult
from machete.pipeline import AgentPipeline, get_last_response, logging_middleware
from machete.types import PipelineError


def run(
    agent_fn: Any,
    input_text: str,
    *,
    provider: LLMProvider | None = None,
    middleware: list[Any] | None = None,
    verbose: bool = False,
) -> str:
    """Run an agent locally and return the final text response.

    This is the simplest entry point — what a data scientist calls
    in a Jupyter notebook cell.

    Usage::

        from machete import agent, tool, run

        @tool(description="Add two numbers")
        def add(a: int, b: int) -> int:
            return a + b

        @agent(tools=[add])
        def calculator(question: str) -> str:
            ...

        answer = run(calculator, "What is 2 + 3?")
        print(answer)

    Args:
        agent_fn: A @agent-decorated function.
        input_text: The user's input message.
        provider: LLM provider (defaults to MockProvider for testing).
        middleware: Optional middleware stack.
        verbose: If True, adds logging middleware.

    Returns:
        The agent's final text response.

    Raises:
        RuntimeError: If the pipeline fails.
    """
    meta = get_meta(agent_fn)
    if meta is None or meta.kind != "agent":
        raise ValueError(f"{agent_fn} is not an @agent-decorated function")

    if provider is None:
        provider = MockProvider()

    pipeline = AgentPipeline()
    if verbose:
        pipeline.add_middleware(logging_middleware)
    if middleware:
        for mw in middleware:
            pipeline.add_middleware(mw)

    result = pipeline.run_from_agent(agent_fn, provider, input_text)

    match result:
        case IOSuccess(inner):
            ctx = inner._inner_value  # type: ignore[union-attr]
            response = get_last_response(ctx)
            _jupyter_display(ctx, verbose)
            return response
        case IOFailure(inner):
            error = inner._inner_value  # type: ignore[union-attr]
            raise RuntimeError(f"Agent pipeline failed: {error}")


async def run_async(
    agent_fn: Any,
    input_text: str,
    *,
    provider: LLMProvider | None = None,
    middleware: list[Any] | None = None,
    verbose: bool = False,
) -> str:
    """Async version of run() — same API, but awaitable."""
    # For now, delegate to sync (returns library is sync-first).
    # Future: use FutureResult for truly async pipelines.
    return await asyncio.to_thread(
        run, agent_fn, input_text, provider=provider, middleware=middleware, verbose=verbose
    )


def run_result(
    agent_fn: Any,
    input_text: str,
    *,
    provider: LLMProvider | None = None,
) -> AgentResult[AgentContext]:
    """Run and return the raw AgentResult — for advanced users who want monadic access."""
    meta = get_meta(agent_fn)
    if meta is None or meta.kind != "agent":
        from machete.monads import failure

        return failure(PipelineError(message=f"{agent_fn} is not an @agent-decorated function"))

    if provider is None:
        provider = MockProvider()

    pipeline = AgentPipeline()
    return pipeline.run_from_agent(agent_fn, provider, input_text)


def _jupyter_display(ctx: AgentContext, verbose: bool) -> None:
    """Pretty-print agent results in Jupyter if available."""
    try:
        from IPython.display import display, Markdown  # type: ignore[import-not-found]

        if verbose:
            parts = [f"**Agent: {ctx.config.name}** | Run: `{ctx.run_id}`\n"]
            for msg in ctx.messages:
                if msg.role.value == "assistant":
                    if msg.tool_calls:
                        tools_str = ", ".join(tc.name for tc in msg.tool_calls)
                        parts.append(f"- **Tool calls**: {tools_str}")
                    if msg.content:
                        parts.append(f"- **Response**: {msg.content}")
            display(Markdown("\n".join(parts)))
    except ImportError:
        pass  # Not in Jupyter — silent
