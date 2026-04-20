"""Redis cache layer with graceful fallback when Redis is unavailable."""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, url: str, project_hash: str, ttl_seconds: int = 31_536_000):
        self.url = url
        self.project_hash = project_hash
        self.ttl = ttl_seconds
        self._r = None
        self.available = False
        try:
            import redis
            self._r = redis.from_url(url, decode_responses=True, socket_timeout=0.5)
            self._r.ping()
            self.available = True
        except Exception as e:
            log.warning("Redis unavailable (%s); falling back to SQLite-only", e)

    def _key(self, *parts: str) -> str:
        return ":".join(("ec2", self.project_hash, *parts))

    def set_memory(self, mid: int, data: dict) -> None:
        if not self.available:
            return
        try:
            self._r.setex(self._key("mem", str(mid)), self.ttl, json.dumps(data))
        except Exception as e:
            log.debug("redis set_memory failed: %s", e)

    def get_memory(self, mid: int) -> dict | None:
        if not self.available:
            return None
        try:
            raw = self._r.get(self._key("mem", str(mid)))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def del_memory(self, mid: int) -> None:
        if not self.available:
            return
        try:
            self._r.delete(self._key("mem", str(mid)))
        except Exception:
            pass

    def add_symbol(self, symbol: str, mid: int) -> None:
        if not self.available:
            return
        try:
            self._r.sadd(self._key("sym", symbol), mid)
            self._r.expire(self._key("sym", symbol), self.ttl)
        except Exception:
            pass

    def get_symbol_ids(self, symbol: str) -> list[int]:
        if not self.available:
            return []
        try:
            return [int(x) for x in self._r.smembers(self._key("sym", symbol))]
        except Exception:
            return []

    def add_file_memory(self, file_path: str, mid: int) -> None:
        if not self.available:
            return
        try:
            self._r.sadd(self._key("file", file_path), mid)
            self._r.expire(self._key("file", file_path), self.ttl)
        except Exception:
            pass

    def get_file_memory_ids(self, file_path: str) -> list[int]:
        if not self.available:
            return []
        try:
            return [int(x) for x in self._r.smembers(self._key("file", file_path))]
        except Exception:
            return []

    def flush(self) -> None:
        if not self.available:
            return
        try:
            cursor = 0
            pattern = self._key("*")
            while True:
                cursor, keys = self._r.scan(cursor=cursor, match=pattern, count=500)
                if keys:
                    self._r.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass
