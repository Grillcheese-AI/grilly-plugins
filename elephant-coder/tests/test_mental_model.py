import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import tempfile
from memory_store import MemoryStore, MemoryEntry, make_memory_id
from mental_model import generate_mental_model


def test_generate_mental_model_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        store.upsert(MemoryEntry(
            memory_id=make_memory_id(os.path.join(tmpdir, "main.py"), "main", "module"),
            file_path=os.path.join(tmpdir, "main.py"), symbol_name="main", kind="module",
            summary="Entry point. Imports: utils, config", keywords=["main", "entry"], line_count=50))
        store.upsert(MemoryEntry(
            memory_id=make_memory_id(os.path.join(tmpdir, "utils.py"), "utils", "module"),
            file_path=os.path.join(tmpdir, "utils.py"), symbol_name="utils", kind="module",
            summary="Utility functions for data processing", keywords=["utils", "data"], line_count=200))
        store.add_file_link(os.path.join(tmpdir, "main.py"), os.path.join(tmpdir, "utils.py"), "import", "utils")
        model = generate_mental_model(store, tmpdir)
        assert "Project Mental Model" in model
        assert "utils" in model.lower()
        store.close()


def test_mental_model_shows_hubs():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        hub_path = os.path.join(tmpdir, "core.py")
        store.upsert(MemoryEntry(
            memory_id=make_memory_id(hub_path, "core", "module"),
            file_path=hub_path, symbol_name="core", kind="module",
            summary="Core module", keywords=["core"], line_count=500))
        for i in range(5):
            store.add_file_link(f"/src/file_{i}.py", hub_path, "import")
        model = generate_mental_model(store, tmpdir)
        assert "core" in model.lower()
        assert "5" in model  # 5 importers
        store.close()


def test_mental_model_shows_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        model = generate_mental_model(store, tmpdir)
        assert "Memory:" in model
        assert "0/" in model  # empty store
        store.close()
