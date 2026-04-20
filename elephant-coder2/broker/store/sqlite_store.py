"""SQLite+FTS5 durable store for memory entries across three tiers."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


TIERS = ("scratch", "project_durable", "global_durable")


@dataclass
class MemoryEntry:
    file_path: str
    symbol: str
    kind: str
    content: str
    summary: str
    keywords: str
    tier: str = "scratch"
    id: int | None = None
    is_identity: int = 0
    is_protected: int = 0
    access_count: int = 0
    last_accessed: str | None = None
    created_at: str | None = None
    promotion_reason: str | None = None
    file_mtime: float | None = None


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                symbol TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                summary TEXT NOT NULL,
                keywords TEXT NOT NULL,
                tier TEXT NOT NULL CHECK (tier IN ('scratch','project_durable','global_durable')),
                is_identity INTEGER NOT NULL DEFAULT 0,
                is_protected INTEGER NOT NULL DEFAULT 0,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT,
                created_at TEXT NOT NULL,
                promotion_reason TEXT,
                file_mtime REAL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_file ON memories(file_path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON memories(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tier ON memories(tier)")
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(
                symbol, summary, keywords, content='memories', content_rowid='id'
            )
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
                INSERT INTO mem_fts(rowid, symbol, summary, keywords)
                VALUES (new.id, new.symbol, new.summary, new.keywords);
            END
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
                INSERT INTO mem_fts(mem_fts, rowid, symbol, summary, keywords)
                VALUES ('delete', old.id, old.symbol, old.summary, old.keywords);
            END
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
                INSERT INTO mem_fts(mem_fts, rowid, symbol, summary, keywords)
                VALUES ('delete', old.id, old.symbol, old.summary, old.keywords);
                INSERT INTO mem_fts(rowid, symbol, summary, keywords)
                VALUES (new.id, new.symbol, new.summary, new.keywords);
            END
        """)

    def insert(self, entry: MemoryEntry) -> int:
        if entry.tier not in TIERS:
            raise ValueError(f"invalid tier {entry.tier}")
        created = entry.created_at or datetime.now().isoformat()
        cur = self._conn.execute(
            """INSERT INTO memories
               (file_path, symbol, kind, content, summary, keywords, tier,
                is_identity, is_protected, access_count, created_at, file_mtime)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entry.file_path, entry.symbol, entry.kind, entry.content, entry.summary,
             entry.keywords, entry.tier, entry.is_identity, entry.is_protected,
             entry.access_count, created, entry.file_mtime),
        )
        return cur.lastrowid

    def get(self, memory_id: int) -> MemoryEntry | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None

    def delete(self, memory_id: int) -> None:
        self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def set_tier(self, memory_id: int, tier: str, reason: str | None = None) -> None:
        if tier not in TIERS:
            raise ValueError(f"invalid tier {tier}")
        self._conn.execute(
            "UPDATE memories SET tier = ?, promotion_reason = ? WHERE id = ?",
            (tier, reason, memory_id),
        )

    def bump_access(self, memory_ids: list[int]) -> None:
        if not memory_ids:
            return
        now = datetime.now().isoformat()
        self._conn.executemany(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            [(now, mid) for mid in memory_ids],
        )

    def fts_search(self, query: str, limit: int = 20, tiers: tuple[str, ...] | None = None) -> list[MemoryEntry]:
        tiers = tiers or TIERS
        placeholders = ",".join("?" * len(tiers))
        q = _sanitize_fts(query)
        sql = f"""
            SELECT m.* FROM memories m
            JOIN mem_fts f ON f.rowid = m.id
            WHERE mem_fts MATCH ? AND m.tier IN ({placeholders})
            ORDER BY bm25(mem_fts)
            LIMIT ?
        """
        rows = self._conn.execute(sql, (q, *tiers, limit)).fetchall()
        return [_row_to_entry(r) for r in rows]

    def iter_by_tier(self, tier: str) -> Iterator[MemoryEntry]:
        for row in self._conn.execute("SELECT * FROM memories WHERE tier = ?", (tier,)):
            yield _row_to_entry(row)

    def by_file(self, file_path: str) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE file_path = ?", (file_path,)
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def by_symbol(self, symbol: str) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE symbol = ?", (symbol,)
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def count(self, tier: str | None = None) -> int:
        if tier:
            return self._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE tier = ?", (tier,)
            ).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def close(self) -> None:
        self._conn.close()


def _row_to_entry(row: tuple) -> MemoryEntry:
    (mid, fp, sym, kind, content, summary, keywords, tier,
     is_id, is_prot, ac, la, ca, pr, fm) = row
    return MemoryEntry(
        id=mid, file_path=fp, symbol=sym, kind=kind, content=content,
        summary=summary, keywords=keywords, tier=tier,
        is_identity=is_id, is_protected=is_prot, access_count=ac,
        last_accessed=la, created_at=ca, promotion_reason=pr, file_mtime=fm,
    )


def _sanitize_fts(query: str) -> str:
    """Quote each whitespace-separated term to avoid FTS5 syntax errors."""
    terms = [t for t in query.replace('"', ' ').split() if t]
    if not terms:
        return '""'
    return " ".join(f'"{t}"' for t in terms)
