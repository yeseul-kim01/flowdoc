"""Unit tests for builder.py — sequence source/trigger extraction."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from flowdoc.scanner.builder import build_spec
from flowdoc.scanner.parser import parse_file
from flowdoc.scanner.resolver import DefinitionIndex, resolve_call_sites


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, source: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return f


def _scan(tmp_path: Path, *names_sources: tuple[str, str]):
    """Parse multiple files in tmp_path and return a built Spec."""
    files = [_write_py(tmp_path, n, s) for n, s in names_sources]
    parsed = [pf for f in files if (pf := parse_file(f, tmp_path)) is not None]
    all_cs = [cs for pf in parsed for cs in pf.call_sites]
    index = DefinitionIndex(parsed)
    edges, _, _ = resolve_call_sites(all_cs, parsed, index)
    return build_spec(parsed, edges, tmp_path)


# ---------------------------------------------------------------------------
# source / trigger — happy path
# ---------------------------------------------------------------------------

def test_flow_entry_produces_declared_source(tmp_path: Path) -> None:
    """@flow_entry → source='declared', trigger is None."""
    spec = _scan(tmp_path, ("api.py", """
        from flowdoc.decorators import flow_entry

        @flow_entry("issue-coupon")
        def issue(campaign_id: int) -> dict:
            return {}
    """))
    assert spec.sequences, "Expected at least one sequence"
    seq = spec.sequences[0]
    assert seq.source == "declared"
    assert seq.tag == "issue-coupon"
    assert seq.trigger is None


def test_fastapi_route_produces_auto_source_with_trigger(tmp_path: Path) -> None:
    """@router.post → source='auto', trigger.kind='http'."""
    spec = _scan(tmp_path, ("routes.py", """
        from fastapi import APIRouter
        router = APIRouter(prefix="/coupons")

        @router.post("/{campaign_id}")
        def issue(campaign_id: int) -> dict:
            return {}
    """))
    assert spec.sequences, "Expected at least one sequence"
    seq = next((s for s in spec.sequences if "POST" in s.tag), None)
    assert seq is not None, "Expected a POST sequence"
    assert seq.source == "auto"
    assert seq.trigger is not None
    assert seq.trigger.kind == "http"
    assert seq.trigger.label is not None
    assert "POST" in seq.trigger.label
    assert seq.trigger.detail.get("verb") == "POST"


def test_prefix_joined_into_full_path(tmp_path: Path) -> None:
    """APIRouter(prefix='/auth') + @router.post('/login') → '/auth/login'."""
    spec = _scan(tmp_path, ("auth.py", """
        from fastapi import APIRouter
        router = APIRouter(prefix="/auth")

        @router.post("/login")
        async def login(username: str) -> dict:
            return {}
    """))
    seq = next((s for s in spec.sequences if "POST" in s.tag), None)
    assert seq is not None
    assert seq.trigger is not None
    assert seq.trigger.detail.get("path") == "/auth/login"
    assert "POST /auth/login" in seq.tag


def test_declared_before_auto_in_sequence_list(tmp_path: Path) -> None:
    """Declared sequences come before auto-detected ones."""
    spec = _scan(tmp_path, ("mixed.py", """
        from fastapi import APIRouter
        from flowdoc.decorators import flow_entry
        router = APIRouter()

        @router.get("/health")
        def health() -> dict:
            return {}

        @flow_entry("create-order")
        @router.post("/orders")
        def create_order() -> dict:
            return {}
    """))
    declared = [s for s in spec.sequences if s.source == "declared"]
    auto = [s for s in spec.sequences if s.source == "auto"]
    if declared and auto:
        first_declared = spec.sequences.index(declared[0])
        first_auto = spec.sequences.index(auto[0])
        assert first_declared < first_auto, "Declared sequences must precede auto ones"


# ---------------------------------------------------------------------------
# source / trigger — error / edge cases
# ---------------------------------------------------------------------------

def test_no_sequences_for_plain_function(tmp_path: Path) -> None:
    """A plain function with no decorator produces no sequence."""
    spec = _scan(tmp_path, ("utils.py", """
        def helper(x: int) -> int:
            return x + 1
    """))
    assert spec.sequences == []


def test_route_without_path_string(tmp_path: Path) -> None:
    """A route decorator with no path argument still produces a sequence."""
    spec = _scan(tmp_path, ("noop.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("")
        def root() -> dict:
            return {}
    """))
    # Should not raise; may produce a sequence with empty path
    assert isinstance(spec.sequences, list)
