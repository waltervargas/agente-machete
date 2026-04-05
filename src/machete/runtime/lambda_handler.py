"""AWS Lambda handler — runtime adapter for cloud execution.

This wraps the same agent pipeline that runs locally, but receives
events from API Gateway / SQS / EventBridge instead of direct calls.
"""

from __future__ import annotations

import json
import os
from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for agent endpoints (API Gateway → Lambda).

    Receives an HTTP request, runs the agent pipeline, returns the response.
    """
    # Lazy imports to keep cold start fast
    from machete.decorators import get_meta
    from machete.llm.protocol import AnthropicProvider
    from machete.pipeline import AgentPipeline, get_last_response
    from machete.context import build_context
    from returns.io import IOSuccess

    # Parse input from API Gateway
    body = json.loads(event.get("body", "{}"))
    input_text = body.get("input", body.get("message", ""))

    agent_name = os.environ.get("MACHETE_AGENT", "")

    # Import the agent module (configured via environment)
    agent_module = os.environ.get("MACHETE_MODULE", "")
    if agent_module:
        import importlib

        mod = importlib.import_module(agent_module)
        # Find the agent function
        import inspect

        agent_fn = None
        for _, obj in inspect.getmembers(mod):
            meta = get_meta(obj)
            if meta and meta.kind == "agent" and meta.name == agent_name:
                agent_fn = obj
                break

        if agent_fn is None:
            return _response(404, {"error": f"Agent '{agent_name}' not found"})

        meta = get_meta(agent_fn)
        provider = AnthropicProvider()
        ctx = build_context(meta, provider, input_text)
        pipeline = AgentPipeline()
        result = pipeline.run(ctx)

        match result:
            case IOSuccess(inner):
                final_ctx = inner._inner_value  # type: ignore[union-attr]
                return _response(200, {"response": get_last_response(final_ctx)})
            case _:
                return _response(500, {"error": "Pipeline execution failed"})

    return _response(400, {"error": "MACHETE_MODULE not configured"})


def tool_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for individual tool execution (SQS/EventBridge → Lambda)."""
    body = event if not event.get("body") else json.loads(event["body"])
    tool_name = os.environ.get("MACHETE_TOOL", "")

    if not tool_name:
        return _response(400, {"error": "MACHETE_TOOL not configured"})

    # Import and find the tool
    agent_module = os.environ.get("MACHETE_MODULE", "")
    if agent_module:
        import importlib
        import inspect
        from machete.decorators import get_meta

        mod = importlib.import_module(agent_module)
        for _, obj in inspect.getmembers(mod):
            meta = get_meta(obj)
            if meta and meta.kind == "tool" and meta.name == tool_name:
                try:
                    kwargs = body.get("arguments", body)
                    result = obj(**kwargs)
                    return _response(200, {"result": str(result)})
                except Exception as e:
                    return _response(500, {"error": str(e)})

    return _response(404, {"error": f"Tool '{tool_name}' not found"})


def step_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for pipeline step execution."""
    return _response(501, {"error": "Step handler not yet implemented"})


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
