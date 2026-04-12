"""
Memory lifecycle manager for elephant-coder.

Handles staleness detection, relevance decay, and capacity-based eviction.
Analogous to the hippocampal consolidation cycle:
- Staleness detection = checking if a memory's source has changed (like stability decay)
- Eviction = circular buffer overwrite from nn/memory.py MemoryWrite
- Relevance recomputation = consolidation_priority update from CognitiveFeatures
"""

import logging
import os

from memory_store import MemoryStore
from retriever import compute_relevance

logger = logging.getLogger("elephant-coder.consolidator")


def detect_stale(store: MemoryStore) -> int:
    """Mark memories as stale if their source file has been modified."""
    conn = store._get_sqlite()
    rows = conn.execute(
        "SELECT DISTINCT file_path, MAX(file_mtime) AS indexed_mtime "
        "FROM memories WHERE is_stale = 0 GROUP BY file_path"
    ).fetchall()

    # Batch stat all files up front
    stale_files: list[str] = []
    for row in rows:
        fp = row["file_path"]
        try:
            actual_mtime = os.path.getmtime(fp)
        except OSError:
            actual_mtime = float("inf")
        if actual_mtime > row["indexed_mtime"]:
            stale_files.append(fp)

    if not stale_files:
        return 0

    # Batch UPDATE for all stale files — chunked to stay under
    # SQLITE_MAX_VARIABLE_NUMBER (999).
    stale_count = 0
    chunk_size = 900
    for i in range(0, len(stale_files), chunk_size):
        chunk = stale_files[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        conn.execute(
            f"UPDATE memories SET is_stale = 1 "
            f"WHERE is_stale = 0 AND file_path IN ({placeholders})",
            chunk,
        )
        stale_count += conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()

    if stale_count:
        logger.info("Marked %d memories as stale", stale_count)
        invalidate_redis_cache(store, stale_files)

    return stale_count


def recompute_relevance(store: MemoryStore) -> int:
    """Recompute relevance_score for all memories based on current time."""
    conn = store._get_sqlite()
    rows = conn.execute(
        "SELECT memory_id, access_count, freshness, created FROM memories"
    ).fetchall()

    updates = []
    for r in rows:
        mid = r["memory_id"]
        # Use pending buffer values if available (they're more current)
        if mid in store._pending:
            entry = store._pending[mid]
            new_score = compute_relevance(entry.access_count, entry.freshness, entry.created)
            entry.relevance_score = new_score
        else:
            new_score = compute_relevance(r["access_count"], r["freshness"], r["created"])
        updates.append((new_score, mid))

    conn.executemany("UPDATE memories SET relevance_score = ? WHERE memory_id = ?", updates)
    conn.commit()
    return len(updates)


def consolidate(store: MemoryStore) -> dict:
    """Run full consolidation cycle."""
    stats = {
        "stale_detected": detect_stale(store),
        "relevance_updated": recompute_relevance(store),
        "evicted": 0,
    }

    total = store.count()
    if total > store.max_memories:
        to_evict = max(1, total - store.max_memories + store.max_memories // 10)
        stats["evicted"] = store.evict_lowest(to_evict)
        logger.info(
            "Evicted %d memories (was %d, max %d)", stats["evicted"], total, store.max_memories
        )

    store.cache.flush_fts()
    return stats


def should_consolidate(store: MemoryStore) -> bool:
    """Check if consolidation should run (>90% capacity)."""
    return store.count() > store.max_memories * 0.9


def invalidate_redis_cache(store: MemoryStore, file_paths: list[str]) -> None:
    """Invalidate Redis cache entries for the given file paths."""
    for fp in file_paths:
        store.cache.invalidate_file(fp)
    store.cache.flush_fts()
