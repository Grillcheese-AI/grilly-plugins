"""
Framework detection for elephant-coder.

Auto-detects installed frameworks (e.g., grilly) in the current project
and generates API maps for global knowledge export.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger("elephant-coder.framework_detector")

_KNOWN_FRAMEWORKS = {
    "grilly": {
        "pip_name": "grilly",
        "project_markers": ["backend/compute.py", "shaders/"],
        "github": "Grillcheese-AI/grilly",
    },
}


def detect_frameworks(project_root: str) -> list[dict]:
    root = Path(project_root)
    found = []
    for name, info in _KNOWN_FRAMEWORKS.items():
        if _is_framework_project(root, info["project_markers"]):
            found.append({"name": name, "detected_as": "source_project",
                         "github": info.get("github"), "repo_path": str(root)})
    deps = _read_dependencies(root)
    for name, info in _KNOWN_FRAMEWORKS.items():
        if info["pip_name"] in deps and not any(f["name"] == name for f in found):
            found.append({"name": name, "detected_as": "dependency",
                         "github": info.get("github"), "repo_path": "auto"})
    return found


def is_grilly_project(project_root: str) -> bool:
    root = Path(project_root)
    return (root / "backend" / "compute.py").exists() and (root / "shaders").is_dir()


def _is_framework_project(root: Path, markers: list[str]) -> bool:
    for marker in markers:
        path = root / marker
        if not (path.exists() or path.is_dir()):
            return False
    return True


def _read_dependencies(root: Path) -> set[str]:
    deps: set[str] = set()
    req_file = root / "requirements.txt"
    if req_file.exists():
        try:
            for line in req_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    name = re.split(r"[>=<!\[]", line)[0].strip()
                    if name:
                        deps.add(name.lower())
        except OSError:
            pass
    pyproj = root / "pyproject.toml"
    if pyproj.exists():
        try:
            text = pyproj.read_text()
            for m in re.finditer(r'"([\w][\w.-]*?)(?:[>=<!\[]|")', text):
                deps.add(m.group(1).lower())
        except OSError:
            pass
    return deps


def generate_api_map() -> dict[str, str]:
    return {
        "torch.nn.Linear": "grilly.nn.Linear",
        "torch.nn.Conv2d": "grilly.nn.Conv2d",
        "torch.nn.Module": "grilly.nn.Module",
        "torch.nn.functional.relu": "grilly.functional.relu",
        "torch.nn.functional.softmax": "grilly.functional.softmax",
        "torch.nn.functional.cross_entropy": "grilly.functional.cross_entropy",
        "torch.optim.Adam": "grilly.optim.Adam",
        "torch.optim.AdamW": "grilly.optim.AdamW",
        "torch.optim.SGD": "grilly.optim.SGD",
        "torch.Tensor": "numpy.ndarray (float32)",
        "torch.device('cuda')": "grilly.Compute()",
        "torch.no_grad()": "# not needed — grilly uses explicit GradientTape",
        "torch.save()": "grilly.utils.save_checkpoint()",
        "torch.load()": "grilly.utils.load_checkpoint()",
    }


def generate_quick_start() -> str:
    return '''import numpy as np
from grilly import Compute
from grilly.nn import Linear, Module
from grilly.optim import Adam

backend = Compute()
model = Linear(784, 10)
optimizer = Adam(model.parameters(), lr=0.001)'''


def generate_differences() -> list[str]:
    return [
        "No CUDA dependency — Vulkan compute shaders on any GPU (AMD, NVIDIA, Intel)",
        "Data is always np.float32 numpy arrays, not torch.Tensor",
        "grilly.Compute() replaces torch.device — single entry point for GPU ops",
        "Shaders are GLSL -> SPIR-V, not CUDA kernels",
        "Explicit GradientTape instead of autograd context managers",
    ]
