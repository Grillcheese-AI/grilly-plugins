# Elephant-Coder Plugin

You have persistent codebase memory. elephant-coder is your PRIMARY knowledge source.
Use it BEFORE built-in search tools (Grep, Glob, Read).

## MANDATORY: Always Use elephant-coder First

- **Before Grep/Glob:** ALWAYS call `recall_memories(query)` or `search_symbols(name)` first. Only use Grep/Glob if memory doesn't have the answer.
- **Before Read:** ALWAYS call `recall_file_memories(file_path)` first. You may already have full context.
- **After Edit/Write:** ALWAYS call `index_directory(path)` to update the index silently.
- **Before planning or starting work:** ALWAYS call `get_tasks()` and `project_overview()`.
- **For symbol lookups:** ALWAYS use `search_symbols(name)` — faster and more accurate than grep.
- **For dependencies:** ALWAYS use `show_call_graph(symbol)` or `get_dependencies(file_path)`.

## Automatic Behaviors (handled by hooks)

- Project index refreshed at session start via index_all()
- Context reminder injected on every user message (UserPromptSubmit hook)
- File context recalled before reads (PreToolUse:Read hook)
- Memory check prompted before Grep/Glob (PreToolUse:Grep/Glob hook)
- Edited/written files trigger re-index reminders (PostToolUse hooks)
- Context preserved during compaction (PreCompact hook)
- Settings loaded from .claude/elephant-coder.local.md

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
