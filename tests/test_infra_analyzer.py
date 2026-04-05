"""Tests for the infrastructure analyzer."""

from machete.infra.analyzer import analyze_module
from machete.infra.graph import ResourceType


class TestAnalyzeModule:
    def test_analyzes_example_module(self) -> None:
        graph = analyze_module("examples.simple_agent")

        # Should have Lambda + API Gateway for the agent, plus Lambdas for tools
        lambda_nodes = [n for n in graph.nodes.values() if n.type == ResourceType.LAMBDA]
        api_nodes = [n for n in graph.nodes.values() if n.type == ResourceType.API_GATEWAY]

        assert len(lambda_nodes) >= 1  # At least the agent Lambda
        assert len(api_nodes) == 1  # One API Gateway
        assert len(graph.edges) > 0  # At least API GW → Lambda edge

    def test_agent_has_api_gateway(self) -> None:
        graph = analyze_module("examples.simple_agent")
        api_nodes = [n for n in graph.nodes.values() if n.type == ResourceType.API_GATEWAY]
        assert len(api_nodes) == 1
        assert "calculator" in api_nodes[0].name

    def test_tools_have_lambdas(self) -> None:
        graph = analyze_module("examples.simple_agent")
        tool_lambdas = [
            n
            for n in graph.nodes.values()
            if n.type == ResourceType.LAMBDA and n.id.startswith("tool-")
        ]
        assert len(tool_lambdas) == 2  # add + multiply

    def test_graph_serializable(self) -> None:
        graph = analyze_module("examples.simple_agent")
        data = graph.to_dict()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0
