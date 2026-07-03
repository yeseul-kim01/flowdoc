"""`diff` — compare two FlowDoc documents.

Summarises what changed between an old and a new flowdoc.json across the axes
that matter for review: sequences added/removed, node/edge counts, data-access
and guard markers, and recorded smells (from the rule engine).

Usage:
    python -m flowdoc diff <old.json> <new.json> [--format text|md] [--exit-code]

CI integration is left to the caller: `--exit-code` returns 1 when anything
changed, so a pipeline can post the `--format md` output as a PR comment and
fail the check on drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from flowdoc.commands.loader import load_doc

# Stable display order for known rules; unknown rules follow, sorted.
_RULE_ORDER = ["tx_outside_write", "query_in_loop", "unguarded_shared_write"]


def _markers(node: dict) -> dict:
    return node.get("markers") or {}


def _metrics(doc: dict) -> dict:
    """Extract comparable metrics from a flowdoc document."""
    nodes = doc.get("nodes", [])
    smells: Counter = Counter()
    for seq in doc.get("sequences", []):
        for sm in seq.get("smells") or []:
            smells[sm.get("rule", "?")] += 1
    return {
        "nodes": len(nodes),
        "edges": len(doc.get("edges", [])),
        "sequences": len(doc.get("sequences", [])),
        "guards": len(doc.get("guards", [])),
        "writes": sum(1 for n in nodes if _markers(n).get("dataAccess") == "write"),
        "reads": sum(1 for n in nodes if _markers(n).get("dataAccess") == "read"),
        "smells": smells,
    }


def _seq_tags(doc: dict) -> Counter:
    return Counter(s.get("tag", "") for s in doc.get("sequences", []))


def _ordered_rules(*counters: Counter) -> list[str]:
    seen = set()
    for c in counters:
        seen |= set(c)
    known = [r for r in _RULE_ORDER if r in seen]
    extra = sorted(seen - set(_RULE_ORDER))
    return known + extra


def compute_diff(old: dict, new: dict) -> dict:
    """Return a structured diff between two documents."""
    old_m, new_m = _metrics(old), _metrics(new)
    old_tags, new_tags = _seq_tags(old), _seq_tags(new)

    added = sorted((new_tags - old_tags).elements())
    removed = sorted((old_tags - new_tags).elements())

    rules = _ordered_rules(old_m["smells"], new_m["smells"])
    smells = {
        r: {"old": old_m["smells"].get(r, 0), "new": new_m["smells"].get(r, 0)}
        for r in rules
    }

    def pair(key: str) -> dict:
        return {"old": old_m[key], "new": new_m[key], "delta": new_m[key] - old_m[key]}

    return {
        "sequencesAdded": added,
        "sequencesRemoved": removed,
        "nodes": pair("nodes"),
        "edges": pair("edges"),
        "sequences": pair("sequences"),
        "guards": pair("guards"),
        "writes": pair("writes"),
        "reads": pair("reads"),
        "smells": smells,
        "smellsTotal": {
            "old": sum(old_m["smells"].values()),
            "new": sum(new_m["smells"].values()),
            "delta": sum(new_m["smells"].values()) - sum(old_m["smells"].values()),
        },
    }


def has_changes(diff: dict) -> bool:
    """Whether any tracked axis changed."""
    if diff["sequencesAdded"] or diff["sequencesRemoved"]:
        return True
    for key in ("nodes", "edges", "guards", "writes", "reads"):
        if diff[key]["delta"] != 0:
            return True
    return diff["smellsTotal"]["delta"] != 0


def _sign(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def _fmt_pair(label: str, p: dict, width: int = 22) -> str:
    arrow = "" if p["delta"] == 0 else f"  ({_sign(p['delta'])})"
    return f"  {label:<{width}} {p['old']:>4} → {p['new']:<4}{arrow}"


def format_text(diff: dict) -> str:
    lines = ["FlowDoc diff", "============"]

    lines.append("")
    lines.append(f"Sequences: {_sign(len(diff['sequencesAdded']))} added, "
                 f"-{len(diff['sequencesRemoved'])} removed "
                 f"({diff['sequences']['old']} → {diff['sequences']['new']})")
    for tag in diff["sequencesAdded"]:
        lines.append(f"  + {tag}")
    for tag in diff["sequencesRemoved"]:
        lines.append(f"  - {tag}")

    lines.append("")
    lines.append("Graph:")
    lines.append(_fmt_pair("nodes", diff["nodes"]))
    lines.append(_fmt_pair("edges", diff["edges"]))

    lines.append("")
    lines.append("Markers:")
    lines.append(_fmt_pair("writes", diff["writes"]))
    lines.append(_fmt_pair("reads", diff["reads"]))
    lines.append(_fmt_pair("guards", diff["guards"]))

    lines.append("")
    lines.append("Smells (recorded):")
    for rule, v in diff["smells"].items():
        delta = v["new"] - v["old"]
        arrow = "" if delta == 0 else f"  ({_sign(delta)})"
        lines.append(f"  {rule:<22} {v['old']:>4} → {v['new']:<4}{arrow}")
    lines.append(_fmt_pair("total", diff["smellsTotal"]))

    if not has_changes(diff):
        lines.append("")
        lines.append("No differences.")
    return "\n".join(lines)


def _md_row(label: str, p: dict) -> str:
    delta = _sign(p["delta"]) if p["delta"] else "—"
    return f"| {label} | {p['old']} | {p['new']} | {delta} |"


def format_md(diff: dict) -> str:
    lines = ["## FlowDoc diff", ""]

    if diff["sequencesAdded"] or diff["sequencesRemoved"]:
        lines.append("**Sequences**")
        for tag in diff["sequencesAdded"]:
            lines.append(f"- 🟢 added: `{tag}`")
        for tag in diff["sequencesRemoved"]:
            lines.append(f"- 🔴 removed: `{tag}`")
        lines.append("")

    lines.append("| metric | old | new | Δ |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(_md_row("sequences", diff["sequences"]))
    lines.append(_md_row("nodes", diff["nodes"]))
    lines.append(_md_row("edges", diff["edges"]))
    lines.append(_md_row("writes", diff["writes"]))
    lines.append(_md_row("reads", diff["reads"]))
    lines.append(_md_row("guards", diff["guards"]))
    for rule, v in diff["smells"].items():
        p = {"old": v["old"], "new": v["new"], "delta": v["new"] - v["old"]}
        lines.append(_md_row(f"smell: {rule}", p))
    lines.append(_md_row("smells (total)", diff["smellsTotal"]))
    lines.append("")
    lines.append("_No differences._" if not has_changes(diff) else "")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m flowdoc diff",
        description="Compare two flowdoc.json documents.",
    )
    parser.add_argument("old", type=Path, help="Baseline flowdoc.json.")
    parser.add_argument("new", type=Path, help="Updated flowdoc.json.")
    parser.add_argument("--format", choices=("text", "md"), default="text",
                        help="Output format (default: text).")
    parser.add_argument("--exit-code", action="store_true",
                        help="Return 1 when anything changed (for CI gating).")
    args = parser.parse_args(argv)

    try:
        old = load_doc(args.old)
        new = load_doc(args.new)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2

    diff = compute_diff(old, new)
    print(format_md(diff) if args.format == "md" else format_text(diff))

    if args.exit_code and has_changes(diff):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
