"""Per-project settings loaded from .claude/elephant-coder2.local.md YAML frontmatter."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class InjectionSettings:
    prompt_budget_tokens: int = 800
    tool_budget_tokens: int = 300
    agent_brief_tokens: int = 500


@dataclass
class SidecarSettings:
    model_path: str = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    n_gpu_layers: int = -1
    rerank_latency_ms: int = 500
    n_ctx: int = 8192


@dataclass
class ExternalSettings:
    openrouter_api_key: str | None = None
    model: str = "google/gemini-3.1-flash-lite-preview"


@dataclass
class Settings:
    max_scratch_entries: int = 32000
    max_durable_entries: int = 50000
    redis_url: str = "redis://localhost:6379"
    redis_ttl_seconds: int = 60 * 60 * 24 * 365
    scratch_idle_consolidation_minutes: int = 10
    injection: InjectionSettings = field(default_factory=InjectionSettings)
    sidecar: SidecarSettings = field(default_factory=SidecarSettings)
    external: ExternalSettings = field(default_factory=ExternalSettings)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    data = yaml.safe_load(block) or {}
    return data if isinstance(data, dict) else {}


def _merge_into(obj: Any, overrides: dict[str, Any]) -> Any:
    for k, v in overrides.items():
        if not hasattr(obj, k):
            continue
        current = getattr(obj, k)
        if hasattr(current, "__dataclass_fields__") and isinstance(v, dict):
            _merge_into(current, v)
        else:
            setattr(obj, k, v)
    return obj


def load_settings(project_root: Path) -> Settings:
    """Load settings for a project; returns defaults if no config file."""
    s = Settings()
    cfg = Path(project_root) / ".claude" / "elephant-coder2.local.md"
    if not cfg.exists():
        return s
    overrides = _parse_frontmatter(cfg.read_text(encoding="utf-8"))
    _merge_into(s, overrides)
    return s
