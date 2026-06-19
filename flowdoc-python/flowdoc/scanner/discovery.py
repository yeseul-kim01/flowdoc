"""Discover Python source files in a project root, skipping non-source paths."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories that are never source (venv, caches, build artefacts, hidden dirs)
_SKIP_DIR_NAMES: frozenset[str] = frozenset({
    ".venv", "venv", "env", ".env",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "site-packages", "dist-packages",
    "build", "dist", ".git", ".hg", ".svn",
    "node_modules", ".tox",
})


def discover_python_files(root: Path) -> list[Path]:
    """Return all .py files under *root*, skipping virtual-env and cache dirs.

    Args:
        root: Absolute path to the project root directory.

    Returns:
        Sorted list of absolute .py file paths.

    Raises:
        NotADirectoryError: If *root* is not an existing directory.
    """
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    found: list[Path] = []

    for path in root.rglob("*.py"):
        # Skip any path whose ancestor directory is in the skip set
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        found.append(path)

    found.sort()
    logger.info("discovery: found %d Python files under %s", len(found), root)
    return found
