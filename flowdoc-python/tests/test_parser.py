"""Unit tests for the AST parser module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from flowdoc.scanner.parser import parse_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, source: str) -> Path:
    """Write source to a .py file and return its path."""
    f = tmp_path / name
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_parse_simple_function(tmp_path: Path) -> None:
    """A simple typed function produces the expected FunctionDef."""
    src = """
        def greet(name: str) -> str:
            return "hello " + name
    """
    f = _write_py(tmp_path, "greet.py", src)
    result = parse_file(f, tmp_path)

    assert result is not None
    assert len(result.definitions) == 1

    defn = result.definitions[0]
    assert defn.simple_name == "greet"
    assert defn.return_type == "str"
    assert len(defn.params) == 1
    assert defn.params[0].name == "name"
    assert defn.params[0].type_hint == "str"
    assert defn.node_id == "greet#greet(str)"


def test_parse_class_method_skips_self(tmp_path: Path) -> None:
    """self is excluded from params and the owner is set to the class name."""
    src = """
        class OrderService:
            def create(self, item_id: int) -> None:
                pass
    """
    f = _write_py(tmp_path, "service.py", src)
    result = parse_file(f, tmp_path)

    assert result is not None
    defn = next(d for d in result.definitions if d.simple_name == "create")
    assert defn.owner == "OrderService"
    assert all(p.name != "self" for p in defn.params)
    assert defn.node_id == "service.OrderService#create(int)"


def test_parse_untyped_param_becomes_underscore(tmp_path: Path) -> None:
    """Unannotated parameters get type hint '_'."""
    src = """
        def process(data, flag: bool) -> None:
            pass
    """
    f = _write_py(tmp_path, "proc.py", src)
    result = parse_file(f, tmp_path)
    assert result is not None
    defn = result.definitions[0]
    types = [p.type_hint for p in defn.params]
    assert "_" in types


def test_parse_decorator_captured(tmp_path: Path) -> None:
    """Decorators are captured in the annotations list."""
    src = """
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items", response_model=dict)
        async def create_item(name: str) -> dict:
            return {}
    """
    f = _write_py(tmp_path, "items.py", src)
    result = parse_file(f, tmp_path)
    assert result is not None
    defn = next(d for d in result.definitions if d.simple_name == "create_item")
    ann_names = [a.name for a in defn.annotations]
    assert "post" in ann_names


def test_parse_call_sites_captured(tmp_path: Path) -> None:
    """Call sites inside a function body are recorded."""
    src = """
        def caller():
            result = helper()
            return result

        def helper():
            return 42
    """
    f = _write_py(tmp_path, "calls.py", src)
    result = parse_file(f, tmp_path)
    assert result is not None
    callee_names = [cs.callee_name for cs in result.call_sites]
    assert "helper" in callee_names


def test_parse_docstring_extracted(tmp_path: Path) -> None:
    """The first line of a docstring is stored as description."""
    src = '''
        def documented():
            """This is the summary.

            More details here.
            """
            pass
    '''
    f = _write_py(tmp_path, "doc.py", src)
    result = parse_file(f, tmp_path)
    assert result is not None
    defn = result.definitions[0]
    assert defn.description == "This is the summary."


# ---------------------------------------------------------------------------
# Error-handling tests
# ---------------------------------------------------------------------------

def test_parse_syntax_error_returns_none(tmp_path: Path) -> None:
    """A file with a syntax error returns None (not an exception)."""
    src = "def broken(:\n    pass\n"
    f = _write_py(tmp_path, "broken.py", src)
    result = parse_file(f, tmp_path)
    assert result is None


def test_parse_nonexistent_file_returns_none(tmp_path: Path) -> None:
    """Attempting to parse a missing file returns None."""
    missing = tmp_path / "ghost.py"
    result = parse_file(missing, tmp_path)
    assert result is None
