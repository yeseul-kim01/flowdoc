"""`affects` — reverse impact analysis.

Given a symbol, find every entry-point sequence whose call tree reaches it, by
walking the edge graph backwards from the matching nodes. Answers "if I change
this function, which flows are affected?".

Usage:
    python -m flowdoc affects <symbol> <flowdoc.json> [--format text|json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flowdoc.commands.loader import (
    load_doc,
    match_nodes,
    reverse_adjacency,
    reverse_reachable,
)


def analyze(doc: dict, symbol: str) -> dict:
    """Compute the impact of *symbol* within *doc*.

    Returns a result dict: {symbol, matchedNodes, affectedSequences}. Affected
    sequences are those whose entry can reach a matching node (sorted by tag).
    """
    matched = match_nodes(doc, symbol)
    rev = reverse_adjacency(doc)
    upstream = reverse_reachable(matched, rev)

    affected = [
        {
            "tag": seq.get("tag"),
            "entry": seq.get("entry"),
            "trigger": seq.get("trigger"),
        }
        for seq in doc.get("sequences", [])
        if seq.get("entry") in upstream
    ]
    affected.sort(key=lambda s: (s.get("tag") or ""))

    return {
        "symbol": symbol,
        "matchedNodes": matched,
        "affectedSequences": affected,
    }


def _trigger_label(trigger: dict | None) -> str:
    if not trigger:
        return "-"
    kind = trigger.get("kind", "?")
    label = trigger.get("label")
    return f"{kind}: {label}" if label else kind


def format_text(result: dict, source: str) -> str:
    lines: list[str] = []
    matched = result["matchedNodes"]
    lines.append(f"Symbol '{result['symbol']}' → {len(matched)} matching node(s) in {source}")
    for nid in matched:
        lines.append(f"  · {nid}")
    if not matched:
        lines.append("  (no nodes match — nothing to analyze)")
        return "\n".join(lines)

    affected = result["affectedSequences"]
    lines.append("")
    lines.append(f"Affected sequences: {len(affected)}")
    for seq in affected:
        lines.append(f"  → {seq['tag']}   [{_trigger_label(seq.get('trigger'))}]")
    if not affected:
        lines.append("  (no entry-point sequence reaches this symbol)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m flowdoc affects",
        description="Reverse impact analysis: which sequences reach a symbol.",
    )
    parser.add_argument("symbol", help="Function/method name (or full node id) to trace.")
    parser.add_argument("flowdoc", type=Path, help="Path to a flowdoc.json document.")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args(argv)

    try:
        doc = load_doc(args.flowdoc)
    except FileNotFoundError:
        print(f"error: file not found: {args.flowdoc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot read {args.flowdoc}: {exc}", file=sys.stderr)
        return 1

    result = analyze(doc, args.symbol)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result, str(args.flowdoc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
