# Elephant-Coder Plugin

Persistent codebase memory with multi-language indexing and full-text search.

## Auto-Behavior

- **SessionStart**: Automatically indexes the full project (all file types). Unchanged files are skipped via mtime check.
- **PostToolUse:Edit/Write**: Reminds to re-index edited/new files to keep memories fresh.

## Available Slash Commands

- `/ec:index` — Full project re-index (all file types, parallel)
- `/ec:recall <query>` — Search memories for code, symbols, or concepts
- `/ec:status` — Memory store statistics
- `/ec:graph <symbol>` — Call graph for a symbol
- `/ec:recent [days]` — Recently changed files with indexed symbols
- `/ec:ingest [path]` — Ingest documents from knowledge directories

## MCP Tools (direct use)

- `index_directory(path, patterns, force)` — Index files by glob pattern
- `ingest_knowledge(path, force)` — Ingest documents
- `recall_memories(query, limit, kind)` — Full-text search
- `recall_file_memories(file_path)` — All memories for a file
- `search_symbols(name, kind)` — Direct symbol lookup
- `show_call_graph(symbol, depth)` — Dependency tracing
- `summarize_directory(path)` — Table of contents for a directory
- `recent_changes(days, limit)` — Git-aware recent modifications
- `get_dependencies(file_path)` — Import graph
- `remember(file_path, symbol_name, summary, kind)` — Manual memory
- `forget(query, file_path, stale_only)` — Remove memories
- `memory_status()` — Store statistics
- `explore_structure(path)` — Directory tree

## Usage Pattern

Always use elephant-coder for codebase discovery and search BEFORE reading files directly.
Use `recall_memories` or `search_symbols` first — if you already have context, skip the file read.
