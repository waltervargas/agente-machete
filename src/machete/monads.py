"""Monadic layer — Result-based pipelines over the `returns` library.

Key CT mapping:
  - IOResult = IO + Result  (side-effects + error handling in one monad)
  - flow / bind            = Kleisli composition
  - safe_step decorator    = natural transformation (plain fn → monadic fn)
  - flow_steps             = catamorphism over a list of Kleisli arrows
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeAlias, TypeVar

from returns.io import IOFailure, IOResult, IOSuccess, impure_safe
from returns.pipeline import flow
from returns.pointfree import bind

from machete.types import AgentError, PipelineError

# ---------------------------------------------------------------------------
# Core type alias — the One Monad to rule the framework
# ---------------------------------------------------------------------------

T = TypeVar("T")
U = TypeVar("U")
P = ParamSpec("P")

AgentResult: TypeAlias = IOResult[T, AgentError]
"""Every framework operation returns this: IO + Result with typed errors."""


# ---------------------------------------------------------------------------
# Lifting helpers
# ---------------------------------------------------------------------------


def success(value: T) -> AgentResult[T]:
    """Lift a pure value into a successful AgentResult."""
    return IOSuccess(value)


def failure(error: AgentError) -> AgentResult[Any]:
    """Lift an error into a failed AgentResult."""
    return IOFailure(error)


# ---------------------------------------------------------------------------
# safe_step — natural transformation from plain functions to monadic
# ---------------------------------------------------------------------------


def safe_step(
    name: str = "",
) -> Callable[[Callable[P, T]], Callable[P, AgentResult[T]]]:
    """Decorator: wraps a function so exceptions become Failure(AgentError).

    This is a *natural transformation*: it maps from the identity functor
    (plain Python functions) to the IOResult functor (monadic functions).

    Usage::

        @safe_step("fetch_data")
        def fetch(url: str) -> dict:
            return requests.get(url).json()

        result: AgentResult[dict] = fetch("https://...")
        # Success(dict) or Failure(PipelineError)
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, AgentResult[T]]:
        step_name = name or fn.__name__

        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> AgentResult[T]:
            # impure_safe captures any exception into IOResult
            @impure_safe
            def _run() -> T:
                return fn(*args, **kwargs)

            result = _run()
            # Map the generic Exception into our AgentError algebra
            return result.alt(  # type: ignore[return-value]
                lambda exc: PipelineError(
                    message=str(exc),
                    step_name=step_name,
                )
            )

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# flow_steps — Kleisli composition of monadic steps
# ---------------------------------------------------------------------------


def flow_steps(
    initial: AgentResult[T],
    *steps: Callable[[Any], AgentResult[Any]],
) -> AgentResult[Any]:
    """Compose monadic steps via Kleisli composition (bind chaining).

    This is a catamorphism over the list of steps — folding them into
    a single monadic computation that short-circuits on first Failure.

    Usage::

        result = flow_steps(
            success(input_data),
            validate,
            enrich,
            summarize,
        )
    """
    if not steps:
        return initial
    return flow(initial, *[bind(s) for s in steps])  # type: ignore[arg-type]
