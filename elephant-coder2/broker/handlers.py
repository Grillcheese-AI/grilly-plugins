"""Broker op handlers: the in-process logic the MCP server and hooks call.

`build_handlers(project_root)` constructs a per-project UnifiedStore and returns
a dict of op-name -> callable(args: dict) -> JSON-serializable result. This is
the minimal v2 surface: index, recall (FTS+vector merge, no model rerank yet),
recall_file, search_symbol, remember, promote, status, ping.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import settings as settings_mod
from .paths import project_dir, project_hash
from .store import embedder
from .store.sqlite_store import TIERS, MemoryEntry
from .store.unified import UnifiedStore
from .indexer.python_ast import _keywords_for, index_python_source
from .indexer.regex_extract import index_c_source, index_glsl_source, index_ts_source
from .indexer.structured import index_json, index_markdown, index_toml, index_yaml

_UNSET = object()

# Extension -> indexer function (source, file_path, file_mtime) -> list[MemoryEntry]
_EXT_DISPATCH = {
    ".py": index_python_source,
    ".ts": index_ts_source, ".tsx": index_ts_source,
    ".js": index_ts_source, ".jsx": index_ts_source, ".mjs": index_ts_source,
    ".c": index_c_source, ".cc": index_c_source, ".cpp": index_c_source,
    ".cxx": index_c_source, ".h": index_c_source, ".hpp": index_c_source,
    ".glsl": index_glsl_source, ".comp": index_glsl_source,
    ".vert": index_glsl_source, ".frag": index_glsl_source,
    ".md": index_markdown, ".markdown": index_markdown,
    ".toml": index_toml,
    ".json": index_json,
    ".yaml": index_yaml, ".yml": index_yaml,
}

_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".benchmarks",
    "dist", "build", ".idea", ".vscode", ".elephant-coder2",
}
_MAX_BYTES = 1_000_000


def _abspath(p: str | Path) -> str:
    return os.path.normpath(os.path.abspath(str(p)))


def _brief(e: MemoryEntry, score: float | None = None) -> dict:
    """Compact, token-lean projection of a memory entry for retrieval results."""
    d = {
        "id": e.id, "symbol": e.symbol, "file": e.file_path,
        "kind": e.kind, "tier": e.tier, "summary": e.summary,
    }
    if score is not None:
        d["score"] = round(float(score), 4)
    return d


def build_handlers(project_root: str, redis_url=_UNSET):
    """Construct the per-project store and return (store, handlers)."""
    root = _abspath(project_root)
    ph = project_hash(root)
    pdir = project_dir(root)
    if redis_url is _UNSET:
        redis_url = settings_mod.load_settings(Path(root)).redis_url

    store = UnifiedStore(
        sqlite_path=pdir / "memories.db",
        vector_prefix=pdir / "vectors",
        redis_url=redis_url,
        project_hash=ph,
    )

    def _index_file(path: Path) -> tuple[int, bool]:
        """Index one file. Returns (n_entries, skipped). Skipped if mtime unchanged."""
        fn = _EXT_DISPATCH.get(path.suffix.lower())
        if fn is None:
            return 0, False
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return 0, False
        fp = _abspath(path)
        existing = store.sqlite.by_file(fp)
        if existing and all(e.file_mtime == mtime for e in existing):
            return 0, True  # unchanged
        try:
            if path.stat().st_size > _MAX_BYTES:
                return 0, False
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return 0, False
        for e in existing:  # stale: drop and re-index
            store.delete(e.id)
        entries = fn(source, fp, mtime)
        for e in entries:
            store.insert(e)
        return len(entries), False

    def _iter_files(base: Path):
        if base.is_file():
            yield base
            return
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                yield Path(dirpath) / name

    # ---- ops ----
    def op_ping(args):
        return {"pong": True}

    def op_status(args):
        counts = {t: store.sqlite.count(t) for t in TIERS}
        counts["total"] = store.sqlite.count()
        return {
            "project_root": root,
            "project_hash": ph,
            "counts": counts,
            "vectors": len(store.vectors),
            "redis": bool(store.redis and store.redis.available),
        }

    def op_remember(args):
        tier = args.get("tier", "scratch")
        if tier not in TIERS:
            raise ValueError(f"invalid tier {tier}")
        content = args.get("content", "")
        symbol = args.get("symbol") or "note"
        entry = MemoryEntry(
            file_path=args.get("file_path", ""),
            symbol=symbol,
            kind=args.get("kind", "note"),
            content=content,
            summary=args.get("summary") or content[:160],
            keywords=args.get("keywords", ""),
            tier=tier,
            is_identity=int(args.get("is_identity", 0)),
            is_protected=int(args.get("is_protected", 0)),
        )
        return {"id": store.insert(entry)}

    def op_promote(args):
        mid = int(args["memory_id"])
        tier = args["tier"]
        if tier not in TIERS:
            raise ValueError(f"invalid tier {tier}")
        store.set_tier(mid, tier, args.get("reason"))
        return {"id": mid, "tier": tier}

    def op_recall(args):
        query = args["query"]
        limit = int(args.get("limit", 5))
        tiers = tuple(args["tiers"]) if args.get("tiers") else None

        scores: dict[int, dict] = {}
        fts = store.sqlite.fts_search(query, limit=20, tiers=tiers)
        n = max(1, len(fts))
        for rank, e in enumerate(fts):
            scores[e.id] = {"e": e, "fts": 1.0 - rank / n, "vec": 0.0}

        try:  # vector arm; degrade to FTS-only if the embedder is unavailable
            qv = embedder.embed(query)
            for mid, sim in store.vectors.search(qv, k=20):
                e = store.sqlite.get(mid)
                if e is None or (tiers and e.tier not in tiers):
                    continue
                scores.setdefault(mid, {"e": e, "fts": 0.0, "vec": 0.0})
                scores[mid]["vec"] = max(0.0, sim)
        except Exception:
            pass

        def _final(s):
            return 0.5 * s["fts"] + 0.5 * s["vec"]

        ranked = sorted(scores.values(), key=_final, reverse=True)[:limit]
        store.bump_access([s["e"].id for s in ranked])
        return [_brief(s["e"], _final(s)) for s in ranked]

    def op_recall_file(args):
        fp = _abspath(args["file_path"])
        return [_brief(e) for e in store.sqlite.by_file(fp)]

    def op_search_symbol(args):
        return [_brief(e) for e in store.sqlite.by_symbol(args["name"])]

    def op_index_path(args):
        base = Path(_abspath(args.get("path") or root))
        indexed_files = entries = skipped = 0
        for f in _iter_files(base):
            n, was_skipped = _index_file(f)
            if was_skipped:
                skipped += 1
            elif n > 0:
                indexed_files += 1
                entries += n
        store.vectors.save()
        return {
            "root": str(base),
            "indexed_files": indexed_files,
            "entries": entries,
            "skipped": skipped,
        }

    # ---- agentic power tools ----
    _SIDECAR_KIND = "sidecar"

    def op_sidecar_store(args):
        """Offload context under a tag. Re-storing the same tag replaces it."""
        tag = args["tag"]
        content = args.get("content", "")
        for e in store.sqlite.by_symbol(tag):
            if e.kind == _SIDECAR_KIND:
                store.delete(e.id)
        entry = MemoryEntry(
            file_path="", symbol=tag, kind=_SIDECAR_KIND, content=content,
            summary=content[:160], keywords=_keywords_for(tag, content), tier="scratch",
        )
        return {"id": store.insert(entry), "tag": tag}

    def op_sidecar_recall(args):
        """Retrieve offloaded context: exact-tag first, else hybrid query over sidecar entries."""
        key = args["key"]
        exact = [e for e in store.sqlite.by_symbol(key) if e.kind == _SIDECAR_KIND]
        if exact:
            return [{"id": e.id, "tag": e.symbol, "content": e.content} for e in exact]
        out = []
        for b in op_recall({"query": key, "limit": int(args.get("limit", 5))}):
            e = store.sqlite.get(b["id"])
            if e and e.kind == _SIDECAR_KIND:
                out.append({"id": e.id, "tag": e.symbol, "content": e.content})
        return out

    def op_brief(args):
        """A ready-to-paste, token-lean memory brief for a task or subagent."""
        task = args["task"]
        hits = op_recall({"query": task, "limit": int(args.get("limit", 5))})
        lines = [f"## Memory brief: {task}", ""]
        if not hits:
            lines.append("_No relevant memories._")
        for h in hits:
            lines.append(f"- **{h['symbol']}** ({h['file'] or '—'}) [{h['kind']}] — {h['summary']}")
        return {"task": task, "n": len(hits), "brief": "\n".join(lines)}

    def op_related(args):
        """Definitions of a symbol plus every memory whose body references it."""
        sym = args["symbol"]
        limit = int(args.get("limit", 20))
        defs = store.sqlite.by_symbol(sym)
        refs = [e for e in store.sqlite.search_content(sym, limit=limit) if e.symbol != sym]
        return {
            "symbol": sym,
            "definitions": [_brief(e) for e in defs],
            "references": [_brief(e) for e in refs],
        }

    def op_forget(args):
        mid = int(args["memory_id"])
        store.delete(mid)
        return {"forgot": mid}

    def op_recent(args):
        """Temporal recall (the recent_chats analog): newest memories first."""
        limit = int(args.get("limit", 10))
        kind = args.get("kind")
        out = []
        for e in store.sqlite.recent(limit, kind):
            d = _brief(e)
            d["created_at"] = e.created_at
            out.append(d)
        return out

    def op_sidecar_list(args):
        """Enumerate offloaded context tags (completes the KV store: store/recall/list/forget)."""
        prefix = args.get("prefix") or ""
        return [
            {"tag": e.symbol, "id": e.id, "summary": e.summary}
            for e in store.sqlite.by_kind(_SIDECAR_KIND)
            if e.symbol.startswith(prefix)
        ]

    handlers = {
        "ping": op_ping,
        "status": op_status,
        "remember": op_remember,
        "promote": op_promote,
        "recall": op_recall,
        "recall_file": op_recall_file,
        "search_symbol": op_search_symbol,
        "index_path": op_index_path,
        "sidecar_store": op_sidecar_store,
        "sidecar_recall": op_sidecar_recall,
        "brief": op_brief,
        "related": op_related,
        "forget": op_forget,
        "recent": op_recent,
        "sidecar_list": op_sidecar_list,
    }
    return store, handlers
