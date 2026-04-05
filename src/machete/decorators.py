"""Decorator API — the surface data scientists interact with.

CT mapping:
  - Each decorator is a *natural transformation*: it transforms a plain
    function (in the identity functor) into a framework-aware monadic
    function (in the AgentResult functor).
  - Metadata is stored on __machete_meta__ for the infra analyzer to read.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, ParamSpec, TypeVar, get_type_hints

from pydantic import TypeAdapter

from machete.types import (
    AgentConfig,
    MacheteMeta,
    ResourceHint,
    ToolParameter,
)

P = ParamSpec("P")
T = TypeVar("T")


# ---------------------------------------------------------------------------
# @tool — turns a plain function into a ToolSpec
# ---------------------------------------------------------------------------


def tool(
    name: str | None = None,
    description: str | None = None,
    *,
    schedule: str | None = None,
    queue: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Register a function as a tool available to agents.

    The function's type hints are automatically converted to a JSON Schema
    for LLM tool-calling.

    Usage::

        @tool(description="Search the web for information")
        def search(query: str) -> str:
            return requests.get(f"https://api.search.com?q={query}").text

    Args:
        name: Tool name (defaults to function name).
        description: Human-readable description for the LLM.
        schedule: Optional cron expression for scheduled execution.
        queue: Whether this tool processes from a queue.
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        tool_name = name or fn.__name__
        tool_desc = description or fn.__doc__ or ""

        # Extract parameters from type hints
        hints = get_type_hints(fn)
        sig = inspect.signature(fn)
        params: list[ToolParameter] = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            hint = hints.get(param_name, Any)
            # Use pydantic to get JSON schema type name
            try:
                schema = TypeAdapter(hint).json_schema()
                type_name = schema.get("type", "string")
            except Exception:
                type_name = "string"

            params.append(
                ToolParameter(
                    name=param_name,
                    type=type_name,
                    description="",
                    required=param.default is inspect.Parameter.empty,
                    default=None if param.default is inspect.Parameter.empty else param.default,
                )
            )

        # Build resource hints for infra analyzer
        hints_list: list[ResourceHint] = [ResourceHint.LAMBDA]
        if schedule:
            hints_list.append(ResourceHint.EVENTBRIDGE)
        if queue:
            hints_list.append(ResourceHint.SQS)

        meta = MacheteMeta(
            kind="tool",
            name=tool_name,
            schedule=schedule,
            queue=queue,
            resource_hints=tuple(hints_list),
        )

        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return fn(*args, **kwargs)

        # Attach ToolSpec-compatible attributes
        wrapper.tool_name = tool_name  # type: ignore[attr-defined]
        wrapper.tool_description = tool_desc  # type: ignore[attr-defined]
        wrapper.tool_parameters = params  # type: ignore[attr-defined]
        wrapper.__machete_meta__ = meta  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# @step — marks a function as a composable pipeline step
# ---------------------------------------------------------------------------


def step(
    name: str | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Mark a function as a composable pipeline step.

    Steps are the building blocks of agent pipelines. They compose
    via monadic bind (Kleisli composition).

    Usage::

        @step("validate_input")
        def validate(data: dict) -> dict:
            assert "query" in data
            return data
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        step_name = name or fn.__name__
        meta = MacheteMeta(
            kind="step",
            name=step_name,
            resource_hints=(ResourceHint.LAMBDA,),
        )
        fn.__machete_meta__ = meta  # type: ignore[attr-defined]
        return fn

    return decorator


# ---------------------------------------------------------------------------
# @agent — the top-level decorator that ties everything together
# ---------------------------------------------------------------------------


def agent(
    name: str | None = None,
    *,
    model: str = "claude-sonnet-4-20250514",
    tools: Sequence[Any] = (),
    description: str = "",
    temperature: float = 0.0,
    max_tokens: int = 4096,
    max_iterations: int = 10,
    system_prompt: str = "",
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Register a function as an agent.

    This is the main entry point for data scientists. The decorated function's
    body serves as documentation / a fallback — the real work is done by the
    framework's agentic loop with the specified model and tools.

    Usage::

        @agent(
            name="researcher",
            model="claude-sonnet-4-20250514",
            tools=[search, summarize],
        )
        def researcher(question: str) -> str:
            \"\"\"Research any question using web search.\"\"\"
            ...

    The infra analyzer reads __machete_meta__ to determine that this needs:
    Lambda + API Gateway (for the agent endpoint), plus whatever the tools need.
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        agent_name = name or fn.__name__
        config = AgentConfig(
            name=agent_name,
            description=description or fn.__doc__ or "",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            system_prompt=system_prompt,
        )

        # Compute resource hints from agent + its tools
        hints: list[ResourceHint] = [ResourceHint.LAMBDA, ResourceHint.API_GATEWAY]
        for t in tools:
            if hasattr(t, "__machete_meta__"):
                hints.extend(t.__machete_meta__.resource_hints)

        meta = MacheteMeta(
            kind="agent",
            name=agent_name,
            config=config,
            tools=tuple(tools),
            resource_hints=tuple(set(hints)),
        )

        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # When called directly (not via runtime), just call the function
            return fn(*args, **kwargs)

        wrapper.__machete_meta__ = meta  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def get_meta(obj: Any) -> MacheteMeta | None:
    """Extract machete metadata from a decorated object."""
    return getattr(obj, "__machete_meta__", None)


def get_tool_schema(t: Any) -> dict[str, Any]:
    """Convert a @tool-decorated function to an LLM tool-calling schema."""
    if not hasattr(t, "tool_name"):
        raise ValueError(f"{t} is not a @tool-decorated function")

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in t.tool_parameters:
        properties[param.name] = {"type": param.type, "description": param.description}
        if param.required:
            required.append(param.name)

    return {
        "type": "function",
        "function": {
            "name": t.tool_name,
            "description": t.tool_description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
