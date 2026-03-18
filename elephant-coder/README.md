# Elephant-Coder

Persistent codebase memory for Claude Code. Elephant-coder indexes your entire project into a local SQLite database, giving Claude instant recall of every function, class, and module across sessions — no re-reading files, no re-exploring. It also tracks cross-file dependencies via a link graph, manages tasks and objectives, fetches RSS news briefings, stores cross-project research notes, enforces code quality with scope guard, detects frameworks, and can send plans to external models for adversarial review via OpenRouter.

Inspired by hippocampal memory circuits: capsule encoding compresses source files into compact summaries, dentate gyrus pattern separation extracts discriminative keywords for FTS5 indexing, and CA3 pattern completion retrieves full context from partial queries.

## Why Elephant-Coder Makes Claude an Enterprise-Grade Senior Engineer

Out of the box, Claude is stateless — every session starts from zero. It re-reads files it already understands, loses track of what was done yesterday, and has no awareness of how changes in one file ripple through the rest of the codebase. Elephant-coder fixes all of that. Each feature below addresses a specific gap between "helpful AI assistant" and "senior engineer who knows the codebase cold."

### 1. Persistent Codebase Memory

**The problem:** Claude forgets everything between sessions. A senior engineer doesn't re-read the same files every morning — they already know the architecture.

**How it works:** On first run, elephant-coder parses every source file in the project using AST parsing (Python) or regex extraction (TypeScript, C/C++, GLSL, etc.), compressing each function, class, and module into a compact memory capsule stored in a local SQLite database with FTS5 full-text search. On subsequent sessions, only changed files are re-indexed (mtime check). Before Claude reads any file, a PreToolUse hook checks if memories already exist — if so, Claude already has context and can skip the read entirely.

**Enterprise impact:** Claude starts every session with full project knowledge. It doesn't waste tokens re-reading code it already understands. It can answer "what does function X do?" or "where is the authentication logic?" instantly from memory, the way a senior engineer answers from experience.

### 2. File Link Graph & Impact Analysis

**The problem:** When you change a function, you need to know what depends on it. Without this, you get cascading breakage — the kind of bug that ships to production because nobody checked the callers.

**How it works:** During indexing, elephant-coder extracts cross-file relationships: Python imports (via AST), C/C++ `#include` directives, and even shader dispatch calls (Python files that reference `.glsl`/`.comp` shaders by name). These are stored in a `file_links` table with source/target/type columns. The `what_broke(since)` tool uses git history + the link graph to show exactly which symbols changed and which files depend on them. The `show_call_graph(symbol, depth)` tool traces both forward (what it calls) and reverse (what calls it) dependency chains. The `project_overview()` tool identifies "hub files" — the most-imported files that form the architectural pillars of the codebase.

**Enterprise impact:** Claude reasons about changes like a staff engineer doing a design review. Before modifying a utility function, it checks the dependency graph and knows that 14 files import it. It flags high-risk changes, suggests running the right tests, and warns you about downstream impact — exactly what prevents production incidents.

### 3. Task Management & Scope Enforcement

**The problem:** AI agents love to wander. You ask for a bug fix and they refactor three unrelated modules. In enterprise development, undisciplined scope creep is how regressions happen.

**How it works:** Elephant-coder maintains a persistent task list with IDs (T-001, T-002), priorities, scopes (which files/directories a task covers), statuses (pending, in_progress, completed, blocked), and notes. Project objectives and constraints are stored alongside tasks. A SessionStart hook enforces the rule: every code change must trace back to an active task. If Claude needs to go out of scope, it must write a Change Request (with risk assessment based on dependent file count) and ask for approval. The task manager also scans for `TODO`/`FIXME`/`HACK`/`XXX` comments across 20+ languages.

**Enterprise impact:** Claude works like an engineer following a ticket system. It stays focused on the current task, documents out-of-scope discoveries as change requests, and maintains a clear audit trail of what was done, why, and what's left. This is the discipline that separates a junior dev from a senior one.

### 4. Scope Guard & Code Quality Enforcement

**The problem:** AI-generated code tends toward long files, duplicated logic, and inconsistent structure. Left unchecked, it produces what the industry calls "AI slop."

**How it works:** After every `Edit`, a PostToolUse hook checks the file length — warning at 900+ lines and enforcing a hard 1000-line limit. If the limit is exceeded, Claude must split the file before continuing. After every `Write`, a hook checks whether a file with the same name already exists elsewhere in the project to prevent accidental duplication. The scope guard also includes a `generate_change_request()` function that assigns risk levels (LOW/MEDIUM/HIGH) based on how many files depend on the code being changed.

**Enterprise impact:** Claude self-enforces the same code quality standards a tech lead would catch in review — file size limits, no duplicates, proper modular structure, and risk-aware change management. Every edit gets an internal "Reddit Test": would you post this code publicly without being called AI slop?

### 5. Project Mental Model & Framework Detection

**The problem:** When a new engineer joins a team, it takes weeks to build a mental model of the codebase — which files are important, what the architecture looks like, what frameworks are in play.

**How it works:** The `project_overview()` tool generates a comprehensive mental model by querying the memory store for the top modules (by line count), the link graph for hub files (most-imported), git history for recent changes (last 7 days), and the framework detector for installed frameworks. Framework detection checks for source project markers (e.g., `backend/compute.py` + `shaders/` = grilly project) and dependency lists (`requirements.txt`, `pyproject.toml`). For detected frameworks, it generates API compatibility maps (e.g., `torch.nn.Linear` → `grilly.nn.Linear`), quick-start code snippets, and lists of key architectural differences.

**Enterprise impact:** Claude onboards itself in seconds. It knows the project's architecture, its most critical files, what's been changing recently, and what frameworks are involved — with framework-specific knowledge baked in. This is the difference between "I see a Python project" and "I see a grilly project with Vulkan compute shaders, and here's how its API maps to PyTorch."

### 6. Cross-Project Research Notes & Global Knowledge

**The problem:** Engineers accumulate knowledge across projects — papers they've read, patterns they've discovered, techniques that worked. Claude loses all of this between sessions and projects.

**How it works:** The global knowledge store (`~/.elephant-coder/global/knowledge.db`) persists across all projects. It stores research notes (with topics, summaries, source URLs, tags, and actionability flags), session summaries (what was accomplished, tasks completed, tasks remaining), coding idioms (recurring patterns tracked by frequency), and framework reference data. Notes are searchable via FTS5 with BM25 ranking.

**Enterprise impact:** Claude accumulates institutional knowledge the way a 10-year veteran does. A technique discovered while working on project A is available when working on project B. Research papers read during one session inform decisions in future sessions. This cross-pollination is one of the most valuable things a senior engineer brings to a team.

### 7. RSS News Briefing & Staying Current

**The problem:** Senior engineers stay current with the industry. They know about new vulnerabilities, API changes, library updates, and emerging best practices. Claude's training data has a cutoff.

**How it works:** At session start, elephant-coder fetches articles from 17 preconfigured RSS/Atom feeds (Hacker News, Ars Technica, The Verge, Wired AI, arXiv CS/AI, Reddit r/LocalLLaMA, CBC Tech, and more). It parses RSS 2.0 and Atom XML, follows links to extract full article text when summaries are short, deduplicates against previously stored notes, and saves new articles as research notes in the global knowledge store. A plain-text briefing is generated and injected into the session context.

**Enterprise impact:** Claude starts every session aware of what happened in the tech world since the last session. If a critical CVE dropped overnight, or a major library released a breaking change, Claude knows about it before you do. This is the kind of situational awareness that prevents "we shipped with a known vulnerability" incidents.

### 8. External Validation via OpenRouter

**The problem:** A single model reviewing its own work is like an engineer reviewing their own pull request — blind spots are inevitable. Enterprise code review requires independent verification.

**How it works:** When enabled, elephant-coder can send plans and completed work to an external model (default: Gemini 3.1 Flash Lite) via OpenRouter for adversarial review. The `get_external_review(plan)` tool sends a plan with project objectives and asks the external model to find every flaw, gap, and risk, tagging each issue as Critical, Major, or Minor. The `request_audit(task_id)` tool sends completed task details, changed files, and test results for independent verification. Responses are parsed into structured issue lists with severity levels.

**Enterprise impact:** Claude gets a second opinion before you do. It's the equivalent of having a staff engineer on another team glance at your design doc and say "have you considered X?" This catches architectural mistakes, missing edge cases, and security issues that self-review misses — the exact failure mode that enterprise code review processes are designed to prevent.

### 9. Hebbian Relevance Scoring & Memory Consolidation

**The problem:** Not all code is equally important. A utility function accessed 50 times matters more than a test fixture accessed once. Flat storage treats everything the same.

**How it works:** Every time a memory is retrieved, its access count increments and its freshness timestamp updates (Hebbian strengthening). Relevance is computed as `0.6 * recency + 0.4 * log(1 + access_count)`, so frequently accessed, recently touched memories rank higher in search results. When the store exceeds 90% capacity (default 50,000 entries), a consolidation cycle runs: stale memories are detected (source file changed on disk), all relevance scores are recomputed, the bottom 10% by relevance are evicted (skipping anything accessed in the last hour), and Redis FTS cache is flushed.

**Enterprise impact:** Claude's memory self-organizes like a human engineer's. The core architecture files that get referenced every session stay top-of-mind. One-off utilities that haven't been touched in months fade away. This means search results are always biased toward the code that actually matters — the same way a senior engineer instinctively knows which files are "hot" in the codebase.

### 10. Redis Write-Through Caching

**The problem:** On large codebases (50K+ memories), SQLite FTS5 queries can take noticeable time. Repeated queries for the same symbols or files shouldn't hit disk every time.

**How it works:** Elephant-coder maintains a write-through Redis cache with three key types: individual memory entries (1-year TTL), file-level memory ID sets (1-year TTL), and FTS search results (3-month TTL). Every write goes to both SQLite and Redis. Every read checks Redis first, falling back to SQLite with automatic cache backfill. File invalidation cascades through the cache — when a file changes, all its cached entries and any FTS results that might reference them are flushed. The cache is completely optional; if Redis is unavailable, everything falls back to SQLite with zero errors.

**Enterprise impact:** Claude operates at the speed of an engineer who has the codebase loaded in their head. Repeated queries return instantly from memory instead of scanning a database. For large enterprise codebases with tens of thousands of symbols, this is the difference between a perceptible pause and instant recall.

### 11. Massive Token Savings

**The problem:** Claude's default workflow is expensive. Every session, it re-reads the same files, re-explores the same directory structures, and re-discovers the same architecture. On a 50-file project, a single session can burn 100K+ tokens just getting oriented — and that cost repeats every session.

**How it works:** Elephant-coder eliminates redundant reads at every level:

- **PreToolUse Read hook** — Before Claude opens any file, the hook checks `recall_file_memories()`. If compressed summaries already exist for that file's functions, classes, and module structure, Claude has the context it needs without reading the full source. A 500-line file that would cost ~2K tokens to read is replaced by a ~200-token compressed summary.
- **Session start injection** — Instead of Claude running `Glob`, `Grep`, `Read`, and `ls` to understand the project (easily 10-20 tool calls), `project_overview()` injects the full mental model in a single response: key modules, hub files, recent changes, detected frameworks. One tool call replaces dozens.
- **FTS5 search vs. file scanning** — When Claude needs to find where a function is defined or how a concept is implemented, `recall_memories()` searches compressed summaries via BM25 ranking. This replaces the pattern of `Grep` → read file 1 → read file 2 → read file 3 that typically costs 5-10K tokens per search.
- **Redis caching** — Repeated queries (common in multi-step tasks where Claude revisits the same symbols) hit Redis cache instead of SQLite, and the results are already in compressed form. Zero redundant disk reads, zero redundant token spend.
- **Incremental indexing** — Only changed files are re-indexed via mtime checks. A session start on an unchanged codebase costs near-zero indexing tokens instead of re-parsing everything.
- **Compressed capsule format** — Each memory is a compressed summary, not raw source. A 200-line class with docstrings, whitespace, and boilerplate becomes a ~50-token capsule listing its methods, dependencies, and purpose. Across 50K memories, this compression ratio is what makes the entire system feasible.

**Enterprise impact:** In practice, elephant-coder reduces per-session token usage by 50-80% on established projects. The first session pays the indexing cost; every subsequent session starts with full context for near-zero tokens. For teams running Claude across multiple engineers and projects, this translates directly into lower API costs, faster response times (fewer tool calls = less latency), and higher output quality (Claude spends its context window on reasoning, not on re-reading code it already knows).

## Installation

```bash
claude plugin add grillcheese-ai/grilly-plugins/elephant-coder
```

### Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (used to run the MCP server)
- Redis (optional, for write-through caching layer)

## How It Works

When you start a Claude Code session, elephant-coder automatically:

1. **Indexes your entire project** — parses all supported file types, extracts functions, classes, modules, and symbols into compressed memory capsules
2. **Generates a project mental model** — identifies key modules, architectural hub files, detected frameworks, and recent git changes
3. **Loads active tasks and objectives** — restores your project's task list and work context
4. **Recalls context before file reads** — a PreToolUse hook checks memories before every `Read`, so Claude already has context
5. **Re-indexes on edits** — PostToolUse hooks trigger after `Edit` and `Write` to keep memories fresh, check file size limits, and detect duplicates
6. **Fetches news briefing** — pulls relevant tech news from configured RSS feeds at session start
7. **Consolidates automatically** — evicts stale/low-relevance memories when the store reaches capacity
8. **Skips unchanged files** — mtime checks make re-indexing fast

All memories persist in `~/.elephant-coder/<project-hash>/` as a SQLite database with FTS5 full-text search.

## Supported Languages

| Language | Extensions | Parsing |
|---|---|---|
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
| Plain text | `.txt`, `.tex`, `.rst`, `.csv`, `.log` | Chunked text ingestion |

## Slash Commands

| Command | Description |
|---|---|
| `/ec:index` | Full project re-index (all file types) |
| `/ec:recall <query>` | Search memories for code, symbols, or concepts |
| `/ec:status` | Memory store statistics |
| `/ec:graph <symbol>` | Call graph for a symbol |
| `/ec:recent [days]` | Recently changed files with indexed symbols |
| `/ec:ingest [path]` | Ingest documents from knowledge directories |

## MCP Tools

### Core Memory

| Tool | Description |
|---|---|
| `index_all(force)` | Index the entire project — all supported file types in one call. Called automatically at session start. |
| `index_directory(path, patterns, max_files, force)` | Index files matching a glob pattern in a directory |
| `recall_memories(query, limit, kind)` | Full-text search across all stored memories with BM25 ranking |
| `recall_file_memories(file_path)` | Retrieve all memories for a specific file |
| `search_symbols(name, kind)` | Direct symbol lookup by name (exact then prefix match) |
| `remember(file_path, symbol_name, summary, kind, keywords)` | Manually store a memory about code you've explored |
| `forget(query, file_path, stale_only)` | Remove memories by query, file, or staleness |
| `memory_status()` | Store statistics: total, capacity, staleness, by-kind breakdown, most accessed |

### Code Intelligence

| Tool | Description |
|---|---|
| `show_call_graph(symbol, depth)` | Forward and reverse dependency trace for a symbol |
| `get_dependencies(file_path)` | Import/include graph — what a file imports and what imports it |
| `explore_structure(path, max_depth)` | Directory tree with file counts grouped by extension |
| `summarize_directory(path, max_symbols)` | Compact table of contents of all indexed symbols in a directory |
| `recent_changes(days, limit)` | Git-aware recently modified files with their indexed symbols |
| `what_broke(since)` | Semantic diff — what symbols changed and what depends on them (impact analysis) |
| `project_overview()` | Full mental model: key modules, hub files, detected frameworks, recent changes, memory stats |

### Task Management

Persistent task tracking with objectives, priorities, scoping, and change requests.

| Tool | Description |
|---|---|
| `get_tasks()` | Current project task list with objectives, constraints, and status |
| `add_task(description, scope, priority)` | Add a new task (auto-assigned T-### ID) |
| `update_task(task_id, status, notes)` | Update task status (`pending`, `in_progress`, `completed`, `blocked`) or notes |
| `set_project_objectives(objectives)` | Set the project's main objectives (pipe-separated) |

Task manager also supports:

- **Scope checking** — verify if a file falls within an active task's scope
- **Change requests** — formal CR records with risk assessment (LOW/MEDIUM/HIGH based on dependent count)
- **TODO scanning** — scans source files for `TODO`, `FIXME`, `HACK`, `XXX` comments across 20+ languages

### Research & Notes

Cross-project knowledge that persists globally in `~/.elephant-coder/global/knowledge.db`.

| Tool | Description |
|---|---|
| `take_note(topic, summary, source, tags)` | Save a research note — papers, techniques, ideas, patterns |
| `recall_notes(query, limit)` | Full-text search across research notes |
| `get_news_briefing(topics)` | Fetch and summarize news from configured RSS/Atom feeds |
| `ingest_knowledge(path, force)` | Ingest documents (PDF, Markdown, text, YAML, JSON) from knowledge directories |

### Global Knowledge Store

The global store tracks knowledge that spans all projects:

- **Frameworks** — detected frameworks with API maps, quick-start guides, and key differences
- **Session summaries** — what was accomplished, tasks completed, tasks remaining
- **Research notes** — searchable notes with tags, source links, and actionability flags
- **Coding idioms** — recurring patterns tracked by frequency across projects

### External Validation (via OpenRouter)

Get adversarial reviews from external models to catch blind spots.

| Tool | Description |
|---|---|
| `get_external_review(plan, context)` | Send a plan to an external model for adversarial review. Returns severity-tagged issues (Critical/Major/Minor). |
| `request_audit(task_id, files_changed, test_results)` | Independent audit of completed task — verifies correctness, completeness, quality |
| `update_settings(...)` | Configure all settings including external validation |

Default model: `google/gemini-3.1-flash-lite-preview` via OpenRouter. Set your API key via `OPENROUTER_API_KEY` env var or in settings.

### Scope Guard

Built-in code quality enforcement:

- **File size checking** — warns at 90% of limit (default 1000 lines), blocks above
- **Duplicate file detection** — scans project for existing files with the same name before creating new ones
- **Change request generation** — structured CR documents with risk assessment based on dependent file count

## Automatic Behaviors (Hooks)

Elephant-coder registers hooks that run without manual intervention:

### SessionStart

- Runs `index_all()` to refresh the project index
- Runs `project_overview()` for the full mental model
- Runs `get_tasks()` to load active tasks and objectives
- Runs `memory_status()` to check store health
- Runs `get_news_briefing()` for today's relevant news
- If no objectives are set, prompts the user to define them

### PreToolUse (Read)

- Before any file read, checks `recall_file_memories()` to provide existing context

### PostToolUse (Edit)

- Checks file length (warns at 900+ lines, enforces 1000-line limit)
- Re-indexes the edited file silently
- Runs relevant tests if available

### PostToolUse (Write)

- Checks for duplicate files in the project
- Enforces file length limit
- Re-indexes the new file silently

### Enforced Rules

- Every code change must trace to an active task
- No out-of-scope features without a Change Request
- Files must stay under 1000 lines (split if approaching)
- Proper OOP structure: classes, single responsibility, clean interfaces
- Tests run after every edit

## Memory Architecture

### Capsule Encoding

Each memory entry is a compressed "capsule" containing:

- **Identity** — deterministic SHA-256 ID from `file_path:symbol_name:kind`
- **Content** — compressed summary and discriminative keywords (DG pattern separation)
- **File metadata** — line count, mtime for staleness detection
- **Cognitive metadata** — access count, relevance score, freshness timestamp, creation time
- **Dependencies** — links to other symbols (imports, includes, shader dispatches)

### Relevance Scoring (Hebbian Learning)

Memories are strengthened on access (like synaptic potentiation):

```
relevance = 0.6 * recency + 0.4 * log(1 + access_count)
```

- `recency = 1 / (1 + hours_since_last_access)` — decays over time
- `frequency = log(1 + access_count)` — grows with use
- Frequently accessed, recently touched memories rank higher
- Stale memories (source file changed since indexing) are flagged and eventually evicted

### Consolidation Cycle

When the store exceeds 90% capacity (default 50,000 memories):

1. **Staleness detection** — compare `file_mtime` against disk, mark outdated entries
2. **Relevance recomputation** — update all scores based on current time
3. **Capacity eviction** — evict bottom 10% by relevance (skip recently accessed)
4. **Cache flush** — invalidate Redis FTS cache (may reference evicted entries)

### File Link Graph

Cross-file relationship tracking stored in a separate `file_links` table:

- **Python** — AST-based import resolution to file paths (with fallback regex)
- **C/C++** — `#include` resolution against project root and file parent
- **Shaders** — detects `load_shader`/`create_pipeline`/`compile_shader` calls linking Python to `.glsl`/`.comp`/`.vert`/`.frag` files

Powers:

- `show_call_graph()` — forward and reverse dependency tracing
- `what_broke()` — impact analysis showing which files depend on changed code
- `project_overview()` — identifies hub files (most-imported architectural pillars)
- `get_dependencies()` — complete import/imported-by graph for any file

### Framework Detection

Auto-detects installed frameworks by checking:

- **Source project markers** (e.g., `backend/compute.py` + `shaders/` = grilly project)
- **Dependency lists** (`requirements.txt`, `pyproject.toml`)

For detected frameworks, generates:

- API compatibility maps (e.g., PyTorch → grilly equivalents)
- Quick-start code snippets
- Key architectural differences

## Configuration

Settings are stored per-project in `.claude/elephant-coder.local.md` (YAML frontmatter) and can be updated via the `update_settings()` tool. Changes take effect on the next tool call.

| Setting | Default | Description |
|---|---|---|
| `max_memories` | 50,000 | Maximum memories in the store |
| `relevance_threshold` | 0.1 | Minimum relevance score for search results |
| `redis_url` | `redis://localhost:6380` | Redis URL for write-through caching |
| `redis_ttl` | 1 year | Redis cache TTL |
| `skip_dirs` | `.venv`, `node_modules`, `__pycache__`, `dist`, `build`, `.git`, `.eggs` | Directories to skip during indexing |
| `scope_guard` | true | Enable scope guard (block untracked changes) |
| `auto_test_after_edit` | true | Prompt to run tests after edits |
| `rss_feeds` | 17 feeds (HN, Ars, Verge, Wired, arXiv, Reddit, CBC, etc.) | RSS/Atom feed URLs for news briefing |
| `rss_max_articles_per_feed` | 5 | Max articles per feed |
| `rss_fetch_full_articles` | true | Follow links to extract full article text |
| `external_validation.enabled` | false | Enable OpenRouter-based external review |
| `external_validation.openrouter_api_key` | null (falls back to `OPENROUTER_API_KEY` env) | OpenRouter API key |
| `external_validation.model` | `google/gemini-3.1-flash-lite-preview` | Model for external reviews |
| `external_validation.validate_plans` | true | Auto-validate plans before execution |
| `external_validation.audit_completed_tasks` | true | Auto-audit completed tasks |
| `external_validation.require_approval_on_issues` | true | Require user approval when issues found |

### Redis Caching

Write-through Redis cache with three key types:

- `ec:{project}:mem:{id}` — individual memory entries (1 year TTL)
- `ec:{project}:file:{hash}` — set of memory IDs per file (1 year TTL)
- `ec:{project}:fts:{hash}` — cached FTS search results (3 month TTL)

Automatic invalidation on file changes and consolidation. Falls back gracefully to SQLite-only if Redis is unavailable.

## Storage

All data is stored locally:

- **Memories** — `~/.elephant-coder/<project-hash>/memories.db` (SQLite + FTS5)
- **Tasks** — `~/.elephant-coder/<project-hash>/tasks.json`
- **Research notes** — `~/.elephant-coder/global/knowledge.db` (shared across all projects)
- **Settings** — `.claude/elephant-coder.local.md` (per-project, YAML frontmatter)

## Dependencies

**Required:**

- `mcp>=1.2.0` — Model Context Protocol server framework
- `pypdf>=4.0.0` — PDF text extraction
- `pyyaml>=6.0` — Settings parsing
- `httpx>=0.27.0` — RSS feed fetching and OpenRouter API calls

**Optional:**

- `redis>=5.0.0` — Write-through caching layer (`pip install elephant-coder[redis]`)

## License

MIT
