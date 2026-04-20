from pathlib import Path
from broker.settings import load_settings, Settings


def test_defaults_when_no_file(tmp_path):
    s = load_settings(tmp_path)
    assert s.max_scratch_entries == 32000
    assert s.max_durable_entries == 50000
    assert s.redis_url == "redis://localhost:6379"
    assert s.injection.prompt_budget_tokens == 800
    assert s.injection.tool_budget_tokens == 300
    assert s.injection.agent_brief_tokens == 500
    assert s.sidecar.rerank_latency_ms == 500


def test_overrides_from_yaml_frontmatter(tmp_path):
    cfg = tmp_path / ".claude" / "elephant-coder2.local.md"
    cfg.parent.mkdir()
    cfg.write_text(
        "---\n"
        "max_scratch_entries: 5000\n"
        "injection:\n"
        "  prompt_budget_tokens: 400\n"
        "sidecar:\n"
        "  model_path: other.gguf\n"
        "---\n"
        "free text below\n"
    )
    s = load_settings(tmp_path)
    assert s.max_scratch_entries == 5000
    assert s.injection.prompt_budget_tokens == 400
    assert s.sidecar.model_path == "other.gguf"
    assert s.max_durable_entries == 50000
