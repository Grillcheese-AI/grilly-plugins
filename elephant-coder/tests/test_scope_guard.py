import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import os
from scope_guard import check_file_size, check_duplicate_file, generate_change_request


# --- check_file_size ---

def test_file_under_limit():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("\n" * 100)
        path = f.name
    try:
        result = check_file_size(path, max_lines=1000)
        assert result["ok"] is True
        assert result["lines"] == 100
        assert result["max"] == 1000
        assert "warning" not in result or result["warning"] is False
    finally:
        os.unlink(path)


def test_file_at_90_percent_of_limit():
    """90% of 1000 = 900 lines — should be ok=True with warning=True."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("\n" * 900)
        path = f.name
    try:
        result = check_file_size(path, max_lines=1000)
        assert result["ok"] is True
        assert result["lines"] == 900
        assert result["warning"] is True
        assert "message" in result
    finally:
        os.unlink(path)


def test_file_over_limit():
    """1001 lines — should be ok=False with a message."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("\n" * 1001)
        path = f.name
    try:
        result = check_file_size(path, max_lines=1000)
        assert result["ok"] is False
        assert result["lines"] == 1001
        assert "message" in result
    finally:
        os.unlink(path)


def test_file_exactly_at_limit():
    """Exactly 1000 lines — should be ok=True (not exceeded), but warning=True (at 100% ≥ 90%)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("\n" * 1000)
        path = f.name
    try:
        result = check_file_size(path, max_lines=1000)
        assert result["ok"] is True
        assert result["warning"] is True
    finally:
        os.unlink(path)


# --- check_duplicate_file ---

def test_no_duplicate():
    with tempfile.TemporaryDirectory() as project_root:
        new_file = "totally_unique_xyz_abc.py"
        result = check_duplicate_file(new_file, project_root)
        assert result["is_duplicate"] is False
        assert result.get("existing_path") is None or result["existing_path"] == ""


def test_duplicate_detected():
    with tempfile.TemporaryDirectory() as project_root:
        # Create an existing file with the same name somewhere inside project_root
        subdir = Path(project_root) / "subpackage"
        subdir.mkdir()
        existing = subdir / "my_module.py"
        existing.write_text("# existing module\n")

        result = check_duplicate_file("my_module.py", project_root)
        assert result["is_duplicate"] is True
        assert "my_module.py" in result["existing_path"]
        assert "message" in result


def test_duplicate_skips_excluded_dirs():
    """Files inside .venv / __pycache__ / node_modules / .git / dist / build / .eggs should be ignored."""
    with tempfile.TemporaryDirectory() as project_root:
        for skip_dir in [".venv", "node_modules", "__pycache__", ".git", "dist", "build", ".eggs"]:
            d = Path(project_root) / skip_dir
            d.mkdir()
            (d / "my_special_module.py").write_text("# noise\n")

        result = check_duplicate_file("my_special_module.py", project_root)
        assert result["is_duplicate"] is False


# --- generate_change_request ---

def test_change_request_low_risk():
    result = generate_change_request(
        what="Add scope_guard module",
        why="Enforce code quality limits",
        current_task="Plan C Task 2",
        files_affected=["scope_guard.py"],
        dependents=0,
    )
    assert "id" in result
    assert isinstance(result["id"], str) and len(result["id"]) > 0
    assert result["risk"] == "LOW"
    assert "text" in result
    assert "scope_guard.py" in result["text"]


def test_change_request_medium_risk():
    result = generate_change_request(
        what="Refactor indexer",
        why="Performance improvement",
        current_task="Task 5",
        files_affected=["indexer.py", "server.py"],
        dependents=5,
    )
    assert result["risk"] == "MEDIUM"


def test_change_request_high_risk():
    result = generate_change_request(
        what="Rewrite memory store",
        why="Switch to Redis backend",
        current_task="Task 10",
        files_affected=["memory_store.py"],
        dependents=11,
    )
    assert result["risk"] == "HIGH"


def test_change_request_text_is_markdown():
    result = generate_change_request(
        what="Add feature X",
        why="Because Y",
        current_task="Task 1",
        files_affected=["a.py", "b.py"],
    )
    text = result["text"]
    # Should contain markdown headings or bold markers
    assert "#" in text or "**" in text


def test_change_request_default_dependents():
    """dependents defaults to 0, so risk should be LOW."""
    result = generate_change_request(
        what="Tiny fix",
        why="Bug",
        current_task="Task 0",
        files_affected=["utils.py"],
    )
    assert result["risk"] == "LOW"
