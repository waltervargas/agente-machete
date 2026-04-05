"""Tests for decorators — the data scientist API surface."""

from machete.decorators import agent, get_meta, get_tool_schema, step, tool
from machete.types import MacheteMeta, ResourceHint


class TestToolDecorator:
    def test_attaches_metadata(self) -> None:
        @tool(name="search", description="Search the web")
        def search(query: str) -> str:
            return f"results for {query}"

        meta = get_meta(search)
        assert meta is not None
        assert meta.kind == "tool"
        assert meta.name == "search"

    def test_preserves_function_behavior(self) -> None:
        @tool(description="Add numbers")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_tool_spec_attributes(self) -> None:
        @tool(name="greet", description="Say hello")
        def greet(name: str) -> str:
            return f"Hello, {name}"

        assert greet.tool_name == "greet"  # type: ignore[attr-defined]
        assert greet.tool_description == "Say hello"  # type: ignore[attr-defined]
        assert len(greet.tool_parameters) == 1  # type: ignore[attr-defined]

    def test_generates_json_schema(self) -> None:
        @tool(name="search", description="Search")
        def search(query: str, limit: int = 10) -> str:
            return ""

        schema = get_tool_schema(search)
        assert schema["function"]["name"] == "search"
        props = schema["function"]["parameters"]["properties"]
        assert "query" in props
        assert "limit" in props
        assert "query" in schema["function"]["parameters"]["required"]

    def test_schedule_hint(self) -> None:
        @tool(name="cron_job", description="Runs daily", schedule="rate(1 day)")
        def cron_job() -> None:
            pass

        meta = get_meta(cron_job)
        assert meta is not None
        assert meta.schedule == "rate(1 day)"
        assert ResourceHint.EVENTBRIDGE in meta.resource_hints

    def test_queue_hint(self) -> None:
        @tool(name="worker", description="Queue worker", queue=True)
        def worker(payload: str) -> str:
            return payload

        meta = get_meta(worker)
        assert meta is not None
        assert meta.queue is True
        assert ResourceHint.SQS in meta.resource_hints


class TestStepDecorator:
    def test_attaches_metadata(self) -> None:
        @step("validate")
        def validate(data: dict) -> dict:
            return data

        meta = get_meta(validate)
        assert meta is not None
        assert meta.kind == "step"
        assert meta.name == "validate"


class TestAgentDecorator:
    def test_attaches_config(self) -> None:
        @tool(name="t1", description="test")
        def t1() -> None:
            pass

        @agent(name="my_agent", model="gpt-4o", tools=[t1])
        def my_agent(q: str) -> str:
            return ""

        meta = get_meta(my_agent)
        assert meta is not None
        assert meta.kind == "agent"
        assert meta.name == "my_agent"
        assert meta.config is not None
        assert meta.config.model == "gpt-4o"
        assert len(meta.tools) == 1

    def test_infers_resource_hints(self) -> None:
        @tool(name="t2", description="test", queue=True)
        def t2() -> None:
            pass

        @agent(name="a2", tools=[t2])
        def a2(q: str) -> str:
            return ""

        meta = get_meta(a2)
        assert meta is not None
        assert ResourceHint.LAMBDA in meta.resource_hints
        assert ResourceHint.API_GATEWAY in meta.resource_hints
        assert ResourceHint.SQS in meta.resource_hints
