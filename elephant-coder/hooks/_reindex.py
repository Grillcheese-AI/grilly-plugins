"""Shared re-indexing utility for PostToolUse hooks.

Called by posttooluse_edit.py and posttooluse_write.py to directly
re-index modified files without relying on Claude to follow reminders.

Uses WAL-mode SQLite, safe for concurrent access with the running MCP server.
"""

import logging
import os
import sys
import time
from pathlib import Path

# Add plugin root to path so we can import elephant-coder modules
_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from indexer import index_file
from memory_store import MemoryStore
from settings import load_settings

logger = logging.getLogger("elephant-coder.hooks.reindex")


def _detect_project_root(file_path: str) -> str:
    """Detect project root by walking up from the file's directory."""
    p = Path(file_path).resolve()
    for parent in [p.parent, *p.parent.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return str(parent)
    return str(p.parent)


def reindex_file(file_path: str) -> tuple[bool, int]:
    """Re-index a single file directly into the memory store.

    Returns (success, num_symbols_indexed).
    """
    if not file_path or not os.path.exists(file_path):
        return False, 0

    try:
        project_root = _detect_project_root(file_path)
        settings = load_settings(project_root)
        redis_url = settings.get("redis_url")
        store = MemoryStore(project_root, redis_url=redis_url)
        entries = index_file(file_path)
        if entries:
            store.upsert_batch(entries)
        store.close()
        return True, len(entries)
    except Exception as exc:
        logger.warning("reindex_file failed for %s: %s", file_path, exc)
        return False, 0
