---
name: recall
description: Search elephant-coder2 memory (hybrid FTS + vector) for code, symbols, or notes
---

Take the user's query (the text after the command) and call the elephant-coder2
`recall` tool with it. Recall runs a hybrid search — SQLite FTS5 + numpy cosine
vector similarity, merged — across the memory tiers and returns compact entry
briefs (symbol, file, kind, tier, summary, score), best first.

Optional refinements the user may ask for:
- `limit` — how many results (default 5).
- `tier` — restrict to one of `scratch`, `project_durable`, `global_durable`.

Present the ranked hits concisely. For follow-up on a specific file, use the
`recall_file` tool; for an exact symbol, use `search_symbol`.
