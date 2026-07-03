"""Smell rule engine — registry and per-sequence evaluation.

Rules are pure functions of a :class:`SequenceView` (a sequence plus the
spec-level context it needs). They read only data already present in the spec —
node markers (``dataAccess`` / ``transaction``), the sequence's aggregated
``transactions`` coverage, and ``guards`` — plus loop edges threaded from the
scanner. No new source extraction happens here.

New rules register themselves with the :func:`register` decorator and are picked
up automatically; see :mod:`flowdoc.rules` for the import wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from flowdoc.spec import Node, Sequence, Smell, Spec


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------

def reachable(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    """All node ids reachable from ``start`` (inclusive), cycle-safe."""
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adjacency.get(cur, []))
    return seen


# ---------------------------------------------------------------------------
# Per-sequence view handed to each rule
# ---------------------------------------------------------------------------

@dataclass
class SequenceView:
    """Precomputed context for evaluating one sequence.

    Attributes:
        seq: The sequence under evaluation.
        nodes_by_id: Global node lookup.
        adjacency: Global call adjacency (from → [to]).
        loop_edges: (caller, callee) pairs whose call site sits inside a loop.
        tree: Node ids reachable from the sequence entry (inclusive).
        tx_covered: Node ids covered by any transaction on this sequence.
        guarded_nodes: Guard-holding node ids that fall within the tree.
        guard_covered: Node ids protected by a guard within this sequence.
    """

    seq: Sequence
    nodes_by_id: dict[str, Node]
    adjacency: dict[str, list[str]]
    loop_edges: set[tuple[str, str]]
    tree: set[str]
    tx_covered: set[str]
    guarded_nodes: set[str]
    guard_covered: set[str]

    def data_access(self, node_id: str) -> Optional[str]:
        """Return "read"/"write"/None for a node's markers.dataAccess."""
        node = self.nodes_by_id.get(node_id)
        if node and node.markers:
            return node.markers.dataAccess
        return None

    def opens_transaction(self, node_id: str) -> bool:
        """Whether the node itself opens a transaction boundary."""
        node = self.nodes_by_id.get(node_id)
        return bool(node and node.markers and node.markers.transaction)

    def label(self, node_id: str) -> str:
        """Human-friendly name for a node (simpleName, id fallback)."""
        node = self.nodes_by_id.get(node_id)
        return node.simpleName if node and node.simpleName else node_id


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

Rule = Callable[[SequenceView], list[Smell]]
_REGISTRY: "dict[str, Rule]" = {}


def register(name: str) -> Callable[[Rule], Rule]:
    """Register a rule function under ``name`` (single responsibility per rule)."""
    def decorator(fn: Rule) -> Rule:
        if name in _REGISTRY:
            raise ValueError(f"duplicate rule registration: {name}")
        _REGISTRY[name] = fn
        return fn
    return decorator


def registered_rules() -> "dict[str, Rule]":
    """Return a copy of the rule registry (name → function)."""
    return dict(_REGISTRY)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _build_view(
    seq: Sequence,
    nodes_by_id: dict[str, Node],
    adjacency: dict[str, list[str]],
    loop_edges: set[tuple[str, str]],
    guards: list,
) -> SequenceView:
    tree = reachable(seq.entry, adjacency)

    tx_covered: set[str] = set()
    for tx in seq.transactions:
        for nid in tx.get("covers", []):
            tx_covered.add(nid)

    guarded_nodes = {g.nodeId for g in guards if g.nodeId in tree}
    guard_covered: set[str] = set()
    for nid in guarded_nodes:
        guard_covered |= reachable(nid, adjacency) & tree

    return SequenceView(
        seq=seq,
        nodes_by_id=nodes_by_id,
        adjacency=adjacency,
        loop_edges=loop_edges,
        tree=tree,
        tx_covered=tx_covered,
        guarded_nodes=guarded_nodes,
        guard_covered=guard_covered,
    )


def run_rules(
    spec: Spec,
    loop_edges: Optional[set[tuple[str, str]]] = None,
) -> Spec:
    """Evaluate every registered rule against every sequence and attach smells.

    Mutates each sequence's ``smells`` in place (``None`` when clean, so the wire
    format stays additive) and returns the same spec for convenience.

    Args:
        spec: The assembled spec to analyse.
        loop_edges: (caller, callee) pairs whose call site is inside a loop.
            Optional — rules that need it (query_in_loop) simply find nothing
            when it is absent (e.g. when re-analysing a bare spec JSON).
    """
    loop_edges = loop_edges or set()
    nodes_by_id = {n.id: n for n in spec.nodes}

    adjacency: dict[str, list[str]] = {}
    for edge in spec.edges:
        adjacency.setdefault(edge.from_id, []).append(edge.to_id)

    rules = registered_rules()
    for seq in spec.sequences:
        view = _build_view(seq, nodes_by_id, adjacency, loop_edges, spec.guards)
        smells: list[Smell] = []
        seen: set[tuple[str, str]] = set()
        for name, rule in rules.items():
            for smell in rule(view):
                key = (smell.rule, smell.nodeId)
                if key not in seen:
                    seen.add(key)
                    smells.append(smell)
        seq.smells = smells or None

    return spec
