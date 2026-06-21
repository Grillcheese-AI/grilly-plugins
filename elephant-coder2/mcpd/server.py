"""elephant-coder2 MCP server.

Embeds the broker: owns one per-project UnifiedStore, starts a BrokerServer in a
daemon thread (so hooks can share the same store over TCP), and exposes the core
memory tools. No GGUF sidecar yet — recall uses a raw FTS+vector merge.

This lives in `mcpd/` (not the spec's `mcp/`) on purpose: a sibling dir named
`mcp/` on sys.path would shadow the installed `mcp` SDK package. We also import
the SDK before putting the plugin root on the path, for belt-and-suspenders.
"""
from __future__ import annotations

import json
import os
import sys

# Import the MCP SDK first, while the plugin root is NOT yet on sys.path.
from mcp.server.fastmcp import FastMCP

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.append(_PLUGIN_ROOT)

from broker.handlers import build_handlers  # noqa: E402
from broker.server import BrokerServer  # noqa: E402

PROJECT_ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
_store, _handlers = build_handlers(PROJECT_ROOT)

# Start the embedded broker so future hooks can reach this same store over TCP.
# Daemon thread; MCP tools still work in-process even if the socket can't bind.
_broker = BrokerServer(handlers=_handlers)
try:
    _broker.start()
except Exception:
    pass

server = FastMCP("elephant-coder2")


def _j(result) -> str:
    return json.dumps(result, indent=2, default=str)


@server.tool()
def status() -> str:
    """Broker + store stats for the current project (entry counts per tier, vector count, redis state)."""
    return _j(_handlers["status"]({}))


@server.tool()
def recall(query: str, limit: int = 5, tier: str | None = None) -> str:
    """Hybrid FTS + vector search across memory tiers. Returns compact entry briefs ranked by relevance."""
    args = {"query": query, "limit": limit}
    if tier:
        args["tiers"] = [tier]
    return _j(_handlers["recall"](args))


@server.tool()
def recall_file(file_path: str) -> str:
    """All memories recorded for a specific file."""
    return _j(_handlers["recall_file"]({"file_path": file_path}))


@server.tool()
def search_symbol(name: str) -> str:
    """Direct lookup of memories by exact symbol name (function/class/method/heading/etc.)."""
    return _j(_handlers["search_symbol"]({"name": name}))


@server.tool()
def remember(
    content: str,
    summary: str = "",
    symbol: str = "",
    file_path: str = "",
    kind: str = "note",
    tier: str = "scratch",
) -> str:
    """Manually store a memory. tier is one of scratch|project_durable|global_durable."""
    return _j(_handlers["remember"]({
        "content": content, "summary": summary, "symbol": symbol,
        "file_path": file_path, "kind": kind, "tier": tier,
    }))


@server.tool()
def promote(memory_id: int, tier: str, reason: str = "") -> str:
    """Move a memory to a more durable tier (project_durable or global_durable)."""
    return _j(_handlers["promote"]({"memory_id": memory_id, "tier": tier, "reason": reason}))


@server.tool()
def index(path: str = "") -> str:
    """Index a file or directory (default: the whole project). mtime-skips unchanged files."""
    return _j(_handlers["index_path"]({"path": path or PROJECT_ROOT}))


@server.tool()
def recent(limit: int = 10, kind: str = "") -> str:
    """Temporal recall: the most recently stored memories first. Optionally filter by kind."""
    args = {"limit": limit}
    if kind:
        args["kind"] = kind
    return _j(_handlers["recent"](args))


@server.tool()
def related(symbol: str, limit: int = 20) -> str:
    """Navigate a symbol: its definitions plus every memory whose body references it."""
    return _j(_handlers["related"]({"symbol": symbol, "limit": limit}))


@server.tool()
def brief(task: str, limit: int = 5) -> str:
    """A ready-to-paste, token-lean memory brief for a task or subagent dispatch."""
    return _j(_handlers["brief"]({"task": task, "limit": limit}))


@server.tool()
def sidecar_store(tag: str, content: str) -> str:
    """Offload context under a tag (key-value). Re-storing the same tag replaces it. Pairs with sidecar_recall/list."""
    return _j(_handlers["sidecar_store"]({"tag": tag, "content": content}))


@server.tool()
def sidecar_recall(key: str, limit: int = 5) -> str:
    """Retrieve offloaded context by exact tag, or by hybrid query if no exact tag matches."""
    return _j(_handlers["sidecar_recall"]({"key": key, "limit": limit}))


@server.tool()
def sidecar_list(prefix: str = "") -> str:
    """List offloaded context tags, optionally filtered by prefix."""
    return _j(_handlers["sidecar_list"]({"prefix": prefix}))


@server.tool()
def forget(memory_id: int) -> str:
    """Delete a memory by id."""
    return _j(_handlers["forget"]({"memory_id": memory_id}))


if __name__ == "__main__":
    server.run()
