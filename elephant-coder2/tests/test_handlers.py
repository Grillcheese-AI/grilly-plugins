"""Tests for the broker handler layer (build_handlers): index, recall, status, etc."""
import os

import numpy as np
import pytest


@pytest.fixture
def fake_embed(monkeypatch):
    """Deterministic fake embedding so tests never load sentence-transformers."""
    def fe(text):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(384).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-8)
    monkeypatch.setattr("broker.store.embedder.embed", fe)
    monkeypatch.setattr("broker.store.unified.embed", fe)
    return fe


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path / "ec2home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "mod.py").write_text(
        '"""Module about widgets."""\n\n'
        'def make_widget(n):\n'
        '    "Build a widget."\n'
        '    return n * 2\n\n'
        'class Gadget:\n'
        '    "A gadget."\n'
        '    def run(self):\n'
        '        return 1\n',
        encoding="utf-8",
    )
    (proj / "notes.md").write_text(
        "# Auth flow\nLogin uses JWT tokens.\n\n# Caching\nRedis primary.\n",
        encoding="utf-8",
    )
    return proj


def _h(project):
    from broker.handlers import build_handlers
    # redis_url=None keeps the test hermetic (no real Redis even if one is up).
    return build_handlers(str(project), redis_url=None)


def test_index_and_status(project, fake_embed):
    store, h = _h(project)
    try:
        res = h["index_path"]({"path": str(project)})
        assert res["indexed_files"] == 2
        assert res["entries"] >= 4  # module + func + class + method + 2 headings
        st = h["status"]({})
        assert st["counts"]["total"] == res["entries"]
        assert st["project_root"] == os.path.normpath(os.path.abspath(str(project)))
    finally:
        store.close()


def test_index_mtime_skip(project, fake_embed):
    store, h = _h(project)
    try:
        h["index_path"]({"path": str(project)})
        res2 = h["index_path"]({"path": str(project)})
        assert res2["skipped"] == 2
        assert res2["indexed_files"] == 0
        assert res2["entries"] == 0
    finally:
        store.close()


def test_recall_finds_symbol(project, fake_embed):
    store, h = _h(project)
    try:
        h["index_path"]({"path": str(project)})
        hits = h["recall"]({"query": "widget", "limit": 5})
        assert hits
        assert any("widget" in (x["symbol"] + x["summary"]).lower() for x in hits)
    finally:
        store.close()


def test_recall_file(project, fake_embed):
    store, h = _h(project)
    try:
        h["index_path"]({"path": str(project)})
        hits = h["recall_file"]({"file_path": str(project / "mod.py")})
        assert len(hits) >= 3  # module docstring, make_widget, Gadget, Gadget.run
        assert all(x["kind"] in ("module", "function", "class", "method") for x in hits)
    finally:
        store.close()


def test_remember_and_search_symbol(project, fake_embed):
    store, h = _h(project)
    try:
        r = h["remember"]({"content": "x", "symbol": "FooBar", "summary": "s", "kind": "note"})
        assert "id" in r
        hits = h["search_symbol"]({"name": "FooBar"})
        assert hits and hits[0]["symbol"] == "FooBar"
    finally:
        store.close()


def test_promote(project, fake_embed):
    store, h = _h(project)
    try:
        r = h["remember"]({"content": "x", "symbol": "Z", "summary": "s"})
        h["promote"]({"memory_id": r["id"], "tier": "project_durable", "reason": "important"})
        e = store.sqlite.get(r["id"])
        assert e.tier == "project_durable"
        assert e.promotion_reason == "important"
    finally:
        store.close()


def test_ping(project, fake_embed):
    store, h = _h(project)
    try:
        assert h["ping"]({})["pong"] is True
    finally:
        store.close()


def test_sidecar_store_and_recall_by_tag(project, fake_embed):
    store, h = _h(project)
    try:
        r = h["sidecar_store"]({"tag": "auth_findings", "content": "entry points: login(), logout()"})
        assert "id" in r
        # storing the same tag again replaces it (tag is a key; latest wins)
        h["sidecar_store"]({"tag": "auth_findings", "content": "updated: login(), logout(), refresh()"})
        hits = h["sidecar_recall"]({"key": "auth_findings"})
        assert len(hits) == 1
        assert "refresh" in hits[0]["content"]
    finally:
        store.close()


def test_sidecar_recall_by_query(project, fake_embed):
    store, h = _h(project)
    try:
        h["sidecar_store"]({"tag": "db_notes", "content": "Postgres uses pgvector for embeddings"})
        hits = h["sidecar_recall"]({"key": "pgvector embeddings"})
        assert any("pgvector" in x["content"] for x in hits)
    finally:
        store.close()


def test_brief_renders(project, fake_embed):
    store, h = _h(project)
    try:
        h["index_path"]({"path": str(project)})
        out = h["brief"]({"task": "widget builder", "limit": 3})
        assert isinstance(out["brief"], str)
        assert "widget" in out["brief"].lower()
        assert out["n"] >= 1
    finally:
        store.close()


def test_related_finds_references(project, fake_embed):
    store, h = _h(project)
    try:
        h["remember"]({"content": "def helper(): pass", "symbol": "helper", "summary": "helper fn"})
        h["remember"]({"content": "this one calls helper() twice", "symbol": "caller", "summary": "caller"})
        rel = h["related"]({"symbol": "helper"})
        assert rel["definitions"][0]["symbol"] == "helper"
        assert "caller" in {x["symbol"] for x in rel["references"]}
        assert "helper" not in {x["symbol"] for x in rel["references"]}  # own defs excluded
    finally:
        store.close()


def test_forget(project, fake_embed):
    store, h = _h(project)
    try:
        r = h["remember"]({"content": "x", "symbol": "Temp", "summary": "s"})
        h["forget"]({"memory_id": r["id"]})
        assert store.sqlite.get(r["id"]) is None
    finally:
        store.close()


def test_recent_orders_newest_first(project, fake_embed):
    store, h = _h(project)
    try:
        h["remember"]({"content": "a", "symbol": "First", "summary": "first"})
        h["remember"]({"content": "b", "symbol": "Second", "summary": "second"})
        rec = h["recent"]({"limit": 2})
        assert [r["symbol"] for r in rec] == ["Second", "First"]
        assert "created_at" in rec[0]
    finally:
        store.close()


def test_sidecar_list(project, fake_embed):
    store, h = _h(project)
    try:
        h["sidecar_store"]({"tag": "ctx:auth", "content": "auth stuff"})
        h["sidecar_store"]({"tag": "ctx:db", "content": "db stuff"})
        h["remember"]({"content": "not a sidecar", "symbol": "ctx:other"})  # excluded
        tags = {x["tag"] for x in h["sidecar_list"]({})}
        assert tags == {"ctx:auth", "ctx:db"}
        only_auth = h["sidecar_list"]({"prefix": "ctx:a"})
        assert {x["tag"] for x in only_auth} == {"ctx:auth"}
    finally:
        store.close()
