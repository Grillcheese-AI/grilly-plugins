---
name: index
description: Index the full project codebase with elephant-coder (all file types)
---

Run elephant-coder `index_all()` to index all supported file types in the project.

This replaces the old approach of 14 parallel index_directory() calls.
One call, all patterns, batch upserts. Much faster.

After indexing, run `memory_status()` and report the summary.

Unchanged files are automatically skipped (mtime check), so this is safe to run repeatedly.
