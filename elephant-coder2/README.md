# elephant-coder2

Automatic memory activation for Claude Code.

v2 of elephant-coder — rebuilt for token efficiency, agentic work, and cross-project knowledge. See `docs/superpowers/specs/2026-04-17-elephant-coder2-design.md` in the parent repo.

**Status:** Minimal runnable (v0.2.0). MCP server (`mcpd/server.py`) exposes
7 memory tools — `status`, `index`, `recall`, `recall_file`, `search_symbol`,
`remember`, `promote` — backed by the broker + SQLite/FTS5 + numpy-vector store.
No GGUF sidecar or hooks yet (recall uses raw FTS+vector merge). See CHANGELOG.
