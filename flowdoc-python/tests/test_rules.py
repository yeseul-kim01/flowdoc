"""Unit tests for the smell rule engine (rules/). One hit + one miss per rule."""

from __future__ import annotations

import textwrap
from pathlib import Path

from flowdoc.rules import registered_rules
from flowdoc.scanner.builder import build_spec
from flowdoc.scanner.parser import parse_file
from flowdoc.scanner.resolver import DefinitionIndex, resolve_call_sites
from flowdoc.spec import spec_to_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, source: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return f


def _scan(tmp_path: Path, *names_sources: tuple[str, str]):
    files = [_write_py(tmp_path, n, s) for n, s in names_sources]
    parsed = [pf for f in files if (pf := parse_file(f, tmp_path)) is not None]
    all_cs = [cs for pf in parsed for cs in pf.call_sites]
    index = DefinitionIndex(parsed)
    edges, _, _ = resolve_call_sites(all_cs, parsed, index)
    return build_spec(parsed, edges, tmp_path)


def _smells(spec, rule: str) -> list:
    out = []
    for seq in spec.sequences:
        for sm in (seq.smells or []):
            if sm.rule == rule:
                out.append(sm)
    return out


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def test_all_three_rules_registered() -> None:
    names = set(registered_rules())
    assert {"tx_outside_write", "query_in_loop", "unguarded_shared_write"} <= names


# ---------------------------------------------------------------------------
# tx_outside_write
# ---------------------------------------------------------------------------

def test_tx_outside_write_flags_uncovered_write(tmp_path: Path) -> None:
    """A write with no surrounding transaction is flagged."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/orders")
        def create_order(session) -> dict:
            write_log(session)
            return {}

        def write_log(session) -> None:
            session.add(1)
    """))
    hits = _smells(spec, "tx_outside_write")
    assert len(hits) == 1
    assert hits[0].nodeId.endswith("#write_log(_)")
    assert hits[0].severity == "warn"


def test_tx_outside_write_clean_when_covered(tmp_path: Path) -> None:
    """A write inside `with session.begin()` produces no tx_outside_write."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/orders")
        def create_order(session) -> dict:
            save_row(session)
            return {}

        def save_row(session) -> None:
            with session.begin():
                session.add(1)
    """))
    assert _smells(spec, "tx_outside_write") == []


# ---------------------------------------------------------------------------
# query_in_loop
# ---------------------------------------------------------------------------

def test_query_in_loop_flags_data_access_in_loop(tmp_path: Path) -> None:
    """A data-access call inside a for-loop is flagged as possible N+1."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/report")
        def report(session, ids) -> dict:
            for i in ids:
                fetch_row(session)
            return {}

        def fetch_row(session):
            return session.get(1)
    """))
    hits = _smells(spec, "query_in_loop")
    assert len(hits) == 1
    assert hits[0].nodeId.endswith("#fetch_row(_)")
    assert "N+1" in hits[0].message


def test_query_in_loop_clean_when_not_looped(tmp_path: Path) -> None:
    """The same data-access call outside a loop is not flagged."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/report")
        def report(session) -> dict:
            fetch_row(session)
            return {}

        def fetch_row(session):
            return session.get(1)
    """))
    assert _smells(spec, "query_in_loop") == []


def test_query_in_loop_ignores_loop_iterable(tmp_path: Path) -> None:
    """`for row in fetch_rows(...)` evaluates the query once — not N+1."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/report")
        def report(session) -> dict:
            for row in fetch_rows(session):
                pass
            return {}

        def fetch_rows(session):
            return session.scalars(1)
    """))
    assert _smells(spec, "query_in_loop") == []


# ---------------------------------------------------------------------------
# unguarded_shared_write
# ---------------------------------------------------------------------------

def test_unguarded_shared_write_flags_write_outside_guard(tmp_path: Path) -> None:
    """In a guarded sequence, a write outside every guard is flagged as error."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        from flowdoc.decorators import guarded
        router = APIRouter()

        @router.post("/reserve")
        def reserve(session) -> dict:
            take_lock()
            persist(session)
            return {}

        @guarded(resource="stock", permits=1)
        def take_lock() -> None:
            pass

        def persist(session) -> None:
            session.add(1)
    """))
    hits = _smells(spec, "unguarded_shared_write")
    assert len(hits) == 1
    assert hits[0].nodeId.endswith("#persist(_)")
    assert hits[0].severity == "error"


def test_unguarded_shared_write_silent_without_guards(tmp_path: Path) -> None:
    """A sequence with no guard at all does not raise unguarded_shared_write."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/reserve")
        def reserve(session) -> dict:
            persist(session)
            return {}

        def persist(session) -> None:
            session.add(1)
    """))
    assert _smells(spec, "unguarded_shared_write") == []


# ---------------------------------------------------------------------------
# wire serialization — smells are additive (absent when clean)
# ---------------------------------------------------------------------------

def test_clean_sequence_omits_smells_key(tmp_path: Path) -> None:
    """A clean sequence serializes without a `smells` key (additive)."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict:
            return {}
    """))
    d = spec_to_dict(spec)
    seq = next(s for s in d["sequences"] if "GET" in s["tag"])
    assert "smells" not in seq


def test_smells_serialized_when_present(tmp_path: Path) -> None:
    """A smell round-trips to the wire dict with all four fields."""
    spec = _scan(tmp_path, ("app.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/orders")
        def create_order(session) -> dict:
            write_log(session)
            return {}

        def write_log(session) -> None:
            session.add(1)
    """))
    d = spec_to_dict(spec)
    seq = next(s for s in d["sequences"] if "POST" in s["tag"])
    assert seq["smells"], "expected serialized smells"
    sm = seq["smells"][0]
    assert set(sm) == {"rule", "nodeId", "severity", "message"}
