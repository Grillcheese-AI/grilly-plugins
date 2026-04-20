import numpy as np
from broker.store.vector_store import VectorStore


def test_add_and_search(tmp_path):
    vs = VectorStore(tmp_path / "vec", dim=4)
    vs.add(1, np.array([1, 0, 0, 0], dtype=np.float32))
    vs.add(2, np.array([0, 1, 0, 0], dtype=np.float32))
    vs.add(3, np.array([0.9, 0.1, 0, 0], dtype=np.float32))
    results = vs.search(np.array([1, 0, 0, 0], dtype=np.float32), k=2)
    ids = [mid for mid, _ in results]
    assert ids[0] == 1
    assert ids[1] == 3


def test_persists_across_instances(tmp_path):
    vs = VectorStore(tmp_path / "vec", dim=4)
    vs.add(10, np.array([1, 0, 0, 0], dtype=np.float32))
    vs.save()
    vs2 = VectorStore(tmp_path / "vec", dim=4)
    results = vs2.search(np.array([1, 0, 0, 0], dtype=np.float32), k=1)
    assert results[0][0] == 10


def test_remove(tmp_path):
    vs = VectorStore(tmp_path / "vec", dim=4)
    vs.add(1, np.array([1, 0, 0, 0], dtype=np.float32))
    vs.add(2, np.array([0, 1, 0, 0], dtype=np.float32))
    vs.remove(1)
    results = vs.search(np.array([1, 0, 0, 0], dtype=np.float32), k=2)
    assert 1 not in {mid for mid, _ in results}
