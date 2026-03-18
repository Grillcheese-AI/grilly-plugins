import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import os
import pytest
from task_manager import TaskManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmpdir):
    """Return a fresh TaskManager rooted at tmpdir."""
    return TaskManager(tmpdir)


# ---------------------------------------------------------------------------
# Task creation and retrieval
# ---------------------------------------------------------------------------

def test_add_and_get_task():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("Refactor auth module", scope=["auth/", "tests/test_auth.py"], priority="high")
        assert task_id == "T-001"

        task = tm.get_task(task_id)
        assert task is not None
        assert task["id"] == "T-001"
        assert task["description"] == "Refactor auth module"
        assert task["scope"] == ["auth/", "tests/test_auth.py"]
        assert task["priority"] == "high"
        assert task["status"] == "pending"


def test_get_nonexistent_task_returns_none():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        assert tm.get_task("T-999") is None


def test_task_ids_increment():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        id1 = tm.add_task("Task one")
        id2 = tm.add_task("Task two")
        id3 = tm.add_task("Task three")
        assert id1 == "T-001"
        assert id2 == "T-002"
        assert id3 == "T-003"


def test_add_task_default_priority():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("Some task")
        task = tm.get_task(task_id)
        assert task["priority"] == "medium"


def test_add_task_no_scope():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("Scopeless task")
        task = tm.get_task(task_id)
        assert task["scope"] is None or task["scope"] == []


# ---------------------------------------------------------------------------
# Status updates
# ---------------------------------------------------------------------------

def test_update_task_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("A task")
        result = tm.update_task(task_id, status="in_progress")
        assert result is True
        task = tm.get_task(task_id)
        assert task["status"] == "in_progress"


def test_update_task_notes():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("A task")
        result = tm.update_task(task_id, notes="Started refactoring")
        assert result is True
        task = tm.get_task(task_id)
        assert task["notes"] == "Started refactoring"


def test_update_nonexistent_task_returns_false():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        result = tm.update_task("T-999", status="done")
        assert result is False


def test_update_task_status_and_notes_together():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("Combo task")
        tm.update_task(task_id, status="done", notes="All finished")
        task = tm.get_task(task_id)
        assert task["status"] == "done"
        assert task["notes"] == "All finished"


# ---------------------------------------------------------------------------
# Task filtering
# ---------------------------------------------------------------------------

def test_get_all_tasks():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        tm.add_task("Task A")
        tm.add_task("Task B")
        tm.add_task("Task C")
        all_tasks = tm.get_all_tasks()
        assert len(all_tasks) == 3


def test_get_active_tasks():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        id1 = tm.add_task("Task A")
        id2 = tm.add_task("Task B")
        tm.add_task("Task C")
        tm.update_task(id1, status="in_progress")
        tm.update_task(id2, status="in_progress")

        active = tm.get_active_tasks()
        assert len(active) == 2
        active_ids = {t["id"] for t in active}
        assert "T-001" in active_ids
        assert "T-002" in active_ids


def test_get_pending_tasks():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        id1 = tm.add_task("Pending A")
        id2 = tm.add_task("Pending B")
        id3 = tm.add_task("Active C")
        tm.update_task(id3, status="in_progress")

        pending = tm.get_pending_tasks()
        assert len(pending) == 2
        pending_ids = {t["id"] for t in pending}
        assert id1 in pending_ids
        assert id2 in pending_ids
        assert id3 not in pending_ids


# ---------------------------------------------------------------------------
# Scope checking
# ---------------------------------------------------------------------------

def test_is_file_in_active_scope_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("Auth work", scope=["auth/", "tests/test_auth.py"])
        tm.update_task(task_id, status="in_progress")

        assert tm.is_file_in_active_scope("auth/login.py") is True
        assert tm.is_file_in_active_scope("tests/test_auth.py") is True


def test_is_file_in_active_scope_no_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("Auth work", scope=["auth/"])
        tm.update_task(task_id, status="in_progress")

        assert tm.is_file_in_active_scope("utils/helpers.py") is False


def test_is_file_in_active_scope_pending_task_not_counted():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        # Task is pending, not in_progress
        tm.add_task("Auth work", scope=["auth/"])
        # File is in scope of the pending task — should return False
        assert tm.is_file_in_active_scope("auth/login.py") is False


def test_is_file_in_active_scope_no_scope():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        task_id = tm.add_task("No scope task")
        tm.update_task(task_id, status="in_progress")
        # No scope defined — file should not match
        assert tm.is_file_in_active_scope("anything.py") is False


# ---------------------------------------------------------------------------
# Objectives and constraints
# ---------------------------------------------------------------------------

def test_objectives_default_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        assert tm.get_objectives() == []


def test_set_and_get_objectives():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        objectives = ["Improve test coverage", "Reduce latency by 20%"]
        tm.set_objectives(objectives)
        assert tm.get_objectives() == objectives


def test_constraints_default_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        assert tm.get_constraints() == []


def test_set_and_get_constraints():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        constraints = ["No breaking API changes", "Must stay under 100ms p99"]
        tm.set_constraints(constraints)
        assert tm.get_constraints() == constraints


def test_set_objectives_overwrites():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        tm.set_objectives(["Old objective"])
        tm.set_objectives(["New objective A", "New objective B"])
        assert tm.get_objectives() == ["New objective A", "New objective B"]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_persistence_tasks_survive_reload():
    with tempfile.TemporaryDirectory() as tmpdir:
        # First manager instance — add data
        tm1 = _make_manager(tmpdir)
        task_id = tm1.add_task("Persistent task", scope=["src/"], priority="high")
        tm1.update_task(task_id, status="in_progress", notes="Working on it")
        tm1.set_objectives(["Objective A"])
        tm1.set_constraints(["Constraint X"])

        # Second manager instance — reload from same directory
        tm2 = _make_manager(tmpdir)
        task = tm2.get_task(task_id)
        assert task is not None
        assert task["description"] == "Persistent task"
        assert task["status"] == "in_progress"
        assert task["notes"] == "Working on it"
        assert task["priority"] == "high"
        assert task["scope"] == ["src/"]
        assert tm2.get_objectives() == ["Objective A"]
        assert tm2.get_constraints() == ["Constraint X"]


def test_persistence_id_counter_survives_reload():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm1 = _make_manager(tmpdir)
        tm1.add_task("Task 1")
        tm1.add_task("Task 2")

        # Reload — next ID should be T-003
        tm2 = _make_manager(tmpdir)
        new_id = tm2.add_task("Task 3")
        assert new_id == "T-003"


# ---------------------------------------------------------------------------
# Change requests
# ---------------------------------------------------------------------------

def test_add_change_request():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        cr_id = tm.add_change_request(
            description="Switch from SQLite to PostgreSQL",
            reason="Need better concurrency",
            impact="High — requires migration",
            triggered_by="T-001",
        )
        assert cr_id.startswith("CR-")


def test_get_pending_change_requests():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        tm.add_change_request("CR one", "reason A", "low", "T-001")
        tm.add_change_request("CR two", "reason B", "high", "T-002")

        crs = tm.get_pending_change_requests()
        assert len(crs) == 2
        assert all(cr["status"] == "pending" for cr in crs)


def test_change_request_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        cr_id = tm.add_change_request(
            description="Add Redis cache",
            reason="Speed",
            impact="Medium",
            triggered_by="T-001",
        )
        crs = tm.get_pending_change_requests()
        cr = next(c for c in crs if c["id"] == cr_id)
        assert cr["description"] == "Add Redis cache"
        assert cr["reason"] == "Speed"
        assert cr["impact"] == "Medium"
        assert cr["triggered_by"] == "T-001"


# ---------------------------------------------------------------------------
# TODO scanning
# ---------------------------------------------------------------------------

def test_scan_todos_finds_comments():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a Python file with various comment tags
        src_file = Path(tmpdir) / "sample.py"
        src_file.write_text(
            "def foo():\n"
            "    # TODO: fix this later\n"
            "    pass\n"
            "\n"
            "def bar():\n"
            "    # FIXME: broken edge case\n"
            "    x = 1  # HACK: workaround for bug\n"
            "    # XXX: investigate\n"
            "    return x\n"
        )

        tm = _make_manager(tmpdir)
        results = tm.scan_todos(tmpdir)

        assert len(results) == 4
        tags = {r["tag"] for r in results}
        assert "TODO" in tags
        assert "FIXME" in tags
        assert "HACK" in tags
        assert "XXX" in tags

        todo_entry = next(r for r in results if r["tag"] == "TODO")
        assert todo_entry["line"] == 2
        assert "fix this later" in todo_entry["text"]
        assert str(src_file) == todo_entry["file"] or "sample.py" in todo_entry["file"]


def test_scan_todos_empty_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        results = tm.scan_todos(tmpdir)
        assert results == []


def test_scan_todos_multiple_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("# TODO: alpha\n")
        (Path(tmpdir) / "b.py").write_text("# FIXME: beta\n")

        tm = _make_manager(tmpdir)
        results = tm.scan_todos(tmpdir)
        assert len(results) == 2
        files = {r["file"] for r in results}
        assert any("a.py" in f for f in files)
        assert any("b.py" in f for f in files)


def test_scan_todos_non_python_ignored():
    """scan_todos should only scan source-code files (e.g. .py, .js, .ts, .go)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "notes.txt").write_text("TODO: remember this\n")
        (Path(tmpdir) / "code.py").write_text("# TODO: real code todo\n")

        tm = _make_manager(tmpdir)
        results = tm.scan_todos(tmpdir)
        # Only the .py file should be scanned, not .txt
        assert len(results) == 1
        assert "code.py" in results[0]["file"]


# ---------------------------------------------------------------------------
# format_task_list
# ---------------------------------------------------------------------------

def test_format_task_list_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        output = tm.format_task_list()
        assert isinstance(output, str)
        # Should still produce some output (header or "no tasks" message)
        assert len(output) > 0


def test_format_task_list_contains_task_info():
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = _make_manager(tmpdir)
        tm.add_task("Implement login", priority="high")
        output = tm.format_task_list()
        assert "T-001" in output
        assert "Implement login" in output
        assert "high" in output.lower() or "HIGH" in output
