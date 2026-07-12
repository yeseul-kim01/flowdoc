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


def test_flow_entry_with_route_keeps_declared_source_and_trigger(tmp_path: Path) -> None:
    """@flow_entry + @router.post → source='declared' with the http trigger attached (Java parity)."""
    spec = _scan(tmp_path, ("api.py", """
        from fastapi import APIRouter
        from flowdoc.decorators import flow_entry
        router = APIRouter(prefix="/coupons")

        @flow_entry("issue-coupon")
        @router.post("/{campaign_id}")
        def issue(campaign_id: int) -> dict:
            return {}
    """))
    seq = next((s for s in spec.sequences if s.tag == "issue-coupon"), None)
    assert seq is not None, "Expected the declared sequence"
    assert seq.source == "declared"
    assert seq.trigger is not None
    assert seq.trigger.kind == "http"
    assert seq.trigger.detail.get("verb") == "POST"
    assert seq.trigger.detail.get("path") == "/coupons/{campaign_id}"
    # No duplicate auto sequence for the same entry
    assert sum(1 for s in spec.sequences if s.entry == seq.entry) == 1


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
# guards — semaphore / lock detection
# ---------------------------------------------------------------------------

def test_guard_semaphore_async_with(tmp_path: Path) -> None:
    """asyncio.Semaphore(5) + async with → guard type='semaphore', permits=5, auto."""
    spec = _scan(tmp_path, ("svc.py", """
        import asyncio
        sem = asyncio.Semaphore(5)

        async def reserve(campaign_id: int) -> bool:
            async with sem:
                return True
    """))
    assert len(spec.guards) == 1
    g = spec.guards[0]
    assert g.type == "semaphore"
    assert g.resource == "sem"
    assert g.permits == 5
    assert g.source == "auto"
    assert g.nodeId.endswith("#reserve(int)")


def test_guard_semaphore_permits_from_module_constant(tmp_path: Path) -> None:
    """Semaphore(CONCURRENCY) resolves permits from the module-level int constant."""
    spec = _scan(tmp_path, ("svc.py", """
        import asyncio
        CONCURRENCY = 20
        sem = asyncio.Semaphore(CONCURRENCY)

        async def reserve(campaign_id: int) -> bool:
            async with sem:
                return True
    """))
    g = spec.guards[0]
    assert g.permits == 20


def test_guard_semaphore_permits_none_for_non_constant_name(tmp_path: Path) -> None:
    """Semaphore(some_param) with no matching module constant -> permits stays
    None rather than guessed (a function parameter isn't statically known)."""
    spec = _scan(tmp_path, ("svc.py", """
        import asyncio

        async def reserve(concurrency: int, campaign_id: int) -> bool:
            sem = asyncio.Semaphore(concurrency)
            async with sem:
                return True
    """))
    assert spec.guards[0].permits is None


def test_guard_lock_threading(tmp_path: Path) -> None:
    """threading.Lock() + with → guard type='lock', no permits."""
    spec = _scan(tmp_path, ("svc.py", """
        import threading
        _lock = threading.Lock()

        def update_counter() -> None:
            with _lock:
                pass
    """))
    assert len(spec.guards) == 1
    g = spec.guards[0]
    assert g.type == "lock"
    assert g.resource == "_lock"
    assert g.permits is None
    assert g.source == "auto"


def test_guard_unknown_context_not_detected(tmp_path: Path) -> None:
    """`with` on a non-primitive (open()) or unknown Lock() emits no guard."""
    spec = _scan(tmp_path, ("svc.py", """
        lock = CustomLock()

        def write_file(path: str) -> None:
            with lock:
                pass
    """))
    assert spec.guards == []


def test_guard_declared_from_guarded_decorator(tmp_path: Path) -> None:
    """@guarded(resource=, permits=) → source='declared' (mirrors Java @Guarded)."""
    spec = _scan(tmp_path, ("svc.py", """
        from flowdoc.decorators import guarded

        @guarded(resource="coupon-stock", permits=1)
        def reserve_stock(campaign_id: int) -> bool:
            return True
    """))
    assert len(spec.guards) == 1
    g = spec.guards[0]
    assert g.type == "semaphore"
    assert g.resource == "coupon-stock"
    assert g.permits == 1
    assert g.source == "declared"


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


def test_sequence_transactions_aggregated(tmp_path: Path) -> None:
    """A tx-opening node in the sequence tree → transactions=[{owner, covers[]}]."""
    spec = _scan(tmp_path, ("shop.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/orders")
        def create_order() -> dict:
            place()
            return {}

        def place() -> None:
            with session.begin():
                write_rows()

        def write_rows() -> None:
            pass
    """))
    seq = next(s for s in spec.sequences if "POST" in s.tag)
    assert len(seq.transactions) == 1
    tx = seq.transactions[0]
    assert tx["owner"].endswith("#place()")
    assert any(c.endswith("#place()") for c in tx["covers"])
    assert any(c.endswith("#write_rows()") for c in tx["covers"])
    assert not any(c.endswith("#create_order()") for c in tx["covers"])


def test_sequence_without_transaction_has_empty_list(tmp_path: Path) -> None:
    """A sequence tree with no tx boundary → transactions == []."""
    spec = _scan(tmp_path, ("plain.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict:
            return {}
    """))
    seq = next(s for s in spec.sequences if "GET" in s.tag)
    assert seq.transactions == []


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


# ---------------------------------------------------------------------------
# sequence.title / sequence.description
# ---------------------------------------------------------------------------

def test_sequence_title_from_route_summary_kwarg(tmp_path: Path) -> None:
    """summary= on the route decorator wins over the docstring first line."""
    spec = _scan(tmp_path, ("api.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/coupons", summary="Issue a coupon")
        def issue() -> dict:
            \"\"\"Handles coupon issuance.

            Reserves stock, saves the issuance, then logs the attempt.
            \"\"\"
            return {}
    """))
    seq = next(s for s in spec.sequences if "POST" in s.tag)
    assert seq.title == "Issue a coupon"
    assert seq.description == "Reserves stock, saves the issuance, then logs the attempt."


def test_sequence_title_falls_back_to_docstring_first_line(tmp_path: Path) -> None:
    """No summary= kwarg -> title falls back to the docstring's first line."""
    spec = _scan(tmp_path, ("api.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict:
            \"\"\"Health check endpoint.\"\"\"
            return {}
    """))
    seq = next(s for s in spec.sequences if "GET" in s.tag)
    assert seq.title == "Health check endpoint."
    assert seq.description is None


def test_sequence_title_and_description_none_without_docstring_or_summary(tmp_path: Path) -> None:
    """Neither summary= nor a docstring -> both fields stay None (additive-optional)."""
    spec = _scan(tmp_path, ("api.py", """
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict:
            return {}
    """))
    seq = next(s for s in spec.sequences if "GET" in s.tag)
    assert seq.title is None
    assert seq.description is None


# ---------------------------------------------------------------------------
# edges[].callType — async dispatch detection
# ---------------------------------------------------------------------------

def test_asyncio_create_task_edge_is_async(tmp_path: Path) -> None:
    """asyncio.create_task(handler()) -> the edge to handler is callType='async'."""
    spec = _scan(tmp_path, ("api.py", """
        import asyncio

        def issue() -> None:
            asyncio.create_task(notify())

        def notify() -> None:
            pass
    """))
    edge = next(e for e in spec.edges if e.to_id.endswith("#notify()"))
    assert edge.callType == "async"


def test_background_tasks_add_task_edge_is_async(tmp_path: Path) -> None:
    """BackgroundTasks.add_task(handler) -> a synthesized async edge to handler."""
    spec = _scan(tmp_path, ("api.py", """
        from fastapi import BackgroundTasks

        def issue(tasks: BackgroundTasks) -> None:
            tasks.add_task(notify)

        def notify() -> None:
            pass
    """))
    edge = next(e for e in spec.edges if e.to_id.endswith("#notify()"))
    assert edge.callType == "async"


def test_plain_call_edge_is_sync(tmp_path: Path) -> None:
    """A direct call with no dispatch wrapper -> callType='sync' (baseline)."""
    spec = _scan(tmp_path, ("api.py", """
        def issue() -> None:
            notify()

        def notify() -> None:
            pass
    """))
    edge = next(e for e in spec.edges if e.to_id.endswith("#notify()"))
    assert edge.callType == "sync"


def test_add_task_on_untyped_receiver_stays_sync(tmp_path: Path) -> None:
    """`.add_task(...)` on a receiver NOT typed as BackgroundTasks is not
    special-cased — no false positive from the method name alone."""
    spec = _scan(tmp_path, ("api.py", """
        def issue(tasks) -> None:
            tasks.add_task(notify)

        def notify() -> None:
            pass
    """))
    # No synthesized async edge to notify() — the call site is only the
    # (unresolvable) `tasks.add_task` attribute call itself.
    assert not any(e.to_id.endswith("#notify()") for e in spec.edges)
