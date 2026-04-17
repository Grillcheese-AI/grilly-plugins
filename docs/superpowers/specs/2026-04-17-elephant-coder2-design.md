# elephant-coder2 — Design Spec

**Date:** 2026-04-17
**Status:** Approved, awaiting implementation plan
**Relationship to v1:** Clean-slate rewrite. v1 continues to exist for legacy projects. No data migration path.

## Motivation

elephant-coder v1 is a substantial Claude Code plugin: persistent codebase memory via Redis/SQLite/Qdrant, 7 hooks, 16+ skills, 30+ MCP tools, user profiling, think tank, self-extending modules. Despite that surface area, it has two persistent weaknesses:

1. **Activation is unreliable.** Hooks inject reminders telling Claude to use elephant-coder, but Claude routinely ignores them. The user finds themselves manually asking "use elephant-coder" on tasks that should obviously benefit from memory. Compliance-by-prompt doesn't work.

2. **No learning loop.** Memory capsules are written once and retrieved as-is. There's no mechanism for the system itself to strengthen, consolidate, or improve memories over time without Claude's involvement. Hebbian scoring exists but is shallow.

v2 addresses both by making activation **mechanical** (baked into tool results, not reminded) and by introducing a local small-model **hippocampus** that autonomously consolidates memories in the background.

## Goals

1. **Automatic activation** — memory context reaches Claude without Claude having to opt in. No reminders, no rules in CLAUDE.md. Mechanical injection at the hook layer.
2. **Token efficiency** — target ~60-75% reduction in elephant-coder context overhead vs v1. Injected tokens are actual retrieved content, not rules or reminders.
3. **Local hippocampus** — a small GGUF model runs in-process via `llama-cpp-python` (Vulkan). Manages session scratch, consolidates memories on idle, reranks retrieval.
4. **Cross-project knowledge** — three-tier storage (scratch / project_durable / global_durable), Claude-driven promotion.
5. **Agentic fitness** — subagents receive memory briefs automatically. Subagents write findings back to the sidecar for main Claude to pull.
6. **Leaner surface** — 20 skills, 12 MCP tools, 5 hooks (vs v1's 18+ / 30+ / 7).

## Non-Goals

- No migration of v1 data. Users keep v1 installed for legacy projects or export/re-ingest manually.
- No cloud/remote memory. Local-only.
- No Qdrant. Small model + numpy vectors handle the semantic-search workload.
- No `PreCompact` rule preservation. v2 has no rules to preserve.
- No persona system. Dropped from v1.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                      Claude Code                          │
│                                                           │
│  [shadowed Read/Grep/Glob]    [12 MCP tools]              │
│  [shadowed Agent dispatch]                                │
└───────┬──────────────────────────────┬───────────────────┘
        │ hook injection                │ MCP calls
        ▼                               ▼
┌──────────────────────────────────────────────────────────┐
│             elephant-coder2 broker (Python)               │
│                                                           │
│  - Unix-socket server (persistent across sessions)        │
│  - Shadowed-tool enrichment at PreToolUse layer           │
│  - Hybrid retrieval (FTS5 + vector + small-model rerank)  │
│  - Tier-aware routing (scratch/project_durable/global)    │
│  - Background task queue + push notifications             │
└───────┬────────────────┬─────────────────┬───────────────┘
        │                │                 │
        ▼                ▼                 ▼
┌────────────────┐  ┌────────────────┐  ┌─────────────────┐
│ Small GGUF     │  │ Redis          │  │ SQLite + FTS5   │
│ model          │  │ (primary read  │  │ (durable ground │
│ (in-process    │  │  cache)        │  │  truth)         │
│  llama.cpp)    │  │                │  │ numpy vectors   │
└────────────────┘  └────────────────┘  └─────────────────┘
```

### Components

**Broker (persistent Python process)**

- Runs as a background process, spawned on first SessionStart of the day, persists across Claude Code sessions.
- Listens on a local Unix-domain socket (`~/.elephant-coder2/broker.sock`) for hook and MCP calls.
- Loads the small GGUF model once at startup, keeps it warm.
- Mediates all access to Redis, SQLite, and the small model. No component touches storage directly except through the broker.

**Small model service (in-process, inside broker)**

- Default model: **Qwen 2.5 1.5B Instruct (Q4_K_M)**, ~1GB on disk.
- Loaded via `llama-cpp-python` with Vulkan acceleration (user's existing global install).
- User can swap to Phi-3.5 mini, Gemma 2 2B, Llama 3.2 3B, etc. via `/ec2:configure`.
- Three job types (promotion-judge from earlier design drafts was dropped — Claude drives promotion):
  1. **Session scratch management** — ingest new content, summarize, embed.
  2. **Consolidation (idle loop)** — dedupe, merge related entries, decay stale ones. Runs every 10 min of idle time by default.
  3. **Retrieval reranking** — top-20 candidates from broker → reranked top-5 with query context.
- Hard latency budget for reranking: 500 ms. If exceeded, broker falls back to raw FTS+vector order.
- State persists at `~/.elephant-coder2/sidecar/` including a `consolidation.log` decision trail.

**Storage layer**

| Store | Role | Contents |
|-------|------|----------|
| Redis | Primary read cache, fast path | Symbol index, kind index, hot memory entries, FTS cache |
| SQLite + FTS5 | Durable ground truth + full-text search | All memory entries (all tiers), links, stats, protected flags |
| numpy `.npy` | Vector store per project | 384-dim embeddings via `all-MiniLM-L6-v2` |
| Global SQLite | Cross-project tier + user profile | `global_durable` memories, user profile DB |

- Writes: SQLite first (durability), then Redis (cache), then vector append.
- Reads: Redis first, fall through to SQLite on miss, then rehydrate Redis.
- If Redis is unreachable, broker degrades to SQLite-only with a log warning. Plugin still works, just slower.

### Memory Tiers

Three tiers in one SQLite table, distinguished by a `tier` column:

| Tier | Scope | Lifecycle | Typical contents |
|------|-------|-----------|-------------------|
| `scratch` | Per-project | Decays on idle; 32,000-entry cap | Session scratch, raw indexed symbols, recent work, stashed subagent findings |
| `project_durable` | Per-project | Long-lived, protected from decay | Project patterns, architecture notes, long-term project context |
| `global_durable` | Cross-project (user-wide) | Long-lived, protected | Transferable patterns/lessons, user-wide knowledge |

Orthogonal flags:

- `is_identity` — always prepended to retrievals for its scope (per-project or global).
- `is_protected` — never evicted, never decayed.

**Promotion is Claude-driven.** The small model does not autonomously decide tier. Claude calls `promote(memory_id, tier, reason)`, which flips the `tier` column. Reason is stored for audit.

**Cross-project retrieval:** broker queries current project DB + global DB in parallel, merges. Project-local results get a small tier weight boost; global results are slightly de-weighted (still relevant, less project-specific).

## Automatic Activation (Shadowed Tools)

This is the core "no more reminding Claude" mechanism.

### Hook behavior

**SessionStart**
- Spawn broker if not running.
- Load identity memory (global + per-project) → inject (~300 tokens).
- Load project mental model (frameworks, recent git changes, top hub files) → inject.
- No rule reiteration. No "always use elephant-coder" text. No CLAUDE.md-style instructions.

**UserPromptSubmit**
- Retrieve top-3 memories matching the user's prompt text.
- Inject as `<memory-context>` block capped at **800 tokens**. Small model trims to fit.
- No reminders, no compliance prompts. Purely retrieved content.
- If nothing relevant, no block injected.

**PreToolUse: Read**
- Broker receives `{tool: "Read", file_path: X}`.
- Queries memory (all tiers) for entries tagged to that file.
- If hits exist, injects `<memory-context>` in hook's `additionalContext` *before* Read runs.
- Claude sees "what you already know about this file" → then the raw file content.
- Hard token cap on injection: **300 tokens** per tool call.

**PreToolUse: Grep / Glob**
- Broker extracts pattern/query terms, does hybrid retrieval (FTS5 + vector + rerank).
- Injects top-N relevant memory snippets (300-token cap).
- Claude sees memory-derived results first, raw tool results second.

**PreToolUse: Agent (subagent dispatch)**
- If Agent prompt does NOT contain `<no-brief/>`, broker auto-generates a `<memory-brief>` from the prompt text and prepends it.
- Brief is capped at 500 tokens.
- Claude opts out for trivial subagents by including `<no-brief/>` in prompt.

**PostToolUse: Edit / Write**
- Broker re-indexes the file directly (AST for Python, regex for other languages).
- New capsules enter `scratch` tier.
- Queued for next consolidation pass.

### What v2 does NOT have

- No PreCompact hook (nothing to preserve).
- No reminder-only PreToolUse hooks.
- No UserPromptSubmit rule injection.
- No elaborate CLAUDE.md overriding Claude's behavior.

### Token-cost expectations

Rough vs v1:

- v1: ~400-800 rule-reminder tokens per user turn + ~200 per tool call.
- v2: ~0 rule tokens. Retrieved-content tokens capped at 800 per turn, 300 per tool call, 500 per subagent brief.
- Net: ~60-75% reduction in elephant-coder-sourced context overhead, with the remaining tokens being actually useful content.

## Agentic Work

### Pre-dispatch briefing

Auto-injected via `PreToolUse:Agent` (default on). Claude can also explicitly call `brief_subagent(task_description)` to get a brief string manually, for cases where it wants to inspect or modify the brief before dispatch.

### Subagent write-back

Subagents call `sidecar_store(tag, content)` to stash findings. Main Claude calls `sidecar_recall(tag_or_query)` to retrieve.

Example flow:

```
Main Claude: Agent(Explore, "find all auth entry points") → [auto-briefed]
  Subagent researches, then: sidecar_store("auth_entry_points_2026-04-17", findings)
  Subagent returns: "Stashed under 'auth_entry_points_2026-04-17'"
Main Claude: sidecar_recall("auth_entry_points_2026-04-17") → compressed answer
```

Main Claude's context only ever sees the compressed summary.

### Background tasks with push notification

Broker exposes `schedule_task(task_type, args)`. Returns a `task_id`. Task types:

- `reindex_project()`
- `consolidate_memories()`
- `run_analysis(prompt)` — small model answers a prompt asynchronously

When task completes, broker sends a Claude Code push notification (system-reminder) with the result. Claude doesn't poll.

## MCP Tool Surface (12)

| Tool | Purpose |
|------|---------|
| `recall(query, tier?, limit?)` | Hybrid search across tiers, reranked by small model |
| `recall_file(file_path)` | All memories for a file |
| `search_symbol(name)` | Direct symbol lookup |
| `graph(symbol, depth?)` | Call graph |
| `remember(content, tags?, tier?)` | Manually store memory |
| `promote(memory_id, tier, reason)` | Flip tier (project_durable or global_durable) |
| `sidecar_store(tag, content)` | Offload context to small model scratch |
| `sidecar_recall(tag_or_query)` | Retrieve from small model |
| `brief_subagent(task_desc)` | Get memory brief for subagent |
| `schedule_task(type, args)` | Background work (returns task_id, push on completion) |
| `status()` | Broker + model + store stats |
| `configure(**settings)` | Update settings |

## Skills Surface (20)

Each skill targets ≤50 lines of markdown (except `/ec2:configure` at ~80, `/ec2:think-tank` at ~80). Skills delegate all non-trivial work to the broker via MCP tools.

| Skill | Purpose |
|-------|---------|
| `/ec2:recall` | Hybrid search across tiers |
| `/ec2:status` | Broker + model + store stats |
| `/ec2:graph` | Call graph |
| `/ec2:recent` | Git-aware recent files |
| `/ec2:ingest` | Ingest docs |
| `/ec2:index` | Force re-index |
| `/ec2:configure` | All settings (consolidates v1's five config skills) |
| `/ec2:profile` | User profile mgmt |
| `/ec2:promote` | Promote memory to durable/global tier |
| `/ec2:sidecar` | Inspect/manage small model scratch |
| `/ec2:agents` | Manual subagent briefing |
| `/ec2:second-opinion` | External model review (OpenRouter) |
| `/ec2:think-tank` | Multi-agent brainstorm |
| `/ec2:changelog` | Update CHANGELOG.md before commit |
| `/ec2:git-versioning` | Conventional commits / semver |
| `/ec2:cicd` | CI/CD setup |
| `/ec2:pdf-convert` | PDF → text/md |
| `/ec2:modules` | Self-extending tools (redesigned around small model) |
| `/ec2:feeds` | RSS briefing |
| `/ec2:merits` | Gamification |

### Dropped from v1

- `/ec:persona` — persona system removed in v2.

### New in v2

- `/ec2:promote`
- `/ec2:sidecar`
- `/ec2:agents`

## Hooks (5)

| Hook | Event | Behavior |
|------|-------|----------|
| SessionStart | Session begins | Spawn broker if needed; load identity + project mental model (~300 tok) |
| UserPromptSubmit | Every user message | Inject top-3 retrieved memories (≤800 tok). No reminders. |
| PreToolUse:Read/Grep/Glob | Before file/search tool | Inject `<memory-context>` (≤300 tok) |
| PreToolUse:Agent | Before subagent dispatch | Auto-brief (≤500 tok) unless `<no-brief/>` in prompt |
| PostToolUse:Edit/Write | After file change | Re-index file; queue for consolidation |

## Project Structure

```
elephant-coder2/
├── broker/
│   ├── __init__.py
│   ├── server.py           # Unix socket server, main loop
│   ├── store.py            # Redis + SQLite + FTS5 + numpy unified store
│   ├── retriever.py        # Hybrid retrieval + tier merging
│   ├── sidecar.py          # llama-cpp-python wrapper + prompt templates
│   ├── indexer.py          # File → memory capsules (AST + regex)
│   ├── consolidator.py     # Idle-time small-model tasks
│   └── tasks.py            # Background task queue + push notify
├── mcp/
│   └── server.py           # MCP server exposing the 12 tools
├── hooks/                  # 5 hook scripts
├── skills/                 # 20 skill markdown files
├── commands/               # Slash command defs
├── tests/
├── pyproject.toml
├── plugin.json
├── CLAUDE.md               # Minimal — broker handles activation
└── README.md
```

## Tech Stack

- Python 3.12+
- `llama-cpp-python` (Vulkan-enabled, user's global install)
- `redis>=7.3.0` (primary read cache)
- SQLite (stdlib) + FTS5
- `numpy>=1.26.0`
- `sentence-transformers>=3.0.0` (`all-MiniLM-L6-v2`, 384-dim)
- `mcp>=1.2.0`
- `httpx>=0.27.0` (OpenRouter / RSS)
- `pypdf>=4.0.0` (PDF conversion)
- `pyyaml>=6.0` (settings)

### Dropped from v1

- `qdrant-client` — small model + numpy covers semantic retrieval.

## Storage Layout

```
~/.elephant-coder2/
├── broker.sock              # Unix socket for hook → broker
├── broker.pid
├── models/
│   └── qwen2.5-1.5b-instruct-q4_k_m.gguf
├── sidecar/
│   └── consolidation.log    # Small model's decision trail
├── projects/
│   └── <project-hash>/
│       ├── memories.db      # scratch + project_durable (SQLite+FTS5)
│       ├── vectors.npy
│       └── vector_index.json
└── global/
    ├── memories.db          # global_durable + user profile
    └── vectors.npy

.claude/
├── elephant-coder2.local.md   # Per-project settings (YAML frontmatter)
```

## Settings

Per-project in `.claude/elephant-coder2.local.md` (YAML frontmatter).

### Storage

| Setting | Default | Description |
|---------|---------|-------------|
| `max_scratch_entries` | 32,000 | Per-project scratch tier cap |
| `max_durable_entries` | 50,000 | Per-project durable cap |
| `redis_url` | `redis://localhost:6379` | Redis URL |
| `redis_ttl` | 1 year | Redis entry TTL |
| `scratch_idle_consolidation_minutes` | 10 | Interval between consolidation passes |

### Small model

| Setting | Default | Description |
|---------|---------|-------------|
| `sidecar.model_path` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | GGUF file name (relative to `~/.elephant-coder2/models/`) |
| `sidecar.n_gpu_layers` | -1 | Vulkan offload (-1 = all) |
| `sidecar.rerank_latency_ms` | 500 | Hard cap; fall back to raw rank on overrun |
| `sidecar.n_ctx` | 8192 | Context window |

### Hooks / injection

| Setting | Default | Description |
|---------|---------|-------------|
| `injection.prompt_budget_tokens` | 800 | UserPromptSubmit cap |
| `injection.tool_budget_tokens` | 300 | PreToolUse:Read/Grep/Glob cap |
| `injection.agent_brief_tokens` | 500 | PreToolUse:Agent cap |

### External

| Setting | Default | Description |
|---------|---------|-------------|
| `external_validation.openrouter_api_key` | null | For `/ec2:second-opinion` |
| `external_validation.model` | `google/gemini-3.1-flash-lite-preview` | External model |

## Testing Approach

- **Broker unit tests:** store (Redis+SQLite round-trip, FTS5 search, tier flipping), retriever (hybrid rank, tier merging), sidecar (prompt templating with model mocked), indexer (AST + regex extraction), consolidator (dedup decisions with model mocked).
- **MCP integration tests:** each of the 12 tools round-trips via a live broker.
- **Hook script tests:** hook → socket → broker → enrichment string, per hook type.
- **End-to-end smoke:** spawn broker, run full hook sequence against a fixture project, verify memory injection appears correctly in simulated tool results.
- **Performance budget tests:** retrieval p95 < 200 ms, rerank p95 < 500 ms, hook round-trip p95 < 50 ms.

## Open Questions (defer to implementation)

- Exact Redis key schema (adopt v1's `ec2:{project_hash}:...` scheme or redesign).
- Consolidation prompt engineering — start simple, iterate as the model's decisions are observed via `consolidation.log`.
- GGUF model quantization tradeoff — Q4_K_M by default; power users can try Q6 or Q8 at their own latency cost.
- Windows compatibility of Unix-domain socket — may need named-pipe fallback on Windows (user's primary platform is Windows 11; this is likely worth addressing in the implementation plan).

## Success Criteria

- Sessions run without the user ever saying "use elephant-coder".
- Token cost of elephant-coder's injection ≤ 1,200 tokens on typical user turns (down from v1's ~2,000-3,000).
- Subagents dispatched via Agent tool receive auto-briefs and can write back via `sidecar_store`.
- Consolidation log shows the small model making deduplication / decay decisions autonomously over multi-hour idle periods.
- `global_durable` tier accumulates promoted entries over weeks of use, and cross-project `recall` calls return relevant results from other projects.
