"""Rule: a data-access node called inside a loop (possible N+1).

Uses the loop flag threaded from the scanner (call sites inside for/while) and
the existing ``markers.dataAccess``: a loop edge whose callee touches the data
layer is a classic N+1 candidate. Anchored on the data-access node, with the
looping caller named in the message.
"""

from __future__ import annotations

from flowdoc.rules.engine import SequenceView, register
from flowdoc.spec import Smell

RULE = "query_in_loop"


@register(RULE)
def check(view: SequenceView) -> list[Smell]:
    smells: list[Smell] = []
    reported: set[tuple[str, str]] = set()
    for caller, callee in view.loop_edges:
        if caller not in view.tree or callee not in view.tree:
            continue
        if view.data_access(callee) is None:
            continue
        key = (caller, callee)
        if key in reported:
            continue
        reported.add(key)
        smells.append(Smell(
            rule=RULE,
            nodeId=callee,
            severity="warn",
            message=(
                f"Data access {view.label(callee)} is called inside a loop in "
                f"{view.label(caller)} — possible N+1."
            ),
        ))
    return smells
