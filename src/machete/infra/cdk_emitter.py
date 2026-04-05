"""CDK synthesizer — functor from ResourceGraph to CDK CloudAssembly.

CT mapping:
  - This is a functor: it maps objects (ResourceNodes) and morphisms
    (ResourceEdges) in our free category to objects (CDK Constructs)
    and morphisms (IAM grants, event subscriptions) in the CDK category.
  - CDK's jsii layer handles the actual CloudFormation synthesis —
    we only map our domain to CDK constructs, never to raw CFN.

The key insight: we use aws_cdk directly in-process. No string
templating, no hand-rolled CloudFormation JSON. We create real
CDK constructs and let `app.synth()` produce the CloudAssembly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
    aws_apigateway as apigw,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as _lambda,
    aws_lambda_event_sources as event_sources,
    aws_sqs as sqs,
    cx_api,
)
from constructs import Construct

from machete.infra.graph import ResourceGraph, ResourceNode, ResourceType


class MacheteStack(Stack):
    """CDK Stack built from a ResourceGraph.

    This is the functor's action on objects: each ResourceNode
    becomes a CDK Construct, and each ResourceEdge becomes a
    CDK relationship (grant, add_event_source, add_target, etc.).
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        graph: ResourceGraph,
        code_asset_path: str = "lambda_code",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self._constructs: dict[str, Construct] = {}
        self._graph = graph

        # Phase 1: create all constructs (functor on objects)
        for node in graph.nodes.values():
            self._create_construct(node, code_asset_path)

        # Phase 2: wire edges (functor on morphisms)
        for edge in graph.edges:
            self._wire_edge(edge)

    def _create_construct(self, node: ResourceNode, code_asset_path: str) -> None:
        match node.type:
            case ResourceType.LAMBDA:
                fn = _lambda.Function(
                    self,
                    node.id,
                    function_name=node.name,
                    handler=node.properties.get("handler", "index.handler"),
                    runtime=_lambda.Runtime.PYTHON_3_11,
                    timeout=Duration.seconds(node.properties.get("timeout", 60)),
                    memory_size=node.properties.get("memory", 256),
                    environment=node.properties.get("environment", {}),
                    code=_lambda.Code.from_asset(code_asset_path),
                )
                self._constructs[node.id] = fn

            case ResourceType.API_GATEWAY:
                api = apigw.RestApi(
                    self,
                    node.id,
                    rest_api_name=node.name,
                    description=node.properties.get("description", ""),
                )
                self._constructs[node.id] = api

            case ResourceType.SQS:
                queue = sqs.Queue(
                    self,
                    node.id,
                    queue_name=node.name,
                    visibility_timeout=Duration.seconds(
                        node.properties.get("visibility_timeout", 30)
                    ),
                )
                self._constructs[node.id] = queue

            case ResourceType.EVENTBRIDGE:
                rule = events.Rule(
                    self,
                    node.id,
                    schedule=events.Schedule.expression(
                        node.properties.get("schedule_expression", "rate(1 hour)")
                    ),
                )
                self._constructs[node.id] = rule

            case ResourceType.IAM_ROLE:
                # CDK auto-creates IAM roles for Lambda — skip explicit ones.
                # The ResourceGraph tracks them for visibility, but CDK
                # handles the actual role creation and policy attachment.
                pass

    def _wire_edge(self, edge: Any) -> None:
        source = self._constructs.get(edge.source)
        target = self._constructs.get(edge.target)
        if source is None or target is None:
            return

        match edge.relation:
            case "invokes":
                # API Gateway → Lambda: add a POST method
                if isinstance(source, apigw.RestApi) and isinstance(target, _lambda.Function):
                    source.root.add_method("POST", apigw.LambdaIntegration(target))

            case "triggers":
                # SQS → Lambda: add event source mapping
                if isinstance(source, sqs.Queue) and isinstance(target, _lambda.Function):
                    target.add_event_source(event_sources.SqsEventSource(source))

                # EventBridge → Lambda: add as target
                if isinstance(source, events.Rule) and isinstance(target, _lambda.Function):
                    source.add_target(targets.LambdaFunction(target))


def synthesize(
    graph: ResourceGraph,
    outdir: str | Path | None = None,
    stack_name: str = "MacheteStack",
    code_asset_path: str | Path | None = None,
) -> cx_api.CloudAssembly:
    """Synthesize a ResourceGraph into a CDK CloudAssembly.

    This is the entire IfC pipeline in one call:
    ResourceGraph → CDK Constructs → CloudAssembly (with CFN templates).

    All synthesis happens in-process via jsii — no subprocess, no
    string templating, no hand-rolled CloudFormation.

    Args:
        graph: The infrastructure resource graph from the analyzer.
        outdir: Output directory for the cloud assembly. Defaults to
            a temporary directory if not specified.
        stack_name: Name of the CDK stack.
        code_asset_path: Path to the Lambda code asset directory.
            If None, creates a placeholder in a temp directory.

    Returns:
        A CloudAssembly containing the synthesized CFN templates,
        asset manifests, and deployment metadata.
    """
    import tempfile

    # CDK validates asset paths exist at synth time — ensure one exists.
    if code_asset_path is None:
        asset_dir = Path(tempfile.mkdtemp()) / "lambda_code"
    else:
        asset_dir = Path(code_asset_path)

    if not asset_dir.exists():
        asset_dir.mkdir(parents=True, exist_ok=True)
        (asset_dir / "index.py").write_text(
            "# Placeholder — replaced at deploy time with actual agent code.\n"
            "def handler(event, context):\n"
            "    return {'statusCode': 501, 'body': 'Not deployed yet'}\n"
        )

    app = cdk.App(outdir=str(outdir) if outdir else None)
    MacheteStack(app, stack_name, graph=graph, code_asset_path=str(asset_dir))
    return app.synth()


def get_template(assembly: cx_api.CloudAssembly, stack_name: str = "MacheteStack") -> dict:
    """Extract the CloudFormation template dict from a CloudAssembly.

    Convenience function for inspecting / testing synthesized output.
    """
    artifact = assembly.get_stack_by_name(stack_name)
    return artifact.template
