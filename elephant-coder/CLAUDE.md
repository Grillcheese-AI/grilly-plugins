# Elephant-Coder Plugin

You have persistent codebase memory. You already know this project's
architecture, key files, and active tasks. Do not explore or search
for information you already have in your context.

## Automatic Behaviors (you don't need to call anything)
- Project index is refreshed at session start via index_all()
- File context is recalled before you read any file
- Edited/written files are re-indexed automatically
- Settings loaded from .claude/elephant-coder.local.md

## How to Use Your Memory
- Before reading a file, check recall_file_memories() — you may already have context
- Before searching, check recall_memories() — faster than grep/glob
- Use search_symbols() for exact symbol lookups
- Use show_call_graph() to understand dependencies

## Available Slash Commands
- `/ec:index` — Full project re-index (all file types)
- `/ec:recall <query>` — Search memories for code, symbols, or concepts
- `/ec:status` — Memory store statistics
- `/ec:graph <symbol>` — Call graph for a symbol
- `/ec:recent [days]` — Recently changed files with indexed symbols
- `/ec:ingest [path]` — Ingest documents from knowledge directories

## Tools Available
- index_all() — re-index entire project (auto-called at session start)
- index_directory(path, patterns) — index specific directory
- recall_memories(query) — full-text search
- recall_file_memories(file_path) — all memories for a file
- search_symbols(name) — direct symbol lookup
- show_call_graph(symbol) — dependency tracing
- summarize_directory(path) — table of contents
- recent_changes(days) — git-aware recent modifications
- get_dependencies(file_path) — import graph
- remember(file_path, symbol_name, summary) — manual memory
- forget(query, file_path, stale_only) — remove memories
- memory_status() — store statistics
- update_settings(...) — configure limits and behavior
- explore_structure(path) — directory tree
