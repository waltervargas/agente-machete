"""Infrastructure analyzer — infer cloud resources from decorated code.

Walks through a module's decorated objects and builds a ResourceGraph.
This is the "programs are syntax" half of the EM perspective — the
decorated code is the syntax, and the analyzer extracts its meaning.

Rules:
  - @agent → Lambda + API Gateway (agent endpoint)
  - @tool  → Lambda (tool executor)
  - @tool(schedule="...") → Lambda + EventBridge
  - @tool(queue=True) → Lambda + SQS
  - Any agent with tools → IAM roles connecting them
"""

from __future__ import annotations

import importlib
import inspect
from types import ModuleType
from typing import Any

from machete.decorators import get_meta
from machete.infra.graph import ResourceEdge, ResourceGraph, ResourceNode, ResourceType
from machete.types import MacheteMeta, ResourceHint


def analyze_module(module: ModuleType | str) -> ResourceGraph:
    """Analyze a module and build an infrastructure resource graph.

    Args:
        module: A Python module object or a dotted module path string.

    Returns:
        A ResourceGraph representing the inferred infrastructure.
    """
    if isinstance(module, str):
        module = importlib.import_module(module)

    graph = ResourceGraph()
    _scan_module(module, graph)
    return graph


def _scan_module(module: ModuleType, graph: ResourceGraph) -> None:
    """Scan all module-level objects for machete metadata."""
    for name, obj in inspect.getmembers(module):
        if name.startswith("_"):
            continue
        meta = get_meta(obj)
        if meta is None:
            continue

        if meta.kind == "agent":
            _add_agent(meta, graph)
        elif meta.kind == "tool":
            _add_tool(meta, graph)
        elif meta.kind == "step":
            _add_step(meta, graph)


def _add_agent(meta: MacheteMeta, graph: ResourceGraph) -> None:
    """Add agent resources: Lambda + API Gateway + connected tools."""
    agent_id = f"agent-{meta.name}"

    # Lambda for the agent
    lambda_node = ResourceNode(
        id=f"{agent_id}-lambda",
        type=ResourceType.LAMBDA,
        name=f"{meta.name}-handler",
        properties={
            "handler": "machete.runtime.lambda_handler.handler",
            "runtime": "python3.11",
            "timeout": 300,
            "memory": 512,
            "environment": {
                "MACHETE_AGENT": meta.name,
                "MACHETE_MODEL": meta.config.model if meta.config else "",
            },
        },
    )
    graph.add_node(lambda_node)

    # API Gateway
    apigw_node = ResourceNode(
        id=f"{agent_id}-api",
        type=ResourceType.API_GATEWAY,
        name=f"{meta.name}-api",
        properties={
            "description": meta.config.description if meta.config else "",
            "route": f"/agent/{meta.name}",
        },
    )
    graph.add_node(apigw_node)
    graph.add_edge(ResourceEdge(
        source=apigw_node.id,
        target=lambda_node.id,
        relation="invokes",
    ))

    # IAM role for the agent Lambda
    role_node = ResourceNode(
        id=f"{agent_id}-role",
        type=ResourceType.IAM_ROLE,
        name=f"{meta.name}-role",
        properties={"assume_role_service": "lambda.amazonaws.com"},
    )
    graph.add_node(role_node)
    graph.add_edge(ResourceEdge(
        source=lambda_node.id,
        target=role_node.id,
        relation="assumes",
    ))

    # Connect tools
    for tool_obj in meta.tools:
        tool_meta = get_meta(tool_obj)
        if tool_meta:
            _add_tool(tool_meta, graph)
            tool_id = f"tool-{tool_meta.name}-lambda"
            graph.add_edge(ResourceEdge(
                source=lambda_node.id,
                target=tool_id,
                relation="invokes",
            ))


def _add_tool(meta: MacheteMeta, graph: ResourceGraph) -> None:
    """Add tool resources: Lambda + optional SQS/EventBridge."""
    tool_id = f"tool-{meta.name}"

    # Lambda for the tool
    lambda_node = ResourceNode(
        id=f"{tool_id}-lambda",
        type=ResourceType.LAMBDA,
        name=f"{meta.name}-handler",
        properties={
            "handler": f"machete.runtime.lambda_handler.tool_handler",
            "runtime": "python3.11",
            "timeout": 60,
            "memory": 256,
            "environment": {"MACHETE_TOOL": meta.name},
        },
    )
    graph.add_node(lambda_node)

    # Scheduled execution
    if meta.schedule:
        event_node = ResourceNode(
            id=f"{tool_id}-schedule",
            type=ResourceType.EVENTBRIDGE,
            name=f"{meta.name}-schedule",
            properties={"schedule_expression": meta.schedule},
        )
        graph.add_node(event_node)
        graph.add_edge(ResourceEdge(
            source=event_node.id,
            target=lambda_node.id,
            relation="triggers",
        ))

    # Queue-based processing
    if meta.queue:
        sqs_node = ResourceNode(
            id=f"{tool_id}-queue",
            type=ResourceType.SQS,
            name=f"{meta.name}-queue",
            properties={"visibility_timeout": 120},
        )
        graph.add_node(sqs_node)
        graph.add_edge(ResourceEdge(
            source=sqs_node.id,
            target=lambda_node.id,
            relation="triggers",
        ))


def _add_step(meta: MacheteMeta, graph: ResourceGraph) -> None:
    """Add step resources — typically just a Lambda."""
    step_id = f"step-{meta.name}"
    lambda_node = ResourceNode(
        id=f"{step_id}-lambda",
        type=ResourceType.LAMBDA,
        name=f"{meta.name}-handler",
        properties={
            "handler": "machete.runtime.lambda_handler.step_handler",
            "runtime": "python3.11",
            "timeout": 60,
            "memory": 256,
        },
    )
    graph.add_node(lambda_node)
