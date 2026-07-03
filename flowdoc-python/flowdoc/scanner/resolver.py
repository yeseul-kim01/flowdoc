"""Resolve call sites to concrete node IDs using a two-pass index.

Resolution rules
----------------
concrete    : receiver has a type hint that maps to a known class owner, OR
              call is a bare-name import resolved to exactly one definition, OR
              call target can be derived from from-import mapping to one def.
single-impl : no type context, but exactly one project-internal definition
              shares the callee name.
dropped     : ambiguous (2+ candidates without type context), or external
              (stdlib / third-party — not found in the project index).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from flowdoc.scanner.parser import CallSite, FunctionDef, ParsedFile

logger = logging.getLogger(__name__)


@dataclass
class ResolvedEdge:
    caller_id: str
    callee_id: str
    resolution: str   # "concrete" | "single-impl"
    file: str
    line: int
    in_loop: bool = False  # the originating call site sits inside a loop


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------

class DefinitionIndex:
    """In-memory index of all function definitions across the project."""

    def __init__(self, parsed_files: list[ParsedFile]) -> None:
        # node_id → FunctionDef
        self._by_id: dict[str, FunctionDef] = {}
        # simple_name → list[FunctionDef]  (for single-impl lookup)
        self._by_name: dict[str, list[FunctionDef]] = {}
        # (owner, simple_name) → list[FunctionDef]  (for class method lookup)
        self._by_owner_name: dict[tuple[str, str], list[FunctionDef]] = {}
        # from-import name → FunctionDef  (for "from x import y" lookups)
        self._from_import_to_def: dict[str, list[FunctionDef]] = {}

        for pf in parsed_files:
            for defn in pf.definitions:
                self._by_id[defn.node_id] = defn
                self._by_name.setdefault(defn.simple_name, []).append(defn)
                key = (defn.owner, defn.simple_name)
                self._by_owner_name.setdefault(key, []).append(defn)

        # Build from-import reverse map from each file
        for pf in parsed_files:
            for local_name, full_name in pf.from_imports.items():
                # full_name is like "app.services.auth_service.create_access_token"
                # We try to match it against node_ids or simple_names
                func_name = full_name.split(".")[-1]
                if func_name in self._by_name:
                    self._from_import_to_def.setdefault(local_name, []).extend(
                        self._by_name[func_name]
                    )

    def lookup_by_id(self, node_id: str) -> Optional[FunctionDef]:
        """Return the definition for an exact node_id, or None."""
        return self._by_id.get(node_id)

    def lookup_by_name(self, name: str) -> list[FunctionDef]:
        """Return all definitions matching a simple function name."""
        return self._by_name.get(name, [])

    def lookup_by_owner_name(self, owner: str, name: str) -> list[FunctionDef]:
        """Return definitions matching (owner_class, simple_name)."""
        return self._by_owner_name.get((owner, name), [])

    def lookup_from_import(self, local_name: str) -> list[FunctionDef]:
        """Return definitions reachable via from-import with the given local name."""
        return self._from_import_to_def.get(local_name, [])

    def all_ids(self) -> set[str]:
        """Return all known node IDs."""
        return set(self._by_id.keys())


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

def _extract_base_type(type_str: str) -> str:
    """Strip generics and Optional wrappers: 'Optional[Foo]' → 'Foo', 'list[Bar]' → 'Bar'."""
    s = type_str.strip()
    # Handle Optional[X], Union[X, None], etc.
    for wrapper in ("Optional[", "Annotated["):
        if s.startswith(wrapper):
            s = s[len(wrapper):-1].split(",")[0].strip()
    # Handle list[X], List[X]
    if "[" in s:
        s = s.split("[")[-1].rstrip("]")
    # Strip module prefix: app.models.user.UserRecord → UserRecord
    return s.split(".")[-1]


def resolve_call_sites(
    call_sites: list[CallSite],
    parsed_files: list[ParsedFile],
    index: DefinitionIndex,
) -> tuple[list[ResolvedEdge], int, int]:
    """Resolve call sites to edges using the definition index.

    Returns:
        (resolved_edges, n_dropped_ambiguous, n_dropped_external)
    """
    # Build a fast lookup: file_path → ParsedFile
    file_to_pf: dict[str, ParsedFile] = {str(pf.file): pf for pf in parsed_files}

    resolved: list[ResolvedEdge] = []
    n_ambiguous = 0
    n_external = 0

    for cs in call_sites:
        # Avoid self-loops (direct recursive calls to same id)
        pf = file_to_pf.get(str(cs.file))
        caller_def = index.lookup_by_id(cs.caller_id)
        if caller_def is None:
            continue

        callee_id: Optional[str] = None
        resolution: Optional[str] = None

        # ----------------------------------------------------------------
        # Strategy 1: receiver has a type hint in the caller's local_types
        # ----------------------------------------------------------------
        if cs.callee_receiver and caller_def:
            receiver_type = caller_def.local_types.get(cs.callee_receiver)
            if receiver_type:
                base_type = _extract_base_type(receiver_type)
                candidates = index.lookup_by_owner_name(base_type, cs.callee_name)
                if len(candidates) == 1:
                    callee_id = candidates[0].node_id
                    resolution = "concrete"
                elif len(candidates) > 1:
                    # Multiple overloads with same owner+name — take first
                    callee_id = candidates[0].node_id
                    resolution = "concrete"

        # ----------------------------------------------------------------
        # Strategy 2: from-import resolution (bare call, no receiver)
        # ----------------------------------------------------------------
        if callee_id is None and cs.callee_receiver is None and pf:
            fi_candidates = pf.from_imports.get(cs.callee_name)
            if fi_candidates:
                # Try to match to a known definition
                func_name = fi_candidates.split(".")[-1]
                defs = index.lookup_by_name(func_name)
                # Filter to those whose module path ends with the import prefix
                import_module = ".".join(fi_candidates.split(".")[:-1])
                matching = [d for d in defs if d.node_id.startswith(import_module + ".")]
                if not matching:
                    matching = defs
                if len(matching) == 1:
                    callee_id = matching[0].node_id
                    resolution = "concrete"
                elif len(matching) > 1:
                    # ambiguous: multiple overloads for the imported name
                    logger.debug(
                        "resolver: ambiguous from-import '%s' → %d candidates, dropping (caller=%s)",
                        cs.callee_name, len(matching), cs.caller_id,
                    )
                    n_ambiguous += 1
                    continue

        # ----------------------------------------------------------------
        # Strategy 3: bare name lookup by simple_name (single-impl rule)
        # ----------------------------------------------------------------
        if callee_id is None:
            name_candidates = index.lookup_by_name(cs.callee_name)
            if len(name_candidates) == 0:
                logger.debug(
                    "resolver: external call '%s' dropped (caller=%s line=%d)",
                    cs.callee_name, cs.caller_id, cs.line,
                )
                n_external += 1
                continue
            elif len(name_candidates) == 1:
                callee_id = name_candidates[0].node_id
                resolution = "single-impl"
            else:
                logger.debug(
                    "resolver: ambiguous '%s' → %d candidates, dropping (caller=%s)",
                    cs.callee_name, len(name_candidates), cs.caller_id,
                )
                n_ambiguous += 1
                continue

        if callee_id and resolution:
            resolved.append(ResolvedEdge(
                caller_id=cs.caller_id,
                callee_id=callee_id,
                resolution=resolution,
                file=str(cs.file),
                line=cs.line,
                in_loop=cs.in_loop,
            ))

    return resolved, n_ambiguous, n_external
