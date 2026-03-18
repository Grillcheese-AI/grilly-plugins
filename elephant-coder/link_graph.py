"""
Import/include resolution for the file link graph.
"""

import ast
import logging
import re

logger = logging.getLogger("elephant-coder.link_graph")


def resolve_python_imports(source: str) -> list[str]:
    """Extract import module names from Python source code."""
    imports = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _fallback_python_imports(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "." * (node.level or 0)
            imports.append(f"{prefix}{module}" if prefix else module)
    return imports


def _fallback_python_imports(source: str) -> list[str]:
    imports = []
    for m in re.finditer(r"^\s*import\s+([\w.]+)", source, re.MULTILINE):
        imports.append(m.group(1))
    for m in re.finditer(r"^\s*from\s+([\w.]+)\s+import", source, re.MULTILINE):
        imports.append(m.group(1))
    return imports


_CPP_INCLUDE_PATTERN = re.compile(r'^\s*#include\s+[<"]([^>"]+)[>"]', re.MULTILINE)


def resolve_cpp_includes(source: str) -> list[str]:
    return [m.group(1) for m in _CPP_INCLUDE_PATTERN.finditer(source)]


_SHADER_LOAD_PATTERN = re.compile(
    r'(?:load_shader|create_pipeline|compile_shader|_load_shader|_compile_shader)\s*\(\s*["\'](\w+)["\']')


def detect_shader_dispatches(source: str) -> list[str]:
    return [m.group(1) for m in _SHADER_LOAD_PATTERN.finditer(source)]


def resolve_module_to_path(module_name: str, project_root: str, source_file: str) -> str | None:
    """Try to resolve a Python module name to a file path within the project."""
    from pathlib import Path
    root = Path(project_root)
    if module_name.startswith("."):
        source_dir = Path(source_file).parent
        dots = len(module_name) - len(module_name.lstrip("."))
        rel_module = module_name.lstrip(".")
        base = source_dir
        for _ in range(dots - 1):
            base = base.parent
        parts = rel_module.split(".") if rel_module else []
        candidate = base / "/".join(parts)
    else:
        parts = module_name.split(".")
        candidate = root / "/".join(parts)
    for suffix in [".py", "/__init__.py"]:
        path = Path(str(candidate) + suffix)
        if path.exists():
            return str(path.resolve())
    return None
