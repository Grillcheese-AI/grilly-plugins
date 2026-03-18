import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import tempfile
import pytest
from settings import DEFAULT_SETTINGS, load_settings, save_settings


def test_default_settings_when_no_file():
    """Returns defaults when .claude/elephant-coder.local.md doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_settings(tmpdir)
        assert result["max_memories"] == DEFAULT_SETTINGS["max_memories"]
        assert result["relevance_threshold"] == DEFAULT_SETTINGS["relevance_threshold"]
        assert result["redis_url"] == DEFAULT_SETTINGS["redis_url"]
        assert result["redis_ttl"] == DEFAULT_SETTINGS["redis_ttl"]
        assert result["skip_dirs"] == DEFAULT_SETTINGS["skip_dirs"]
        assert result["frameworks"] == DEFAULT_SETTINGS["frameworks"]
        assert result["auto_test_after_edit"] == DEFAULT_SETTINGS["auto_test_after_edit"]
        assert result["scope_guard"] == DEFAULT_SETTINGS["scope_guard"]
        assert result["external_validation"] == DEFAULT_SETTINGS["external_validation"]


def test_load_settings_from_file():
    """Parses full YAML frontmatter with all fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "elephant-coder.local.md"
        settings_file.write_text(
            "---\n"
            "max_memories: 10000\n"
            "relevance_threshold: 0.25\n"
            "redis_url: redis://myhost:6381\n"
            "redis_ttl: 86400\n"
            "skip_dirs:\n"
            "  - .venv\n"
            "  - node_modules\n"
            "frameworks:\n"
            "  - pytorch\n"
            "  - numpy\n"
            "auto_test_after_edit: false\n"
            "scope_guard: false\n"
            "external_validation:\n"
            "  enabled: true\n"
            "  openrouter_api_key: sk-or-test-key\n"
            "  model: google/gemini-3.1-flash-lite-preview\n"
            "  validate_plans: false\n"
            "  audit_completed_tasks: true\n"
            "  require_approval_on_issues: false\n"
            "---\n"
            "# My project notes\n"
            "Some markdown body here.\n",
            encoding="utf-8",
        )

        result = load_settings(tmpdir)

        assert result["max_memories"] == 10000
        assert result["relevance_threshold"] == 0.25
        assert result["redis_url"] == "redis://myhost:6381"
        assert result["redis_ttl"] == 86400
        assert result["skip_dirs"] == [".venv", "node_modules"]
        assert result["frameworks"] == ["pytorch", "numpy"]
        assert result["auto_test_after_edit"] is False
        assert result["scope_guard"] is False
        assert result["external_validation"]["enabled"] is True
        assert result["external_validation"]["openrouter_api_key"] == "sk-or-test-key"
        assert result["external_validation"]["model"] == "google/gemini-3.1-flash-lite-preview"
        assert result["external_validation"]["validate_plans"] is False
        assert result["external_validation"]["audit_completed_tasks"] is True
        assert result["external_validation"]["require_approval_on_issues"] is False


def test_partial_settings_merged_with_defaults():
    """Only some keys overridden, rest fall back to defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "elephant-coder.local.md"
        settings_file.write_text(
            "---\n"
            "max_memories: 1234\n"
            "frameworks:\n"
            "  - grilly\n"
            "---\n"
            "# Notes\n",
            encoding="utf-8",
        )

        result = load_settings(tmpdir)

        # Overridden values
        assert result["max_memories"] == 1234
        assert result["frameworks"] == ["grilly"]

        # Untouched defaults
        assert result["relevance_threshold"] == DEFAULT_SETTINGS["relevance_threshold"]
        assert result["redis_url"] == DEFAULT_SETTINGS["redis_url"]
        assert result["redis_ttl"] == DEFAULT_SETTINGS["redis_ttl"]
        assert result["skip_dirs"] == DEFAULT_SETTINGS["skip_dirs"]
        assert result["auto_test_after_edit"] == DEFAULT_SETTINGS["auto_test_after_edit"]
        assert result["scope_guard"] == DEFAULT_SETTINGS["scope_guard"]

        # Nested external_validation should still have all defaults intact
        ev = result["external_validation"]
        assert ev["enabled"] == DEFAULT_SETTINGS["external_validation"]["enabled"]
        assert ev["model"] == DEFAULT_SETTINGS["external_validation"]["model"]


def test_save_settings_creates_file():
    """save_settings writes YAML frontmatter and returns the file path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = dict(DEFAULT_SETTINGS)
        settings["max_memories"] = 999

        path = save_settings(tmpdir, settings)

        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8")
        assert "---" in content
        assert "max_memories: 999" in content


def test_save_settings_preserves_body():
    """save_settings preserves existing markdown body after frontmatter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "elephant-coder.local.md"
        settings_file.write_text(
            "---\n"
            "max_memories: 100\n"
            "---\n"
            "# My existing notes\n"
            "Keep this content!\n",
            encoding="utf-8",
        )

        settings = dict(DEFAULT_SETTINGS)
        settings["max_memories"] = 200

        save_settings(tmpdir, settings)

        content = settings_file.read_text(encoding="utf-8")
        assert "max_memories: 200" in content
        assert "# My existing notes" in content
        assert "Keep this content!" in content


def test_openrouter_env_var_fallback(monkeypatch):
    """OPENROUTER_API_KEY env var is used as fallback for api key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("OPENROUTER_API_KEY", "env-key-value")
        result = load_settings(tmpdir)
        assert result["external_validation"]["openrouter_api_key"] == "env-key-value"


def test_openrouter_file_takes_precedence_over_env(monkeypatch):
    """File-specified api key takes precedence over the env var."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("OPENROUTER_API_KEY", "env-key-value")
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "elephant-coder.local.md"
        settings_file.write_text(
            "---\n"
            "external_validation:\n"
            "  openrouter_api_key: file-key-value\n"
            "---\n",
            encoding="utf-8",
        )
        result = load_settings(tmpdir)
        assert result["external_validation"]["openrouter_api_key"] == "file-key-value"
