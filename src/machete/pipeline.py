"""Pipeline engine — the agentic loop as monadic composition.

CT mapping:
  - The agentic loop is an anamorphism (unfold): it generates a sequence
    of LLM calls + tool executions until a termination condition.
  - Each iteration is a monadic bind in IOResult.
  - Middleware = endomorphism on step functions (chained algebras).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from returns.io import IOFailure, IOSuccess

from machete.context import AgentContext, build_context, tool_session
from machete.decorators import get_meta, get_tool_schema
from machete.monads import AgentResult, failure, success
from machete.types import (
    LLMMessage,
    LLMResponse,
    PipelineError,
    Role,
    ToolCall,
    ToolError,
)

logger = logging.getLogger("machete")

# ---------------------------------------------------------------------------
# Middleware — chained algebras over step functions
# ---------------------------------------------------------------------------

StepFn = Callable[[AgentContext], AgentResult[AgentContext]]
Middleware = Callable[[StepFn], StepFn]


def logging_middleware(step: StepFn) -> StepFn:
    """Log each pipeline step execution."""

    def wrapper(ctx: AgentContext) -> AgentResult[AgentContext]:
        logger.info("[%s] step executing (messages=%d)", ctx.run_id, len(ctx.messages))
        result = step(ctx)
        # IOResult doesn't have a simple match, use map/fix
        result.map(lambda c: logger.info("[%s] step succeeded", c.run_id))
        return result

    return wrapper


# ---------------------------------------------------------------------------
# Core pipeline steps
# ---------------------------------------------------------------------------


def _execute_tool(ctx: AgentContext, tool_call: ToolCall) -> AgentResult[str]:
    """Execute a single tool call, returning the result as a string."""
    tool = ctx.get_tool(tool_call.name)
    if tool is None:
        return failure(ToolError(tool_name=tool_call.name, message="Tool not found"))

    try:
        result = tool(**tool_call.arguments)
        return success(str(result))
    except Exception as e:
        return failure(ToolError(tool_name=tool_call.name, message=str(e), original=e))


def _llm_step(ctx: AgentContext, tool_schemas: list[dict[str, Any]]) -> AgentResult[AgentContext]:
    """Single LLM call step — call the provider and update context."""
    result = ctx.provider.complete(
        messages=ctx.messages,
        tools=tool_schemas if tool_schemas else None,
        model=ctx.config.model,
        temperature=ctx.config.temperature,
        max_tokens=ctx.config.max_tokens,
    )

    def _handle_response(response: LLMResponse) -> AgentContext:
        return ctx.append_message(response.message)

    return result.map(_handle_response)  # type: ignore[return-value]


def _tool_step(ctx: AgentContext) -> AgentResult[AgentContext]:
    """Execute tool calls from the last assistant message and append results."""
    if not ctx.messages:
        return success(ctx)

    last = ctx.messages[-1]
    if last.role != Role.ASSISTANT or not last.tool_calls:
        return success(ctx)

    new_ctx = ctx
    for tc in last.tool_calls:
        tool_result = _execute_tool(new_ctx, tc)

        # Extract the result or propagate failure
        match tool_result:
            case IOSuccess(inner):
                result_str = inner._inner_value  # type: ignore[union-attr]
                new_ctx = new_ctx.append_message(
                    LLMMessage(
                        role=Role.TOOL,
                        content=result_str,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )
            case IOFailure(inner):
                # On tool error, report it back to the LLM rather than failing the pipeline
                error = inner._inner_value  # type: ignore[union-attr]
                error_msg = f"Error: {error.message}" if hasattr(error, "message") else str(error)
                new_ctx = new_ctx.append_message(
                    LLMMessage(
                        role=Role.TOOL,
                        content=error_msg,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )

    return success(new_ctx)


# ---------------------------------------------------------------------------
# AgentPipeline — the main orchestrator
# ---------------------------------------------------------------------------


@dataclass
class AgentPipeline:
    """The agentic loop as a monadic pipeline.

    This unfolds the LLM interaction: call LLM → maybe execute tools →
    call LLM again → ... until the LLM stops requesting tools or we
    hit max iterations.
    """

    middleware: list[Middleware] = field(default_factory=list)

    def add_middleware(self, mw: Middleware) -> AgentPipeline:
        """Add middleware (returns self for chaining)."""
        self.middleware.append(mw)
        return self

    def _wrap_step(self, step: StepFn) -> StepFn:
        """Apply middleware stack (fold from right — outermost first)."""
        wrapped = step
        for mw in reversed(self.middleware):
            wrapped = mw(wrapped)
        return wrapped

    def run(self, ctx: AgentContext) -> AgentResult[AgentContext]:
        """Execute the agentic loop.

        This is an anamorphism: it unfolds a sequence of LLM + tool steps
        until termination, threading the context through monadically.
        """
        # Build tool schemas once
        tool_schemas = [get_tool_schema(t) for t in ctx.tools.values()]

        with tool_session(ctx) as session_ctx:
            current: AgentResult[AgentContext] = success(session_ctx)

            for i in range(ctx.config.max_iterations):
                # LLM step
                def _do_llm(c: AgentContext) -> AgentResult[AgentContext]:
                    return _llm_step(c, tool_schemas)

                wrapped_llm = self._wrap_step(_do_llm)

                # Bind: current >>= wrapped_llm
                current = current.bind(wrapped_llm)  # type: ignore[assignment]

                # Check if we should continue (did the LLM request tools?)
                should_continue = False

                match current:
                    case IOSuccess(inner):
                        c = inner._inner_value  # type: ignore[union-attr]
                        if c.messages and c.messages[-1].tool_calls:
                            should_continue = True
                    case IOFailure(_):
                        return current  # Short-circuit on error

                if not should_continue:
                    break

                # Tool step
                current = current.bind(_tool_step)  # type: ignore[assignment]

            return current

    def run_from_agent(
        self,
        agent_fn: Any,
        provider: Any,
        input_text: str,
    ) -> AgentResult[AgentContext]:
        """Convenience: build context from a @agent-decorated function and run."""
        meta = get_meta(agent_fn)
        if meta is None or meta.kind != "agent":
            return failure(
                PipelineError(message=f"{agent_fn} is not an @agent-decorated function")
            )
        ctx = build_context(meta, provider, input_text)
        return self.run(ctx)


def get_last_response(ctx: AgentContext) -> str:
    """Extract the final text response from a completed context."""
    for msg in reversed(ctx.messages):
        if msg.role == Role.ASSISTANT and msg.content and not msg.tool_calls:
            return msg.content
    # Fall back to last assistant message even if it had tool calls
    for msg in reversed(ctx.messages):
        if msg.role == Role.ASSISTANT and msg.content:
            return msg.content
    return ""
