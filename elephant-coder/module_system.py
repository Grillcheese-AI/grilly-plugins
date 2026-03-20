"""
Elephant module system — Claude creates its own tools.

Allows Claude to dynamically create, manage, and execute Python modules
that extend elephant-coder's capabilities. Modules are self-contained
units of functionality that Claude writes to help the user better.

Module types:
- tool: callable function exposed via run_module()
- analyzer: runs analysis on code/files, returns insights
- workflow: multi-step automated process
- checker: validation/quality check that can run automatically
- generator: creates files, boilerplate, or scaffolding

Module storage:
- Global: ~/.elephant-coder/modules/  (shared across projects)
- Project: .claude/elephant-modules/  (project-specific)

Each module has:
- module.py: the code (must define run(args: dict) -> str)
- manifest.json: metadata, config, activation status
"""

import importlib.util
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger("elephant-coder.modules")

MODULE_TYPES = {"tool", "analyzer", "workflow", "checker", "generator", "mcp_server"}

# Template for new modules
MODULE_TEMPLATE = '''"""
Elephant module: {name}

{description}

Type: {module_type}
Author: claude
"""


def run(args: dict) -> str:
    """Entry point called by elephant-coder.

    Args:
        args: dict with module-specific parameters

    Returns:
        Result string to display
    """
{code}
'''

MCP_SERVER_TEMPLATE = '''"""
Elephant MCP sub-server: {name}

{description}

This is a standalone MCP server created by Claude within elephant-coder.
It has its own tools, can define its own skills and hooks.
Managed by the elephant-coder module system.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{name}")

{code}

if __name__ == "__main__":
    mcp.run(transport="stdio")
'''

SKILL_TEMPLATE = '''---
name: {name}
description: {description}
---

{content}
'''

HOOK_TEMPLATE = '''#!/usr/bin/env python3
"""{name} hook — {description}"""
import json
import sys

{code}
'''

MANIFEST_TEMPLATE = {
    "name": "",
    "description": "",
    "version": "1.0.0",
    "author": "claude",
    "scope": "project",
    "type": "tool",
    "triggers": [],
    "dependencies": [],
    "active": True,
    "created": 0.0,
    "last_used": 0.0,
    "use_count": 0,
    "tags": [],
}


@dataclass
class ModuleInfo:
    """Metadata about an installed module."""
    name: str
    description: str
    version: str
    author: str
    scope: str          # "global" or "project"
    module_type: str    # tool, analyzer, workflow, checker, generator
    triggers: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    active: bool = True
    created: float = 0.0
    last_used: float = 0.0
    use_count: int = 0
    tags: list[str] = field(default_factory=list)
    path: str = ""      # resolved filesystem path


def _global_modules_dir() -> Path:
    """Global modules directory shared across all projects."""
    d = Path.home() / ".elephant-coder" / "modules"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _project_modules_dir(project_root: str) -> Path:
    """Project-specific modules directory."""
    d = Path(project_root) / ".claude" / "elephant-modules"
    d.mkdir(parents=True, exist_ok=True)
    return d


class ModuleSystem:
    """Manages elephant modules — creation, discovery, execution."""

    def __init__(self, project_root: str):
        self._project_root = project_root
        self._global_dir = _global_modules_dir()
        self._project_dir = _project_modules_dir(project_root)

    def create_module(
        self,
        name: str,
        description: str,
        code: str,
        module_type: str = "tool",
        scope: str = "project",
        triggers: list[str] | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> ModuleInfo:
        """Create a new elephant module.

        Claude writes the code, which must define a run(args: dict) -> str function.
        The module is saved to disk and registered in the manifest.
        """
        if module_type not in MODULE_TYPES:
            raise ValueError(f"Invalid type '{module_type}'. Must be one of: {MODULE_TYPES}")

        name = name.replace(" ", "_").lower()
        base_dir = self._global_dir if scope == "global" else self._project_dir
        module_dir = base_dir / name
        module_dir.mkdir(parents=True, exist_ok=True)

        # Write module code
        # If code doesn't define run(), wrap it
        if "def run(" not in code:
            indented = "\n".join(f"    {line}" for line in code.strip().split("\n"))
            full_code = MODULE_TEMPLATE.format(
                name=name, description=description,
                module_type=module_type, code=indented,
            )
        else:
            full_code = f'"""\nElephant module: {name}\n\n{description}\n\nType: {module_type}\nAuthor: claude\n"""\n\n{code}'

        module_file = module_dir / "module.py"
        module_file.write_text(full_code, encoding="utf-8")

        # Write manifest
        now = time.time()
        manifest = {
            **MANIFEST_TEMPLATE,
            "name": name,
            "description": description,
            "scope": scope,
            "type": module_type,
            "triggers": triggers or [],
            "dependencies": dependencies or [],
            "created": now,
            "tags": tags or [],
        }
        manifest_file = module_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        logger.info("Created module '%s' at %s", name, module_dir)

        return ModuleInfo(
            name=name, description=description, version="1.0.0",
            author="claude", scope=scope, module_type=module_type,
            triggers=triggers or [], dependencies=dependencies or [],
            active=True, created=now, tags=tags or [],
            path=str(module_dir),
        )

    def list_modules(self, scope: str | None = None,
                     module_type: str | None = None,
                     active_only: bool = False) -> list[ModuleInfo]:
        """List all installed modules."""
        modules = []

        dirs_to_scan = []
        if scope is None or scope == "global":
            dirs_to_scan.append(("global", self._global_dir))
        if scope is None or scope == "project":
            dirs_to_scan.append(("project", self._project_dir))

        for dir_scope, base_dir in dirs_to_scan:
            if not base_dir.exists():
                continue
            for manifest_path in base_dir.glob("*/manifest.json"):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    info = ModuleInfo(
                        name=manifest["name"],
                        description=manifest.get("description", ""),
                        version=manifest.get("version", "1.0.0"),
                        author=manifest.get("author", "claude"),
                        scope=dir_scope,
                        module_type=manifest.get("type", "tool"),
                        triggers=manifest.get("triggers", []),
                        dependencies=manifest.get("dependencies", []),
                        active=manifest.get("active", True),
                        created=manifest.get("created", 0.0),
                        last_used=manifest.get("last_used", 0.0),
                        use_count=manifest.get("use_count", 0),
                        tags=manifest.get("tags", []),
                        path=str(manifest_path.parent),
                    )
                    if module_type and info.module_type != module_type:
                        continue
                    if active_only and not info.active:
                        continue
                    modules.append(info)
                except Exception as exc:
                    logger.warning("Failed to load module manifest %s: %s", manifest_path, exc)

        modules.sort(key=lambda m: (m.scope, m.name))
        return modules

    def get_module(self, name: str) -> ModuleInfo | None:
        """Get a specific module by name."""
        for mod in self.list_modules():
            if mod.name == name:
                return mod
        return None

    def run_module(self, name: str, args: dict | None = None) -> str:
        """Execute a module's run() function in a subprocess.

        Runs in a separate process for safety. The module receives args as JSON
        on stdin and returns its result on stdout.
        """
        mod = self.get_module(name)
        if mod is None:
            return f"Module '{name}' not found."
        if not mod.active:
            return f"Module '{name}' is deactivated."

        module_file = Path(mod.path) / "module.py"
        if not module_file.exists():
            return f"Module file not found: {module_file}"

        # Run in subprocess for isolation
        runner_code = f"""
import json, sys
sys.path.insert(0, {repr(str(Path(mod.path)))})
sys.path.insert(0, {repr(self._project_root)})
from module import run
args = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {{}}
result = run(args)
print(result)
"""
        try:
            proc = subprocess.run(
                [sys.executable, "-c", runner_code],
                input=json.dumps(args or {}),
                capture_output=True, text=True, timeout=30,
                cwd=self._project_root,
            )
            # Update usage stats
            self._update_stats(mod)

            if proc.returncode != 0:
                return f"Module '{name}' failed:\n{proc.stderr.strip()}"
            return proc.stdout.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Module '{name}' timed out (30s limit)."
        except Exception as exc:
            return f"Module '{name}' error: {exc}"

    def update_module(self, name: str, code: str | None = None,
                      description: str | None = None,
                      active: bool | None = None,
                      triggers: list[str] | None = None) -> str:
        """Update an existing module's code or settings."""
        mod = self.get_module(name)
        if mod is None:
            return f"Module '{name}' not found."

        manifest_path = Path(mod.path) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if code is not None:
            module_file = Path(mod.path) / "module.py"
            if "def run(" not in code:
                indented = "\n".join(f"    {line}" for line in code.strip().split("\n"))
                full_code = MODULE_TEMPLATE.format(
                    name=name, description=manifest["description"],
                    module_type=manifest["type"], code=indented,
                )
            else:
                full_code = code
            module_file.write_text(full_code, encoding="utf-8")
            # Bump version
            parts = manifest["version"].split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            manifest["version"] = ".".join(parts)

        if description is not None:
            manifest["description"] = description
        if active is not None:
            manifest["active"] = active
        if triggers is not None:
            manifest["triggers"] = triggers

        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return f"Module '{name}' updated (v{manifest['version']})."

    def delete_module(self, name: str) -> str:
        """Delete a module and all its files."""
        mod = self.get_module(name)
        if mod is None:
            return f"Module '{name}' not found."

        import shutil
        shutil.rmtree(mod.path)
        return f"Module '{name}' deleted."

    def get_triggered_modules(self, event: str) -> list[ModuleInfo]:
        """Get modules triggered by a specific event (e.g. 'PostToolUse:Edit')."""
        return [
            m for m in self.list_modules(active_only=True)
            if event in m.triggers
        ]

    def get_module_code(self, name: str) -> str:
        """Read a module's source code."""
        mod = self.get_module(name)
        if mod is None:
            return f"Module '{name}' not found."
        module_file = Path(mod.path) / "module.py"
        if not module_file.exists():
            return f"Module file not found."
        return module_file.read_text(encoding="utf-8")

    def suggest_modules(self) -> list[dict]:
        """Suggest modules Claude could create based on project context.

        Analyzes:
        - User profile recurrent requests (auto-eligible patterns)
        - Project type and framework
        - Existing modules (avoid duplicates)
        """
        suggestions = []
        existing = {m.name for m in self.list_modules()}

        # Check for user profile recurrent requests
        try:
            from user_profile import UserProfile
            up = UserProfile()
            requests = up.get_recurrent_requests(min_frequency=3)
            for req in requests:
                mod_name = req["pattern"].replace(" ", "_").lower()[:30]
                if mod_name not in existing:
                    suggestions.append({
                        "name": mod_name,
                        "reason": f"User requests this frequently ({req['frequency']}x): {req['pattern']}",
                        "type": "workflow",
                        "based_on": req["examples"],
                    })
            up.close()
        except Exception:
            pass

        return suggestions

    def create_mcp_module(
        self,
        name: str,
        description: str,
        tools_code: str,
        skills: list[dict] | None = None,
        hooks: list[dict] | None = None,
        scope: str = "project",
        tags: list[str] | None = None,
    ) -> ModuleInfo:
        """Create a full MCP sub-server module with its own tools, skills, and hooks.

        This is the most powerful module type — Claude creates an entire MCP server
        that elephant-coder manages. The server gets its own tools, can define
        skills (slash commands), and register hooks.

        Args:
            name: Module name (used as MCP server name)
            description: What this server does
            tools_code: Python code defining @mcp.tool() functions (mcp object is pre-defined)
            skills: List of {"name": str, "description": str, "content": str} for slash commands
            hooks: List of {"event": str, "name": str, "description": str, "code": str} for hooks
            scope: "global" or "project"
            tags: Classification tags
        """
        name = name.replace(" ", "_").lower()
        base_dir = self._global_dir if scope == "global" else self._project_dir
        module_dir = base_dir / name
        module_dir.mkdir(parents=True, exist_ok=True)

        # Write MCP server
        server_code = MCP_SERVER_TEMPLATE.format(
            name=name, description=description, code=tools_code,
        )
        (module_dir / "server.py").write_text(server_code, encoding="utf-8")

        # Write .mcp.json for Claude Code registration
        mcp_config = {
            "mcpServers": {
                f"ec-{name}": {
                    "command": sys.executable,
                    "args": ["-u", str(module_dir / "server.py")],
                }
            }
        }
        (module_dir / ".mcp.json").write_text(
            json.dumps(mcp_config, indent=2), encoding="utf-8"
        )

        # Write skills
        if skills:
            skills_dir = module_dir / "skills"
            skills_dir.mkdir(exist_ok=True)
            for skill in skills:
                skill_dir = skills_dir / skill["name"]
                skill_dir.mkdir(exist_ok=True)
                skill_content = SKILL_TEMPLATE.format(
                    name=skill["name"],
                    description=skill.get("description", ""),
                    content=skill.get("content", ""),
                )
                (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        # Write hooks
        if hooks:
            hooks_dir = module_dir / "hooks"
            hooks_dir.mkdir(exist_ok=True)
            hooks_config = {"description": f"{name} module hooks", "hooks": {}}
            for hook in hooks:
                event = hook["event"]
                hook_name = hook["name"].replace(" ", "_").lower()
                hook_file = hooks_dir / f"{hook_name}.py"
                hook_code = HOOK_TEMPLATE.format(
                    name=hook_name,
                    description=hook.get("description", ""),
                    code=hook.get("code", "print(json.dumps({'additionalContext': ''}))\nsys.exit(0)"),
                )
                hook_file.write_text(hook_code, encoding="utf-8")

                if event not in hooks_config["hooks"]:
                    hooks_config["hooks"][event] = []
                hooks_config["hooks"][event].append({
                    "matcher": hook.get("matcher", ""),
                    "hooks": [{
                        "type": "command",
                        "command": f"python {hook_file}",
                        "timeout": hook.get("timeout", 5),
                    }]
                })
            (hooks_dir / "hooks.json").write_text(
                json.dumps(hooks_config, indent=2), encoding="utf-8"
            )

        # Also write a run() entry point for compatibility with run_module()
        run_wrapper = f'''"""Run wrapper for MCP module {name}."""
import subprocess, sys, json

def run(args: dict) -> str:
    """Start the MCP server or execute a tool directly."""
    if args.get("start_server"):
        proc = subprocess.Popen(
            [sys.executable, "-u", "server.py"],
            cwd={repr(str(module_dir))},
        )
        return f"MCP server started (PID {{proc.pid}})"
    return "Use start_server=true to launch, or register via .mcp.json"
'''
        (module_dir / "module.py").write_text(run_wrapper, encoding="utf-8")

        # Write manifest
        now = time.time()
        manifest = {
            **MANIFEST_TEMPLATE,
            "name": name,
            "description": description,
            "scope": scope,
            "type": "mcp_server",
            "triggers": [],
            "dependencies": [],
            "created": now,
            "tags": tags or [],
            "mcp_config": mcp_config,
            "has_skills": bool(skills),
            "has_hooks": bool(hooks),
            "skill_count": len(skills) if skills else 0,
            "hook_count": len(hooks) if hooks else 0,
        }
        (module_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        logger.info("Created MCP module '%s' at %s (skills=%d, hooks=%d)",
                     name, module_dir, len(skills or []), len(hooks or []))

        return ModuleInfo(
            name=name, description=description, version="1.0.0",
            author="claude", scope=scope, module_type="mcp_server",
            active=True, created=now, tags=tags or [],
            path=str(module_dir),
        )

    def _update_stats(self, mod: ModuleInfo) -> None:
        """Update last_used and use_count in manifest."""
        try:
            manifest_path = Path(mod.path) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["last_used"] = time.time()
            manifest["use_count"] = manifest.get("use_count", 0) + 1
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except Exception:
            pass
