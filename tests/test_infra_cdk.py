"""Tests for CDK emission."""

from machete.infra.analyzer import analyze_module
from machete.infra.cdk_emitter import emit_cdk_app, emit_cdk_json


class TestEmitCdkJson:
    def test_produces_valid_cfn_structure(self) -> None:
        graph = analyze_module("examples.simple_agent")
        template = emit_cdk_json(graph)

        assert template["AWSTemplateFormatVersion"] == "2010-09-09"
        assert "Resources" in template
        assert len(template["Resources"]) > 0

    def test_lambda_resources_present(self) -> None:
        graph = analyze_module("examples.simple_agent")
        template = emit_cdk_json(graph)

        lambda_resources = {
            k: v for k, v in template["Resources"].items()
            if v.get("Type") == "AWS::Lambda::Function"
        }
        assert len(lambda_resources) >= 1

    def test_api_gateway_present(self) -> None:
        graph = analyze_module("examples.simple_agent")
        template = emit_cdk_json(graph)

        apigw = {
            k: v for k, v in template["Resources"].items()
            if v.get("Type") == "AWS::ApiGateway::RestApi"
        }
        assert len(apigw) == 1


class TestEmitCdkApp:
    def test_produces_valid_python(self) -> None:
        graph = analyze_module("examples.simple_agent")
        source = emit_cdk_app(graph)

        assert "import aws_cdk" in source
        assert "class MacheteStack" in source
        assert "app.synth()" in source

    def test_contains_lambda_constructs(self) -> None:
        graph = analyze_module("examples.simple_agent")
        source = emit_cdk_app(graph)

        assert "_lambda.Function(" in source

    def test_contains_api_gateway(self) -> None:
        graph = analyze_module("examples.simple_agent")
        source = emit_cdk_app(graph)

        assert "apigw.RestApi(" in source
