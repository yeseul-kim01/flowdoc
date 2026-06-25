"""FlowDoc runtime decorators.

All decorators are no-ops at runtime; the scanner detects them statically.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

_FLOW_ENTRY_ATTR = "__flowdoc_entry__"

F = TypeVar("F", bound=Callable)


def flow_entry(tag: str) -> Callable[[F], F]:
    """Mark a function as a FlowDoc sequence entry point with the given tag.

    The scanner detects this decorator statically; the runtime wrapper is a no-op.
    """
    def decorator(func: F) -> F:
        setattr(func, _FLOW_ENTRY_ATTR, tag)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        setattr(wrapper, _FLOW_ENTRY_ATTR, tag)
        return wrapper  # type: ignore[return-value]

    return decorator


def guarded(resource: str, permits: int = 1) -> Callable[[F], F]:
    """Mark a function as protected by a concurrency guard (semaphore).

    Args:
        resource: Logical resource name (e.g. "inventory").
        permits: Maximum concurrent permits (default 1).
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator


def flow_external(func: F) -> F:
    """Mark a function as an external boundary call (e.g. third-party API)."""
    @functools.wraps(func)  # type: ignore[arg-type]
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)
    return wrapper  # type: ignore[return-value]


def flow_ignore(func: F) -> F:
    """Exclude a function from FlowDoc output (noise reduction)."""
    @functools.wraps(func)  # type: ignore[arg-type]
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)
    return wrapper  # type: ignore[return-value]


def flow_doc(description: str) -> Callable[[F], F]:
    """Attach a human-readable description to a function for FlowDoc output.

    Args:
        description: Short description shown in the FlowDoc viewer.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator
