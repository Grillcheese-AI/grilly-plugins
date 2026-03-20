"""
Hybrid retriever for elephant-coder — FTS5 keyword + vector semantic search.

Combines two retrieval strategies:
1. BM25 keyword search via SQLite FTS5 (exact term matching)
2. Semantic vector search via Qdrant/local numpy (meaning matching)

Results are fused using Reciprocal Rank Fusion (RRF) to get the best of both.
This solves the "empty response" problem where keyword search fails on
semantically related but lexically different queries (e.g., "authentication"
matching "verify_token").

Analogous to CA3 pattern completion in nn/hippocampal.py: given a partial
cue (query), retrieve full memory entries using ranked search, then
strengthen accessed memories (Hebbian learning via access_count increment).
"""

import logging
import math
import time

from memory_store import MemoryEntry, MemoryStore

logger = logging.getLogger("elephant-coder.retriever")

# RRF constant — higher values favor lower-ranked results more
RRF_K = 60


def compute_relevance(access_count: int, last_access: float, created: float) -> float:
    """Compute relevance score combining recency and frequency.

    Higher score = more relevant. Decays over hours without access.
    """
    now = time.time()
    hours_since_access = max((now - last_access) / 3600.0, 0.001)
    recency = 1.0 / (1.0 + hours_since_access)
    frequency = math.log1p(access_count)
    return round(recency * 0.6 + frequency * 0.4, 4)


def _rrf_merge(
    fts_results: list[MemoryEntry],
    vector_ids: list[str],
    store: MemoryStore,
    k: int = RRF_K,
) -> list[MemoryEntry]:
    """Reciprocal Rank Fusion: merge keyword and vector results.

    Each result gets score = 1/(k + rank). Results appearing in both lists
    get summed scores, so they rank higher.
    """
    scores: dict[str, float] = {}
    entries: dict[str, MemoryEntry] = {}

    # Score FTS results by rank
    for rank, entry in enumerate(fts_results):
        mid = entry.memory_id
        scores[mid] = scores.get(mid, 0.0) + 1.0 / (k + rank)
        entries[mid] = entry

    # Score vector results by rank, fetch entries we don't have yet
    for rank, mid in enumerate(vector_ids):
        scores[mid] = scores.get(mid, 0.0) + 1.0 / (k + rank)
        if mid not in entries:
            entry = store.get(mid)
            if entry:
                entries[mid] = entry

    # Sort by fused score descending
    ranked_ids = sorted(scores.keys(), key=lambda mid: scores[mid], reverse=True)
    return [entries[mid] for mid in ranked_ids if mid in entries]


def recall(
    store: MemoryStore,
    query: str,
    limit: int = 5,
    kind: str | None = None,
    relevance_threshold: float = 0.0,
    vector_store=None,
) -> list[MemoryEntry]:
    """Hybrid search: FTS5 keywords + vector semantics, fused with RRF.

    When vector_store is available, both keyword and semantic results are
    retrieved and merged. When unavailable, falls back to FTS5 only.
    """
    fetch_count = limit * 3

    # 1. FTS5 keyword search
    fts_results = store.search_fts(query, limit=fetch_count)

    # 2. Vector semantic search (if available)
    vector_ids: list[str] = []
    if vector_store is not None:
        try:
            vector_hits = vector_store.search(query, limit=fetch_count)
            vector_ids = [hit.memory_id for hit in vector_hits]
        except Exception as exc:
            logger.warning("Vector search failed, using FTS only: %s", exc)

    # 3. Merge results
    if vector_ids:
        results = _rrf_merge(fts_results, vector_ids, store)
    else:
        results = fts_results

    # 4. Filter
    if kind:
        results = [r for r in results if r.kind == kind]

    if relevance_threshold > 0:
        results = [r for r in results if r.relevance_score >= relevance_threshold]

    results = results[:limit]

    # 5. Hebbian strengthening
    now = time.time()
    ids_to_touch = [entry.memory_id for entry in results]
    store.touch_batch(ids_to_touch)

    for entry in results:
        entry.access_count += 1
        entry.freshness = now
        entry.relevance_score = compute_relevance(
            entry.access_count, entry.freshness, entry.created
        )
        store.update_relevance(entry.memory_id, entry.relevance_score)

    return results


def recall_file(store: MemoryStore, file_path: str) -> list[MemoryEntry]:
    """Retrieve all memories for a specific file, touching each."""
    results = store.search_by_file(file_path)
    ids_to_touch = [entry.memory_id for entry in results]
    store.touch_batch(ids_to_touch)
    return results


def format_results(entries: list[MemoryEntry]) -> str:
    """Format memory entries as plain text for minimal token usage."""
    if not entries:
        return "No memories found."

    parts = []
    for i, e in enumerate(entries, 1):
        header = f"[{i}] {e.kind}: {e.symbol_name}"
        if e.file_path:
            header += f"  ({e.file_path})"
        if e.line_count and e.kind == "module":
            header += f"  [{e.line_count} lines]"
        lines = [header, e.summary]
        if e.is_stale:
            lines.append("  [STALE — source file has changed]")
        meta = f"  accessed: {e.access_count}x | relevance: {e.relevance_score:.3f}"
        lines.append(meta)
        parts.append("\n".join(lines))

    return "\n\n".join(parts)
