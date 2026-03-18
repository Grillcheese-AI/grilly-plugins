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
