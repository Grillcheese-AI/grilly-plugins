"""
Settings parser for elephant-coder.

Reads `.claude/elephant-coder.local.md` files with YAML frontmatter and merges
them with sensible defaults.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SETTINGS: dict[str, Any] = {
    "max_memories": 50_000,
    "relevance_threshold": 0.1,
    "redis_url": "redis://localhost:6380",
    "redis_ttl": 365 * 24 * 3600,
    "skip_dirs": [".venv", "node_modules", "__pycache__", "dist", "build", ".git", ".eggs"],
    "frameworks": [],
    "auto_test_after_edit": True,
    "scope_guard": True,
    "external_validation": {
        "enabled": False,
        "openrouter_api_key": None,
        "model": "google/gemini-3.1-flash-lite-preview",
        "validate_plans": True,
        "audit_completed_tasks": True,
        "require_approval_on_issues": True,
    },
    "rss_feeds": [
        "https://hackernoon.com/feed",
        "https://globalnews.ca/feed/",
        "https://feedx.net/rss/ap.xml",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://techcrunch.com/feed/",
        "https://blog.bytebytego.com/feed",
        "https://www.wired.com/feed/tag/ai/latest/rss",
        "https://www.wired.com/feed/category/ideas/latest/rss",
        "https://rss.arxiv.org/rss/math.QA",
        "https://rss.arxiv.org/rss/cs.ai",
        "https://www.reddit.com/r/news/.rss",
        "https://www.reddit.com/r/LocalLLaMA/.rss",
        "https://www.reddit.com/r/singularity/.rss",
        "https://www.cbc.ca/webfeed/rss/rss-topstories",
        "https://www.cbc.ca/webfeed/rss/rss-technology",
        "https://www.cbc.ca/webfeed/rss/rss-world",
    ],
    "rss_max_articles_per_feed": 5,
    "rss_fetch_full_articles": True,
}

_SETTINGS_PATH = Path(".claude") / "elephant-coder.local.md"


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML between the first pair of ``---`` markers and return parsed dict."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}

    end_index = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index is None:
        return {}

    yaml_text = "".join(lines[1:end_index])
    parsed = yaml.safe_load(yaml_text)
    if isinstance(parsed, dict):
        return parsed
    return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into a copy of *base* and return the result."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_settings(project_root: str) -> dict[str, Any]:
    """Load settings from ``.claude/elephant-coder.local.md`` and merge with defaults.

    Falls back to ``OPENROUTER_API_KEY`` environment variable when the api key
    is not set in the file.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        Merged settings dict.
    """
    settings_file = Path(project_root) / _SETTINGS_PATH

    file_settings: dict[str, Any] = {}
    if settings_file.exists():
        text = settings_file.read_text(encoding="utf-8")
        file_settings = _parse_frontmatter(text)

    merged = _deep_merge(DEFAULT_SETTINGS, file_settings)

    # Apply OPENROUTER_API_KEY env var as fallback (file value takes precedence)
    if merged["external_validation"]["openrouter_api_key"] is None:
        env_key = os.environ.get("OPENROUTER_API_KEY")
        if env_key:
            merged["external_validation"]["openrouter_api_key"] = env_key

    return merged


def save_settings(project_root: str, settings: dict[str, Any]) -> str:
    """Write *settings* as YAML frontmatter to ``.claude/elephant-coder.local.md``.

    Preserves any existing markdown body that follows the frontmatter block.

    Args:
        project_root: Absolute path to the project root directory.
        settings: Settings dict to serialise.

    Returns:
        Absolute path of the written file as a string.
    """
    settings_file = Path(project_root) / _SETTINGS_PATH
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    # Preserve existing markdown body
    body = ""
    if settings_file.exists():
        existing = settings_file.read_text(encoding="utf-8")
        lines = existing.splitlines(keepends=True)
        if lines and lines[0].strip() == "---":
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    body = "".join(lines[i + 1 :])
                    break

    yaml_text = yaml.dump(settings, default_flow_style=False, allow_unicode=True, sort_keys=True)
    content = f"---\n{yaml_text}---\n{body}"

    settings_file.write_text(content, encoding="utf-8")
    return str(settings_file.resolve())
