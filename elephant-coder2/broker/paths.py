"""Path resolution for elephant-coder2 state."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def ec2_home() -> Path:
    """Root dir for all v2 state. Override with EC2_HOME env var."""
    env = os.environ.get("EC2_HOME")
    if env:
        p = Path(env)
    else:
        p = Path.home() / ".elephant-coder2"
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_hash(project_path: str) -> str:
    """Stable 12-char hash of a project path."""
    norm = os.path.normpath(os.path.abspath(project_path))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def project_dir(project_path: str) -> Path:
    """Per-project state dir, created if missing."""
    d = ec2_home() / "projects" / project_hash(project_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def global_dir() -> Path:
    """Cross-project global state."""
    d = ec2_home() / "global"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_dir() -> Path:
    """GGUF model cache."""
    d = ec2_home() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def broker_port_file() -> Path:
    return ec2_home() / "broker.port"


def broker_pid_file() -> Path:
    return ec2_home() / "broker.pid"
