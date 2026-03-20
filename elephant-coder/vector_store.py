"""
Vector store for elephant-coder — semantic search with project bucketing.

Architecture:
- Qdrant (optional primary): fast ANN search with HNSW, project isolation via payload filter
- Local fallback: numpy cosine similarity with memory-mapped embeddings
- Encoder: sentence-transformers all-MiniLM-L6-v2 (384-dim, matches existing Qdrant collection)

Project bucketing:
- Each project gets its own namespace (project_hash in Qdrant payload or separate .npy file)
- Global queries can search across all projects with project_hash as metadata
- No cross-project pollution by default
"""

import hashlib
import json
import logging
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger("elephant-coder.vectors")

# Embedding dimension for all-MiniLM-L6-v2
EMBED_DIM = 384
COLLECTION_NAME = "elephant_coder"


@dataclass
class VectorResult:
    """A single vector search result."""
    memory_id: str
    score: float
    project_hash: str


class Encoder:
    """Lazy-loaded sentence-transformers encoder.

    Loads the model on first use to avoid startup delay when vector search
    isn't needed. Thread-safe after first load (model is read-only).
    """

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def encode(self, texts: list[str] | str) -> np.ndarray:
        """Encode text(s) into 384-dim normalized vectors."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Loaded encoder: all-MiniLM-L6-v2 (384-dim)")
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
        if isinstance(texts, str):
            texts = [texts]
        embeddings = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(embeddings, dtype=np.float32)


def _project_hash(project_root: str) -> str:
    return hashlib.sha256(project_root.encode()).hexdigest()[:12]


def _vectors_dir(project_root: str) -> Path:
    """Per-project vector storage directory."""
    phash = _project_hash(project_root)
    base = Path.home() / ".elephant-coder" / phash
    base.mkdir(parents=True, exist_ok=True)
    return base


# ------------------------------------------------------------------
# Qdrant Backend
# ------------------------------------------------------------------

class QdrantBackend:
    """Qdrant vector backend with project bucketing via payload filter."""

    def __init__(self, url: str, project_root: str):
        self._project_hash = _project_hash(project_root)
        self._available = False
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            self._client = QdrantClient(url=url, timeout=5)
            # Ensure collection exists
            collections = [c.name for c in self._client.get_collections().collections]
            if COLLECTION_NAME not in collections:
                self._client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
                )
                logger.info("Created Qdrant collection: %s", COLLECTION_NAME)
            self._available = True
            logger.info("Qdrant connected: %s (project: %s)", url, self._project_hash)
        except Exception as exc:
            logger.info("Qdrant not available at %s — will use local fallback: %s", url, exc)

    @property
    def available(self) -> bool:
        return self._available

    def upsert(self, memory_id: str, vector: np.ndarray, metadata: dict | None = None) -> None:
        if not self._available:
            return
        try:
            from qdrant_client.models import PointStruct
            payload = {"project_hash": self._project_hash, "memory_id": memory_id}
            if metadata:
                payload.update(metadata)
            point = PointStruct(
                id=self._point_id(memory_id),
                vector=vector.tolist(),
                payload=payload,
            )
            self._client.upsert(collection_name=COLLECTION_NAME, points=[point])
        except Exception as exc:
            logger.warning("Qdrant upsert failed: %s", exc)

    def upsert_batch(self, items: list[tuple[str, np.ndarray, dict | None]]) -> None:
        """Batch upsert: list of (memory_id, vector, metadata)."""
        if not self._available or not items:
            return
        try:
            from qdrant_client.models import PointStruct
            points = []
            for memory_id, vector, metadata in items:
                payload = {"project_hash": self._project_hash, "memory_id": memory_id}
                if metadata:
                    payload.update(metadata)
                points.append(PointStruct(
                    id=self._point_id(memory_id),
                    vector=vector.tolist(),
                    payload=payload,
                ))
            self._client.upsert(collection_name=COLLECTION_NAME, points=points)
        except Exception as exc:
            logger.warning("Qdrant batch upsert failed: %s", exc)

    def search(self, vector: np.ndarray, limit: int = 10,
               global_search: bool = False) -> list[VectorResult]:
        """Search for similar vectors. Scoped to current project unless global_search=True."""
        if not self._available:
            return []
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = None
            if not global_search:
                query_filter = Filter(must=[
                    FieldCondition(key="project_hash", match=MatchValue(value=self._project_hash))
                ])
            hits = self._client.search(
                collection_name=COLLECTION_NAME,
                query_vector=vector.tolist(),
                query_filter=query_filter,
                limit=limit,
            )
            return [
                VectorResult(
                    memory_id=hit.payload.get("memory_id", ""),
                    score=hit.score,
                    project_hash=hit.payload.get("project_hash", ""),
                )
                for hit in hits
            ]
        except Exception as exc:
            logger.warning("Qdrant search failed: %s", exc)
            return []

    def delete(self, memory_id: str) -> None:
        if not self._available:
            return
        try:
            from qdrant_client.models import PointIdsList
            self._client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=PointIdsList(points=[self._point_id(memory_id)]),
            )
        except Exception:
            pass

    def delete_project(self) -> None:
        """Delete all vectors for the current project."""
        if not self._available:
            return
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            self._client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(must=[
                    FieldCondition(key="project_hash", match=MatchValue(value=self._project_hash))
                ]),
            )
        except Exception:
            pass

    def count(self, global_count: bool = False) -> int:
        if not self._available:
            return 0
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            if global_count:
                info = self._client.get_collection(COLLECTION_NAME)
                return info.points_count
            result = self._client.count(
                collection_name=COLLECTION_NAME,
                count_filter=Filter(must=[
                    FieldCondition(key="project_hash", match=MatchValue(value=self._project_hash))
                ]),
            )
            return result.count
        except Exception:
            return 0

    @staticmethod
    def _point_id(memory_id: str) -> int:
        """Convert memory_id (hex string) to a positive integer for Qdrant."""
        return int(hashlib.sha256(memory_id.encode()).hexdigest()[:15], 16)


# ------------------------------------------------------------------
# Local Numpy Backend (fallback)
# ------------------------------------------------------------------

class LocalBackend:
    """Local numpy-based vector search with per-project storage.

    Stores embeddings in a flat .npy file and an index mapping in a JSON file.
    Search uses brute-force cosine similarity (fast for <100k vectors at 384-dim).
    """

    def __init__(self, project_root: str):
        self._dir = _vectors_dir(project_root)
        self._vectors_path = self._dir / "vectors.npy"
        self._index_path = self._dir / "vector_index.json"
        self._project_hash = _project_hash(project_root)

        # In-memory state
        self._vectors: np.ndarray | None = None  # (N, 384)
        self._index: dict[str, int] = {}  # memory_id -> row index
        self._dirty = False

        self._load()

    def _load(self) -> None:
        """Load vectors and index from disk."""
        if self._vectors_path.exists() and self._index_path.exists():
            try:
                self._vectors = np.load(str(self._vectors_path))
                with open(self._index_path, "r") as f:
                    self._index = json.load(f)
                logger.info("Loaded %d local vectors for project %s",
                            len(self._index), self._project_hash)
            except Exception as exc:
                logger.warning("Failed to load local vectors: %s", exc)
                self._vectors = np.zeros((0, EMBED_DIM), dtype=np.float32)
                self._index = {}
        else:
            self._vectors = np.zeros((0, EMBED_DIM), dtype=np.float32)
            self._index = {}

    def _save(self) -> None:
        """Persist vectors and index to disk."""
        if not self._dirty:
            return
        try:
            np.save(str(self._vectors_path), self._vectors)
            with open(self._index_path, "w") as f:
                json.dump(self._index, f)
            self._dirty = False
        except Exception as exc:
            logger.warning("Failed to save local vectors: %s", exc)

    def upsert(self, memory_id: str, vector: np.ndarray, metadata: dict | None = None) -> None:
        vec = vector.reshape(1, EMBED_DIM).astype(np.float32)
        if memory_id in self._index:
            # Update existing
            idx = self._index[memory_id]
            self._vectors[idx] = vec[0]
        else:
            # Append
            idx = self._vectors.shape[0]
            self._vectors = np.vstack([self._vectors, vec]) if self._vectors.shape[0] > 0 else vec
            self._index[memory_id] = idx
        self._dirty = True

    def upsert_batch(self, items: list[tuple[str, np.ndarray, dict | None]]) -> None:
        if not items:
            return
        for memory_id, vector, metadata in items:
            self.upsert(memory_id, vector, metadata)
        self._save()

    def search(self, vector: np.ndarray, limit: int = 10,
               global_search: bool = False) -> list[VectorResult]:
        if self._vectors is None or self._vectors.shape[0] == 0:
            return []
        query = vector.reshape(1, EMBED_DIM).astype(np.float32)
        # Cosine similarity (vectors are already normalized)
        scores = (self._vectors @ query.T).flatten()
        top_k = min(limit, len(scores))
        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        # Reverse lookup: index -> memory_id
        idx_to_id = {v: k for k, v in self._index.items()}
        results = []
        for idx in top_indices:
            mid = idx_to_id.get(int(idx))
            if mid and scores[idx] > 0:
                results.append(VectorResult(
                    memory_id=mid,
                    score=float(scores[idx]),
                    project_hash=self._project_hash,
                ))
        return results

    def delete(self, memory_id: str) -> None:
        if memory_id not in self._index:
            return
        idx = self._index.pop(memory_id)
        # Mark row as zero (lazy deletion — compacted on save/load)
        if self._vectors is not None and idx < self._vectors.shape[0]:
            self._vectors[idx] = 0
        self._dirty = True

    def count(self, global_count: bool = False) -> int:
        return len(self._index)

    def flush(self) -> None:
        """Force save to disk."""
        self._save()


# ------------------------------------------------------------------
# VectorStore — unified interface
# ------------------------------------------------------------------

class VectorStore:
    """Unified vector store: Qdrant primary, local numpy fallback.

    Project-scoped by default. Global search available for cross-project queries.
    """

    def __init__(self, project_root: str, qdrant_url: str | None = None):
        self._project_root = project_root
        self._encoder = Encoder()

        # Try Qdrant first
        self._qdrant: QdrantBackend | None = None
        if qdrant_url:
            self._qdrant = QdrantBackend(qdrant_url, project_root)
            if not self._qdrant.available:
                self._qdrant = None

        # Always initialize local backend (fallback + offline support)
        self._local = LocalBackend(project_root)

        self._mode = "qdrant" if self._qdrant else "local"
        logger.info("VectorStore mode: %s", self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    def embed_text(self, text: str) -> np.ndarray:
        """Encode text into a 384-dim vector. Exposed for external use."""
        return self._encoder.encode(text)[0]

    def upsert(self, memory_id: str, text: str, metadata: dict | None = None) -> None:
        """Embed and store a single entry."""
        vector = self._encoder.encode(text)[0]
        if self._qdrant:
            self._qdrant.upsert(memory_id, vector, metadata)
        self._local.upsert(memory_id, vector, metadata)

    def upsert_batch(self, items: list[tuple[str, str, dict | None]]) -> None:
        """Embed and store multiple entries. items: [(memory_id, text, metadata), ...]"""
        if not items:
            return
        texts = [text for _, text, _ in items]
        vectors = self._encoder.encode(texts)

        batch = [(mid, vectors[i], meta) for i, (mid, _, meta) in enumerate(items)]
        if self._qdrant:
            self._qdrant.upsert_batch(batch)
        self._local.upsert_batch(batch)

    def search(self, query: str, limit: int = 10,
               global_search: bool = False) -> list[VectorResult]:
        """Semantic search: encode query and find similar vectors."""
        vector = self._encoder.encode(query)[0]
        if self._qdrant:
            results = self._qdrant.search(vector, limit, global_search)
            if results:
                return results
        # Fallback to local
        return self._local.search(vector, limit, global_search)

    def delete(self, memory_id: str) -> None:
        if self._qdrant:
            self._qdrant.delete(memory_id)
        self._local.delete(memory_id)

    def flush(self) -> None:
        """Persist local vectors to disk."""
        self._local.flush()

    def stats(self) -> dict:
        result = {"mode": self._mode, "encoder": "all-MiniLM-L6-v2", "dim": EMBED_DIM}
        if self._qdrant:
            result["qdrant_project_vectors"] = self._qdrant.count()
            result["qdrant_total_vectors"] = self._qdrant.count(global_count=True)
        result["local_vectors"] = self._local.count()
        return result
