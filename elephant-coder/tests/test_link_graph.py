import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from memory_store import MemoryStore
from link_graph import resolve_python_imports, resolve_cpp_includes, detect_shader_dispatches


def test_add_and_query_file_links():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        store.add_file_link("/src/main.py", "/src/utils.py", "import", "utils")
        store.add_file_link("/src/main.py", "/src/config.py", "import", "config")
        store.add_file_link("/src/app.py", "/src/utils.py", "import", "utils")
        imports = store.get_outbound_links("/src/main.py")
        assert len(imports) == 2
        targets = {link["target_path"] for link in imports}
        assert "/src/utils.py" in targets
        assert "/src/config.py" in targets
        importers = store.get_inbound_links("/src/utils.py")
        assert len(importers) == 2
        store.close()


def test_hub_detection():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        for i in range(5):
            store.add_file_link(f"/src/file_{i}.py", "/src/utils.py", "import")
        for i in range(2):
            store.add_file_link(f"/src/file_{i}.py", "/src/config.py", "import")
        hubs = store.get_hub_files(limit=5)
        assert len(hubs) >= 2
        assert hubs[0]["file_path"] == "/src/utils.py"
        assert hubs[0]["inbound_count"] == 5
        store.close()


def test_clear_file_links():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        store.add_file_link("/src/main.py", "/src/a.py", "import")
        store.add_file_link("/src/main.py", "/src/b.py", "import")
        assert len(store.get_outbound_links("/src/main.py")) == 2
        store.clear_file_links("/src/main.py")
        assert len(store.get_outbound_links("/src/main.py")) == 0
        store.close()


def test_shader_dispatch_link():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        store.add_file_link("/backend/conv.py", "/shaders/conv2d_gemm.glsl", "shader_dispatch", "conv2d_forward")
        links = store.get_outbound_links("/backend/conv.py")
        assert len(links) == 1
        assert links[0]["link_type"] == "shader_dispatch"
        assert links[0]["symbol_name"] == "conv2d_forward"
        store.close()


def test_batch_add_links():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(tmpdir, redis_url="redis://localhost:59999")
        links = [
            ("/src/main.py", "/src/a.py", "import", "a"),
            ("/src/main.py", "/src/b.py", "import", "b"),
            ("/src/main.py", "/src/c.py", "import", None),
        ]
        store.add_file_links_batch(links)
        assert len(store.get_outbound_links("/src/main.py")) == 3
        store.close()
