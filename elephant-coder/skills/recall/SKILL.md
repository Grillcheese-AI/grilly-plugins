---
name: recall
description: Search elephant-coder memories for code, symbols, or concepts
---

The user wants to search their codebase memory. Use the query they provided after `/ec:recall`.

1. First try `search_symbols(name=<query>)` for exact symbol matches
2. Then try `recall_memories(query=<query>, limit=10)` for full-text search
3. Present results clearly with file paths and summaries

If no results found, suggest the user run `/ec:index` first to populate the memory store.
