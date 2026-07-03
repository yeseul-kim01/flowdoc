"""Tests for the `diff` CLI — change present vs identical documents."""

from __future__ import annotations

import json
from pathlib import Path

from flowdoc.commands.diff import compute_diff, format_md, has_changes, main


def _doc(**over) -> dict:
    base = {
        "flowdoc": "0.1",
        "nodes": [],
        "edges": [],
        "sequences": [],
        "guards": [],
    }
    base.update(over)
    return base


OLD = _doc(
    nodes=[
        {"id": "m#a()", "simpleName": "a"},
        {"id": "m#w()", "simpleName": "w", "markers": {"dataAccess": "write"}},
    ],
    edges=[{"from": "m#a()", "to": "m#w()"}],
    sequences=[{"tag": "GET /old", "entry": "m#a()"}],
    guards=[],
)

NEW = _doc(
    nodes=[
        {"id": "m#a()", "simpleName": "a"},
        {"id": "m#w()", "simpleName": "w", "markers": {"dataAccess": "write"}},
        {"id": "m#g()", "simpleName": "g"},
    ],
    edges=[{"from": "m#a()", "to": "m#w()"}],
    sequences=[
        {"tag": "GET /old", "entry": "m#a()",
         "smells": [{"rule": "tx_outside_write", "nodeId": "m#w()",
                     "severity": "warn", "message": "x"}]},
        {"tag": "POST /new", "entry": "m#g()"},
    ],
    guards=[{"nodeId": "m#g()", "type": "lock", "resource": "r"}],
)


# ---------------------------------------------------------------------------
# change present
# ---------------------------------------------------------------------------

def test_diff_detects_changes() -> None:
    d = compute_diff(OLD, NEW)
    assert has_changes(d)
    assert d["sequencesAdded"] == ["POST /new"]
    assert d["sequencesRemoved"] == []
    assert d["nodes"]["delta"] == 1
    assert d["guards"]["delta"] == 1
    assert d["smells"]["tx_outside_write"] == {"old": 0, "new": 1}
    assert d["smellsTotal"]["delta"] == 1


def test_diff_md_lists_added_sequence() -> None:
    md = format_md(compute_diff(OLD, NEW))
    assert "## FlowDoc diff" in md
    assert "POST /new" in md
    assert "| smell: tx_outside_write | 0 | 1 | +1 |" in md


# ---------------------------------------------------------------------------
# identical
# ---------------------------------------------------------------------------

def test_diff_identical_has_no_changes() -> None:
    d = compute_diff(NEW, NEW)
    assert not has_changes(d)
    assert d["sequencesAdded"] == []
    assert d["nodes"]["delta"] == 0
    assert d["smellsTotal"]["delta"] == 0


def test_diff_cli_exit_code(tmp_path: Path) -> None:
    old_p = tmp_path / "old.json"
    new_p = tmp_path / "new.json"
    old_p.write_text(json.dumps(OLD), encoding="utf-8")
    new_p.write_text(json.dumps(NEW), encoding="utf-8")

    # identical → exit-code 0
    assert main([str(new_p), str(new_p), "--exit-code"]) == 0
    # changed → exit-code 1
    assert main([str(old_p), str(new_p), "--exit-code"]) == 1
    # without --exit-code, always 0
    assert main([str(old_p), str(new_p)]) == 0


def test_diff_cli_missing_file(tmp_path: Path) -> None:
    assert main([str(tmp_path / "nope.json"), str(tmp_path / "nope2.json")]) == 2
