"""End-to-end tests — the full vertical slice.

Tests the complete flow: define agent → run locally → emit infra.
"""

import json
from pathlib import Path

from returns.io import IOSuccess

from machete import agent, run, tool
from machete.decorators import get_meta, get_tool_schema
from machete.infra.analyzer import analyze_module
from machete.infra.cdk_app import write_cfn_template
from machete.infra.cdk_emitter import emit_cdk_json
from machete.llm.protocol import MockProvider
from machete.types import LLMMessage, LLMResponse, Role, ToolCall


class TestFullVerticalSlice:
    """Data scientist defines an agent → runs it → deploys it."""

    def test_define_and_run_agent(self) -> None:
        """Step 1: Define an agent with tools and run it locally."""

        @tool(name="lookup", description="Look up a fact")
        def lookup(topic: str) -> str:
            return f"{topic}: it's a thing"

        @agent(
            name="researcher",
            tools=[lookup],
            system_prompt="You research topics.",
        )
        def researcher(question: str) -> str:
            ...

        # Mock the LLM to call the tool then respond
        provider = MockProvider(responses=[
            LLMResponse(
                message=LLMMessage(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[ToolCall(id="tc1", name="lookup", arguments={"topic": "Python"})],
                ),
                model="mock",
                stop_reason="tool_use",
            ),
            LLMResponse(
                message=LLMMessage(
                    role=Role.ASSISTANT,
                    content="Python is a programming language.",
                ),
                model="mock",
                stop_reason="end_turn",
            ),
        ])

        result = run(researcher, "Tell me about Python", provider=provider)
        assert result == "Python is a programming language."

    def test_analyze_example_and_emit_cfn(self, tmp_path: Path) -> None:
        """Step 2: Analyze the example module and emit CloudFormation."""
        graph = analyze_module("examples.simple_agent")
        template = emit_cdk_json(graph, stack_name="CalcStack")

        # Write and verify it's valid JSON
        path = write_cfn_template(template, output_dir=str(tmp_path))
        assert path.exists()

        loaded = json.loads(path.read_text())
        assert loaded["AWSTemplateFormatVersion"] == "2010-09-09"
        assert "CalcStack" in loaded["Description"]
        assert len(loaded["Resources"]) > 0

    def test_tool_schema_for_llm(self) -> None:
        """Verify tool schemas are LLM-compatible."""

        @tool(name="search", description="Search the web")
        def search(query: str, max_results: int = 5) -> str:
            return ""

        schema = get_tool_schema(search)

        # Should match OpenAI/Anthropic tool format
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == "search"
        assert fn["description"] == "Search the web"
        assert "query" in fn["parameters"]["properties"]
        assert "max_results" in fn["parameters"]["properties"]
        assert "query" in fn["parameters"]["required"]

    def test_metadata_chain(self) -> None:
        """Verify metadata flows from decorators to infra analyzer."""

        @tool(name="t", description="test tool")
        def t() -> None:
            pass

        @agent(name="a", tools=[t])
        def a(q: str) -> str:
            ...

        meta = get_meta(a)
        assert meta is not None
        assert meta.kind == "agent"
        assert len(meta.tools) == 1

        tool_meta = get_meta(meta.tools[0])
        assert tool_meta is not None
        assert tool_meta.kind == "tool"
