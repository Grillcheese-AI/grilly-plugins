# Changelog

All notable changes to elephant-coder are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.3.0] - 2026-03-20

### Added

- **Hybrid semantic search** — `recall_memories()` now combines FTS5 keyword matching with vector similarity (Reciprocal Rank Fusion), solving the "empty response" problem when query terms don't match code identifiers
- **Vector store** (`vector_store.py`) — Qdrant as optional primary vector backend, local numpy cosine similarity as fallback, `all-MiniLM-L6-v2` encoder (384-dim), project bucketing via payload filter
- **UserPromptSubmit hook** — reinforces elephant-coder context on every user message so Claude never forgets to use it
- **PreCompact hook** — preserves elephant-coder rules and workflow through context compression
- **PreToolUse:Grep/Glob hooks** — reminds Claude to check memory before searching
- **Direct re-indexing in PostToolUse hooks** — Edit/Write hooks now actually re-index files via `_reindex.py` instead of just reminding Claude
- **Redis symbol and kind indexes** — `sym:{name}`, `sym:{name}:{kind}`, `kind:{kind}` keys for fast lookups
- **New slash commands:**
  - `/ec:configure` — interactive project settings (redis, qdrant, framework, API keys, docs paths, github repo)
  - `/ec:feeds` — manage RSS feeds (add, remove, list, start/stop)
  - `/ec:persona` — manage AI personas (add, edit, select, set default)
  - `/ec:ensemble` — toggle second opinion from external AI model (OpenRouter)
  - `/ec:second-opinion` — structured review from external model before implementing features
  - `/ec:cicd` — set up CI/CD pipelines (GitHub Actions, pre-commit, deploy)
  - `/ec:changelog` — update changelog before commits
- **Persona system** — stored in `.claude/personas/*.md` with YAML frontmatter, default persona auto-loaded at session start
- **Ensemble mode** — automatic external validation for features/bugs via OpenRouter, configurable model
- **CI/CD pipeline** (`.github/workflows/ci.yml`) — tests memory store, indexer, retriever, hooks; lint; plugin validation across Python 3.12/3.13 with Redis service
- **Expanded `update_settings()` MCP tool** — supports qdrant_url, vector_search_enabled, framework, github_repo, knowledge_docs_path, business_docs_path, openrouter_api_key, external_model, rss_feeds, rss_enabled
- **CHANGELOG.md** — full release history from v0.1.0 to v0.3.0
- `/ec:changelog` skill — enforces changelog updates before every commit
- `/ec:git-versioning` skill — automated conventional commits, semantic versioning, branch hygiene
- `/ec:user-profile` skill — manage "know your user" profile (opt-in, global across projects)
- **User profile engine** (`user_profile.py`) — silently observes user behavior, emotions, goals, habits, problems, victories, and recurrent requests. Adapts Claude's behavior to the user's personality and objectives. Hebbian reinforcement increases confidence on repeated observations. Stale observations decay. Global database at `~/.elephant-coder/user_profile.db`
- **MCP tools**: `observe_user()`, `record_user_request()`, `get_user_profile()`, `delete_user_observation()`
- **Professional/personal goals** tracked as first-class categories — inform all suggestions and decisions
- **Recurrent request automation** — patterns seen 3+ times become auto-eligible for proactive action
- **UserPromptSubmit hook** updated to remind Claude to observe user patterns when profile is enabled
- **SessionStart hook** loads user profile summary and injects observation rules
- **Elephant module system** (`module_system.py`) — Claude can create its own tools, analyzers, workflows, checkers, generators, and full MCP sub-servers to extend elephant-coder's capabilities dynamically
- `/ec:modules` skill — create, list, run, update, delete custom modules
- **MCP sub-servers** — Claude can create standalone MCP servers with their own `@mcp.tool()` functions, skills, and hooks within elephant-coder's module system
- **MCP tools**: `create_module()`, `create_mcp_module()`, `list_modules()`, `run_module()`, `update_module()`, `delete_module()`, `get_module_code()`
- **Module auto-suggestions** — analyzes user recurrent requests and suggests modules Claude should create
- **Module types**: tool, analyzer, workflow, checker, generator, mcp_server
- **Merit/reward system** (`merit_ledger.py`) — gamified point system tracking task completions, positive feedback, proactive actions, bugs caught, tests written, and more. 9 rank tiers from Novice to Transcendent. Global database at `~/.elephant-coder/merit_ledger.db`, syncs to `merit_ledger.json` for portability
- `/ec:merits` skill — view rank, points, stats, and award history
- **MCP tools**: `award_merit()`, `get_merits()` — Claude silently awards/deducts points
- **SessionStart hook** shows current merit rank
- **UserPromptSubmit hook** reminds Claude to award merits for completed tasks and positive feedback

### Changed

- **Redis is now primary store**, SQLite is durable fallback (was: SQLite primary, Redis optional cache)
- **Write order reversed** — Redis first, then SQLite for durability (was: SQLite first, Redis write-through)
- `search_by_symbol()` and `search_by_kind()` now check Redis first with SQLite fallback + backfill
- `upsert_batch()` writes to Redis pipeline first, then SQLite transaction
- `delete()` cleans up all Redis indexes (mem, file, sym, kind)
- SessionStart hook now loads default persona and checks ensemble mode
- SessionStart prompt uses mandatory language ("ALWAYS call...") instead of suggestions
- CLAUDE.md rewritten with mandatory directives and full command reference
- PostToolUse hooks read tool input from stdin to get file paths
- PostToolUse hook timeout increased from 5s to 8s for direct re-indexing
- Bumped version from 0.2.2 to 0.3.0

### Fixed

- Claude ignoring elephant-coder after session start — now reinforced on every message via UserPromptSubmit hook
- elephant-coder context lost during compression — now preserved via PreCompact hook
- `search_by_symbol()` bypassing Redis entirely — now Redis-first
- `search_by_kind()` bypassing Redis entirely — now Redis-first
- PostToolUse hooks only reminded Claude to re-index — now actually perform re-indexing

### Dependencies

- Added: `numpy>=1.26.0`, `sentence-transformers>=3.0.0`
- Optional: `qdrant-client>=1.9.0` (for Qdrant vector backend)

## [0.2.2] - 2026-03-19

### Fixed

- Hook output format — use `decision: "approve"` with `reason` for PreToolUse hooks
- PostToolUse hooks — correct `additionalContext` output format

## [0.2.1] - 2026-03-19

### Fixed

- Various hook behavior bugs

## [0.2.0] - 2026-03-18

### Added

- Project-aware RSS — auto-filter news by project keywords
- Command-type hooks with per-project memory isolation
- Comprehensive README with feature descriptions

## [0.1.0] - 2026-03-17

### Added

- Initial release
- SQLite-backed memory store with Redis cache
- Multi-language code indexer (Python, TypeScript, C/C++, GLSL, Markdown, PDF, TOML, JSON, YAML, CMake)
- FTS5 full-text search with BM25 ranking
- File link graph and call graph analysis
- Task management with objectives
- RSS news briefing
- Research notes and external validation via OpenRouter
- Scope guard (file size limits, duplicate detection)
- SessionStart, PreToolUse:Read, PostToolUse:Edit/Write hooks
- 6 slash commands: index, recall, status, graph, recent, ingest
