---
name: index
description: Index the full project codebase with elephant-coder (all file types)
---

Run elephant-coder index_directory for ALL supported file types in the project. Execute these in parallel:

1. `index_directory(path='.', patterns='**/*.py')`
2. `index_directory(path='.', patterns='**/*.cpp')`
3. `index_directory(path='.', patterns='**/*.h')`
4. `index_directory(path='.', patterns='**/*.c')`
5. `index_directory(path='.', patterns='**/*.hpp')`
6. `index_directory(path='.', patterns='**/*.glsl')`
7. `index_directory(path='.', patterns='**/*.md')`
8. `index_directory(path='.', patterns='**/*.toml')`
9. `index_directory(path='.', patterns='**/*.json')`
10. `index_directory(path='.', patterns='**/*.yaml')`
11. `index_directory(path='.', patterns='**/*.yml')`
12. `index_directory(path='.', patterns='**/CMakeLists.txt')`
13. `ingest_knowledge(path='docs/official_papers')`
14. `ingest_knowledge(path='docs/project_knowledge')`

After all complete, run `memory_status()` and report the summary.

Unchanged files are automatically skipped (mtime check), so this is safe to run repeatedly.
