"""Infrastructure resource graph — a DAG of inferred cloud resources.

CT mapping:
  - The resource graph is a free category over resource types
  - Edges represent dependencies (data flow, IAM permissions)
  - The CDK emitter is a functor from this free category to CDK constructs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResourceType(str, Enum):
    LAMBDA = "lambda"
    API_GATEWAY = "api_gateway"
    SQS = "sqs"
    DYNAMODB = "dynamodb"
    EVENTBRIDGE = "eventbridge"
    IAM_ROLE = "iam_role"
    S3 = "s3"


@dataclass(frozen=True)
class ResourceNode:
    """A single infrastructure resource."""

    id: str
    type: ResourceType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceEdge:
    """A dependency between two resources."""

    source: str  # ResourceNode.id
    target: str  # ResourceNode.id
    relation: str = "depends_on"  # e.g., "invokes", "reads", "writes", "triggers"


@dataclass
class ResourceGraph:
    """DAG of infrastructure resources inferred from application code.

    This is the intermediate representation between code analysis
    and CDK emission. It's a free category — we capture the structure
    without committing to a specific cloud provider's semantics.
    """

    nodes: dict[str, ResourceNode] = field(default_factory=dict)
    edges: list[ResourceEdge] = field(default_factory=list)

    def add_node(self, node: ResourceNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: ResourceEdge) -> None:
        self.edges.append(edge)

    def get_node(self, node_id: str) -> ResourceNode | None:
        return self.nodes.get(node_id)

    def get_dependencies(self, node_id: str) -> list[ResourceNode]:
        """Get all nodes that this node depends on."""
        target_ids = [e.target for e in self.edges if e.source == node_id]
        return [self.nodes[tid] for tid in target_ids if tid in self.nodes]

    def get_dependents(self, node_id: str) -> list[ResourceNode]:
        """Get all nodes that depend on this node."""
        source_ids = [e.source for e in self.edges if e.target == node_id]
        return [self.nodes[sid] for sid in source_ids if sid in self.nodes]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for inspection / debugging."""
        return {
            "nodes": [
                {"id": n.id, "type": n.type.value, "name": n.name, "properties": n.properties}
                for n in self.nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "relation": e.relation}
                for e in self.edges
            ],
        }
