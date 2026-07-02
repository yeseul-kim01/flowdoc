"""Unit tests for builder.py — sequence source/trigger extraction."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# trigger kinds — websocket / scheduled / event / messaging (Issue #2)
# ---------------------------------------------------------------------------

def _seq_by_kind(spec, kind):
    return next((s for s in spec.sequences if s.trigger and s.trigger.kind == kind), None)


def test_websocket_route_trigger(tmp_path: Path) -> None:
    """@router.websocket → kind='websocket', label 'WS · {prefixed path}'."""
    spec = _scan(tmp_path, ("ws.py", """
        from fastapi import APIRouter
        router = APIRouter(prefix="/ws")

        @router.websocket("/live")
        async def live_updates(campaign_id: int) -> None:
            pass
    """))
    seq = _seq_by_kind(spec, "websocket")
    assert seq is not None
    assert seq.trigger.label == "WS · /ws/live"
    assert seq.trigger.detail == {"destination": "/ws/live"}
    assert seq.source == "auto"


def test_websocket_like_decorator_not_detected(tmp_path: Path) -> None:
    """A decorator merely resembling websocket (websocket_connect) is not a trigger."""
    spec = _scan(tmp_path, ("ws.py", """
        @app.websocket_connect
        async def handler() -> None:
            pass
    """))
    assert _seq_by_kind(spec, "websocket") is None


def test_repeat_every_scheduled_trigger(tmp_path: Path) -> None:
    """@repeat_every(seconds=60) → kind='scheduled', rate in ms (Java form)."""
    spec = _scan(tmp_path, ("jobs.py", """
        from fastapi_utils.tasks import repeat_every

        @repeat_every(seconds=60)
        def refresh_cache() -> None:
            pass
    """))
    seq = _seq_by_kind(spec, "scheduled")
    assert seq is not None
    assert seq.trigger.label == "Scheduled · rate 60000ms"
    assert seq.trigger.detail == {"fixedRate": "60000"}


def test_repeat_every_non_constant_falls_back_plain(tmp_path: Path) -> None:
    """A non-constant seconds= keeps a plain 'Scheduled' label (no invented detail)."""
    spec = _scan(tmp_path, ("jobs.py", """
        from fastapi_utils.tasks import repeat_every

        @repeat_every(seconds=INTERVAL)
        def refresh_cache() -> None:
            pass
    """))
    seq = _seq_by_kind(spec, "scheduled")
    assert seq is not None
    assert seq.trigger.label == "Scheduled"
    assert seq.trigger.detail == {}


def test_on_event_startup_trigger(tmp_path: Path) -> None:
    """@app.on_event("startup") → kind='event', label 'Event · startup'."""
    spec = _scan(tmp_path, ("lifecycle.py", """
        @app.on_event("startup")
        async def warm_up() -> None:
            pass
    """))
    seq = _seq_by_kind(spec, "event")
    assert seq is not None
    assert seq.trigger.label == "Event · startup"
    assert seq.trigger.detail == {"event": "startup"}


def test_on_event_like_decorator_not_detected(tmp_path: Path) -> None:
    """A decorator merely resembling on_event is not a trigger."""
    spec = _scan(tmp_path, ("lifecycle.py", """
        @app.on_events
        async def warm_up() -> None:
            pass
    """))
    assert _seq_by_kind(spec, "event") is None


def test_shared_task_messaging_trigger(tmp_path: Path) -> None:
    """Celery @shared_task → kind='messaging', broker Celery."""
    spec = _scan(tmp_path, ("workers.py", """
        from celery import shared_task

        @shared_task(queue="emails")
        def send_email(to: str) -> None:
            pass
    """))
    seq = _seq_by_kind(spec, "messaging")
    assert seq is not None
    assert seq.trigger.label == "Celery · emails"
    assert seq.trigger.detail == {"broker": "Celery", "destination": "emails"}


def test_celery_app_task_receiver_required(tmp_path: Path) -> None:
    """@celery_app.task is detected; a generic @app.task receiver is not (miss > false positive)."""
    spec = _scan(tmp_path, ("workers.py", """
        @celery_app.task
        def process() -> None:
            pass

        @app.task
        def not_a_task() -> None:
            pass
    """))
    msgs = [s for s in spec.sequences if s.trigger and s.trigger.kind == "messaging"]
    assert len(msgs) == 1
    assert msgs[0].entry.endswith("#process()")


# ---------------------------------------------------------------------------
# markers.transaction — node markers + wire serialization
# ---------------------------------------------------------------------------

def _node(spec, simple_name):
    return next(n for n in spec.nodes if n.simpleName == simple_name)


def test_transactional_write_node_has_both_markers(tmp_path: Path) -> None:
    """A write inside `with session.begin()` → markers.transaction + dataAccess='write'."""
    spec = _scan(tmp_path, ("repo.py", """
        def save(session, obj):
            with session.begin():
                session.add(obj)
    """))
    node = _node(spec, "save")
    assert node.markers is not None
    assert node.markers.transaction == {"boundary": "open", "propagation": None}
    assert node.markers.dataAccess == "write"


def test_write_without_transaction_has_no_tx_marker(tmp_path: Path) -> None:
    """A write with no boundary → dataAccess='write', transaction is None (the smell)."""
    spec = _scan(tmp_path, ("repo.py", """
        def save(session, obj):
            session.add(obj)
    """))
    node = _node(spec, "save")
    assert node.markers is not None
    assert node.markers.dataAccess == "write"
    assert node.markers.transaction is None


def test_plain_node_has_no_markers(tmp_path: Path) -> None:
    """A function touching neither data nor a transaction gets markers=None."""
    spec = _scan(tmp_path, ("utils.py", """
        def add(a: int, b: int) -> int:
            return a + b
    """))
    assert _node(spec, "add").markers is None


def test_transaction_marker_serialized_to_wire(tmp_path: Path) -> None:
    """spec_to_dict emits markers.transaction and drops the null propagation."""
    spec = _scan(tmp_path, ("repo.py", """
        def save(session, obj):
            with session.begin():
                session.add(obj)
    """))
    d = spec_to_dict(spec)
    node = next(n for n in d["nodes"] if n["simpleName"] == "save")
    assert node["markers"]["transaction"] == {"boundary": "open"}
    assert node["markers"]["dataAccess"] == "write"
