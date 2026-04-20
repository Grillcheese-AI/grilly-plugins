import pytest
from broker.store.sqlite_store import SQLiteStore, MemoryEntry


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(tmp_path / "mem.db")
    yield s
    s.close()


def test_insert_and_fetch(store):
    mid = store.insert(MemoryEntry(
        file_path="a/b.py", symbol="foo", kind="function",
        content="def foo(): return 1", summary="simple foo",
        keywords="foo function", tier="scratch",
    ))
    assert mid > 0
    got = store.get(mid)
    assert got.symbol == "foo"
    assert got.tier == "scratch"
    assert got.access_count == 0
    assert got.is_protected == 0


def test_fts5_search(store):
    store.insert(MemoryEntry(
        file_path="auth.py", symbol="verify_token", kind="function",
        content="check token", summary="verify jwt token",
        keywords="auth token jwt", tier="scratch"))
    store.insert(MemoryEntry(
        file_path="db.py", symbol="connect", kind="function",
        content="open db", summary="db connection",
        keywords="database sql", tier="scratch"))
    results = store.fts_search("jwt", limit=10)
    assert len(results) == 1
    assert results[0].symbol == "verify_token"


def test_tier_flip(store):
    mid = store.insert(MemoryEntry(
        file_path="x.py", symbol="s", kind="function",
        content="c", summary="s", keywords="s", tier="scratch"))
    store.set_tier(mid, "project_durable", reason="it's important")
    got = store.get(mid)
    assert got.tier == "project_durable"
    assert got.promotion_reason == "it's important"


def test_bump_access(store):
    mid = store.insert(MemoryEntry(
        file_path="x.py", symbol="s", kind="function",
        content="c", summary="s", keywords="s", tier="scratch"))
    store.bump_access([mid, mid])
    got = store.get(mid)
    assert got.access_count == 2


def test_filter_by_tier(store):
    a = store.insert(MemoryEntry(file_path="a.py", symbol="a", kind="function",
        content="a", summary="a", keywords="a", tier="scratch"))
    b = store.insert(MemoryEntry(file_path="b.py", symbol="b", kind="function",
        content="b", summary="b", keywords="b", tier="project_durable"))
    scratch = list(store.iter_by_tier("scratch"))
    durable = list(store.iter_by_tier("project_durable"))
    assert {m.id for m in scratch} == {a}
    assert {m.id for m in durable} == {b}


def test_delete(store):
    mid = store.insert(MemoryEntry(file_path="x.py", symbol="s", kind="function",
        content="c", summary="s", keywords="s", tier="scratch"))
    store.delete(mid)
    assert store.get(mid) is None
