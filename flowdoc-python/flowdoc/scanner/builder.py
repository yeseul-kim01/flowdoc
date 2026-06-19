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
    Trigger,
)

logger = logging.getLogger(__name__)

# HTTP method decorator names recognised as FastAPI route handlers
_HTTP_METHODS: frozenset[str] = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options", "api_route",
})

# Decorator names for @flow_entry
_FLOW_ENTRY_NAMES: frozenset[str] = frozenset({"flow_entry"})

# Trigger kind for HTTP routes
_HTTP_KIND: str = "http"


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


def _build_router_prefix_map(parsed_files: list[ParsedFile]) -> dict[tuple[str, str], str]:
    """Build a lookup of (module_path, var_name) → prefix from all files.

    Args:
        parsed_files: All successfully parsed files.

    Returns:
        Mapping of (module_path, variable_name) → prefix string.
    """
    result: dict[tuple[str, str], str] = {}
    for pf in parsed_files:
        for var, prefix in pf.router_prefixes.items():
            result[(pf.module_path, var)] = prefix
    return result


def _full_path(
    receiver: str | None,
    route_path: str,
    module_path: str,
    prefix_map: dict[tuple[str, str], str],
) -> str:
    """Join APIRouter prefix with the route decorator path.

    Args:
        receiver: Variable name of the router object (e.g. "router").
        route_path: Path string from the decorator (e.g. "/items").
        module_path: Dotted module path of the defining file.
        prefix_map: Pre-built (module_path, var) → prefix lookup.

    Returns:
        Combined path string (e.g. "/auth/items").
    """
    prefix = ""
    if receiver:
        prefix = prefix_map.get((module_path, receiver), "")
    # Avoid double slashes
    if prefix and route_path:
        return prefix.rstrip("/") + "/" + route_path.lstrip("/")
    return prefix + route_path


def _extract_receiver(defn: FunctionDef, method_name: str) -> str | None:
    """Return the router variable name used in @router.post etc., or None."""
    for ann in defn.annotations:
        if ann.name == method_name:
            # Decorator was recorded as AnnotationInfo(name="post", ...)
            # The original AST was `router.post(...)`, so we need the receiver.
            # The parser stores ann.name = attr (e.g. "post"), but we need the
            # object name. We store it back via a special "__receiver__" attribute
            # added by the decorator visitor — see parser._decorator_to_info.
            return ann.attributes.get("__receiver__")
    return None


def _extract_sequences(
    parsed_files: list[ParsedFile],
    prefix_map: dict[tuple[str, str], str],
) -> list[Sequence]:
    """Build Sequence entries from @flow_entry and FastAPI route decorators.

    Rules:
    - @flow_entry("tag") → source="declared", tag from argument, trigger=None
    - HTTP route decorator → source="auto", tag="{VERB} {full_path}",
        trigger=Trigger(kind="http", label="{VERB} {full_path}",
                        detail={"verb": "VERB", "path": "/full_path"})

    Args:
        parsed_files: All parsed files.
        prefix_map: Router variable → prefix lookup built from all files.

    Returns:
        List of Sequence entries (declared first, then auto).
    """
    declared_seqs: list[Sequence] = []
    auto_seqs: list[Sequence] = []

    for pf in parsed_files:
        for defn in pf.definitions:
            matched = False

            # ── @flow_entry ─────────────────────────────────────────────
            for ann in defn.annotations:
                if ann.name not in _FLOW_ENTRY_NAMES:
                    continue
                tag = (
                    ann.attributes.get("tag")
                    or ann.attributes.get("value")
                    or defn.simple_name
                )
                tag = tag.strip("\"'")
                declared_seqs.append(Sequence(
                    tag=tag,
                    entry=defn.node_id,
                    source="declared",
                    trigger=None,
                ))
                matched = True
                break

            if matched:
                continue

            # ── FastAPI HTTP route ───────────────────────────────────────
            for ann in defn.annotations:
                if ann.name not in _HTTP_METHODS:
                    continue
                verb = ann.name.upper()
                route_path = ann.attributes.get("value", "").strip("\"'")
                receiver = ann.attributes.get("__receiver__")
                path = _full_path(receiver, route_path, pf.module_path, prefix_map)
                label = f"{verb} {path}" if path else verb
                auto_seqs.append(Sequence(
                    tag=label,
                    entry=defn.node_id,
                    source="auto",
                    trigger=Trigger(
                        kind=_HTTP_KIND,
                        label=label,
                        detail={"verb": verb, "path": path},
                    ),
                ))
                break

    return declared_seqs + auto_seqs


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

    prefix_map = _build_router_prefix_map(parsed_files)
    sequences = _extract_sequences(parsed_files, prefix_map)

    logger.info(
        "builder: %d nodes, %d edges, %d sequences (%d declared, %d auto)",
        len(nodes), len(edges), len(sequences),
        sum(1 for s in sequences if s.source == "declared"),
        sum(1 for s in sequences if s.source == "auto"),
    )

    return Spec(
        source=Source(language="python", framework="fastapi", collector="static"),
        nodes=nodes,
        edges=edges,
        sequences=sequences,
        guards=[],
        traces=[],
    )
