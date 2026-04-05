"""Tests for CDK synthesis — in-process via aws_cdk, no subprocess."""

from machete.infra.analyzer import analyze_module
from machete.infra.cdk_emitter import get_template, synthesize


class TestSynthesize:
    def test_produces_cloud_assembly(self, tmp_path) -> None:
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        assert assembly.directory == str(tmp_path)
        assert len(assembly.stacks) == 1

    def test_template_has_resources(self, tmp_path) -> None:
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        template = get_template(assembly, "TestStack")

        assert "Resources" in template
        assert len(template["Resources"]) > 0

    def test_lambda_functions_present(self, tmp_path) -> None:
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        template = get_template(assembly, "TestStack")

        lambdas = {
            k: v
            for k, v in template["Resources"].items()
            if v.get("Type") == "AWS::Lambda::Function"
        }
        assert len(lambdas) == 3  # agent + add + multiply

        names = {v["Properties"]["FunctionName"] for v in lambdas.values()}
        assert names == {"calculator-handler", "add-handler", "multiply-handler"}

    def test_api_gateway_present(self, tmp_path) -> None:
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        template = get_template(assembly, "TestStack")

        apigws = {
            k: v
            for k, v in template["Resources"].items()
            if v.get("Type") == "AWS::ApiGateway::RestApi"
        }
        assert len(apigws) == 1

    def test_api_gateway_wired_to_lambda(self, tmp_path) -> None:
        """API GW POST method exists with AWS_PROXY integration."""
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        template = get_template(assembly, "TestStack")

        methods = {
            k: v
            for k, v in template["Resources"].items()
            if v.get("Type") == "AWS::ApiGateway::Method"
        }
        assert len(methods) >= 1
        method = list(methods.values())[0]
        assert method["Properties"]["HttpMethod"] == "POST"
        assert method["Properties"]["Integration"]["Type"] == "AWS_PROXY"

    def test_iam_roles_auto_created(self, tmp_path) -> None:
        """CDK auto-generates IAM execution roles — we don't hand-roll them."""
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        template = get_template(assembly, "TestStack")

        roles = {
            k: v for k, v in template["Resources"].items() if v.get("Type") == "AWS::IAM::Role"
        }
        # CDK creates one role per Lambda + one for API GW CloudWatch
        assert len(roles) >= 3

    def test_environment_variables(self, tmp_path) -> None:
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        template = get_template(assembly, "TestStack")

        lambdas = {
            v["Properties"]["FunctionName"]: v["Properties"]
            for v in template["Resources"].values()
            if v.get("Type") == "AWS::Lambda::Function"
        }

        assert (
            lambdas["calculator-handler"]["Environment"]["Variables"]["MACHETE_AGENT"]
            == "calculator"
        )
        assert lambdas["add-handler"]["Environment"]["Variables"]["MACHETE_TOOL"] == "add"

    def test_lambda_permissions_created(self, tmp_path) -> None:
        """CDK auto-creates Lambda permissions for API GW invocation."""
        graph = analyze_module("examples.simple_agent")
        assembly = synthesize(graph, outdir=tmp_path, stack_name="TestStack")
        template = get_template(assembly, "TestStack")

        permissions = {
            k: v
            for k, v in template["Resources"].items()
            if v.get("Type") == "AWS::Lambda::Permission"
        }
        assert len(permissions) >= 1
