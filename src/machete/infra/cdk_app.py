"""CDK app entry point — synthesizable by `cdk synth`.

This module scaffolds a complete CDK project directory that can be
synthesized with the CDK CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

from machete.infra.graph import ResourceGraph


def scaffold_cdk_project(
    graph: ResourceGraph,
    output_dir: str | Path,
    stack_name: str = "MacheteStack",
) -> Path:
    """Scaffold a complete CDK project that `cdk synth` can run.

    Creates:
        output_dir/
            app.py          — the CDK app (from emit_cdk_app)
            cdk.json        — CDK config pointing to app.py
            lambda_code/    — placeholder asset directory
                index.py    — minimal handler placeholder

    Args:
        graph: The infrastructure resource graph.
        output_dir: Directory to write the CDK project into.
        stack_name: Name of the CDK stack.

    Returns:
        Path to the generated app.py file.
    """
    from machete.infra.cdk_emitter import emit_cdk_app

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Write app.py with code_asset_path pointing to sibling lambda_code/
    source = emit_cdk_app(graph, stack_name=stack_name, code_asset_path="lambda_code")
    app_path = out / "app.py"
    app_path.write_text(source)

    # Write cdk.json so `cdk synth` knows the entry point
    cdk_json = {
        "app": "python3 app.py",
        "context": {
            "@aws-cdk/core:bootstrapQualifier": "machete",
        },
    }
    (out / "cdk.json").write_text(json.dumps(cdk_json, indent=2))

    # Create the lambda_code asset directory with a placeholder
    asset_dir = out / "lambda_code"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "index.py").write_text(
        "# Placeholder — replaced at deploy time with actual agent code.\n"
        "def handler(event, context):\n"
        "    return {'statusCode': 501, 'body': 'Not deployed yet'}\n"
    )

    return app_path


def write_cdk_app(cdk_source: str, output_dir: str = "cdk.out") -> Path:
    """Write a CDK app file to disk.

    Args:
        cdk_source: Python source code for the CDK app (from emit_cdk_app).
        output_dir: Directory to write the app to.

    Returns:
        Path to the generated app.py file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    app_path = out / "app.py"
    app_path.write_text(cdk_source)

    return app_path


def write_cfn_template(template: dict, output_dir: str = "cdk.out") -> Path:
    """Write a CloudFormation template JSON to disk.

    Args:
        template: CloudFormation template dict (from emit_cdk_json).
        output_dir: Directory to write to.

    Returns:
        Path to the generated template.json file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    template_path = out / "template.json"
    template_path.write_text(json.dumps(template, indent=2))

    return template_path
