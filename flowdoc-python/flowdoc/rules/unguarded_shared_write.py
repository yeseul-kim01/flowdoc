"""Rule: a write not protected by a concurrency guard within a guarded sequence.

Fires only when the sequence establishes at least one concurrency guard
(semaphore / lock) — that is what makes its shared state "guarded" in the first
place. A write that escapes every guard's covered subtree is then flagged:
a transaction gives atomicity, not mutual exclusion, so a tx-covered write can
still be an unguarded shared write.

Restricting to guarded sequences keeps the rule quiet on read-only or lock-free
flows instead of flagging every write in the codebase.
"""

from __future__ import annotations

from flowdoc.rules.engine import SequenceView, register
from flowdoc.spec import Smell

RULE = "unguarded_shared_write"


@register(RULE)
def check(view: SequenceView) -> list[Smell]:
    if not view.guarded_nodes:
        return []  # no guarding pattern in this sequence — nothing to violate
    smells: list[Smell] = []
    for node_id in view.tree:
        if view.data_access(node_id) != "write":
            continue
        if node_id in view.guard_covered:
            continue
        smells.append(Smell(
            rule=RULE,
            nodeId=node_id,
            severity="error",
            message=(
                f"Write in {view.label(node_id)} runs without a concurrency guard "
                f"in a sequence that guards other work — potential race on shared state."
            ),
        ))
    return smells
