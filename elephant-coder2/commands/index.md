---
name: index
description: Index the current project into elephant-coder2 memory (all supported file types)
---

Call the elephant-coder2 `index` tool with no `path` argument to index the whole
project. It walks the project, dispatches each file to the right indexer
(Python AST / regex for TS·JS·C·GLSL / structured for md·toml·json·yaml), and
**mtime-skips unchanged files**, so it is safe to run repeatedly.

To index a single file or subdirectory, pass `path`.

After indexing, call the `status` tool and report the summary: indexed files,
total entries, per-tier counts, vector count, and Redis state.
