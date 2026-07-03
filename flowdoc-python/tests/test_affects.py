"""Tests for the `affects` reverse-impact CLI."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from flowdoc.commands.affects import analyze, main
from flowdoc.scanner.builder import build_spec
from flowdoc.scanner.parser import parse_file
from flowdoc.scanner.resolver import DefinitionIndex, resolve_call_sites
from flowdoc.spec import spec_to_dict

FIXTURE = """
    from fastapi import APIRouter
    router = APIRouter(prefix="/auth")

    @router.post("/register")
    def register(session) -> dict:
        hash_password("x")
        return {}

    @router.post("/login")
    def login(session) -> dict:
        verify(session)
        return {}

    def verify(session):
        hash_password("y")

    def hash_password(raw: str) -> str:
        return raw
"""


def _doc(tmp_path: Path) -> dict:
    f = tmp_path / "auth.py"
    f.write_text(textwrap.dedent(FIXTURE), encoding="utf-8")
    parsed = [parse_file(f, tmp_path)]
    cs = [c for pf in parsed for c in pf.call_sites]
    index = DefinitionIndex(parsed)
    edges, _, _ = resolve_call_sites(cs, parsed, index)
    return spec_to_dict(build_spec(parsed, edges, tmp_path))


# ---------------------------------------------------------------------------
# hit — a shared helper reached (in)directly from two entry points
# ---------------------------------------------------------------------------

def test_affects_finds_all_reaching_sequences(tmp_path: Path) -> None:
    doc = _doc(tmp_path)
    result = analyze(doc, "hash_password")
    assert len(result["matchedNodes"]) == 1
    tags = {s["tag"] for s in result["affectedSequences"]}
    # register calls it directly; login reaches it via verify()
    assert any("register" in t for t in tags)
    assert any("login" in t for t in tags)


def test_affects_transitive_via_helper(tmp_path: Path) -> None:
    """Reverse BFS crosses the intermediate verify() node to reach /login."""
    doc = _doc(tmp_path)
    result = analyze(doc, "hash_password")
    login = next(s for s in result["affectedSequences"] if "login" in s["tag"])
    assert login["trigger"]["kind"] == "http"


# ---------------------------------------------------------------------------
# miss — an unknown symbol matches nothing
# ---------------------------------------------------------------------------

def test_affects_unknown_symbol_is_empty(tmp_path: Path) -> None:
    doc = _doc(tmp_path)
    result = analyze(doc, "does_not_exist")
    assert result["matchedNodes"] == []
    assert result["affectedSequences"] == []


# ---------------------------------------------------------------------------
# CLI surface — exit code + json format
# ---------------------------------------------------------------------------

def test_affects_cli_json(tmp_path: Path, capsys) -> None:
    doc = _doc(tmp_path)
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    rc = main(["hash_password", str(path), "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "hash_password"
    assert payload["affectedSequences"]


def test_affects_cli_missing_file(tmp_path: Path) -> None:
    rc = main(["hash_password", str(tmp_path / "nope.json")])
    assert rc == 1
