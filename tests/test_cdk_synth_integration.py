"""Integration test: in-process CDK synthesis produces valid CloudFormation.

This test runs entirely in /tmp to verify the full Infrastructure
From Code pipeline:

  1. Analyze decorated agent code -> ResourceGraph
  2. Synthesize via CDK in-process -> CloudAssembly
  3. Assert the resulting CloudFormation template contains the
     expected resources (Lambda, API Gateway, IAM roles)

No subprocess calls, no cdk CLI — pure in-process synthesis via jsii.

Requires: aws-cdk-lib, constructs (pip install agente-machete[infra])
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from machete.infra.analyzer import analyze_module
from machete.infra.cdk_emitter import get_template, synthesize

# Skip if aws_cdk is not installed
try:
    import aws_cdk  # noqa: F401
except ImportError:
    pytest.skip("aws-cdk-lib not installed", allow_module_level=True)


@pytest.fixture
def synth_result(tmp_path: Path):
    """Synthesize the simple_agent example in /tmp and return (assembly, template)."""
    graph = analyze_module("examples.simple_agent")
    assembly = synthesize(graph, outdir=tmp_path, stack_name="MacheteTestStack")
    template = get_template(assembly, "MacheteTestStack")
    return assembly, template


class TestCdkSynthIntegration:
    """Verify that in-process CDK synthesis produces valid CloudFormation."""

    def test_synth_produces_template(self, synth_result) -> None:
        assembly, template = synth_result
        assert "Resources" in template
        assert len(template["Resources"]) > 0

    def test_lambda_functions_created(self, synth_result) -> None:
        """Each agent + tool gets a Lambda function."""
        _, template = synth_result
        lambdas = {
            k: v for k, v in template["Resources"].items() if v["Type"] == "AWS::Lambda::Function"
        }

        assert len(lambdas) == 3

        function_names = {v["Properties"]["FunctionName"] for v in lambdas.values()}
        assert "calculator-handler" in function_names
        assert "add-handler" in function_names
        assert "multiply-handler" in function_names

    def test_lambda_runtimes(self, synth_result) -> None:
        """All Lambdas use Python 3.11."""
        _, template = synth_result
        lambdas = [
            v for v in template["Resources"].values() if v["Type"] == "AWS::Lambda::Function"
        ]
        for fn in lambdas:
            assert fn["Properties"]["Runtime"] == "python3.11"

    def test_lambda_environment_variables(self, synth_result) -> None:
        """Agent Lambda has MACHETE_AGENT, tool Lambdas have MACHETE_TOOL."""
        _, template = synth_result
        lambdas = {
            v["Properties"]["FunctionName"]: v["Properties"]
            for v in template["Resources"].values()
            if v["Type"] == "AWS::Lambda::Function"
        }

        agent_env = lambdas["calculator-handler"]["Environment"]["Variables"]
        assert agent_env["MACHETE_AGENT"] == "calculator"
        assert agent_env["MACHETE_MODEL"] == "claude-sonnet-4-20250514"

        add_env = lambdas["add-handler"]["Environment"]["Variables"]
        assert add_env["MACHETE_TOOL"] == "add"

        multiply_env = lambdas["multiply-handler"]["Environment"]["Variables"]
        assert multiply_env["MACHETE_TOOL"] == "multiply"

    def test_api_gateway_created(self, synth_result) -> None:
        """An API Gateway REST API is created for the agent."""
        _, template = synth_result
        apigws = {
            k: v
            for k, v in template["Resources"].items()
            if v["Type"] == "AWS::ApiGateway::RestApi"
        }
        assert len(apigws) == 1
        apigw = list(apigws.values())[0]
        assert apigw["Properties"]["Name"] == "calculator-api"

    def test_api_gateway_has_post_method(self, synth_result) -> None:
        """The API Gateway has a POST method wired to the agent Lambda."""
        _, template = synth_result
        methods = {
            k: v
            for k, v in template["Resources"].items()
            if v["Type"] == "AWS::ApiGateway::Method"
        }
        assert len(methods) >= 1
        method = list(methods.values())[0]
        assert method["Properties"]["HttpMethod"] == "POST"
        assert method["Properties"]["Integration"]["Type"] == "AWS_PROXY"

    def test_iam_roles_created(self, synth_result) -> None:
        """CDK auto-generates IAM roles with Lambda execution policies."""
        _, template = synth_result
        roles = {k: v for k, v in template["Resources"].items() if v["Type"] == "AWS::IAM::Role"}
        assert len(roles) >= 3

        lambda_roles = [
            v
            for v in roles.values()
            if any(
                "lambda.amazonaws.com" in str(s.get("Principal", {}))
                for s in v["Properties"]["AssumeRolePolicyDocument"]["Statement"]
            )
        ]
        assert len(lambda_roles) == 3

    def test_output_in_tmp(self, synth_result) -> None:
        """Verify the CloudAssembly was created in /tmp, not in the repo."""
        assembly, _ = synth_result
        assert str(assembly.directory).startswith("/tmp")

    def test_cloud_assembly_structure(self, synth_result) -> None:
        """CloudAssembly has the expected stack artifact."""
        assembly, _ = synth_result
        assert len(assembly.stacks) == 1
        stack = assembly.stacks[0]
        assert stack.stack_name == "MacheteTestStack"

    def test_template_is_valid_json(self, synth_result) -> None:
        """Template round-trips through JSON serialization."""
        _, template = synth_result
        serialized = json.dumps(template, indent=2)
        roundtripped = json.loads(serialized)
        assert roundtripped == template
