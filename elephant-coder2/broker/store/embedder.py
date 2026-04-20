"""Sentence-transformer wrapper. Lazy-loads to keep broker startup fast."""
from __future__ import annotations

import numpy as np

_MODEL = None
_MODEL_NAME = "all-MiniLM-L6-v2"
DIM = 384


def _load():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def embed(text: str) -> np.ndarray:
    m = _load()
    v = m.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return v.astype(np.float32)


def embed_batch(texts: list[str]) -> np.ndarray:
    m = _load()
    vs = m.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vs.astype(np.float32)
