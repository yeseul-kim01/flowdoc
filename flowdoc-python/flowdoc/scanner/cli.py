"""CLI entry point for the FlowDoc Python scanner.

Usage:
    python -m flowdoc <source_root> <output_path>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import jsonschema

_SCHEMA_PATH: Path = Path(__file__).parents[3] / "spec" / "flowdoc-0.1.schema.json"

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

def _load_schema() -> dict:
    """Load the FlowDoc JSON Schema.

    Raises:
        FileNotFoundError: If the schema file is missing.
        json.JSONDecodeError: If the schema file is malformed JSON.
    """
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


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
        schema = _load_schema()
        jsonschema.validate(spec_dict, schema)
    except FileNotFoundError:
        logger.warning("Schema file not found at %s — skipping validation", _SCHEMA_PATH)
    except json.JSONDecodeError as exc:
        logger.warning("Schema file is malformed JSON — skipping validation: %s", exc)
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
        prog="python -m flowdoc",
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
