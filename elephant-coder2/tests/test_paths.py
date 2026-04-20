import os
from pathlib import Path
from broker.paths import ec2_home, project_hash, project_dir, global_dir, model_dir


def test_ec2_home_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    assert ec2_home() == tmp_path


def test_ec2_home_default_is_dot_ec2(monkeypatch):
    monkeypatch.delenv("EC2_HOME", raising=False)
    assert ec2_home().name == ".elephant-coder2"


def test_project_hash_stable():
    h1 = project_hash("/some/project/path")
    h2 = project_hash("/some/project/path")
    assert h1 == h2
    assert len(h1) == 12


def test_project_hash_differs_by_path():
    assert project_hash("/a") != project_hash("/b")


def test_project_dir_creates(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    pdir = project_dir("/some/proj")
    assert pdir.exists()
    assert pdir.parent.name == "projects"


def test_global_and_model_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    assert global_dir().exists()
    assert model_dir().exists()
