"""FlowDoc spec v0.1 dataclasses and JSON serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Param:
    """A single function parameter."""

    name: str
    type: str  # type hint string or "_" if unannotated


@dataclass
class Returns:
    """Function return type."""

    type: str


@dataclass
class AnnotationAttr:
    """Key-value attribute on an annotation."""

    name: str
    value: str


@dataclass
class NodeAnnotation:
    """A decorator/annotation attached to a node."""

    name: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Auto:
    """Auto-extracted metadata from source analysis."""

    params: list[Param] = field(default_factory=list)
    returns: Returns | None = None
    annotations: list[NodeAnnotation] = field(default_factory=list)


@dataclass
class Declared:
    """Manually declared metadata (e.g. docstring description)."""

    description: str | None = None



@dataclass
class Markers:
    """Structural markers on a node (data access, transaction boundary, …)."""

    transaction: dict | None = None
    dataAccess: str | None = None  # "read" | "write"

@dataclass
class Location:
    """Source location of a node."""

    file: str
    line: int


@dataclass
class Node:
    """A function or method node in the call graph."""

    id: str
    simpleName: str
    owner: str  # class name or module name
    kind: str   # always "method" in MVP
    location: Location
    auto: Auto = field(default_factory=Auto)
    declared: Declared | None = None
    markers: Markers | None = None


@dataclass
class Edge:
    """A directed call edge between two nodes."""

    from_id: str
    to_id: str
    callType: str  # always "sync" in MVP
    site: Location
    resolution: str  # "concrete" | "single-impl"


@dataclass
class Trigger:
    """Language-neutral description of how a sequence is entered.

    Collectors map their framework's annotations onto this; the UI renders
    from kind/label only — never from framework annotation names directly.
    """

    kind: str  # "http" | "scheduled" | "messaging" | "event" | "websocket"
    label: str | None = None
    detail: dict[str, str] = field(default_factory=dict)


@dataclass
class Smell:
    """A structural smell attached to a sequence, anchored on the offending node.

    Derived purely from existing markers (data access, transactions, guards) by
    the rule engine — no new source extraction. Absent (``None``) on clean
    sequences so the wire format stays additive.
    """

    rule: str        # rule identifier, e.g. "tx_outside_write"
    nodeId: str      # node the smell is anchored on
    severity: str    # "warn" | "error"
    message: str


@dataclass
class Sequence:
    """An entry-point tagged sequence (from @flow_entry or auto-detected route)."""

    tag: str
    entry: str  # node id of the entry point
    source: str = "auto"  # "declared" (@flow_entry) | "auto" (framework annotation)
    trigger: Trigger | None = None
    transactions: list[Any] = field(default_factory=list)
    smells: list[Any] | None = None  # populated by the rule engine; None when clean


@dataclass
class Guard:
    """A concurrency guard protecting a node (semaphore / lock)."""

    nodeId: str
    type: str  # "semaphore" | "lock"
    resource: str
    permits: int | None = None
    source: str = "auto"  # "declared" (@guarded) | "auto" (sync primitive usage)


@dataclass
class Source:
    """Describes the source language/framework/collector."""

    language: str = "python"
    framework: str = "fastapi"
    collector: str = "static"


@dataclass
class Spec:
    """Top-level FlowDoc specification."""

    flowdoc: str = "0.1"
    source: Source = field(default_factory=Source)
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    sequences: list[Sequence] = field(default_factory=list)
    guards: list[Any] = field(default_factory=list)
    traces: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _clean(obj: Any) -> Any:
    """Recursively clean None values and rename 'from_id'/'to_id' for the wire format."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if v is None:
                continue
            wire_key = {"from_id": "from", "to_id": "to"}.get(k, k)
            out[wire_key] = _clean(v)
        return out
    if isinstance(obj, list):
        return [_clean(i) for i in obj]
    return obj


def spec_to_dict(spec: Spec) -> dict[str, Any]:
    """Convert a Spec to a JSON-serializable dict matching the wire format."""
    return _clean(asdict(spec))


def spec_to_json(spec: Spec, indent: int = 2) -> str:
    """Serialize a Spec to a JSON string."""
    return json.dumps(spec_to_dict(spec), ensure_ascii=False, indent=indent)
