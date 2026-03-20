"""
Redis-primary memory store for elephant-coder with SQLite durable fallback.

Inspired by CapsuleMemory (backend/capsule_transformer.py:91-155) and the
hippocampal circular buffer pattern from nn/memory.py MemoryWrite.

Architecture:
- Redis is the PRIMARY store for reads (fast key-value, symbol, kind lookups)
- SQLite is the DURABLE FALLBACK (always written to, used when Redis is down)
- FTS5 lives in SQLite (no Redis equivalent without RediSearch module)
- Writes go to Redis first, then SQLite for durability

Each memory is a compressed "capsule" of code context with cognitive metadata
for relevance-based retrieval and lifecycle management.
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger("elephant-coder.store")


@dataclass
class MemoryEntry:
    """A compressed code context capsule.

    Mirrors CapsuleMemory's structure: identity + content + cognitive metadata.
    The 'summary' field is the capsule encoding (full source -> compact text),
    'keywords' is the DG sparse expansion (discriminative tokens for search).
    """

    memory_id: str
    file_path: str
    symbol_name: str
    kind: str  # "function" | "class" | "module" | "file_summary" | "note"

    # Capsule content
    summary: str
    keywords: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    # File metadata
    line_count: int = 0  # Total lines in the source file (set on module entries)

    # Cognitive metadata
    access_count: int = 0
    relevance_score: float = 0.0
    freshness: float = 0.0
    file_mtime: float = 0.0
    created: float = 0.0
    compression_level: int = 0
    is_stale: bool = False


def make_memory_id(file_path: str, symbol_name: str, kind: str) -> str:
    """Deterministic ID from file + symbol + kind."""
    raw = f"{file_path}:{symbol_name}:{kind}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _db_dir(project_root: str) -> Path:
    """Return per-project database directory under ~/.elephant-coder/."""
    project_hash = hashlib.sha256(project_root.encode()).hexdigest()[:12]
    base = Path.home() / ".elephant-coder" / project_hash
    base.mkdir(parents=True, exist_ok=True)
    return base


def _project_hash(project_root: str) -> str:
    return hashlib.sha256(project_root.encode()).hexdigest()[:12]


def _entry_to_dict(entry: MemoryEntry) -> dict:
    """Serialize a MemoryEntry to a JSON-safe dict."""
    d = asdict(entry)
    return d


def _dict_to_entry(d: dict) -> MemoryEntry:
    """Deserialize a dict to a MemoryEntry."""
    return MemoryEntry(**d)


# ------------------------------------------------------------------
# Redis Cache
# ------------------------------------------------------------------


class RedisCache:
    """Write-through Redis cache for MemoryStore.

    Key schema:
        ec:{project_hash}:mem:{memory_id}     — individual entry (JSON)
        ec:{project_hash}:file:{file_path_hash} — set of memory_ids for a file
        ec:{project_hash}:fts:{query_hash}     — cached FTS result (JSON list)
    """

    # 1 year in seconds
    DEFAULT_TTL = 365 * 24 * 3600
    # 3 months in seconds for FTS results
    DEFAULT_FTS_TTL = 90 * 24 * 3600

    def __init__(self, redis_url: str, project_hash: str, ttl: int = DEFAULT_TTL):
        self._available = False
        self._prefix = f"ec:{project_hash}"
        self._ttl = ttl
        self._fts_ttl = self.DEFAULT_FTS_TTL
        try:
            import redis as redis_lib
            self._r = redis_lib.from_url(redis_url, decode_responses=True)
            self._r.ping()
            self._available = True
            logger.info("Redis cache connected: %s", redis_url)
        except Exception as exc:
            self._available = False
            logger.info("Redis not available at %s — using SQLite only (this is fine): %s", redis_url, exc)

    @property
    def available(self) -> bool:
        return self._available

    def _key(self, kind: str, id_part: str) -> str:
        return f"{self._prefix}:{kind}:{id_part}"

    def _file_hash(self, file_path: str) -> str:
        return hashlib.sha256(file_path.encode()).hexdigest()[:16]

    def _query_hash(self, query: str) -> str:
        return hashlib.sha256(query.encode()).hexdigest()[:16]

    # --- Entry operations ---

    def put_entry(self, entry: MemoryEntry) -> None:
        if not self._available:
            return
        try:
            key = self._key("mem", entry.memory_id)
            self._r.setex(key, self._ttl, json.dumps(_entry_to_dict(entry)))
            # Add to file set
            fkey = self._key("file", self._file_hash(entry.file_path))
            self._r.sadd(fkey, entry.memory_id)
            self._r.expire(fkey, self._ttl)
        except Exception:
            pass
        # Update symbol and kind indexes
        self.put_symbol(entry)
        self.put_kind(entry)

    def get_entry(self, memory_id: str) -> MemoryEntry | None:
        if not self._available:
            return None
        try:
            data = self._r.get(self._key("mem", memory_id))
            if data:
                return _dict_to_entry(json.loads(data))
        except Exception:
            pass
        return None

    def delete_entry(self, memory_id: str, file_path: str | None = None,
                     symbol_name: str | None = None, kind: str | None = None) -> None:
        if not self._available:
            return
        try:
            self._r.delete(self._key("mem", memory_id))
            if file_path:
                fkey = self._key("file", self._file_hash(file_path))
                self._r.srem(fkey, memory_id)
            if symbol_name:
                self._r.srem(self._key("sym", symbol_name), memory_id)
                if kind:
                    self._r.srem(self._key("sym", f"{symbol_name}:{kind}"), memory_id)
            if kind:
                self._r.srem(self._key("kind", kind), memory_id)
        except Exception:
            pass

    # --- File set operations ---

    def get_file_entries(self, file_path: str) -> list[str] | None:
        """Return memory_ids for a file, or None if not cached."""
        if not self._available:
            return None
        try:
            fkey = self._key("file", self._file_hash(file_path))
            members = self._r.smembers(fkey)
            return list(members) if members else None
        except Exception:
            return None

    def invalidate_file(self, file_path: str) -> None:
        """Remove all cached entries for a file."""
        if not self._available:
            return
        try:
            fkey = self._key("file", self._file_hash(file_path))
            mem_ids = self._r.smembers(fkey)
            if mem_ids:
                pipe = self._r.pipeline()
                for mid in mem_ids:
                    pipe.delete(self._key("mem", mid))
                pipe.delete(fkey)
                pipe.execute()
        except Exception:
            pass

    # --- Symbol index ---

    def put_symbol(self, entry: MemoryEntry) -> None:
        """Index an entry by symbol_name for direct lookup."""
        if not self._available:
            return
        try:
            # Exact name -> set of memory_ids
            skey = self._key("sym", entry.symbol_name)
            self._r.sadd(skey, entry.memory_id)
            self._r.expire(skey, self._ttl)
            # Kind-specific: sym:{name}:{kind} -> set of memory_ids
            skkey = self._key("sym", f"{entry.symbol_name}:{entry.kind}")
            self._r.sadd(skkey, entry.memory_id)
            self._r.expire(skkey, self._ttl)
        except Exception:
            pass

    def get_symbol(self, name: str, kind: str | None = None) -> list[str] | None:
        """Get memory_ids for a symbol name. Returns None if not in cache."""
        if not self._available:
            return None
        try:
            if kind:
                skey = self._key("sym", f"{name}:{kind}")
            else:
                skey = self._key("sym", name)
            members = self._r.smembers(skey)
            return list(members) if members else None
        except Exception:
            return None

    def delete_symbol(self, entry: MemoryEntry) -> None:
        """Remove an entry from symbol indexes."""
        if not self._available:
            return
        try:
            skey = self._key("sym", entry.symbol_name)
            self._r.srem(skey, entry.memory_id)
            skkey = self._key("sym", f"{entry.symbol_name}:{entry.kind}")
            self._r.srem(skkey, entry.memory_id)
        except Exception:
            pass

    # --- Kind index ---

    def put_kind(self, entry: MemoryEntry) -> None:
        """Index an entry by kind for filtered lookup."""
        if not self._available:
            return
        try:
            kkey = self._key("kind", entry.kind)
            self._r.sadd(kkey, entry.memory_id)
            self._r.expire(kkey, self._ttl)
        except Exception:
            pass

    def get_kind(self, kind: str) -> list[str] | None:
        """Get memory_ids for a kind. Returns None if not in cache."""
        if not self._available:
            return None
        try:
            kkey = self._key("kind", kind)
            members = self._r.smembers(kkey)
            return list(members) if members else None
        except Exception:
            return None

    def delete_kind(self, entry: MemoryEntry) -> None:
        """Remove an entry from kind index."""
        if not self._available:
            return
        try:
            kkey = self._key("kind", entry.kind)
            self._r.srem(kkey, entry.memory_id)
        except Exception:
            pass

    # --- FTS cache ---

    def put_fts(self, query: str, entries: list[MemoryEntry]) -> None:
        if not self._available:
            return
        try:
            key = self._key("fts", self._query_hash(query))
            data = json.dumps([_entry_to_dict(e) for e in entries])
            self._r.setex(key, self._fts_ttl, data)
        except Exception:
            pass

    def get_fts(self, query: str) -> list[MemoryEntry] | None:
        if not self._available:
            return None
        try:
            data = self._r.get(self._key("fts", self._query_hash(query)))
            if data:
                return [_dict_to_entry(d) for d in json.loads(data)]
        except Exception:
            pass
        return None

    def flush_fts(self) -> None:
        """Invalidate all cached FTS results."""
        if not self._available:
            return
        try:
            pattern = self._key("fts", "*")
            cursor = 0
            while True:
                cursor, keys = self._r.scan(cursor, match=pattern, count=100)
                if keys:
                    self._r.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass


class MemoryStore:
    """Redis-primary storage with SQLite durable fallback and FTS5 search.

    Read path: Redis first, SQLite fallback (backfill Redis on miss).
    Write path: Redis first, then SQLite for durability.
    FTS: SQLite FTS5 (no Redis equivalent without RediSearch).
    Capacity-limited circular buffer: when count exceeds max_memories,
    lowest-relevance entries are evicted (like MemoryWrite overwrite mode).
    """

    def __init__(self, project_root: str, max_memories: int = 50_000, redis_url: str | None = None):
        self.project_root = project_root
        self.max_memories = max_memories
        db_path = _db_dir(project_root) / "memories.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

        # Redis — primary store for reads, SQLite is durable fallback
        r_url = redis_url or os.environ.get("ELEPHANT_CODER_REDIS_URL", "redis://localhost:6379")
        ttl = int(os.environ.get("ELEPHANT_CODER_REDIS_TTL", str(RedisCache.DEFAULT_TTL)))
        self._cache = RedisCache(r_url, _project_hash(project_root), ttl=ttl)

    @property
    def cache(self) -> RedisCache:
        return self._cache

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                symbol_name TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                keywords TEXT NOT NULL DEFAULT '[]',
                dependencies TEXT NOT NULL DEFAULT '[]',
                line_count INTEGER DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                relevance_score REAL DEFAULT 0.0,
                freshness REAL NOT NULL,
                file_mtime REAL DEFAULT 0.0,
                created REAL NOT NULL,
                compression_level INTEGER DEFAULT 0,
                is_stale INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_memories_file_path
                ON memories(file_path);
            CREATE INDEX IF NOT EXISTS idx_memories_kind
                ON memories(kind);
            CREATE INDEX IF NOT EXISTS idx_memories_symbol_name
                ON memories(symbol_name);
            CREATE INDEX IF NOT EXISTS idx_memories_relevance
                ON memories(relevance_score DESC);
        """)

        # Migration: add line_count column if missing (pre-0.3.0 databases)
        try:
            cur.execute("SELECT line_count FROM memories LIMIT 1")
        except sqlite3.OperationalError:
            cur.execute("ALTER TABLE memories ADD COLUMN line_count INTEGER DEFAULT 0")

        # Standalone FTS5 table (not external content — avoids rowid sync issues)
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                memory_id UNINDEXED,
                symbol_name,
                summary,
                keywords
            )
        """)
        self._conn.commit()

        # File link graph
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_links (
                source_path TEXT NOT NULL,
                target_path TEXT NOT NULL,
                link_type TEXT NOT NULL,
                symbol_name TEXT,
                PRIMARY KEY (source_path, target_path, link_type)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_links_target ON file_links(target_path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_links_source ON file_links(source_path)")
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert(self, entry: MemoryEntry) -> None:
        """Insert or replace a memory entry. Redis first, then SQLite for durability."""
        now = time.time()
        if entry.created == 0.0:
            entry.created = now
        if entry.freshness == 0.0:
            entry.freshness = now

        # 1. Write to Redis first (primary store)
        self._cache.put_entry(entry)

        # 2. Write to SQLite for durability + FTS index
        cur = self._conn.cursor()
        cur.execute("DELETE FROM memories_fts WHERE memory_id = ?", (entry.memory_id,))
        cur.execute(
            """
            INSERT OR REPLACE INTO memories
                (memory_id, file_path, symbol_name, kind, summary, keywords,
                 dependencies, line_count, access_count, relevance_score, freshness,
                 file_mtime, created, compression_level, is_stale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.memory_id,
                entry.file_path,
                entry.symbol_name,
                entry.kind,
                entry.summary,
                json.dumps(entry.keywords),
                json.dumps(entry.dependencies),
                entry.line_count,
                entry.access_count,
                entry.relevance_score,
                entry.freshness,
                entry.file_mtime,
                entry.created,
                entry.compression_level,
                int(entry.is_stale),
            ),
        )
        cur.execute(
            """
            INSERT INTO memories_fts (memory_id, symbol_name, summary, keywords)
            VALUES (?, ?, ?, ?)
            """,
            (
                entry.memory_id,
                entry.symbol_name,
                entry.summary,
                " ".join(entry.keywords),
            ),
        )
        self._conn.commit()

    def upsert_batch(self, entries: list[MemoryEntry]) -> None:
        """Insert or replace multiple entries. Redis first, then SQLite for durability."""
        if not entries:
            return
        now = time.time()
        for entry in entries:
            if entry.created == 0.0:
                entry.created = now
            if entry.freshness == 0.0:
                entry.freshness = now

        # 1. Write to Redis first (primary store) — pipelined for performance
        if self._cache.available:
            try:
                pipe = self._cache._r.pipeline()
                for entry in entries:
                    key = self._cache._key("mem", entry.memory_id)
                    pipe.setex(key, self._cache._ttl, json.dumps(_entry_to_dict(entry)))
                    fkey = self._cache._key("file", self._cache._file_hash(entry.file_path))
                    pipe.sadd(fkey, entry.memory_id)
                    pipe.expire(fkey, self._cache._ttl)
                    # Symbol index
                    skey = self._cache._key("sym", entry.symbol_name)
                    pipe.sadd(skey, entry.memory_id)
                    pipe.expire(skey, self._cache._ttl)
                    skkey = self._cache._key("sym", f"{entry.symbol_name}:{entry.kind}")
                    pipe.sadd(skkey, entry.memory_id)
                    pipe.expire(skkey, self._cache._ttl)
                    # Kind index
                    kkey = self._cache._key("kind", entry.kind)
                    pipe.sadd(kkey, entry.memory_id)
                    pipe.expire(kkey, self._cache._ttl)
                pipe.execute()
            except Exception:
                pass

        # 2. Write to SQLite for durability + FTS index
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            for entry in entries:
                cur.execute("DELETE FROM memories_fts WHERE memory_id = ?", (entry.memory_id,))
                cur.execute(
                    """INSERT OR REPLACE INTO memories
                        (memory_id, file_path, symbol_name, kind, summary, keywords,
                         dependencies, line_count, access_count, relevance_score, freshness,
                         file_mtime, created, compression_level, is_stale)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (entry.memory_id, entry.file_path, entry.symbol_name,
                     entry.kind, entry.summary, json.dumps(entry.keywords),
                     json.dumps(entry.dependencies), entry.line_count,
                     entry.access_count, entry.relevance_score, entry.freshness,
                     entry.file_mtime, entry.created, entry.compression_level,
                     int(entry.is_stale)),
                )
                cur.execute(
                    "INSERT INTO memories_fts (memory_id, symbol_name, summary, keywords) VALUES (?, ?, ?, ?)",
                    (entry.memory_id, entry.symbol_name, entry.summary, " ".join(entry.keywords)),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Fetch a single memory by ID."""
        # Check Redis first
        cached = self._cache.get_entry(memory_id)
        if cached is not None:
            return cached

        row = self._conn.execute(
            "SELECT * FROM memories WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        entry = self._row_to_entry(row)
        # Backfill cache
        self._cache.put_entry(entry)
        return entry

    def search_fts(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Full-text search with BM25 ranking. Checks Redis cache first."""
        # Check Redis FTS cache
        cached = self._cache.get_fts(query)
        if cached is not None:
            return cached[:limit]

        # Escape special FTS5 characters
        safe_query = query.replace('"', '""')
        try:
            rows = self._conn.execute(
                """
                SELECT m.* FROM memories m
                JOIN memories_fts fts ON m.memory_id = fts.memory_id
                WHERE memories_fts MATCH ?
                ORDER BY bm25(memories_fts) ASC
                LIMIT ?
                """,
                (f'"{safe_query}" OR {safe_query}', limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # Fallback: simple LIKE search if FTS query fails
            like = f"%{query}%"
            rows = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE summary LIKE ? OR symbol_name LIKE ? OR keywords LIKE ?
                ORDER BY relevance_score DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        results = [self._row_to_entry(r) for r in rows]

        # Cache results in Redis
        self._cache.put_fts(query, results)
        return results

    def search_by_file(self, file_path: str) -> list[MemoryEntry]:
        """Get all memories for a specific file."""
        # Check Redis file set for cached entries
        cached_ids = self._cache.get_file_entries(file_path)
        if cached_ids:
            entries = []
            for mid in cached_ids:
                e = self._cache.get_entry(mid)
                if e is not None:
                    entries.append(e)
            if entries:
                entries.sort(key=lambda e: (e.kind, e.symbol_name))
                return entries

        rows = self._conn.execute(
            "SELECT * FROM memories WHERE file_path = ? ORDER BY kind, symbol_name",
            (file_path,),
        ).fetchall()
        results = [self._row_to_entry(r) for r in rows]
        # Backfill cache
        for e in results:
            self._cache.put_entry(e)
        return results

    def search_by_kind(self, kind: str, limit: int = 50) -> list[MemoryEntry]:
        """Get memories filtered by kind. Redis first, SQLite fallback."""
        # 1. Try Redis kind index
        cached_ids = self._cache.get_kind(kind)
        if cached_ids:
            entries = []
            for mid in list(cached_ids)[:limit]:
                e = self._cache.get_entry(mid)
                if e is not None:
                    entries.append(e)
            if entries:
                entries.sort(key=lambda e: e.relevance_score, reverse=True)
                return entries

        # 2. SQLite fallback
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE kind = ? ORDER BY relevance_score DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
        results = [self._row_to_entry(r) for r in rows]
        # Backfill Redis
        for e in results:
            self._cache.put_entry(e)
        return results

    def search_by_symbol(self, name: str, kind: str | None = None) -> list[MemoryEntry]:
        """Direct symbol lookup by name. Redis first, SQLite fallback."""
        # 1. Try Redis symbol index
        cached_ids = self._cache.get_symbol(name, kind)
        if cached_ids:
            entries = []
            for mid in cached_ids:
                e = self._cache.get_entry(mid)
                if e is not None:
                    entries.append(e)
            if entries:
                entries.sort(key=lambda e: e.relevance_score, reverse=True)
                return entries

        # 2. SQLite fallback (exact match, then prefix)
        if kind:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE symbol_name = ? AND kind = ? ORDER BY relevance_score DESC",
                (name, kind),
            ).fetchall()
            if not rows:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE symbol_name LIKE ? AND kind = ? ORDER BY relevance_score DESC LIMIT 20",
                    (f"{name}%", kind),
                ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE symbol_name = ? ORDER BY relevance_score DESC",
                (name,),
            ).fetchall()
            if not rows:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE symbol_name LIKE ? ORDER BY relevance_score DESC LIMIT 20",
                    (f"{name}%",),
                ).fetchall()
        results = [self._row_to_entry(r) for r in rows]
        # Backfill Redis
        for e in results:
            self._cache.put_entry(e)
        return results

    def get_dependencies(self, file_path: str) -> dict:
        """Get what a file imports and what imports it."""
        # What this file imports
        row = self._conn.execute(
            "SELECT dependencies FROM memories WHERE file_path = ? AND kind = 'module'",
            (file_path,),
        ).fetchone()
        imports = json.loads(row["dependencies"]) if row else []

        # What imports this file (search dependencies that mention this file's module name)
        module_name = Path(file_path).stem
        rows = self._conn.execute(
            "SELECT DISTINCT file_path FROM memories WHERE kind = 'module' AND dependencies LIKE ? AND file_path != ?",
            (f"%{module_name}%", file_path),
        ).fetchall()
        imported_by = [r["file_path"] for r in rows]

        return {"imports": imports, "imported_by": imported_by}

    def touch(self, memory_id: str) -> None:
        """Increment access_count and update freshness on retrieval (Hebbian)."""
        now = time.time()
        self._conn.execute(
            """
            UPDATE memories
            SET access_count = access_count + 1, freshness = ?
            WHERE memory_id = ?
            """,
            (now, memory_id),
        )
        self._conn.commit()

    def touch_batch(self, memory_ids: list[str]) -> None:
        """Batch touch: increment access_count and update freshness for multiple entries."""
        if not memory_ids:
            return
        now = time.time()
        self._conn.executemany(
            "UPDATE memories SET access_count = access_count + 1, freshness = ? WHERE memory_id = ?",
            [(now, mid) for mid in memory_ids],
        )
        self._conn.commit()

    def update_relevance(self, memory_id: str, relevance_score: float) -> None:
        """Lightweight relevance update without full upsert (avoids FTS5 delete+insert)."""
        self._conn.execute(
            "UPDATE memories SET relevance_score = ? WHERE memory_id = ?",
            (relevance_score, memory_id),
        )
        self._conn.commit()

    def delete(self, memory_id: str) -> bool:
        """Delete a memory and its FTS entry. Cleans up all Redis indexes."""
        # Get full entry info for cache invalidation
        row = self._conn.execute(
            "SELECT file_path, symbol_name, kind FROM memories WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        file_path = row["file_path"] if row else None
        symbol_name = row["symbol_name"] if row else None
        kind = row["kind"] if row else None

        cur = self._conn.cursor()
        cur.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))
        cur.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
        self._conn.commit()

        self._cache.delete_entry(memory_id, file_path, symbol_name, kind)
        return cur.rowcount > 0

    def delete_by_file(self, file_path: str) -> int:
        """Delete all memories for a file."""
        ids = [
            r["memory_id"]
            for r in self._conn.execute(
                "SELECT memory_id FROM memories WHERE file_path = ?", (file_path,)
            ).fetchall()
        ]
        for mid in ids:
            self.delete(mid)
        self._cache.invalidate_file(file_path)
        return len(ids)

    def delete_stale(self) -> int:
        """Delete all stale memories."""
        ids = [
            r["memory_id"]
            for r in self._conn.execute(
                "SELECT memory_id FROM memories WHERE is_stale = 1"
            ).fetchall()
        ]
        for mid in ids:
            self.delete(mid)
        return len(ids)

    def evict_lowest(self, count: int) -> int:
        """Evict lowest-relevance memories, skipping recently accessed ones."""
        one_hour_ago = time.time() - 3600
        rows = self._conn.execute(
            """
            SELECT memory_id FROM memories
            WHERE freshness < ?
            ORDER BY relevance_score ASC
            LIMIT ?
            """,
            (one_hour_ago, count),
        ).fetchall()
        evicted = 0
        for r in rows:
            if self.delete(r["memory_id"]):
                evicted += 1
        return evicted

    def count(self) -> int:
        """Total number of memories."""
        row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return row["c"]

    def stats(self) -> dict:
        """Aggregate statistics about the memory store."""
        total = self.count()
        kinds = {}
        for r in self._conn.execute(
            "SELECT kind, COUNT(*) AS c FROM memories GROUP BY kind"
        ).fetchall():
            kinds[r["kind"]] = r["c"]

        stale_count = self._conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE is_stale = 1"
        ).fetchone()["c"]

        top_accessed = self._conn.execute(
            "SELECT symbol_name, file_path, access_count FROM memories "
            "ORDER BY access_count DESC LIMIT 5"
        ).fetchall()

        result = {
            "total": total,
            "max_capacity": self.max_memories,
            "utilization_pct": round(total / self.max_memories * 100, 1)
            if self.max_memories
            else 0,
            "by_kind": kinds,
            "stale": stale_count,
            "top_accessed": [
                {"symbol": r["symbol_name"], "file": r["file_path"], "count": r["access_count"]}
                for r in top_accessed
            ],
            "redis_connected": self._cache.available,
        }
        return result

    # ------------------------------------------------------------------
    # File Link Graph
    # ------------------------------------------------------------------

    def add_file_link(self, source_path: str, target_path: str, link_type: str, symbol_name: str | None = None) -> None:
        """Add a directed link between two files."""
        self._conn.execute(
            "INSERT OR REPLACE INTO file_links (source_path, target_path, link_type, symbol_name) VALUES (?, ?, ?, ?)",
            (source_path, target_path, link_type, symbol_name))
        self._conn.commit()

    def add_file_links_batch(self, links: list[tuple[str, str, str, str | None]]) -> None:
        """Batch add file links. Each tuple: (source, target, link_type, symbol_name)."""
        if not links:
            return
        self._conn.executemany(
            "INSERT OR REPLACE INTO file_links (source_path, target_path, link_type, symbol_name) VALUES (?, ?, ?, ?)", links)
        self._conn.commit()

    def get_outbound_links(self, source_path: str) -> list[dict]:
        """Get all files that source_path imports/includes."""
        rows = self._conn.execute("SELECT * FROM file_links WHERE source_path = ? ORDER BY target_path", (source_path,)).fetchall()
        return [{"source_path": r["source_path"], "target_path": r["target_path"],
                 "link_type": r["link_type"], "symbol_name": r["symbol_name"]} for r in rows]

    def get_inbound_links(self, target_path: str) -> list[dict]:
        """Get all files that import/include target_path."""
        rows = self._conn.execute("SELECT * FROM file_links WHERE target_path = ? ORDER BY source_path", (target_path,)).fetchall()
        return [{"source_path": r["source_path"], "target_path": r["target_path"],
                 "link_type": r["link_type"], "symbol_name": r["symbol_name"]} for r in rows]

    def get_hub_files(self, limit: int = 10) -> list[dict]:
        """Get files with the most inbound links (architectural pillars)."""
        rows = self._conn.execute(
            "SELECT target_path, COUNT(*) as inbound_count FROM file_links GROUP BY target_path ORDER BY inbound_count DESC LIMIT ?",
            (limit,)).fetchall()
        return [{"file_path": r["target_path"], "inbound_count": r["inbound_count"]} for r in rows]

    def clear_file_links(self, source_path: str) -> None:
        """Clear all outbound links for a file (before re-indexing)."""
        self._conn.execute("DELETE FROM file_links WHERE source_path = ?", (source_path,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        # Handle DBs that pre-date the line_count column
        try:
            lc = row["line_count"]
        except (IndexError, KeyError):
            lc = 0
        return MemoryEntry(
            memory_id=row["memory_id"],
            file_path=row["file_path"],
            symbol_name=row["symbol_name"],
            kind=row["kind"],
            summary=row["summary"],
            keywords=json.loads(row["keywords"]),
            dependencies=json.loads(row["dependencies"]),
            line_count=lc,
            access_count=row["access_count"],
            relevance_score=row["relevance_score"],
            freshness=row["freshness"],
            file_mtime=row["file_mtime"],
            created=row["created"],
            compression_level=row["compression_level"],
            is_stale=bool(row["is_stale"]),
        )
