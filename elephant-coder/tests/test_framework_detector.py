import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from framework_detector import detect_frameworks, is_grilly_project, generate_api_map


def test_detect_grilly_in_requirements():
    with tempfile.TemporaryDirectory() as tmpdir:
        req = Path(tmpdir) / "requirements.txt"
        req.write_text("numpy>=1.24\ngrilly>=0.1.0\nredis>=5.0\n")
        frameworks = detect_frameworks(tmpdir)
        assert any(f["name"] == "grilly" for f in frameworks)


def test_detect_grilly_in_pyproject():
    with tempfile.TemporaryDirectory() as tmpdir:
        pyproj = Path(tmpdir) / "pyproject.toml"
        pyproj.write_text('[project]\nname = "my-app"\ndependencies = ["grilly>=0.1.0", "numpy"]\n')
        frameworks = detect_frameworks(tmpdir)
        assert any(f["name"] == "grilly" for f in frameworks)


def test_is_grilly_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "backend").mkdir()
        (Path(tmpdir) / "backend" / "compute.py").write_text("class VulkanCompute: pass")
        (Path(tmpdir) / "shaders").mkdir()
        (Path(tmpdir) / "shaders" / "test.glsl").write_text("void main() {}")
        assert is_grilly_project(tmpdir) is True


def test_not_grilly_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "main.py").write_text("print('hello')")
        assert is_grilly_project(tmpdir) is False


def test_generate_api_map():
    api_map = generate_api_map()
    assert "torch.nn.Linear" in api_map
    assert api_map["torch.nn.Linear"] == "grilly.nn.Linear"
    assert "torch.optim.Adam" in api_map


def test_detect_grilly_source_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "backend").mkdir()
        (Path(tmpdir) / "backend" / "compute.py").write_text("class VulkanCompute: pass")
        (Path(tmpdir) / "shaders").mkdir()
        (Path(tmpdir) / "shaders" / "test.glsl").write_text("void main() {}")
        frameworks = detect_frameworks(tmpdir)
        assert any(f["name"] == "grilly" and f["detected_as"] == "source_project" for f in frameworks)
