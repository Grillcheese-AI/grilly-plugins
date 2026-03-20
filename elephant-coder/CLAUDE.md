# Elephant-Coder Plugin

You have persistent codebase memory. elephant-coder is your PRIMARY knowledge source.
Use it BEFORE built-in search tools (Grep, Glob, Read).

## MANDATORY: Always Use elephant-coder First

- **Before Grep/Glob:** ALWAYS call `recall_memories(query)` or `search_symbols(name)` first. Only use Grep/Glob if memory doesn't have the answer.
- **Before Read:** ALWAYS call `recall_file_memories(file_path)` first. You may already have full context.
- **After Edit/Write:** Files are auto-re-indexed by PostToolUse hooks.
- **Before planning or starting work:** ALWAYS call `get_tasks()` and `project_overview()`.
- **For symbol lookups:** ALWAYS use `search_symbols(name)` — faster and more accurate than grep.
- **For dependencies:** ALWAYS use `show_call_graph(symbol)` or `get_dependencies(file_path)`.

## Automatic Behaviors (handled by hooks)

- Project index refreshed at session start via index_all()
- Context reminder injected on every user message (UserPromptSubmit hook)
- File context recalled before reads (PreToolUse:Read hook)
- Memory check prompted before Grep/Glob (PreToolUse:Grep/Glob hook)
- Edited/written files are auto-re-indexed directly (PostToolUse hooks)
- Context preserved during compaction (PreCompact hook)
- Default persona loaded on session start
- Ensemble mode status checked on session start
- Settings loaded from .claude/elephant-coder.local.md

## Available Slash Commands

### Core Memory

- `/ec:index` — Full project re-index (all file types + vector embeddings)
- `/ec:recall <query>` — Hybrid search: keywords + semantic similarity
- `/ec:status` — Memory store + vector store statistics
- `/ec:graph <symbol>` — Call graph for a symbol
- `/ec:recent [days]` — Recently changed files with indexed symbols
- `/ec:ingest [path]` — Ingest documents from knowledge directories

### Configuration

- `/ec:configure` — Interactive project settings (redis, qdrant, framework, API keys, paths)
- `/ec:feeds` — Manage RSS feeds (add, remove, list, start/stop)
- `/ec:ensemble` — Toggle second opinion from external AI model
- `/ec:persona` — Manage AI personas (add, edit, select, set default)

### Review

- `/ec:second-opinion` — Get structured review from external model before implementing
- `/ec:cicd` — Set up or manage CI/CD pipelines (GitHub Actions, pre-commit, deploy)
- `/ec:changelog` — Update CHANGELOG.md (MANDATORY before every commit)
- `/ec:git-versioning` — Configure git versioning rules (conventional commits, semver, branch hygiene)
- `/ec:user-profile` — Manage user profile (view, enable/disable, delete observations) — opt-in, global
- `/ec:modules` — Create and manage elephant modules (custom tools, MCP servers, workflows)
- `/ec:merits` — View merit points, rank, stats, and award history

## Search Architecture

- **Redis** — primary store for reads (fast key-value, symbol, kind lookups)
- **SQLite** — durable fallback + FTS5 full-text search
- **Vector search** — semantic similarity via Qdrant (optional) or local numpy
- **Hybrid retrieval** — FTS5 + vector results merged with Reciprocal Rank Fusion

## Tools Available

- index_all() — re-index entire project with vector embeddings
- recall_memories(query) — hybrid search (keywords + semantic)
- recall_file_memories(file_path) — all memories for a file
- search_symbols(name) — direct symbol lookup
- show_call_graph(symbol) — dependency tracing
- get_dependencies(file_path) — import graph
- project_overview() — full project mental model
- memory_status() — store + vector statistics
- update_settings(...) — configure all settings
- get_external_review(plan, context) — second opinion from external model
- request_audit(task_id, files, results) — post-implementation audit
- observe_user(category, content) — record user observation (silent, opt-in)
- record_user_request(pattern, example) — track recurrent request
- get_user_profile(category) — view user profile
- delete_user_observation(id, category, delete_all) — manage profile data
- create_module(name, description, code, type) — create custom tool module
- create_mcp_module(name, description, tools_code) — create full MCP sub-server
- list_modules(scope, type) — list installed modules
- run_module(name, args) — execute a module
- update_module(name, code, active) — update or toggle module
- delete_module(name) — remove a module
- award_merit(category, reason, points) — award merit points (silent)
- get_merits(show_log, limit) — view rank, stats, history
