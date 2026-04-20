"""numpy-based vector store with cosine similarity. Persists as .npy + .json index."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class VectorStore:
    def __init__(self, prefix: str | Path, dim: int):
        self.prefix = Path(prefix)
        self.dim = dim
        self._vec_path = self.prefix.with_suffix(".npy")
        self._idx_path = self.prefix.with_suffix(".json")
        self._vectors: np.ndarray = np.zeros((0, dim), dtype=np.float32)
        self._ids: list[int] = []
        self._load()

    def _load(self) -> None:
        if self._vec_path.exists() and self._idx_path.exists():
            self._vectors = np.load(self._vec_path)
            self._ids = json.loads(self._idx_path.read_text())

    def save(self) -> None:
        self.prefix.parent.mkdir(parents=True, exist_ok=True)
        np.save(self._vec_path, self._vectors)
        self._idx_path.write_text(json.dumps(self._ids))

    def add(self, memory_id: int, vec: np.ndarray) -> None:
        v = vec.astype(np.float32).reshape(1, -1)
        if v.shape[1] != self.dim:
            raise ValueError(f"dim mismatch: got {v.shape[1]}, expected {self.dim}")
        if memory_id in self._ids:
            i = self._ids.index(memory_id)
            self._vectors[i] = v[0]
        else:
            self._vectors = np.vstack([self._vectors, v])
            self._ids.append(memory_id)
        self.save()

    def remove(self, memory_id: int) -> None:
        if memory_id not in self._ids:
            return
        i = self._ids.index(memory_id)
        self._vectors = np.delete(self._vectors, i, axis=0)
        del self._ids[i]
        self.save()

    def search(self, query: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
        if len(self._ids) == 0:
            return []
        q = query.astype(np.float32).reshape(-1)
        qn = q / (np.linalg.norm(q) + 1e-8)
        keys = self._vectors
        kn = keys / (np.linalg.norm(keys, axis=1, keepdims=True) + 1e-8)
        sims = kn @ qn
        if k >= len(sims):
            order = np.argsort(sims)[::-1]
        else:
            idx = np.argpartition(sims, -k)[-k:]
            order = idx[np.argsort(sims[idx])[::-1]]
        return [(self._ids[i], float(sims[i])) for i in order]

    def __len__(self) -> int:
        return len(self._ids)
