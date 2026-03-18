"""
scope_guard.py — Enforces code quality rules for elephant-coder.

Functions:
    check_file_size(file_path, max_lines=1000) -> dict
    check_duplicate_file(new_file_path, project_root) -> dict
    generate_change_request(what, why, current_task, files_affected, dependents=0) -> dict
"""

from __future__ import annotations

import uuid
from pathlib import Path

# Directories to skip when scanning for duplicates
_SKIP_DIRS = frozenset(
    [".venv", "node_modules", "__pycache__", ".git", "dist", "build", ".eggs"]
)


def check_file_size(file_path: str, max_lines: int = 1000) -> dict:
    """Check whether a file exceeds the allowed line-count limit.

    Returns a dict with:
        ok      (bool)  — True if line count <= max_lines
        lines   (int)   — actual line count
        max     (int)   — the limit that was checked against
        warning (bool)  — present and True when lines >= 90% of max (even if ok)
        message (str)   — present when warning or not ok
    """
    path = Path(file_path)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = sum(1 for _ in fh)

    threshold = max_lines * 0.9
    result: dict = {"ok": lines <= max_lines, "lines": lines, "max": max_lines}

    if lines > max_lines:
        result["warning"] = True
        result["message"] = (
            f"File '{path.name}' has {lines} lines, which exceeds the {max_lines}-line limit."
        )
    elif lines >= threshold:
        result["warning"] = True
        result["message"] = (
            f"File '{path.name}' has {lines} lines "
            f"({lines / max_lines * 100:.0f}% of the {max_lines}-line limit). "
            "Consider splitting it soon."
        )

    return result


def check_duplicate_file(new_file_path: str, project_root: str) -> dict:
    """Scan *project_root* for an existing file whose name matches *new_file_path*.

    Skips directories listed in _SKIP_DIRS.

    Returns a dict with:
        is_duplicate  (bool)
        existing_path (str)  — populated when is_duplicate is True, otherwise ""
        message       (str)  — populated when is_duplicate is True
    """
    target_name = Path(new_file_path).name
    root = Path(project_root)

    for candidate in _walk_project(root):
        if candidate.name == target_name:
            existing = str(candidate)
            return {
                "is_duplicate": True,
                "existing_path": existing,
                "message": (
                    f"A file named '{target_name}' already exists at '{existing}'. "
                    "Consider reusing or renaming it instead of creating a duplicate."
                ),
            }

    return {"is_duplicate": False, "existing_path": ""}


def _walk_project(root: Path):
    """Yield all file paths under *root*, skipping excluded directories."""
    for item in root.iterdir():
        if item.is_dir():
            if item.name in _SKIP_DIRS:
                continue
            yield from _walk_project(item)
        else:
            yield item


def generate_change_request(
    what: str,
    why: str,
    current_task: str,
    files_affected: list[str],
    dependents: int = 0,
) -> dict:
    """Generate a structured change-request record.

    Risk is determined by *dependents*:
        > 10  → HIGH
        > 3   → MEDIUM
        else  → LOW

    Returns a dict with:
        id    (str)  — unique identifier (UUID4 short form)
        risk  (str)  — HIGH / MEDIUM / LOW
        text  (str)  — formatted markdown change-request document
    """
    if dependents > 10:
        risk = "HIGH"
    elif dependents > 3:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    cr_id = uuid.uuid4().hex[:8].upper()
    files_list = "\n".join(f"- `{f}`" for f in files_affected)

    text = f"""\
# Change Request {cr_id}

**Task:** {current_task}
**Risk:** {risk}
**Dependents:** {dependents}

## What
{what}

## Why
{why}

## Files Affected
{files_list}
"""

    return {"id": cr_id, "risk": risk, "text": text}
