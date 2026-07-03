"""Shared helpers for the analysis CLIs (affects, diff).

These operate on the raw wire dict (``from``/``to`` edge keys, node ``id`` /
``simpleName``) rather than the scanner's Spec dataclasses, so they work on any
FlowDoc document — Python or Java, static or runtime.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_doc(path: Path) -> dict:
    """Load a flowdoc.json document.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a JSON object.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a FlowDoc object")
    return data


def node_index(doc: dict) -> dict[str, dict]:
    """Map node id → node object."""
    return {n["id"]: n for n in doc.get("nodes", []) if "id" in n}


def reverse_adjacency(doc: dict) -> dict[str, list[str]]:
    """Build callee → [callers] from edges (``to`` → list of ``from``)."""
    rev: dict[str, list[str]] = {}
    for edge in doc.get("edges", []):
        frm, to = edge.get("from"), edge.get("to")
        if frm is not None and to is not None:
            rev.setdefault(to, []).append(frm)
    return rev


def match_nodes(doc: dict, symbol: str) -> list[str]:
    """Return ids of nodes matching *symbol* (case-sensitive).

    A node matches when the symbol equals its simpleName, the method component
    of its id (``…#symbol(…)``), or the full id. Order follows the document.
    """
    matched: list[str] = []
    for node in doc.get("nodes", []):
        nid = node.get("id", "")
        if (
            node.get("simpleName") == symbol
            or f"#{symbol}(" in nid
            or nid == symbol
        ):
            matched.append(nid)
    return matched


def reverse_reachable(seeds: list[str], rev: dict[str, list[str]]) -> set[str]:
    """All nodes that transitively reach any seed (seeds included), cycle-safe."""
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(rev.get(cur, []))
    return seen
