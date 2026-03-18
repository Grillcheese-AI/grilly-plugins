"""
task_manager.py — Persistent task list stored as JSON.

Storage layout (tasks.json):
{
    "objectives": [...],
    "constraints": [...],
    "tasks": { "T-001": {...}, ... },
    "change_requests": { "CR-001": {...}, ... },
    "next_id": 2,
    "next_cr_id": 1
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Source-code extensions we want to scan for TODO comments
_SCANNABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".rb",
    ".swift", ".kt", ".scala", ".sh", ".bash",
}

_TODO_PATTERN = re.compile(
    r"(?:#|//|/\*|<!--)\s*(?P<tag>TODO|FIXME|HACK|XXX)\s*[:\-]?\s*(?P<text>.*)",
    re.IGNORECASE,
)


class TaskManager:
    """Persistent task list backed by a JSON file in *project_dir*."""

    def __init__(self, project_dir: str | Path) -> None:
        self._dir = Path(project_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "tasks.json"
        self._data = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        else:
            data = {}

        # Ensure all required keys are present
        data.setdefault("objectives", [])
        data.setdefault("constraints", [])
        data.setdefault("tasks", {})
        data.setdefault("change_requests", {})
        data.setdefault("next_id", 1)
        data.setdefault("next_cr_id", 1)
        return data

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def add_task(
        self,
        description: str,
        scope: list[str] | None = None,
        priority: str = "medium",
    ) -> str:
        task_id = f"T-{self._data['next_id']:03d}"
        self._data["next_id"] += 1
        self._data["tasks"][task_id] = {
            "id": task_id,
            "description": description,
            "scope": scope if scope is not None else [],
            "priority": priority,
            "status": "pending",
            "notes": "",
        }
        self._save()
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._data["tasks"].get(task_id)

    def update_task(
        self,
        task_id: str,
        status: str | None = None,
        notes: str | None = None,
    ) -> bool:
        task = self._data["tasks"].get(task_id)
        if task is None:
            return False
        if status is not None:
            task["status"] = status
        if notes is not None:
            task["notes"] = notes
        self._save()
        return True

    def get_all_tasks(self) -> list[dict[str, Any]]:
        return list(self._data["tasks"].values())

    def get_active_tasks(self) -> list[dict[str, Any]]:
        return [t for t in self._data["tasks"].values() if t["status"] == "in_progress"]

    def get_pending_tasks(self) -> list[dict[str, Any]]:
        return [t for t in self._data["tasks"].values() if t["status"] == "pending"]

    # ------------------------------------------------------------------
    # Scope checking
    # ------------------------------------------------------------------

    def is_file_in_active_scope(self, file_path: str) -> bool:
        """Return True if *file_path* falls within any active task's scope entries."""
        for task in self.get_active_tasks():
            scope = task.get("scope") or []
            for entry in scope:
                if file_path.startswith(entry) or entry in file_path:
                    return True
        return False

    # ------------------------------------------------------------------
    # Objectives & constraints
    # ------------------------------------------------------------------

    def get_objectives(self) -> list[str]:
        return list(self._data["objectives"])

    def set_objectives(self, objectives: list[str]) -> None:
        self._data["objectives"] = list(objectives)
        self._save()

    def get_constraints(self) -> list[str]:
        return list(self._data["constraints"])

    def set_constraints(self, constraints: list[str]) -> None:
        self._data["constraints"] = list(constraints)
        self._save()

    # ------------------------------------------------------------------
    # Change requests
    # ------------------------------------------------------------------

    def add_change_request(
        self,
        description: str,
        reason: str,
        impact: str,
        triggered_by: str,
    ) -> str:
        cr_id = f"CR-{self._data['next_cr_id']:03d}"
        self._data["next_cr_id"] += 1
        self._data["change_requests"][cr_id] = {
            "id": cr_id,
            "description": description,
            "reason": reason,
            "impact": impact,
            "triggered_by": triggered_by,
            "status": "pending",
        }
        self._save()
        return cr_id

    def get_pending_change_requests(self) -> list[dict[str, Any]]:
        return [
            cr
            for cr in self._data["change_requests"].values()
            if cr["status"] == "pending"
        ]

    # ------------------------------------------------------------------
    # TODO scanning
    # ------------------------------------------------------------------

    def scan_todos(self, directory: str | Path) -> list[dict[str, Any]]:
        """Scan *directory* recursively for TODO/FIXME/HACK/XXX comments.

        Returns a list of dicts with keys: file, line, tag, text.
        Only source-code file extensions are scanned.
        """
        results: list[dict[str, Any]] = []
        root = Path(directory)

        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in _SCANNABLE_EXTENSIONS:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for line_no, line in enumerate(content.splitlines(), start=1):
                match = _TODO_PATTERN.search(line)
                if match:
                    results.append(
                        {
                            "file": str(file_path),
                            "line": line_no,
                            "tag": match.group("tag").upper(),
                            "text": match.group("text").strip(),
                        }
                    )

        return results

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_task_list(self) -> str:
        """Return a human-readable summary of all tasks."""
        lines: list[str] = []
        tasks = self.get_all_tasks()

        objectives = self.get_objectives()
        if objectives:
            lines.append("=== Objectives ===")
            for obj in objectives:
                lines.append(f"  • {obj}")
            lines.append("")

        constraints = self.get_constraints()
        if constraints:
            lines.append("=== Constraints ===")
            for c in constraints:
                lines.append(f"  • {c}")
            lines.append("")

        if not tasks:
            lines.append("=== Tasks ===")
            lines.append("  (no tasks)")
            return "\n".join(lines)

        # Group by status
        groups: dict[str, list[dict]] = {}
        for task in tasks:
            groups.setdefault(task["status"], []).append(task)

        status_order = ["in_progress", "pending", "done", "blocked"]
        status_labels = {
            "in_progress": "In Progress",
            "pending": "Pending",
            "done": "Done",
            "blocked": "Blocked",
        }

        lines.append("=== Tasks ===")
        for status in status_order:
            group = groups.get(status, [])
            if not group:
                continue
            lines.append(f"\n[{status_labels.get(status, status.title())}]")
            for task in group:
                scope_str = ""
                scope = task.get("scope") or []
                if scope:
                    scope_str = f" | scope: {', '.join(scope)}"
                notes_str = f" | {task['notes']}" if task.get("notes") else ""
                lines.append(
                    f"  {task['id']} [{task['priority'].upper()}] {task['description']}"
                    f"{scope_str}{notes_str}"
                )

        # Any statuses not in the known order
        for status, group in groups.items():
            if status not in status_order:
                lines.append(f"\n[{status.title()}]")
                for task in group:
                    lines.append(f"  {task['id']} [{task['priority'].upper()}] {task['description']}")

        pending_crs = self.get_pending_change_requests()
        if pending_crs:
            lines.append("\n=== Pending Change Requests ===")
            for cr in pending_crs:
                lines.append(f"  {cr['id']} {cr['description']} (triggered by: {cr['triggered_by']})")

        return "\n".join(lines)
