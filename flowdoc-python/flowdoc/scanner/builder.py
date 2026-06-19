"""Build a FlowDoc Spec from parsed definitions and resolved edges."""

from __future__ import annotations

import logging
from pathlib import Path

from flowdoc.scanner.parser import FunctionDef, ParsedFile
from flowdoc.scanner.resolver import ResolvedEdge
from flowdoc.spec import (
    Auto,
    Declared,
    Edge,
    Location,
    Node,
    NodeAnnotation,
    Param,
    Returns,
    Sequence,
    Source,
    Spec,
)

logger = logging.getLogger(__name__)

# Decorator names that mark FastAPI route handlers (indicate a flow entry)
_FASTAPI_ROUTE_DECORATOR_NAMES: frozenset[str] = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options", "api_route",
})

# Decorator names for the @flow_entry decorator
_FLOW_ENTRY_NAMES: frozenset[str] = frozenset({"flow_entry"})


def _relative_path(file: Path, root: Path) -> str:
    """Return POSIX-style relative path from root, or absolute fallback."""
    try:
        return file.relative_to(root).as_posix()
    except ValueError:
        return file.as_posix()


def _build_node(defn: FunctionDef, root: Path) -> Node:
    """Convert a FunctionDef to a FlowDoc Node."""
    params = [Param(name=p.name, type=p.type_hint) for p in defn.params]
    returns = Returns(type=defn.return_type) if defn.return_type else None
    annotations = [
        NodeAnnotation(name=ann.name, attributes=ann.attributes)
        for ann in defn.annotations
    ]
    auto = Auto(params=params, returns=returns, annotations=annotations)
    declared = Declared(description=defn.description) if defn.description else None

    return Node(
        id=defn.node_id,
        simpleName=defn.simple_name,
        owner=defn.owner,
        kind="method",
        location=Location(file=_relative_path(defn.file, root), line=defn.line),
        auto=auto,
        declared=declared,
    )


def _build_edge(edge: ResolvedEdge, root: Path) -> Edge:
    """Convert a ResolvedEdge to a FlowDoc Edge."""
    return Edge(
        from_id=edge.caller_id,
        to_id=edge.callee_id,
        callType="sync",
        site=Location(file=_relative_path(Path(edge.file), root), line=edge.line),
        resolution=edge.resolution,
    )


def _extract_sequences(parsed_files: list[ParsedFile]) -> list[Sequence]:
    """Scan all definitions for @flow_entry or FastAPI route decorators to build sequences."""
    sequences: list[Sequence] = []

    for pf in parsed_files:
        for defn in pf.definitions:
            # Check for @flow_entry(tag="...")
            for ann in defn.annotations:
                if ann.name in _FLOW_ENTRY_NAMES:
                    tag = ann.attributes.get("tag") or ann.attributes.get("value") or defn.simple_name
                    # Strip surrounding quotes from string literals
                    tag = tag.strip("\"'")
                    sequences.append(Sequence(tag=tag, entry=defn.node_id))
                    break

            # Check for FastAPI route decorators if no @flow_entry
            else:
                for ann in defn.annotations:
                    if ann.name in _FASTAPI_ROUTE_DECORATOR_NAMES:
                        # Use the HTTP method + path as the tag
                        path = ann.attributes.get("value", "").strip("\"'")
                        tag = f"{ann.name.upper()} {path}" if path else ann.name.upper()
                        sequences.append(Sequence(tag=tag, entry=defn.node_id))
                        break

    return sequences


def build_spec(
    parsed_files: list[ParsedFile],
    resolved_edges: list[ResolvedEdge],
    root: Path,
) -> Spec:
    """Assemble the final FlowDoc Spec from all parsed and resolved data.

    Args:
        parsed_files: All successfully parsed files.
        resolved_edges: Resolved call edges.
        root: Project root directory (for relative path computation).

    Returns:
        A populated Spec instance ready for serialization.
    """
    nodes: list[Node] = []
    seen_ids: set[str] = set()

    for pf in parsed_files:
        for defn in pf.definitions:
            if defn.node_id not in seen_ids:
                nodes.append(_build_node(defn, root))
                seen_ids.add(defn.node_id)

    edges: list[Edge] = []
    seen_edges: set[tuple[str, str]] = set()
    for re in resolved_edges:
        key = (re.caller_id, re.callee_id)
        if key not in seen_edges:
            edges.append(_build_edge(re, root))
            seen_edges.add(key)

    sequences = _extract_sequences(parsed_files)

    logger.info(
        "builder: %d nodes, %d edges, %d sequences",
        len(nodes), len(edges), len(sequences),
    )

    return Spec(
        source=Source(language="python", framework="fastapi", collector="static"),
        nodes=nodes,
        edges=edges,
        sequences=sequences,
        guards=[],
        traces=[],
    )
