# Agente Machete

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
$ machete synth my_agent.py
# CloudAssembly written to: cdk.out
# => Lambda functions, API Gateway, IAM roles — all generated from your @agent and @tool decorators
```

## Why Machete?

| | Machete | LangChain | CrewAI |
|---|---|---|---|
| **Define agents** | `@agent` decorator | Chain/Graph classes | Agent/Task/Crew classes |
| **Error handling** | Monadic (`IOResult`) — composable, typed | try/except | try/except |
| **Infrastructure** | Inferred from decorators, CDK synthesis | Manual (Terraform, etc.) | Manual |
| **Core deps** | 2 (returns + pydantic) | 15+ | 10+ |
| **LLM lock-in** | None — Protocol-based | Partial | Partial |

**Infrastructure From Code** is the key differentiator. Other frameworks stop at "run my agent." Machete goes from decorated Python functions to production AWS infrastructure (Lambda + API Gateway + SQS + EventBridge) with a single command. No Terraform. No SAM. No Serverless Framework.

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
machete run my_agent --input "What is 7 * 8 + 3?" --provider anthropic
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

The synthesis happens **in-process** via the AWS CDK Python SDK and jsii — no subprocess calls, no string templating, no hand-rolled CloudFormation. Machete creates real CDK constructs (`_lambda.Function`, `apigw.RestApi`, `sqs.Queue`) and lets CDK handle IAM roles, permissions, deployment stages, and all the details.

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

- **Decorators** (`@agent`, `@tool`, `@step`) — the surface API. Attach metadata for the pipeline and infra analyzer.
- **Pipeline** — the agentic loop. Calls the LLM, executes tools, feeds results back, repeats until done. Supports middleware.
- **Monads** — `AgentResult[T] = IOResult[T, AgentError]`. Errors short-circuit. Side-effects are tracked. Composition via Kleisli arrows.
- **LLM Providers** — Protocol-based (PEP 544). Swap providers with one line. No inheritance required.
- **Infra** — Analyzer reads decorator metadata, builds a ResourceGraph, synthesizes CDK constructs in-process.

## LLM Providers

### Anthropic (Claude)

```python
from machete.llm import AnthropicProvider

provider = AnthropicProvider()  # uses ANTHROPIC_API_KEY env var
# or
provider = AnthropicProvider(api_key="sk-ant-...")
```

### OpenAI

```python
from machete.llm.protocol import OpenAIProvider

provider = OpenAIProvider()  # uses OPENAI_API_KEY env var
```

### Mock (testing)

```python
from machete.llm import MockProvider
from machete.types import LLMMessage, LLMResponse, Role

provider = MockProvider(responses=[
    LLMResponse(
        message=LLMMessage(role=Role.ASSISTANT, content="Hello!"),
        model="mock",
    ),
])
```

### Custom provider

Implement the `LLMProvider` Protocol — no inheritance needed:

```python
from machete.llm import LLMProvider

class MyProvider:
    def complete(self, messages, tools=None, *, model="", temperature=0.0, max_tokens=4096):
        # Call your LLM, return IOResult[LLMResponse, AgentError]
        ...

# MyProvider satisfies LLMProvider via structural subtyping (PEP 544)
```

## Project Status

**v0.1.0** — early but functional. The full vertical slice works: define agents with decorators, run them locally, synthesize AWS infrastructure via CDK.

- 55 tests passing (unit + CDK integration)
- CI on GitHub Actions (Python 3.11, 3.12, 3.13)
- MIT licensed

### What works

- `@agent`, `@tool`, `@step` decorators with metadata inference
- Agentic loop with tool calling (LLM call -> tool exec -> repeat)
- Anthropic and OpenAI adapters
- Local execution (`run()`, Jupyter-friendly)
- Infrastructure analysis and CDK synthesis (Lambda, API Gateway, SQS, EventBridge)
- CLI (`run`, `synth`, `graph`, `deploy`)

### What's next

- Streaming responses
- Multi-agent pipelines
- State persistence (DynamoDB)
- More cloud targets (GCP, Azure)
- Observability / tracing middleware

## Contributing

```bash
git clone https://github.com/waltervargas/agente-machete.git
cd agente-machete
uv sync --dev --extra infra
uv run pytest tests/ -v
```

Issues and PRs welcome at [github.com/waltervargas/agente-machete](https://github.com/waltervargas/agente-machete/issues).

## License

MIT
