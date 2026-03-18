import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from global_store import GlobalKnowledgeStore


def test_store_framework_knowledge():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = GlobalKnowledgeStore(base_dir=tmpdir)
        store.save_framework(
            name="grilly", repo_path="/path/to/grilly", github="Grillcheese-AI/grilly",
            api_map={"torch.nn.Linear": "grilly.nn.Linear"},
            quick_start="from grilly.nn import Linear",
            differences=["Vulkan instead of CUDA", "numpy not torch.Tensor"])
        fw = store.get_framework("grilly")
        assert fw is not None
        assert fw["name"] == "grilly"
        assert fw["api_map"]["torch.nn.Linear"] == "grilly.nn.Linear"
        store.close()


def test_store_session_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = GlobalKnowledgeStore(base_dir=tmpdir)
        store.save_session_summary(project="grilly",
            summary="Worked on Conv2d GEMM path. Blocked by GPU transpose kernel.",
            tasks_completed=["T-001"], tasks_remaining=["T-002"])
        sessions = store.get_recent_sessions("grilly", limit=5)
        assert len(sessions) == 1
        assert "Conv2d" in sessions[0]["summary"]
        store.close()


def test_store_research_note():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = GlobalKnowledgeStore(base_dir=tmpdir)
        store.save_note(topic="LSH attention",
            summary="Reduces O(n^2) to O(n log n) via locality-sensitive hashing",
            source="arxiv:2106.04554", tags=["attention", "performance"])
        notes = store.search_notes("attention")
        assert len(notes) == 1
        assert notes[0]["topic"] == "LSH attention"
        store.close()


def test_store_idiom():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = GlobalKnowledgeStore(base_dir=tmpdir)
        store.save_idiom("VulkanCompute with gpu_mode(True)", "initialization", project="grilly")
        store.save_idiom("VulkanCompute with gpu_mode(True)", "initialization", project="grilly")
        idioms = store.get_idioms(project="grilly")
        assert len(idioms) == 1
        assert idioms[0]["frequency"] == 2
        store.close()


def test_get_notes_by_tags():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = GlobalKnowledgeStore(base_dir=tmpdir)
        store.save_note(topic="Flash attention", summary="Fast attention", tags=["attention", "gpu"])
        store.save_note(topic="LoRA adapters", summary="Low-rank adaptation", tags=["training", "efficiency"])
        store.save_note(topic="Sparse attention", summary="Sparse patterns", tags=["attention", "sparse"])
        notes = store.get_notes_by_tags(["attention"])
        assert len(notes) == 2
        topics = {n["topic"] for n in notes}
        assert "Flash attention" in topics
        assert "Sparse attention" in topics
        store.close()
