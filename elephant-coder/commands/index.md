---
name: index
description: Index the full project codebase with elephant-coder (all file types)
---

Run elephant-coder `index_all()` to index all supported file types in the project.

This is a single call that handles all patterns internally with batch upserts.
Unchanged files are automatically skipped (mtime check), so this is safe to run repeatedly.

After indexing, run `memory_status()` and report the summary.
