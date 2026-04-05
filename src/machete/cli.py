"""Machete CLI — run, synth, deploy.

Usage:
    machete run <module> --input "..."     Run agent locally
    machete synth <module>                 Emit CDK / CloudFormation
    machete deploy <module>                Synth + deploy
    machete graph <module>                 Show inferred infra graph
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def main(argv: list[str] | None = None) -> None:
    # Ensure CWD is on sys.path so `examples.foo` resolves
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    parser = argparse.ArgumentParser(
        prog="machete",
        description="Agente Machete — AI agents you can actually steer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    run_p = sub.add_parser("run", help="Run an agent locally")
    run_p.add_argument("module", help="Python module path (e.g., examples.simple_agent)")
    run_p.add_argument("--input", "-i", required=True, help="Input message for the agent")
    run_p.add_argument("--agent", "-a", default=None, help="Agent name (if module has multiple)")
    run_p.add_argument("--provider", "-p", default="mock", choices=["mock", "anthropic", "openai"])
    run_p.add_argument("--verbose", "-v", action="store_true")

    # --- synth ---
    synth_p = sub.add_parser("synth", help="Emit infrastructure (CloudFormation/CDK)")
    synth_p.add_argument("module", help="Python module path")
    synth_p.add_argument("--output", "-o", default="cdk.out", help="Output directory")
    synth_p.add_argument("--format", "-f", default="cfn", choices=["cfn", "cdk"], help="Output format")
    synth_p.add_argument("--stack-name", default="MacheteStack", help="Stack name")

    # --- graph ---
    graph_p = sub.add_parser("graph", help="Show inferred infrastructure graph")
    graph_p.add_argument("module", help="Python module path")

    # --- deploy ---
    deploy_p = sub.add_parser("deploy", help="Synth + deploy (requires CDK)")
    deploy_p.add_argument("module", help="Python module path")
    deploy_p.add_argument("--stack-name", default="MacheteStack")

    args = parser.parse_args(argv)

    match args.command:
        case "run":
            _cmd_run(args)
        case "synth":
            _cmd_synth(args)
        case "graph":
            _cmd_graph(args)
        case "deploy":
            _cmd_deploy(args)


def _cmd_run(args: Any) -> None:
    import importlib
    import inspect

    from machete.decorators import get_meta
    from machete.runtime.local import run

    mod = importlib.import_module(args.module)
    agent_fn = _find_agent(mod, args.agent)

    provider = _make_provider(args.provider)
    result = run(agent_fn, args.input, provider=provider, verbose=args.verbose)
    print(result)


def _cmd_synth(args: Any) -> None:
    from machete.infra.analyzer import analyze_module
    from machete.infra.cdk_emitter import emit_cdk_app, emit_cdk_json
    from machete.infra.cdk_app import write_cdk_app, write_cfn_template

    graph = analyze_module(args.module)

    if args.format == "cdk":
        source = emit_cdk_app(graph, stack_name=args.stack_name)
        path = write_cdk_app(source, output_dir=args.output)
        print(f"CDK app written to: {path}")
    else:
        template = emit_cdk_json(graph, stack_name=args.stack_name)
        path = write_cfn_template(template, output_dir=args.output)
        print(f"CloudFormation template written to: {path}")
        print(json.dumps(template, indent=2))


def _cmd_graph(args: Any) -> None:
    from machete.infra.analyzer import analyze_module

    graph = analyze_module(args.module)
    data = graph.to_dict()
    print(json.dumps(data, indent=2))


def _cmd_deploy(args: Any) -> None:
    import subprocess

    # First synth
    from machete.infra.analyzer import analyze_module
    from machete.infra.cdk_emitter import emit_cdk_app
    from machete.infra.cdk_app import write_cdk_app

    graph = analyze_module(args.module)
    source = emit_cdk_app(graph, stack_name=args.stack_name)
    app_path = write_cdk_app(source)

    print(f"CDK app generated at: {app_path}")
    print("Running: cdk deploy")
    subprocess.run(["cdk", "deploy", "--app", f"python {app_path}"], check=True)


def _find_agent(mod: Any, agent_name: str | None) -> Any:
    import inspect
    from machete.decorators import get_meta

    agents = []
    for name, obj in inspect.getmembers(mod):
        meta = get_meta(obj)
        if meta and meta.kind == "agent":
            if agent_name is None or meta.name == agent_name:
                agents.append(obj)

    if not agents:
        print(f"Error: No @agent found in module", file=sys.stderr)
        sys.exit(1)
    if len(agents) > 1 and agent_name is None:
        names = [get_meta(a).name for a in agents]  # type: ignore[union-attr]
        print(f"Error: Multiple agents found: {names}. Use --agent to specify.", file=sys.stderr)
        sys.exit(1)

    return agents[0]


def _make_provider(name: str) -> Any:
    match name:
        case "mock":
            from machete.llm.protocol import MockProvider
            return MockProvider()
        case "anthropic":
            from machete.llm.protocol import AnthropicProvider
            return AnthropicProvider()
        case "openai":
            from machete.llm.protocol import OpenAIProvider
            return OpenAIProvider()
        case _:
            raise ValueError(f"Unknown provider: {name}")


if __name__ == "__main__":
    main()
