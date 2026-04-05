"""Integration test: emitter → cdk synth → CloudFormation templates.

This test runs *outside* the codebase (in /tmp) to verify the full
Infrastructure From Code pipeline:

  1. Analyze decorated agent code → ResourceGraph
  2. Scaffold a CDK project from the graph
  3. Run `cdk synth` against it
  4. Assert the resulting CloudFormation template contains the
     expected resources (Lambda, API Gateway, IAM roles)

Requires: aws-cdk-lib, constructs, and the `cdk` CLI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from machete.infra.analyzer import analyze_module
from machete.infra.cdk_app import scaffold_cdk_project

# Skip the entire module if cdk CLI is not available
pytestmark = pytest.mark.skipif(
    shutil.which("cdk") is None,
    reason="cdk CLI not installed",
)


@pytest.fixture
def cdk_project(tmp_path: Path) -> Path:
    """Scaffold a CDK project in /tmp from the simple_agent example."""
    graph = analyze_module("examples.simple_agent")
    scaffold_cdk_project(graph, tmp_path, stack_name="MacheteTestStack")
    return tmp_path


def _run_cdk_synth(project_dir: Path) -> dict:
    """Run `cdk synth` and return the parsed CloudFormation template."""
    # Determine the uv project root (this repo)
    repo_root = Path(__file__).resolve().parent.parent

    result = subprocess.run(
        [
            "cdk",
            "synth",
            "--app",
            f"uv run --project {repo_root} python3 app.py",
            "--no-staging",
            "--output",
            str(project_dir / "cdk.out"),
        ],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"cdk synth failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # cdk synth writes the template to cdk.out/MacheteTestStack.template.json
    template_path = project_dir / "cdk.out" / "MacheteTestStack.template.json"
    assert template_path.exists(), (
        f"Template not found at {template_path}. "
        f"cdk.out contents: {list((project_dir / 'cdk.out').iterdir())}"
    )
    return json.loads(template_path.read_text())


class TestCdkSynthIntegration:
    """Verify that the emitted CDK app produces valid CloudFormation."""

    def test_synth_succeeds(self, cdk_project: Path) -> None:
        """cdk synth exits 0 and produces a template."""
        template = _run_cdk_synth(cdk_project)
        assert "Resources" in template
        assert len(template["Resources"]) > 0

    def test_lambda_functions_created(self, cdk_project: Path) -> None:
        """Each agent + tool gets a Lambda function."""
        template = _run_cdk_synth(cdk_project)
        lambdas = {
            k: v for k, v in template["Resources"].items() if v["Type"] == "AWS::Lambda::Function"
        }

        # 3 Lambdas: calculator agent + add tool + multiply tool
        assert len(lambdas) == 3

        function_names = {v["Properties"]["FunctionName"] for v in lambdas.values()}
        assert "calculator-handler" in function_names
        assert "add-handler" in function_names
        assert "multiply-handler" in function_names

    def test_lambda_runtimes(self, cdk_project: Path) -> None:
        """All Lambdas use Python 3.11."""
        template = _run_cdk_synth(cdk_project)
        lambdas = [
            v for v in template["Resources"].values() if v["Type"] == "AWS::Lambda::Function"
        ]
        for fn in lambdas:
            assert fn["Properties"]["Runtime"] == "python3.11"

    def test_lambda_environment_variables(self, cdk_project: Path) -> None:
        """Agent Lambda has MACHETE_AGENT, tool Lambdas have MACHETE_TOOL."""
        template = _run_cdk_synth(cdk_project)
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

    def test_api_gateway_created(self, cdk_project: Path) -> None:
        """An API Gateway REST API is created for the agent."""
        template = _run_cdk_synth(cdk_project)
        apigws = {
            k: v
            for k, v in template["Resources"].items()
            if v["Type"] == "AWS::ApiGateway::RestApi"
        }
        assert len(apigws) == 1
        apigw = list(apigws.values())[0]
        assert apigw["Properties"]["Name"] == "calculator-api"

    def test_api_gateway_has_post_method(self, cdk_project: Path) -> None:
        """The API Gateway has a POST method wired to the agent Lambda."""
        template = _run_cdk_synth(cdk_project)
        methods = {
            k: v
            for k, v in template["Resources"].items()
            if v["Type"] == "AWS::ApiGateway::Method"
        }
        assert len(methods) >= 1
        method = list(methods.values())[0]
        assert method["Properties"]["HttpMethod"] == "POST"
        assert method["Properties"]["Integration"]["Type"] == "AWS_PROXY"

    def test_iam_roles_created(self, cdk_project: Path) -> None:
        """CDK auto-generates IAM roles with Lambda execution policies."""
        template = _run_cdk_synth(cdk_project)
        roles = {k: v for k, v in template["Resources"].items() if v["Type"] == "AWS::IAM::Role"}
        # At least one role per Lambda (3) + one for API GW CloudWatch
        assert len(roles) >= 3

        # All Lambda roles should have the basic execution policy
        lambda_roles = [
            v
            for v in roles.values()
            if any(
                "lambda.amazonaws.com" in str(s.get("Principal", {}))
                for s in v["Properties"]["AssumeRolePolicyDocument"]["Statement"]
            )
        ]
        assert len(lambda_roles) == 3

    def test_template_in_tmp_not_in_repo(self, cdk_project: Path) -> None:
        """Verify the CDK project was created in /tmp, not in the repo."""
        assert str(cdk_project).startswith("/tmp")
        assert not str(cdk_project).startswith("/home/user/agente-machete")

    def test_scaffold_structure(self, cdk_project: Path) -> None:
        """Verify the scaffolded project has the expected files."""
        assert (cdk_project / "app.py").exists()
        assert (cdk_project / "cdk.json").exists()
        assert (cdk_project / "lambda_code" / "index.py").exists()

        cdk_json = json.loads((cdk_project / "cdk.json").read_text())
        assert "app" in cdk_json
