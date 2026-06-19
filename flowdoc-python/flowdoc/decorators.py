"""FlowDoc decorator: @flow_entry."""

from __future__ import annotations

import functools
from typing import Callable, TypeVar

_FLOW_ENTRY_ATTR = "__flowdoc_entry__"

F = TypeVar("F", bound=Callable)


def flow_entry(tag: str) -> Callable[[F], F]:
    """Mark a function as a FlowDoc sequence entry point with the given tag.

    The scanner detects this decorator statically; the runtime wrapper is a no-op.
    """
    def decorator(func: F) -> F:
        setattr(func, _FLOW_ENTRY_ATTR, tag)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            return func(*args, **kwargs)

        setattr(wrapper, _FLOW_ENTRY_ATTR, tag)
        return wrapper  # type: ignore[return-value]

    return decorator
