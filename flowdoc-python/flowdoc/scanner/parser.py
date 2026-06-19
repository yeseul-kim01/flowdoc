"""AST parser: index function/method definitions and extract call sites (pass 1 & 2)."""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Decorators recognised as FastAPI route decorators (prefix stripped, e.g. router.get → get)
_FASTAPI_HTTP_METHODS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

# Names treated as FastAPI entry-point decorators (carry HTTP method + path)
_FASTAPI_ROUTE_ATTRS: frozenset[str] = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options",
    "api_route", "route",
})

# flow_entry decorator name (both plain and module-qualified)
_FLOW_ENTRY_NAMES: frozenset[str] = frozenset({"flow_entry", "flowdoc.flow_entry"})

# Parameters that are never included in the node ID
_SELF_PARAMS: frozenset[str] = frozenset({"self", "cls"})


@dataclass
class ParamInfo:
    name: str
    type_hint: str  # annotation string or "_"


@dataclass
class AnnotationInfo:
    name: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class FunctionDef:
    """Represents one parsed function or method definition."""

    # Unique identifier  "{module[.class]}#{name}({type,...})"
    node_id: str
    simple_name: str
    owner: str          # class name or last module component
    file: Path
    line: int
    params: list[ParamInfo] = field(default_factory=list)
    return_type: Optional[str] = None
    annotations: list[AnnotationInfo] = field(default_factory=list)
    # Optional: docstring first line
    description: Optional[str] = None
    # For local-variable type resolution: {var_name: type_str}
    local_types: dict[str, str] = field(default_factory=dict)


@dataclass
class CallSite:
    """A detected function call inside a function body."""

    caller_id: str
    callee_name: str       # bare name or "obj.method" string
    callee_receiver: Optional[str]   # name of the receiver object (for attr calls)
    file: Path
    line: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _annotation_to_str(node: Optional[ast.expr]) -> str:
    """Convert an AST annotation node to a compact string."""
    if node is None:
        return "_"
    return ast.unparse(node)


def _decorator_to_info(dec: ast.expr) -> Optional[AnnotationInfo]:
    """Convert a decorator AST node to AnnotationInfo, or None if unparseable."""
    if isinstance(dec, ast.Name):
        return AnnotationInfo(name=dec.id)
    if isinstance(dec, ast.Attribute):
        return AnnotationInfo(name=dec.attr)
    if isinstance(dec, ast.Call):
        # func part
        if isinstance(dec.func, ast.Name):
            name = dec.func.id
        elif isinstance(dec.func, ast.Attribute):
            name = dec.func.attr
        else:
            return None
        # collect keyword args as attributes
        attrs: dict[str, str] = {}
        for kw in dec.keywords:
            if kw.arg:
                attrs[kw.arg] = ast.unparse(kw.value)
        # positional args → "value" key (FastAPI path string)
        if dec.args:
            attrs["value"] = ast.unparse(dec.args[0])
        return AnnotationInfo(name=name, attributes=attrs)
    return None


def _build_node_id(module_path: str, class_name: Optional[str], func_name: str, params: list[ParamInfo]) -> str:
    """Build the canonical node id string."""
    owner = f"{module_path}.{class_name}" if class_name else module_path
    param_types = ",".join(p.type_hint for p in params)
    return f"{owner}#{func_name}({param_types})"


def _first_docstring(body: list[ast.stmt]) -> Optional[str]:
    """Extract the first line of a docstring from a function/class body."""
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        doc = str(body[0].value.value).strip()
        return doc.split("\n")[0] if doc else None
    return None


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------

class _FileVisitor(ast.NodeVisitor):
    """Single-file AST visitor that collects FunctionDef and CallSite entries."""

    def __init__(self, module_path: str, file: Path) -> None:
        self._module_path = module_path
        self._file = file
        self._class_stack: list[str] = []
        self._func_stack: list[str] = []  # node_ids of enclosing functions
        self.definitions: list[FunctionDef] = []
        self.call_sites: list[CallSite] = []
        # import alias → full module.name  (e.g. "auth_service" → "app.services.auth_service")
        self._import_aliases: dict[str, str] = {}
        # from X import Y → {Y: X.Y}
        self._from_imports: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Import tracking (for resolution hints — stored but used by resolver)
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            key = alias.asname or alias.name.split(".")[-1]
            self._import_aliases[key] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            key = alias.asname or alias.name
            self._from_imports[key] = f"{module}.{alias.name}" if module else alias.name
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Class tracking
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    # ------------------------------------------------------------------
    # Function definitions
    # ------------------------------------------------------------------

    def _visit_funcdef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        class_name = self._class_stack[-1] if self._class_stack else None

        # Build params (skip self/cls)
        params: list[ParamInfo] = []
        for arg in node.args.args:
            if arg.arg in _SELF_PARAMS:
                continue
            params.append(ParamInfo(
                name=arg.arg,
                type_hint=_annotation_to_str(arg.annotation),
            ))
        # *args
        if node.args.vararg:
            a = node.args.vararg
            if a.arg not in _SELF_PARAMS:
                params.append(ParamInfo(name=f"*{a.arg}", type_hint=_annotation_to_str(a.annotation)))
        # **kwargs
        if node.args.kwarg:
            a = node.args.kwarg
            params.append(ParamInfo(name=f"**{a.arg}", type_hint=_annotation_to_str(a.annotation)))
        # kw-only
        for arg in node.args.kwonlyargs:
            if arg.arg in _SELF_PARAMS:
                continue
            params.append(ParamInfo(name=arg.arg, type_hint=_annotation_to_str(arg.annotation)))

        return_type = _annotation_to_str(node.returns) if node.returns else None

        node_id = _build_node_id(self._module_path, class_name, node.name, params)

        # Build local variable type map (simple assignments with type comments or annotated assigns)
        local_types: dict[str, str] = {}
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                local_types[stmt.target.id] = _annotation_to_str(stmt.annotation)

        # Add params to local types too
        for p in params:
            if p.type_hint != "_":
                local_types[p.name] = p.type_hint

        annotations: list[AnnotationInfo] = []
        for dec in node.decorator_list:
            info = _decorator_to_info(dec)
            if info:
                annotations.append(info)

        desc = _first_docstring(node.body)

        func_def = FunctionDef(
            node_id=node_id,
            simple_name=node.name,
            owner=class_name or self._module_path.split(".")[-1],
            file=self._file,
            line=node.lineno,
            params=params,
            return_type=return_type,
            annotations=annotations,
            description=desc,
            local_types=local_types,
        )
        self.definitions.append(func_def)

        # Descend into body to collect call sites
        self._func_stack.append(node_id)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_funcdef(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_funcdef(node)

    # ------------------------------------------------------------------
    # Call sites
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        if not self._func_stack:
            self.generic_visit(node)
            return

        caller_id = self._func_stack[-1]
        func = node.func

        if isinstance(func, ast.Name):
            # bare function call: some_func(...)
            self.call_sites.append(CallSite(
                caller_id=caller_id,
                callee_name=func.id,
                callee_receiver=None,
                file=self._file,
                line=node.lineno,
            ))
        elif isinstance(func, ast.Attribute):
            # attribute call: obj.method(...)
            if isinstance(func.value, ast.Name):
                receiver = func.value.id
            elif isinstance(func.value, ast.Attribute):
                receiver = ast.unparse(func.value)
            else:
                receiver = None
            self.call_sites.append(CallSite(
                caller_id=caller_id,
                callee_name=func.attr,
                callee_receiver=receiver,
                file=self._file,
                line=node.lineno,
            ))

        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class ParsedFile:
    """Result of parsing a single .py file."""

    module_path: str
    file: Path
    definitions: list[FunctionDef]
    call_sites: list[CallSite]
    import_aliases: dict[str, str]   # alias → full module path
    from_imports: dict[str, str]     # name → module.name


def parse_file(file: Path, root: Path) -> Optional[ParsedFile]:
    """Parse a single Python file and return its definitions and call sites.

    Args:
        file: Absolute path to the .py file.
        root: Project root (used to compute module path).

    Returns:
        ParsedFile on success, None on parse error (logged as WARNING).
    """
    try:
        source = file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file))
    except SyntaxError as exc:
        logger.warning("parser: SyntaxError in %s: %s", file, exc)
        return None
    except UnicodeDecodeError as exc:
        logger.warning("parser: UnicodeDecodeError in %s: %s", file, exc)
        return None
    except OSError as exc:
        logger.warning("parser: OSError reading %s: %s", file, exc)
        return None

    rel = file.relative_to(root)
    # Convert path to dotted module: app/services/auth_service.py → app.services.auth_service
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # strip .py
    module_path = ".".join(parts)

    visitor = _FileVisitor(module_path, file)
    visitor.visit(tree)

    return ParsedFile(
        module_path=module_path,
        file=file,
        definitions=visitor.definitions,
        call_sites=visitor.call_sites,
        import_aliases=visitor._import_aliases,
        from_imports=visitor._from_imports,
    )
