"""Unified store facade combining SQLite, Redis, and vector backends."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .embedder import DIM, embed
from .redis_cache import RedisCache
from .sqlite_store import MemoryEntry, SQLiteStore
from .vector_store import VectorStore


class UnifiedStore:
    def __init__(
        self,
        sqlite_path: str | Path,
        vector_prefix: str | Path,
        redis_url: str | None,
        project_hash: str,
        redis_ttl: int = 31_536_000,
    ):
        self.sqlite = SQLiteStore(sqlite_path)
        self.vectors = VectorStore(vector_prefix, dim=DIM)
        self.redis = (
            RedisCache(redis_url, project_hash=project_hash, ttl_seconds=redis_ttl)
            if redis_url
            else None
        )
        self.project_hash = project_hash

    def insert(self, entry: MemoryEntry) -> int:
        mid = self.sqlite.insert(entry)
        text = f"{entry.summary}\n{entry.keywords}\n{entry.content}"
        vec = embed(text)
        self.vectors.add(mid, vec)
        if self.redis:
            full = self.sqlite.get(mid)
            self.redis.set_memory(mid, asdict(full))
            self.redis.add_symbol(entry.symbol, mid)
            self.redis.add_file_memory(entry.file_path, mid)
        return mid

    def delete(self, memory_id: int) -> None:
        self.sqlite.delete(memory_id)
        self.vectors.remove(memory_id)
        if self.redis:
            self.redis.del_memory(memory_id)

    def set_tier(self, memory_id: int, tier: str, reason: str | None = None) -> None:
        self.sqlite.set_tier(memory_id, tier, reason)
        if self.redis:
            updated = self.sqlite.get(memory_id)
            if updated:
                self.redis.set_memory(memory_id, asdict(updated))

    def bump_access(self, ids: list[int]) -> None:
        self.sqlite.bump_access(ids)

    def close(self) -> None:
        self.sqlite.close()
        self.vectors.save()
