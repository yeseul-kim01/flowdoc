"""Rule: a write reached outside any transaction boundary (atomicity smell).

Promotes the UI's "write outside a transaction" badge to a spec-level rule. A
write node is flagged when it neither opens a transaction itself nor is covered
by any transaction aggregated onto the sequence (``transactions[].covers``).
"""

from __future__ import annotations

from flowdoc.rules.engine import SequenceView, register
from flowdoc.spec import Smell

RULE = "tx_outside_write"


@register(RULE)
def check(view: SequenceView) -> list[Smell]:
    smells: list[Smell] = []
    for node_id in view.tree:
        if view.data_access(node_id) != "write":
            continue
        if view.opens_transaction(node_id):
            continue  # the write itself owns a transaction
        if node_id in view.tx_covered:
            continue  # covered by an ancestor's transaction
        smells.append(Smell(
            rule=RULE,
            nodeId=node_id,
            severity="warn",
            message=(
                f"Write in {view.label(node_id)} occurs outside any transaction "
                f"boundary — not atomic if it fails partway."
            ),
        ))
    return smells
