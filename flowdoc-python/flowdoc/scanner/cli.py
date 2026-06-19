"""CLI entry point for the FlowDoc Python scanner.

Usage:
    python -m flowdoc.scanner <source_root> <output_path>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import jsonschema

from flowdoc.scanner.builder import build_spec
from flowdoc.scanner.discovery import discover_python_files
from flowdoc.scanner.parser import parse_file
from flowdoc.scanner.resolver import DefinitionIndex, resolve_call_sites
from flowdoc.spec import spec_to_dict, spec_to_json

# ---------------------------------------------------------------------------
# Custom SUCCESS log level (between INFO=20 and WARNING=30)
# ---------------------------------------------------------------------------
SUCCESS_LEVEL: int = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def _success(self: logging.Logger, msg: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
    """Emit a SUCCESS-level log message."""
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, msg, args, **kwargs)


logging.Logger.success = _success  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema for spec validation
# ---------------------------------------------------------------------------
_FLOWDOC_SCHEMA: dict = {
    "type": "object",
    "required": ["flowdoc", "source", "nodes", "edges", "sequences", "guards", "traces"],
    "properties": {
        "flowdoc": {"type": "string", "const": "0.1"},
        "source": {
            "type": "object",
            "required": ["language", "framework", "collector"],
            "properties": {
                "language": {"type": "string"},
                "framework": {"type": "string"},
                "collector": {"type": "string"},
            },
        },
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "simpleName", "owner", "kind", "location", "auto"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["from", "to", "callType", "site", "resolution"],
            },
        },
        "sequences": {"type": "array"},
        "guards": {"type": "array"},
        "traces": {"type": "array"},
    },
}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else SUCCESS_LEVEL
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=level, handlers=[handler], force=True)


def run(source_root: Path, output_path: Path, *, verbose: bool = False) -> int:
    """Execute the full scan pipeline and write the output JSON.

    Returns:
        0 on success, non-zero on failure.
    """
    _setup_logging(verbose)

    if not source_root.is_dir():
        logger.error("Source root does not exist or is not a directory: %s", source_root)
        return 1

    # ── Discovery ──────────────────────────────────────────────────────
    py_files = discover_python_files(source_root)
    logger.info("Scanning %d Python files under %s", len(py_files), source_root)

    # ── Parse (pass 1) ────────────────────────────────────────────────
    parsed_files = []
    parse_failures = 0
    for f in py_files:
        result = parse_file(f, source_root)
        if result is None:
            parse_failures += 1
        else:
            parsed_files.append(result)

    if parse_failures:
        logger.warning("Skipped %d file(s) due to parse errors", parse_failures)

    all_call_sites = [cs for pf in parsed_files for cs in pf.call_sites]

    # ── Resolve (pass 2) ───────────────────────────────────────────────
    index = DefinitionIndex(parsed_files)
    resolved_edges, n_ambiguous, n_external = resolve_call_sites(
        all_call_sites, parsed_files, index
    )

    total_calls = len(all_call_sites)
    dropped = n_ambiguous + n_external
    drop_pct = (dropped / total_calls * 100) if total_calls else 0.0
    logger.warning(
        "Dropped %d/%d call sites (%.1f%%) — ambiguous=%d, external=%d",
        dropped, total_calls, drop_pct, n_ambiguous, n_external,
    )

    # ── Build ──────────────────────────────────────────────────────────
    spec = build_spec(parsed_files, resolved_edges, source_root)

    # ── Validate ───────────────────────────────────────────────────────
    spec_dict = spec_to_dict(spec)
    try:
        jsonschema.validate(spec_dict, _FLOWDOC_SCHEMA)
    except jsonschema.ValidationError as exc:
        logger.warning("Spec validation warning: %s", exc.message)

    # ── Write ──────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(spec_to_json(spec), encoding="utf-8")

    logger.success(  # type: ignore[attr-defined]
        "FlowDoc: %d nodes, %d edges, %d sequences → %s",
        len(spec.nodes), len(spec.edges), len(spec.sequences), output_path,
    )
    return 0


def main() -> None:
    """Parse CLI arguments and run the scanner."""
    parser = argparse.ArgumentParser(
        prog="python -m flowdoc.scanner",
        description="FlowDoc Python static scanner — generates flowdoc.json from a FastAPI project.",
    )
    parser.add_argument(
        "source_root",
        type=Path,
        help="Root directory of the Python project to scan.",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Output path for the generated flowdoc.json.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )

    args = parser.parse_args()
    sys.exit(run(args.source_root.resolve(), args.output.resolve(), verbose=args.verbose))


if __name__ == "__main__":
    main()
