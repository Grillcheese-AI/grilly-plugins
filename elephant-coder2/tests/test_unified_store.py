import pytest
from broker.store.unified import UnifiedStore
from broker.store.sqlite_store import MemoryEntry


@pytest.fixture
def store(tmp_path, monkeypatch):
    import broker.store.embedder as emb
    import numpy as np
    def fake_embed(text):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(384).astype(np.float32)
        v /= (np.linalg.norm(v) + 1e-8)
        return v
    monkeypatch.setattr(emb, "embed", fake_embed)
    s = UnifiedStore(
        sqlite_path=tmp_path / "mem.db",
        vector_prefix=tmp_path / "vec",
        redis_url=None,
        project_hash="p",
    )
    yield s
    s.close()


def test_insert_creates_sqlite_and_vector(store):
    e = MemoryEntry(file_path="a.py", symbol="foo", kind="function",
                    content="c", summary="s", keywords="k", tier="scratch")
    mid = store.insert(e)
    assert store.sqlite.get(mid) is not None
    assert mid in store.vectors._ids


def test_delete_removes_from_both(store):
    mid = store.insert(MemoryEntry(
        file_path="a.py", symbol="foo", kind="function",
        content="c", summary="s", keywords="k", tier="scratch"))
    store.delete(mid)
    assert store.sqlite.get(mid) is None
    assert mid not in store.vectors._ids


def test_set_tier_persists(store):
    mid = store.insert(MemoryEntry(
        file_path="a.py", symbol="foo", kind="function",
        content="c", summary="s", keywords="k", tier="scratch"))
    store.set_tier(mid, "project_durable", reason="hub file")
    e = store.sqlite.get(mid)
    assert e.tier == "project_durable"
    assert e.promotion_reason == "hub file"
