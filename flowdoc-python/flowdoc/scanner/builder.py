"""Build a FlowDoc Spec from parsed definitions and resolved edges."""

from __future__ import annotations

import logging
from pathlib import Path

from flowdoc.rules import run_rules
from flowdoc.scanner.parser import FunctionDef, ParsedFile
from flowdoc.scanner.resolver import ResolvedEdge
from flowdoc.spec import (
    Auto,
    Declared,
    Markers,
    Edge,
    Guard,
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

# WebSocket route decorators: @app.websocket("/path") / @router.websocket_route("/path")
_WEBSOCKET_ATTRS: frozenset[str] = frozenset({"websocket", "websocket_route"})

# Scheduled decorators: fastapi-utils @repeat_every(seconds=N), APScheduler @scheduler.scheduled_job(...)
_SCHEDULED_ATTRS: frozenset[str] = frozenset({"repeat_every", "scheduled_job"})

# Lifecycle event decorators: @app.on_event("startup") / @router.on_event("shutdown")
_EVENT_ATTRS: frozenset[str] = frozenset({"on_event"})

# Celery task decorators: @shared_task always; @<celery*>.task only when the receiver
# names a celery app — an unknown `obj.task` is more likely a false positive than a task.
_MESSAGING_BARE_ATTRS: frozenset[str] = frozenset({"shared_task"})
_MESSAGING_RECEIVER_ATTR: str = "task"


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
    if defn.data_access or defn.transaction:
        markers = Markers(transaction=defn.transaction, dataAccess=defn.data_access)
    else:
        markers = None

    return Node(
        id=defn.node_id,
        simpleName=defn.simple_name,
        owner=defn.owner,
        kind="method",
        location=Location(file=_relative_path(defn.file, root), line=defn.line),
        auto=auto,
        declared=declared,
        markers=markers,
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


def _http_trigger(ann, module_path: str, prefix_map: dict[tuple[str, str], str]) -> Trigger:
    """FastAPI route decorator → kind='http' (label/detail mirror the Java collector)."""
    verb = ann.name.upper()
    route_path = ann.attributes.get("value", "").strip("\"'")
    receiver = ann.attributes.get("__receiver__")
    path = _full_path(receiver, route_path, module_path, prefix_map)
    detail = {"verb": verb}
    if path:
        detail["path"] = path
    return Trigger(kind=_HTTP_KIND, label=f"{verb} {path}" if path else verb, detail=detail)


def _websocket_trigger(ann, module_path: str, prefix_map: dict[tuple[str, str], str]) -> Trigger:
    """@app.websocket("/path") → kind='websocket', label 'WS · {path}'."""
    route_path = ann.attributes.get("value", "").strip("\"'")
    receiver = ann.attributes.get("__receiver__")
    dest = _full_path(receiver, route_path, module_path, prefix_map)
    detail = {"destination": dest} if dest else {}
    return Trigger(kind="websocket", label=f"WS · {dest}" if dest else "WebSocket", detail=detail)


def _scheduled_trigger(ann) -> Trigger:
    """@repeat_every(seconds=N) / APScheduler @scheduled_job → kind='scheduled'.

    Mirrors the Java collector: fixedRate is expressed in ms ("Scheduled · rate 60000ms");
    a schedule we cannot express as a constant stays a plain "Scheduled".
    """
    detail: dict[str, str] = {}
    when = ""
    seconds = ann.attributes.get("seconds")
    if seconds is not None:
        try:
            ms = int(float(seconds) * 1000)
            when = f"rate {ms}ms"
            detail["fixedRate"] = str(ms)
        except ValueError:
            pass  # non-constant seconds= expression — emit plain "Scheduled"
    return Trigger(kind="scheduled", label=f"Scheduled · {when}" if when else "Scheduled", detail=detail)


def _event_trigger(ann) -> Trigger:
    """@app.on_event("startup"/"shutdown") → kind='event', label 'Event · {type}'."""
    event_type = ann.attributes.get("value", "").strip("\"'")
    detail = {"event": event_type} if event_type else {}
    return Trigger(kind="event", label=f"Event · {event_type}" if event_type else "Event", detail=detail)


def _messaging_trigger(ann) -> Trigger:
    """Celery @shared_task / @celery_app.task → kind='messaging', broker 'Celery'."""
    dest = ann.attributes.get("queue", "").strip("\"'")
    detail = {"broker": "Celery"}
    if dest:
        detail["destination"] = dest
    return Trigger(kind="messaging", label=f"Celery · {dest}" if dest else "Celery", detail=detail)


def _trigger_for(
    defn: FunctionDef,
    module_path: str,
    prefix_map: dict[tuple[str, str], str],
) -> Trigger | None:
    """Map a function's decorators to a language-neutral Trigger (mirrors Java triggerFor).

    Only confident FastAPI-ecosystem patterns are mapped — a miss is better
    than a false trigger. Returns the first match in decorator order.
    """
    for ann in defn.annotations:
        if ann.name in _HTTP_METHODS:
            return _http_trigger(ann, module_path, prefix_map)
        if ann.name in _WEBSOCKET_ATTRS:
            return _websocket_trigger(ann, module_path, prefix_map)
        if ann.name in _SCHEDULED_ATTRS:
            return _scheduled_trigger(ann)
        if ann.name in _EVENT_ATTRS:
            return _event_trigger(ann)
        if ann.name in _MESSAGING_BARE_ATTRS:
            return _messaging_trigger(ann)
        if ann.name == _MESSAGING_RECEIVER_ATTR:
            receiver = ann.attributes.get("__receiver__", "")
            if "celery" in receiver.lower():
                return _messaging_trigger(ann)
    return None


def _extract_sequences(
    parsed_files: list[ParsedFile],
    prefix_map: dict[tuple[str, str], str],
) -> list[Sequence]:
    """Build Sequence entries from @flow_entry and framework trigger decorators.

    Rules:
    - @flow_entry("tag") → source="declared", tag from argument; trigger still
      read from any framework decorator on the same function (Java parity)
    - a recognised trigger decorator (HTTP route, websocket, scheduled, event,
      Celery task) → source="auto", tag=trigger.label

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
                    trigger=_trigger_for(defn, pf.module_path, prefix_map),
                ))
                matched = True
                break

            if matched:
                continue

            # ── framework triggers (http / websocket / scheduled / event / messaging) ──
            trigger = _trigger_for(defn, pf.module_path, prefix_map)
            if trigger is not None:
                auto_seqs.append(Sequence(
                    tag=trigger.label or defn.simple_name,
                    entry=defn.node_id,
                    source="auto",
                    trigger=trigger,
                ))

    return declared_seqs + auto_seqs


def _extract_guards(parsed_files: list[ParsedFile]) -> list[Guard]:
    """Collect concurrency guards (Java-parity shape: nodeId/type/resource/permits/source).

    - @guarded(resource=, permits=) → source="declared" (mirrors Java @Guarded)
    - `with`/`async with` on an asyncio/threading Semaphore/Lock variable
      → source="auto", resource = variable name, permits captured for constants only
    """
    guards: list[Guard] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(guard: Guard) -> None:
        key = (guard.nodeId, guard.type, guard.resource)
        if key not in seen:
            seen.add(key)
            guards.append(guard)

    for pf in parsed_files:
        for defn in pf.definitions:
            for ann in defn.annotations:
                if ann.name != "guarded":
                    continue
                resource = (ann.attributes.get("resource") or ann.attributes.get("value") or "").strip("\"'")
                permits_str = ann.attributes.get("permits", "")
                permits = int(permits_str) if permits_str.isdigit() else 1
                _add(Guard(
                    nodeId=defn.node_id,
                    type="semaphore",
                    resource=resource or defn.simple_name,
                    permits=permits,
                    source="declared",
                ))
            for var in defn.guard_uses:
                gv = pf.guard_vars.get(var)
                if gv is None:
                    continue
                _add(Guard(
                    nodeId=defn.node_id,
                    type=gv["type"],
                    resource=var,
                    permits=gv.get("permits"),
                    source="auto",
                ))
    return guards


def _reachable_from(start: str, adjacency: dict[str, list[str]]) -> list[str]:
    """All node ids reachable from start (inclusive), DFS order, cycle-safe."""
    seen: set[str] = set()
    order: list[str] = []
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        order.append(cur)
        stack.extend(reversed(adjacency.get(cur, [])))
    return order


def _sequence_transactions(
    entry: str,
    adjacency: dict[str, list[str]],
    tx_open_ids: set[str],
) -> list[dict]:
    """Aggregate transaction coverage for one sequence tree (Issue #4).

    Every node in the sequence tree whose markers.transaction.boundary is
    "open" becomes an owner; covers is its whole call subtree (owner included).
    Nested boundaries (begin_nested) each get their own entry — the inner
    owner also appears inside the outer covers.
    """
    transactions: list[dict] = []
    for node_id in _reachable_from(entry, adjacency):
        if node_id in tx_open_ids:
            transactions.append({
                "owner": node_id,
                "covers": _reachable_from(node_id, adjacency),
            })
    return transactions


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

    # Aggregate per-sequence transaction coverage from markers (Issue #4)
    adjacency: dict[str, list[str]] = {}
    for e in edges:
        adjacency.setdefault(e.from_id, []).append(e.to_id)
    tx_open_ids = {
        n.id for n in nodes
        if n.markers and n.markers.transaction and n.markers.transaction.get("boundary") == "open"
    }
    for seq in sequences:
        seq.transactions = _sequence_transactions(seq.entry, adjacency, tx_open_ids)

    logger.info(
        "builder: %d nodes, %d edges, %d sequences (%d declared, %d auto)",
        len(nodes), len(edges), len(sequences),
        sum(1 for s in sequences if s.source == "declared"),
        sum(1 for s in sequences if s.source == "auto"),
    )

    guards = _extract_guards(parsed_files)

    spec = Spec(
        source=Source(language="python", framework="fastapi", collector="static"),
        nodes=nodes,
        edges=edges,
        sequences=sequences,
        guards=guards,
        traces=[],
    )

    # Run the smell rule engine over the assembled spec. Loop edges are derived
    # from resolved call sites (for/while nesting); everything else the rules
    # need is already on the spec (markers, transactions, guards).
    loop_edges = {
        (re.caller_id, re.callee_id) for re in resolved_edges if re.in_loop
    }
    run_rules(spec, loop_edges)

    return spec
