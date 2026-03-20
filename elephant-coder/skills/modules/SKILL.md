---
name: modules
description: Create and manage elephant modules — Claude's self-extending tool system. Build custom tools, analyzers, workflows, checkers, generators, and full MCP sub-servers.
---

Elephant modules let Claude create its own tools to help the user better.
When Claude identifies a repeating need or gap in capabilities, it can create
a module to address it — from simple utility functions to full MCP servers
with their own tools, skills, and hooks.

## Usage

- `/ec:modules` — list all modules and show suggestions
- `/ec:modules create` — guided module creation
- `/ec:modules list` — list installed modules with status
- `/ec:modules run <name>` — execute a module
- `/ec:modules delete <name>` — remove a module

## Module Types

| Type | Purpose | Example |
|------|---------|---------|
| `tool` | Callable function | "format JSON", "count lines" |
| `analyzer` | Code/file analysis | "find unused imports", "complexity report" |
| `workflow` | Multi-step automation | "create PR with tests", "deploy staging" |
| `checker` | Validation/quality check | "check API compatibility", "lint config" |
| `generator` | Create files/boilerplate | "scaffold React component", "generate API client" |
| `mcp_server` | Full MCP server with tools, skills, hooks | "project-specific API tools", "custom linter server" |

## When to Create Modules

Claude should proactively create modules when:
1. The user asks for the same thing 3+ times (check recurrent requests)
2. A task requires capabilities elephant-coder doesn't have
3. A project has unique workflows that should be automated
4. The user explicitly asks for a custom tool

## Creating a Simple Module

Call `create_module()`:
```
create_module(
    name="count_todo",
    description="Count TODO comments across the codebase",
    module_type="analyzer",
    scope="project",
    code='''
import os

def run(args: dict) -> str:
    root = args.get("path", ".")
    count = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith((".py", ".ts", ".js")):
                with open(os.path.join(dirpath, f)) as fh:
                    count += sum(1 for line in fh if "TODO" in line)
    return f"Found {count} TODO comments"
'''
)
```

## Creating an MCP Server Module

Call `create_mcp_module()` for a full server with its own tools:
```
create_mcp_module(
    name="project_metrics",
    description="Custom project metrics and health checks",
    tools_code='''
@mcp.tool()
def code_health() -> str:
    """Check overall code health metrics."""
    import subprocess
    result = subprocess.run(["git", "log", "--oneline", "-10"], capture_output=True, text=True)
    return f"Last 10 commits:\\n{result.stdout}"

@mcp.tool()
def dependency_freshness() -> str:
    """Check if dependencies are up to date."""
    # ... implementation
    return "All dependencies current"
''',
    skills=[{
        "name": "health",
        "description": "Run project health check",
        "content": "Run `code_health()` and `dependency_freshness()` and present a summary."
    }],
)
```

## Module Storage

- **Project modules**: `.claude/elephant-modules/<name>/`
- **Global modules**: `~/.elephant-coder/modules/<name>/`

Each module contains:
- `module.py` — the code (run() entry point)
- `manifest.json` — metadata, version, activation status
- For MCP servers: `server.py`, `.mcp.json`, optional `skills/` and `hooks/` dirs

## Module Lifecycle

1. **Create** — Claude writes the code via `create_module()` or `create_mcp_module()`
2. **Test** — Run with `run_module()` to verify it works
3. **Activate** — Active by default, toggle with `update_module(active=True/False)`
4. **Use** — Execute via `run_module()` or triggered by events
5. **Evolve** — Update code with `update_module(code=...)`
6. **Archive** — Deactivate modules no longer needed
7. **Delete** — Remove with `delete_module()`

## Auto-Suggestions

The module system analyzes user profile recurrent requests (3+ times) and
suggests modules Claude could create. Check with `list_modules()` — suggestions
appear when no modules match a pattern.
