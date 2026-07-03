"""FlowDoc smell rule engine.

Importing this package registers the built-in rules (via their module-level
``@register`` decorators) and exposes :func:`run_rules`. Add a new rule by
dropping a module here and importing it below.
"""

from __future__ import annotations

from flowdoc.rules.engine import registered_rules, run_rules

# Import rule modules for their registration side effects.
from flowdoc.rules import (  # noqa: E402,F401  (side-effect imports)
    query_in_loop,
    tx_outside_write,
    unguarded_shared_write,
)

__all__ = ["run_rules", "registered_rules"]
