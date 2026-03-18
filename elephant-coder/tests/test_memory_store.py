import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import pytest
from memory_store import MemoryStore, MemoryEntry, make_memory_id


def _make_entry(file_path: str, symbol: str, kind: str, summary: str, tags=None) -> MemoryEntry:
    return MemoryEntry(
        memory_id=make_memory_id(file_path, symbol, kind),
        file_path=file_path,
        symbol_name=symbol,
        kind=kind,
        summary=summary,
        keywords=tags or [],
    )


def test_store_works_without_redis():
    """MemoryStore should work fine when Redis is not reachable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(project_root=tmpdir, redis_url="redis://localhost:59999")
        cache = store._cache
        assert cache.available is False

        # SQLite operations should all work
        entry = _make_entry("/some/file.py", "MyClass", "class", "A test class", ["test"])
        store.upsert(entry)

        assert store.count() == 1

        results = store.search_fts("test class")
        assert isinstance(results, list)

        file_entries = store.search_by_file("/some/file.py")
        assert len(file_entries) == 1
        assert file_entries[0].symbol_name == "MyClass"


def test_store_works_with_redis_if_available():
    """MemoryStore with default Redis URL should not crash regardless of availability."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Default Redis URL — may or may not be running; either way should not raise
        store = MemoryStore(project_root=tmpdir, redis_url="redis://localhost:6379")
        assert store is not None
        # Basic SQLite op should always work
        entry = _make_entry("/other/file.py", "helper_fn", "function", "Helper function")
        store.upsert(entry)
        assert store.count() >= 1


def test_upsert_batch():
    """upsert_batch inserts 100 entries atomically; FTS and get() work afterward."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(project_root=tmpdir, redis_url="redis://localhost:59999")
        assert store._cache.available is False

        entries = [
            _make_entry(f"/proj/file_{i}.py", f"func_{i}", "function",
                        f"Summary for function {i}", [f"tag_{i}", "batch"])
            for i in range(100)
        ]
        store.upsert_batch(entries)

        assert store.count() == 100

        # FTS search should find entries by tag
        results = store.search_fts("batch")
        assert len(results) > 0

        # Individual get() should work
        target = entries[42]
        fetched = store.get(target.memory_id)
        assert fetched is not None
        assert fetched.symbol_name == "func_42"
        assert fetched.summary == "Summary for function 42"


def test_upsert_batch_replaces_existing():
    """upsert_batch with duplicate memory_id updates summary; count stays 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(project_root=tmpdir, redis_url="redis://localhost:59999")

        original = _make_entry("/proj/mod.py", "MyClass", "class", "Original summary", ["v1"])
        store.upsert(original)
        assert store.count() == 1

        updated = MemoryEntry(
            memory_id=original.memory_id,
            file_path=original.file_path,
            symbol_name=original.symbol_name,
            kind=original.kind,
            summary="Updated summary",
            keywords=["v2"],
        )
        store.upsert_batch([updated])

        assert store.count() == 1
        fetched = store.get(original.memory_id)
        assert fetched is not None
        assert fetched.summary == "Updated summary"
