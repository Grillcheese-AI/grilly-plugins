import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_index_all_exists():
    """index_all should be importable from server module."""
    from server import index_all
    assert callable(index_all)


def test_load_settings_exists():
    """_load_settings helper should be importable."""
    from server import _load_settings
    assert callable(_load_settings)


def test_update_settings_exists():
    """update_settings should be importable from server module."""
    from server import update_settings
    assert callable(update_settings)


def test_project_overview_exists():
    from server import project_overview
    assert callable(project_overview)

def test_what_broke_exists():
    from server import what_broke
    assert callable(what_broke)

def test_get_tasks_exists():
    from server import get_tasks
    assert callable(get_tasks)

def test_add_task_exists():
    from server import add_task
    assert callable(add_task)
