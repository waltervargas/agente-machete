"""Core type definitions and Protocols (weak typeclasses).

Protocols here serve as PEP 544 structural subtyping — the closest Python
gets to typeclasses. They define the *interface* of each algebra without
requiring inheritance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# LLM message types
# ---------------------------------------------------------------------------

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """An LLM-requested tool invocation."""
    id: str
    name: str
    arguments: dict[str, Any]


class LLMMessage(BaseModel):
    """A single message in a conversation."""
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = []
    tool_call_id: str | None = None
    name: str | None = None


class LLMResponse(BaseModel):
    """Response from an LLM provider."""
    message: LLMMessage
    usage: dict[str, int] = {}
    model: str = ""
    stop_reason: str | None = None


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    """Declarative agent configuration — what a data scientist specifies."""
    name: str
    description: str = ""
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.0
    max_tokens: int = 4096
    max_iterations: int = 10
    system_prompt: str = ""


# ---------------------------------------------------------------------------
# Error algebra — sum type of all agent errors
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMError:
    """LLM provider returned an error."""
    message: str
    provider: str = ""
    status_code: int | None = None


@dataclass(frozen=True)
class ToolError:
    """A tool invocation failed."""
    tool_name: str
    message: str
    original: Exception | None = None


@dataclass(frozen=True)
class ValidationError:
    """Input or output validation failed."""
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineError:
    """Pipeline composition or execution error."""
    message: str
    step_name: str = ""


# The sum type — every monadic Failure carries one of these.
AgentError = LLMError | ToolError | ValidationError | PipelineError


# ---------------------------------------------------------------------------
# Tool Protocol — the weak typeclass for tools
# ---------------------------------------------------------------------------

class ToolParameter(BaseModel):
    """JSON Schema-compatible parameter description."""
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None


@runtime_checkable
class ToolSpec(Protocol):
    """Protocol (typeclass) for anything that behaves as a tool.

    Decorating a function with @tool makes it satisfy this protocol.
    """

    @property
    def tool_name(self) -> str: ...

    @property
    def tool_description(self) -> str: ...

    @property
    def tool_parameters(self) -> Sequence[ToolParameter]: ...

    def __call__(self, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Metadata tag — attached by decorators for infra analysis
# ---------------------------------------------------------------------------

class ResourceHint(str, Enum):
    """Hints the infra analyzer uses to infer cloud resources."""
    LAMBDA = "lambda"
    API_GATEWAY = "api_gateway"
    SQS = "sqs"
    DYNAMODB = "dynamodb"
    EVENTBRIDGE = "eventbridge"
    S3 = "s3"


@dataclass(frozen=True)
class MacheteMeta:
    """Metadata attached to decorated objects via __machete_meta__."""
    kind: str  # "agent", "tool", or "step"
    name: str
    config: AgentConfig | None = None
    tools: tuple[Any, ...] = ()
    schedule: str | None = None  # cron expression
    queue: bool = False
    resource_hints: tuple[ResourceHint, ...] = ()
