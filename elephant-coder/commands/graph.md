---
name: graph
description: Show call graph for a symbol — what calls it and what it calls
---

The user wants to see the dependency graph for a symbol. Use the name they provided after `/ec:graph`.

Run `show_call_graph(symbol=<name>, depth=2)` and present the results.

If the symbol isn't found, suggest alternatives using `search_symbols` or `recall_memories`.
