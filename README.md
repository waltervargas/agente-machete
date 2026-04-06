# Agente Machete

**Three commands from decorated Python to production AWS.**

Define agents with decorators. Run locally. Deploy to AWS. Zero infra config.

[![CI](https://github.com/waltervargas/agente-machete/actions/workflows/ci.yml/badge.svg)](https://github.com/waltervargas/agente-machete/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

```python
from machete import agent, tool, run
from machete.llm import AnthropicProvider

@tool(description="Search the web for information")
def search(query: str) -> str:
    return web_search(query)  # your implementation

@tool(description="Summarize text")
def summarize(text: str, max_length: int = 100) -> str:
    return text[:max_length] + "..."

@agent(
    name="researcher",
    model="claude-sonnet-4-20250514",
    tools=[search, summarize],
    system_prompt="You research topics thoroughly, then summarize findings.",
)
def researcher(question: str) -> str:
    """Research any question using web search."""
    ...

# Run locally — works in Jupyter, scripts, anywhere
answer = run(researcher, "What is Infrastructure From Code?", provider=AnthropicProvider())
print(answer)
```

That's it. No chains, no graphs, no YAML. The framework handles the agentic loop (LLM call, tool execution, repeat) and infers your cloud infrastructure from the decorators.

```bash
$ machete synth my_agent.py     # generates Lambda, API Gateway, IAM — from your decorators
$ machete deploy my_agent.py    # deploys to AWS
```

## Try It in 30 Seconds

No API key needed. Copy-paste this into a Python file or Jupyter notebook:

```python
from machete import agent, tool, run
from machete.llm import MockProvider

@tool(name="add", description="Add two numbers")
def add(a: int, b: int) -> int:
    return a + b

@tool(name="multiply", description="Multiply two numbers")
def multiply(a: int, b: int) -> int:
    return a * b

@agent(
    name="calculator",
    model="claude-sonnet-4-20250514",
    tools=[add, multiply],
    system_prompt="You are a calculator. Use tools to compute answers.",
)
def calculator(question: str) -> str:
    """Answer math questions."""
    ...

# MockProvider returns canned responses — great for testing and prototyping
answer = run(calculator, "What is 7 * 8 + 3?")
print(answer)
```

```bash
pip install agente-machete && python my_agent.py
```

Swap `MockProvider` for `AnthropicProvider()` or `OpenAIProvider()` when you're ready for real LLM calls.

## Why Machete?

Most agent frameworks stop at "run my agent." Machete goes further: your decorated Python functions **are** your infrastructure definition.

| | Machete | LangChain | CrewAI |
|---|---|---|---|
| **Define agents** | `@agent` decorator | Chain/Graph classes | Agent/Task/Crew classes |
| **Error handling** | Monadic (`IOResult`) -- composable, typed | try/except | try/except |
| **Infrastructure** | Inferred from decorators | Manual (Terraform, etc.) | Manual |
| **Testing** | Built-in `MockProvider` | Manual mocking | Manual mocking |
| **Core deps** | 2 (returns + pydantic) | 15+ | 10+ |
| **LLM lock-in** | None -- Protocol-based (PEP 544) | Partial | Partial |

**Infrastructure From Code** is the key differentiator. Machete goes from decorated Python functions to production AWS infrastructure (Lambda + API Gateway + SQS + EventBridge) with a single command. No Terraform. No SAM. No Serverless Framework.

## Installation

```bash
pip install agente-machete                  # core only
pip install agente-machete[anthropic]       # + Claude support
pip install agente-machete[openai]          # + OpenAI support
pip install agente-machete[infra]           # + AWS CDK synthesis
```

Or with uv:

```bash
uv add agente-machete
uv add agente-machete --extra anthropic     # + Claude
```

Requires Python 3.11+.

## Quickstart

### 1. Define tools and an agent

```python
# my_agent.py
from machete import agent, tool

@tool(name="add", description="Add two numbers")
def add(a: int, b: int) -> int:
    return a + b

@tool(name="multiply", description="Multiply two numbers")
def multiply(a: int, b: int) -> int:
    return a * b

@agent(
    name="calculator",
    model="claude-sonnet-4-20250514",
    tools=[add, multiply],
    system_prompt="You are a calculator. Use tools to compute answers.",
)
def calculator(question: str) -> str:
    """Answer math questions."""
    ...
```

### 2. Run locally

```python
from machete import run
from machete.llm import AnthropicProvider

answer = run(calculator, "What is 7 * 8 + 3?", provider=AnthropicProvider())
print(answer)  # "59"
```

Or from the CLI:

```bash
machete run examples.simple_agent --input "What is 7 * 8 + 3?" --provider anthropic
```

### 3. Deploy to AWS

```bash
# See what infrastructure Machete infers
machete graph my_agent

# Synthesize CloudFormation (in-process, via CDK)
machete synth my_agent

# Deploy
machete deploy my_agent
```

## How It Works

Machete's execution model has two paths from the same code:

**Local execution** -- the agentic loop:

```
You call run(agent, input)
  → Pipeline sends messages to LLM provider
    → LLM returns tool calls
      → Pipeline executes your @tool functions
        → Results fed back to LLM
          → Repeat until LLM responds with text (no more tool calls)
```

**Cloud deployment** -- infrastructure inference:

```
machete synth my_agent
  → Analyzer scans your module for @agent / @tool / @step decorators
    → Reads __machete_meta__ attached by each decorator
      → Builds a ResourceGraph (DAG of cloud resources)
        → CDK synthesizes real CloudFormation (Lambda, API Gateway, SQS, etc.)
```

The same decorators power both paths. Your `@tool` functions run locally during development and become Lambda functions in production.

## CLI

| Command | Description | Example |
|---|---|---|
| `machete run` | Run an agent locally | `machete run my_app --input "hello" -p anthropic` |
| `machete graph` | Show inferred infrastructure as JSON | `machete graph my_app` |
| `machete synth` | Synthesize CloudFormation via CDK | `machete synth my_app -o cdk.out` |
| `machete deploy` | Synth + deploy to AWS | `machete deploy my_app` |

## Infrastructure From Code

Machete analyzes your decorated code and infers what cloud resources you need:

| Decorator | Inferred Resources |
|---|---|
| `@agent(tools=[...])` | Lambda + API Gateway + IAM role |
| `@tool()` | Lambda |
| `@tool(schedule="rate(1 hour)")` | Lambda + EventBridge rule |
| `@tool(queue=True)` | Lambda + SQS queue |

The synthesis happens **in-process** via the AWS CDK Python SDK and jsii -- no subprocess calls, no string templating, no hand-rolled CloudFormation. Machete creates real CDK constructs (`_lambda.Function`, `apigw.RestApi`, `sqs.Queue`) and lets CDK handle IAM roles, permissions, deployment stages, and all the details.

```bash
$ machete graph examples.simple_agent
```

```json
{
  "nodes": [
    {"id": "agent-calculator-lambda", "type": "lambda", "name": "calculator-handler"},
    {"id": "agent-calculator-api", "type": "api_gateway", "name": "calculator-api"},
    {"id": "tool-add-lambda", "type": "lambda", "name": "add-handler"},
    {"id": "tool-multiply-lambda", "type": "lambda", "name": "multiply-handler"}
  ],
  "edges": [
    {"source": "agent-calculator-api", "target": "agent-calculator-lambda", "relation": "invokes"},
    {"source": "agent-calculator-lambda", "target": "tool-add-lambda", "relation": "invokes"},
    {"source": "agent-calculator-lambda", "target": "tool-multiply-lambda", "relation": "invokes"}
  ]
}
```

You can also use the `synthesize()` function directly from Python:

```python
from machete.infra.analyzer import analyze_module
from machete.infra.cdk_emitter import synthesize, get_template

graph = analyze_module("my_agent")
assembly = synthesize(graph, outdir="/tmp/my-stack")
template = get_template(assembly)
# template is a dict with the full CloudFormation template
```

## LLM Providers

Providers are Protocol-based (PEP 544) -- swap with one line, no inheritance required.

### Anthropic (Claude)

```python
from machete.llm import AnthropicProvider

provider = AnthropicProvider()  # uses ANTHROPIC_API_KEY env var
```

### OpenAI

```python
from machete.llm import OpenAIProvider

provider = OpenAIProvider()  # uses OPENAI_API_KEY env var
```

### Mock (testing)

```python
from machete.llm import MockProvider
from machete.types import LLMMessage, LLMResponse, Role

provider = MockProvider(responses=[
    LLMResponse(
        message=LLMMessage(role=Role.ASSISTANT, content="The answer is 42."),
        model="mock",
    ),
])
```

### Custom provider

Any object with a `complete()` method works -- no base class needed:

```python
class MyProvider:
    def complete(self, messages, tools=None, *, model="", temperature=0.0, max_tokens=4096):
        # Call your LLM, return IOResult[LLMResponse, AgentError]
        ...

# MyProvider satisfies LLMProvider via structural subtyping
run(my_agent, "hello", provider=MyProvider())
```

## Middleware

The pipeline supports middleware for cross-cutting concerns like logging, tracing, and caching. Middleware wraps each pipeline step:

```python
from machete import run
from machete.pipeline import logging_middleware

answer = run(calculator, "What is 2 + 3?", provider=provider, middleware=[logging_middleware])
# [a1b2c3] step executing (messages=2)
# [a1b2c3] step succeeded
```

Write your own middleware -- it's just a function that wraps a step:

```python
def timing_middleware(step):
    def wrapper(ctx):
        start = time.time()
        result = step(ctx)
        print(f"Step took {time.time() - start:.2f}s")
        return result
    return wrapper

answer = run(calculator, "What is 2 + 3?", provider=provider, middleware=[timing_middleware])
```

## Error Handling

Machete uses monadic error handling via the `returns` library. Every operation returns `IOResult[T, AgentError]` -- errors compose and short-circuit without try/except:

```python
from machete import run_result

# run_result returns the raw IOResult for monadic composition
result = run_result(calculator, "What is 2 + 3?", provider=provider)

# Pattern match on success/failure
from returns.io import IOSuccess, IOFailure

match result:
    case IOSuccess(ctx):
        print("Success:", get_last_response(ctx))
    case IOFailure(error):
        print("Error:", error)
```

The error algebra covers all failure modes:

| Error Type | When |
|---|---|
| `LLMError` | Provider call fails (rate limit, auth, network) |
| `ToolError` | Tool execution raises an exception |
| `ValidationError` | Invalid input or configuration |
| `PipelineError` | Pipeline-level failure (max iterations, etc.) |

Tool errors are special: they're reported back to the LLM as tool results, giving the agent a chance to recover. Only LLM and pipeline errors short-circuit execution.

## Testing

Machete is designed for testability. The `MockProvider` lets you write deterministic tests without API calls:

```python
from machete import run
from machete.llm import MockProvider
from machete.types import LLMMessage, LLMResponse, ToolCall, Role

# Test that your agent calls the right tools
provider = MockProvider(responses=[
    # First response: agent decides to call "add" tool
    LLMResponse(
        message=LLMMessage(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="1", name="add", arguments={"a": 2, "b": 3})],
        ),
        model="mock",
    ),
    # Second response: agent returns final answer
    LLMResponse(
        message=LLMMessage(role=Role.ASSISTANT, content="The answer is 5."),
        model="mock",
    ),
])

answer = run(calculator, "What is 2 + 3?", provider=provider)
assert answer == "The answer is 5."
```

You can also pass a function for dynamic responses:

```python
provider = MockProvider(response_fn=lambda messages, **kw: LLMResponse(
    message=LLMMessage(role=Role.ASSISTANT, content=f"Got {len(messages)} messages"),
    model="mock",
))
```

## Architecture

```
  @agent / @tool / @step          Decorators attach __machete_meta__
          |
          v
    AgentPipeline                 Agentic loop: LLM call -> tool exec -> repeat
          |
          v
   AgentResult[T]                 IOResult[T, AgentError] from `returns`
   = IOResult monad               Composable errors, tracked side-effects
          |
     +---------+
     |         |
     v         v
  LLMProvider   Infra Analyzer
  (Protocol)    reads __machete_meta__
     |              |
     v              v
  Anthropic     ResourceGraph -> CDK MacheteStack -> CloudAssembly
  OpenAI
  Mock
  (yours)
```

**Layers:**

- **Decorators** (`@agent`, `@tool`, `@step`) -- the surface API. Attach metadata for the pipeline and infra analyzer.
- **Pipeline** -- the agentic loop. Calls the LLM, executes tools, feeds results back, repeats until done. Supports middleware.
- **Monads** -- `AgentResult[T] = IOResult[T, AgentError]`. Errors short-circuit. Side-effects are tracked. Composition via Kleisli arrows.
- **LLM Providers** -- Protocol-based (PEP 544). Swap providers with one line. No inheritance required.
- **Infra** -- Analyzer reads decorator metadata, builds a ResourceGraph, synthesizes CDK constructs in-process.

## Advanced Features

### Async execution

```python
from machete import run_async

answer = await run_async(calculator, "What is 2 + 3?", provider=provider)
```

### Tool lifecycle hooks

Tools can define setup and teardown logic:

```python
@tool(description="Query a database")
def query_db(sql: str) -> str:
    return db.execute(sql)

query_db.__machete_init__ = lambda: db.connect()
query_db.__machete_cleanup__ = lambda: db.close()
```

The pipeline calls `__machete_init__()` before first use and `__machete_cleanup__()` after completion.

### Scheduled tools and queues

```python
@tool(description="Sync data every hour", schedule="rate(1 hour)")
def sync_data() -> str:
    return fetch_and_store()

@tool(description="Process uploads async", queue=True)
def process_upload(file_key: str) -> str:
    return transform(file_key)
```

These hints are picked up by `machete synth` to create EventBridge rules and SQS queues automatically.

### Type-driven tool schemas

Tool parameters are automatically converted to JSON Schema via Pydantic, so LLMs understand your tool signatures natively:

```python
@tool(description="Search with filters")
def search(query: str, max_results: int = 10, include_archived: bool = False) -> str:
    ...

# Machete generates this for the LLM:
# {"type": "object", "properties": {"query": {"type": "string"}, ...}, "required": ["query"]}
```

## Project Status

**v0.1.0** -- early but functional. The full vertical slice works: define agents with decorators, run them locally, synthesize AWS infrastructure via CDK.

- 55 tests passing (unit + CDK integration)
- CI on GitHub Actions (Python 3.11, 3.12, 3.13)
- MIT licensed

### What works

- `@agent`, `@tool`, `@step` decorators with metadata inference
- Agentic loop with tool calling (LLM call -> tool exec -> repeat)
- Anthropic and OpenAI providers
- Local execution (`run()`, `run_async()`, Jupyter-friendly)
- Middleware pipeline
- Infrastructure analysis and CDK synthesis (Lambda, API Gateway, SQS, EventBridge)
- CLI (`run`, `synth`, `graph`, `deploy`)
- Deterministic testing with `MockProvider`

### Roadmap

- Streaming responses
- Multi-agent pipelines
- State persistence (DynamoDB)
- More cloud targets (GCP, Azure)
- Observability / tracing middleware
- Plugin registry for community tools

## Contributing

```bash
git clone https://github.com/waltervargas/agente-machete.git
cd agente-machete
uv sync --dev --extra infra
uv run pytest tests/ -v
```

The codebase is ~2,200 lines of Python. Reading `src/machete/decorators.py` and `src/machete/pipeline.py` covers the core design.

Issues and PRs welcome at [github.com/waltervargas/agente-machete](https://github.com/waltervargas/agente-machete/issues).

## License

MIT
