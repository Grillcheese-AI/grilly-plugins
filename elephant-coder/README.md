# Elephant-Coder

Persistent codebase memory, semantic search, and self-extending AI tools for Claude Code.

Elephant-coder gives Claude a brain that persists across sessions. It indexes your entire project, stores compressed summaries in Redis (primary) and SQLite (durable fallback), adds semantic vector search via Qdrant or local embeddings, learns your personality and habits, and lets Claude create its own tools to help you better.

Inspired by hippocampal memory circuits: capsule encoding compresses source files into compact summaries, dentate gyrus pattern separation extracts discriminative keywords for FTS5 indexing, and CA3 pattern completion retrieves full context from partial queries.

## What Makes Elephant-Coder Different

Out of the box, Claude is stateless — every session starts from zero. Elephant-coder turns Claude into a senior engineer who knows the codebase cold, remembers what you care about, creates its own tools when it needs them, and gets better at helping you over time.

### Persistent Memory

Claude forgets everything between sessions. Elephant-coder parses every source file using AST parsing (Python) or regex extraction (TypeScript, C/C++, GLSL, etc.), compresses each function, class, and module into a memory capsule, and stores them in Redis (primary) with SQLite as durable fallback. On subsequent sessions, only changed files are re-indexed. Claude starts every session with full project knowledge.

### Semantic Search

Keyword search fails when "authentication" should match `verify_token`. Elephant-coder uses hybrid retrieval — FTS5 keyword matching + vector semantic search (all-MiniLM-L6-v2, 384-dim) merged with Reciprocal Rank Fusion. Vectors are stored in Qdrant (optional) or locally via numpy. No more "empty response" on conceptual queries.

### Know Your User

Opt-in user profiling that silently observes your behavior, emotions, goals, habits, and recurring requests. Stored globally at `~/.elephant-coder/user_profile.db` — the same you across all projects. Professional and personal objectives inform all suggestions. Recurrent requests seen 3+ times trigger proactive action. Hebbian reinforcement strengthens observations with repetition; stale ones decay.

### Self-Extending Modules

Claude can create its own tools. When it identifies a gap in capabilities or a recurring need, it writes a Python module — from simple utilities to full MCP sub-servers with their own tools, skills, and hooks. Claude can then tell subagents "use `run_module('my_tool')` to do X." The system auto-suggests modules based on your recurrent request patterns.

### External Validation (Ensemble Mode)

Single-model self-review has blind spots. Elephant-coder can send plans and completed work to an external model via OpenRouter for adversarial review. The `/ec:second-opinion` skill provides structured review before implementing features, flagging issues as Critical/Major/Minor.

## Installation

```bash
claude plugin add grillcheese-ai/grilly-plugins/elephant-coder
```

### Requirements

- Python 3.12+
- Redis (primary store — falls back to SQLite-only if unavailable)

### Optional

- [Qdrant](https://qdrant.tech/) for vector search (falls back to local numpy)
- `qdrant-client` — `pip install elephant-coder[qdrant]`
- OpenRouter API key for ensemble mode / external validation

## How It Works

When you start a Claude Code session, elephant-coder automatically:

1. **Indexes your entire project** — all supported file types, with vector embeddings
2. **Generates a project mental model** — key modules, hub files, frameworks, recent git changes
3. **Loads tasks, objectives, user profile, and persona** — full context restoration
4. **Reinforces context on every message** — UserPromptSubmit hook ensures Claude never forgets
5. **Recalls context before file reads** — PreToolUse hooks check memory before Read, Grep, Glob
6. **Re-indexes on edits** — PostToolUse hooks directly re-index files (not just reminders)
7. **Preserves context during compression** — PreCompact hook survives context window limits
8. **Fetches news briefing** — pulls relevant tech news from configured RSS feeds
9. **Loads active persona and ensemble mode** — behavioral customization from session start

## Architecture

```text
┌─────────────────────────────────────────────────────┐
│                   Claude Code                        │
├─────────────┬───────────────┬───────────────────────┤
│   7 Hooks   │  16 Skills    │  30+ MCP Tools        │
├─────────────┴───────────────┴───────────────────────┤
│                elephant-coder                        │
├──────────┬──────────┬──────────┬───────────────────┤
│  Redis   │ SQLite   │ Qdrant/  │ User Profile      │
│ (primary)│ (fallback│  numpy   │ (global db)       │
│          │  + FTS5) │ (vectors)│                   │
├──────────┴──────────┴──────────┴───────────────────┤
│              Module System                          │
│  (Claude-created tools, MCP servers, workflows)     │
└─────────────────────────────────────────────────────┘
```

### Storage Hierarchy

| Store | Role | Data |
|-------|------|------|
| **Redis** | Primary read store | Entries, symbol index, kind index, FTS cache |
| **SQLite** | Durable fallback + FTS5 | Full entries, FTS5 full-text search, file links |
| **Qdrant** | Vector search (optional) | 384-dim embeddings, project-bucketed |
| **Local numpy** | Vector fallback | `.npy` files per project |
| **User profile DB** | Global user knowledge | `~/.elephant-coder/user_profile.db` |
| **Module storage** | Custom tools | `~/.elephant-coder/modules/` + `.claude/elephant-modules/` |

## Supported Languages

| Language | Extensions | Parsing |
|----------|-----------|---------|
| Python | `.py` | Full AST parsing |
| TypeScript/JavaScript | `.ts`, `.js`, `.tsx`, `.jsx` | Regex extraction |
| C/C++ | `.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` | Regex extraction |
| GLSL Shaders | `.glsl`, `.vert`, `.frag`, `.comp`, `.geom`, `.tesc`, `.tese` | Regex extraction |
| Markdown | `.md` | Heading/section extraction |
| PDF | `.pdf` | Text extraction (via pypdf) |
| TOML | `.toml` | Key/table extraction |
| JSON | `.json` | Key/structure extraction |
| YAML | `.yaml`, `.yml` | Key/structure extraction |
| CMake | `CMakeLists.txt`, `.cmake` | Target/variable extraction |

## Slash Commands

### Core Memory

| Command | Description |
|---------|-------------|
| `/ec:index` | Full project re-index with vector embeddings |
| `/ec:recall <query>` | Hybrid search: keywords + semantic similarity |
| `/ec:status` | Memory store + vector store + user profile statistics |
| `/ec:graph <symbol>` | Call graph for a symbol |
| `/ec:recent [days]` | Recently changed files with indexed symbols |
| `/ec:ingest [path]` | Ingest documents from knowledge directories |

### Configuration

| Command | Description |
|---------|-------------|
| `/ec:configure` | Interactive project settings (redis, qdrant, framework, API keys, docs paths) |
| `/ec:feeds` | Manage RSS feeds — add, remove, list, start/stop |
| `/ec:ensemble` | Toggle second opinion from external AI model (OpenRouter) |
| `/ec:persona` | Manage AI personas — add, edit, select, set default |
| `/ec:user-profile` | Manage user profile — view, enable/disable, delete observations |
| `/ec:modules` | Create and manage elephant modules (custom tools, MCP servers) |

### Development Workflow

| Command | Description |
|---------|-------------|
| `/ec:second-opinion` | Structured review from external model before implementing |
| `/ec:cicd` | Set up CI/CD pipelines (GitHub Actions, pre-commit, deploy) |
| `/ec:changelog` | Update CHANGELOG.md — mandatory before every commit |
| `/ec:git-versioning` | Enforce conventional commits, semantic versioning, branch hygiene |

## MCP Tools (30+)

### Core Memory

| Tool | Description |
|------|-------------|
| `index_all(force)` | Index entire project with vector embeddings |
| `index_directory(path, patterns, max_files, force)` | Index files matching a glob pattern |
| `recall_memories(query, limit, kind)` | Hybrid search: FTS5 + vector, merged with RRF |
| `recall_file_memories(file_path)` | All memories for a specific file |
| `search_symbols(name, kind)` | Direct symbol lookup (Redis-first) |
| `remember(file_path, symbol_name, summary, kind, keywords)` | Manually store a memory |
| `forget(query, file_path, stale_only)` | Remove memories |
| `memory_status()` | Full statistics: memory, vectors, user profile, modules |

### Code Intelligence

| Tool | Description |
|------|-------------|
| `show_call_graph(symbol, depth)` | Forward and reverse dependency trace |
| `get_dependencies(file_path)` | Import/include graph |
| `explore_structure(path, max_depth)` | Directory tree with file counts |
| `summarize_directory(path, max_symbols)` | Table of contents of indexed symbols |
| `recent_changes(days, limit)` | Git-aware file modifications |
| `what_broke(since)` | Impact analysis: changed symbols + their dependents |
| `project_overview()` | Full mental model |

### Task Management

| Tool | Description |
|------|-------------|
| `get_tasks()` | Current task list with objectives |
| `add_task(description, scope, priority)` | Create task (auto T-### ID) |
| `update_task(task_id, status, notes)` | Update task status/notes |
| `set_project_objectives(objectives)` | Set project objectives |

### User Profile (opt-in)

| Tool | Description |
|------|-------------|
| `observe_user(category, content, confidence, context)` | Record user observation (silent) |
| `record_user_request(pattern, example, suggested_action)` | Track recurrent requests |
| `get_user_profile(category)` | View profile with confidence indicators |
| `delete_user_observation(observation_id, category, delete_all)` | Manage profile data |

**Categories:** `professional_goal`, `personal_goal`, `emotion`, `habit`, `problem`, `victory`, `preference`, `recurrent_request`, `personality`, `expertise`, `growth`

### Module System

| Tool | Description |
|------|-------------|
| `create_module(name, description, code, module_type, scope)` | Create a custom tool module |
| `create_mcp_module(name, description, tools_code, skills, hooks)` | Create a full MCP sub-server |
| `list_modules(scope, module_type)` | List installed modules with suggestions |
| `run_module(name, args)` | Execute a module in isolated subprocess |
| `update_module(name, code, description, active)` | Update or toggle a module |
| `delete_module(name)` | Remove a module |
| `get_module_code(name)` | Read module source for review |

**Module types:** `tool`, `analyzer`, `workflow`, `checker`, `generator`, `mcp_server`

### External Validation

| Tool | Description |
|------|-------------|
| `get_external_review(plan, context)` | Second opinion from external model |
| `request_audit(task_id, files_changed, test_results)` | Post-implementation audit |

### Research & News

| Tool | Description |
|------|-------------|
| `take_note(topic, summary, source, tags)` | Save a research note |
| `recall_notes(query, limit)` | Search research notes |
| `get_news_briefing(topics)` | Fetch and summarize RSS news |
| `ingest_knowledge(path, force)` | Ingest documents from knowledge directories |

### Settings

| Tool | Description |
|------|-------------|
| `update_settings(...)` | Configure everything: redis, qdrant, framework, github_repo, docs paths, API keys, feeds, user profile, ensemble mode |

## Hooks (7 Events)

| Hook | Event | What It Does |
|------|-------|-------------|
| SessionStart | Session begins | Injects rules, loads persona, user profile, ensemble mode; triggers startup sequence |
| UserPromptSubmit | Every user message | Reinforces elephant-coder usage; reminds to observe user patterns |
| PreCompact | Context compression | Preserves all elephant-coder rules and workflows through compaction |
| PreToolUse:Read | Before file read | Reminds to check `recall_file_memories()` first |
| PreToolUse:Grep/Glob | Before search | Reminds to check `recall_memories()` first |
| PostToolUse:Edit | After file edit | **Directly re-indexes** the file + checks file length |
| PostToolUse:Write | After file create | **Directly re-indexes** the file + checks for duplicates |

## Memory Architecture

### Hybrid Retrieval

```text
Query → Encoder (all-MiniLM-L6-v2, 384-dim)
         ├── FTS5 BM25 keyword search (SQLite)
         └── Vector cosine similarity (Qdrant or numpy)
              ↓
         Reciprocal Rank Fusion (RRF)
              ↓
         Ranked results with Hebbian strengthening
```

### Relevance Scoring (Hebbian Learning)

```python
relevance = 0.6 * recency + 0.4 * log(1 + access_count)
```

Memories are strengthened on access. Frequently accessed, recently touched memories rank higher. Stale memories decay and are eventually evicted.

### Consolidation Cycle

When the store exceeds 90% capacity (default 50,000 memories):

1. **Staleness detection** — compare `file_mtime` against disk
2. **Relevance recomputation** — update all scores
3. **Capacity eviction** — evict bottom 10% by relevance
4. **Cache flush** — invalidate stale Redis/FTS caches

### Project Bucketing

Each project is isolated via `project_hash` — no cross-project pollution:
- Redis keys: `ec:{project_hash}:mem:*`, `ec:{project_hash}:sym:*`, etc.
- SQLite: `~/.elephant-coder/{project_hash}/memories.db`
- Qdrant: payload filter on `project_hash` within shared collection
- User profile and global knowledge: shared across all projects (intentional)

## Configuration

Settings are per-project in `.claude/elephant-coder.local.md` (YAML frontmatter).

### Storage

| Setting | Default | Description |
|---------|---------|-------------|
| `max_memories` | 50,000 | Maximum memories in the store |
| `relevance_threshold` | 0.1 | Minimum relevance for search results |
| `redis_url` | `redis://localhost:6379` | Redis URL (primary store) |
| `redis_ttl` | 1 year | Redis entry TTL |

### Vector Search

| Setting | Default | Description |
|---------|---------|-------------|
| `vector_search.enabled` | true | Enable hybrid semantic search |
| `vector_search.qdrant_url` | null | Qdrant URL (null = local numpy fallback) |
| `vector_search.encoder_model` | `all-MiniLM-L6-v2` | Sentence-transformers model |

### Project

| Setting | Default | Description |
|---------|---------|-------------|
| `project.framework` | auto-detect | Framework (e.g., "grilly", "django", "react") |
| `project.github_repo` | null | GitHub repo (e.g., "grillcheese/elephant-coder") |
| `project.knowledge_docs_path` | `docs/project_knowledge` | Path for knowledge documents |
| `project.business_docs_path` | `docs/business` | Path for business documents |

### User Profile

| Setting | Default | Description |
|---------|---------|-------------|
| `user_profile.enabled` | false | **Opt-in** — enable user profiling |
| `user_profile.auto_observe` | true | Silently observe user behavior |
| `user_profile.decay_days` | 90 | Days before stale observations decay |

### External Validation

| Setting | Default | Description |
|---------|---------|-------------|
| `external_validation.enabled` | false | Enable ensemble mode |
| `external_validation.openrouter_api_key` | null | OpenRouter API key |
| `external_validation.model` | `google/gemini-3.1-flash-lite-preview` | External model |

### RSS Feeds

| Setting | Default | Description |
|---------|---------|-------------|
| `rss_feeds` | 17 feeds | RSS/Atom feed URLs |
| `rss_max_articles_per_feed` | 5 | Max articles per feed |
| `rss_fetch_full_articles` | true | Follow links for full text |

## Storage Layout

```text
~/.elephant-coder/
├── <project-hash>/
│   ├── memories.db          # SQLite + FTS5 (durable fallback)
│   ├── vectors.npy          # Local vector embeddings
│   ├── vector_index.json    # Vector ID mapping
│   └── tasks.json           # Task persistence
├── global/
│   └── knowledge.db         # Cross-project research notes
├── modules/                 # Global elephant modules
│   └── <module-name>/
│       ├── module.py        # Module code
│       └── manifest.json    # Metadata
└── user_profile.db          # Global user profile

.claude/
├── elephant-coder.local.md  # Per-project settings (YAML frontmatter)
├── elephant-modules/        # Project-specific modules
│   └── <module-name>/
│       ├── module.py / server.py
│       ├── manifest.json
│       ├── skills/          # Module skills (for MCP servers)
│       └── hooks/           # Module hooks (for MCP servers)
└── personas/                # AI persona definitions
    └── <name>.md            # Persona with YAML frontmatter
```

## Dependencies

**Required:**

- `mcp>=1.2.0` — Model Context Protocol server
- `pypdf>=4.0.0` — PDF text extraction
- `pyyaml>=6.0` — Settings parsing
- `httpx>=0.27.0` — RSS feeds and OpenRouter API
- `redis>=7.3.0` — Primary store
- `numpy>=1.26.0` — Vector operations
- `sentence-transformers>=3.0.0` — Text embedding

**Optional:**

- `qdrant-client>=1.9.0` — Qdrant vector backend (`pip install elephant-coder[qdrant]`)

## CI/CD

GitHub Actions pipeline in `.github/workflows/ci.yml`:

- **test** — Memory store, indexer, retriever, hooks (Python 3.12 + 3.13, Redis service)
- **lint** — Syntax compilation of all 17 modules
- **plugin-validate** — Plugin manifest, hooks, all 16 skills/commands

## License

MIT
