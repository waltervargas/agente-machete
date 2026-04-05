"""CDK project scaffolding for deployment.

Synthesis happens in-process via `cdk_emitter.synthesize()` — no
scaffolding needed. This module only exists for the `machete deploy`
path, where we need a directory with a code asset for `cdk deploy`.
"""

from __future__ import annotations

from pathlib import Path

from machete.infra.graph import ResourceGraph


def scaffold_deploy_dir(
    graph: ResourceGraph,
    output_dir: str | Path,
    stack_name: str = "MacheteStack",
) -> Path:
    """Create a deployment directory with the Lambda code asset.

    The `cdk deploy` command needs a real directory with Lambda code
    to package and upload. This creates that directory and runs
    in-process synthesis into it.

    Creates:
        output_dir/
            lambda_code/    — placeholder asset directory
                index.py    — minimal handler placeholder

    Returns:
        Path to the output directory.
    """
    from machete.infra.cdk_emitter import synthesize

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Create the lambda_code asset directory with a placeholder
    asset_dir = out / "lambda_code"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "index.py").write_text(
        "# Placeholder — replaced at deploy time with actual agent code.\n"
        "def handler(event, context):\n"
        "    return {'statusCode': 501, 'body': 'Not deployed yet'}\n"
    )

    # Synthesize into output_dir (CloudAssembly goes here)
    synthesize(
        graph,
        outdir=out,
        stack_name=stack_name,
        code_asset_path=str(asset_dir),
    )

    return out
